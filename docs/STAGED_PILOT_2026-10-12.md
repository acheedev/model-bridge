# Staged two-worker pilot: local delivery

John approved the saved pilot parameters and implementation scope. Implemented
in the Ubuntu checkout; installed service not activated. Existing user data was
not purged. No model calls, production application/restart/config changes,
commits or pushes were performed.

## Delivered and proven locally

- Explicit registered repos under `/home/jachee/projects/acheedev/`; only the
  existing model-bridge mapping. Separate inbound/outbound transfer roots.
- Filtered per-job snapshots, inputs, scratch, original byte/mode manifests and
  retained before-images. Worker policy denies the live checkout and other jobs.
  Credential/private/runtime directories, symlinks and special files excluded;
  known credential contents refused. Caller modifications are captured as-is.
- Submit requires 1..8 declared text `target_paths`. Undeclared final stage
  changes fail delivery. Text patches include missing-final-newline markers;
  mode changes are carried in the bundle manifest. Exact replacement files,
  SHA-256 hashes, and unified diff travel through verified outbound transfers.
  No applicable patch/file is silently truncated. Existing total/file ceilings
  apply to the entire publication, including report/bundle overhead.
- Separate `project_apply(job_id, bundle_hash, base_hash, authority)` with exact
  authority `{apply:true,test:false,commit:false,push:false}`. Testing is a
  separate operation. Complete bundle preflight, content/existence/mode rechecks,
  no-follow directories, exclusive additions, verified deletions, per-repo lock,
  output verification and durable partial/completed receipts. Additions require
  existing parent directories in this narrow pilot. Same bundle returns its
  original receipt without reapplying over newer caller changes.
- Two staged workers maximum; second slot requires at least 5 GiB available
  memory, increased for explicit larger per-process overrides. Default memory
  2048 MiB and CPU 300 seconds per process; original queue/execution/backoff
  deadline at most 1800 seconds; eight pending jobs. These limits do not bound
  aggregate descendants or reserve memory. Low memory queues the second job.
- Attempt ledger and at most one retry after two seconds, only when process
  creation fails with EAGAIN/ENOMEM before any launcher/worker executes. A
  returned process/PID, uncertain model outcome, partial stage writes,
  cancellation, authentication failure or stale base never auto-retries.
  Retry cannot extend the original deadline or authority.
- Acceptance and idempotency key commit in one SQLite transaction. Reusing a key
  with changed input refuses; restarting marks queued/running jobs interrupted,
  retains stages/inputs and records uncertainty without replay. Periodic durable
  phase/checkpoint timestamps are not a durable reasoning/stdout stream.
- Manual dependencies: submit B with successful A's job ID and verified outbound
  transfer ID as an input. A's hashes/state are checked; B explicitly consumes
  the output, and A's artifacts stay referenced. No general dependency engine.
- Storage gates: 1 GiB minimum free, 1 GiB per stage, 8 GiB managed retained
  state/stages/owned outbound watermark. Snapshot reserves space conservatively;
  running-stage/free-space checks occur approximately once per second, so these
  are admission/monitoring limits, not hard filesystem quotas. Stage growth can
  overshoot before detection. Transfer publication reserves required bytes.
  Metadata write failure halts dispatch and exposes uncertain durability.
- Explicit review and named-job retention only. No automatic startup/scheduled
  purge. Seven-day reviewed bulk removal and 90-day summary compaction retain
  small idempotency/apply tombstones. Active, unreviewed, pinned and referenced
  data is protected; missing review metadata means keep. Consuming-job bulk
  removal releases its dependency references. Arbitrary/unowned inbound uploads
  are never garbage-collected by this policy. Cleanup was tested only in fixtures.

## Evidence and practical limits

[Full test record](STAGED_PILOT_TESTS_2026-10-12.json): 132 tests passed, including
21 new staged/parallel/retry/durability fixtures, 26 existing transfer/job checks,
and two adapted lifecycle integration checks. New cases prove actual overlap,
independent cancellation, memory rejection, clean edit/add/delete and duplicate
apply, all-target stale preflight, tamper/traversal/link refusal, partial apply,
same-repo serialization, two active jobs plus queued work interrupted after an
actual disposable supervisor crash, bounded retries/deadline/backoff cancellation,
verified manual dependencies, storage failure and protected retention.

Commands: `.venv/bin/python -m unittest discover -s tests -v` for regression;
`scripts/demo_project_lifecycle.py --scenario all` remains a disposable fixture
entry point, not installed-client proof. Do not run it through project_submit.

Cooperative application boundary: no manual/non-cooperating writes during apply.
The bridge lock cannot serialize arbitrary editors. Multi-file application is
not atomic: interrupted receipts require inspection, never blind replay. The
full suite exercises real disposable subprocesses, SQLite and registered MCP
handlers, but not the installed Codex CLI sandbox or remote authenticated endpoint.
The nominal two-worker gate is injected in fixtures; no host memory change was
made and no promise is made that current WSL headroom admits two model workers.

## Remaining activation/client proof

Separately authorize activation of the reviewed source and an installed CLI
sandbox check proving stage writes permitted, live checkout/private/other-job
writes denied, and usable dependencies. The historical `probe_worker_inputs.py`
checks the retired shared-input architecture and is not proof for this pilot.
Then use actual authenticated MCP submit/status/result/readback with two narrow
jobs, inspect overlap/admission and receipts, and verify apply conflict behavior
on a separately authorized disposable repo/fixture. Any real production apply
requires its own explicit authority; any model requests need a separately agreed
small usage budget. No service restart/config activation/provider calls are
included in the local implementation authority.

3.8 and 4.7 remain open for that installed proof; 3.9 remains open for separately
authorized production application. Advanced 4.6b, pause/resume 4.8 and hour proof
4.9 stay backlog. No hour-long job was run.

Measured full-suite interval: 2026-10-12T00:07:45.767511-04:00 to 2026-10-12T00:07:57.697383-04:00; 11.929858 monotonic subprocess seconds. Unittest reported 10.744 seconds. Initial implementation start was not timestamped, so exact total engineering duration is unknown.
