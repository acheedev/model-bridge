import asyncio
import json
import os
import signal
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from model_bridge import claude_bridge as bridge
from model_bridge import codex_runner as runner
from model_bridge import configure_mcp_timeout as client_config
from model_bridge import bridge_paths


def temporary_test_directory():
    return tempfile.TemporaryDirectory(prefix='bridge-test-', dir=runner.temporary_root())


def jsonl(*events):
    return '\n'.join(json.dumps(event) for event in events)


SUCCESS = jsonl(
    {'type': 'thread.started', 'thread_id': 'cli-session-not-bridge-id'},
    {'type': 'item.completed', 'item': {'id': 'item_0', 'type': 'agent_message', 'text': 'Bridge confirmed.'}},
    {'type': 'turn.completed', 'usage': {'input_tokens': 12, 'cached_input_tokens': 3, 'output_tokens': 4}},
)
CATALOG = json.dumps({'models': [
    {'slug': 'capable-model', 'supported_reasoning_levels': [
        {'effort': effort} for effort in ('medium', 'high', 'xhigh', 'ultra')], 'tool_mode': 'code_mode_only'},
    {'slug': 'limited-model', 'supported_reasoning_levels': [{'effort': 'medium'}]},
]})


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = temporary_test_directory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        (self.home / 'auth.json').write_text(json.dumps({'auth_mode': 'chatgpt', 'OPENAI_API_KEY': None,
            'tokens': {'access_token': 'private-access-credential', 'refresh_token': 'private-refresh-credential'}}))
        self.env = patch.dict(os.environ, {'CODEX_HOME': str(self.home), 'CODEX_BIN': '/mock/codex',
            'BRIDGE_CODEX_AUTH_CACHE': str(self.home / 'cache.json'),
            'OPENAI_API_KEY': 'private-api-credential', 'CODEX_API_KEY': 'other-api-credential',
            'OPENAI_BASE_URL': 'https://untrusted.invalid', 'MODEL_BRIDGE_CHILD': ''}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.which = patch.object(runner.shutil, 'which', return_value='/mock/codex')
        self.which.start()
        self.addCleanup(self.which.stop)

    def process(self, output, code=0):
        proc = Mock(pid=4321, returncode=code)
        proc.communicate.return_value = (output, '')
        return proc

    def test_success_stdin_isolation_and_auth(self):
        processes = [self.process('Logged in using ChatGPT'), self.process('[]'), self.process(SUCCESS)]
        calls = []
        def spawn(argv, **kw):
            calls.append((argv, kw))
            self.assertFalse(kw['shell'])
            self.assertTrue(kw['start_new_session'])
            self.assertEqual(list(Path(kw['cwd']).iterdir()), [])
            self.assertTrue(Path(kw['cwd']).resolve().is_relative_to(runner.PROJECT_ROOT / '.tmp'))
            self.assertTrue(Path(kw['env']['TMPDIR']).resolve().is_relative_to(runner.PROJECT_ROOT / '.tmp'))
            self.assertNotEqual(kw['env']['CODEX_HOME'], str(self.home))
            auth = json.loads((Path(kw['env']['CODEX_HOME']) / 'auth.json').read_text())
            self.assertNotIn('OPENAI_API_KEY', auth)
            self.assertEqual(auth['tokens']['access_token'], 'private-access-credential')
            self.assertEqual((Path(kw['env']['CODEX_HOME']) / 'auth.json').stat().st_mode & 0o777, 0o600)
            self.assertEqual(kw['env']['MODEL_BRIDGE_CHILD'], '1')
            for key in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'OPENAI_BASE_URL'):
                self.assertNotIn(key, kw['env'])
            return processes[len(calls)-1]
        with patch.object(runner.subprocess, 'Popen', side_effect=spawn):
            result = runner.consult('user prompt with $(shell syntax)')
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['text'], 'Bridge confirmed.')
        self.assertEqual(result['usage']['output_tokens'], 4)
        self.assertIsNone(result['model'])
        self.assertIsNone(result['stop_reason'])
        argv = calls[-1][0]
        for flag in ('--no-daemon', '--strict-config', '--ignore-user-config', '--ignore-rules', '--ephemeral', '--json'):
            self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index('--sandbox')+1], 'read-only')
        self.assertNotIn('user prompt with $(shell syntax)', argv)
        processes[-1].communicate.assert_called_once()
        self.assertEqual(processes[-1].communicate.call_args.kwargs['input'], 'user prompt with $(shell syntax)')
        self.assertGreater(processes[-1].communicate.call_args.kwargs['timeout'], 0)
        self.assertLessEqual(processes[-1].communicate.call_args.kwargs['timeout'], 120)
        for feature in runner.DISABLED_FEATURES:
            self.assertIn('features.'+feature+'=false', argv)
        self.assertIn('mcp_servers={}', argv)
        self.assertFalse(Path(calls[-1][1]['cwd']).exists())

    def test_api_login_blocked(self):
        with patch.object(runner.subprocess, 'Popen', return_value=self.process('Logged in using an API key')) as spawn:
            result = runner.consult('hello')
        self.assertEqual(result['error']['code'], 'subscription_auth_unavailable')
        self.assertEqual(spawn.call_count, 1)

    def test_missing_or_api_auth_blocked(self):
        for auth in ({'auth_mode': 'apikey', 'OPENAI_API_KEY': 'private-key'}, {}):
            (self.home / 'auth.json').write_text(json.dumps(auth))
            with patch.object(runner.subprocess, 'Popen') as spawn:
                self.assertEqual(runner.consult('hello')['error']['code'], 'subscription_auth_unavailable')
                spawn.assert_not_called()

    def test_managed_mcp_server_blocks_exec(self):
        processes = [self.process('Logged in using ChatGPT'), self.process('[{"name":"model-bridge"}]')]
        with patch.object(runner.subprocess, 'Popen', side_effect=processes) as spawn:
            result = runner.consult('hello')
        self.assertEqual(result['error']['code'], 'mcp_isolation_failed')
        self.assertEqual(spawn.call_count, 2)

    def test_timeout_terminates_group_and_never_retries(self):
        proc = self.process('')
        proc.communicate.side_effect = [subprocess.TimeoutExpired('codex', 7), subprocess.TimeoutExpired('codex', 2), ('', '')]
        processes = [self.process('Logged in using ChatGPT'), self.process('[]'), proc]
        with patch.dict(os.environ, {'CODEX_TIMEOUT_SECONDS': '7'}), patch.object(runner.subprocess, 'Popen', side_effect=processes) as spawn, patch.object(runner.os, 'killpg') as kill:
            result = runner.consult('hello')
        self.assertEqual(result['error']['code'], 'timeout')
        self.assertEqual(spawn.call_count, 3)
        self.assertEqual(kill.call_args_list[0].args, (4321, signal.SIGTERM))
        self.assertEqual(kill.call_args_list[1].args, (4321, signal.SIGKILL))

    def test_process_start_failure(self):
        with patch.object(runner.subprocess, 'Popen', side_effect=OSError('private-access-credential')):
            result = runner.consult('hello')
        self.assertEqual(result['error']['code'], 'process_start_failed')
        self.assertNotIn('private-access-credential', json.dumps(result))

    def test_cli_failure_and_jsonl_error_redaction(self):
        output = jsonl({'type': 'error', 'message': 'private-access-credential Bearer unknown-token sk-any-key'},
                       {'type': 'turn.failed', 'error': {'message': 'private-api-credential'}})
        result = runner.parse_events(output, 1, ['private-access-credential', 'private-api-credential'])
        self.assertEqual(result['error']['code'], 'cli_failed')
        for secret in ('private-access-credential', 'private-api-credential', 'unknown-token', 'sk-any-key'):
            self.assertNotIn(secret, json.dumps(result))

    def test_malformed_or_incomplete_events(self):
        for output in ('not json', 'null', '{"type":"item.completed","item":42}'):
            self.assertEqual(runner.parse_events(output, 0, [])['error']['code'], 'invalid_jsonl')
        self.assertEqual(runner.parse_events('', 0, [])['error']['code'], 'incomplete_response')
        self.assertEqual(runner.parse_events(SUCCESS, 2, [])['error']['code'], 'cli_failed')

    def test_only_report_actual_metadata(self):
        output = SUCCESS + '\n' + jsonl({'type': 'turn.completed', 'model': 'reported-model', 'stop_reason': 'reported-reason'})
        result = runner.parse_events(output, 0, [])
        self.assertEqual(result['model'], 'reported-model')
        self.assertEqual(result['stop_reason'], 'reported-reason')
        self.assertIsNone(result['usage'])

    def test_final_answer_excludes_progress(self):
        progress = {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'Checking...', 'phase': 'commentary'}}
        self.assertEqual(runner.parse_events(jsonl(progress) + '\n' + SUCCESS, 0, [])['text'], 'Bridge confirmed.')
        unphased = {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'Earlier message'}}
        self.assertEqual(runner.parse_events(jsonl(unphased) + '\n' + SUCCESS, 0, [])['text'], 'Bridge confirmed.')

    def test_exec_failure_no_retry(self):
        processes = [self.process('Logged in using ChatGPT'), self.process('[]'),
                     self.process(jsonl({'type': 'turn.failed', 'error': {'message': 'failed'}}), 1)]
        with patch.object(runner.subprocess, 'Popen', side_effect=processes) as spawn:
            result = runner.consult('hello')
        self.assertEqual(result['error']['code'], 'cli_failed')
        self.assertEqual(spawn.call_count, 3)

    def test_unavailable_executable_and_path_fallback(self):
        with patch.object(runner.shutil, 'which', return_value=None):
            self.assertEqual(runner.consult('hello')['error']['code'], 'cli_unavailable')
        os.environ.pop('CODEX_BIN')
        runner.executable()
        runner.shutil.which.assert_called_with('codex')

    def test_invalid_timeout(self):
        for value in ('nan', 'inf', '0', '-1', 'oops'):
            with patch.dict(os.environ, {'CODEX_TIMEOUT_SECONDS': value}):
                self.assertEqual(runner.consult('hello')['error']['code'], 'invalid_timeout')

    def test_per_call_validation_blocks_processes(self):
        invalid = [({'timeout_seconds': value}, 'invalid_timeout') for value in
                   (True, False, '900', 0, -1, 1801, float('nan'), float('inf'), 10**400)]
        invalid += [({'task': 'project_edit'}, 'invalid_task'),
                    ({'model': ''}, 'invalid_selection'),
                    ({'model': 'bad model'}, 'invalid_selection'),
                    ({'reasoning_effort': 'high'}, 'model_required'),
                    ({'model': 'capable-model', 'reasoning_effort': 'high"'}, 'invalid_selection')]
        with patch.object(runner.subprocess, 'Popen') as spawn:
            for kwargs, error in invalid:
                with self.subTest(kwargs=kwargs):
                    self.assertEqual(runner.consult('hello', **kwargs)['error']['code'], error)
            spawn.assert_not_called()

    def test_task_defaults_override_and_maximum(self):
        self.assertEqual(runner.timeout_seconds(), 120)
        self.assertEqual(runner.timeout_seconds(task='code_generation'), 900)
        with patch.dict(os.environ, {'CODEX_TIMEOUT_SECONDS': '8'}):
            self.assertEqual(runner.timeout_seconds(), 8)
            self.assertEqual(runner.timeout_seconds(task='code_generation'), 900)
            self.assertEqual(runner.timeout_seconds(60, 'question'), 60)
        self.assertEqual(runner.timeout_seconds(1800), 1800)
        self.assertEqual(runner.timeout_seconds(0.5), 0.5)

    def test_catalog_discovery_is_offline_without_auth(self):
        def spawn(argv, **kw):
            self.assertEqual(argv[-3:], ['debug', 'models', '--bundled'])
            self.assertFalse((Path(kw['env']['CODEX_HOME']) / 'auth.json').exists())
            self.assertEqual(list(Path(kw['cwd']).iterdir()), [])
            self.assertNotIn('OPENAI_API_KEY', kw['env'])
            return self.process(CATALOG)
        with patch.object(runner.subprocess, 'Popen', side_effect=spawn):
            catalog = runner.discover_capabilities(deadline=runner.consultation_deadline())
        self.assertEqual(catalog['capable-model']['reasoning_efforts'], ['medium', 'high', 'xhigh', 'ultra'])

    def test_exact_model_effort_arguments_and_unknown_reported_model(self):
        for effort in ('medium', 'high', 'xhigh', 'ultra'):
            processes = [self.process(CATALOG), self.process('Logged in using ChatGPT'),
                         self.process('[]'), self.process(SUCCESS)]
            with patch.object(runner.subprocess, 'Popen', side_effect=processes) as spawn:
                result = runner.consult('author code', task='code_generation', model='capable-model',
                                        reasoning_effort=effort, timeout_seconds=60)
            self.assertEqual(result['status'], 'ok')
            self.assertEqual(result['requested_model'], 'capable-model')
            self.assertEqual(result['requested_reasoning_effort'], effort)
            self.assertIsNone(result['model'])
            argv = spawn.call_args.args[0]
            self.assertEqual(argv[argv.index('--model')+1], 'capable-model')
            self.assertGreater(argv.index('--model'), argv.index('exec'))
            self.assertIn('model_reasoning_effort="'+effort+'"', argv)
            self.assertEqual(argv[argv.index('--sandbox')+1], 'read-only')
            self.assertNotIn('--add-dir', argv)
            self.assertEqual(spawn.call_count, 4)

    def test_unsupported_selections_stop_before_exec(self):
        for model, effort, error in [('unknown-model', 'medium', 'unsupported_model'),
                                     ('limited-model', 'ultra', 'unsupported_reasoning_effort')]:
            with patch.object(runner.subprocess, 'Popen', return_value=self.process(CATALOG)) as spawn:
                result = runner.consult('hello', model=model, reasoning_effort=effort)
            self.assertEqual(result['error']['code'], error)
            self.assertEqual(result['requested_model'], model)
            self.assertEqual(spawn.call_count, 1)
            self.assertEqual(spawn.call_args.args[0][-1], '--bundled')

    def test_model_only_keeps_effort_unspecified(self):
        processes = [self.process(CATALOG), self.process('Logged in using ChatGPT'),
                     self.process('[]'), self.process(SUCCESS)]
        with patch.object(runner.subprocess, 'Popen', side_effect=processes) as spawn:
            result = runner.consult('hello', model='capable-model')
        self.assertEqual(result['status'], 'ok')
        self.assertIsNone(result['requested_reasoning_effort'])
        self.assertFalse(any(arg.startswith('model_reasoning_effort=') for arg in spawn.call_args.args[0]))

    def test_catalog_failure_never_falls_back(self):
        for output, code in [('not json', 0), ('{"models": []}', 0), (CATALOG, 1),
                             ('{"models": [{}]}', 0)]:
            with patch.object(runner.subprocess, 'Popen', return_value=self.process(output, code)) as spawn:
                result = runner.consult('hello', model='capable-model')
            self.assertEqual(result['error']['code'], 'capabilities_unavailable')
            self.assertEqual(spawn.call_count, 1)

    def test_capability_discovery_shares_consultation_deadline(self):
        clock = [100.0]
        outputs = [CATALOG, 'Logged in using ChatGPT', '[]', SUCCESS]
        processes = [self.process(output) for output in outputs]
        for proc, output in zip(processes, outputs):
            def communicate(output=output, **kw):
                clock[0] += 2
                return output, ''
            proc.communicate.side_effect = communicate
        with patch.object(runner.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(runner.subprocess, 'Popen', side_effect=processes):
            result = runner.consult('code', model='capable-model', task='code_generation', timeout_seconds=10)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual([p.communicate.call_args.kwargs['timeout'] for p in processes], [10, 8, 6, 4])

    def test_model_selection_credentials_are_rejected_and_redacted(self):
        with patch.object(runner.subprocess, 'Popen') as spawn:
            result = runner.consult('safe prompt', model='private-access-credential')
        self.assertEqual(result['error']['code'], 'credential_in_prompt')
        self.assertNotIn('private-access-credential', json.dumps(result))
        spawn.assert_not_called()

    def test_code_mode_diagnostic_is_visible_and_does_not_invent_model(self):
        diagnostic = {'type': 'item.completed', 'item': {'type': 'error', 'message': 'Code Mode is unavailable; private-access-credential'}}
        result = runner.parse_events(jsonl(diagnostic) + '\n' + SUCCESS, 0, ['private-access-credential'])
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(len(result['warnings']), 1)
        self.assertIn('[REDACTED]', result['warnings'][0]['message'])
        self.assertIsNone(result['model'])

    def test_recursion_and_credentials_in_prompt(self):
        with patch.object(runner.subprocess, 'Popen') as spawn:
            with patch.dict(os.environ, {'MODEL_BRIDGE_CHILD': '1'}):
                self.assertEqual(runner.consult('hello')['error']['code'], 'recursive_call')
            self.assertEqual(runner.consult('private-access-credential')['error']['code'], 'credential_in_prompt')
            spawn.assert_not_called()
        self.assertFalse(runner.prompt_is_safe('private-refresh-credential'))

    def test_refresh_cached_privately_without_writing_source_login(self):
        original = runner.subscription_auth()
        with temporary_test_directory() as temp:
            home = Path(temp)
            refreshed = {**original, 'tokens': {'access_token': 'new-private-token'}, 'last_refresh': 'now'}
            (home / 'auth.json').write_text(json.dumps(refreshed))
            runner.persist_auth_refresh(home, original)
            self.assertEqual(runner.subscription_auth(), original)
            self.assertEqual(runner.cached_subscription_auth(original)['tokens'], refreshed['tokens'])
            self.assertEqual(runner.auth_cache_path().stat().st_mode & 0o777, 0o600)
            concurrent = {'auth_mode': 'chatgpt', 'tokens': {'access_token': 'concurrent-login'}}
            (self.home / 'auth.json').write_text(json.dumps(concurrent))
            runner.persist_auth_refresh(home, original)
            self.assertEqual(runner.subscription_auth(), concurrent)
            self.assertEqual(runner.cached_subscription_auth(concurrent), concurrent)

    def test_login_changes_at_replace_boundary_are_never_overwritten(self):
        original = runner.subscription_auth()
        concurrent = {'auth_mode': 'chatgpt', 'tokens': {'access_token': 'concurrent-login'}}
        replace = os.replace
        with temporary_test_directory() as temp:
            home = Path(temp)
            (home / 'auth.json').write_text(json.dumps({**original, 'tokens': {'access_token': 'refreshed-token'}}))
            def change_login_then_replace(src, dst):
                # Reproduce the old check-to-replace race at its final write boundary.
                (self.home / 'auth.json').write_text(json.dumps(concurrent))
                self.assertEqual(dst, runner.auth_cache_path())
                replace(src, dst)
            with patch.object(runner.os, 'replace', side_effect=change_login_then_replace):
                runner.persist_auth_refresh(home, original)
        self.assertEqual(runner.subscription_auth(), concurrent)
        self.assertEqual(runner.cached_subscription_auth(concurrent), concurrent)

    def test_cache_cannot_replace_source_auth_even_through_symlink(self):
        original = (self.home / 'auth.json').read_bytes()
        link = self.home / 'auth-link.json'
        link.symlink_to(self.home / 'auth.json')
        for target in (self.home / 'auth.json', link):
            with patch.dict(os.environ, {'BRIDGE_CODEX_AUTH_CACHE': str(target)}), patch.object(runner.subprocess, 'Popen') as spawn:
                result = runner.consult('hello')
            self.assertEqual(result['error']['code'], 'invalid_auth_cache')
            spawn.assert_not_called()
            self.assertEqual((self.home / 'auth.json').read_bytes(), original)

    def test_consultation_uses_cached_refresh_and_redacts_it(self):
        original = runner.subscription_auth()
        cache = {'source_fingerprint': runner.auth_fingerprint(original), 'auth':
                 {**original, 'tokens': {'access_token': 'cached-private-token'}}}
        runner.auth_cache_path().write_text(json.dumps(cache))
        processes = [self.process('Logged in using ChatGPT'), self.process('[]'),
                     self.process(SUCCESS.replace('Bridge confirmed.', 'cached-private-token'))]
        def spawn(argv, **kw):
            copied = json.loads((Path(kw['env']['CODEX_HOME']) / 'auth.json').read_text())
            self.assertEqual(copied['tokens']['access_token'], 'cached-private-token')
            return processes.pop(0)
        with patch.object(runner.subprocess, 'Popen', side_effect=spawn):
            result = runner.consult('safe prompt')
        self.assertEqual(result['text'], '[REDACTED]')
        self.assertNotIn('cached-private-token', json.dumps(result))
        self.assertFalse(runner.prompt_is_safe('cached-private-token'))
        self.assertEqual(runner.subscription_auth(), original)

    def test_one_deadline_reduces_each_stage_budget(self):
        clock = [100.0]
        processes = [self.process('Logged in using ChatGPT'), self.process('[]'), self.process(SUCCESS)]
        for proc, output, duration in zip(processes, ['Logged in using ChatGPT', '[]', SUCCESS], [3, 4, 2]):
            def communicate(output=output, duration=duration, **kw):
                clock[0] += duration
                return output, ''
            proc.communicate.side_effect = communicate
        with patch.dict(os.environ, {'CODEX_TIMEOUT_SECONDS': '10'}), patch.object(runner.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(runner.subprocess, 'Popen', side_effect=processes):
            result = runner.consult('hello')
        self.assertEqual(result['status'], 'ok')
        self.assertEqual([p.communicate.call_args.kwargs['timeout'] for p in processes], [10, 7, 3])

    def test_preflights_can_exhaust_overall_deadline(self):
        clock = [100.0]
        login, mcp = self.process(''), self.process('[]')
        def communicate(**kw):
            clock[0] += 7
            return 'Logged in using ChatGPT', ''
        login.communicate.side_effect = communicate
        def mcp_communicate(**kw):
            clock[0] += 4
            return '[]', ''
        mcp.communicate.side_effect = mcp_communicate
        with patch.dict(os.environ, {'CODEX_TIMEOUT_SECONDS': '10'}), patch.object(runner.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(runner.subprocess, 'Popen', side_effect=[login, mcp]) as spawn, patch.object(runner.os, 'killpg') as kill:
            result = runner.consult('hello')
        self.assertEqual(result['error']['code'], 'timeout')
        self.assertEqual(spawn.call_count, 2)  # Never starts exec with a new timeout.
        self.assertEqual(mcp.communicate.call_args_list[0].kwargs['timeout'], 3)
        self.assertEqual(kill.call_count, 2)

    def test_expired_deadline_does_not_spawn(self):
        with patch.object(runner.time, 'monotonic', return_value=100), patch.object(runner.subprocess, 'Popen') as spawn:
            with self.assertRaises(runner.CodexFailure) as failure:
                runner.run_process(['codex'], env={}, cwd=self.home, deadline=99)
        self.assertEqual(failure.exception.error['code'], 'timeout')
        spawn.assert_not_called()

    def test_cleanup_has_separate_bounded_budget(self):
        proc = self.process('')
        proc.communicate.side_effect = [subprocess.TimeoutExpired('codex', 1), subprocess.TimeoutExpired('codex', 2), subprocess.TimeoutExpired('codex', 2)]
        with patch.object(runner.time, 'monotonic', return_value=100), patch.object(runner.subprocess, 'Popen', return_value=proc), patch.object(runner.os, 'killpg'):
            with self.assertRaises(runner.CodexFailure) as failure:
                runner.run_process(['codex'], env={}, cwd=self.home, deadline=101)
        self.assertEqual(failure.exception.error['code'], 'cleanup_timeout')
        self.assertEqual([c.kwargs['timeout'] for c in proc.communicate.call_args_list], [1, 2, 2])
        proc.stdout.close.assert_called_once()

    def test_mcp_timeout_alignment_preserves_other_configuration(self):
        path = self.home / 'config.toml'
        text = '[mcp_servers.other]\ntool_timeout_sec = 9\n[mcp_servers.model-bridge]\nurl = "local-url"\nhttp_headers_helper = "private-helper"\n[features]\nplugins = true\n'
        path.write_text(text)
        with patch.dict(os.environ, {'CODEX_TIMEOUT_SECONDS': '120'}):
            self.assertEqual(client_config.configure(path), 1811)
        updated = path.read_text()
        self.assertIn('[mcp_servers.model-bridge]\ntool_timeout_sec = 1811\n', updated)
        self.assertEqual(updated.replace('tool_timeout_sec = 1811\n', ''), text)
        self.assertEqual(client_config.aligned_config(updated, 1811), updated)
        with patch.dict(os.environ, {'CODEX_TIMEOUT_SECONDS': '7.1'}):
            self.assertEqual(client_config.configure(path), 1811)
        self.assertGreater(runner.mcp_timeout_seconds(), runner.MAX_TIMEOUT_SECONDS + runner.CLEANUP_SECONDS + runner.MCP_RESPONSE_MARGIN_SECONDS)
        self.assertIn('tool_timeout_sec = 9', path.read_text())
        with self.assertRaises(ValueError): client_config.aligned_config('[features]\n', 130)


class PathBoundaryTests(unittest.TestCase):
    def test_package_layout_keeps_runtime_stores_at_checkout_root(self):
        project = Path(bridge_paths.__file__).resolve().parents[1]
        self.assertEqual(bridge_paths.PROJECT_ROOT, project)
        self.assertEqual(runner.PROJECT_ROOT, project)
        with patch.dict(os.environ, clear=True):
            self.assertEqual(bridge_paths.transcript_directory(), project / 'transcripts')
            self.assertEqual(runner.temporary_root(), project / '.tmp')

    def setUp(self):
        self.tmp = temporary_test_directory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_approved_overrides_are_resolved(self):
        for value in (self.root / 'nested/../transcripts', Path('/home/jachee/.codex/model-bridge/test-data')):
            with patch.dict(os.environ, {'BRIDGE_DATA_DIR': str(value), 'BRIDGE_CODEX_AUTH_CACHE': str(value / 'cache.json')}):
                self.assertEqual(bridge_paths.transcript_directory(), value.resolve())
                self.assertEqual(runner.auth_cache_path(), (value / 'cache.json').resolve())

    def test_outside_overrides_fail_before_io_or_cli(self):
        home = self.root / 'home'
        home.mkdir()
        (home / 'auth.json').write_text(json.dumps({'auth_mode': 'chatgpt', 'tokens': {'access_token': 'fixture-token'}}))
        for value in ('/home/jachee/blocked-bridge-test', '/home/jachee/projects-escape/test', '/home/jachee/.codex-escape/test'):
            with patch.dict(os.environ, {'BRIDGE_DATA_DIR': value}):
                with self.assertRaises(ValueError): bridge_paths.transcript_directory()
            with patch.dict(os.environ, {'BRIDGE_CODEX_AUTH_CACHE': value, 'CODEX_HOME': str(home), 'MODEL_BRIDGE_CHILD': ''}), patch.object(runner.subprocess, 'Popen') as spawn, patch.object(runner, 'executable', return_value='/mock/codex'):
                with self.assertRaises(runner.CodexFailure): runner.cached_subscription_auth({})
                result = runner.consult('fixture question')
                self.assertEqual(result['error']['code'], 'invalid_auth_cache')
                spawn.assert_not_called()

    def test_directory_and_file_symlink_escapes_rejected(self):
        directory = self.root / 'escape'
        directory.symlink_to('/home/jachee', target_is_directory=True)
        cache = self.root / 'cache.json'
        cache.symlink_to('/home/jachee/blocked-bridge-cache.json')
        for value in (directory / 'blocked-bridge-test', cache):
            with patch.dict(os.environ, {'BRIDGE_DATA_DIR': str(value)}):
                with self.assertRaises(ValueError): bridge_paths.transcript_directory()
            with patch.dict(os.environ, {'BRIDGE_CODEX_AUTH_CACHE': str(value)}):
                with self.assertRaises(runner.CodexFailure): runner.auth_cache_path()

    def test_transcript_database_and_output_symlink_escapes_rejected(self):
        database = self.root / 'threads.sqlite3'
        database.symlink_to('/home/jachee/blocked-bridge-db.sqlite3')
        with patch.object(bridge, 'DATA', self.root), patch.object(bridge.sqlite3, 'connect') as connect:
            with self.assertRaises(ValueError): bridge.connect()
            connect.assert_not_called()
        output = self.root / 'test.md'
        output.symlink_to('/home/jachee/blocked-bridge-output.md')
        with self.assertRaises(ValueError): bridge.atomic_text(output, 'test')
        output.unlink()
        output.with_suffix('.md.tmp').symlink_to('/home/jachee/blocked-bridge-output.tmp')
        with self.assertRaises(ValueError): bridge.atomic_text(output, 'test')
        self.assertFalse(output.exists())

    def test_atomic_export_failure_cleans_temp_and_preserves_original(self):
        output = self.root / 'test.md'
        output.write_text('original')
        with patch.object(bridge.os, 'replace', side_effect=OSError('injected failure')):
            with self.assertRaises(OSError): bridge.atomic_text(output, 'replacement')
        self.assertEqual(output.read_text(), 'original')
        self.assertFalse(output.with_suffix('.md.tmp').exists())

    def test_capability_failure_cleans_project_temp(self):
        work = []
        def fail(*args, **kwargs):
            work.append(kwargs['cwd'])
            self.assertTrue(kwargs['cwd'].is_relative_to(runner.PROJECT_ROOT / '.tmp'))
            raise runner.CodexFailure('timeout', 'injected failure')
        with patch.object(runner, 'run_process', side_effect=fail):
            with self.assertRaises(runner.CodexFailure): runner.discover_capabilities(deadline=1, binary='/mock/codex')
        self.assertEqual(len(work), 1)
        self.assertFalse(work[0].parent.exists())

    def test_cache_permissions_and_failed_replace_cleanup(self):
        home = self.root / 'home'
        home.mkdir()
        original = {'auth_mode': 'chatgpt', 'tokens': {'access_token': 'original'}}
        (home / 'auth.json').write_text(json.dumps({'auth_mode': 'chatgpt', 'tokens': {'access_token': 'refreshed'}}))
        folder = self.root / 'cache'
        folder.mkdir(mode=0o755)
        target = folder / 'auth.json'
        with patch.dict(os.environ, {'BRIDGE_CODEX_AUTH_CACHE': str(target)}):
            runner.persist_auth_refresh(home, original)
            self.assertEqual(folder.stat().st_mode & 0o777, 0o700)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            saved = target.read_bytes()
            with patch.object(runner.os, 'replace', side_effect=OSError('injected failure')):
                with self.assertRaises(runner.CodexFailure): runner.persist_auth_refresh(home, original)
            self.assertEqual(target.read_bytes(), saved)
            self.assertEqual(list(folder.glob('.bridge-auth-*')), [])

    def test_tmp_directory_symlink_escape_rejected(self):
        project = self.root / 'project'
        project.mkdir()
        (project / '.tmp').symlink_to('/home/jachee', target_is_directory=True)
        with patch.object(runner, 'PROJECT_ROOT', project):
            with self.assertRaises(runner.CodexFailure): runner.temporary_root()

    def test_consultation_failure_cleans_private_home_and_work(self):
        home = self.root / 'home'
        home.mkdir()
        (home / 'auth.json').write_text(json.dumps({'auth_mode': 'chatgpt', 'tokens': {'access_token': 'fixture-token'}}))
        work = []
        def fail(*args, **kwargs):
            work.append(kwargs['cwd'])
            raise runner.CodexFailure('timeout', 'injected failure')
        with patch.dict(os.environ, {'CODEX_HOME': str(home), 'BRIDGE_CODEX_AUTH_CACHE': str(self.root / 'cache.json'), 'MODEL_BRIDGE_CHILD': ''}), patch.object(runner, 'executable', return_value='/mock/codex'), patch.object(runner, 'run_process', side_effect=fail):
            result = runner.consult('fixture question')
        self.assertEqual(result['error']['code'], 'timeout')
        self.assertEqual(len(work), 1)
        self.assertFalse(work[0].parent.exists())


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = temporary_test_directory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        for name, value in [('DATA', self.data), ('api_key', ''), ('bridge_token', ''), ('calls', 0), ('client', Mock())]:
            patcher = patch.object(bridge, name, value)
            patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch.dict(os.environ, {'MODEL_BRIDGE_CHILD': ''}, clear=True)
        patcher.start(); self.addCleanup(patcher.stop)
        self.result = runner.parse_events(SUCCESS, 0, [])
        self.consult = patch.object(runner, 'consult', return_value=self.result).start()
        self.addCleanup(patch.stopall)

    def test_modes_history_synthesis_and_provider_isolation(self):
        a = bridge.ask_codex('first', context='background')
        b = bridge.ask_codex('unrelated')
        self.assertNotEqual(a['thread_id'], b['thread_id'])
        self.assertNotEqual(a['thread_id'], 'cli-session-not-bridge-id')
        bridge.ask_codex('critique this', mode='critique', thread_id=a['thread_id'], other_answer='alternative')
        prompt = self.consult.call_args.args[0]
        for text in ('first', 'background', 'Bridge confirmed.', 'alternative'):
            self.assertIn(text, prompt)
        self.assertNotIn('unrelated', prompt)
        bridge.ask_codex('continue', mode='open', thread_id=b['thread_id'])
        self.assertNotIn('first', self.consult.call_args.args[0])
        bridge.save_synthesis(a['thread_id'], 'final synthesis')
        document = json.loads(Path(a['transcript']).with_suffix('.json').read_text())
        self.assertEqual(document['provider'], 'codex')
        self.assertEqual([e['kind'] for e in document['events']], ['request', 'response', 'request', 'response', 'synthesis'])
        with bridge.connect() as con:
            with self.assertRaisesRegex(ValueError, 'different provider'):
                bridge.load_thread(con, a['thread_id'])
            con.execute("INSERT INTO threads(id,messages,provider) VALUES (?,?,?)", ('a'*32, '[]', 'claude'))
        with self.assertRaisesRegex(ValueError, 'different provider'):
            bridge.ask_codex('hello', mode='open', thread_id='a'*32)
        with self.assertRaisesRegex(ValueError, 'different provider'):
            bridge.ask_claude('hello', mode='open', thread_id=a['thread_id'])

    def test_failed_request_saved_history_not_changed(self):
        self.consult.return_value = {'status': 'error', 'error': {'code': 'timeout'}}
        response = bridge.ask_codex('question')
        document = json.loads(Path(response['transcript']).with_suffix('.json').read_text())
        self.assertEqual([e['kind'] for e in document['events']], ['request', 'error'])
        with bridge.connect() as con:
            self.assertEqual(bridge.load_thread(con, response['thread_id'], 'codex'), [])

    def test_request_persisted_before_run(self):
        def consult(*args, **kwargs):
            files = list(self.data.glob('*.json'))
            self.assertEqual(len(files), 1)
            self.assertEqual(json.loads(files[0].read_text())['events'][0]['kind'], 'request')
            return self.result
        self.consult.side_effect = consult
        bridge.ask_codex('hello')

    def test_deadline_includes_bridge_lock_wait(self):
        lock = Mock()
        lock.acquire.return_value = False
        with patch.object(bridge, 'LOCK', lock), patch.object(runner.time, 'monotonic', return_value=100):
            result = bridge.ask_codex('hello')
        self.assertEqual(result['error']['code'], 'timeout')
        lock.acquire.assert_called_once_with(timeout=120)
        lock.release.assert_not_called()
        self.consult.assert_not_called()

    def test_bridge_passes_original_deadline_to_runner(self):
        with patch.object(runner.time, 'monotonic', return_value=100):
            bridge.ask_codex('hello')
        self.assertEqual(self.consult.call_args.kwargs['deadline'], 220)

    def test_code_generation_returns_unexecuted_text_and_records_selection(self):
        code = 'raise RuntimeError("generated code must never execute")'
        self.consult.return_value = {**self.result, 'text': code}
        with patch.object(runner.time, 'monotonic', return_value=100):
            result = bridge.ask_codex('Write Python', context='supplied sources', task='code_generation',
                                     model='capable-model', reasoning_effort='ultra')
        self.assertEqual(result['text'], code)
        self.assertIsNone(result['model'])
        self.assertEqual(result['requested_model'], 'capable-model')
        self.assertEqual(result['requested_reasoning_effort'], 'ultra')
        self.assertEqual(result['timeout_seconds'], 900)
        self.assertEqual(self.consult.call_args.kwargs['deadline'], 1000)
        self.assertEqual(self.consult.call_args.kwargs['timeout_seconds'], 900)
        self.assertIn('return it as text', self.consult.call_args.args[0])
        self.assertIn('supplied sources', self.consult.call_args.args[0])
        doc = json.loads(Path(result['transcript']).with_suffix('.json').read_text())
        request = doc['events'][0]['request']
        self.assertEqual(request['requested_model'], 'capable-model')
        self.assertEqual(request['timeout_seconds'], 900)
        self.assertNotIn('model', request)

    def test_custom_deadline_also_includes_lock_wait(self):
        lock = Mock()
        lock.acquire.return_value = False
        with patch.object(bridge, 'LOCK', lock), patch.object(runner.time, 'monotonic', return_value=100):
            result = bridge.ask_codex('code', task='code_generation', timeout_seconds=1800)
        self.assertEqual(result['error']['code'], 'timeout')
        lock.acquire.assert_called_once_with(timeout=1800)
        self.consult.assert_not_called()

    def test_invalid_options_do_not_consult_or_persist(self):
        for kwargs in ({'task': 'project_edit'}, {'reasoning_effort': 'high'},
                       {'timeout_seconds': True}, {'timeout_seconds': 1801}, {'model': ''}):
            self.assertEqual(bridge.ask_codex('hello', **kwargs)['status'], 'error')
        self.consult.assert_not_called()
        self.assertEqual(list(self.data.iterdir()), [])

    def test_selection_credentials_are_not_persisted(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'private-selection-credential'}):
            result = bridge.ask_codex('hello', model='private-selection-credential')
        self.assertEqual(result['error']['code'], 'credential_in_prompt')
        self.consult.assert_not_called()
        self.assertEqual(list(self.data.glob('*.json')), [])
        with bridge.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM events').fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM threads').fetchone()[0], 0)

    def test_mcp_timeout_validation_rejects_coercion(self):
        for value in (True, '900', 0, 1801, float('nan')):
            with self.assertRaises(Exception):
                asyncio.run(bridge.mcp.call_tool('ask_codex', {'question': 'hello', 'timeout_seconds': value}))
        self.consult.assert_not_called()

    def test_mode_validation_no_child(self):
        for kwargs in ({'mode': 'open'}, {'mode': 'critique', 'other_answer': 'answer'},
                       {'mode': 'independent', 'thread_id': 'a'*32}, {'mode': 'independent', 'other_answer': 'answer'},
                       {'mode': 'critique', 'thread_id': 'a'*32}):
            with self.assertRaises(ValueError): bridge.ask_codex('hello', **kwargs)
        self.consult.assert_not_called()

    def test_recursion_blocks_both_providers_and_startup(self):
        with patch.dict(os.environ, {'MODEL_BRIDGE_CHILD': '1'}):
            self.assertEqual(bridge.ask_codex('hello')['error']['code'], 'recursive_call')
            with self.assertRaises(ValueError): bridge.ask_claude('hello')
            with self.assertRaises(RuntimeError): bridge.initialize()
        self.consult.assert_not_called()

    def test_credentials_never_persisted(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'private-env-credential'}):
            result = bridge.ask_codex('private-env-credential')
            self.assertEqual(result['error']['code'], 'credential_in_prompt')
            self.assertEqual(list(self.data.glob('*.json')), [])
            response = bridge.ask_codex('safe question')
            with self.assertRaises(ValueError): bridge.save_synthesis(response['thread_id'], 'private-env-credential')

    def test_legacy_claude_thread_migration_and_working_claude(self):
        con = sqlite3.connect(self.data / 'threads.sqlite3')
        con.execute('CREATE TABLE threads (id TEXT PRIMARY KEY,messages TEXT NOT NULL)')
        con.execute('INSERT INTO threads VALUES (?,?)', ('a'*32, '[]'))
        con.commit(); con.close()
        response = Mock(model='actual-claude', stop_reason='end_turn')
        block = SimpleNamespace(type='text', text='Claude answer', model_dump=lambda **kw: {'type': 'text', 'text': 'Claude answer'})
        response.content = [block]
        response.usage.model_dump.return_value = {'input_tokens': 1, 'output_tokens': 2}
        response.model_dump.return_value = {'model': 'actual-claude'}
        bridge.client.messages.create.return_value = response
        a = bridge.ask_claude('continue', mode='open', thread_id='a'*32)
        with patch.dict(os.environ, {'CODEX_TIMEOUT_SECONDS': 'invalid'}):
            b = bridge.ask_claude('new question')
        self.assertEqual(a['text'], 'Claude answer')
        self.assertEqual(b['status'], 'ok')
        self.assertEqual(bridge.client.messages.create.call_args.kwargs['max_tokens'], bridge.MAX_TOKENS)
        self.assertNotIn('max_tokens', self.result)
        self.consult.assert_not_called()

    def test_mcp_registration(self):
        tools = asyncio.run(bridge.mcp.list_tools())
        names = {tool.name for tool in tools}
        self.assertTrue({'ask_codex', 'ask_claude', 'bridge_ping', 'save_synthesis'} <= names)
        for tool in tools:
            if tool.name in ('ask_codex', 'ask_claude'):
                self.assertIn('title', tool.inputSchema['properties'])
                self.assertNotIn('title', tool.inputSchema.get('required', []))

    def claude_response(self):
        response = Mock(model='actual-claude', stop_reason='end_turn')
        response.content = [SimpleNamespace(type='text', text='Claude answer',
            model_dump=lambda **kw: {'type': 'text', 'text': 'Claude answer'})]
        response.usage.model_dump.return_value = {'input_tokens': 1, 'output_tokens': 2}
        response.model_dump.return_value = {'model': 'actual-claude'}
        bridge.client.messages.create.return_value = response

    def test_readable_paths_stable_across_followups_synthesis_and_reconnect(self):
        self.claude_response()
        for provider, ask in (('codex', bridge.ask_codex), ('claude', bridge.ask_claude)):
            with patch.object(bridge, 'now', return_value='2026-10-10T13:30:00+00:00'):
                first = ask('RAW PROMPT MUST NOT BE A FILENAME', title='Python helper')
            thread, path = first['thread_id'], Path(first['transcript'])
            self.assertEqual(len(thread), 32)
            self.assertEqual(path.name, f'2026-10-10_09-30-00-0400_{provider}_python-helper_{thread[:8]}.md')
            # A later title and a different date must not rename a thread.
            with patch.object(bridge, 'now', return_value='2026-12-12T15:00:00+00:00'):
                followup = ask('continue', mode='open', thread_id=thread, title='Different title')
                synthesis = bridge.save_synthesis(thread, 'Final answer')
            self.assertEqual(followup['transcript'], str(path))
            self.assertEqual(synthesis['transcript'], str(path))
            with bridge.connect() as con:
                self.assertEqual(bridge.export(con, thread), str(path))
            document = json.loads(path.with_suffix('.json').read_text())
            self.assertEqual(document['thread_id'], thread)
            self.assertEqual(document['title'], 'Python helper')
            self.assertEqual(document['started_at'], '2026-10-10T13:30:00+00:00')
            self.assertEqual(len(document['events']), 5)
            index = (self.data / 'index.md').read_text()
            for text in (thread, provider, 'Python helper', '2026-10-10T09:30:00-04:00', path.name):
                self.assertIn(text, index)
            self.assertNotIn('RAW PROMPT', index)
            self.assertNotIn('Different title', index)

    def test_sanitization_defaults_and_index_escaping(self):
        for title, slug in ((None, 'consultation'), ('', 'consultation'), ('../..\\/?!', 'consultation'),
                            ('你好 🐈', 'consultation'), (' Café / Python: helper! ', 'cafe-python-helper'),
                            ('x'*200, 'x'*40), ('a'*39 + ' / b', 'a'*39)):
            result = bridge.ask_codex('secret prompt', title=title)
            name = Path(result['transcript']).name
            self.assertIn('_codex_' + slug + '_', name)
            self.assertRegex(name, r'^[a-z0-9_-]+\.md$')
            self.assertNotIn('secret', name)
        result = bridge.ask_codex('question', title='[click](evil) | <script> *bold* `code`\nnext')
        index = (self.data / 'index.md').read_text()
        self.assertNotIn('<script>', index)
        self.assertNotIn('[click]', index)
        self.assertIn('&lt;script&gt;', index)
        self.assertIn('&#124;', index)
        self.assertIn('&#96;', index)
        self.assertIn(Path(result['transcript']).name, index)

    def test_title_credentials_and_length_rejected_before_consultation(self):
        self.claude_response()
        for ask in (bridge.ask_codex, bridge.ask_claude):
            for kwargs in ({'title': 'x'*201}, {'title': 123}):
                with self.assertRaises(ValueError): ask('question', **kwargs)
            with patch.object(bridge, 'bridge_token', 'bridge-secret'):
                with self.assertRaises(ValueError): ask('question', title='contains bridge-secret')
            with patch.dict(os.environ, {'OPENAI_API_KEY': 'env-secret'}):
                with self.assertRaises(ValueError): ask('question', title='contains env-secret')
        self.consult.assert_not_called()
        bridge.client.messages.create.assert_not_called()
        self.assertEqual(list(self.data.iterdir()), [])

    def test_short_id_and_existing_file_collisions(self):
        ids = ['abcdef01' + '1'*24, 'abcdef01' + '2'*24, 'abcdef01' + '3'*24]
        with patch.object(bridge, 'now', return_value='2026-01-10T15:00:00+00:00'):
            with bridge.connect() as con:
                for thread in ids[:2]:
                    with patch.object(bridge.uuid, 'uuid4', return_value=SimpleNamespace(hex=thread)):
                        bridge.create_thread(con, 'codex', 'Same title')
                first = bridge.export(con, ids[0])
                second = bridge.export(con, ids[1])
                self.assertTrue(first.endswith('abcdef01.md'))
                self.assertTrue(second.endswith('abcdef012222.md'))
                self.assertIn('10-00-00-0500', first)
                # An untracked file with the next candidate name is preserved.
                occupied = self.data / '2026-01-10_10-00-00-0500_codex_same-title_abcdef013333.json'
                occupied.write_text('do not overwrite')
                with patch.object(bridge.uuid, 'uuid4', return_value=SimpleNamespace(hex=ids[2])):
                    bridge.create_thread(con, 'codex', 'Same title')
                third = bridge.export(con, ids[2])
                self.assertTrue(third.endswith('abcdef0133333333.md'))
                self.assertEqual(occupied.read_text(), 'do not overwrite')
                self.assertEqual(json.loads(Path(first).with_suffix('.json').read_text())['thread_id'], ids[0])

    def test_legacy_files_preserved_and_original_start_migrated(self):
        thread = 'a'*32
        with sqlite3.connect(self.data / 'threads.sqlite3') as con:
            con.execute('CREATE TABLE threads (id TEXT PRIMARY KEY,messages TEXT NOT NULL)')
            con.execute('INSERT INTO threads VALUES (?,?)', (thread, '[]'))
            con.execute('CREATE TABLE events (seq INTEGER PRIMARY KEY,thread TEXT NOT NULL,payload TEXT NOT NULL)')
            con.execute('INSERT INTO events(thread,payload) VALUES (?,?)', (thread, json.dumps({
                'timestamp': '2025-01-10T15:00:00+00:00', 'kind': 'request'})))
        legacy_md = self.data / (thread + '.md')
        legacy_json = self.data / (thread + '.json')
        legacy_md.write_text('original markdown')
        legacy_json.write_text('original json')
        with bridge.connect() as con:
            bridge.export_index(con)
            self.assertEqual(con.execute('SELECT started_at FROM threads').fetchone()[0], '2025-01-10T15:00:00+00:00')
        self.assertEqual(legacy_md.read_text(), 'original markdown')
        self.assertEqual(legacy_json.read_text(), 'original json')
        index = (self.data / 'index.md').read_text()
        self.assertIn('2025-01-10T10:00:00-05:00', index)
        self.assertIn(f'[MD]({thread}.md)', index)
        self.claude_response()
        follow = bridge.ask_claude('continue', mode='open', thread_id=thread, title='New title')
        self.assertEqual(follow['transcript'], str(legacy_md))
        self.assertEqual(bridge.save_synthesis(thread, 'final')['transcript'], str(legacy_md))
        self.assertEqual(len(list(self.data.glob('*.json'))), 1)
        self.assertEqual(json.loads(legacy_json.read_text())['title'], 'Consultation')

    def test_dst_repeated_hour_has_distinct_offsets(self):
        names = []
        for timestamp in ('2026-11-01T05:30:00+00:00', '2026-11-01T06:30:00+00:00'):
            with patch.object(bridge, 'now', return_value=timestamp):
                result = bridge.ask_codex('question', title='DST')
            names.append(Path(result['transcript']).name)
        self.assertIn('_01-30-00-0400_', names[0])
        self.assertIn('_01-30-00-0500_', names[1])

    def test_all_filename_candidates_occupied_fails_without_overwriting(self):
        thread = 'c'*32
        prefix = '2026-01-10_10-00-00-0500_codex_consultation_'
        for length in range(8, 33, 4):
            (self.data / (prefix + thread[:length] + '.md')).write_text('keep me')
        with bridge.connect() as con, patch.object(bridge, 'now', return_value='2026-01-10T15:00:00+00:00'), \
                patch.object(bridge.uuid, 'uuid4', return_value=SimpleNamespace(hex=thread)):
            with self.assertRaisesRegex(ValueError, 'collision'):
                bridge.create_thread(con, 'codex', 'Consultation')
            self.assertEqual(con.execute('SELECT COUNT(*) FROM threads').fetchone()[0], 0)
        for path in self.data.glob('*.md'):
            self.assertEqual(path.read_text(), 'keep me')

    def test_legacy_no_events_uses_file_time_once(self):
        thread = 'b'*32
        with sqlite3.connect(self.data / 'threads.sqlite3') as con:
            con.execute('CREATE TABLE threads (id TEXT PRIMARY KEY,messages TEXT NOT NULL,provider TEXT NOT NULL)')
            con.execute('INSERT INTO threads VALUES (?,?,?)', (thread, '[]', 'codex'))
        path = self.data / (thread + '.md')
        path.write_text('legacy')
        os.utime(path, (0, 0))
        with bridge.connect() as con:
            started = con.execute('SELECT started_at FROM threads').fetchone()[0]
        os.utime(path, (1000, 1000))
        with bridge.connect() as con:
            self.assertEqual(con.execute('SELECT started_at FROM threads').fetchone()[0], started)
        self.assertEqual(started, '1970-01-01T00:00:00+00:00')

    def test_codex_only_startup_without_anthropic_key(self):
        (self.data / 'bridge.token').write_text('b'*32)
        with patch.object(bridge, 'CONFIG', self.data):
            app = bridge.initialize()
        self.assertIsInstance(app, bridge.BearerGate)
        self.assertIsNone(bridge.client)


if __name__ == '__main__':
    unittest.main()
