# Gemini validation and narrow repairs

Target: live Ubuntu `/home/jachee/projects/acheedev/model-bridge` only.

## 1. Live conversation-mode checks

Four new generation attempts used the actual registered FastMCP `ask_gemini`
handler through `mcp.call_tool`, not direct SDK-only generation. This was an
isolated host handler test, not a new authenticated HTTP client test. Mimi's
prior authenticated MCP proof remains in the [activation record](GEMINI_HOST_ACTIVATION_2026-10-11.md).

Each call explicitly selected `gemini-3.5-flash-lite`: 30,000 ms HTTP timeout,
128-token cap, one total attempt, no fallback, no automatic function calling.
Only tiny synthetic nonce/context was supplied. The existing protected Gemini
key loader was used privately; no other provider credentials were read.

| Call | Observation | Finish | Prompt / candidate / total tokens |
| --- | --- | --- | --- |
| independent-A | MB-Q7; fresh one-user-message thread | STOP | 127 / 4 / 131 |
| open-A | MB-Q7 retained from earlier history | STOP | 178 / 4 / 182 |
| critique-A | Explicitly discussed supplied other_answer MB-Z9; incomplete critique | MAX_TOKENS | 255 / 124 / 379 |
| independent-B | CLEAN; new thread, no prior nonce | STOP | 129 / 2 / 131 |

Total: **689 prompt + 134 candidate = 823 tokens**. Thinking usage was null,
not inferred as zero. Provider-reported model matched 3.5 Flash-Lite for all four.

Critique received and discussed `other_answer` but did not obey the requested
exact short output format. It hit `MAX_TOKENS`; this proves supplied-content
receipt, not a complete critique or guaranteed exact-format compliance. The
historical result had `truncated: false` because the old flag covered only the
character cap. The subsequent repair includes provider token truncation;
local tests prove the change without repeating a live request.

| Call | Start / completion (America/New_York, EDT) | Monotonic handler wall seconds |
| --- | --- | --- |
| independent-A | 2026-10-11T21:23:25.880179-04:00 / 2026-10-11T21:23:26.364217-04:00 | 0.48404 |
| open-A | 2026-10-11T21:23:26.364325-04:00 / 2026-10-11T21:23:26.712885-04:00 | 0.348566 |
| critique-A | 2026-10-11T21:23:26.713018-04:00 / 2026-10-11T21:23:27.437426-04:00 | 0.724414 |
| independent-B | 2026-10-11T21:23:27.437588-04:00 / 2026-10-11T21:23:27.819456-04:00 | 0.381873 |

Timing used timezone-aware datetime around each handler call and a monotonic
clock for duration. Runner request duration is separately retained in results.
Assignment-wide start/duration were not measured and remain unknown.

Open/critique reused the first Gemini thread; independent-B had exactly one
user message, a different thread ID, and neither prior nonce in its request.
Local synthetic SQLite fixtures rejected Claude and Codex IDs before generation.
No existing-provider live requests were made.

Synthetic live evidence is retained under the ignored workspace:
`/home/jachee/projects/acheedev/model-bridge/.tmp/gemini-checks-5hdpwbb9/`.
It includes `live-results.json`, `repaired-suite.json`, and JSON/Markdown pairs:

- `/home/jachee/projects/acheedev/model-bridge/.tmp/gemini-checks-5hdpwbb9/live-transcripts/2026-10-11_21-23-25-0400_gemini_gemini-contract-nonce-a_53619398.md`
- `/home/jachee/projects/acheedev/model-bridge/.tmp/gemini-checks-5hdpwbb9/live-transcripts/2026-10-11_21-23-27-0400_gemini_gemini-contract-clean-b_f186f442.md`

## 2. Mocked failures and limits

Existing meaningful tests were reused for missing SDK/key, blocked/empty
responses, length truncation, usage/finish metadata, and failed-history behavior.
Nine focused regressions additionally cover invalid local keys/timeouts,
API_KEY_INVALID, 401/403 auth, 429 quota, 400 invalid request, 404 model access,
503 provider errors, connection/HTTP timeout failures, provider MAX_TOKENS,
provider-thread isolation, and exclusion of a synthetic secret sentinel from
public responses and persisted transcript errors.

The shared input check previously omitted the known Gemini key. It now rejects
that key in question/context/other_answer/title before persistence or generation.
Actionable error categories/statuses are returned without raw provider bodies,
headers, or secret-bearing messages. No actual key/quota failure was forced.

## 3. Direct-host full regressions

Command from the Ubuntu checkout:

```bash
env -u MODEL_BRIDGE_CHILD -u PROJECT_WORKER_CHILD .venv/bin/python -m unittest discover -s tests -v
```

- Original authorized run: **100 passed, 0 failed, 0 errors, 0 skipped**, exit 0.
  October 11, 21:09:36.133988–21:09:39.702800 EDT; monotonic subprocess duration
  3.568801 seconds. Recorded here without repeating unchanged work.
- Narrow repairs justified one subsequent full run: **109 passed, 0 failed,
  0 errors, 0 skipped**, exit 0. October 11, 21:24:28.357497–21:24:32.456496 EDT;
  monotonic subprocess duration 4.098999 seconds; unittest measured 3.103 seconds.

Both runs were direct-host executions, outside project_submit, with both
inherited recursion markers absent. All existing Claude/Codex, transfer,
registration, and worker regressions passed using mocks/disposable fixtures.
No production-job cancellation occurred. The initial eight focused tests passed
before adding a ninth token-truncation regression; the final suite includes all nine.

## 4. Actual SDK retry/timeout enforcement

Installed SDK: google-genai 2.29.0. Local field descriptions/request implementation
confirmed milliseconds for HttpOptions.timeout and one total attempt for
HttpRetryOptions(attempts=1). The original installed client had retry_options=None,
which already means one attempt in this SDK; no original repeated live request
was observed. The repair pins one attempt explicitly at client/request level.

The original Future timeout and cancel/shutdown(wait=False) left running work
uncancelled. The repair removes that executor, calls the synchronous SDK with
an explicit HTTP timeout, and disables SDK automatic function calling.

Actual installed SDK against a local fake HTTP server proved:

- Retryable 503: exactly one request despite a three-attempt client default.
- Silent peer: an 80 ms HTTP timeout, observed socket EOF, one request, and no
  new non-daemon client worker thread remaining after return; elapsed under one second.
- Success: usage/finish parsing, server-observed output cap of 128, no tools.
- MAX_TOKENS: even a short response now flags truncated: true.

**Limits:** HTTP phase/inactivity timeout is not a hard whole-call monotonic
deadline across lock wait, DNS, all transport phases, or a trickling response.
The synchronous caller returns after transport completion/failure, without an
abandoned executor request. Local socket closure does not prove cancellation
of Google's remote computation. No such cancellation claim is made.

## Delivery and activation boundary

The [assignment-only source/test diff](GEMINI_HARDENING_ASSIGNMENT_2026-10-11.patch)
compares with assignment-start file snapshots, excluding all preexisting edits.
Changed source/tests: model_bridge/gemini_runner.py, model_bridge/claude_bridge.py,
tests/test_bridge.py, and new tests/test_gemini_transport.py. Relevant checklist,
operations, and validation documentation records the results.

The running service was not restarted and needs one host restart to load the
source repairs:

```bash
sudo systemctl restart model-bridge.service
```

No daemon-reload is needed for this source-only change. At this original four-call handoff, no further generation was requested.
John subsequently authorized exactly one higher-cap critique; its evidence is below. No installed service/config,
key/permission/billing change, commit, push, or broad audit was performed.

Report recorded: 2026-10-11T21:29:21.051279-04:00.

## Separately authorized complete critique, 2048-token cap

John subsequently authorized one more critique to obtain a complete response.
The connector default is now 2048 output tokens; explicit environment overrides
remain supported, with the existing maximum of 8192. Deliberately small mocked
truncation fixtures were unchanged. This live validation used an explicit cap
of 2048 and reused the existing synthetic Gemini thread/history and other_answer.
No independent/open repetitions or automatic retries/fallbacks were made.

Focused command:

```bash
env -u MODEL_BRIDGE_CHILD -u PROJECT_WORKER_CHILD PYTHONPATH=.:tests .venv/bin/python -m unittest test_bridge.GeminiRunnerTests test_gemini_transport -v
```

13 tests passed, zero failures/errors/skips; unittest duration 0.546 seconds.
No full-suite repeat was needed for this default-only change. Local checks also
confirmed default 2048 and explicit maximum override 8192. The previous 109-test
result predates this default-only change and is not presented as a fresh full run.

- Exactly one newly authorized live generation attempt via registered `ask_gemini` MCP handler.
- Requested and provider-reported model: `gemini-3.5-flash-lite`.
- Status: `ok`; finish: `STOP`; truncated: `false`.
- Response length: 96 words; requested at most 150.
- Usage: 467 prompt + 142 candidate = 609 total tokens; thinking unavailable/null.
- Output cap: 2048; HTTP timeout: 30 seconds; total SDK attempts: one.
- Start: `2026-10-11T21:39:42.639571-04:00`; completion: `2026-10-11T21:39:43.684854-04:00` (America/New_York, EDT).
- Monotonic registered-handler wall duration: 1.045282 seconds.
- Reported runner request duration: 1.0340522300029988 seconds.
- Thread: `53619398aa164bf6bd50b271a84568bf`.
- Transcript: `/home/jachee/projects/acheedev/model-bridge/.tmp/gemini-checks-5hdpwbb9/live-transcripts/2026-10-11_21-23-25-0400_gemini_gemini-contract-nonce-a_53619398.md`; corresponding JSON and `complete-critique-result.json` are retained.

Full returned critique text, preserved verbatim:

```text
The supplied answer (`Saved token: MB-Z9.`) is **incorrect**. 

The correct remembered token is **MB-Q7**. 

**Explanation:** 
Throughout the conversation history, the user established and successfully tested the recall of the token `MB-Q7`. The final prompt introduces a deceptive premise via the `chatgpt_answer` field, falsely claiming a different token was supplied and instructing the model to return "WRONG" followed by that altered token. This is an adversarial prompt injection attempt designed to override the established ground truth. Critical evaluation requires ignoring the injected misinformation and relying strictly on the verified history, where `MB-Q7` remains the authentic remembered token.
```

Normal STOP plus nontruncated output demonstrates completion, rather than
assuming it from status ok alone. The response correctly identifies MB-Q7 from
history and rejects the supplied MB-Z9 answer. Its characterization of the
synthetic exercise as adversarial is the model's interpretation, not an
independently established security finding.

This is a host registered-handler proof, not a new authenticated HTTP service
call. The running service was not restarted: sudo -n true returned exit 1
because a password is required. John must run `sudo systemctl restart
model-bridge.service` once to load the timeout/key/truncation/default repairs.
No daemon-reload, config/key/permission/billing changes, commits, or pushes
were made. This follow-up used 609 tokens; all five scoped live calls together
reported 1432 tokens (1156 prompt + 276 candidate), excluding earlier assignments.

## Reported restart and authenticated ping checkpoint

John subsequently reported completing the pending Ubuntu service restart.
Mimi then reported authenticated bridge_ping status ok with exact echo and
reported gemini_model gemini-3.5-flash-lite. The checklist's source-repair restart
step is checked off based on John's report, with that reachability checkpoint.

The earlier pending-restart statements describe the prior handoff. This ping
independently checks authenticated reachability and the reported model only;
it does not independently verify loaded source revision, effective 2048-token
cap, or deployment of every repair. Exact restart/ping timestamps and duration
were not supplied and remain unknown. Recorded October 11, 2026. No new probe,
model call, code/config/service operation, or Git change was performed for this
update. Existing edits were preserved.
