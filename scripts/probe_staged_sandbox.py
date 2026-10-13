"""No-model installed CLI/production-launcher proof using disposable canaries."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_bridge import codex_runner
from model_bridge.bridge_paths import approved_path
from model_bridge.project_jobs import JobManager


def main():
    root = approved_path(Path(__file__).resolve().parents[1])
    scratch = approved_path(root / '.tmp')
    scratch.mkdir(mode=0o700, exist_ok=True)
    report_path = approved_path(scratch / 'staged-sandbox-proof-2026-10-13.json')
    started = datetime.now(timezone.utc).isoformat()
    clock = time.monotonic()
    report = {'started_at_utc': started, 'outcome': 'running', 'model_calls': 0}
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    state = approved_path(root / 'job-data')
    job = approved_path(state / uuid.uuid4().hex)
    other = approved_path(state / uuid.uuid4().hex)
    job.mkdir(mode=0o700)
    other.mkdir(mode=0o700)
    try:
        with tempfile.TemporaryDirectory(dir=scratch, prefix='sandbox-canary-') as temp:
            live = Path(temp)
            (live / 'private.txt').write_text('synthetic-live-canary')
            stage = job / 'workspace'
            stage.mkdir(mode=0o700)
            (stage / '.tmp').mkdir(mode=0o700)
            inputs = job / 'inputs'
            inputs.mkdir(mode=0o700)
            (inputs / 'reference.txt').write_text('synthetic-reference')
            home = job / 'home'
            home.mkdir(mode=0o700)
            (home / 'private.txt').write_text('synthetic-home-canary')
            (other / 'private.txt').write_text('synthetic-other-job-canary')
            (job / 'private.txt').write_text('synthetic-job-metadata')
            forbidden_reads = [live / 'private.txt', home / 'private.txt',
                               other / 'private.txt', job / 'private.txt', state / 'jobs.sqlite3']
            forbidden_writes = [live / 'unexpected-write', home / 'unexpected-write',
                                other / 'unexpected-write', job / 'unexpected-write',
                                inputs / 'unexpected-write']
            probe = stage / 'inside.py'
            probe.write_text("""import json,os,pathlib
root=pathlib.Path.cwd()
(root/'stage-write').write_text('allowed')
(root/'.tmp'/'scratch-write').write_text('allowed')
checks={'stage_write':True,'scratch_write':True,
        'inputs_read':pathlib.Path(INPUT).read_text()=='synthetic-reference'}
checks['private_reads_denied']=[]
for path in READS:
    try:
        fd=os.open(path,os.O_RDONLY);os.close(fd);denied=False
    except OSError:denied=True
    checks['private_reads_denied'].append({'path':path,'denied':denied})
checks['private_writes_denied']=[]
for path in WRITES:
    try:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd);denied=False
    except OSError:denied=True
    checks['private_writes_denied'].append({'path':path,'denied':denied})
print(json.dumps(checks))
""".replace('INPUT', repr(str(inputs / 'reference.txt')))
   .replace('READS', repr([str(p) for p in forbidden_reads]))
   .replace('WRITES', repr([str(p) for p in forbidden_writes])))
            binary = os.environ.get('CODEX_BIN') or codex_runner.executable()
            manager = object.__new__(JobManager)
            manager.projects, manager.state_dir = {'model-bridge': root}, state
            with patch.object(codex_runner, 'executable', return_value=binary):
                settings = manager.worker_settings(stage, job)
            argv = [binary, '--no-daemon']
            for setting in settings:
                argv += ['-c', setting]
            argv += ['sandbox', '--permission-profile', 'bridge-worker', '--cd',
                     str(stage), '/usr/bin/python3', str(probe)]
            env = {k: os.environ[k] for k in ('PATH', 'LANG', 'LC_ALL') if k in os.environ}
            env.update(HOME=str(job), CODEX_HOME=str(home), TMPDIR=str(stage / '.tmp'),
                       MODEL_BRIDGE_CHILD='1', PROJECT_WORKER_CHILD='1')
            launch = job / 'launch.json'
            launch.write_text(json.dumps({'project': str(stage), 'argv': argv,
                'environment': env, 'limits': {'memory_mb': 2048, 'cpu_seconds': 30}}))
            parent = dict(os.environ)
            parent.pop('MODEL_BRIDGE_CHILD', None)
            parent.pop('PROJECT_WORKER_CHILD', None)
            run = subprocess.run([sys.executable, str(root / 'model_bridge/project_worker.py'),
                                  str(launch)], env=parent, capture_output=True,
                                  text=True, timeout=30, start_new_session=True)
            report.update(exit_code=run.returncode, stderr=run.stderr)
            assert run.returncode == 0, run.stderr
            checks = json.loads(run.stdout)
            report['checks'] = checks
            assert checks['stage_write'] and checks['scratch_write'] and checks['inputs_read']
            assert all(item['denied'] for item in checks['private_reads_denied'])
            # bwrap synthesizes ancestor directories to mount the allowed stage.
            # The synthetic job parent can accept ephemeral files, but never
            # maps them to the real metadata directory. Check the host as well.
            assert all(item['denied'] for item in checks['private_writes_denied']
                       if Path(item['path']).parent != job)
            checks['host_private_writes_absent'] = all(not p.exists() for p in forbidden_writes)
            assert checks['host_private_writes_absent']
            assert (inputs / 'reference.txt').read_text() == 'synthetic-reference'
            report['outcome'] = 'completed'
    except Exception as error:
        report.update(outcome='failed', error=str(error))
        raise
    finally:
        shutil.rmtree(job)
        shutil.rmtree(other)
        report.update(finished_at_utc=datetime.now(timezone.utc).isoformat(),
                      seconds=time.monotonic() - clock, duration_clock='monotonic')
        report_path.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
