# Repository layout validation

Validated October 11, 2026, using the existing Ubuntu WSL Python 3.10.12 virtual
environment against a disposable copy of this checkout under
`/home/jachee/projects/`. The copy was removed after validation. The installed
service and its checkout/data were not modified.

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests -v` | 93 tests passed; unittest reported 2.360 seconds. |
| `python -m compileall -q model_bridge tests` | Passed on Linux and Windows. |
| `bash -n scripts/mbridge.sh` | Passed. |
| `git diff --check` | Passed. |
| Local Markdown navigation | Relative file links resolve. |
| Private inventory exclusion | `private/` is ignored and has no tracked files. |

Two regression checks cover the package move: transcript/temp paths still resolve
to the checkout root, and the job allowlist and private worker launcher still use
that same root. Existing tests cover relative imports through actual server/tool
registration, job subprocess execution, resource limits, and cancellation.

This was local validation without live model requests. Authentication to provider
backends, installed service startup, client discovery, reboot availability, and
model-driven project completion were outside this layout-validation run. Later
sections record separate service and authenticated MCP checks. Earlier CLI/Code
Mode diagnostics in [operations](OPERATIONS.md) remain historical observations.

The user reported that the bridge service is stopped. Its installed unit must
adopt the new module entry point before a separately authorized restart; the
repository template is [deploy/model-bridge.service](../deploy/model-bridge.service).
No commit, push, installation, or service restart was performed.

The test runner measured suite duration. Task start, implementation completion,
and validation completion timestamps were not captured; total task duration is
unknown.

## Systemd service validation

On October 11, 2026, the user installed the repository unit after the assistant's
installation attempt was blocked by password-required sudo. The exact user
installation completion timestamp was not recorded. No installation or restart
was performed by the assistant.

Host systemd inspection confirmed:

- Unit: `/etc/systemd/system/model-bridge.service`, loaded, enabled, active/running.
- Entry point: checkout `.venv/bin/python -m model_bridge.claude_bridge`.
- Working directory: `/home/jachee/projects/acheedev/model-bridge`; user: `jachee`.
- No drop-ins; PID at inspection: `185421`.
- Observed service start: 2026-10-11 20:44:25 UTC
  (2026-10-11 16:44:25 -0400, America/New_York).
- Host default target: `graphical.target`; repository unit uses
  `WantedBy=multi-user.target`.

Post-restructure live MCP validation completed at 2026-10-11 20:45:32.208822 UTC
(2026-10-11 16:45:32.208822 -0400, America/New_York). An authenticated SDK
session to `http://127.0.0.1:8081/mcp` initialized successfully and
`bridge_ping` for "Post-restructure authenticated bridge availability check"
returned `status: ok` with the expected echo and no model call. A request without
credentials returned HTTP 401. Credentials were not displayed.

The server advertised all eleven tools, including the seven transfer/job tools:
`transfer_upload`, `transfer_manifest`, `transfer_read`, `project_submit`,
`project_status`, `project_result`, and `project_cancel`. This proves
authenticated endpoint reachability and schema exposure only. Installed-unit
reconciliation, fresh transfer roundtrip, cancellation/recovery, worker
execution, provider login, availability after terminals close, pre-sign-in
startup, uninterrupted uptime, and Windows power settings remain unverified here.

Verification segment began at 2026-10-11 20:45:15.227846 UTC
(2026-10-11 16:45:15.227846 -0400, America/New_York). Its monotonic start and
completion timing are recorded in `.tmp/systemd-validation-timing.json`.

## Baseline reconciliation 2026-10-11

Read-only reconciliation inspection began at the first recorded timestamp
2026-10-11 17:01:07 -0400 (2026-10-11 21:01:07 UTC), measured with `date`.
Inspection and documentation validation completed at 2026-10-11 17:02:03 -0400
(2026-10-11 21:02:03 UTC). Elapsed time from the first recorded timestamp to
that completion check was 56 seconds. No fetch, stage, commit, rebase, merge,
push, service restart, reload, installation, startup-task change, live model
probe, credential dump, or configuration change was performed.

Repository inspection:

- Checkout: `/home/jachee/projects/acheedev/model-bridge`, resolving to the same
  path with `readlink -f`.
- Branch: `main`.
- HEAD: `e55d157d9631b85644a0608f169c425e85d6176b`.
- Locally available tracking ref: `origin/main` at
  `e55d157d9631b85644a0608f169c425e85d6176b`; no fetch was performed.
- Working tree before this reconciliation edit already had modified
  documentation files: `docs/PROJECT_SPEC.md`, `docs/TASKS.md`, and
  `docs/VALIDATION.md`. These preexisting edits were preserved and treated as
  user-owned baseline content.
- Git emitted permission warnings for a denied sandbox path under `job-data/...`
  when looking for user config/ignore/attributes. No attempt was made to bypass
  that restriction.

Installed unit and template inspection:

- Repository template: `deploy/model-bridge.service`.
- Installed unit path: `/etc/systemd/system/model-bridge.service`.
- `diff -u deploy/model-bridge.service /etc/systemd/system/model-bridge.service`
  produced no differences, so the maintained template and installed unit agree
  for the nonsecret launch settings inspected here.
- Relevant launch settings in both files: `User=jachee`,
  `WorkingDirectory=/home/jachee/projects/acheedev/model-bridge`,
  `ExecStart=/home/jachee/projects/acheedev/model-bridge/.venv/bin/python -m
  model_bridge.claude_bridge`, `Restart=on-failure`, `RestartSec=5`,
  `TimeoutStopSec=10`, `UMask=0077`, and `WantedBy=multi-user.target`.
- The service working directory resolves to
  `/home/jachee/projects/acheedev/model-bridge`; the Python executable resolves
  to `/usr/bin/python3.10`.
- Readable enablement evidence: `/etc/systemd/system/multi-user.target.wants/model-bridge.service`
  points to `/etc/systemd/system/model-bridge.service`. No drop-in files were
  found by the targeted filesystem inspection.

Blocked or inconclusive host/runtime checks:

- `systemctl show` and active-state inspection failed in this sandbox with
  `System has not been booted with systemd as init system (PID 1). Can't operate.`
  and `Failed to connect to bus: Host is down`.
- `systemctl is-enabled model-bridge.service` returned `enabled`, but the same
  active-state command group could not connect to the systemd bus, so active
  state, target relationship details from the manager, MainPID, restart count,
  and active-enter timestamps were not freshly verified here.
- Process inspection inside the sandbox did not expose a real
  `model_bridge.claude_bridge` service process; the only matches were the
  sandbox command itself. Actual process identity, executable/arguments, and
  runtime working directory therefore remain unverified in this pass.
- Because the running process could not be inspected, no evidence from this
  assignment links a live loaded Python process to the current checkout, HEAD, or
  uncommitted source state. Git HEAD and installed file agreement alone do not
  prove the revision loaded into any long-running process.

Discrepancies and smallest corrective next steps:

- The installed unit/template point at this checkout and agree on launch
  settings, while host active-state/process inspection was blocked by sandbox
  isolation. Re-run the same sanitized systemd and `/proc` checks from a host
  context that can see the real systemd manager and service process.
- If a live service process is found, record its PID, sanitized command line,
  resolved executable, process working directory, service start time, and a
  source/load evidence boundary. For an already-running Python process with
  uncommitted files, retain loaded-revision uncertainty unless a direct runtime
  mechanism proves the loaded source revision.
- Keep the generalized concurrent-change protection item open until the worker
  implements and proves a reusable before-application check; artifact hash
  verification is not sufficient.

## Credential inventory and directory boundary audit 2026-10-11

The bounded inventory/audit is recorded in
[DIRECTORY_BOUNDARY_AUDIT_2026-10-11.md](DIRECTORY_BOUNDARY_AUDIT_2026-10-11.md).
No code, runtime configuration, service state, permissions, credential stores,
production data, live provider calls, Git history, commits, pushes, or
authentication state were changed.

Validation evidence:

- `.gitignore` now contains the exact approved `/private/` rule while preserving
  the preexisting `private/` rule.
- `private/` resolved inside this checkout as a normal directory before notes
  were written.
- A private credential inventory/recovery note was created only after the
  location, ignore, and tracking checks. Its contents are not reproduced in
  public documentation.
- `git check-ignore` confirmed the private note is ignored, and `git ls-files --
  private` returned no tracked private paths.
- Source and metadata checks covered transcript storage, job records, worker
  homes/scratch, transfer roots, staged inputs, artifact publication, tests,
  caches, overrides, symlink handling, and cleanup boundaries.
- Host systemd active-state and real process checks remain pending because the
  worker sandbox cannot inspect the host systemd manager or real bridge process.

## Host baseline follow-up 2026-10-11

The scoped host follow-up verified active state, stable MainPID, owning account,
actual executable/arguments/working directory, service start, zero restarts,
non-environment launch settings, no drop-ins, and locally available Git refs.
Metadata-only inspection verified the real transfer roots and fixed protected
credential locations. The earlier sandbox limitations are historical; loaded
Python revision and runtime-environment overrides remain unverified.

See [reconciliation evidence](RECONCILIATION_REPORT_2026-10-11.md#host-follow-up-scoped-read-only-inspection)
and [host path metadata](DIRECTORY_BOUNDARY_AUDIT_2026-10-11.md#host-metadata-follow-up).
No new authentication, provider, transfer-roundtrip, service-operation, or
availability test was performed.

## Gemini direct-host regression and follow-through, October 11

Original direct-host suite: 100/100 passed, zero failures/errors/skips, exit 0;
21:09:36.133988–21:09:39.702800 EDT, 3.568801 monotonic subprocess seconds.
Both inherited recursion markers were absent; the project virtual environment
ran the documented unittest command outside any project_submit worker.

Minimal Gemini transport, key-exclusion, and token-truncation repairs justified
one later full regression: 109/109 passed, zero failures/errors/skips, exit 0;
21:24:28.357497–21:24:32.456496 EDT, 4.098999 monotonic subprocess seconds.
Suites used mocks/disposable fixtures, not live providers or production jobs.

Four separately authorized live registered-handler calls used 823 reported
tokens. Independent/open context and supplied critique content were proven;
the critique hit MAX_TOKENS and was not retried. Running-service adoption of
the repairs remains pending a separate host restart. Detailed evidence and
the assignment-only diff are in
[GEMINI_VALIDATION_2026-10-11.md](GEMINI_VALIDATION_2026-10-11.md).

### Complete higher-cap critique follow-up

One separately authorized registered-handler critique used an explicit
2048-token output cap on the existing synthetic thread. The connector default
was raised to 2048, preserving explicit overrides and the 8192 maximum; small
mocked truncation fixtures were unchanged. All 13 focused tests passed
(unittest: 0.546 seconds); no full-suite rerun or extra live mode tests occurred.

Actual critique: status ok, STOP, truncated false, 96 words; 467 prompt + 142
candidate = 609 total tokens. Start/end: October 11,
21:39:42.639571–21:39:43.684854 EDT; monotonic handler duration 1.045282 seconds.
Full returned text and metadata are retained in the
[Gemini validation record](GEMINI_VALIDATION_2026-10-11.md).
A single interactive-sudo service restart remains necessary to load source/default
changes. This host test did not restart or validate the running service's defaults.

### Subsequent reported restart checkpoint

John reported completing the pending Ubuntu service restart; Mimi then reported
an authenticated bridge_ping with status ok, exact echo, and reported
Gemini model gemini-3.5-flash-lite. The source-repair restart step is checked off
on that reported basis. Ping does not independently verify loaded source or
the effective 2048-token cap. Exact checkpoint timestamps were not supplied.
See the [detailed validation checkpoint](GEMINI_VALIDATION_2026-10-11.md#reported-restart-and-authenticated-ping-checkpoint).
No new probes or service/code/configuration/Git operations accompanied this update.

## Scoped non-model project lifecycle scaffolding and critical next brief

New scripts/demo_project_lifecycle.py uses only disposable project/state/transfer
roots under this checkout's .tmp and actual registered MCP handlers. Cancellation
stops its fixture process group/grandchild, retains partial/unrelated files,
records durable status/result, and verifies exact outbound bytes/hash/job state.
An abrupt isolated supervisor exit demonstrates running/queued interruption,
unknown stop timestamps, retained before-status/partial files, no replay, and
acceptance/completion of a new non-model job. No production jobs were cancelled
and no installed service restart occurred; live 4.4/4.5 proofs stay unchecked.

Two new integration tests passed. Final focused run: October 11,
23:13:42.407095–23:13:43.659126 EDT; 1.252030 monotonic subprocess seconds;
unittest 0.973 seconds, zero failures/errors/skips. The CLI demo's two scenarios
also passed at 23:12:34.788411–23:12:35.840858 EDT, 1.052448 monotonic seconds;
that earlier CLI run preceded stronger readback assertions verified by the
focused retest. No full-suite repeat was needed: production source is unchanged.

3.8 integrated protection stopped at the authorized design/estimate fallback:
current workers directly edit the target, so pre-apply protection needs staging
and a distinct apply contract. No clean/stale patch application was claimed.
John's accepted repo/transfer boundary and immediate-versus-advanced 4.6 split
are recorded. Critical 4.7 has a concrete scoped implementation/proof brief and
remains pending actual delivery, not completed by design. 4.8/4.9 stay backlog.

See [proposal/evidence](PROJECT_WORK_PROPOSAL_2026-10-11.md),
[next implementation brief](NEXT_IMPLEMENTATION_BRIEF.md), and
[sanitized disposable demo trace](PROJECT_LIFECYCLE_DEMO_2026-10-11.json).
No provider calls, production code/config/permission changes, real restart,
commit, push, hour job, or broad audit accompanied this work.

## October 12 staged parallel pilot

132 full-suite tests passed. [Exact timings/output](STAGED_PILOT_TESTS_2026-10-12.json) and [implemented behavior, fixture scope and remaining installed proof](STAGED_PILOT_2026-10-12.md). No provider calls, production apply/restart/config changes, commits or pushes. Existing data untouched.
