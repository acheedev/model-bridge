# Gemini connector report

Sanitized outbound report for the Gemini connector implementation stage.

## Result

- Implemented `ask_gemini` beside `ask_claude` and `ask_codex`.
- Authentication decision completed: official `google-genai` SDK, Gemini
  Developer API key from the protected bridge keystore, no billing enablement.
- Default Gemini model: configurable `gemini-2.5-flash-lite`; no fallback model
  is selected by the bridge.
- Live Gemini proof was not attempted in this stage.

## Behavior

- Supports `independent`, `critique`, and `open` modes with provider-bound
  Gemini thread IDs.
- Independent mode rejects `thread_id` and `other_answer`, so another model's
  answer is not included.
- Stores request/error/response events in the existing transcript database and
  export files.
- Returns provider, model, text, actual elapsed call duration, available usage
  metadata, finish reason, truncation status, max output token cap, thread ID,
  and transcript path.
- Handles missing credentials, missing SDK, authentication, quota/rate limit,
  timeout, network/provider, and blocked-or-empty responses with sanitized
  structured errors.
- Does not change project-worker routing and grants Gemini no project access,
  host tools, file execution, or worker credentials.

## Activation

The current project environment does not have `google-genai` installed. Minimal
host step after review:

```bash
cd /home/jachee/projects/acheedev/model-bridge
.venv/bin/python -m pip install -e .
```

Then restart/reload the bridge under separate service authority so the running
MCP server loads the new dependency and tool registration. The protected key file
expected by default is `~/.codex/model-bridge/gemini.key`; alternatively set
`GEMINI_API_KEY_FILE` to another approved protected path. Do not print the key.

Optional environment controls:

- `GEMINI_MODEL`, default `gemini-2.5-flash-lite`
- `GEMINI_TIMEOUT_SECONDS`, default `60`, max `1800`
- `GEMINI_MAX_OUTPUT_TOKENS`, default `1024`, max `8192`

## Validation

- Passed: `.venv/bin/python -m unittest tests.test_bridge.BridgeTests tests.test_bridge.GeminiRunnerTests -v`
- Passed: `env -u MODEL_BRIDGE_CHILD -u PROJECT_WORKER_CHILD .venv/bin/python -m unittest tests.test_transfers_jobs.TransferTests tests.test_transfers_jobs.RegistrationTests -v`
- Passed: `.venv/bin/python -m compileall -q model_bridge tests`
- Passed: `git diff --check`
- Full suite note: a plain full-suite run inherits this worker's
  `MODEL_BRIDGE_CHILD=1` and `PROJECT_WORKER_CHILD=1` markers, causing expected
  project-worker recursion refusal. With those markers unset, remaining
  project-worker subprocess tests still fail in this worker sandbox with
  `missing_or_invalid_worker_result`/deadline-related outcomes; these are
  outside the Gemini connector path and were not debugged further per scope.

## Timing

- Start: 2026-10-11 19:51:57 EDT
- End: 2026-10-11 19:54:31 EDT
- Elapsed: 2 minutes 34 seconds
