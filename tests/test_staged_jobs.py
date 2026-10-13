"""Disposable end-to-end pilot proofs; no credentials or model requests."""
import asyncio
import errno
import json
import os
import shutil
import signal
import stat
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from mcp.server.fastmcp import FastMCP
from model_bridge import codex_runner, project_jobs as jobs, staged_work as stage
from model_bridge.bridge_runtime import register_tools
from model_bridge.file_transfers import TransferStore

AUTH = {'edit': True, 'test': True, 'commit': False, 'push': False}
APPLY = {'apply': True, 'test': False, 'commit': False, 'push': False}
WORKER = r"""import json,os,pathlib,sys,time
p=json.load(sys.stdin);root=pathlib.Path.cwd()
if p['assignment']=='runtime':
 home=pathlib.Path(os.environ['CODEX_HOME'])
 (home/'runtime-data').write_text('counted runtime data')
 (home/'helper-link').symlink_to(home/'runtime-data')
 os.mkfifo(home/'runtime-pipe')
 time.sleep(1.2)
if p['assignment']=='unsafe-storage':
 (root/'unsafe-link').symlink_to(root/'a.txt')
 time.sleep(1.2)
if p['assignment'].startswith('hold'):
 (root/'.tmp'/'ready').write_text(str(os.getpid()))
 while not (root/'.tmp'/'release').exists():time.sleep(.02)
if p['assignment']=='partial':
 (root/'a.txt').write_text('partial')
 sys.exit(9)
if p['assignment']=='undeclared':(root/'outside.txt').write_text('bad')
(root/'a.txt').write_text('new text')
if p['assignment']=='bundle':
 (root/'b.txt').unlink()
 (root/'c.txt').write_text('added text\n')
(root/'.tmp'/'scratch').write_text('temporary fixture')
pathlib.Path(os.environ['PROJECT_JOB_RESULT']).write_text(json.dumps({
 'completed':True,'summary':'non-model proof',
 'acceptance_results':[{'criterion':c,'passed':True,'details':'fixture'} for c in p['acceptance_criteria']],
 'artifact_paths':[]}))
print('fixture done')
"""

class StagedJobTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=codex_runner.temporary_root(),prefix='stage-test-')
        self.root=Path(self.temp.name);self.project=self.root/'repo';self.project.mkdir()
        (self.project/'a.txt').write_text('old text')
        (self.project/'b.txt').write_text('delete me\n')
        (self.project/'unrelated.txt').write_text('caller work')
        (self.root/'worker.py').write_text(WORKER)
        self.store=TransferStore(self.root/'inbound',self.root/'outbound')
        self.memory=6*1024**3
        self.manager=self.open_manager()
        self.addCleanup(self.cleanup)

    def open_manager(self):
        return jobs.JobManager(self.store,state_dir=self.root/'state',projects={'model-bridge':self.project},
               command_factory=lambda *args:[sys.executable,str(self.root/'worker.py')],
               available_memory=lambda:self.memory,start=False)

    def cleanup(self):
        self.manager.close()
        self.temp.cleanup()

    def submit(self,assignment='success',**kwargs):
        kwargs.setdefault('target_paths',['a.txt','b.txt','c.txt'])
        return self.manager.submit(assignment,['done'],'model-bridge',AUTH,**kwargs)['job_id']

    def stage(self,job):
        return self.root/'state'/job/'workspace'

    def wait(self,predicate):
        until=time.monotonic()+5
        while not predicate() and time.monotonic()<until:time.sleep(.02)
        self.assertTrue(predicate())

    def complete(self,assignment='bundle',**kwargs):
        job=self.submit(assignment,**kwargs)
        self.assertTrue(self.manager.run_once())
        value=self.manager.get(job)
        self.assertEqual(value['state'],'succeeded',value.get('error'))
        return value

    def apply(self,job):
        return self.manager.apply(job['job_id'],job['bundle_hash'],job['base_hash'],APPLY)

    def test_clean_bundle_diff_apply_and_duplicate_preserve_unrelated_work(self):
        job=self.complete()
        self.assertEqual((self.project/'a.txt').read_text(),'old text')
        self.assertTrue((self.project/'b.txt').exists())
        self.assertFalse((self.project/'c.txt').exists())
        manifest,files=self.store.load('outbound',job['outbound_transfer_id'])
        files=dict(files)
        self.assertIn(b'\\ No newline at end of file',files['changes.diff'])
        check=subprocess.run(['patch','--dry-run','-p1'],cwd=self.project,input=files['changes.diff'],capture_output=True)
        self.assertEqual(check.returncode,0,check.stdout+check.stderr)
        receipt=self.apply(job)
        self.assertEqual(receipt['state'],'applied')
        self.assertEqual((self.project/'a.txt').read_text(),'new text')
        self.assertFalse((self.project/'b.txt').exists())
        self.assertEqual((self.project/'c.txt').read_text(),'added text\n')
        self.assertEqual((self.project/'unrelated.txt').read_text(),'caller work')
        (self.project/'a.txt').write_text('later caller work')
        self.assertEqual(self.apply(job),receipt)
        self.assertEqual((self.project/'a.txt').read_text(),'later caller work')

    def test_whole_bundle_preflight_refuses_changed_deleted_and_existing_addition(self):
        job=self.complete()
        for action in ('edit','delete','addition'):
            with self.subTest(action=action):
                if action=='edit':(self.project/'b.txt').write_text('caller edit')
                elif action=='delete':(self.project/'b.txt').unlink()
                else:(self.project/'c.txt').write_text('caller addition')
                with self.assertRaises(jobs.JobError):self.apply(job)
                self.assertEqual((self.project/'a.txt').read_text(),'old text')
                (self.project/'b.txt').write_text('delete me\n')
                (self.project/'c.txt').unlink(missing_ok=True)

    def test_tampered_outbound_and_wrong_hash_refuse_before_writes(self):
        job=self.complete()
        with self.assertRaises(jobs.JobError):
            self.manager.apply(job['job_id'],'0'*64,job['base_hash'],APPLY)
        path=self.root/'outbound'/job['outbound_transfer_id']/'after-0.txt'
        path.write_bytes(b'tampered')
        with self.assertRaises((ValueError,OSError)):self.apply(job)
        self.assertEqual((self.project/'a.txt').read_text(),'old text')

    def test_symlink_hardlink_traversal_and_repo_boundary_refused(self):
        outside=self.root/'external';outside.mkdir();(outside/'x.txt').write_text('protected')
        (self.project/'linked').symlink_to(outside,target_is_directory=True)
        for paths in (['../external/x.txt'],['linked/x.txt'],['private/auth.json'],['/etc/passwd']):
            with self.subTest(paths=paths),self.assertRaises((ValueError,OSError)):self.submit(target_paths=paths)
        os.link(self.project/'a.txt',self.project/'hard.txt')
        with self.assertRaises(ValueError):self.submit(target_paths=['hard.txt'])
        (self.project/'hard.txt').unlink()
        job=self.complete()
        (self.project/'a.txt').unlink();(self.project/'a.txt').symlink_to(outside/'x.txt')
        with self.assertRaises((ValueError,OSError)):self.apply(job)
        self.assertEqual((outside/'x.txt').read_text(),'protected')
        with self.assertRaises(ValueError):stage.repo_root('/home/jachee/projects/mcp-inbound')

    def test_parent_swap_refuses_without_touching_outside(self):
        folder=self.project/'folder';folder.mkdir();(folder/'a.txt').write_text('old text')
        # Use a completed root-file bundle, then swap the entire repo ancestor.
        job=self.complete()
        parked=self.root/'parked';self.project.rename(parked)
        external=self.root/'external';external.mkdir();(external/'a.txt').write_text('protected')
        self.project.symlink_to(external,target_is_directory=True)
        with self.assertRaises((ValueError,OSError)):self.apply(job)
        self.assertEqual((external/'a.txt').read_text(),'protected')
        self.project.unlink();parked.rename(self.project)

    def test_queued_stale_base_and_undeclared_stage_changes_fail_without_live_edits(self):
        job=self.submit();(self.project/'a.txt').write_text('new caller work')
        self.manager.run_once()
        self.assertEqual(self.manager.get(job)['error'],'stale_base_before_launch')
        self.assertEqual(self.manager.get(job)['attempts'],[])
        job=self.submit('undeclared');self.manager.run_once()
        self.assertEqual(self.manager.get(job)['error'],'undeclared_stage_changes')
        self.assertEqual((self.project/'a.txt').read_text(),'new caller work')
        self.assertFalse((self.project/'outside.txt').exists())

    def test_crash_between_apply_operations_records_partial_and_never_replays(self):
        job=self.complete()
        original=jobs.private_json
        def interrupted(path,value):
            original(path,value)
            if path.name=='apply-receipt.json' and value.get('state')=='applying' and value.get('completed_paths')==['a.txt']:
                raise OSError('fixture interruption')
        with patch.object(jobs,'private_json',side_effect=interrupted):
            with self.assertRaises(OSError):self.apply(job)
        receipt=json.loads((self.root/'state'/job['job_id']/'apply-receipt.json').read_text())
        self.assertEqual(receipt['state'],'partial')
        self.assertEqual((self.project/'a.txt').read_text(),'new text')
        self.assertTrue((self.project/'b.txt').exists())
        self.manager.close();self.manager=self.open_manager()
        with self.assertRaises(jobs.JobError):self.apply(job)
        self.assertTrue((self.project/'b.txt').exists())

    def test_two_workers_really_overlap_memory_gate_and_cancel_independence(self):
        one=self.submit('hold-one');two=self.submit('hold-two')
        self.manager.run_once(background=True)
        self.wait(lambda:(self.stage(one)/'.tmp'/'ready').exists())
        self.memory=0
        self.assertFalse(self.manager.run_once(background=True))
        self.assertEqual(self.manager.get(two)['state'],'queued')
        self.memory=6*1024**3
        self.assertTrue(self.manager.run_once(background=True))
        self.wait(lambda:(self.stage(two)/'.tmp'/'ready').exists())
        self.assertEqual(len(self.manager.active),2)
        self.assertTrue(all(self.manager.get(job)['state']=='running' for job in (one,two)))
        self.assertNotEqual(self.manager.get(one)['attempts'][0]['pid'],self.manager.get(two)['attempts'][0]['pid'])
        self.manager.cancel(one)
        self.wait(lambda:self.manager.get(one)['state']=='cancelled')
        self.assertEqual(self.manager.get(two)['state'],'running')
        (self.stage(two)/'.tmp'/'release').write_text('go')
        self.wait(lambda:self.manager.get(two)['state']=='succeeded')
        self.assertEqual((self.project/'a.txt').read_text(),'old text')

    def test_retry_only_never_launched_transient_then_success_with_real_backoff(self):
        original=jobs.subprocess.Popen;calls=[]
        def launch(*args,**kwargs):
            calls.append(time.monotonic())
            if len(calls)==1:raise OSError(errno.EAGAIN,'fixture before child exists')
            return original(*args,**kwargs)
        with patch.object(jobs.subprocess,'Popen',side_effect=launch):job=self.complete('success')
        self.assertEqual(len(job['attempts']),2)
        self.assertGreaterEqual(calls[1]-calls[0],2)
        self.assertEqual(job['attempts'][0]['outcome'],'prelaunch_os_error')
        self.assertFalse(job['attempts'][0].get('pid'))

    def test_repeated_transient_stops_at_two_and_nontransient_at_one(self):
        for code,attempts in ((errno.EAGAIN,2),(errno.EACCES,1)):
            job=self.submit()
            with patch.object(jobs.subprocess,'Popen',side_effect=OSError(code,'fixture')):
                self.manager.run_once()
            self.assertEqual(len(self.manager.get(job)['attempts']),attempts)
            self.assertEqual(self.manager.get(job)['state'],'failed')

    def test_retry_deadline_and_cancel_backoff_stop_without_second_launch(self):
        job=self.submit();value=self.manager.get(job);value['submitted_epoch']=time.time()-599
        self.manager.save(value)
        with patch.object(jobs.subprocess,'Popen',side_effect=OSError(errno.EAGAIN,'fixture')):
            self.manager.run_once()
        self.assertEqual(self.manager.get(job)['error'],'retry_deadline_exhausted')
        self.assertEqual(len(self.manager.get(job)['attempts']),1)
        job=self.submit()
        with patch.object(jobs.subprocess,'Popen',side_effect=OSError(errno.EAGAIN,'fixture')):
            self.manager.run_once(background=True)
            self.wait(lambda:self.manager.get(job)['phase']=='retry_backoff')
            self.manager.cancel(job)
            self.wait(lambda:self.manager.get(job)['state']=='cancelled')
        self.assertEqual(len(self.manager.get(job)['attempts']),1)

    def test_partial_write_failure_never_retries_and_keeps_stage(self):
        job=self.submit('partial');self.manager.run_once();value=self.manager.get(job)
        self.assertEqual(value['state'],'failed');self.assertEqual(len(value['attempts']),1)
        self.assertEqual((self.stage(job)/'a.txt').read_text(),'partial')
        self.assertEqual((self.project/'a.txt').read_text(),'old text')

    def test_atomic_idempotent_acceptance_key_conflict_and_queue_cap(self):
        job=self.submit(idempotency_key='same')
        self.assertEqual(self.submit(idempotency_key='same'),job)
        with self.assertRaises(jobs.JobError):self.submit('different',idempotency_key='same')
        self.manager.close();self.manager=self.open_manager()
        self.assertEqual(self.submit(idempotency_key='same'),job)
        self.assertEqual(self.manager.get(job)['state'],'interrupted')
        for _ in range(8):self.submit()
        with self.assertRaises(jobs.JobError):self.submit()

    def test_storage_and_transfer_admission_refuse_without_filling_disk(self):
        self.manager.free_space=lambda path:0
        with self.assertRaises(jobs.JobError):self.submit()
        self.manager.free_space=lambda path:10*1024**3
        job=self.submit();self.manager.free_space=lambda path:0
        self.assertFalse(self.manager.run_once())
        self.assertEqual(self.manager.get(job)['phase'],'storage_blocked')
        self.assertEqual(self.manager.get(job)['attempts'],[])
        self.store.free_space=lambda path:0
        with self.assertRaises(ValueError):self.store.publish('inbound',[('x.txt',b'x')])

    def test_runtime_home_entries_allow_worker_to_finish_without_live_edits(self):
        job=self.complete('runtime')
        self.assertEqual((self.project/'a.txt').read_text(),'old text')
        self.assertFalse((self.root/'state'/job['job_id']/'home').exists())
        self.assertEqual(len(job['attempts']),1)

    def test_runtime_accounting_counts_files_but_never_follows_links(self):
        home=self.root/'runtime-home';home.mkdir()
        (home/'regular').write_bytes(b'12345')
        external=self.root/'external';external.mkdir();(external/'large').write_bytes(b'x'*100)
        (home/'link').symlink_to(external,target_is_directory=True)
        os.mkfifo(home/'pipe')
        self.assertEqual(stage.managed_size(home,runtime_roots=[home]),5)
        with self.assertRaises(stage.StageError):stage.managed_size(home)
        # Runtime exception cannot exempt a symlink replacing the home directory itself.
        home_link=self.root/'home-link';home_link.symlink_to(home,target_is_directory=True)
        with self.assertRaises(stage.StageError):
            stage.managed_size(self.root,runtime_roots=[home,home_link])

    def test_socket_type_is_scoped_to_runtime_home(self):
        home=self.root/'runtime-home';home.mkdir();(home/'socket-fixture').touch()
        real_stat=stage.os.stat
        def socket_stat(path,*args,**kwargs):
            if path=='socket-fixture':return SimpleNamespace(st_mode=stat.S_IFSOCK,st_size=0)
            return real_stat(path,*args,**kwargs)
        with patch.object(stage.os,'stat',side_effect=socket_stat):
            self.assertEqual(stage.managed_size(home,runtime_roots=[home]),0)
            with self.assertRaises(stage.StageError) as rejected:stage.managed_size(home)
        self.assertEqual(rejected.exception.details,{'path':str(home/'socket-fixture'),'file_type':'s'})

    def test_vanishing_runtime_files_and_directories_are_tolerated_only_in_home(self):
        home=self.root/'runtime-home';home.mkdir();(home/'vanishing').touch()
        real_stat=stage.os.stat
        def vanished(path,*args,**kwargs):
            if path=='vanishing':raise FileNotFoundError(path)
            return real_stat(path,*args,**kwargs)
        with patch.object(stage.os,'stat',side_effect=vanished):
            self.assertEqual(stage.managed_size(home,runtime_roots=[home]),0)
            with self.assertRaises(FileNotFoundError):stage.managed_size(home)
        shutil.rmtree(home)
        self.assertEqual(stage.managed_size(home,runtime_roots=[home]),0)
        with self.assertRaises(FileNotFoundError):stage.managed_size(home)

    def test_workspace_special_file_failure_records_path_and_type(self):
        job=self.submit('unsafe-storage');self.manager.run_once();value=self.manager.get(job)
        self.assertEqual(value['error'],'unsafe_managed_storage')
        self.assertEqual(value['storage_error'],{'path':str(self.stage(job)/'unsafe-link'),'file_type':'l'})
        self.assertIsNotNone(value['worker_stopped_at'])
        self.assertEqual((self.project/'a.txt').read_text(),'old text')

    def test_admission_special_file_records_diagnostic_without_stopping_manager(self):
        job=self.submit();path=self.root/'state'/'unsafe-link';path.symlink_to(self.project/'a.txt')
        self.assertFalse(self.manager.run_once())
        value=self.manager.get(job)
        self.assertEqual(value['admission_error'],'unsafe_managed_storage')
        self.assertEqual(value['storage_error'],{'path':str(path),'file_type':'l'})
        self.assertIsNone(self.manager.persistence_error)
        path.unlink();self.manager.run_once()
        self.assertEqual(self.manager.get(job)['state'],'succeeded')

    def test_reviewed_retention_only_named_fixtures_and_tombstones(self):
        job=self.complete('success',idempotency_key='retained')
        receipt=self.apply(job)
        now=time.time()+91*86400
        self.assertFalse(self.manager.retention(now=now)['candidates'][0]['bulk_eligible'])
        self.manager.review(job['job_id'])
        self.assertTrue(self.manager.retention(now=now)['candidates'][0]['summary_eligible'])
        with self.assertRaises(jobs.JobError):self.manager.retention(apply=True,now=now)
        self.manager.retention(apply=True,job_ids=[job['job_id']],now=now)
        self.assertFalse((self.root/'state'/job['job_id']).exists())
        self.assertEqual(self.submit('success',idempotency_key='retained'),job['job_id'])
        self.assertEqual(self.apply(job),receipt)
        self.assertTrue((self.project/'unrelated.txt').exists())

    def test_active_pinned_and_referenced_data_never_retained_cleanup_candidates(self):
        done=self.complete('success')
        pending=self.submit()
        self.manager.review(done['job_id'],pinned=True)
        rows=self.manager.retention(now=time.time()+100*86400)['candidates']
        self.assertTrue(all(not row['bulk_eligible'] for row in rows))

    def test_manual_verified_output_dependency_and_reference_pin(self):
        first=self.complete('success')
        second=self.submit('success',inbound_transfer_ids=[first['outbound_transfer_id']],dependency_job_ids=[first['job_id']])
        self.manager.run_once()
        self.assertEqual(self.manager.get(second)['state'],'succeeded')
        self.assertTrue((self.root/'state'/second/'inputs'/first['outbound_transfer_id']/'bundle.json').exists())
        self.manager.review(first['job_id'])
        candidates=self.manager.retention(now=time.time()+100*86400)['candidates']
        self.assertFalse(next(row for row in candidates if row['job_id']==first['job_id'])['bulk_eligible'])
        with self.assertRaises(jobs.JobError):self.submit(dependency_job_ids=[second])

    def test_registered_mcp_delivery_readback_and_apply(self):
        mcp=FastMCP('staged-fixture');register_tools(mcp,lambda:SimpleNamespace(jobs=self.manager,transfers=self.store))
        async def call(name,args):
            response=await mcp.call_tool(name,args)
            blocks=response[0] if isinstance(response,tuple) else response
            return json.loads(next(block.text for block in blocks if hasattr(block,'text')))
        job=asyncio.run(call('project_submit',{'assignment':'success','acceptance_criteria':['done'],
             'project_id':'model-bridge','authority':AUTH,'target_paths':['a.txt'],'idempotency_key':'mcp'}))
        self.assertEqual(job['status'],'ok');self.manager.run_once()
        result=asyncio.run(call('project_result',{'job_id':job['job_id']}))
        read=asyncio.run(call('transfer_read',{'direction':'outbound','transfer_id':result['outbound_transfer_id'],'filename':'bundle.json'}))
        self.assertEqual(read['status'],'ok')
        applied=asyncio.run(call('project_apply',{'job_id':job['job_id'],'bundle_hash':result['bundle_hash'],'base_hash':result['base_hash'],'authority':APPLY}))
        self.assertEqual(applied['state'],'applied')

    def test_mcp_storage_rejection_returns_redacted_path_and_type(self):
        path=self.root/'state'/'unsafe-link';path.symlink_to(self.project/'a.txt')
        mcp=FastMCP('storage-fixture');register_tools(mcp,lambda:SimpleNamespace(jobs=self.manager,transfers=self.store))
        async def submit():
            response=await mcp.call_tool('project_submit',{'assignment':'success','acceptance_criteria':['done'],
                'project_id':'model-bridge','authority':AUTH,'target_paths':['a.txt']})
            blocks=response[0] if isinstance(response,tuple) else response
            return json.loads(next(block.text for block in blocks if hasattr(block,'text')))
        self.manager.secrets_provider=lambda:('unsafe-link',)
        result=asyncio.run(submit())
        self.assertEqual(result['status'],'error')
        self.assertEqual(result['error']['code'],'unsafe_managed_storage')
        self.assertEqual(result['error']['file_type'],'l')
        self.assertNotIn('unsafe-link',result['error']['path'])

    def test_same_repo_apply_lock_serializes_two_bundles_and_refuses_second_stale(self):
        first=self.complete('success');second=self.complete('success')
        original=jobs.private_json;entered=threading.Event();release=threading.Event();results=[]
        def paused(path,value):
            original(path,value)
            if path.parent.name==first['job_id'] and path.name=='apply-receipt.json' and not value.get('completed_paths') and value.get('current_path') is None:
                entered.set();release.wait(3)
        def applying(job):
            try:results.append(self.apply(job)['state'])
            except jobs.JobError as error:results.append(str(error))
        with patch.object(jobs,'private_json',side_effect=paused):
            a=threading.Thread(target=applying,args=(first,));a.start()
            self.assertTrue(entered.wait(3))
            b=threading.Thread(target=applying,args=(second,));b.start()
            time.sleep(.1)
            self.assertEqual(results,[])
            self.assertEqual((self.project/'a.txt').read_text(),'old text')
            release.set();a.join(3);b.join(3)
        self.assertFalse(a.is_alive() or b.is_alive())
        self.assertCountEqual(results,['applied','stale_base'])

    def test_actual_two_active_supervisor_crash_preserves_stages_without_replay(self):
        self.manager.close()
        script = r"""import json,os,sys,time
from pathlib import Path
from model_bridge.project_jobs import JobManager
from model_bridge.file_transfers import TransferStore
root=Path(sys.argv[1]);store=TransferStore(root/'inbound',root/'outbound')
m=JobManager(store,state_dir=root/'state',projects={'model-bridge':root/'repo'},
 command_factory=lambda *args:[sys.executable,str(root/'worker.py')],available_memory=lambda:6*1024**3,start=False)
a={'edit':True,'test':True,'commit':False,'push':False}
ids=[m.submit('hold-'+str(i),['done'],'model-bridge',a,target_paths=['a.txt'])['job_id'] for i in range(3)]
m.run_once(background=True);m.run_once(background=True)
until=time.monotonic()+5
while not all((root/'state'/j/'workspace'/'.tmp'/'ready').exists() for j in ids[:2]) and time.monotonic()<until:time.sleep(.02)
assert all((root/'state'/j/'workspace'/'.tmp'/'ready').exists() for j in ids[:2])
(root/'crash.json').write_text(json.dumps({'ids':ids,'pids':[m.get(j)['attempts'][0]['pid'] for j in ids[:2]]}))
os._exit(0)
"""
        child=subprocess.run([sys.executable,'-c',script,str(self.root)],cwd=jobs.PROJECT,capture_output=True,timeout=8)
        self.assertEqual(child.returncode,0,child.stderr)
        record=json.loads((self.root/'crash.json').read_text())
        for pid in record['pids']:
            # Signal only positively identified fixture worker process groups.
            argv=Path(f'/proc/{pid}/cmdline').read_bytes()
            self.assertIn(str(self.root/'worker.py').encode(),argv)
            self.assertEqual(os.getpgid(pid),pid)
            try:os.killpg(pid,signal.SIGKILL)
            except ProcessLookupError:pass
        self.manager=self.open_manager()
        for job in record['ids']:
            value=self.manager.get(job)
            self.assertEqual(value['state'],'interrupted')
            self.assertIsNone(value['worker_stopped_at'])
        self.assertFalse(self.manager.run_once())
        self.assertTrue(all((self.stage(j)/'.tmp'/'ready').exists() for j in record['ids'][:2]))
        self.complete('success')

    def test_metadata_write_failure_halts_dispatch_and_reports_uncertain_durability(self):
        first=self.submit();second=self.submit()
        original=self.manager.save
        def fail_after_dispatch(job):
            if job.get('phase')=='preparing_stage':return original(job)
            raise sqlite3.OperationalError('fixture disk full')
        with patch.object(self.manager,'save',side_effect=fail_after_dispatch):
            self.manager.run_once()
        self.assertIsNotNone(self.manager.persistence_error)
        self.assertFalse(self.manager.active)
        self.assertFalse(self.manager.run_once())
        self.assertEqual(self.manager.get(second)['state'],'queued')
        self.assertIn('unknown',self.manager.get(first)['manager_warning'])
        self.assertEqual(self.manager.get(first)['attempts'],[])
