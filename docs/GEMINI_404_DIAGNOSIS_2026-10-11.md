# Gemini MCP 404 diagnosis

Checked at 2026-10-11 20:29:00 EDT (-0400).

## Finding

No local connector endpoint-construction defect was found in the accessible
source or installed SDK.

- The bridge default model is `gemini-2.5-flash-lite`.
- The deployed service template does not set `GEMINI_MODEL`, so the default is
  used unless the live host process has an external environment override.
- The connector creates `google.genai.Client(api_key=...)` for the Gemini
  Developer API and calls `client.models.generate_content(...)`.
- Installed official SDK: `google-genai 2.29.0`.
- SDK Developer API defaults are base URL
  `https://generativelanguage.googleapis.com/` and API version `v1beta`.
- The SDK accepts bare Gemini model IDs, prefixes them as `models/<id>`, and
  posts to `models/<id>:generateContent`.

This makes the observed first-live-test `ClientError` HTTP 404 most consistent
with provider-side model availability/routing for the authenticated key and
requested model, not with the bridge inventing a malformed endpoint locally.

## Evidence limits

The sandbox could not resolve `ai.google.dev`, so current public Google docs
could not be fetched live here. The accessible official evidence was the
installed Google SDK package and metadata. No credential files, raw environment
dumps, live model generations, retries, service restarts, config edits, or Git
mutations were used.

## Focused validation

Command run without live provider calls:

```bash
.venv/bin/python -m unittest \
  tests.test_bridge.GeminiRunnerTests \
  tests.test_bridge.BridgeTests.test_gemini_modes_history_usage_finish_and_provider_isolation \
  tests.test_bridge.BridgeTests.test_gemini_independent_missing_credentials_and_failed_history \
  tests.test_bridge.BridgeTests.test_gemini_sdk_startup_error_does_not_break_existing_tools \
  tests.test_bridge.BridgeTests.test_mcp_registration
```

Result: 8 tests passed in 0.319s.

## Smallest safe host diagnostic

On the authenticated host only, without printing the key or making a generation
request, list Gemini Developer API models visible to the configured key and
check whether `models/gemini-2.5-flash-lite` is present and supports
`generateContent`.

Sanitized Python shape:

```python
from google import genai

client = genai.Client(api_key=read_key_without_printing_it())
for model in client.models.list():
    methods = getattr(model, "supported_actions", None) or getattr(model, "supported_generation_methods", None)
    print(model.name, methods)
```

Do not print the key, headers, full environment, or raw credential path contents.
If `gemini-2.5-flash-lite` is absent or lacks generation support, choose an
explicit supported free-tier model, for example the currently documented SDK
example alias `gemini-flash-latest`, only after confirming it appears in that
authenticated list and meets the cost policy. Do not silently change the bridge
default.

## Status

`docs/TASKS.md` item 5.4 remains pending until an actual successful client
response is observed through MCP.
