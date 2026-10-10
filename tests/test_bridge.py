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

import claude_bridge as bridge
import codex_runner as runner


def jsonl(*events):
    return '\n'.join(json.dumps(event) for event in events)


SUCCESS = jsonl(
    {'type': 'thread.started', 'thread_id': 'cli-session-not-bridge-id'},
    {'type': 'item.completed', 'item': {'id': 'item_0', 'type': 'agent_message', 'text': 'Bridge confirmed.'}},
    {'type': 'turn.completed', 'usage': {'input_tokens': 12, 'cached_input_tokens': 3, 'output_tokens': 4}},
)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        (self.home / 'auth.json').write_text(json.dumps({'auth_mode': 'chatgpt', 'OPENAI_API_KEY': None,
            'tokens': {'access_token': 'private-access-credential', 'refresh_token': 'private-refresh-credential'}}))
        self.env = patch.dict(os.environ, {'CODEX_HOME': str(self.home), 'CODEX_BIN': '/mock/codex',
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
        processes[-1].communicate.assert_called_once_with(input='user prompt with $(shell syntax)', timeout=120)
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

    def test_recursion_and_credentials_in_prompt(self):
        with patch.object(runner.subprocess, 'Popen') as spawn:
            with patch.dict(os.environ, {'MODEL_BRIDGE_CHILD': '1'}):
                self.assertEqual(runner.consult('hello')['error']['code'], 'recursive_call')
            self.assertEqual(runner.consult('private-access-credential')['error']['code'], 'credential_in_prompt')
            spawn.assert_not_called()
        self.assertFalse(runner.prompt_is_safe('private-refresh-credential'))

    def test_refresh_saved_privately_and_concurrent_login_preserved(self):
        original = runner.subscription_auth()
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            refreshed = {**original, 'tokens': {'access_token': 'new-private-token'}, 'last_refresh': 'now'}
            (home / 'auth.json').write_text(json.dumps(refreshed))
            runner.persist_auth_refresh(home, original)
            self.assertEqual(runner.subscription_auth()['tokens'], refreshed['tokens'])
            self.assertEqual((self.home / 'auth.json').stat().st_mode & 0o777, 0o600)
            concurrent = {'auth_mode': 'chatgpt', 'tokens': {'access_token': 'concurrent-login'}}
            (self.home / 'auth.json').write_text(json.dumps(concurrent))
            runner.persist_auth_refresh(home, original)
            self.assertEqual(runner.subscription_auth(), concurrent)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
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
        document = json.loads((self.data / (a['thread_id']+'.json')).read_text())
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
        def consult(*args):
            files = list(self.data.glob('*.json'))
            self.assertEqual(len(files), 1)
            self.assertEqual(json.loads(files[0].read_text())['events'][0]['kind'], 'request')
            return self.result
        self.consult.side_effect = consult
        bridge.ask_codex('hello')

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
        b = bridge.ask_claude('new question')
        self.assertEqual(a['text'], 'Claude answer')
        self.assertEqual(b['status'], 'ok')
        self.assertEqual(bridge.client.messages.create.call_args.kwargs['max_tokens'], bridge.MAX_TOKENS)
        self.assertNotIn('max_tokens', self.result)
        self.consult.assert_not_called()

    def test_mcp_registration(self):
        names = {tool.name for tool in asyncio.run(bridge.mcp.list_tools())}
        self.assertTrue({'ask_codex', 'ask_claude', 'bridge_ping', 'save_synthesis'} <= names)

    def test_codex_only_startup_without_anthropic_key(self):
        (self.data / 'bridge.token').write_text('b'*32)
        with patch.object(bridge, 'CONFIG', self.data):
            app = bridge.initialize()
        self.assertIsInstance(app, bridge.BearerGate)
        self.assertIsNone(bridge.client)


if __name__ == '__main__':
    unittest.main()
