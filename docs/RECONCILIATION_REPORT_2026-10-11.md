# Baseline reconciliation report, 2026-10-11

Assignment scope: read-only operational inspection plus narrow documentation
edits. No application code, deployment template, installed unit, service,
startup task, configuration, credential, live model consultation, Git history, or
branch state was changed.

## Timing

- Measurement method: shell `date` for wall-clock timestamps; command results and
  Git/doc checks for completion evidence.
- First recorded start: 2026-10-11 17:01:07 -0400 EDT
  (2026-10-11 21:01:07 UTC).
- Inspection/documentation validation completion: 2026-10-11 17:02:03 -0400 EDT
  (2026-10-11 21:02:03 UTC).
- End: 2026-10-11 17:02:03 -0400 EDT (2026-10-11 21:02:03 UTC), before the final
  status summary.
- Elapsed duration: 56 seconds from the first recorded timestamp to the
  completion/end timestamp.

## Preexisting edits

Before this reconciliation edit, `git status --short --branch` reported:

```text
## main...origin/main
 M docs/PROJECT_SPEC.md
 M docs/TASKS.md
 M docs/VALIDATION.md
```

Those edits were treated as accepted/user-owned baseline content and preserved.
The reviewable diff artifact for this assignment is intentionally labeled as a
diff against HEAD that includes preexisting documentation edits.

## Sanitized evidence

- Checkout: `/home/jachee/projects/acheedev/model-bridge`.
- Branch/HEAD: `main` at `e55d157d9631b85644a0608f169c425e85d6176b`.
- Local tracking ref: `origin/main` at the same revision; no fetch was run.
- Installed unit: `/etc/systemd/system/model-bridge.service`.
- Template: `deploy/model-bridge.service`.
- Template/installed diff: no differences.
- Enablement evidence available by filesystem: `multi-user.target.wants`
  symlink points to the installed unit. `systemctl is-enabled` also returned
  `enabled`.
- Launch settings inspected in both template and installed unit:
  `User=jachee`, checkout `WorkingDirectory`, checkout `.venv/bin/python -m
  model_bridge.claude_bridge`, restart-on-failure, `UMask=0077`, and
  `WantedBy=multi-user.target`.

## Limits and discrepancies

- Host systemd bus checks were blocked in the sandbox with `System has not been
  booted with systemd as init system (PID 1). Can't operate.` and
  `Failed to connect to bus: Host is down`.
- Real active state, MainPID, restart count, active-enter timestamps, target
  relationship details from the manager, process executable/arguments, and
  process working directory were not freshly verified here.
- Process search from inside the sandbox did not expose a real bridge service
  process; it only matched the sandbox command itself.
- No evidence from this pass links a live loaded Python process to the current
  checkout revision or uncommitted source. Loaded-revision uncertainty remains.
- Git emitted denied-path warnings for sandboxed `job-data/...` config files.
  They were not bypassed.

## Documentation changes

- `docs/TASKS.md`: split patch/result delivery from generalized
  concurrent-change protection; left concurrent-change protection unchecked and
  explicitly unfulfilled.
- `docs/VALIDATION.md`: added current reconciliation evidence, blocked checks,
  loaded-revision uncertainty, and corrective next steps.
- `docs/RECONCILIATION_REPORT_2026-10-11.md`: this concise outbound report.

## Proposed next action

Run the same sanitized systemd and process checks from a host context with access
to the real systemd manager and service process. Do not mark reconciliation
complete until those facts are available or explicitly waived.

## Host follow-up: scoped read-only inspection

This follow-up supersedes the earlier sandbox-blocked host checks, without
changing their historical record. No service operations, authentication actions,
model calls, configuration/permission changes, or Git mutations were performed.
Environment values, credential contents, private notes, and job contents were
excluded. Scoped `/proc` inspection was explicitly approved by John.

| Host/process check | Observed evidence |
| --- | --- |
| Service | Loaded; active/running; enabled; `NeedDaemonReload=no` |
| MainPID and restarts | `185421`, stable across process inspection; `NRestarts=0` for the current manager accounting period |
| Account | Configured `jachee`; actual real/effective/saved/fs UID and GID all `1000`, account/group `jachee` |
| Start | Systemd reports 2026-10-11 20:44:25 UTC (2026-10-11 16:44:25 -0400, America/New_York); this is the manager's exec-start timestamp |
| Actual executable | `/proc/185421/exe` points to `/usr/bin/python3.10` |
| Actual sanitized arguments | Checkout `.venv/bin/python -m model_bridge.claude_bridge`, exactly matching configured `ExecStart` |
| Actual working directory | `/home/jachee/projects/acheedev/model-bridge` |
| Checkout linkage | Process holds checkout `job-data/.manager-lock`; other descriptor destinations withheld |

Effective non-environment launch settings agree with the maintained template
already recorded in this session: description, `Type=simple`, `User=jachee`,
checkout working directory and module command, `Restart=on-failure`, 5-second
restart delay, 10-second stop timeout, `UMask=0077`, and `network.target` ordering.
Systemd adds normal implicit ordering dependencies. The manager lists no relevant
drop-ins or environment files. It reports `WantedBy=multi-user.target`; the
root-owned enablement symlink resolves to the installed unit. The installed unit
is a regular root:root file, mode `0644`. A fresh full-content unit comparison
was deliberately excluded because environment values were out of scope; the
earlier full-file comparison remains historical evidence only.

### Current Git snapshot

Branch `main`; full HEAD and locally available `origin/main` both
`e55d157d9631b85644a0608f169c425e85d6176b`. Local `main` tracks `origin/main`.
Only these local branch/tracking refs were present; their remote freshness is
unknown because no fetch was performed. Before this follow-up, tracked changes
were `.gitignore`, `docs/OPERATIONS.md`, `docs/PROJECT_SPEC.md`, `docs/TASKS.md`,
and `docs/VALIDATION.md`; untracked public files were this report,
`DIRECTORY_BOUNDARY_AUDIT_2026-10-11.md`, and `PUBLIC_AUDIT_DIFF_2026-10-11.patch`.
No staged changes were reported. Existing edits were preserved. `model_bridge/`,
`deploy/`, `scripts/`, and `pyproject.toml` had no tracked or untracked changes.
`git ls-files -- private` returned no tracked entries; private notes were not read.

### Remaining evidence limits and proposed remedies

The actual command, working directory, interpreter resolution, and manager-lock
handle link the process to this checkout. They do **not** identify the loaded
Python source revision. HEAD and a currently clean source tree cannot prove what
was imported at startup; loaded module paths/bytes, prior edits, import-path
overrides, and installed dependencies were not captured. Retain loaded-revision
uncertainty. Under future implementation authority, record startup source
digests/revision and imported module paths for reproducible provenance.

No discrepancy was observed in the inspected launch settings or metadata.
Environment values and overrides remain uninspected, so full unit equivalence,
effective provider paths, and any overridden transcript/auth-cache paths are not
claimed. Default-cache absence is not an authentication failure. Account login
validity, credential freshness, availability after terminals close, and reboot
persistence were not tested. The public audit contains the metadata evidence.

### Follow-up timing

Start: 2026-10-11T21:18:19.363855+00:00 UTC (2026-10-11 17:18:19 -0400, America/New_York).
Inspection completion: 2026-10-11T21:21:32.824247+00:00 UTC.
Documentation implementation completion: 2026-10-11T21:22:08.384600+00:00 UTC.
Validation/finish checkpoint: 2026-10-11T21:22:36.877071+00:00 UTC (2026-10-11 17:22:36 -0400).
Elapsed wall-clock span: 251.7 seconds, measured with a monotonic clock;
includes permission consultation and waiting. Outcome: completed within scope;
remaining evidence limits are explicit above. No model consultations.
Documentation links and `git diff --check` passed.
