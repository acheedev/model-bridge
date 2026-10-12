# Model Bridge project specification

Status: reconciled project direction and implementation status as of
October 10, 2026, America/New_York.

Layout update, October 11, 2026: Python source is in `model_bridge/`, documentation
in `docs/`, launch scripts in `scripts/`, and the maintained unit in `deploy/`.
Runtime stores remain at the checkout root. The ordered [project checklist](TASKS.md)
tracks implementation and outstanding validation without changing this specification's scope.

Source basis: the verified inbound `PROJECT_SPEC.md` and `README.md` from
transfer `4c41071bfb3c48369b66a07b00651dc8`, merged with the current repository
documentation and observed source/doc evidence. The inbound documents are
reference material, not execution authority. This file distinguishes observed
current behavior, implementation reports, approved plans, proposals, and open
questions.

## 1. Purpose

Model Bridge is a loopback-only authenticated MCP service for human-led
consultation and controlled project work. It starts with dependable Claude and
Codex consultations, preserves readable records, and provides a path toward
background implementation jobs and council coordination.

Long-running work must preserve state outside a chat turn. A larger timeout is
not the architecture for unattended projects.

## 2. Roles and authority

| Member | Title | Role |
| --- | --- | --- |
| John Achee | Chief Solutions Architect | Sets direction, approves scope, and defines execution authority. |
| Mimi | Chief Information Officer | Coordinates assignments, synthesizes evidence, and recommends decisions. |
| Ezra | Principal Developer | Sole code author in v1; also participates as a council consultant. |
| Gem | Principal Solutions Consultant | Advice and independent review only in v1. |
| Claude | Principal Solutions Consultant | Advice and independent review only in v1. |

Consultation does not authorize implementation. Project briefs define authority
in advance so routine work inside approved scope can continue without repeated
approval requests. Applying changes, committing, pushing, installing, restarting
services, and live provider probes remain distinct authorized operations.

## 3. Current baseline

Observed in the repository documentation and source layout:

- Authenticated local MCP at `http://127.0.0.1:8081/mcp`.
- `bridge_ping`, `ask_claude`, `ask_codex`, and `save_synthesis`.
- Claude API consultations when the optional Anthropic key is present.
- Codex CLI consultations using saved ChatGPT file authentication, isolated
  temporary homes, read-only supplied-context execution, recursion guards,
  disabled tools/plugins/apps/hooks/sub-agents, and transcript persistence.
- Provider-separated threads, SQLite-backed history, Markdown/JSON transcripts,
  readable title-based filenames for new threads, and `index.md`.
- Model, reasoning-effort, task, timeout, and title controls for Codex, with
  explicit catalog validation for requested model/effort combinations.
- Byte-preserving MCP file transfer and a separate authorized project worker.

Implementation reports in `MCP_PROJECT_WORK.md` say the worker-transfer bootstrap
is implemented and tested, with exact tool schemas in `MCP_TOOL_SCHEMAS.json`.
This worker capability was added before the planned baseline-closeout merge.
That sequencing is now historical fact, not a reason to treat all later roadmap
items as complete.

Observed after the layout update: the installed Ubuntu systemd service was
reported updated and separately spot-validated as enabled, active, running the
new module entry point, and accepting authenticated `bridge_ping`; see
[validation](VALIDATION.md#systemd-service-validation). A post-restructure
authenticated ping also exposed all 11 tool schemas, including the seven
transfer/project tools. This proves reachability and schema exposure, not
installed-unit/source reconciliation, fresh transfer roundtrip, live
cancellation/recovery, worker execution, or provider login. Availability after
closing terminals, startup before Windows sign-in, uninterrupted uptime, and
Windows power settings still need explicit verification.

## 4. Current worker-transfer capability

The current bootstrap is intentionally narrow:

- Seven MCP tools are documented: `transfer_upload`, `transfer_manifest`,
  `transfer_read`, `project_submit`, `project_status`, `project_result`, and
  `project_cancel`.
- Binary transfer is canonical base64 with byte-exact SHA-256 and size
  accounting. Completed transfers are immutable.
- Only `project_id: "model-bridge"` is accepted.
- The only accepted authority is
  `{"edit":true,"test":true,"commit":false,"push":false}`.
- Jobs receive verified inbound files through read-only `.worker-inputs/`
  mounts, can edit this checkout, can run relevant tests, and publish sanitized
  outbound artifacts.
- Worker Git access is read-only for this repository, shell networking is
  disabled, and nested bridge/runtime submissions are blocked.
- Jobs are serialized; queued/running jobs become `interrupted` after restart
  and are not replayed automatically.

Known limits:

- This is not a hostile-code multi-tenant isolation system.
- CPU and memory limits are per process rather than cgroup-wide budgets.
- Failure or cancellation does not revert project edits.
- A succeeded worker result records the worker's completion claim; it is not an
  independent proof that every assertion is true.
- Retention of completed transfers and job records is manual.

## 5. Approved milestones

### Milestone 1: Close out the baseline

Keep the README and project specification current as work proceeds. Record
decisions, validation evidence, limitations, and next actions.

Approved baseline-closeout work:

- Store private credential inventory and recovery notes under project `private/`,
  ignored before files are created. Verify the directory has no tracked contents.
  Leave actual secret values in protected credential files.
- Verify runtime/test temporary files, transcripts, caches, configured
  overrides, and symlink destinations stay under `/home/jachee/projects` and
  `/home/jachee/.codex`.
- Preserve the approved exception for systemd registration under
  `/etc/systemd/system` and logging through the system journal.
- Check the working tree, service checkout, running revision, service startup,
  and authenticated MCP access. Record validation results and timestamps before
  treating the baseline as closed.
- Preserve the reported historical Git closeout separately from the current
  layout. John relayed Ezra's report that `feature/codex-runner` was rebased,
  fast-forward pushed, merged/pushed to `main` at `11a56a1`, deleted
  locally/remotely, and left a clean tree with 91 previously passing tests.
  Current-layout Git state still requires separate Git authority before any new
  Git operation.

Pending clarification/housekeeping for this milestone:

- Section 5.2 already includes automatic Ubuntu startup and service
  startup/reboot verification, but the earlier specification did not precisely
  capture explicit `systemd` enablement and target checks.
- The previously requested interactive feature-branch rebase is now a reported
  historical closeout for an already deleted branch, not an unresolved future
  step. Any new Git housekeeping still requires separate authority.

### Milestone 2: Build one useful coding loop

Pick a small project task. Supply a filtered, read-only snapshot; let Ezra
inspect it and return a patch; review the patch; apply it through a separate
authorized operation; run relevant checks and record the result.

The current worker-transfer bootstrap partially advances this milestone by
providing verified input transfer, authorized project jobs, relevant validation,
and outbound artifacts. It does not finish the full generalized coding loop for
arbitrary projects or broader patch-review policy.

Completion evidence: one end-to-end task with supplied context, generated patch,
review, authorized application, concurrent-change protection, and relevant
validation.

### Milestone 3: Make long work manageable

Add persistent jobs with IDs, status, elapsed time, cancellation, and result
retrieval. Return promptly after accepting work instead of holding one MCP call
open for the whole task.

The current `project_submit`/status/result/cancel path is an implemented
bootstrap for the model-bridge project only. A historical model-driven
documentation job and outbound artifact retrieval succeeded after an earlier
failed job exposed an input-mount issue that was repaired. Live cancellation and
interruption recovery remain unproved end to end. Remaining design work includes
bounded parallelism, restart policy beyond marking interrupted jobs, dependency
ordering across coding/review/application/validation steps, and richer recovery.

Automatic job-completion notifications are deferred until v1.2.

### Milestone 4: Connect this chat and add Gem

Investigate the supported connection path for John's ChatGPT client, including
the iPhone app. Review Gem's supplied integration instructions and add Gemini
using the common consultation contract.

This remains planned work. Do not expose a remote endpoint, install provider
integrations, or run live model probes without separate authority.

### Milestone 5: Add council coordination

Coordinate Ezra's code authoring with independent advice and review from Claude
and Gem. Give every participant a clear assignment, shared evidence, and bounded
execution.

"Run this by every member of the council" should create a consultation workflow
with one shared briefing, independent first responses, complete member status
accounting, Mimi's comparison/recommendation, and links to individual Markdown
transcripts. Ezra is a consultant in this workflow; it does not launch
implementation.

This remains planned work.

## 6. Additional approved requirements

### 6.1 Persistent project execution

The long-term destination is a project runner that executes thorough assignments
through planning, coding, consultation, testing, and delivery across hours, days,
or weeks.

It needs a project brief with acceptance criteria and authority, durable tasks
and dependencies, checkpoints, decisions, test evidence, bounded retries and
resource budgets, and status/pause/resume/cancel controls. Stop for conflicting
instructions, exhausted limits, or stalled progress rather than looping
indefinitely.

Build toward this architecture incrementally; prove one unattended hour-long task
before extending to longer projects.

### 6.2 Host availability and Oracle

Use John's normally powered-on Windows PC as the worker host. Docker is deferred.

Next infrastructure tests:

- Verify Ubuntu and authenticated MCP access after all Ubuntu terminals and
  VS Code close.
- Reconcile explicit `systemd` enablement and target configuration with the
  running service/source state after changes.
- Configure and verify automatic Ubuntu/service startup before Windows sign-in.
- Recheck automatic Ubuntu/service startup after Windows sign-in when the startup
  mechanism changes. Historically, a Task Scheduler task under `aihub\default`
  with interactive logon launched Ubuntu as `jachee` after PIN sign-in, and
  authenticated bridge access was checked at 2026-10-11 01:18:20 -0400.
- Verify Windows power settings support the required availability.

Keep Oracle on Windows. Do not install another database in WSL. Verify network
connectivity and use an appropriately scoped database account for authorized
work. Protect `sql_triage`; use `pattern_lab` for authorized experiments.

### 6.3 Authentication watchdog and phone alerts

Add a watchdog for Ezra's authentication and alert John by phone push when
interactive login is required.

Approved design:

- Preliminary saved-login/CLI-status checks every 15 minutes. They are not proof
  of backend acceptance.
- Classify authentication failures separately from network problems, usage
  limits, and timeouts encountered during actual work.
- Pause affected jobs, preserve progress, and send one incident alert instead of
  repeated alerts or endless retries.
- Verify recovery after login, send a recovery notification, and resume eligible
  jobs within their original authority.
- Reuse existing bridge authentication handling rather than create a competing
  refresh/cache path.
- Keep credentials and project contents out of push messages.

Phone push is selected; the provider remains undecided. Any periodic live model
probe requires a separate decision about frequency and subscription usage.

### 6.4 Standard workflow templates

Store versioned reusable workflows in the repository under `workflows/`. Each
defines required inputs, assignments, outputs, completion criteria, and
escalation rules. Save the template version with each job.

| Template | Purpose | Standard response |
| --- | --- | --- |
| A: Code review | Evaluate scope, patch, and requirements. | Severity-ranked findings, file references, suggested fixes, verdict. |
| B: Solution proposal | Compare ways to meet goals and constraints. | Options, tradeoffs, recommendation, implementation plan. |
| C: Code authoring | Implement a specification from authorized context. | Ezra's patch, validation results, remaining issues. |
| D: Council consultation | Gather independent assessments of a shared briefing. | Member opinions, comparison, disagreements, Mimi's recommendation. |
| E: Troubleshooting | Investigate symptoms using reproducible evidence. | Hypotheses, diagnostics, verified cause when established, proposed fix. |

Research [garrytan/gstack](https://github.com/garrytan/gstack) before inventing
equivalents. Map useful existing workflows to these templates, adapt permissions
and council roles, validate them against this project, pin the reused source
version, preserve applicable license notices and attribution, and record
modifications.

This approves reuse-oriented investigation and adaptation, not unconditional
installation or execution of upstream workflows.

### 6.5 Readable records and progress documentation

Markdown is the primary human-readable record. Council reports contain the
question, shared briefing, member status, comparison table, synthesis, unresolved
disagreements, and links to individual transcripts. JSON remains available for
machine processing.

Record task start, implementation completion, validation completion, elapsed time,
and measurement method. An unrecorded timestamp or unknown measurement stays
unknown. Documents must distinguish observed results, approved plans, unresolved
decisions, technical proposals, and implementation reports.

## 7. Release boundaries

| Scope | Agreement |
| --- | --- |
| v1 authoring | Ezra alone writes code; Claude and Gem consult. |
| Initial background interaction | Manual code-check and council status checks. |
| v1.2 | Automatic job-completion notification mechanism. |
| Authentication alerts | Phone push watchdog requirement, separate from completion notifications. |
| Docker | Deferred. |
| Oracle | Existing Windows installation; no duplicate WSL installation. |
| Multi-day projects | Long-term target, proven incrementally. |

No additional release dates were agreed. Do not invent a schedule or treat the
roadmap as a completed implementation.

## 8. Unresolved choices

- Supported iPhone/ChatGPT connection and authenticated remote-access mechanism.
- Gem's supplied integration instructions and authentication approach.
- Push provider and any live authentication-probe schedule.
- CLI output capture/truncation, patch transport, and resource limits for larger
  project work.
- Job storage/state model, interrupted-work policy, concurrency limits, and
  coordinator implementation beyond the current single-project bootstrap.
- Exact gstack components, source revision, compatibility, and adaptation scope.
- Evidence requirements for any future Git housekeeping after the reported
  `feature/codex-runner` closeout.

## 9. Documentation evidence and limits

Historical documentation merge evidence includes verified inbound file hashes
and review of the repository README, `MCP_PROJECT_WORK.md`, and
`MCP_TOOL_SCHEMAS.json`. Later validation separately spot-checked the installed
systemd service and authenticated `bridge_ping`. This specification update did
not run live model consultations, inspect secrets, restart services, perform a
fresh transfer roundtrip, prove live cancellation/recovery, rebase, commit,
merge, or push.

Future technical completion should verify current source/configuration, installed
service files, running checkout, tests, credential handling, private inventory,
directory boundaries, and known diagnostics before broadening implementation
claims.
