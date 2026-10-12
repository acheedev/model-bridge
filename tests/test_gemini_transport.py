"""Gemini transport and credential regressions; no live provider calls."""
import contextlib
import json
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from google import genai
from google.genai import types
from model_bridge import claude_bridge as bridge, codex_runner, gemini_runner

SENTINEL = 'synthetic-gemini-secret-never-public'


@contextlib.contextmanager
def fake_provider():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            self.server.calls += 1
            self.server.body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.server.silent:
                self.connection.settimeout(1)
                try:
                    if self.connection.recv(1) == b'':
                        self.server.disconnected.set()
                except OSError:
                    pass
                return
            code = self.server.response_code
            if code == 200:
                payload = {'candidates': [{'content': {'role': 'model', 'parts': [{'text': 'ok'}]},
                                          'finishReason': self.server.finish_reason}],
                           'usageMetadata': {'promptTokenCount': 2, 'candidatesTokenCount': 1,
                                             'totalTokenCount': 3},
                           'modelVersion': 'synthetic-model'}
            else:
                payload = {'error': {'code': code, 'status': 'UNAVAILABLE', 'message': SENTINEL}}
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    server.calls = 0
    server.silent = False
    server.response_code = 200
    server.finish_reason = 'STOP'
    server.disconnected = threading.Event()
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02},
                              name='fake-gemini-server', daemon=True)
    thread.start()
    client = genai.Client(api_key=SENTINEL, http_options=types.HttpOptions(
        base_url=f'http://127.0.0.1:{server.server_port}', api_version='v1beta',
        timeout=5000, retry_options=types.HttpRetryOptions(attempts=3),
        httpx_client=httpx.Client(trust_env=False)))
    try:
        yield server, client
    finally:
        client.close()
        server.shutdown()
        server.server_close()
        thread.join(1)


class GeminiTransportTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def generate(self, client, timeout=.2):
        return gemini_runner.generate(client, model='synthetic-model',
                                      system_instruction='synthetic', contents='test', timeout=timeout)

    def test_retryable_provider_error_is_one_network_attempt(self):
        with fake_provider() as (server, client):
            server.response_code = 503
            result = self.generate(client)
            self.assertEqual(result['error']['code'], 'network_or_provider_error')
            self.assertEqual(result['error']['status'], 503)
            self.assertEqual(server.calls, 1)
            self.assertNotIn(SENTINEL, json.dumps(result))

    def test_transport_timeout_closes_socket_without_lingering_client_thread(self):
        with fake_provider() as (server, client):
            server.silent = True
            before = {t.ident for t in threading.enumerate() if not t.daemon}
            started = time.monotonic()
            result = self.generate(client, timeout=.08)
            elapsed = time.monotonic() - started
            self.assertEqual(result['error']['code'], 'timeout')
            self.assertLess(elapsed, 1)
            self.assertTrue(server.disconnected.wait(.8), 'local peer did not observe socket EOF')
            self.assertEqual(server.calls, 1)
            self.assertEqual({t.ident for t in threading.enumerate() if not t.daemon}, before)
            self.assertNotIn(SENTINEL, json.dumps(result))

    def test_real_sdk_preserves_usage_finish_and_output_cap(self):
        with fake_provider() as (server, client), patch.dict(os.environ, {'GEMINI_MAX_OUTPUT_TOKENS': '128'}):
            result = self.generate(client)
            self.assertEqual(result['status'], 'ok')
            self.assertEqual(result['text'], 'ok')
            self.assertEqual(result['finish_reason'], 'STOP')
            self.assertEqual(result['usage']['total_token_count'], 3)
            self.assertEqual(server.body['generationConfig']['maxOutputTokens'], 128)
            self.assertNotIn('tools', server.body)
            self.assertEqual(server.calls, 1)

    def test_provider_token_limit_flags_even_short_output_as_truncated(self):
        with fake_provider() as (server, client):
            server.finish_reason = 'MAX_TOKENS'
            result = self.generate(client)
            self.assertEqual(result['text'], 'ok')
            self.assertEqual(result['finish_reason'], 'MAX_TOKENS')
            self.assertTrue(result['truncated'])
            self.assertEqual(server.calls, 1)

    def test_invalid_credentials_and_timeout_fail_before_network(self):
        for key in (None, '', '   ', 123):
            with self.subTest(key=key), self.assertRaises(gemini_runner.GeminiFailure):
                gemini_runner.make_client(key)
        for timeout in (True, False, 0, -1, float('nan'), float('inf'), 'invalid'):
            client = SimpleNamespace(models=SimpleNamespace(generate_content=Mock()))
            with self.subTest(timeout=timeout), self.assertRaises(gemini_runner.GeminiFailure):
                self.generate(client, timeout=timeout)
            client.models.generate_content.assert_not_called()

    def test_auth_quota_not_found_invalid_request_and_network_are_sanitized(self):
        from google.genai.errors import APIError
        cases = [(401, 'UNAUTHENTICATED', 'authentication_failed'),
                 (403, 'PERMISSION_DENIED', 'authentication_failed'),
                 (429, 'RESOURCE_EXHAUSTED', 'quota_or_rate_limited'),
                 (404, 'NOT_FOUND', 'model_not_found'),
                 (400, 'INVALID_ARGUMENT', 'invalid_request')]
        for status, label, expected in cases:
            error = APIError(status, {'error': {'code': status, 'status': label, 'message': SENTINEL}})
            client = SimpleNamespace(models=SimpleNamespace(generate_content=Mock(side_effect=error)))
            with self.subTest(status=status):
                result = self.generate(client)
                self.assertEqual(result['error']['code'], expected)
                self.assertEqual(result['error']['status'], status)
                self.assertNotIn(SENTINEL, json.dumps(result))
                client.models.generate_content.assert_called_once()
        error = APIError(400, {'error': {'code': 400, 'message': 'API_KEY_INVALID '+SENTINEL}})
        self.assertEqual(gemini_runner._classify_exception(error)['code'], 'authentication_failed')
        for error, expected in [(httpx.ConnectError(SENTINEL), 'network_or_provider_error'),
                                (httpx.ReadTimeout(SENTINEL), 'timeout')]:
            client = SimpleNamespace(models=SimpleNamespace(generate_content=Mock(side_effect=error)))
            result = self.generate(client)
            self.assertEqual(result['error']['code'], expected)
            self.assertNotIn(SENTINEL, json.dumps(result))


class GeminiBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=codex_runner.temporary_root(), prefix='gemini-boundary-test-')
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        for name, value in [('DATA', self.data), ('api_key', ''), ('bridge_token', ''),
                            ('gemini_api_key', SENTINEL), ('gemini_client', Mock()),
                            ('gemini_startup_error', None), ('GEMINI_MODEL', 'synthetic-model')]:
            patcher = patch.object(bridge, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.dict(os.environ, {}, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_known_gemini_key_rejected_before_public_error_or_persistence(self):
        for fields in ({'question': SENTINEL}, {'question': 'safe', 'context': SENTINEL},
                       {'question': 'safe', 'other_answer': SENTINEL}, {'question': 'safe', 'title': SENTINEL}):
            with self.subTest(fields=list(fields)), patch.object(gemini_runner, 'generate') as call:
                with self.assertRaises(ValueError) as failure:
                    bridge.ask_gemini(**fields)
                self.assertNotIn(SENTINEL, str(failure.exception))
                call.assert_not_called()
                self.assertEqual(list(self.data.iterdir()), [])

    def test_claude_and_codex_thread_ids_rejected_without_provider_call(self):
        with bridge.connect() as con:
            for provider, thread in [('claude', 'a'*32), ('codex', 'b'*32)]:
                con.execute('INSERT INTO threads(id,messages,provider) VALUES (?,?,?)', (thread, '[]', provider))
        with patch.object(gemini_runner, 'generate') as call:
            for thread in ('a'*32, 'b'*32):
                with self.assertRaisesRegex(ValueError, 'different provider'):
                    bridge.ask_gemini('safe', mode='open', thread_id=thread)
            call.assert_not_called()

    def test_provider_failure_keeps_secret_out_of_public_and_transcript_errors(self):
        from google.genai.errors import APIError
        error = APIError(429, {'error': {'code': 429, 'message': SENTINEL}})
        bridge.gemini_client = SimpleNamespace(models=SimpleNamespace(generate_content=Mock(side_effect=error)))
        result = bridge.ask_gemini('synthetic request')
        self.assertEqual(result['error']['code'], 'quota_or_rate_limited')
        self.assertNotIn(SENTINEL, json.dumps(result))
        for path in self.data.iterdir():
            if path.suffix in ('.md', '.json'):
                self.assertNotIn(SENTINEL, path.read_text())
        with bridge.connect() as con:
            self.assertEqual(bridge.load_thread(con, result['thread_id'], 'gemini'), [])


if __name__ == '__main__':
    unittest.main()
