"""Gemini Developer API consultation helper using google-genai."""
import importlib
import json
import math
import os
import time

DEFAULT_MODEL = 'gemini-2.5-flash-lite'
DEFAULT_TIMEOUT_SECONDS = 60.0
MAX_TIMEOUT_SECONDS = 1800.0
DEFAULT_MAX_OUTPUT_TOKENS = 2048
MAX_OUTPUT_CHARS = 64000


class GeminiFailure(Exception):
    def __init__(self, code, message, **fields):
        super().__init__(message)
        self.error = {'code': code, 'message': message, **fields}


def configured_model():
    model = os.environ.get('GEMINI_MODEL', DEFAULT_MODEL).strip()
    if not model:
        raise GeminiFailure('invalid_model', 'GEMINI_MODEL must be a nonempty model identifier.')
    return model


def timeout_seconds(value=None):
    if value is None:
        value = os.environ.get('GEMINI_TIMEOUT_SECONDS', str(DEFAULT_TIMEOUT_SECONDS))
    try:
        if isinstance(value, bool):
            raise ValueError()
        value = float(value)
    except (TypeError, ValueError):
        raise GeminiFailure('invalid_timeout', 'Gemini timeout must be a finite positive number at most 1800.') from None
    if not 0 < value <= MAX_TIMEOUT_SECONDS:
        raise GeminiFailure('invalid_timeout', 'Gemini timeout must be a finite positive number at most 1800.')
    return value


def max_output_tokens():
    try:
        value = int(os.environ.get('GEMINI_MAX_OUTPUT_TOKENS', str(DEFAULT_MAX_OUTPUT_TOKENS)))
    except ValueError:
        raise GeminiFailure('invalid_max_output_tokens', 'GEMINI_MAX_OUTPUT_TOKENS must be an integer from 1 to 8192.') from None
    if not 1 <= value <= 8192:
        raise GeminiFailure('invalid_max_output_tokens', 'GEMINI_MAX_OUTPUT_TOKENS must be an integer from 1 to 8192.')
    return value


def make_client(api_key):
    if not isinstance(api_key, str) or not api_key.strip():
        raise GeminiFailure('credentials_unavailable', 'Gemini API key is not configured for this bridge.')
    try:
        genai = importlib.import_module('google.genai')
    except ImportError:
        raise GeminiFailure('sdk_unavailable', 'Install google-genai in the bridge environment before enabling Gemini.') from None
    types = importlib.import_module('google.genai.types')
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(
        timeout=math.ceil(timeout_seconds() * 1000),
        retry_options=types.HttpRetryOptions(attempts=1)))


def _to_plain(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_to_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_plain(item) for key, item in value.items()}
    for method in ('model_dump', 'to_json_dict'):
        if hasattr(value, method):
            try:
                return _to_plain(getattr(value, method)())
            except TypeError:
                try:
                    return _to_plain(getattr(value, method)(mode='json', exclude_none=True))
                except TypeError:
                    pass
    if hasattr(value, 'name'):
        return value.name
    return str(value)


def _usage(response):
    usage = _to_plain(getattr(response, 'usage_metadata', None))
    return usage if isinstance(usage, dict) else None


def _finish_reason(response):
    candidates = getattr(response, 'candidates', None) or []
    if not candidates:
        return None
    reason = getattr(candidates[0], 'finish_reason', None)
    return _to_plain(reason)


def _response_payload(response):
    payload = _to_plain(response)
    if isinstance(payload, dict):
        return payload
    return {
        'text': getattr(response, 'text', None),
        'usage_metadata': _usage(response),
        'finish_reason': _finish_reason(response),
    }


def _classify_exception(exc):
    name = type(exc).__name__
    status = getattr(exc, 'status_code', None) or getattr(exc, 'code', None)
    lowered = (name + ' ' + str(status)).lower()
    invalid_key = 'api_key_invalid' in str(getattr(exc, 'message', '')).lower()
    if invalid_key or status in (401, 403) or 'unauth' in lowered or 'permission' in lowered:
        code = 'authentication_failed'
    elif status == 429 or 'quota' in lowered or 'resourceexhausted' in lowered:
        code = 'quota_or_rate_limited'
    elif status == 404:
        code = 'model_not_found'
    elif status == 400:
        code = 'invalid_request'
    elif 'timeout' in lowered:
        code = 'timeout'
    elif 'blocked' in lowered or 'safety' in lowered:
        code = 'blocked_or_empty_response'
    else:
        code = 'network_or_provider_error'
    messages = {
        'authentication_failed': 'Gemini authentication failed; check the protected key and access.',
        'quota_or_rate_limited': 'Gemini quota or rate limit reached; no automatic retry.',
        'model_not_found': 'Gemini model was not found or is inaccessible; no fallback.',
        'invalid_request': 'Gemini rejected the request configuration; no automatic retry.',
        'timeout': 'Gemini HTTP request timed out; no automatic retry.',
        'blocked_or_empty_response': 'Gemini blocked the request or returned no usable response.',
        'network_or_provider_error': 'Gemini network or provider request failed; no automatic retry.',
    }
    return {'code': code, 'message': messages[code],
            'type': name, 'status': status}


def generate(client, *, model, system_instruction, contents, timeout=None):
    seconds = timeout_seconds(timeout)
    max_tokens = max_output_tokens()
    started = time.monotonic()
    try:
        types = importlib.import_module('google.genai.types')
        config = types.GenerateContentConfig(
            system_instruction=system_instruction, max_output_tokens=max_tokens,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            http_options=types.HttpOptions(
                timeout=math.ceil(seconds * 1000),
                retry_options=types.HttpRetryOptions(attempts=1)))
        # The synchronous transport owns its HTTP timeout. Do not return while
        # a ThreadPoolExecutor continues the request after a Future timeout.
        # This is an HTTP phase/inactivity timeout, not an overall wall deadline.
        response = client.models.generate_content(model=model, contents=contents, config=config)
    except ImportError:
        return {'status': 'error', 'elapsed_seconds': time.monotonic() - started,
                'error': {'code': 'sdk_unavailable', 'message': 'Gemini SDK is unavailable.'}}
    except Exception as exc:
        return {'status': 'error', 'elapsed_seconds': time.monotonic() - started,
                'error': _classify_exception(exc)}

    elapsed = time.monotonic() - started
    text = getattr(response, 'text', '') or ''
    finish_reason = _finish_reason(response)
    usage = _usage(response)
    truncated = finish_reason == 'MAX_TOKENS'
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[:MAX_OUTPUT_CHARS]
        truncated = True
    result = {'status': 'ok', 'text': text, 'model': model, 'usage': usage,
              'finish_reason': finish_reason, 'elapsed_seconds': elapsed,
              'truncated': truncated, 'max_output_tokens': max_tokens,
              'response': _response_payload(response)}
    if not text.strip():
        result['status'] = 'error'
        result['error'] = {'code': 'blocked_or_empty_response',
                           'message': 'Gemini returned no text.',
                           'finish_reason': finish_reason}
    return result
