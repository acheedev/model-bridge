"""Subscription-only, isolated Codex CLI consultations (no OpenAI SDK)."""
import json
import math
import os
import re
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path

CHILD_MARKER = 'MODEL_BRIDGE_CHILD'
DISABLED_FEATURES = (
    'plugins', 'remote_plugin', 'apps', 'hooks', 'shell_tool', 'unified_exec',
    'multi_agent', 'skill_mcp_dependency_install', 'code_mode_host', 'daemon_auto_start',
)
CONFIG_OVERRIDES = (
    'forced_login_method="chatgpt"', 'cli_auth_credentials_store="file"',
    'model_provider="openai"', 'mcp_servers={}', 'approval_policy="never"',
    'sandbox_mode="read-only"',
) + tuple('features.' + feature + '=false' for feature in DISABLED_FEATURES)


class CodexFailure(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.error = {'code': code, 'message': message}


def executable():
    configured = os.environ.get('CODEX_BIN')
    found = shutil.which(configured if configured is not None else 'codex')
    if not found:
        raise CodexFailure('cli_unavailable', 'Codex CLI unavailable. Set CODEX_BIN to an executable or put codex on PATH.')
    return str(Path(found).resolve())


def timeout_seconds():
    try:
        value = float(os.environ.get('CODEX_TIMEOUT_SECONDS', '120'))
        if not math.isfinite(value) or value <= 0:
            raise ValueError()
        return value
    except ValueError:
        raise CodexFailure('invalid_timeout', 'CODEX_TIMEOUT_SECONDS must be a finite positive number.') from None


def subscription_auth():
    home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))).expanduser()
    try:
        auth = json.loads((home / 'auth.json').read_text(encoding='utf-8'))
        tokens = auth.get('tokens')
        if auth.get('auth_mode') not in (None, 'chatgpt') or not isinstance(tokens, dict) or not tokens.get('access_token'):
            raise ValueError()
        # Never copy an API credential, even if the original file contains one.
        return {k: auth[k] for k in ('auth_mode', 'tokens', 'last_refresh') if k in auth}
    except (OSError, ValueError, AttributeError):
        raise CodexFailure('subscription_auth_unavailable',
                           'Saved ChatGPT file authentication unavailable. Run codex login with ChatGPT; API-key authentication is not supported.') from None


def persist_auth_refresh(home, original):
    """Keep CLI token refreshes without replacing a concurrently changed login."""
    temporary = None
    try:
        refreshed = json.loads((home / 'auth.json').read_text(encoding='utf-8'))
        tokens = refreshed.get('tokens')
        if not isinstance(tokens, dict) or not tokens.get('access_token'):
            return original
        if tokens == original.get('tokens') and refreshed.get('last_refresh') == original.get('last_refresh'):
            return refreshed
        source = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))).expanduser() / 'auth.json'
        current = json.loads(source.read_text(encoding='utf-8'))
        if {k: current[k] for k in ('auth_mode', 'tokens', 'last_refresh') if k in current} != original:
            return refreshed  # Another CLI changed the login; never overwrite it.
        current['tokens'] = tokens
        if 'last_refresh' in refreshed:
            current['last_refresh'] = refreshed['last_refresh']
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', prefix='.bridge-auth-', dir=source.parent, delete=False) as stream:
            temporary = Path(stream.name)  # NamedTemporaryFile uses mode 0600.
            json.dump(current, stream)
        os.replace(temporary, source)
        return refreshed
    except (OSError, ValueError, AttributeError):
        raise CodexFailure('auth_refresh_persist_failed', 'Unable to preserve refreshed ChatGPT authentication. Run codex login with ChatGPT before another consultation.') from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def secret_values(auth):
    values = [v for k, v in auth.get('tokens', {}).items() if k.endswith('_token') and isinstance(v, str)]
    values += [v for k, v in os.environ.items() if re.search(r'(?:^|_)(?:KEY|TOKEN|SECRET|PASSWORD)$', k.upper()) and v]
    return values


def redact(value, secrets):
    if isinstance(value, dict):
        return {k: ('[REDACTED]' if re.search(r'(?:api[_-]?key|access_token|refresh_token|id_token|authorization|password|secret)', k, re.I)
                    else redact(v, secrets)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in sorted(secrets, key=len, reverse=True):
            if secret:
                value = value.replace(secret, '[REDACTED]')
        value = re.sub(r'(?i)Bearer\s+[^\s"\']+', 'Bearer [REDACTED]', value)
        return re.sub(r'\bsk-[A-Za-z0-9_-]+', '[REDACTED]', value)
    return value


def child_environment(home):
    # Allowlist prevents OPENAI_API_KEY, CODEX_API_KEY, CODEX_ACCESS_TOKEN,
    # provider/base URL overrides, VS Code state, and bridge credentials leaking in.
    env = {key: os.environ[key] for key in ('HOME', 'PATH', 'LANG', 'LC_ALL', 'TZ', 'SSL_CERT_FILE', 'SSL_CERT_DIR') if key in os.environ}
    env.update(CODEX_HOME=str(home), MODEL_BRIDGE_CHILD='1')
    return env


def prompt_is_safe(prompt, extra_secrets=()):
    try:
        auth = subscription_auth()
    except CodexFailure:
        auth = {}
    return redact(prompt, secret_values(auth) + list(extra_secrets)) == prompt


def config_arguments():
    return [arg for setting in CONFIG_OVERRIDES for arg in ('-c', setting)]


def run_process(argv, *, env, cwd, timeout, prompt=None):
    """Start a private process group; reap it and its descendants on timeout."""
    try:
        child = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, encoding='utf-8',
                                 errors='replace', cwd=cwd, env=env, start_new_session=True,
                                 shell=False)
    except OSError:
        raise CodexFailure('process_start_failed', 'Unable to start Codex CLI.') from None
    try:
        stdout, stderr = child.communicate(input=prompt, timeout=timeout)
        return child.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(child.pid, sig)
            except ProcessLookupError:
                pass
            if sig == signal.SIGTERM:
                try:
                    child.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
        child.communicate(timeout=2)
        raise CodexFailure('timeout', 'Codex CLI timed out; its process group was terminated. No automatic retry.') from None


def parse_events(stdout, returncode, secrets):
    events, answers, final_answers, usage, model, stop_reason = [], [], [], None, None, None
    completed, failure = False, None
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if not isinstance(entry, dict) or not isinstance(entry.get('type'), str):
                raise ValueError()
        except ValueError:
            return {'status': 'error', 'error': {'code': 'invalid_jsonl', 'message': 'Codex emitted invalid JSONL.'}, 'events': events}
        entry = redact(entry, secrets)
        events.append(entry)
        kind = entry['type']
        if kind == 'item.completed':
            item = entry.get('item') or {}
            if not isinstance(item, dict):
                return {'status': 'error', 'error': {'code': 'invalid_jsonl', 'message': 'Codex emitted an invalid item.'}, 'events': events}
            if item.get('type') == 'agent_message' and isinstance(item.get('text'), str):
                if item.get('phase') == 'final_answer':
                    final_answers.append(item['text'])
                elif item.get('phase') is None:
                    answers.append(item['text'])
        if kind == 'turn.completed':
            completed = True
            usage = entry.get('usage')
        if entry.get('model') is not None:
            model = entry['model']
        if entry.get('stop_reason') is not None:
            stop_reason = entry['stop_reason']
        if kind in ('error', 'turn.failed'):
            failure = entry
    answer = (final_answers or answers or [None])[-1]
    result = {'status': 'ok', 'text': answer, 'model': model,
              'usage': usage, 'stop_reason': stop_reason, 'events': events, 'exit_code': returncode}
    if returncode != 0 or failure or not completed or answer is None:
        result.update(status='error', error={'code': 'cli_failed' if returncode or failure else 'incomplete_response',
                      'message': 'Codex consultation failed.' if returncode or failure else 'Codex did not emit a completed answer.',
                      'event': failure})
    return result


def consult(prompt, extra_secrets=()):
    if os.environ.get(CHILD_MARKER):
        return {'status': 'error', 'error': {'code': 'recursive_call', 'message': 'Bridge calls are disabled in Codex child runs.'}}
    try:
        binary, timeout, auth = executable(), timeout_seconds(), subscription_auth()
        secrets = secret_values(auth) + list(extra_secrets)
        if any(secret and secret in prompt for secret in secrets):
            raise CodexFailure('credential_in_prompt', 'Prompt contains a credential; remove it before consulting Codex.')
        with tempfile.TemporaryDirectory(prefix='model-bridge-codex-') as root:
            home, work = Path(root) / 'home', Path(root) / 'work'
            home.mkdir(mode=0o700)
            work.mkdir(mode=0o700)
            auth_path = home / 'auth.json'
            auth_path.touch(mode=0o600)
            auth_path.write_text(json.dumps(auth), encoding='utf-8')
            try:
                env = child_environment(home)
                # Local preflights only: verify subscription login and reject any managed
                # MCP configuration that survived home isolation. Plugins/apps are disabled.
                code, out, err = run_process([binary, *config_arguments(), 'login', 'status'], env=env, cwd=work, timeout=timeout)
                if code or 'Logged in using ChatGPT' not in out + err:
                    raise CodexFailure('subscription_auth_unavailable', 'Codex login status did not confirm ChatGPT authentication. Run codex login with ChatGPT.')
                code, out, _ = run_process([binary, *config_arguments(), 'mcp', 'list', '--json'], env=env, cwd=work, timeout=timeout)
                try:
                    servers = json.loads(out)
                    if code or servers != []:
                        raise ValueError()
                except ValueError:
                    raise CodexFailure('mcp_isolation_failed', 'Cannot confirm an empty MCP server configuration; child run blocked.') from None
                argv = [binary, '--no-daemon', *config_arguments(), 'exec', '--strict-config',
                        '--ignore-user-config', '--ignore-rules', '--sandbox', 'read-only',
                        '--ephemeral', '--skip-git-repo-check', '--json', '--color', 'never', '-']
                code, out, _ = run_process(argv, env=env, cwd=work, timeout=timeout, prompt=prompt)
                # Do not retain stderr: it is unstructured and can contain sensitive data.
                return parse_events(out, code, secrets + secret_values(json.loads(auth_path.read_text(encoding='utf-8'))))
            finally:
                persist_auth_refresh(home, auth)
    except CodexFailure as exc:
        return {'status': 'error', 'error': exc.error}
    except (OSError, ValueError):
        return {'status': 'error', 'error': {'code': 'local_setup_failed', 'message': 'Unable to prepare isolated Codex consultation.'}}
