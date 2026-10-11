"""Subscription-only, isolated Codex CLI consultations (no OpenAI SDK)."""
import json
import hashlib
import math
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from .bridge_paths import approved_path

CHILD_MARKER = 'MODEL_BRIDGE_CHILD'
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TERMINATE_GRACE_SECONDS = 2
REAP_GRACE_SECONDS = 2
CLEANUP_SECONDS = TERMINATE_GRACE_SECONDS + REAP_GRACE_SECONDS
MCP_RESPONSE_MARGIN_SECONDS = 6
MAX_TIMEOUT_SECONDS = 1800
TASK_DEFAULTS = {'question': 120, 'code_generation': 900}
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


def timeout_seconds(value=None, task='question'):
    if not isinstance(task, str) or task not in TASK_DEFAULTS:
        raise CodexFailure('invalid_task', 'task must be question or code_generation; project access is not supported.')
    if value is None:
        value = TASK_DEFAULTS[task]
        if task == 'question' and 'CODEX_TIMEOUT_SECONDS' in os.environ:
            try:
                value = float(os.environ['CODEX_TIMEOUT_SECONDS'])
            except ValueError:
                raise CodexFailure('invalid_timeout', 'CODEX_TIMEOUT_SECONDS must be a finite positive number at most 1800.') from None
    try:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError()
        if not math.isfinite(value) or not 0 < value <= MAX_TIMEOUT_SECONDS:
            raise ValueError()
        return value
    except (ValueError, OverflowError):
        raise CodexFailure('invalid_timeout', 'timeout_seconds must be a finite positive number at most 1800.') from None


def consultation_deadline(value=None, task='question'):
    return time.monotonic() + timeout_seconds(value, task)


def remaining_seconds(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise CodexFailure('timeout', 'Overall Codex consultation deadline exceeded. No automatic retry.')
    return remaining


def mcp_timeout_seconds():
    # Strictly exceed the largest permitted deadline, cleanup and response margin.
    return MAX_TIMEOUT_SECONDS + CLEANUP_SECONDS + MCP_RESPONSE_MARGIN_SECONDS + 1


def validate_options(task='question', model=None, reasoning_effort=None, timeout=None):
    seconds = timeout_seconds(timeout, task)
    for value, label in ((model, 'model'), (reasoning_effort, 'reasoning_effort')):
        if value is not None and (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', value)):
            raise CodexFailure('invalid_selection', label + ' must be a nonempty model catalog identifier.')
    if reasoning_effort is not None and model is None:
        raise CodexFailure('model_required', 'Specify model when setting reasoning_effort so the combination can be verified.')
    return {'task': task, 'requested_model': model,
            'requested_reasoning_effort': reasoning_effort, 'timeout_seconds': seconds}


def temporary_root():
    root = PROJECT_ROOT / '.tmp'
    if not root.resolve().is_relative_to(PROJECT_ROOT):
        raise CodexFailure('invalid_temp_directory', 'Project tmp directory must stay inside the project.')
    root.mkdir(mode=0o700, exist_ok=True)
    root.chmod(0o700)
    return root


def discover_capabilities(*, deadline, binary=None):
    """Read this executable's bundled catalog offline; never use auth or inference."""
    binary = binary or executable()
    with tempfile.TemporaryDirectory(prefix='model-bridge-capabilities-', dir=temporary_root()) as root:
        home, work = Path(root) / 'home', Path(root) / 'work'
        home.mkdir(mode=0o700)
        work.mkdir(mode=0o700)
        code, out, _ = run_process(
            [binary, '--no-daemon', *config_arguments(), 'debug', 'models', '--bundled'],
            env=child_environment(home), cwd=work, deadline=deadline)
    try:
        if code:
            raise ValueError()
        models = json.loads(out)['models']
        if not isinstance(models, list) or not models:
            raise ValueError()
        catalog = {}
        for entry in models:
            slug = entry['slug']
            efforts = [level['effort'] for level in entry['supported_reasoning_levels']]
            if (not isinstance(slug, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', slug)
                    or slug in catalog or not efforts
                    or any(not isinstance(effort, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', effort) for effort in efforts)):
                raise ValueError()
            catalog[slug] = {'reasoning_efforts': efforts, 'tool_mode': entry.get('tool_mode')}
        return catalog
    except (ValueError, KeyError, TypeError):
        raise CodexFailure('capabilities_unavailable', 'Installed CLI did not supply a valid bundled model catalog; no substitution or model request was made.') from None


def validate_selection(catalog, model, reasoning_effort):
    if model not in catalog:
        raise CodexFailure('unsupported_model', 'Requested model is absent from the installed CLI catalog; no substitution was made.')
    if reasoning_effort is not None and reasoning_effort not in catalog[model]['reasoning_efforts']:
        raise CodexFailure('unsupported_reasoning_effort', 'Requested effort is not supported for this model in the installed CLI catalog; no substitution was made.')


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


def auth_fingerprint(auth):
    return hashlib.sha256(json.dumps(auth, sort_keys=True).encode('utf-8')).hexdigest()


def auth_cache_path():
    try:
        target = approved_path(os.environ.get('BRIDGE_CODEX_AUTH_CACHE', str(
            Path.home() / '.codex/model-bridge/codex-auth-cache.json')))
    except (OSError, ValueError, RuntimeError):
        raise CodexFailure('invalid_auth_cache', 'Auth cache must resolve inside an approved filesystem root.') from None
    source = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))).expanduser() / 'auth.json'
    if target.resolve() == source.resolve():
        raise CodexFailure('invalid_auth_cache', 'BRIDGE_CODEX_AUTH_CACHE must be separate from the saved Codex auth.json.')
    return target


def cached_subscription_auth(original):
    """Reuse our refresh only while the saved source login matches its seed."""
    try:
        cache = json.loads(auth_cache_path().read_text(encoding='utf-8'))
        auth = cache['auth']
        if (cache['source_fingerprint'] == auth_fingerprint(original)
                and auth.get('auth_mode') in (None, 'chatgpt')
                and isinstance(auth.get('tokens'), dict) and auth['tokens'].get('access_token')):
            return {k: auth[k] for k in ('auth_mode', 'tokens', 'last_refresh') if k in auth}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return original


def persist_auth_refresh(home, original):
    """Save only to our private cache. Never replace the source login file.

    A check followed by os.replace cannot implement compare-and-swap against
    another CLI's login. Avoid that race by never writing the shared auth.json.
    One bridge process owns this cache, as required for the transcript database.
    """
    temporary = None
    try:
        refreshed = json.loads((home / 'auth.json').read_text(encoding='utf-8'))
        tokens = refreshed.get('tokens')
        if not isinstance(tokens, dict) or not tokens.get('access_token'):
            return original
        if tokens == original.get('tokens') and refreshed.get('last_refresh') == original.get('last_refresh'):
            return refreshed
        target = auth_cache_path()
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.parent.chmod(0o700)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', prefix='.bridge-auth-', dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)  # NamedTemporaryFile uses mode 0600.
            json.dump({'source_fingerprint': auth_fingerprint(original), 'auth':
                       {k: refreshed[k] for k in ('auth_mode', 'tokens', 'last_refresh') if k in refreshed}}, stream)
        os.replace(temporary, target)
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
    env.update(CODEX_HOME=str(home), MODEL_BRIDGE_CHILD='1', TMPDIR=str(home.parent))
    return env


def prompt_is_safe(prompt, extra_secrets=()):
    try:
        auth = subscription_auth()
    except CodexFailure:
        auth = {}
    return redact(prompt, secret_values(auth) + secret_values(cached_subscription_auth(auth)) + list(extra_secrets)) == prompt


def config_arguments():
    return [arg for setting in CONFIG_OVERRIDES for arg in ('-c', setting)]


def run_process(argv, *, env, cwd, deadline, prompt=None):
    """Start a private process group; reap it and its descendants on timeout."""
    remaining_seconds(deadline)  # Do not spawn another stage after expiry.
    try:
        child = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, encoding='utf-8',
                                 errors='replace', cwd=cwd, env=env, start_new_session=True,
                                 shell=False)
    except OSError:
        raise CodexFailure('process_start_failed', 'Unable to start Codex CLI.') from None
    try:
        stdout, stderr = child.communicate(input=prompt, timeout=remaining_seconds(deadline))
        remaining_seconds(deadline)
        return child.returncode, stdout, stderr
    except (subprocess.TimeoutExpired, CodexFailure):
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(child.pid, sig)
            except ProcessLookupError:
                pass
            if sig == signal.SIGTERM:
                try:
                    child.communicate(timeout=TERMINATE_GRACE_SECONDS)
                except subprocess.TimeoutExpired:
                    pass
        try:
            child.communicate(timeout=REAP_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            for pipe in (child.stdin, child.stdout, child.stderr):
                pipe.close()
            raise CodexFailure('cleanup_timeout', 'Codex process group was signalled but cleanup did not finish within its budget. No automatic retry.') from None
        raise CodexFailure('timeout', 'Codex CLI timed out; its process group was terminated. No automatic retry.') from None


def parse_events(stdout, returncode, secrets):
    events, answers, final_answers, usage, model, stop_reason = [], [], [], None, None, None
    warnings = []
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
            elif item.get('type') == 'error':
                warnings.append(item)
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
              'usage': usage, 'stop_reason': stop_reason, 'events': events, 'exit_code': returncode,
              'warnings': warnings}
    if returncode != 0 or failure or not completed or answer is None:
        result.update(status='error', error={'code': 'cli_failed' if returncode or failure else 'incomplete_response',
                      'message': 'Codex consultation failed.' if returncode or failure else 'Codex did not emit a completed answer.',
                      'event': failure})
    return result


def consult(prompt, extra_secrets=(), *, deadline=None, task='question', model=None,
            reasoning_effort=None, timeout_seconds=None):
    if os.environ.get(CHILD_MARKER):
        return {'status': 'error', 'error': {'code': 'recursive_call', 'message': 'Bridge calls are disabled in Codex child runs.'}}
    requested = {}
    secrets = secret_values({}) + list(extra_secrets)
    try:
        requested = validate_options(task, model, reasoning_effort, timeout_seconds)
        if deadline is None:
            deadline = consultation_deadline(requested['timeout_seconds'], task)
        remaining_seconds(deadline)
        binary = executable()
        original = subscription_auth()
        auth = cached_subscription_auth(original)
        secrets += secret_values(original) + secret_values(auth)
        supplied = prompt + '\n' + (model or '') + '\n' + (reasoning_effort or '')
        if redact(supplied, secrets) != supplied:
            raise CodexFailure('credential_in_prompt', 'Prompt contains a credential; remove it before consulting Codex.')
        if model is not None:
            catalog = discover_capabilities(deadline=deadline, binary=binary)
            validate_selection(catalog, model, reasoning_effort)
        with tempfile.TemporaryDirectory(prefix='model-bridge-codex-', dir=temporary_root()) as root:
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
                code, out, err = run_process([binary, *config_arguments(), 'login', 'status'], env=env, cwd=work, deadline=deadline)
                if code or 'Logged in using ChatGPT' not in out + err:
                    raise CodexFailure('subscription_auth_unavailable', 'Codex login status did not confirm ChatGPT authentication. Run codex login with ChatGPT.')
                code, out, _ = run_process([binary, *config_arguments(), 'mcp', 'list', '--json'], env=env, cwd=work, deadline=deadline)
                try:
                    servers = json.loads(out)
                    if code or servers != []:
                        raise ValueError()
                except ValueError:
                    raise CodexFailure('mcp_isolation_failed', 'Cannot confirm an empty MCP server configuration; child run blocked.') from None
                selection_args = []
                if model is not None:
                    selection_args += ['--model', model]
                if reasoning_effort is not None:
                    selection_args += ['-c', 'model_reasoning_effort=' + json.dumps(reasoning_effort)]
                argv = [binary, '--no-daemon', *config_arguments(), 'exec', *selection_args, '--strict-config',
                        '--ignore-user-config', '--ignore-rules', '--sandbox', 'read-only',
                        '--ephemeral', '--skip-git-repo-check', '--json', '--color', 'never', '-']
                code, out, _ = run_process(argv, env=env, cwd=work, deadline=deadline, prompt=prompt)
                # Do not retain stderr: it is unstructured and can contain sensitive data.
                result = parse_events(out, code, secrets + secret_values(json.loads(auth_path.read_text(encoding='utf-8'))))
                remaining_seconds(deadline)
                return redact({**result, **requested}, secrets)
            finally:
                persist_auth_refresh(home, original)
    except CodexFailure as exc:
        return redact({'status': 'error', 'error': exc.error, **requested}, secrets)
    except (OSError, ValueError):
        return redact({'status': 'error', 'error': {'code': 'local_setup_failed', 'message': 'Unable to prepare isolated Codex consultation.'}, **requested}, secrets)
