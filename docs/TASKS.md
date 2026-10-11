# Project checklist

Updated October 11, 2026. Work top to bottom; each box is a useful stopping point.
Checked items have source or documentation evidence. Live service, host, and
end-to-end behavior need their own checks. This list tracks work, not permission
to install, restart, commit, push, expose endpoints, or run paid model probes.

## 1. Give the project a clean home

- [x] Put Python code in `model_bridge/`, documentation in `docs/`, launch scripts in `scripts/`, and service configuration in `deploy/`.
- [x] Update imports, worker launch paths, startup commands, and documentation links.
- [x] Keep transcripts, temporary files, and job data rooted in the checkout.
- [x] Add a short README with navigation and a Python package manifest.
- [x] Ignore `private/` before creating any private inventory.
- [ ] Update the installed service to the new module entry point and verify authenticated startup under separate service authority.

## 2. Close the baseline

- [x] Run existing tests and record results, known diagnostics, and validation limits: [layout validation](VALIDATION.md).
- [ ] Create private credential inventory and recovery notes without copying secret values; verify nothing in `private/` is tracked.
- [ ] Audit runtime/test directories, overrides, caches, and symlinks against the approved Linux roots; retain the systemd/journal exceptions.
- [ ] Reconcile this checkout, service checkout, installed unit, running revision, and working-tree changes.
- [ ] Verify explicit systemd enablement and startup target, then authenticated `bridge_ping`.
- [ ] Confirm MCP remains available after all Ubuntu terminals and VS Code close.
- [ ] Configure and verify Ubuntu/service startup after a Windows reboot; check Windows power settings.
- [ ] Review the baseline and record evidence and timestamps in the documentation.
- [ ] Under separate Git authority, reconcile the feature branch with current main, perform the planned interactive rebase, review, merge, and push in the agreed order.

## 3. Prove one complete coding loop

- [x] Implement the narrow model-bridge worker with explicit edit/test authority and no commit/push authority.
- [x] Implement verified byte-preserving input transfers and sanitized outbound artifacts.
- [ ] Confirm client discovery of all seven worker-transfer tools after the authorized service update.
- [ ] Complete client byte/size/SHA-256 readback proof with actual reference files; keep the transfer receipt and comparison evidence.
- [ ] Choose one small task and write its brief, exact acceptance criteria, and authority.
- [ ] Supply a filtered read-only snapshot with provenance and hashes, excluding credentials.
- [ ] Return a reviewable patch and validation evidence; detect concurrent project changes before application.
- [ ] Review and apply the patch through a separately authorized step, run relevant checks, and save the end-to-end evidence.
- [ ] Decide broader project allowlisting, patch transport, output truncation, and resource limits before generalizing beyond model-bridge.

## 4. Make background work dependable

- [x] Implement durable job IDs, prompt acceptance, status/results, elapsed-time reporting, and cancellation.
- [x] Serialize bootstrap jobs and mark queued/running work interrupted after restart without automatic replay.
- [ ] Verify a model-driven job, result retrieval, cancellation, and interruption recovery end to end.
- [ ] Define the broader durable state model, restart policy, retention/disk limits, and recovery rules.
- [ ] Add task dependencies, checkpoints, bounded parallelism, retries, and resource budgets.
- [ ] Add status/pause/resume/cancel controls with clear stop rules for conflicts, exhausted limits, and stalled progress.
- [ ] Prove one unattended hour-long assignment before extending to multi-day projects.

## 5. Connect ChatGPT and bring in Gem

- [ ] Select a supported authenticated connection for ChatGPT and the iPhone app.
- [ ] Review Gem's supplied integration instructions and decide Gemini authentication.
- [ ] Add Gemini through the common independent/critique/follow-up consultation contract.
- [ ] Under separate integration and live-probe authority, validate client access and Gemini behavior; preserve transcripts and usage evidence.

## 6. Build reusable council workflows

- [ ] Research `garrytan/gstack`; select useful components, pin a source revision, and retain licenses, attribution, and adaptation notes.
- [ ] Create versioned `workflows/` templates A-E: code review, solution proposal, code authoring, council consultation, and troubleshooting.
- [ ] Define inputs, assignments, outputs, completion criteria, and escalation rules; persist the template version with every job.
- [ ] Build one shared council briefing with independent first responses and bounded execution for each member.
- [ ] Report every member's status, disagreements, comparison, Mimi's recommendation, and links to individual transcripts; keep consultation separate from implementation authority.
- [ ] Record observed start/completion/validation times and elapsed-time measurement methods; leave unknown values unknown.

## 7. Add authentication alerts and authorized database access

- [ ] Choose the phone-push provider and decide whether periodic live authentication probes are needed and at what usage cost.
- [ ] Add 15-minute saved-login/CLI-status checks using the existing authentication/cache path.
- [ ] Distinguish authentication failures from network errors, usage limits, and timeouts.
- [ ] Pause affected work, preserve progress, and send one credential-free incident alert.
- [ ] Verify login recovery, notify recovery, and resume eligible work within its original authority.
- [ ] Verify connectivity to the existing Windows Oracle installation with a scoped account; protect `sql_triage` and use `pattern_lab` only for authorized experiments.

## Later: v1.2 and beyond

- [ ] Add automatic job-completion notifications in v1.2; keep initial status checks manual.
- [ ] Extend proven checkpoint/recovery behavior to assignments lasting days or weeks.

Docker remains deferred. No release dates have been agreed.

Sources: [specification](PROJECT_SPEC.md), [operations](OPERATIONS.md),
[worker-transfer guide](MCP_PROJECT_WORK.md), and [exact schemas](MCP_TOOL_SCHEMAS.json).
The bootstrap checkmarks describe implementation presence, not fresh live verification.
