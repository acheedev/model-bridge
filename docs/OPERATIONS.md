# Model bridge

For navigation and the current layout, see the [repository README](../README.md).
Track remaining work in the [project checklist](TASKS.md). Run the commands in
this guide from the checkout root; Python entry points now use `-m model_bridge...`.

A loopback-only authenticated MCP server with `bridge_ping`, `ask_claude`,
`ask_codex`, and `save_synthesis`. It runs as an ordinary Python process; VS Code
is not required. The existing Claude tool uses Anthropic API credits. The Codex
tool uses the installed CLI and saved ChatGPT subscription login, without an
OpenAI API key or API-key billing. ChatGPT plan usage limits still apply.

Reusable byte-preserving file transfer and a separate authorized implementation
worker are now available. See [MCP_PROJECT_WORK.md](MCP_PROJECT_WORK.md) for the
seven new tools, exact schemas, limits, authorization, recovery behavior and
Windows-client proof steps. Consultation isolation remains unchanged.

## Project direction and roles

Model Bridge supports a human-led council workflow. John Achee sets direction
and execution authority; Mimi coordinates work, evaluates evidence, and presents
recommendations; Ezra is the v1 code author and can also participate as a
consultant; Claude and Gem are independent consultants. Consultation never
authorizes implementation by itself. Project jobs require explicit assignment
text, acceptance criteria, a known project ID, and authority flags.

The approved direction is to move from dependable consultations to a controlled
coding loop, durable background jobs, ChatGPT/iPhone access, Gemini integration,
and council coordination. Those roadmap items are not all current capabilities.
The current worker-transfer bootstrap was implemented before the planned
baseline-closeout merge; baseline documentation, service/checkout reconciliation,
and review/merge housekeeping remain pending. See [PROJECT_SPEC.md](PROJECT_SPEC.md)
for the reconciled specification, observed implementation status, and open
questions.

## Start with the currently installed CLI

From any WSL terminal, including one outside VS Code:

```bash
cd /home/jachee/projects/acheedev/model-bridge
CLAUDE_MODEL='claude-haiku-5-5' BRIDGE_MAX_TOKENS='4096' CODEX_TIMEOUT_SECONDS='120' \
CODEX_BIN='/home/jachee/.vscode-server/extensions/openai.chatgpt-26.1007.21434-linux-x64/bin/linux-x86_64/codex' \
  /home/jachee/projects/acheedev/model-bridge/.venv/bin/python \
  -m model_bridge.claude_bridge
```

The endpoint is `http://127.0.0.1:8081/mcp`. Clients must send the bearer token
stored in `~/.codex/model-bridge/bridge.token`. Do not print or commit that file.
The local MCP authentication helper is
`~/.codex/model-bridge/codex-http-headers.py`; it reads that token and emits the
bearer header for the client. Capture its output privately when verifying it.
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
`~/.codex/model-bridge/anthropic.key` remains optional at startup: when present,
Claude retains its existing API behavior; when absent, Codex and local tools can
still run, while `ask_claude` reports that it is not initialized. Python requires
3.10+ and the existing `mcp`, `anthropic`, and `uvicorn` dependencies.

## Consultations and transcripts

`ask_codex` supports two supplied-context tasks: `task="question"` (the default)
and `task="code_generation"`. Code generation returns the completed answer as
text; the bridge never executes that generated code or writes it to a project.
Supply source snippets and requirements in `context`. Both tasks use the same
empty temporary working directory under the project’s `.tmp/`, ignored user
config/rules, read-only sandbox, disabled tool integrations, and subscription
authentication. There is no project path argument. Inspecting or editing project
files requires the separate project-worker tools and is not enabled by choosing
code generation.

Example MCP arguments (illustrative; not a request made during validation):

```json
{
  "question": "Generate a Python function that validates these records.",
  "context": "Records contain a name string and a positive integer count.",
  "task": "code_generation",
  "model": "gpt-6.1-sol",
  "reasoning_effort": "high",
  "timeout_seconds": 900
}
```

`model`, `reasoning_effort`, and `timeout_seconds` are optional. Explicit model
selection must match an exact catalog slug. An explicit effort requires an
explicit model so its combination can be checked without relying on a default.
Unsupported models/efforts are rejected before `codex exec`; nothing is silently
substituted. Omitting both leaves selection to the CLI without claiming which
model or effort was used. Model-only selection leaves effort unspecified.

The installed CLI documents `codex debug models --bundled` as skipping refresh
and dumping its bundled catalog. The bridge runs that command in an isolated,
unauthenticated home under the same overall deadline for every explicit model
selection. It validates `slug` and `supported_reasoning_levels[].effort`, and
fails closed if the catalog is unavailable or malformed. It does not hard-code
model names or a universal effort enum. Inspect these capabilities offline with:

```bash
.venv/bin/python -m model_bridge.codex_capabilities
```

Verified with installed `codex-cli 0.162.0-alpha.17.2`:

| Bundled model slugs | medium | high | xhigh | ultra | Other advertised efforts |
| --- | --- | --- | --- | --- | --- |
| `gpt-6.1-sol`, `gpt-6-astra`, `gpt-6-sol`, `gpt-5.6-sol`, `gpt-5.6-terra` | yes | yes | yes | yes | low, max |
| `gpt-6-luna`, `gpt-5.6-luna` | yes | yes | yes | no | low, max |
| `gpt-5.5` | yes | yes | yes | no | low |
| `gpt-daybreak-blue-latest`, `gpt-daybreak-red-latest` (hidden) | yes | yes | yes | yes | low, max |
| `codex-auto-review` (hidden) | yes | yes | yes | no | low, max |

An isolated, unauthenticated app-server `model/list` probe agreed with these
combinations. These are installed CLI capabilities, not proof of account access
or backend acceptance; no inference was used to verify entitlement. OpenAI also
documents that model catalogs may be bundled and do not verify entitlement:
[official OpenAI documentation](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server).
The catalog describes `ultra` as reasoning with automatic task delegation. This
bridge continues to disable sub-agents and Code Mode execution; accepting the
advertised effort does not enable delegation, promise it will work with these
restrictions, or downgrade it. Recheck after CLI upgrades.

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
transcripts in `BRIDGE_DATA_DIR` (default `transcripts/` in the project root,
independent of the working directory). In this checkout that is
`/home/jachee/projects/acheedev/model-bridge/transcripts`. Set `BRIDGE_DATA_DIR`
only when intentionally choosing another data location. Transcript and auth-cache
overrides must resolve under `/home/jachee/projects` or `/home/jachee/.codex`;
paths outside those roots, including directory or file symlink escapes, are rejected.

Both consultation tools accept an optional `title` (at most 200 characters).
Use a short descriptive label, never credentials. Omitted or blank titles use
`Consultation`; titles are never derived from the question or context. Titles
are checked against known credentials before any consultation or persistence.
New transcript pairs use names such as
`2026-10-10_09-30-00-0400_codex_python-helper_ab12cd34.md` (and `.json`): the
thread's original start time in America/New_York, including its UTC offset,
provider, a sanitized ASCII title slug of at most 40 characters, and an
eight-character ID prefix. Conflicting database names or existing files extend
the ID prefix until unique; existing files are never overwritten by a new thread.
The full 32-character UUID remains the thread ID in SQLite, tool results and
transcripts. The original title, start time, and chosen filename are persisted;
follow-up titles are ignored, and follow-ups and synthesis saves reuse that path
even after restart.

`index.md` lists titles, providers, New York start times, full thread IDs, and
relative Markdown/JSON transcript links. It refreshes at startup and after each
export. Existing threads retain their UUID filenames; migration does not rename,
delete or rewrite their transcripts. Subsequent turns append to those same
transcripts as before. Legacy start times use the first recorded event; if none
exists, migration uses the existing transcript's modification time, or migration
time if neither a file nor an event exists, and preserves that fallback thereafter.
Legacy titles use `Consultation`, without extracting prompts into the index.

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
in a **separate bridge-owned cache**, defaulting to
`~/.codex/model-bridge/codex-auth-cache.json` (override with
`BRIDGE_CODEX_AUTH_CACHE`). The bridge never writes the source Codex `auth.json`;
it does not attempt a check-then-replace against that shared file. Cache updates
are atomic to avoid partial files, not to provide compare-and-swap against
another client's login. Run only one bridge process and reserve its cache for
that process. The cache must not point to the source authentication file.

Cached refreshes are reused only when the source login's fingerprint matches
their original seed. If another CLI changes the source login during a consultation,
that consultation may finish with the older login; the next consultation uses the
new source login. Other Codex clients do not share the bridge's cache and may need
to sign in again if refresh-token rotation invalidates their saved tokens. Do not
place arbitrary credentials in consultation text.

`requested_model` and `requested_reasoning_effort` are recorded in the request,
response, and tool result independently of reported metadata. The effective
`task` and `timeout_seconds` are also recorded. `model`, `usage`, and `stop_reason`
come only from JSONL events. If the CLI does
not emit a field, the bridge returns `null`; it does not infer a model identifier
or manufacture an `end_turn` reason. The final completed agent answer is returned,
while other events remain in the transcript. Nonzero exits, JSONL error events,
invalid output, missing completed answers, setup failures, and timeouts return
structured errors. No consultation is retried automatically.

Item-level error diagnostics are returned as redacted `warnings` when the CLI
still completes a successful answer. They remain in the saved event stream;
top-level error events, failed turns and nonzero exits still fail the consultation.

### Code Mode diagnostic and actual-model limits

The live confirmation stream included an item-level error: Code Mode was
unavailable because the host was disabled. The bridge explicitly sets
`features.code_mode_host=false`. The installed bundled catalog specifies
`tool_mode="code_mode_only"` for every listed model above except `gpt-5.5`;
model metadata can select this mode even when the generic `code_mode` feature
is off. The diagnostic identifies the conflicting host setting. It does not
identify the model that served that consultation. No feature settings were
changed to enable a host or project tools, and no host was installed. The
diagnostic may recur; text-only answers can still complete, as in the live test.

The installed exec help offers selection (`--model`) and JSONL (`--json`), but no
dedicated actual-model output option. The previous stream had no model field.
The bridge keeps `model=null` in that situation even with an explicit request.
For future richer reporting, the installed app-server schema has
`ThreadStartResponse.model` and `ThreadResumeResponse.model` for resolved session
selection, plus turn-scoped `model/rerouted` with `fromModel`, `toModel`, and
`reason`. These should be captured with provenance and routing changes rather
than treating a selection/default as a backend model snapshot. This bridge has
not switched its inference transport to app-server.
See [official OpenAI documentation](https://learn.chatgpt.com/docs/app-server).

`timeout_seconds` must be a finite numeric value greater than zero and at most
**1800 seconds**; booleans and strings are rejected. Defaults are **120 seconds
for questions** and **900 seconds for code generation**. For compatibility,
`CODEX_TIMEOUT_SECONDS` can override the question default, subject to the same
bound; it does not override the code generation default or an explicit per-call
timeout. Each call has **one overall monotonic consultation deadline**, including
the bridge lock wait, setup, optional capability discovery, both local
preflights, and `codex exec`. Each subprocess receives only the remaining budget;
an expired deadline prevents the next stage from starting. On timeout the bridge
sends SIGTERM and then SIGKILL to the child process group. Cleanup has a separate
budget of up to 4 seconds (2 seconds to terminate and 2 seconds to reap). Cleanup
that exceeds its budget returns a structured `cleanup_timeout` failure.

The MCP client must wait long enough to receive the structured result. Set
`tool_timeout_sec` under `[mcp_servers.model-bridge]` in `~/.codex/config.toml`
to **1811 seconds**, strictly exceeding the maximum server deadline (1800),
cleanup budget (4), and response/transcript margin (6). Other MCP clients need
the same allowance. The larger client timeout does **not** extend a shorter
server deadline: a 120-second question still expires after 120 seconds even
though the client is prepared to wait longer. Align the local client with:

```bash
.venv/bin/python -m model_bridge.configure_mcp_timeout
```

This local helper updates only model-bridge's tool timeout and prints only the
resulting value. Reload the MCP client after changing its configuration, and
restart the bridge to load the updated tool signature and code (and any startup
environment changes). This implementation does not restart the running bridge.
`BRIDGE_MAX_TOKENS` and `BRIDGE_MAX_CALLS` apply only to Claude. This CLI exposes no
Codex output-token cap in `exec --help`, so neither variable is used as one.

## Project-worker scope

Project inspection and editing use separate worker-transfer tools, not an extra
privilege switch on `ask_codex`. The current bootstrap accepts only
`project_id: "model-bridge"` and exactly
`{"edit":true,"test":true,"commit":false,"push":false}`. It can edit this
checkout and run relevant validation under a sandboxed worker, but it cannot
commit, push, restart services, access job state, or call the bridge from inside
the child process. It is serialized, not a general multi-project scheduler.

Inbound transfers provide byte-preserving reference files. The supervisor mounts
verified job inputs read-only under `.worker-inputs/`, records job state under a
private Git-ignored store, and publishes sanitized outbound artifacts for MCP
retrieval. `MCP_PROJECT_WORK.md` is the source for exact schemas, storage limits,
credential exclusions, cancellation behavior, and known sandbox limits.

The earlier design requirement still applies to future broader project access:
authorize narrow roots, exclude credentials, record provenance and hashes, detect
concurrent edits, return reviewable diffs and validation evidence, and keep patch
application, test execution, commits, pushes, installations, and service restarts
behind explicit authority. Prompt instructions alone are not a filesystem
security boundary.

## Validation

Verified locally against `codex-cli 0.162.0-alpha.17.2`:

- Exact exec flags accepted by `exec --help`, with no model request.
- Offline bundled catalog discovery checked medium, high, xhigh and ultra;
  selections are passed unchanged as `--model` and `model_reasoning_effort`.
- Local unauthenticated `config/read` probes accepted medium, high, xhigh and
  ultra unchanged with `model="gpt-6.1-sol"` and all isolation switches intact.
  The model CLI flag is scoped to `exec` in the implementation; these config
  probes verify configuration acceptance, not a model response or backend use.
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
.venv/bin/python -m compileall -q model_bridge tests
git diff --check
```

Recheck CLI compatibility after upgrading or replacing the executable. Unsupported
flags/configuration fail rather than removing sandbox or authentication guards.

Consultation and capability-check temporary directories live in `.tmp/` in the project root, are private, and are removed after each call. The child CLI
also receives `TMPDIR` inside its private directory. Tests explicitly create
their temporary fixtures under the same project `.tmp/`, independent of the
caller’s `TMPDIR`. `.tmp/` is Git-ignored.
