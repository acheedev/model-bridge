"""Real disposable processes/SQLite/MCP handlers, with no model calls."""
import asyncio
import unittest
from unittest.mock import patch
from scripts.demo_project_lifecycle import run_demo
from model_bridge import codex_runner


class ProjectLifecycleDemoTests(unittest.TestCase):
    def test_registered_cancel_status_result_and_outbound_fixture(self):
        with patch.object(codex_runner, 'subscription_auth', side_effect=AssertionError('No model credentials in demo')):
            report = asyncio.run(run_demo('cancellation'))
        result = report['results'][0]
        self.assertTrue(result['cancelled_state_durable'])
        self.assertTrue(result['worker_and_grandchild_stopped_or_zombie'])
        self.assertTrue(result['outbound_readback'])
        self.assertTrue(result['queued_successor_succeeded'])
        self.assertIn('project_cancel', [call['tool'] for call in result['calls']])

    def test_abrupt_isolated_crash_records_interruption_without_replay(self):
        report = asyncio.run(run_demo('recovery'))
        result = report['results'][0]
        self.assertTrue(result['running_and_queued_interrupted'])
        self.assertTrue(result['partial_file_and_before_status_retained'])
        self.assertFalse(result['automatic_replay'])
        self.assertTrue(result['new_job_accepted_and_succeeded'])
