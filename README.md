# Model bridge

A loopback-only authenticated MCP server with `bridge_ping`, `ask_claude`,
`ask_codex`, and `save_synthesis`. It runs as an ordinary Python process; VS Code
is not required. The existing Claude tool uses Anthropic API credits. The Codex
tool uses the installed CLI and saved ChatGPT subscription login, without an
OpenAI API key or API-key billing. ChatGPT plan usage limits still apply.

## Start with the currently installed CLI

From any WSL terminal, including one outside VS Code:

```bash
CODEX_BIN='/home/jachee/.vscode-server/extensions/openai.chatgpt-26.1007.21434-linux-x64/bin/linux-x86_64/codex' \
  /home/jachee/projects/acheedev/model-bridge/.venv/bin/python \
  /home/jachee/projects/acheedev/model-bridge/claude_bridge.py
```

The endpoint is `http://127.0.0.1:8081/mcp`. Clients must send the bearer token
stored in `~/.config/model-bridge/bridge.token`. Do not print or commit that file.
Run only one bridge process at a time. Stop the existing bridge before starting
this command; this change does not restart the running server.

The executable above is bundled with the extension but does not need the editor
running. Extension removal or upgrades can change its path. `CODEX_BIN` can point
to any compatible standalone Codex executable; when unset, the bridge uses
`shutil.which("codex")`. An invalid configured path fails without falling back to
another executable.

## Standalone CLI setup (instructions only)

For a durable installation independent of extension files, install the official
standalone Codex CLI in WSL using the instructions in the
[official OpenAI documentation](https://developers.openai.com/codex/cli).
For example, after installing Node.js/npm separately:

```bash
npm install -g @openai/codex
command -v codex
codex --version
codex login
codex login status
```

Choose **Sign in with ChatGPT**, not API-key authentication. Set `CODEX_BIN` to the
standalone executable reported by `command -v codex`, or omit it if the bridge
process has that executable on its PATH. None of these installation or login
commands were executed as part of this implementation.

The bridge currently supports saved **file** authentication at
`${CODEX_HOME:-$HOME/.codex}/auth.json`. Keyring-only and external-token login
are rejected clearly; they do not fall back to API keys. No OpenAI key is needed.
`~/.config/model-bridge/anthropic.key` remains optional at startup: when present,
Claude retains its existing API behavior; when absent, Codex and local tools can
still run, while `ask_claude` reports that it is not initialized. Python requires
3.10+ and the existing `mcp`, `anthropic`, and `uvicorn` dependencies.

## Consultations and transcripts

- `independent`: supply `question` and optional `context`, without `thread_id` or
  `other_answer`.
- `critique`: supply the returned **Codex** `thread_id`, a new `question`, and
  `other_answer`.
- `open`: supply the returned **Codex** `thread_id` and a follow-up `question`.
- `save_synthesis`: accepts either provider's thread ID and records the final
  synthesis locally without a consultation.

Every consultation starts a new ephemeral CLI session. Bridge-owned UUIDs and
saved history implement continuation; CLI thread IDs are never reused. SQLite
threads are tagged by provider, and existing untagged threads migrate to Claude.
A thread cannot cross providers. Failed turns are recorded but do not change
successful conversation history. Requests are exported before child execution;
responses, JSONL events, errors, and synthesis use the existing JSON/Markdown
transcripts in `BRIDGE_DATA_DIR` (default `~/model-bridge/transcripts`).

The child receives its prompt through stdin using a subprocess argument list and
`shell=False` (no command interpolation). Each request uses a private temporary
Codex home containing only subscription authentication and a separate empty
working directory. User configuration and rules are ignored; the shared daemon
is disabled. Read-only sandboxing is always enabled, and approvals never grant
additional access. Config overrides disable direct MCP configuration, plugins
(including remote plugins), apps, hooks, shell tools, sub-agents, and automatic
skill MCP installation. An offline MCP-list preflight blocks execution if any
configured server remains. A child marker also rejects recursive bridge tool
calls and bridge startup. Authentication preflights must confirm ChatGPT login.

The environment is allowlisted; API keys, access-token overrides, provider URLs,
VS Code state, and bridge credentials are not inherited. Known credentials are
rejected before request logging and redacted from returned events. Raw stderr is
never returned or persisted. Temporary credential copies are private and removed
on completion. CLI token refreshes are saved atomically with private file permissions
when the source login has not changed; a concurrent login is never replaced. Do not place arbitrary credentials in consultation text.

`model`, `usage`, and `stop_reason` come only from JSONL events. If the CLI does
not emit a field, the bridge returns `null`; it does not infer a model identifier
or manufacture an `end_turn` reason. The final completed agent answer is returned,
while other events remain in the transcript. Nonzero exits, JSONL error events,
invalid output, missing completed answers, setup failures, and timeouts return
structured errors. No consultation is retried automatically.

`CODEX_TIMEOUT_SECONDS` defaults to `120` and limits each child process, including
local preflights. On timeout the bridge sends SIGTERM and then SIGKILL to the
child process group, reaps the process, and returns a timeout failure.
`BRIDGE_MAX_TOKENS` and `BRIDGE_MAX_CALLS` apply only to Claude. This CLI exposes no
Codex output-token cap in `exec --help`, so neither variable is used as one.

## Validation

Verified locally against `codex-cli 0.162.0-alpha.17.2`:

- Exact exec flags accepted by `exec --help`, with no model request.
- An isolated local `app-server` `config/read` probe with `--strict-config`
  confirmed `forced_login_method="chatgpt"`, file credentials, the OpenAI provider,
  an empty MCP server map, read-only sandboxing, approval policy `never`, and all
  specified feature switches disabled. The probe had no authentication file and
  made no inference request.
- Mocked subprocess tests cover success, errors, auth/environment isolation,
  recursion, timeout process groups, transcripts, provider separation, legacy
  migration, and working Claude behavior.

Run the checks without live model requests:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q claude_bridge.py codex_runner.py bridge_ping.py tests
git diff --check
```

Recheck CLI compatibility after upgrading or replacing the executable. Unsupported
flags/configuration fail rather than removing sandbox or authentication guards.
