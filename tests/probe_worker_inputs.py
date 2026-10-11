"""No-model production-launcher probe; argument is an existing terminal job ID."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_bridge import codex_runner
from model_bridge.bridge_paths import approved_path
from model_bridge.file_transfers import TransferStore, valid_id
from model_bridge.project_jobs import JobManager, TERMINAL


def main():
    started = time.monotonic()
    project = approved_path(Path(__file__).resolve().parents[1])
    state = approved_path(project / 'job-data')
    job_id = sys.argv[1]
    valid_id(job_id)
    with sqlite3.connect('file:' + str(approved_path(state / 'jobs.sqlite3')) + '?mode=ro', uri=True) as db:
        assert not db.execute("SELECT 1 FROM jobs WHERE state IN ('queued','running')").fetchone(), 'Supervisor must be idle'
        job = json.loads(db.execute('SELECT data FROM jobs WHERE id=?', (job_id,)).fetchone()[0])
    assert job['state'] in TERMINAL
    # Read-only store access: avoid constructor recovery, chmod, or supervisor startup.
    store = object.__new__(TransferStore)
    store.roots = {name: approved_path(Path('/home/jachee/projects/mcp-' + name))
                   for name in ('inbound', 'outbound')}
    store.secrets_provider = lambda: ()
    manager = object.__new__(JobManager)
    manager.state_dir, manager.transfers = state, store
    originals = []
    for receipt in job['inbound_transfers']:
        for entry in receipt['files']:
            originals.extend((store.roots['inbound'] / receipt['transfer_id'] / entry['filename'],
                              state / job_id / 'inputs' / receipt['transfer_id'] / entry['filename']))
    originals = [approved_path(p) for p in originals if p.exists()]
    before = {str(p): (p.stat().st_uid, p.stat().st_gid, p.stat().st_mode,
                        hashlib.sha256(p.read_bytes()).hexdigest()) for p in originals}
    with tempfile.TemporaryDirectory(dir=approved_path(project / '.tmp'), prefix='input-mount-probe-') as temporary:
        temp = Path(temporary)
        home = temp / 'home'
        home.mkdir(mode=0o700)
        other = approved_path(state / uuid.uuid4().hex)
        other.mkdir(mode=0o700)
        canary = other / 'private.txt'
        canary.write_bytes(b'other-job-private-canary')
        try:
            with manager.input_workspace(project) as inputs:
                manager.materialize_inputs(job, inputs)
                expected = [{'path': str(inputs / receipt['transfer_id'] / entry['filename']),
                             'sha256': entry['sha256'], 'size_bytes': entry['size_bytes']}
                            for receipt in job['inbound_transfers'] for entry in receipt['files']]
                probe = temp / 'inside.py'
                probe.write_text('''import hashlib,json,os,pathlib
expected = ''' + repr(expected) + '''
report={'euid':os.geteuid(),'egid':os.getegid(),'groups':os.getgroups(),'files':[]}
for entry in expected:
    path=pathlib.Path(entry['path'])
    data=path.read_bytes()
    result={'filename':path.name,'readable':True,'hash_matches':hashlib.sha256(data).hexdigest()==entry['sha256'],'size_matches':len(data)==entry['size_bytes']}
    try:
        fd=os.open(path,os.O_WRONLY|os.O_APPEND);os.close(fd);result['write_denied']=False
    except OSError:result['write_denied']=True
    report['files'].append(result)
report['private_reads_denied']=[]
for path in ''' + repr([str(canary), str(state / job_id / 'launch.json'), str(state / 'jobs.sqlite3')]) + ''':
    try:
        fd=os.open(path,os.O_RDONLY);os.close(fd);denied=False
    except OSError:denied=True
    report['private_reads_denied'].append({'path':path,'denied':denied})
try:
    os.listdir(''' + repr(str(state)) + ''');report['state_listing_denied']=False
except OSError:report['state_listing_denied']=True
report['mounts']=[line.strip() for line in pathlib.Path('/proc/self/mountinfo').read_text().splitlines() if '.worker-inputs' in line or 'job-data' in line]
print(json.dumps(report))
''')
                argv = [codex_runner.executable(), '--no-daemon']
                for setting in manager.worker_settings(project, state / job_id):
                    argv += ['-c', setting]
                argv += ['sandbox', '--permission-profile', 'bridge-worker', '--cd', str(project), '/usr/bin/python3', str(probe)]
                env = {k: os.environ[k] for k in ('PATH', 'LANG', 'LC_ALL', 'SSL_CERT_FILE', 'SSL_CERT_DIR') if k in os.environ}
                env.update(HOME=str(temp), CODEX_HOME=str(home), TMPDIR=str(project / '.tmp'),
                           MODEL_BRIDGE_CHILD='1', PROJECT_WORKER_CHILD='1')
                launch = temp / 'launch.json'
                launch.write_text(json.dumps({'project': str(project), 'limits': {'memory_mb': 2048, 'cpu_seconds': 30},
                                              'argv': argv, 'environment': env}))
                parent = os.environ.copy()
                for marker in ('MODEL_BRIDGE_CHILD', 'PROJECT_WORKER_CHILD'):
                    parent.pop(marker, None)
                run = subprocess.run([sys.executable, str(project / 'model_bridge' / 'project_worker.py'), str(launch)],
                                     env=parent, capture_output=True, text=True, timeout=30, start_new_session=True)
                assert run.returncode == 0, run.stderr[:1000]
                report = json.loads(run.stdout)
                assert len(report['files']) == 2
                assert all(all(f[k] for k in ('readable', 'hash_matches', 'size_matches', 'write_denied')) for f in report['files'])
                assert all(f['denied'] for f in report['private_reads_denied'])
                assert report['state_listing_denied']
        finally:
            canary.unlink()
            other.rmdir()
    assert before == {str(p): (p.stat().st_uid, p.stat().st_gid, p.stat().st_mode,
                               hashlib.sha256(p.read_bytes()).hexdigest()) for p in originals}
    assert not list((project / '.worker-inputs').iterdir())
    report.update(existing_inputs_unchanged=True, cleanup_passed=True,
                  probe_seconds=time.monotonic()-started,
                  validation_completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    approved_path(project / 'logs/input-mount-repair.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
