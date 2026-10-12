# Credential Inventory and Directory Boundary Audit, 2026-10-11

Assignment scope: private credential inventory plus sanitized directory-boundary
audit. No code, runtime configuration, service state, permissions, credential
stores, production data, live provider calls, Git history, commits, pushes, or
authentication state were changed. The only non-document edit was adding the
approved repository-root `/private/` ignore rule.

## Timing

- Time source: shell `date` in America/New_York; duration below uses the first
  captured audit timestamp and final validation timestamp.
- First captured audit timestamp: 2026-10-11 17:11:50 -0400 EDT
  (2026-10-11 21:11:50 UTC).
- Inspection/documentation validation completed: 2026-10-11 17:13:47 -0400 EDT
  (2026-10-11 21:13:47 UTC).
- End: 2026-10-11 17:13:47 -0400 EDT, before final status return.
- Elapsed duration by captured timestamps: 1 minute 57 seconds.
- Limit: initial exploratory commands began before the first captured timestamp;
  their exact wall-clock start was not independently recorded.

## Private Inventory Status

- Status: Complete for source/configuration/metadata-supported inventory.
- `private/` was absent at the initial check, so there were no existing private
  notes or tracked private contents to inspect.
- The exact `/private/` rule was added to `.gitignore` while preserving existing
  rules, including the preexisting `private/` rule.
- The created `private/` directory resolved inside this checkout and was a normal
  directory, not a symlink redirect.
- A private credential inventory/recovery note was created under `private/` after
  the ignore and location checks. Its contents are intentionally excluded from
  this public report and outbound artifacts.
- Final checks confirmed the private note is ignored and no `private/` path is
  tracked by Git.
- No credential values, auth headers, provider calls, login/refresh commands, or
  secret-bearing file contents were read or copied.

Inventory count: five credential/procedure records, covering local MCP bearer
authentication, optional Claude provider authentication, Codex ChatGPT saved
login, the bridge-owned Codex refresh cache, and the local MCP header helper.
Unverified facts remain for protected-store file metadata and provider account
state because those checks would require credential-store or live-provider
access outside this assignment.

## Directory Audit Status

Status: Complete for repository source, public documentation, accessible
filesystem metadata, and deterministic local path-resolution evidence. Host
systemd active-state and real process checks remain pending from the prior
sandbox limitation and were not re-debugged.

| Category | Purpose and source | Resolved destination | Root/exception | Accessible evidence | Verdict |
| --- | --- | --- | --- | --- | --- |
| Transcripts, index, database | Consultation history from `bridge_paths.py` and `claude_bridge.py` | Checkout `transcripts/` by default; override must resolve under approved roots | `/home/jachee/projects` or approved Codex root | Existing directory resolved inside checkout, mode `0700`; source wraps database and exports with approved-path checks | Supported; override safety covered by source/tests, live override not exercised |
| Job records | Durable worker state from `project_jobs.py` | Checkout `job-data/` by default | `/home/jachee/projects` | Directory metadata visible but contents denied by sandbox profile; source uses approved-path checks and private JSON writes | Supported for destination; contents intentionally not inspected |
| Isolated worker homes and scratch | Per-job child home, auth copy, launch/result schema, stdout capture | Per-job subdirectory below job state; worker `TMPDIR` points at checkout `.tmp/` | `/home/jachee/projects` | Source shows state dir denial to child, isolated child home removal, private process launcher, resource limits | Supported by source/tests; host process facts pending |
| Consultation temp homes/workdirs | Ephemeral Codex CLI home and empty workdir | Checkout `.tmp/` | `/home/jachee/projects` | Existing `.tmp/` resolved inside checkout, mode `0700`; source rejects symlink escape and creates `0700` | Supported |
| Inbound transfers | Byte-preserving upload store | Projects-root transfer directory | `/home/jachee/projects` | Directory absent in this sandbox; source requires root under projects and creates via no-follow ancestor pinning | Supported by source/tests; live store metadata absent here |
| Outbound transfers and artifact publication | Sanitized result/artifact retrieval store | Projects-root transfer directory | `/home/jachee/projects` | Directory absent in this sandbox; source validates artifact relative paths and reserved names | Supported by source/tests; live store metadata absent here |
| Staged worker inputs | Read-only active-job input exposure | Checkout `.worker-inputs/` | `/home/jachee/projects` | Existing directory resolved inside checkout, mode `0700`; source clears before/after active jobs | Supported; no other job private contents inspected |
| Test fixtures and disposable checkouts | Unit-test temp roots, transfer/job test stores | Checkout `.tmp/` in tests | `/home/jachee/projects` | Tests use project `.tmp/`; source does not rely on global `/tmp` for bridge temp roots | Supported |
| Cache and auth overrides | Transcript dir and Codex refresh cache path controls | Approved roots only | `/home/jachee/projects` or approved Codex root | Source rejects path escapes and source/cache collision; protected Codex root metadata not visible here | Supported by source/tests; protected-store metadata pending |
| Cleanup targets | Pending transfers, worker inputs, temporary homes, failed auth temps | Transfer roots, `.worker-inputs/`, `.tmp/`, protected cache parent | Approved roots | Source cleanup is bounded to pinned directories or explicit temp files; tests cover cleanup and symlink rejection | Supported; no production cleanup performed |
| Service/drop-in path settings | Installed launch boundary | Repository template; installed service checked in prior reconciliation | Systemd registration exception under `/etc/systemd/system`; logging exception via journal | Prior pass found unit/template agreement but active host manager/process facts blocked | Partially supported; host active-state and process revision pending |

## Findings

- No boundary violation was found in source-defined write roots. Runtime and test
  paths resolve under `/home/jachee/projects` or the approved Codex root, with
  the documented systemd and journal exceptions.
- The new exact `/private/` ignore rule is present. The preexisting `private/`
  rule was preserved.
- The protected Codex root was not visible in this worker sandbox, so credential
  store metadata, actual helper metadata, cache freshness, provider account
  ownership, and live login state remain unknown.
- The visible denied `job-data/...` shell startup and Git config warnings are
  sandbox artifacts from this worker environment. They were not treated as host
  write evidence and were not bypassed.
- The worker sandbox can expose synthetic namespace paths; a visible path inside
  that namespace is not, by itself, proof of an outside host write. Evidence was
  limited to source, tests, and accessible metadata.

## Follow-Up

- Re-run sanitized host systemd/process checks from a context that can see the
  real systemd manager and bridge process. Keep MainPID, active-state,
  process-working-directory, command-line, and loaded-source revision pending
  until then.
- Verify protected credential-store metadata and recovery steps only under
  separate authority that permits credential-store inspection without printing
  secret values.
- Continue to keep private inventory notes and credential-bearing logs out of
  outbound transfers and public reports.

## Host metadata follow-up

This follow-up supersedes the earlier inaccessible/absent host-metadata findings.
Only fixed-path metadata was inspected; transfer contents, per-job directories,
credential contents, helper contents, and private notes were not read. All paths
below resolve to themselves with no symlink redirects and are owned by
`jachee:jachee` (UID/GID `1000:1000`), unless marked absent.

| Resolved path | Type / mode |
| --- | --- |
| `/home/jachee/projects/mcp-inbound` | Directory `0700` |
| `/home/jachee/projects/mcp-outbound` | Directory `0700` |
| `/home/jachee/.codex` | Directory `0700` |
| `/home/jachee/.codex/model-bridge` | Directory `0700` |
| `/home/jachee/.codex/model-bridge/bridge.token` | Regular file `0600` |
| `/home/jachee/.codex/model-bridge/anthropic.key` | Regular file `0600` |
| `/home/jachee/.codex/auth.json` | Regular file `0600` |
| `/home/jachee/.codex/model-bridge/codex-auth-cache.json` | Absent at the default location; no file permissions/owner to verify |
| `/home/jachee/.codex/model-bridge/codex-http-headers.py` | Regular file `0700` |
| Checkout `transcripts/`, `job-data/`, `.tmp/`, `.worker-inputs/`, `private/` | Each directory `0700` |

The real inbound/outbound roots match the fixed paths in
`model_bridge/file_transfers.py`; the current runtime source initializes the
transfer store with those defaults. They are siblings of the active project,
inspected only because this assignment explicitly concerns those stores. Their
contents were not listed. `/home/jachee/projects` itself is `jachee:jachee`,
mode `0755`; the private leaf directories restrict traversal.

Interpreter symlinks inside the checkout are `.venv/bin/python -> python3`
and `.venv/bin/python3 -> /usr/bin/python3`; resolution yields
`/usr/bin/python3.10`, agreeing with the approved process executable-link check.
The outside interpreter target was not opened or statted. This is an installed
runtime dependency, not a project-data write-root escape.

No permission or path discrepancy was observed in these fixed locations.
Credential metadata proves protection/existence only, not authentication validity
or provider-account ownership. Runtime environment values were not inspected;
`CODEX_HOME`, transcript-directory, and auth-cache overrides remain unverified.
The absent default cache is optional until a refresh is persisted and does not
prove that no overridden cache exists. No fix is warranted from absence alone.
Per-job credential copies and transient paths were not inspected. See the
[host reconciliation follow-up](RECONCILIATION_REPORT_2026-10-11.md#host-follow-up-scoped-read-only-inspection)
for process evidence and loaded-revision limits.
