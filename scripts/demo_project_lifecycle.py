"""Disposable non-model MCP cancellation/recovery demo; never uses installed service."""
import argparse
import asyncio
import base64
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from mcp.server.fastmcp import FastMCP
from model_bridge import codex_runner
from model_bridge.bridge_runtime import register_tools
from model_bridge.file_transfers import TransferStore
from model_bridge.project_jobs import JobManager

AUTHORITY = {'edit': True, 'test': True, 'commit': False, 'push': False}
WORKER = r"""import json,os,pathlib,subprocess,sys,time
prompt=json.load(sys.stdin)
p=pathlib.Path.cwd()
if prompt['assignment']=='fixture-tree':
 child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])
 (p/'partial.txt').write_text('fixture checkpoint retained')
 (p/'pids.json').write_text(json.dumps({'worker':os.getpid(),'grandchild':child.pid}))
 print('fixture started',flush=True)
 time.sleep(30)
else:
 (p/'artifact.txt').write_text('fixture success')
 pathlib.Path(os.environ['PROJECT_JOB_RESULT']).write_text(json.dumps({
  'completed':True,'summary':'non-model fixture',
  'acceptance_results':[{'criterion':c,'passed':True,'details':'fixture passed'} for c in prompt['acceptance_criteria']],
  'artifact_paths':['artifact.txt']}))
 print('fixture complete',flush=True)
"""


def refuse_worker_context():
    if os.environ.get('MODEL_BRIDGE_CHILD') or os.environ.get('PROJECT_WORKER_CHILD'):
        raise RuntimeError('Run this demo directly in Ubuntu, never inside a project worker.')


def stopped(pid):
    path = Path(f'/proc/{pid}/stat')
    try:
        return path.read_text().rsplit(')', 1)[1].split()[0] == 'Z'
    except FileNotFoundError:
        return True


def stop_fixture_group(root, pid):
    """Cleanup only a worker whose argv identifies this disposable fixture."""
    if stopped(pid):
        return
    argv = Path(f'/proc/{pid}/cmdline').read_bytes()
    if str(root / 'worker.py').encode() not in argv or os.getpgid(pid) != pid:
        raise RuntimeError('Refusing to signal a process outside the fixture group.')
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            break


class Lab:
    def __enter__(self):
        refuse_worker_context()
        self.temp = tempfile.TemporaryDirectory(prefix='lifecycle-demo-', dir=codex_runner.temporary_root())
        self.root = Path(self.temp.name)
        self.project = self.root / 'project'
        self.project.mkdir()
        (self.project / 'unrelated.txt').write_text('caller-owned fixture')
        subprocess.run(['git', 'init', '-q', str(self.project)], check=True)
        (self.root / 'worker.py').write_text(WORKER)
        self.store = TransferStore(self.root / 'inbound', self.root / 'outbound')
        self.manager = None
        self.calls = []
        self.runtime = SimpleNamespace(transfers=self.store, jobs=None)
        self.mcp = FastMCP('disposable-project-lifecycle-demo')
        register_tools(self.mcp, lambda: self.runtime)
        self.open_manager()
        return self

    def open_manager(self, start=False):
        self.manager = JobManager(self.store, state_dir=self.root / 'state',
                                  projects={'model-bridge': self.project},
                                  secrets_provider=lambda: (),
                                  command_factory=lambda *args: [sys.executable, str(self.root / 'worker.py')],
                                  start=start, available_memory=lambda:0)
        self.runtime.jobs = self.manager

    def close_manager(self):
        if self.manager is not None:
            self.manager.close()
            self.manager = None
            self.runtime.jobs = None

    async def tool(self, name, arguments):
        response = await self.mcp.call_tool(name, arguments)
        blocks = response[0] if isinstance(response, tuple) else response
        result = json.loads(next(block.text for block in blocks if hasattr(block, 'text')))
        if result.get('status') != 'ok':
            raise RuntimeError('Fixture tool failed: ' + name + ' ' + json.dumps(result))
        self.calls.append({'tool': name, 'job_id': result.get('job_id'), 'state': result.get('state')})
        return result

    async def submit(self, assignment):
        return (await self.tool('project_submit', {
            'assignment': assignment, 'acceptance_criteria': ['fixture completed'],
            'project_id': 'model-bridge', 'authority': AUTHORITY,
            'target_paths': ['partial.txt','pids.json','artifact.txt'], 'deadline_seconds': 20, 'memory_mb': 2048, 'cpu_seconds': 300}))['job_id']

    async def until(self, predicate, seconds=5):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                return
            await asyncio.sleep(.02)
        raise AssertionError('Disposable fixture did not reach its checkpoint.')

    def __exit__(self, *args):
        self.close_manager()
        for pids in (self.root / 'state').glob('*/workspace/pids.json'):
            stop_fixture_group(self.root, json.loads(pids.read_text())['worker'])
        self.temp.cleanup()


async def cancellation():
    with Lab() as lab:
        lab.close_manager()
        lab.open_manager(start=True)
        running = await lab.submit('fixture-tree')
        stage = lab.root / 'state' / running / 'workspace'
        await lab.until(lambda: (stage / 'pids.json').exists())
        pids = json.loads((stage / 'pids.json').read_text())
        assert not stopped(pids['worker']) and not stopped(pids['grandchild'])
        queued = await lab.submit('fixture-success')
        assert (await lab.tool('project_status', {'job_id': queued}))['state'] == 'queued'
        await lab.tool('project_cancel', {'job_id': running})
        await lab.until(lambda: lab.manager.get(running)['state'] == 'cancelled')
        status = await lab.tool('project_status', {'job_id': running})
        result = await lab.tool('project_result', {'job_id': running})
        assert status['cancel_requested_at'] and result['worker_stopped_at']
        await lab.until(lambda: all(stopped(pid) for pid in pids.values()))
        assert (stage / 'partial.txt').read_text() == 'fixture checkpoint retained'
        assert (lab.project / 'unrelated.txt').read_text() == 'caller-owned fixture'
        manifest = await lab.tool('transfer_manifest', {'direction': 'outbound', 'transfer_id': result['outbound_transfer_id']})
        readback = await lab.tool('transfer_read', {'direction': 'outbound', 'transfer_id': result['outbound_transfer_id'], 'filename': 'job-result.json'})
        decoded = base64.b64decode(readback['content_base64'], validate=True)
        receipt = next(item for item in manifest['files'] if item['filename'] == 'job-result.json')
        assert len(decoded) == receipt['size_bytes'] and hashlib.sha256(decoded).hexdigest() == receipt['sha256']
        published = json.loads(decoded)
        assert published['state'] == 'cancelled' and published['job_id'] == running
        assert (await lab.tool('project_cancel', {'job_id': running}))['state'] == 'cancelled'
        await lab.until(lambda: lab.manager.get(queued)['state'] == 'succeeded')
        lab.close_manager()
        lab.open_manager()
        assert lab.manager.get(running)['state'] == 'cancelled'
        assert lab.manager.get(queued)['state'] == 'succeeded'
        return {'scenario': 'cancellation', 'cancelled_state_durable': True,
                'worker_and_grandchild_stopped_or_zombie': True, 'partial_file_retained': True,
                'unrelated_fixture_preserved': True, 'outbound_readback': True,
                'queued_successor_succeeded': True, 'calls': lab.calls}


def crash_supervisor(root):
    refuse_worker_context()
    root = Path(root)
    if root.parent.resolve() != codex_runner.temporary_root() or not root.name.startswith('lifecycle-demo-') or root.is_symlink():
        raise RuntimeError('Crash demo requires its disposable project temp root.')
    store = TransferStore(root / 'inbound', root / 'outbound')
    manager = JobManager(store, state_dir=root / 'state', projects={'model-bridge': root / 'project'},
                         command_factory=lambda *args: [sys.executable, str(root / 'worker.py')], start=True, available_memory=lambda:0)
    args = (['fixture completed'], 'model-bridge', AUTHORITY)
    running = manager.submit('fixture-tree', *args, deadline_seconds=20,target_paths=['partial.txt','pids.json','artifact.txt'])['job_id']
    queued = manager.submit('fixture-success', *args, deadline_seconds=20,target_paths=['partial.txt','pids.json','artifact.txt'])['job_id']
    stage = root / 'state' / running / 'workspace'
    deadline = time.monotonic() + 5
    while not (stage / 'pids.json').exists() and time.monotonic() < deadline:
        time.sleep(.02)
    assert manager.get(running)['state'] == 'running' and manager.get(queued)['state'] == 'queued'
    pids = json.loads((stage / 'pids.json').read_text())
    (root / 'crash-record.json').write_text(json.dumps({'running': running, 'queued': queued, 'pids': pids}))
    os._exit(0)  # Deliberately bypass close/finally to simulate only this supervisor crash.


async def recovery():
    with Lab() as lab:
        lab.close_manager()
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--crash-supervisor', str(lab.root)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            assert child.wait(timeout=8) == 0
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
        record = json.loads((lab.root / 'crash-record.json').read_text())
        stop_fixture_group(lab.root, record['pids']['worker'])
        await lab.until(lambda: all(stopped(pid) for pid in record['pids'].values()))
        lab.open_manager()
        for key in ('running', 'queued'):
            result = await lab.tool('project_result', {'job_id': record[key]})
            assert result['state'] == 'interrupted' and result['error'] == 'service_restart'
            assert result['interruption_detected_at'] and result['last_activity_at']
            assert result['finished_at'] is None and result['worker_stopped_at'] is None
        assert lab.manager.get(record['running'])['working_tree_before'] is not None
        stage = lab.root / 'state' / record['running'] / 'workspace'
        assert (stage / 'partial.txt').read_text() == 'fixture checkpoint retained'
        assert not lab.manager.run_once()  # Neither interrupted job was queued/replayed.
        next_job = await lab.submit('fixture-success')
        assert lab.manager.run_once()
        assert (await lab.tool('project_result', {'job_id': next_job}))['state'] == 'succeeded'
        return {'scenario': 'isolated_crash_recovery', 'running_and_queued_interrupted': True,
                'exact_stop_time_unknown': True, 'partial_file_and_before_status_retained': True,
                'automatic_replay': False, 'new_job_accepted_and_succeeded': True, 'calls': lab.calls}


async def run_demo(scenario='all'):
    started = datetime.now(ZoneInfo('America/New_York'))
    clock = time.monotonic()
    results = []
    if scenario in ('all', 'cancellation'):
        results.append(await cancellation())
    if scenario in ('all', 'recovery'):
        results.append(await recovery())
    return {'status': 'ok', 'scope': 'disposable non-model registered-handler demo; not installed-service proof',
            'started_at': started.isoformat(), 'completed_at': datetime.now(ZoneInfo('America/New_York')).isoformat(),
            'elapsed_seconds': round(time.monotonic() - clock, 6), 'measurement': 'monotonic demo wall time',
            'results': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=('all', 'cancellation', 'recovery'), default='all')
    parser.add_argument('--crash-supervisor', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.crash_supervisor:
        crash_supervisor(args.crash_supervisor)
    else:
        print(json.dumps(asyncio.run(run_demo(args.scenario)), indent=2))
