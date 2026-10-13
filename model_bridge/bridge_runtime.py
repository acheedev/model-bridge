"""MCP registration for transfers and separately authorized implementation jobs."""
import os
from typing import Literal
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr
from .file_transfers import TransferError, TransferStore
from .project_jobs import JobError, JobManager
from .staged_work import StageError


class Runtime:
    def __init__(self, secrets_provider):
        self.transfers = TransferStore(secrets_provider=secrets_provider)
        self.jobs = JobManager(self.transfers, secrets_provider=secrets_provider)

    def close(self):
        self.jobs.close()


class TransferFile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    filename: StrictStr
    content_base64: StrictStr


class ApplyAuthority(BaseModel):
    model_config = ConfigDict(extra='forbid')
    apply: StrictBool
    test: StrictBool
    commit: StrictBool
    push: StrictBool


class Authority(BaseModel):
    model_config = ConfigDict(extra='forbid')
    edit: StrictBool
    test: StrictBool
    commit: StrictBool
    push: StrictBool


def register_tools(mcp, get_runtime):
    def invoke(action):
        if os.environ.get('MODEL_BRIDGE_CHILD') or os.environ.get('PROJECT_WORKER_CHILD'):
            return {'status': 'error', 'error': {'code': 'recursive_bridge_call'}}
        try:
            return {'status': 'ok', **action(get_runtime())}
        except StageError as error:
            return {'status': 'error', 'error': {'code': str(error),
                    **get_runtime().jobs.sanitize(error.details)}}
        except (TransferError, JobError) as error:
            return {'status': 'error', 'error': {'code': str(error)}}
        except (OSError, ValueError):
            return {'status': 'error', 'error': {'code': 'filesystem_or_input_failure'}}

    read = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)

    @mcp.tool(annotations=write)
    def transfer_upload(files: list[TransferFile]) -> dict:
        """Publish one inbound transfer. Each file has filename and strict content_base64.
        Max 16 files, 2 MiB/file, 8 MiB decoded total, 12 MiB encoded request.
        No project destination argument; returns ID, sizes and decoded SHA-256 hashes.
        """
        return invoke(lambda runtime: runtime.transfers.accept([file.model_dump() for file in files]))

    @mcp.tool(annotations=read)
    def transfer_manifest(direction: Literal['inbound', 'outbound'], transfer_id: str) -> dict:
        """Verify every file/hash and retrieve a completed transfer's manifest."""
        return invoke(lambda runtime: runtime.transfers.load(direction, transfer_id)[0])

    @mcp.tool(annotations=read)
    def transfer_read(direction: Literal['inbound', 'outbound'], transfer_id: str, filename: str) -> dict:
        """Retrieve one byte-exact file as base64; at most 3 MiB encoded response.
        Both inbound readback and outbound retrieval use this tool.
        """
        return invoke(lambda runtime: runtime.transfers.retrieve(direction, transfer_id, filename))

    @mcp.tool(annotations=write)
    def project_submit(assignment: str, acceptance_criteria: list[str], project_id: str,
                       authority: Authority, inbound_transfer_ids: list[str] | None = None,
                       deadline_seconds: int = 600, memory_mb: int = 2048, cpu_seconds: int = 300,
                       target_paths: list[str] | None = None, idempotency_key: str | None = None,
                       dependency_job_ids: list[str] | None = None) -> dict:
        """Durably queue an isolated staged worker. target_paths (1..8 text files) required.
        Edit/test authority never applies to the live repo. Optional idempotency_key
        returns the original job; changed input with the same key is rejected.
        Manual dependencies must have verified successful outbound IDs supplied as inputs.
        At most two workers with second-slot memory admission; eight pending.
        Only project_id=model-bridge is allowlisted. Bootstrap authority must be
        exactly edit=true, test=true, commit=false, push=false. Inbound IDs must
        already be client-verified; server checks completion/hashes at acceptance
        and execution. Deadline 10..1800s includes queue time; memory 512..8192 MiB;
        CPU 10..1800s. Returns a job ID promptly; never blocks for model completion.
        """
        return invoke(lambda runtime: runtime.jobs.submit(assignment, acceptance_criteria, project_id, authority.model_dump(),
                      inbound_transfer_ids, deadline_seconds, memory_mb, cpu_seconds, target_paths, idempotency_key, dependency_job_ids))

    @mcp.tool(annotations=read)
    def project_status(job_id: str) -> dict:
        """Read durable job state, timestamps, limits, error and outbound transfer ID."""
        def action(runtime):
            job = runtime.jobs.get(job_id)
            return {k: v for k, v in job.items() if k not in ('assignment', 'acceptance_criteria', 'result', 'inbound_transfers', 'working_tree_before', 'partial_changes', 'snapshot_inventory', 'base_manifest')}
        return invoke(action)

    @mcp.tool(annotations=read)
    def project_result(job_id: str) -> dict:
        """Read the durable assignment/result and partial-change record, plus artifact references.
        Substantial output is retrieved with transfer_read using outbound_transfer_id.
        """
        return invoke(lambda runtime: runtime.jobs.get(job_id))

    @mcp.tool(annotations=write)
    def project_cancel(job_id: str) -> dict:
        """Cancel queued work or request process-tree termination; preserve partial edits."""
        return invoke(lambda runtime: runtime.jobs.cancel(job_id))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False))
    def project_apply(job_id: str, bundle_hash: str, base_hash: str, authority: ApplyAuthority) -> dict:
        """Explicit guarded application of a succeeded staged bundle. Requires apply=true,
        test=false, commit=false, push=false; testing is separately authorized.
        Serialized per repo, refuses stale/escaped/tampered targets. Writers must
        cooperate: no manual edits during application. Partial failures require review.
        """
        return invoke(lambda runtime: runtime.jobs.apply(job_id, bundle_hash, base_hash, authority.model_dump()))

    @mcp.tool(annotations=write)
    def project_review(job_id: str, pinned: bool = False) -> dict:
        """Explicitly mark a terminal job reviewed; releases its default retention pin."""
        return invoke(lambda runtime: runtime.jobs.review(job_id, pinned))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False))
    def project_retention(apply: bool = False, job_ids: list[str] | None = None) -> dict:
        """Preview retention or explicitly clean named eligible jobs. Never runs automatically.
        Protect active/unreviewed/pinned/referenced work. Reviewed bulk: 7 days;
        summaries: compact at 90 days while keeping duplicate-operation tombstones.
        """
        return invoke(lambda runtime: runtime.jobs.retention(apply, job_ids))
