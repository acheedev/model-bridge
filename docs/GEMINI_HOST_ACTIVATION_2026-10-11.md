# Gemini host test and activation

Target: `/home/jachee/projects/acheedev/model-bridge`, Ubuntu WSL.

The protected host key was loaded through the existing `GEMINI_API_KEY_FILE` /
`~/.codex/model-bridge/gemini.key` convention with `approved_path` validation.
No key was copied to Windows or printed. The bridge startup loader was not
called, avoiding transcript/runtime startup side effects.

## Single controlled request

Installed `google-genai` version: 2.29.0. Installed SDK field descriptions
confirmed that `HttpOptions.timeout` uses milliseconds and
`HttpRetryOptions.attempts=1` means one total attempt with no retries.

- Requested and provider-reported model: `gemini-3.5-flash-lite`.
- Prompt: `Reply exactly: Gemini bridge connection confirmed.`
- Response: `Gemini bridge connection confirmed.`
- Finish status: `STOP`; exact text check passed.
- HTTP timeout: 30,000 ms; output cap: 128 tokens; attempts: 1.
- Usage: 9 prompt tokens, 6 candidate tokens, 15 total tokens.
- Start: October 11, 2026, 20:48:55.417922 America/New_York (EDT, UTC-04:00).
- Completion: October 11, 2026, 20:48:56.038932 America/New_York.
- Elapsed: 0.621 seconds, measured with a monotonic clock.

No fallback, second generation request, or 2.5 generation request was made.
This proves one successful host request. It does not prove ongoing free-tier
quota eligibility, final MCP client access, or the service's effective model.

## Prepared activation: historical host handoff

Prepared `deploy/model-bridge.service.d/20-gemini-model.conf`:

```ini
[Service]
Environment=GEMINI_MODEL=gemini-3.5-flash-lite
```

The installed base unit already starts `python -m model_bridge.claude_bridge`.
Its existing authentication, other environment settings, and `UMask=0077` are
preserved by using a model-only drop-in. No installed unit/configuration was
changed and no restart was attempted: `sudo -n true` reported
`sudo: a password is required`. Root switching or another bypass was not used.

The following activation commands were supplied at the earlier host handoff.
They are retained as historical evidence, not a request to repeat a restart:

```bash
cd /home/jachee/projects/acheedev/model-bridge
sudo install -D -m 0644 deploy/model-bridge.service.d/20-gemini-model.conf /etc/systemd/system/model-bridge.service.d/20-gemini-model.conf &&
sudo systemctl daemon-reload &&
sudo systemctl restart model-bridge.service &&
systemctl is-active model-bridge.service
```

These commands install only a non-secret model setting, then restart once.
If installation, reload, or restart fails, the command chain stops. At handoff,
task 5.4 remained unchecked pending Mimi's proof. The subsequent result is below.

Preexisting working-tree edits were preserved. No code/security changes,
billing changes, commits, or pushes were made. The diagnostic did not perform
activation. Actual installation/restart timing remains unknown to this record.


## Subsequent authenticated MCP client proof

Mimi independently invoked authenticated `ask_gemini` in `independent` mode and
reported the following evidence. Ezra recorded the supplied result without a
new model request, service inspection, or independent reproduction.

- Status: `ok`.
- Exact response text: `Gemini bridge connection confirmed.`
- Reported model: `gemini-3.5-flash-lite`.
- Finish: `STOP`; `truncated: false`.
- Usage: 121 prompt tokens + 6 candidate tokens = 127 total tokens.
- Thinking usage: unavailable/null; not inferred to be zero.
- Reported elapsed seconds: `0.5675054520033882`.
- Thread: `86b6f737a8a14a44b875e6eff1536b54`.
- Transcript: `/home/jachee/projects/acheedev/model-bridge/transcripts/2026-10-11_20-51-56-0400_gemini_gemini-activated-mcp-connection-proof_86b6f737.md`.
- Timestamp: October 11, 2026, 20:51:56 America/New_York (EDT, UTC-04:00),
  derived from the transcript filename. Exact call start/end were not
  independently clocked; the elapsed-time measurement method was not supplied.

Task 5.4 is complete for initial authenticated independent-mode connectivity
and preservation of the supplied transcript/usage reference. This does not
claim live critique/follow-up validation, full host verification, confirmed
installed configuration, or ongoing free-tier quota eligibility. No additional
model calls, code/configuration/service changes, commits, pushes, or broad
audits were performed for this documentation update.
