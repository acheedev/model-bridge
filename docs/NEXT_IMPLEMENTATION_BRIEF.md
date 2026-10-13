# Next implementation brief: critical 4.7 delivery

Update October 12: John approved this scope; local implementation and tests are delivered. The design below is the historical approval record. Current status: [staged pilot](STAGED_PILOT_2026-10-12.md). Installed activation/client proof remains pending.

Status: concrete scope for John's vote; not implemented or implicitly authorized
by this document. The preceding narrow assignment delivered lifecycle scaffolding
and the [decision proposal](PROJECT_WORK_PROPOSAL_2026-10-11.md). John prioritizes
end-to-end bounded parallel jobs and safe retries. Once remaining choices are
accepted, execute the following phases to delivery rather than leave a roadmap.

## Fixed decisions and remaining vote

| Topic | Decision/remaining choice |
| --- | --- |
| Repo boundary | Accepted: only explicit project-ID -> specific canonical repo under /home/jachee/projects/acheedev/; only model-bridge currently registered |
| Transfers | Accepted separate purposes: /home/jachee/projects/mcp-inbound/ and /home/jachee/projects/mcp-outbound/, never repo access |
| Concurrency | Target maximum 2 staged workers; recommend second-slot gate at >=5 GiB available memory; currently ~4.21 GiB at measured checkpoint |
| Authority | Worker edits staging only; separate authenticated apply permission for the original repo; same-project apply serialized |
| Outside writers | Accept cooperative/no-manual-edits apply window and immediate rechecks, or request stronger isolation; no universal hash-CAS guarantee |
| Limits | Proposed <=1800-second original wall budget, 2048 MiB address space, CPU 300 seconds per process; overrides within current ranges |
| Retry | Proposed initial attempt + max 1 safe retry, fixed 2-second backoff in original budget; never ambiguous model outcome or partial writes |
| Queue/storage | Proposed 8 pending, 1 GiB stage/job, 8 GiB managed retained work, >=1 GiB free; reviewed bulk 7 days, summaries/receipts 90 days; preserve pinned/unreviewed/referenced data |
| Dependency automation | Recommend manual verified A-success/output -> submit B for first delivery; durable dependency machinery is not required yet |
| Live proof budget | Later separate approval for source activation and at most two narrowly briefed model-worker attempts; no automatic extra model calls; actual usage metered because CLI has no promised token cap |

Resource choices above are proposals, not new current defaults. Maximum 2 means
at most two, not a guarantee to launch both under memory pressure. Current limits
are per process; aggregate descendant limits are not proven. No host memory,
permission, service, or billing change is requested implicitly.

## Phase 1: 3.8 staging and apply prerequisite

Implement within current supervisor/transfer architecture:

- Explicit targeted paths; capture original existence/content/modes in immutable
  base receipt, including caller-owned modifications/untracked files.
- Filtered per-job writable staging with exact repo-root and no-follow checks;
  live checkout denied for worker writes. Per-job inputs/scratch/artifacts only.
- Real unified diff + base/after hashes + full bounded replacement artifacts.
  Unsupported binary/encoding/oversize data fails explicitly, never truncates.
- Separate apply contract bound to project/job/bundle/base hashes and authority;
  project apply lock, whole-bundle preflight, immediate target rechecks, exclusive
  additions, verified deletions, output hashes, and durable partial/apply receipts.
- Preserve unrelated work and require review after partial application; never
  blind retry or treat a posthoc diff as protection.

Proof gate: deterministic clean edit/add/delete, stale edited/deleted/missing
base, existing addition, tampered bundle, duplicate apply receipt, symlink/
traversal/outside-root/hardlink cases, unrelated edits, and crash between file
operations. No production apply until separately authorized (3.9). Validate
installed CLI write/read mount boundaries later under explicit test authority.

## Phase 2: immediate 4.6 durable acceptance and storage safeguards

Reuse SQLite/job JSON, not a new orchestrator. Combine acceptance/idempotency
into one transaction. Add bounded phase/attempt/checkpoint/receipt fields and
storage-blocked dispatch behavior. Keep interrupted restart recording/no replay.
Implement agreed preflight watermarks and an operator-reviewed cleanup plan;
active, unreviewed, pinned, and referenced artifacts are ineligible for deletion.

Proof gate: isolated crash before/after acceptance, during worker/publication,
and during apply; idempotent duplicate submit; simulated disk-full/write failure
without actually filling the host; preserved uncertainty and partial evidence.
Advanced recovery remains backlog. Do not claim SQLite makes filesystem apply
atomic or that buffered stdout survives a supervisor crash.

## Phase 3: bounded two-worker dispatch

Replace singular active state and shared input clearing with per-job records,
inputs, stages, timers and process groups. Keep one supervisor lock and short
SQLite transactions. Dispatch maximum two eligible independent staged jobs;
serialize apply per repo. Respect original queue/deadline budgets and memory
admission. Cancellation targets only its job; shutdown accounts for both groups.

Proof gate: non-model barriers prove two jobs actually overlap, independent
resources do not leak/clobber, same-project applies serialize, memory rejection
queues the second job, cancellation leaves the other alive, and restart marks
both active/queued work interrupted without replay. A second launch alone is
not proof of overlapping execution or isolation.

## Phase 4: bounded safe retries

Persist attempt ordinal, request/idempotency hash, start/stop/outcome, and receipt.
At most one retry after a proven pre-model/no-write transient or an idempotent
non-model operation; fixed backoff and remaining original deadline/authority.
Ambiguous model execution, partial writes/publication, auth, cancellation,
stale base, and unknown outcomes are manual-review stops, not retryable labels.

Proof gate: deterministic fail-before-start then success in 2 attempts; repeated
transient stops at 2; backoff/deadline exhaustion prevents attempt 2; partial
write/ambiguous paid outcome produces zero automatic retries; duplicate submit/
apply keys return original receipts without duplicate work. Track resource
usage honestly; per-process limits alone are not a total-job CPU budget.

## Phase 5: 3.9 and final client proof

After local focused/full regressions pass and John separately approves service
activation/client calls, Mimi uses actual authenticated MCP tools to verify:

1. Submit two narrowly scoped jobs with independent stages; observe overlap and
   correct durable status/results and exact outbound byte/hash retrieval.
2. Review an applicable delivered bundle, explicitly authorize one small apply,
   run relevant checks, and retain before/after/receipt evidence. A conflicting
   counterpart must refuse without overwriting caller changes.
3. Exercise safe retry eligibility with an isolated non-model client fixture and
   inspect attempt/backoff/deadline accounting. Do not force real auth/quota
   failures or replay uncertain model calls.
4. Confirm project/transfer boundaries, apply serialization, cancellation scope,
   and interrupted/no-replay behavior with separately authorized safe fixtures.

Mark 4.7 complete only after implemented overlap/retries and final client proof,
3.8 after its guarded-apply scope/limits are demonstrated, and 3.9 only for the
explicitly authorized application/evidence. Do not complete them by this design.

## Effort and cost assumptions

| Package | Rough engineering effort |
| --- | --- |
| Staging/apply and disposable 3.9 cases | 8–16 hours |
| Two-worker dispatch/admission/isolation | 6–12 hours after staging |
| Safe retry/idempotency/attempt accounting | 4–8 hours |
| Immediate storage/checkpoint safeguards | 2–5 hours after parameters agreed |
| Overall planning range | About 20–41 engineering hours, uncertain, not guaranteed wall time |

Assumes one owner/project, narrow text targets, existing SQLite/transfers,
cooperating apply writers, and no broader host admin/automatic recovery. CLI
sandbox compatibility, peak memory, and live client proof may add work. Model
usage is separate from engineering time; non-model overlap/retry simulations
cost zero provider tokens. Later worker calls use subscription limits and need
observed usage; do not promise a token cap the CLI cannot enforce.

4.8 pause/resume and 4.9 one-hour proof stay backlog. A later non-model heartbeat
simulator proves mechanics, not useful model reasoning. An hour exceeds the
current 1800-second cap and needs an explicit isolated-test override if chosen.
No hour-long job, major architecture implementation, model call, service action,
or Git mutation was performed in the preceding narrow assignment.
