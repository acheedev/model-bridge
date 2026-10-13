# Project checklist

Updated October 11, 2026. Work top to bottom; each box is a useful stopping point.
Checked items have source, validation, or explicitly reported historical evidence.
Each item separates implementation from verification when those facts differ.
This list tracks work; it does not grant permission to install, restart, commit,
push, expose endpoints, run paid model probes, or perform roadmap tasks.

## Current evidence boundaries

- Current layout validation: Implemented / Last verified: October 11, 2026 in a
  disposable checkout / Evidence: [validation](VALIDATION.md) records 93 passing
  tests, compile checks, shell syntax, `git diff --check`, local Markdown
  navigation, and private inventory exclusion. Task start, implementation
  completion, validation completion, and total duration were not captured for
  that validation run and remain unknown.
- Post-restructure authenticated connectivity: Recheck needed for broader
  behavior / Last verified: 2026-10-11 17:31:35 EDT (-04:00), after John
  reported all Ubuntu terminals and VS Code instances closed / Evidence:
  authenticated `bridge_ping` returned `status: ok`, echoed the exact expected
  message, made no model call, and advertised all 11 exposed tool schemas
  including all seven transfer/project tools. This proves authenticated
  checkpoint reachability under the existing keepalive and schema exposure only;
  it does not prove indefinite uptime, installed-unit reconciliation, transfer
  roundtrip, cancellation/recovery, reboot startup, or worker execution.
- Historical worker-transfer proof: Historically passed / Last verified:
  earlier bootstrap, exact timestamp not supplied here / Evidence: all seven
  transfer/project tools were discovered; client upload/readback of `README.md`
  and `PROJECT_SPEC.md` independently matched byte counts, bytes, and SHA-256;
  original job `0fdb620e9589472cb35b275c31dbf903` failed; after input-mount
  repair, retry job `549ac2a1731a445fbf9b5b18a6ee4b1d` used inbound transfer
  `4c41071bfb3c48369b66a07b00651dc8` and outbound transfer
  `03457b8540884be49790318b1b148603`; the client locally verified returned
  `README.md`, `PROJECT_SPEC.md`, report, and patch hashes. Worker-reported
  preservation of useful existing README content remains a worker claim, not
  independent source-state verification. The assignment did not provide the
  literal byte counts or SHA-256 values, so they are not invented here.
- Historical Git closeout: Reported historical closeout / Last verified: John
  relayed Ezra's report, timestamp not supplied here / Evidence: branch
  `feature/codex-runner` was reported rebased, fast-forward pushed,
  merged/pushed to `main` at commit `11a56a1`, deleted locally/remotely, and
  left a clean tree with 91 previously passing tests. This is not evidence of
  the current layout's Git status and is not an unresolved future rebase for an
  already deleted branch.
- Startup after sign-in: Historically passed for checkpoint reachability only /
  Last verified: John observed launch after Windows PIN sign-in; Mimi checked
  authenticated bridge access at 2026-10-11 01:18:20 -0400 / Evidence: Windows
  Task Scheduler task runs under `aihub\default` with interactive logon and
  launches Ubuntu as `jachee` with `sleep infinity`; John supplied task
  `Running` and Ubuntu-running output after a PC reboot, roughly 30 seconds
  after sign-in. This does not prove pre-sign-in startup, uninterrupted uptime,
  Windows power settings, or an unattended hour-long assignment.

Prior totals of 90 and 91 passing tests are historical. Today's layout validation
total is 93 tests, within the boundaries above.

## 1. Give the project a clean home

- [x] **1.1** Put Python code in `model_bridge/`, documentation in `docs/`, launch
  scripts in `scripts/`, and service configuration in `deploy/`.
  Status: Implemented. Last verified: layout validation, October 11, 2026.
- [x] **1.2** Update imports, worker launch paths, startup commands, and documentation
  links.
  Status: Implemented. Last verified: 93-test layout validation and local link
  check. Recheck needed for installed/running service reconciliation.
- [x] **1.3** Keep transcripts, temporary files, and job data rooted in the checkout.
  Status: Implemented by source/tests. Last verified: layout validation. Recheck
  needed for full directory/override/cache/symlink audit.
- [x] **1.4** Add a short README with navigation and a Python package manifest.
  Status: Implemented. Last verified: layout validation and documentation read.
- [x] **1.5** Ignore `private/` before creating any private inventory.
  Status: Implemented. Last verified: layout validation confirmed `private/` is
  ignored and has no tracked files.
- [x] **1.6** Update the installed service to the new module entry point and verify
  authenticated startup under separate service authority.
  Status: Implemented/reported and spot-verified. Last verified:
  [systemd service validation](VALIDATION.md#systemd-service-validation).
  Recheck needed for service/source/running-revision reconciliation.

## 2. Close the baseline

Section 2 is closed for the current low-impact personal-project scope; deferred
items and retained limitations remain visible below, and the next work is
section 3.

- [x] **2.1** Run existing tests and record results, known diagnostics, and validation
  limits.
  Status: Implemented. Last verified: [layout validation](VALIDATION.md) records
  93 tests passed; earlier 90/91 totals remain historical only.
- [x] **2.2** Create private credential inventory and recovery notes without copying
  secret values; verify nothing in `private/` is tracked.
  Status: Completed for inventory locations and procedures on 2026-10-11.
  Evidence: [directory boundary audit](DIRECTORY_BOUNDARY_AUDIT_2026-10-11.md)
  records safe `private/` location, ignored/untracked verification, and private
  note creation without credential contents in public artifacts. Protected-store
  metadata and provider account state remain unresolved.
- [x] **2.3** Audit runtime/test directories, overrides, caches, and symlinks against
  the approved Linux roots; retain the systemd/journal exceptions.
  Status: Completed within sandbox-accessible evidence on 2026-10-11. Evidence:
  [directory boundary audit](DIRECTORY_BOUNDARY_AUDIT_2026-10-11.md) records
  source origins, resolved destinations, accessible metadata, verdicts, and
  host-versus-sandbox limits. Host systemd/process facts remain pending under
  the existing reconciliation item.
- [x] **2.4** Reconcile this checkout, service checkout, installed unit, running revision,
   and working-tree changes.
   Status: Completed/accepted for current scope on 2026-10-11. Host direct
   inspection was reported completed for actual process/user/command/cwd/start/
   restarts, installed/template non-environment launch settings,
   checkout/branch/HEAD/tracking refs, and metadata. Retained limitations:
   exact loaded Python revision and environment-value equivalence were not
   established and are not claimed verified. Evidence: [host follow-up](RECONCILIATION_REPORT_2026-10-11.md#host-follow-up-scoped-read-only-inspection).
- [x] **2.5** Verify actual host service/process identity, start time, restart count,
   non-environment launch settings, and relevant drop-ins.
   Status: Verified; active PID `185421`, account `jachee`, expected command/cwd,
   zero restarts, no drop-ins. Full environment/unit equivalence is not claimed.
- [x] **2.6** Record current branch, full HEAD, working-tree state, and local tracking refs.
   Status: Verified read-only; `main` and `origin/main` at
   `e55d157d9631b85644a0608f169c425e85d6176b`; no fetch or Git mutation.
- [x] **2.7** Verify metadata for real transfer roots and fixed protected credential paths.
   Status: Verified; private modes/ownership, no redirects; default auth cache
   absent. Runtime overrides and credential validity remain unverified.
   Evidence: [host metadata](DIRECTORY_BOUNDARY_AUDIT_2026-10-11.md#host-metadata-follow-up).
- [x] **2.8** Verify explicit systemd enablement and startup target, then authenticated
  `bridge_ping`.
  Status: Implemented for the observed installed service. Last verified:
  [systemd service validation](VALIDATION.md#systemd-service-validation).
- [x] **2.9** Confirm MCP remains available after all Ubuntu terminals and VS Code close.
  Status: Completed for checkpoint reachability on 2026-10-11 17:31:35 EDT
  (-04:00). John reported all Ubuntu terminals and VS Code instances closed;
  Mimi independently verified authenticated `bridge_ping` status `ok`, exact
  echo, and all 11 exposed tool schemas. No model call was used for the ping.
  This proves checkpoint reachability under the existing keepalive, not
  indefinite uptime.
- [x] **2.10** Verify automatic Ubuntu/service startup after Windows sign-in.
  Status: Historically passed for after-sign-in checkpoint reachability. Last
  verified: John observed post-reboot launch after PIN sign-in and Mimi checked
  authenticated access at 2026-10-11 01:18:20 -0400. Recheck needed after any
  startup mechanism changes.
- [ ] **2.11** Verify automatic Ubuntu/service startup before Windows sign-in.
  Status: Deferred/backlog by John's decision; unchecked and not part of the
  current scope. Account-password recovery was deferred.
- [ ] **2.12** Verify Windows power settings support the required availability.
  Status: Deferred/backlog by John's decision; unchecked and not part of the
  current scope.
- [ ] **2.13** Review the baseline and record evidence and timestamps in the documentation.
  Status: Deferred/backlog by John's decision; unchecked and not part of the
  current scope. Partial evidence and retained limitations are recorded in this
  checklist, [validation](VALIDATION.md), and the
  [directory boundary audit](DIRECTORY_BOUNDARY_AUDIT_2026-10-11.md).
- [x] **2.14** Record historical Git branch closeout separately from current layout work.
  Status: Reported historical closeout. Last verified: John relayed Ezra's report
  that `feature/codex-runner` was rebased, fast-forward pushed, merged/pushed to
  `main` at `11a56a1`, deleted locally/remotely, and had 91 previously passing
  tests. Recheck needed for the current layout's Git state only if separate Git
  authority is granted.

## 3. Prove one complete coding loop

- [x] **3.1** Implement the narrow model-bridge worker with explicit edit/test authority
  and no commit/push authority.
  Status: Implemented. Last verified: layout validation covers tests; historical
  worker job exercised the path.
- [x] **3.2** Implement verified byte-preserving input transfers and sanitized outbound
  artifacts.
  Status: Implemented. Last verified: layout validation and historical client
  transfer/readback proof.
- [x] **3.3** Confirm client discovery of all seven worker-transfer tools after the
  authorized service update.
  Status: Historically passed and freshly schema-visible. Last verified:
  historical client discovery of all seven tools; post-restructure authenticated
  discovery exposed all 11 tools including the same seven. Evidence limit:
  today's proof is discovery only.
- [x] **3.4** Complete client byte/size/SHA-256 readback proof with actual reference
  files; keep the transfer receipt and comparison evidence.
  Status: Historically passed for `README.md` and `PROJECT_SPEC.md`. Evidence:
  inbound transfer `4c41071bfb3c48369b66a07b00651dc8`; client independently
  matched byte counts, bytes, and SHA-256. Recheck needed for a fresh
  post-restructure transfer roundtrip.
- [x] **3.5** Choose one small task and write its brief, exact acceptance criteria, and
  authority.
  Status: Historically passed for the model-driven documentation job. Evidence:
  failed original job `0fdb620e9589472cb35b275c31dbf903`; successful retry
  `549ac2a1731a445fbf9b5b18a6ee4b1d`.
- [x] **3.6** Supply a filtered read-only snapshot with provenance and hashes, excluding
  credentials.
  Status: Historically passed for the verified documentation-job inputs. Evidence
  limit: literal hash values were not included in this assignment text.
- [x] **3.7** Return a reviewable patch and validation evidence.
  Status: Historically passed for the documentation job's outbound retrieval.
  Evidence: outbound transfer `03457b8540884be49790318b1b148603`; client locally
  verified returned README, spec, report, and patch hashes. Worker claims are not
  independent source-state verification.
- [ ] **3.8** Protect concurrent project changes before patch application.
  Status: Local staging/guarded apply implemented and tested. Clean/stale,
  edit/add/delete, tamper/link/escape and partial-apply fixtures pass. Installed
  CLI sandbox boundaries remain pending; cooperative no-manual-edit apply window.
- [ ] **3.9** Apply through separate authority and retain end-to-end evidence.
  Status: Local registered-handler application/conflict fixtures passed. No
  production apply; explicit production authority/client proof remains pending.
- [x] **3.10** Agree project boundaries, patch transport and pilot resource limits.
  Status: John approved the parameters; implemented locally. Only specifically
  registered acheedev repos, separate transfer roots, private exclusions and
  bounded full-artifact transport. Installed activation pending.
  See [local pilot evidence and limits](STAGED_PILOT_2026-10-12.md).

## 4. Make background work dependable

- [x] **4.1** Implement durable job IDs, prompt acceptance, status/results, elapsed-time
  reporting, and cancellation.
  Status: Implemented. Last verified: tests and documentation.
- [x] **4.2** Serialize bootstrap jobs and mark queued/running work interrupted after
  restart without automatic replay.
  Status: Historical serialized bootstrap passed; current local pilot permits two
  isolated stages and serializes apply per repo. Restart still never auto-replays.
- [x] **4.3** Verify a model-driven job and result retrieval end to end.
  Status: Historically passed. Evidence: successful retry job
  `549ac2a1731a445fbf9b5b18a6ee4b1d` and outbound transfer
  `03457b8540884be49790318b1b148603`.
- [ ] **4.4** Verify live cancellation end to end.
  Status: Installed-client proof pending. New deterministic non-model demo
  exercised registered submit/status/cancel/result/readback handlers, stopped
  its fixture process tree, retained partial evidence, and verified durable
  cancelled status/output hashes. Production jobs were not cancelled.
- [ ] **4.5** Verify interruption recovery end to end after restart.
  Status: Installed-restart proof pending. New isolated abrupt-crash demo
  recorded running/queued interruption, retained partial files/before-status,
  performed no automatic replay, and accepted a successful next fixture job.
  No real service restart or model reasoning was tested.
- [x] **4.6a** Implement minimum durable acceptance, checkpoints and disk/retention gates.
  Status: Local implementation and disposable tests passed. Atomic idempotent
  acceptance, interrupted/no-replay restart, storage refusal, explicit reviewed
  retention and protected partial work. Installed activation pending; existing
  user data was not deleted.
- [ ] **4.6b** Advanced recovery.
  Status: Backlog: automatic model resume/replay, rich dependency graphs,
  arbitrary filesystem rollback and durable reasoning/stream replay.
- [x] **4.7-local** Implement and prove two staged workers, safe retries and manual dependencies.
  Status: Actual non-model overlap, memory admission, independent cancellation,
  per-repo apply serialization, bounded retry/idempotency and two-active crash
  fixtures passed. Manual B consumes verified successful A output; no DAG engine.
- [ ] **4.7** Complete installed end-to-end parallel/retry client proof.
  Status: CRITICAL remaining delivery gate. Reviewed source needs separately
  authorized activation/CLI boundary validation and authenticated client proof.
  No new paid calls or service changes authorized. See
  [exact remaining proof](STAGED_PILOT_2026-10-12.md#remaining-activationclient-proof).
- [ ] **4.8** Add status/pause/resume/cancel controls with clear stop rules for conflicts,
  exhausted limits, and stalled progress.
  Status: Backlog beyond current status/cancel bootstrap controls; pause/resume
  was not implemented in this assignment.
- [ ] **4.9** Prove one unattended hour-long assignment before extending to multi-day
  projects.
  Status: Backlog by John's final instruction; no hour job run. A future cheap
  non-model heartbeat simulator proves mechanics, not useful model reasoning.
  An hour exceeds the current 1800-second limit and needs a scoped isolated-test
  override if chosen; no override was introduced.

## 5. Connect ChatGPT and bring in Gem

- [ ] **5.1** Select a supported authenticated connection for ChatGPT and the iPhone app.
  Status: Skipped/deferred by John's decision for the Gemini connector stage.
- [x] **5.2** Review Gem's supplied integration instructions and decide Gemini
  authentication.
  Status: Complete for this stage. Decision: use the official `google-genai` SDK
  with Gemini Developer API-key authentication from the protected bridge keystore;
  no billing enablement and no project-worker credential access.
- [x] **5.3** Add Gemini through the common independent/critique/follow-up consultation
  contract.
  Status: Implemented in source and mocked tests. Host SDK and Mimi's authenticated
  MCP independent-mode proof passed using `gemini-3.5-flash-lite`. Source default
  remains configurable `gemini-2.5-flash-lite`; the model-only service drop-in
  selects `gemini-3.5-flash-lite` without fallback. Live critique/follow-up tests
  and full host verification are not covered by this connectivity proof.
- [x] **5.4** Under separate integration and live-probe authority, validate client access
  and Gemini behavior; preserve transcripts and usage evidence.
  Status: Complete for initial authenticated independent-mode connectivity only.
  Mimi reported `status: ok`, exact confirmation text, `gemini-3.5-flash-lite`,
  `STOP`, no truncation, 121 prompt + 6 candidate = 127 total tokens, and
  0.5675054520033882 seconds. Transcript start label: October 11, 20:51:56 EDT;
  exact call start/end were not independently clocked. Live critique/follow-up
  tests and full host verification remain outside this completion claim.
  See [host and MCP validation record](GEMINI_HOST_ACTIVATION_2026-10-11.md).


### Gemini follow-through checks

- [x] **Check 1: Conversation modes.** Four original tiny registered-handler
  calls proved fresh independent context, open history, and other_answer receipt.
  John then authorized one 2048-token critique on the same synthetic history:
  complete 96-word response, STOP, no truncation, 609 reported tokens. No exact
  response-format guarantee is claimed. Claude/Codex IDs were rejected locally.
- [x] **Check 2: Failures and limits.** Mock/local-server coverage passed for
  credentials, auth/quota/network/timeout, blocked/empty, truncation, metadata,
  and secret-free public/transcript errors.
- [x] **Check 3: Existing regressions.** Direct Ubuntu suite: 100/100 passed on
  October 11, 21:09:36.133988–21:09:39.702800 EDT, 3.568801 monotonic seconds.
  Narrow repairs justified one later full run: 109/109 passed, no failures/skips.
- [x] **Check 4: Source transport enforcement.** Actual SDK/local server proved
  one network attempt, HTTP timeout socket closure, and no abandoned client
  executor thread. This is an HTTP inactivity bound, not a hard whole-call
  deadline or proof of remote provider cancellation.
- [x] **Load source repairs into the running service.** Completed based on
  John's report of the Ubuntu service restart. Mimi then reported authenticated
  bridge_ping status ok, exact echo, and gemini_model gemini-3.5-flash-lite.
  This checkpoint does not independently verify the loaded source or 2048 cap.

See [Gemini validation and repair evidence](GEMINI_VALIDATION_2026-10-11.md).

## 6. Build reusable council workflows

- [ ] **6.1** Research `garrytan/gstack`; select useful components, pin a source
  revision, and retain licenses, attribution, and adaptation notes.
  Status: Pending.
- [ ] **6.2** Create versioned `workflows/` templates A-E: code review, solution proposal,
  code authoring, council consultation, and troubleshooting.
  Status: Pending.
- [ ] **6.3** Define inputs, assignments, outputs, completion criteria, and escalation
  rules; persist the template version with every job.
  Status: Pending.
- [ ] **6.4** Build one shared council briefing with independent first responses and
  bounded execution for each member.
  Status: Pending.
- [ ] **6.5** Report every member's status, disagreements, comparison, Mimi's
  recommendation, and links to individual transcripts; keep consultation
  separate from implementation authority.
  Status: Pending.
- [ ] **6.6** Record observed start/completion/validation times and elapsed-time
  measurement methods; leave unknown values unknown.
  Status: Pending as a reusable workflow requirement. This documentation
  assignment records its own timings separately in the outbound report.

## 7. Add authentication alerts and authorized database access

- [ ] **7.1** Choose the phone-push provider and decide whether periodic live
  authentication probes are needed and at what usage cost.
  Status: Pending.
- [ ] **7.2** Add 15-minute saved-login/CLI-status checks using the existing
  authentication/cache path.
  Status: Pending.
- [ ] **7.3** Distinguish authentication failures from network errors, usage limits, and
  timeouts.
  Status: Pending.
- [ ] **7.4** Pause affected work, preserve progress, and send one credential-free
  incident alert.
  Status: Pending.
- [ ] **7.5** Verify login recovery, notify recovery, and resume eligible work within its
  original authority.
  Status: Pending.
- [ ] **7.6** Verify connectivity to the existing Windows Oracle installation with a
  scoped account; protect `sql_triage` and use `pattern_lab` only for authorized
  experiments.
  Status: Pending.

## 8. Later: v1.2 and beyond

- [ ] **8.1** Add automatic job-completion notifications in v1.2; keep initial status
  checks manual.
  Status: Pending.
- [ ] **8.2** Extend proven checkpoint/recovery behavior to assignments lasting days or
  weeks.
  Status: Pending.

Docker remains deferred. No release dates have been agreed.

Sources: [specification](PROJECT_SPEC.md), [operations](OPERATIONS.md),
[worker-transfer guide](MCP_PROJECT_WORK.md), [validation](VALIDATION.md), and
[exact schemas](MCP_TOOL_SCHEMAS.json). Bootstrap checkmarks describe
implementation presence or historical proof, not blanket fresh live verification.
