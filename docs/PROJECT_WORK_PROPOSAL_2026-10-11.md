# Project work: lifecycle evidence and decisions for John

Update October 12: John approved this scope; local implementation and tests are delivered. The design below is the historical approval record. Current status: [staged pilot](STAGED_PILOT_2026-10-12.md). Installed activation/client proof remains pending.

Scope: Ubuntu `/home/jachee/projects/acheedev/model-bridge`. No provider calls,
production cancellation, installed service/configuration/permission changes,
restart, commit, or push. Production worker code and current authorization
contracts are unchanged. The only implementation additions are a disposable
non-model demo and its focused integration tests; checklist/validation edits
record their evidence and the design proposals below.

## Outcome and decision table

| Item | This assignment | Next decision/action |
| --- | --- | --- |
| 3.8 concurrent-change protection | Architecture inspected; integrated implementation stopped as a substantial staging/apply change | Approve the small staged-worker pilot and apply contract below; remains unchecked |
| 3.9 authorized application | Acceptance/fixture plan prepared; no production patch applied | Prove staged clean/stale cases first, then separately authorize a production apply |
| 4.4 cancellation | Real registered handlers/process groups/durable fixtures passed; no wiring gap found | Installed-client proof remains pending; use the disposable demo now |
| 4.5 recovery | Abrupt isolated supervisor crash and durable recovery passed | Real installed-service restart proof remains pending and was not performed |
| 4.6 state/retention/disk | Immediate-versus-advanced split accepted; immediate parameters proposed only | Implement the small supervisor safeguards after parameters are agreed; advanced recovery stays backlog |
| 4.7 parallelism/retries/dependencies | CRITICAL delivery item; phased implementation/proof brief prepared | Approve remaining scope/budget choices, then execute phases end to end; not completed by design |
| 3.10 parameters | Concrete allowlist/transport/resource proposal only | Agree on policy; no broader project access granted |
| 4.8 pause/resume | Backlog | No implementation in this scope |
| 4.9 one-hour proof | Backlog by John's instruction | No hour job run; later simulator is mechanics evidence only |

## A. Why 3.8 needs staging, and the smallest coherent pilot

`JobManager.execute_with_inputs` currently gives the worker shell write access
to the original project; it records status before/after and exports artifacts.
No separate apply step exists. Recording a diff/hash after direct edits cannot
prevent the worker from having already overwritten a concurrent human edit.
The one-project authority currently grants edit/test directly, not a separate
apply capability. Keeping that path and adding a posthoc comparison would be a
false 3.8 completion claim.

A coherent fix touches snapshot creation, sandbox write roots, per-job inputs,
artifact collection, durable delivery state, and the apply contract. That is
substantially larger than a guard added at one line. Implementation of this
part stops here under the assignment's explicit fallback; no staging/apply
framework or production protection was silently substituted.

Proposed first pilot, still the one model-bridge project:

1. Accept an explicit targeted relative-path set and immutable baseline manifest
   before launching the job. Record existence, SHA-256 of exact bytes, file type,
   mode, and receipt hash. An addition has expected absence; a deletion has an
   expected original hash. Modified/untracked caller files must be represented
   as they exist now, not reconstructed only from Git HEAD.
2. Construct a filtered per-job workspace under an approved staging root. Only
   that job's workspace/scratch is writable to the worker; the original target
   checkout is denied for write. Dependencies/source references are narrowly
   read-only. Exclude state, private/credential files, Git/config content not
   needed for the task, and other jobs' inputs/staging. Never follow symlinks.
   The installed CLI sandbox mount behavior needs its own later validation.
3. Deliver a real UTF-8 unified diff plus base manifest and after-file hashes,
   without applying it. Keep exact replacement bytes as bounded artifacts to
   verify that the diff reproduces the advertised result. Initially reject
   binary/unsupported encodings rather than silently rewriting them.
4. A separate supervisor apply operation binds project ID, job ID, bundle hash,
   expected baseline-manifest hash, exact paths, and explicit apply/test
   authority. Worker edit authority never implies production application.
5. Acquire the project's apply lock, validate every target before any write,
   pin approved-root ancestors using no-follow dirfds, reject traversal,
   symlink/hard-link/special-file paths, and refuse changed contents/existence.
   Touch only declared targets; preserve unrelated files. Additions require
   exclusive creation; deletions require the matching base. Do not use shell
   patch commands assembled from caller paths.
6. Journal prepared operations/before-images and completion receipts durably.
   Recheck immediately before each operation and verify output hashes. Multi-file
   filesystem application is not a SQLite transaction: after a crash, retain
   evidence and require review of partially applied targets, never blind replay.

Important design limit: project locks serialize bridge-controlled apply steps,
not arbitrary editor processes that ignore that lock. Hash preflight has a race
window against outside writes. The agreed pilot must require cooperating
writers/no manual edits during the short apply window, recheck pinned targets,
and report conflict/partial application honestly. A blanket atomic compare-and-
swap guarantee for arbitrary outside writers is not supported by this design.
John must accept this boundary or request a stronger, more expensive isolation
mechanism before 3.8 is called complete.

Prepared 3.9 fixture acceptance matrix, NOT implemented/run in this assignment:

| Case | Required outcome |
| --- | --- |
| Clean edit/add/delete bundle | Apply exact expected bytes and modes; persist receipt; preserve unrelated edits |
| Edited/deleted original or newly existing addition | Refuse all targets in preflight; no production writes |
| Missing/wrong base receipt or bundle tampering | Refuse before application |
| Parent/file symlink swap, traversal, hard link, outside root | Refuse without following/writing outside the root |
| Duplicate identical apply receipt | Return previous receipt; do not apply twice or overwrite newer edits |
| Failure after some filesystem operations | Mark partial/interrupted application, preserve journal, require review |

Current direct-edit jobs remain direct-edit jobs and do not acquire this
protection by reading the proposal. No clean/stale patch demo was claimed: those
fixtures depend on the stopped staging/apply implementation.

## B-C. Deterministic cancellation and crash/recovery demo

Added `scripts/demo_project_lifecycle.py` and `tests/test_project_lifecycle_demo.py`.
The script creates a fresh Git fixture, SQLite job store, transfer roots, and
stub Python worker exclusively under the checkout's `.tmp/`. Its internal
model-bridge ID maps to that fixture only through constructor injection; the
production allowlist is unchanged. It refuses execution from a marked project
worker context. No protected credentials, provider SDK inference, installed MCP
service, or production job store are used.

Cancellation uses the actual registered project_submit/status/cancel/result
and transfer_manifest/read handlers. A stub worker creates a grandchild and a
partial checkpoint file. The real launcher/process-group kill path stops them
(stopped or briefly zombie, not executing), preserves the file and an unrelated
caller fixture, and publishes a cancelled result. Readback independently checks
bytes, size, SHA-256, and cancelled job identity. Repeated cancel is idempotent;
a queued successor succeeds. Reopening the isolated manager retains both states.

Recovery deliberately exits only a disposable supervisor without cleanup while
one job runs and another is queued. The harness then stops only its positively
identified fixture group and constructs a new isolated manager. Both jobs become
interrupted; discovery/last-activity fields exist while actual stop/finish times
remain unknown to the manager. Partial project files and before-status survive.
No interrupted job is queued/replayed, and a newly submitted fixture succeeds.
This does not test a real systemd restart or provider/model reasoning.

Client iteration commands, from the Ubuntu checkout:

```bash
.venv/bin/python scripts/demo_project_lifecycle.py --scenario cancellation
.venv/bin/python scripts/demo_project_lifecycle.py --scenario recovery
# Or both short scenarios:
.venv/bin/python scripts/demo_project_lifecycle.py --scenario all
```

Run directly, outside project_submit. If inherited recursion markers are present,
use an authorized host terminal, not a restricted-worker workaround. Each run
prints JSON with tool/state checkpoints, timestamps, and duration and removes
its fixture afterward. Its IDs belong to removed fixtures; do not send them to
the production connector. A failed assertion means stop and inspect that specific
fixture behavior; do not cancel another job or restart the real service.

Installed-client proofs 4.4/4.5 remain unchecked. When separately authorized,
4.4 needs a dedicated safe production job and the same submit/status/cancel/
result/readback sequence. 4.5 needs a specifically authorized real restart with
known running/queued jobs and preserved evidence. This assignment authorizes
neither production action.

Two focused integration tests passed after adding exact readback assertions:
October 11, 23:13:42.407095–23:13:43.659126 EDT; 1.252030 monotonic subprocess
seconds; unittest 0.973 seconds; zero failures/errors/skips. Initial two tests
also passed before the stronger readback assertion; no full suite was rerun
because production source is unchanged. Earlier 109 full-suite and 13 focused
Gemini passes remain historical evidence, not a newly executed full run.

CLI demo: October 11, 23:12:34.788411–23:12:35.840858 EDT; 1.052448 monotonic
seconds for both scenarios. That run preceded the extra readback assertions;
the focused tests above exercise the final stronger demo code.

## D. CRITICAL 4.7: concrete next implementation, not indefinite roadmap

Keep one supervisor and the existing SQLite store. Do not merely add a second
thread: current `active` is singular and `.worker-inputs/` clears all copies.
Both must become per-job before overlapping work. Cancellation must address
only the selected process group; shutdown must account for both active groups.

Proposed dispatch: maximum two running jobs with separate staging/input/scratch
resources. Different approved projects or independent staged jobs can compute
concurrently. Apply operations serialize per original project and enforce 3.8.
With only one allowlisted project and no staging today, do not enable parallel
direct editors. No scheduler/retry implementation was made here. The concrete next assignment is
[NEXT_IMPLEMENTATION_BRIEF.md](NEXT_IMPLEMENTATION_BRIEF.md); after the remaining
scope/parameter vote it is a delivery task with explicit proof gates, not
indefinite research.

| Decision | Smallest recommended pilot |
| --- | --- |
| Worker concurrency | Configured maximum 2; resource admission can leave only 1 active |
| Apply concurrency | One apply operation per project; never two direct editors |
| Attempts | Initial attempt plus at most one eligible transient retry |
| Retry delay | Fixed 2-second backoff inside the original queue/execution deadline |
| Eligible retry | Proven pre-launch/local transient or idempotent non-model step with no published/partial writes |
| Ineligible retry | Ambiguous paid/provider outcome, CLI crash after model start, partial staged/live writes, timeout after send, auth failure, cancellation, or stale bases |
| Idempotency | Persist caller key + request hash, attempt ledger, output receipt, and apply receipt; reject key reuse with changed input |
| Dependencies now | Manual: submit B only after A succeeds and its output receipt/hashes are verified |
| Dependencies later | Add durable A->B edges only when automatic chaining is approved; failed/cancelled/interrupted A must block B |

The original deadline, authority, inputs, and result contract are not enlarged on
retry. Failed/ambiguous model calls need explicit review, not guessed transient
classification from a nonzero CLI exit. CPU limits currently apply per process;
resetting them on attempt two is not a proven total-job CPU budget. Aggregate
CPU/memory enforcement would require additional accounting/isolation and is not
claimed by this pilot. [Python resource-limit reference](https://docs.python.org/3/library/resource.html)

## E. 3.10 parameters for agreement, not access expansion

| Parameter | Proposed agreement |
| --- | --- |
| Project allowlist | Repos only under /home/jachee/projects/acheedev/; explicit model-bridge -> /home/jachee/projects/acheedev/model-bridge only until John names another specific repo; reject caller roots, traversal, and canonical/symlink escapes |
| Worker reads/writes | Filtered snapshot + its verified inputs/dependencies; write only its staging/scratch; no live target writes |
| Exclusions | private, credential names/content, .env variants, .git/.codex user config, transcripts, job state, other jobs' scratch/input/staging, symlinks/special files |
| Inbound/outbound | /home/jachee/projects/mcp-inbound/ and /home/jachee/projects/mcp-outbound/ are transfer-only roots, never repos; immutable bounded receipts/byte hashes; supervisor publication only |
| Patch delivery | Real unified diff + original existence/content hashes + output hashes; exact full artifacts through transfer_read; initially text-only |
| Apply authorization | Separate authenticated supervisor operation bound to stored project/job/bundle/base receipts and apply/test authority; never an inferred worker privilege |
| Truncation | No silently shortened patches/files; oversized/incomplete output fails with explicit reason, partial-stage evidence retained; never advertise a partial bundle as applicable |
| Model output limits | Report actual finish/truncation/usage and worker completion claims; an incomplete report is not success or an automatically safe retry |
| Per-job wall deadline | Current <=1800 seconds including queue/backoff; no automatic extension |
| Memory/CPU | Proposed default 2048 MiB address space and CPU 300 seconds per process; explicit overrides stay within current validated ranges |
| Queue | Current 32 pending supported; recommend pilot cap 8 pending with 2 active, subject to agreement |
| Transfer ceilings | Retain 2 MiB/file, 8 MiB/transfer, 16 files, <=8 inbound IDs with 8 MiB aggregate; count envelopes exactly as current transport does |
| Staging/disk | Proposed <=1 GiB per staging job, <=8 GiB aggregate retained work, >=1 GiB free before acceptance/publication; reject rather than truncate |
| Retention | Proposal below only; no deletion/policy implementation until agreement |

Host snapshot at 23:07:24.408764 EDT: 24 logical CPUs, about 7.64 GiB WSL-visible
RAM and 4.21 GiB available; about 927 GiB free on this project filesystem. These
are measurements of that checkpoint, not reservations or a guarantee of later
capacity. Two workers at nominal 2048 MiB leave little conservative headroom
at the observed available memory. Recommend a 5 GiB available-memory admission
threshold for the second slot (4 GiB nominal workers + 1 GiB headroom), otherwise
queue it. Address-space limits are not RSS reservations or cgroup-wide limits;
descendants can multiply resource consumption. Real model/CLI peak usage remains
unmeasured here. Do not change WSL memory settings in this scope.

John's boundary decision is accepted, not merely proposed: repo roots must be
canonical descendants of /home/jachee/projects/acheedev/ and explicitly named in
project-ID mappings. The parent does not authorize every descendant. Other
/home/jachee/projects siblings are not project roots. The two fixed transfer
roots have transfer-specific authority only. Credential stores remain protected
and excluded, not repos or transferable inputs. Existing broad approved_path
checks are general storage bounds, not sufficient project authorization: new
snapshot/apply paths must also enforce the exact registered repo, no-follow
ancestors, and the separate purpose-specific root. No production mapping was
broadened or changed by this design update.

Recommended deviations from the draft: reduce pending queue to 8 and gate the
second active slot on headroom. Keep 2048 MiB/300-second defaults as proposed,
subject to CLI fixture/peak validation; do not silently raise caps when a worker
fails. Proposed stage caps and future filtering need practical snapshot-size
checks before enabling them. No current defaults/allowlist were changed.

## F. Accepted 4.6 split: immediate small safeguards versus advanced backlog

John accepted the immediate/advanced split. Immediate scope extends this
supervisor and keeps its SQLite/private-directory architecture. Parameters below
remain for agreement; no retention/recovery implementation was made here.

Keep SQLite plus private artifact directories, not a message broker or general
workflow platform. Extend the existing job record with attempt/phase/checkpoint,
input/output receipt, and idempotency information. A small separate apply receipt
journal is needed for crash recovery of filesystem changes. Acceptance and its
idempotency key should commit together before returning an ID; the current
submit code has two commit points, so an error between them can leave a durable
queued job without a returned acceptance. Do not fix that by blindly resubmitting.

SQLite transactions can protect job metadata, but do not make independent
filesystem edits/transfer publication one atomic operation. Record phases and
verify receipts after crashes. [SQLite atomic commit](https://www.sqlite.org/atomiccommit.html)

| Case | Minimal safe response/policy proposal |
| --- | --- |
| Crash after accepting, before launch | Persist queued receipt; mark interrupted on next startup; no model replay |
| Crash during worker | Preserve stage/checkpoint and last activity; exact stop unknown; inspect before any new attempt |
| Crash during multi-file apply | Journal before/after hash per target; mark application interrupted; never guess whole-bundle success |
| Disk fills before acceptance | Refuse new work; no claimed acceptance or retry storm |
| Disk fills after acceptance/output | Stop further dispatch/publication, retain database/partial files, report storage failure where durably possible; unknown results stay unknown |
| Publication succeeded but final metadata commit failed | Retain transfer receipt and reconcile phase; do not publish or execute twice on a guess |
| Unreviewed failed/interrupted stage | Pin until explicit review/recovery; if quota exhausted, refuse new jobs rather than delete it silently |

For a personal project, propose 7 days for reviewed bulk output/staging, 90 days
for terminal summaries/receipts, and explicit pins for unreviewed failure data.
Operator-approved cleanup must use no-follow fixed-root handling and exclude
active jobs, referenced/pinned artifacts, private credential files, and inputs
still needed by a job. Add count/byte watermarks and available-space preflight.
No automatic retention or new disk policy was implemented. A database backup is
useful later; a distributed queue, unlimited checkpoint history, automatic
resumption, and many dependency types are unnecessary for this next pilot.
Current worker stdout is buffered until outcome; an abrupt supervisor crash can
lose that in-memory output. The demo proves partial files/before-status retention,
not durable streaming logs. A small persisted checkpoint receipt is the minimum
next step before claiming richer long-running recovery.

Immediate 4.6 implementation brief: one acceptance/idempotency transaction;
a small attempt/phase/checkpoint receipt in current JSON/SQLite; interrupted
restart recording with no automatic model replay; admission/free-space gates;
a bounded operator-reviewed cleanup plan that excludes active/pinned/unreviewed
or referenced data. Proposed defaults are 1 GiB minimum free, 1 GiB per staged
job, 8 GiB managed-job retained-data watermark, 7-day reviewed bulk retention,
and 90-day terminal summary/receipt retention. Count only supervisor-owned job
state/staging and owned outbound artifacts for the managed watermark; never
claim it bounds arbitrary uploads or the whole disk. Independently gate transfer
acceptance/publication on available space. Unowned or referenced inbound transfers
cannot be silently garbage-collected. Missing review/pin metadata means keep.
No automatic deletion until policy and ownership/reference handling are agreed.

Advanced recovery stays backlog: automatic resume/replay, filesystem rollback
across arbitrary edits, rich dependency DAGs, durable streaming of every token,
checkpointed model reasoning, distributed workers, and sophistication unrelated
to the two-worker delivery. After a crash, immediate recovery preserves evidence
and requires an explicit new authorized attempt; it does not reconstruct unknown
remote outcomes. If accepted work hits disk-full and metadata cannot be saved,
stop dispatch, retain partial files, and report uncertainty rather than claim a
durable terminal outcome or loop retries.

Pause/resume 4.8 and one-hour proof 4.9 remain backlog. A cheap future non-model
heartbeat/checkpoint simulator can verify timekeeping, cancellation, checkpoints,
crash recovery, and bounded log growth. It cannot prove useful model reasoning.
An hour-long test exceeds the current 1800-second limit and needs a specifically
scoped isolated-test override if chosen; no override or hour job was run here.

## Effort ranges for John's vote

These are rough engineering work ranges, not elapsed model-runtime promises.
Assumptions: one owner/one project, narrow text-file targets, no broader host
administration, existing transfer/SQLite mechanisms reused, and no universal
atomic filesystem transaction or arbitrary noncooperating-editor guarantee.

| Work package | Rough engineering effort | Main risk/decision |
| --- | --- | --- |
| 3.8 staged worker + manifests + guarded apply pilot and disposable 3.9 fixtures | 8–16 hours | Sandbox mount/credential exclusion and cooperative apply boundary |
| Two-worker dispatch + per-job inputs/cancellation + serialized apply | 6–12 hours after staging | Shared-state/resource pressure and shutdown handling |
| Safe one-retry/idempotency/attempt ledger | 4–8 hours | Distinguishing never-started work from ambiguous model outcome |
| Agreed storage gates/retention/checkpoint receipt | 2–5 hours after policy agreement | Disk-full crash consistency and preserving pinned partial work |
| Total if all phases approved | Roughly 20–41 engineering hours, with overlap/uncertainty | Installed CLI/security/live acceptance may reveal additional work |

Today's demos used zero model/provider calls and zero model tokens. These effort
ranges do not estimate future consultation/token costs or free-tier entitlement.
Parallelism shortens some independent wall time but can increase simultaneous
usage and memory; staging/retries do not make model work free. Each future live
acceptance task needs its own small call/token budget. Vote on staged apply first,
then worker count/admission and retry/storage parameters before implementation.

## Assignment timing and final limits

First captured checkpoint: 2026-10-11T23:07:24.408764-04:00; documentation/validation checkpoint: 2026-10-11T23:24:02.583647-04:00.
Monotonic elapsed since first capture: 993.488157 seconds. Initial architecture inspection began before that captured checkpoint; exact assignment start/total duration are unknown. All displayed wall timestamps use America/New_York.
