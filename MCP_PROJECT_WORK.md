# MCP transfers and authorized project work

This is separate from `ask_codex`/`ask_claude`. Consultations retain their isolated,
read-only supplied-context behavior. `project_submit` authorizes an implementation
worker with shell tools and project edits; it can consume ChatGPT subscription
usage. No model is called to upload, retrieve, inspect status, or cancel work.

## Tools and exact contracts

[MCP_TOOL_SCHEMAS.json](MCP_TOOL_SCHEMAS.json) contains the exact registered input
schemas, including required properties, types and defaults. There are seven new tools:

| Tool | Arguments |
| --- | --- |
| `transfer_upload` | `files: [{filename: string, content_base64: string}]` |
| `transfer_manifest` | `direction: "inbound" or "outbound", transfer_id: string` |
| `transfer_read` | `direction, transfer_id, filename: string` |
| `project_submit` | `assignment: string, acceptance_criteria: string[], project_id: string, authority: {edit: boolean, test: boolean, commit: boolean, push: boolean}, inbound_transfer_ids: string[] or null = null, deadline_seconds: integer = 600, memory_mb: integer = 2048, cpu_seconds: integer = 600` |
| `project_status` | `job_id: string` |
| `project_result` | `job_id: string` |
| `project_cancel` | `job_id: string` |

All calls use the existing authenticated loopback MCP endpoint. There is no new
endpoint, destination-project argument in transfer tools, caller-supplied command,
allowlist argument, or caller-selected worker model. IDs are 32 lowercase hex
characters. Successful responses have `status: "ok"`; validation/storage failures
have `status: "error", error: {code: ...}`. MCP schema failures are tool errors.

`transfer_upload` returns the transfer ID, direction, complete state, encoding and
file manifest. Every entry has its original filename, `size_bytes`, and `sha256`.
`transfer_manifest` verifies all files before returning that manifest.
`transfer_read` verifies the whole transfer, then returns the selected entry plus
`content_base64`. Both inbound readback and outbound retrieval use it.

`project_submit` returns the durably recorded job ID, queued state and timestamp
without waiting for worker execution. Status omits assignment/result text;
result includes the stored assignment, authority, criteria, timestamps, limits,
worker result, current and initial working-tree status, errors, and outbound ID.
Cancellation is idempotent for terminal jobs; poll status to confirm termination.

Job timestamps are UTC. Acceptance follows durable storage; queue and execution
durations use a monotonic clock and are reported separately. Cancellation records
the request and confirmed worker stop separately. Recovery records interruption
discovery and last activity; an unobserved worker stop remains unknown.

## Encoding, limits and storage

Binary transport is strict canonical RFC 4648 base64 with padding, no whitespace
or URL-safe substitutions. Encode the original bytes, not a reserialized string.
SHA-256 and sizes always refer to decoded bytes. UTF-8 is only needed when a
client chooses to interpret a text file; no newline or encoding conversion occurs.

| Limit | Value |
| --- | --- |
| Individual decoded file | 2 MiB, inclusive |
| Total decoded transfer | 8 MiB, inclusive |
| Files per transfer | 1–16 |
| Encoded HTTP POST body / upload payload | 12 MiB; HTTP envelope counts too |
| Encoded single-file response | 3 MiB JSON payload (MCP envelope is small extra overhead) |
| Filename | 128 UTF-8 bytes |
| Assignment | 32,768 UTF-8 bytes |
| Acceptance criteria | 1–20 unique nonempty strings, 512 UTF-8 bytes each |
| Verified input transfers per job | At most 8 unique IDs, 8 MiB decoded aggregate |
| Pending jobs | At most 32 across queued/running jobs |
| Wall deadline | 10–1,800 seconds from submission, including queue time |
| Address-space hard limit | 512–8,192 MiB; default 2,048 |
| CPU hard limit | 10–1,800 seconds per process; default 600, hard grace of 1 second |
| Worker stdout / structured result | 1 MiB each; excessive stdout terminates the worker |
| Worker-created file / open descriptors | 16 MiB per file / 256 per process |

Inbound files live under `/home/jachee/projects/mcp-inbound/<transfer_id>/`;
outbound files under `/home/jachee/projects/mcp-outbound/<transfer_id>/`. Both
roots are private `0700` and inside the approved projects root. File and manifest
creation uses `0600`; the service already has umask `0077`.

Each publication first writes a private `.pending-<id>/`, verifies every decoded
file, fsyncs files/manifest/directory, then publishes using Linux
`renameat2(RENAME_NOREPLACE)` and fsyncs the root. Publication never overwrites an
existing transfer. Interrupted unpublished directories are removed under the
store's exclusive lock at startup; in-process failures clean their own staging
directory. Unexpected staging subdirectories or symlinks fail closed instead of
recursively following an arbitrary tree. Completed transfers have no mutation API.
Retention of completed transfers and job records is manual; there is no global
disk quota or automatic deletion of completed data in this bootstrap.

Operations pin directory descriptors from `/` through every ancestor with
`O_DIRECTORY|O_NOFOLLOW`. Files use relative dirfd opens with `O_NOFOLLOW`, regular
file/single-link checks, bounded reads and hash verification. Swapping an ancestor
after it is opened cannot redirect writes into a symlink target. A local owner
can still alter stored files; readback detects corruption, and accepted jobs also
compare the original receipt with the manifest reverified at execution time.

Absolute filenames, separators (`/`, `\\`, `:`), traversal, control characters,
case/NFC-equivalent duplicates, and the reserved `manifest.json` are rejected.
Missing/incomplete IDs, missing files, malformed manifests/base64, oversized
payloads, corruption, and invalid/symlinked files return distinct error codes.

## Credential exclusions

Excluded names are `auth.json`, `bridge.token`, `anthropic.key`,
`codex-auth-cache.json`, `.netrc`, `.npmrc`, `.gitconfig`, `credentials`,
`credentials.json`, `id_rsa`, `id_dsa`, `id_ecdsa`, and `id_ed25519`; matching is
case-insensitive. `.env`, `.env.*` and `.key`, `.pem`, `.p12`, `.pfx` suffixes are
also excluded. Publication checks file names and decoded bytes for the bridge's
known bearer/API credentials and saved/cached Codex token values. Those known
values are rejected in assignments and redacted in saved results and stdout.
Raw worker stderr is discarded. Invalid raw result files are deleted, valid
results are replaced with their sanitized form, and isolated authentication homes
are removed after execution, including failure/cancellation.

Filename filtering and known-value checks cannot identify every secret embedded
in arbitrary content. Clients/workers must not submit or publish unknown private
credentials. A response's intended file bytes are never silently redacted:
unsafe content is rejected instead, preserving the byte-exact transfer contract.

## Authorization and worker isolation

Only `project_id: "model-bridge"` maps to the bootstrap project
`/home/jachee/projects/acheedev/model-bridge`. The allowlist is a server constant;
assignment text cannot add projects. This bootstrap accepts exactly
`{"edit":true,"test":true,"commit":false,"push":false}`. Other authorities,
including read-only jobs or permission to commit/push, are rejected rather than
quietly expanding support. Both edit and test permission are required because
this worker exposes general project shell tools, not a command classifier.

The installed mechanism verified for this bootstrap is Codex CLI
`0.162.0-alpha.17.2`. Bundled offline catalog inspection confirms `gpt-5.5` is
present without a code-mode-only requirement; it is the fixed worker model.
The worker launches independently through `project_worker.py`, with isolated file
authentication, explicit permissions, strict configuration, ephemeral sessions,
no automatic approval/escalation, and no imported user configuration/rules.
Project configuration is treated as untrusted. Apps, MCP integrations, plugins,
hooks, nested agents and daemons are disabled. Recursion markers also reject
direct bridge/runtime submissions from a child. Consultation settings are not reused.

The permissions profile gives write access to this project and its fixed `.tmp/`,
runtime dependencies read access, `.git` read-only access, `.venv` read-only access,
and denies job state. Only the active job's verified inputs are mounted read-only
from the separate project `.worker-inputs/` directory, whose project ancestor is
traversable. This avoids placing an input mount below the denied state directory.
The serialized supervisor clears active copies before and after each execution;
after an interruption it clears stale copies before launching another worker.
Existing project `.codex` is denied and existing `.agents` is read-only. Host paths
outside the permitted project/runtime mounts are not readable or writable.
Some absent paths in the sandbox's synthetic ancestor directories can be written
as disposable tmpfs scratch; this does not modify the outside host filesystem.
`/tmp` is not writable. Shell networking is disabled, including loopback access
to the bridge; the outer CLI still uses its authenticated model connection.

Read-only project `.git` blocks commits to this repository, and kernel-enforced
shell network restrictions block remote network pushes. The environment additionally
sets Git's default `protocol.allow=never`. These are enforcement beyond prompt
instructions. This is not a universal ban on manufacturing commits or local
pushes inside authorized scratch directories: a deliberately adversarial command
can override Git environment defaults there. Such actions remain prohibited by
the assignment. Authorized edits can change the bridge's source; an administrator
must review changes before restarting it. This bootstrap is not a hostile-code
multi-tenant isolation system and grants no systemd or host-administration access.

## Persistence, serialization and failure recovery

State lives in Git-ignored `model-bridge/job-data/`: `jobs.sqlite3` and one private
directory per job with launcher configuration, result schema and
sanitized result. SQLite commits with synchronous FULL happen before acceptance
returns. A nonblocking process lock prevents competing supervisors. The single
supervisor runs one job at a time, serializing this allowlisted project's work.

States are `queued`, `running`, `succeeded`, `failed`, `cancelled`, `interrupted`.
Terminal records preserve timestamps, errors, process exit code when available,
worker claims and working-tree status. A zero process exit alone is insufficient:
the final structured result must contain `completed: true` and one successful
result for every exact acceptance criterion. `succeeded` records the worker's
completion claim, not independent verification of every assertion it made.

Deadlines, output limits and cancellation terminate the private process group
with TERM followed by KILL; CPU/address-space/file/descriptor/core limits are
installed before exec and inherited by descendants. CPU/memory limits are per
process, not cgroup-wide budgets; there is no hard process-count limit. A hostile
process deliberately escaping its group is outside that cancellation guarantee.
The existing service's verified `KillMode=control-group` additionally cleans
descendants on service restart; its 10-second stop deadline is unchanged.

On restart, both queued and running records become `interrupted`, with no
automatic replay. Inspect partial project edits and explicitly submit new work
if desired. A CLI crash/nonzero exit, timeout, invalid/missing completion report,
failed criterion, corrupted input, excessive stdout, or artifact failure makes
the job failed. Cancellation/failure never resets, cleans or reverts the working
tree. The initial/current status records help distinguish existing work from the
partial state; they are not a full backup of original file contents.

Outbound publication is controlled by the supervisor, not an arbitrary MCP caller.
It exports a sanitized `job-result.json`, bounded `worker-output.txt`, and the
worker's approved relative artifact paths. Artifact reads use no-follow dirfd
operations, size limits and credential exclusions; Git/config/environment/state
paths are excluded. Missing, duplicate or unsafe artifacts fail publication.
Failure results remain durable and get a report-only outbound transfer when
possible. A storage failure may leave no outbound ID; `project_result` still
returns the persisted outcome. Project edits and prepared files remain available
locally for recovery. Cancellation of a never-started queued job has no artifacts.

## Client proof: actual Windows files, then a separate assignment

No copies of Mimi's Windows `README.md` or `PROJECT_SPEC.md` were supplied during
this bootstrap. They have not been transferred or incorporated. This document is
implementation documentation, not a substitute for either file.

1. Refresh/reconnect the MCP client after the existing service is restarted and
   confirm all seven tools appear. `bridge_ping`/tool discovery need no model.
2. Read each actual Windows file as bytes, calculate SHA-256, and base64-encode
   those bytes. Submit both in **one** `transfer_upload` call:

   ```json
   {"files":[
     {"filename":"README.md","content_base64":"<base64 of actual README bytes>"},
     {"filename":"PROJECT_SPEC.md","content_base64":"<base64 of actual spec bytes>"}
   ]}
   ```

3. Save the returned inbound transfer ID and manifest. Call `transfer_read` twice
   with `direction:"inbound"`, that ID and each filename. Decode the returned
   base64; compare each decoded byte sequence, size and SHA-256 against its Windows
   original. Do not submit project work if either comparison fails.
4. Only after both comparisons pass, submit a **separate** `project_submit`:

   ```json
   {
     "assignment":"Read the two verified reference documents. Report concerns/questions. Incorporate them into the repository root while preserving useful existing documentation, then begin Technical completion assigned to Ezra. Do not commit or push.",
     "acceptance_criteria":[
       "Both verified documents were read and concerns/questions reported",
       "Repository documentation incorporates the supplied documents while preserving useful existing material",
       "Technical completion assigned to Ezra has begun with an accurate progress report"
     ],
     "project_id":"model-bridge",
     "authority":{"edit":true,"test":true,"commit":false,"push":false},
     "inbound_transfer_ids":["<verified inbound transfer ID>"],
     "deadline_seconds":600,
     "memory_mb":2048,
     "cpu_seconds":600
   }
   ```

5. Poll `project_status(job_id)`, then `project_result(job_id)`. Read the outbound
   manifest and retrieve its files with `transfer_read(direction:"outbound",...)`.
   Check hashes again. Use `project_cancel(job_id)` if the separate job must stop.

The server rechecks input hashes but cannot know whether a Windows client actually
performed its comparison; providing IDs is the caller's explicit verification
assertion. The separate documentation assignment has not been started here.

Installed sandbox behavior was tested without inference. Actual model-driven
project completion still needs the separately authorized client proof. Official
[permissions documentation](https://learn.chatgpt.com/docs/permissions) describes
the underlying runtime controls; local probes, not that documentation alone,
establish this installation's observed containment behavior.
