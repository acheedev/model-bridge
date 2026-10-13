import asyncio
import base64
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from model_bridge import claude_bridge as bridge
from model_bridge import codex_runner
from model_bridge import file_transfers as transfer
from model_bridge import project_jobs as jobs


def encoded(name, data):
    return {'filename': name, 'content_base64': base64.b64encode(data).decode()}


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=codex_runner.temporary_root(), prefix='transfer-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = transfer.TransferStore(self.root / 'inbound', self.root / 'outbound', lambda: ['private-known-token'])

    def test_binary_unicode_round_trip_both_directions(self):
        files = [('bytes.bin', bytes(range(256))), ('中文.txt', 'Mimi ♥ Ezra\n'.encode())]
        receipt = self.store.accept([encoded(n, d) for n, d in files])
        outbound = self.store.publish('outbound', files)
        for direction, manifest in [('inbound', receipt), ('outbound', outbound)]:
            for name, data in files:
                result = self.store.retrieve(direction, manifest['transfer_id'], name)
                self.assertEqual(base64.b64decode(result['content_base64']), data)
                self.assertEqual(result['size_bytes'], len(data))
                self.assertEqual(result['sha256'], hashlib.sha256(data).hexdigest())

    def test_bad_names_duplicates_and_credentials(self):
        for name in ('../x', '/etc/x', 'a/b', 'a\\b', 'C:x', '.', '..', 'bad\0x'):
            with self.assertRaises(transfer.TransferError): self.store.accept([encoded(name, b'x')])
        for names in [('x', 'x'), ('X', 'x'), ('café', 'cafe\u0301')]:
            with self.assertRaises(transfer.TransferError): self.store.accept([encoded(n, b'x') for n in names])
        for name in ('auth.json', 'bridge.token', 'anthropic.key', '.env', '.env.production', 'private.pem', 'id_rsa'):
            with self.assertRaises(transfer.TransferError): self.store.accept([encoded(name, b'x')])
        with self.assertRaises(transfer.TransferError): self.store.accept([encoded('notes.txt', b'a private-known-token b')])
        with self.assertRaises(transfer.TransferError): self.store.accept([encoded('private-known-token', b'x')])

    def test_encoding_and_limits(self):
        for content in ('%%%=', 'Zg==\n', 'Zh==', 'é'):
            with self.assertRaises(transfer.TransferError): self.store.accept([{'filename':'x', 'content_base64':content}])
        with patch.multiple(transfer, FILE_BYTES=4, TOTAL_BYTES=6, FILE_COUNT=2):
            self.store.accept([encoded('a', b'123'), encoded('b', b'456')])
            self.store.accept([encoded('a', b'1234')])
            for files in ([], [encoded('x',b'12345')], [encoded('a',b'1234'),encoded('b',b'1234')], [encoded(str(i),b'') for i in range(3)]):
                with self.assertRaises(transfer.TransferError): self.store.accept(files)
        with patch.object(transfer, 'REQUEST_BYTES', 1):
            with self.assertRaises(transfer.TransferError): self.store.accept([encoded('x',b'')])
        receipt=self.store.accept([encoded('x',b'')])
        with patch.object(transfer, 'RESPONSE_BYTES',1):
            with self.assertRaises(transfer.TransferError): self.store.retrieve('inbound',receipt['transfer_id'],'x')

    def test_no_overwrite_and_unique_subdirectories(self):
        first=self.store.accept([encoded('same',b'first')])
        second=self.store.accept([encoded('same',b'second')])
        self.assertNotEqual(first['transfer_id'],second['transfer_id'])
        with patch.object(transfer.uuid,'uuid4',return_value=SimpleNamespace(hex=first['transfer_id'])):
            with self.assertRaises(OSError): self.store.accept([encoded('same',b'replacement')])
        self.assertEqual(self.store.load('inbound',first['transfer_id'])[1],[('same',b'first')])

    def test_failed_writes_cleanup_and_restart_cleanup(self):
        real=transfer.write_file
        def fail(fd,name,data):
            if name=='second': raise OSError('interrupted write')
            real(fd,name,data)
        with patch.object(transfer,'write_file',side_effect=fail):
            with self.assertRaises(OSError): self.store.accept([encoded('first',b'a'),encoded('second',b'b')])
        self.assertFalse(list((self.root/'inbound').glob('.pending-*')))
        stage=self.root/'inbound'/('.pending-'+'a'*32)
        stage.mkdir();(stage/'partial').write_bytes(b'x')
        transfer.TransferStore(self.root/'inbound',self.root/'outbound')
        self.assertFalse(stage.exists())

    def test_missing_incomplete_corrupt_and_symlink_files(self):
        for value in ('../bad','a'*32):
            with self.assertRaises(transfer.TransferError): self.store.load('inbound',value)
        incomplete=self.root/'inbound'/('b'*32);incomplete.mkdir()
        with self.assertRaises(transfer.TransferError): self.store.load('inbound','b'*32)
        receipt=self.store.accept([encoded('x',b'original')])
        file=self.root/'inbound'/receipt['transfer_id']/'x'
        file.write_bytes(b'changed')
        with self.assertRaises(transfer.TransferError): self.store.load('inbound',receipt['transfer_id'])
        file.unlink(); outside=self.root/'outside';outside.write_bytes(b'original');file.symlink_to(outside)
        with self.assertRaises(transfer.TransferError): self.store.load('inbound',receipt['transfer_id'])

    def test_root_symlink_rejected_and_racing_root_swap_pinned(self):
        outside=self.root/'outside';outside.mkdir()
        link=self.root/'link';link.symlink_to(outside,target_is_directory=True)
        with self.assertRaises(OSError): transfer.TransferStore(link,self.root/'outbound')
        original=transfer.write_file
        switched=[]
        def swap(fd,name,data):
            if not switched:
                (self.root/'inbound').rename(self.root/'pinned')
                (self.root/'inbound').symlink_to(outside,target_is_directory=True)
                switched.append(True)
            original(fd,name,data)
        with patch.object(transfer,'write_file',side_effect=swap):
            receipt=self.store.accept([encoded('x',b'safe')])
        self.assertEqual(list(outside.iterdir()),[])
        self.assertEqual((self.root/'pinned'/receipt['transfer_id']/'x').read_bytes(),b'safe')
        with self.assertRaises(transfer.TransferError): self.store.load('inbound',receipt['transfer_id'])


STUB = '''import json,os,pathlib,subprocess,sys,time,resource
prompt=json.load(sys.stdin)
assignment=prompt['assignment']
p=pathlib.Path.cwd()
if assignment in ('sleep','tree'):
 if assignment=='tree':
  child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
  (p/'grandchild.pid').write_text(str(child.pid))
 (p/'started').write_text('started')
 time.sleep(60)
if assignment=='flood':
 sys.stdout.write('x'*(2*1024*1024));sys.stdout.flush();time.sleep(60)
if assignment=='crash':sys.exit(7)
if assignment=='exit-only':sys.exit(0)
if assignment=='consume':
 d=pathlib.Path(prompt['reference_directory'])
 files=list(d.glob('*/*'))
 assert files and files[0].read_bytes()==b'reference bytes'
(p/'artifact.txt').write_text('shareable result')
result={'completed':assignment!='incomplete','summary':'done private-known-token',
 'acceptance_results':[{'criterion':c,'passed':assignment!='incomplete','details':'checked'} for c in prompt['acceptance_criteria']],
 'artifact_paths':['artifact.txt']}
if assignment=='limits':result['summary']=json.dumps({'memory':resource.getrlimit(resource.RLIMIT_AS)[0], 'cpu':resource.getrlimit(resource.RLIMIT_CPU)[0], 'core':resource.getrlimit(resource.RLIMIT_CORE)[0], 'nofile':resource.getrlimit(resource.RLIMIT_NOFILE)[0]})
pathlib.Path(os.environ['PROJECT_JOB_RESULT']).write_text(json.dumps(result))
print('worker output private-known-token')
'''


class JobTests(unittest.TestCase):
    def test_package_layout_preserves_worker_project_root(self):
        project = Path(jobs.__file__).resolve().parents[1]
        self.assertEqual(jobs.PROJECT, project)
        self.assertEqual(jobs.PROJECTS['model-bridge'], project)
        self.assertTrue((project / 'model_bridge' / 'project_worker.py').is_file())

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=codex_runner.temporary_root(),prefix='job-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.project=self.root/'project';self.project.mkdir()
        subprocess.run(['git','init','-q',str(self.project)],check=True)
        self.store=transfer.TransferStore(self.root/'inbound',self.root/'outbound',lambda:['private-known-token'])
        self.stub=self.root/'stub.py';self.stub.write_text(STUB)
        self.manager=self.new_manager()
        self.addCleanup(lambda:self.manager.close())

    def new_manager(self):
        return jobs.JobManager(self.store,state_dir=self.root/'state',projects={'model-bridge':self.project},
             secrets_provider=lambda:['private-known-token'],command_factory=lambda *args:[sys.executable,str(self.stub)],start=False,available_memory=lambda:0)

    def submit(self, assignment='success', **kw):
        kw.setdefault('target_paths',['artifact.txt','started','grandchild.pid'])
        return self.manager.submit(assignment,['done'],'model-bridge',{'edit':True,'test':True,'commit':False,'push':False},**kw)['job_id']

    def test_authority_project_resource_and_recursion_rejections(self):
        args=('assignment',['done'],'unknown',{'edit':True,'test':True,'commit':False,'push':False})
        with self.assertRaises(jobs.JobError): self.manager.submit(*args)
        for authority in ({'edit':True,'test':True,'commit':True,'push':False},{'edit':False,'test':True,'commit':False,'push':False},{}):
            with self.assertRaises(jobs.JobError): self.manager.submit('a',['done'],'model-bridge',authority)
        for kw in ({'deadline_seconds':9},{'memory_mb':1},{'cpu_seconds':1801},{'deadline_seconds':True}):
            with self.assertRaises(jobs.JobError): self.submit(**kw)
        with patch.dict(os.environ,{'PROJECT_WORKER_CHILD':'1'}):
            with self.assertRaises(jobs.JobError): self.submit()
        with self.assertRaises(jobs.JobError): self.submit('private-known-token')

    def test_durable_acceptance_status_success_result_and_artifacts(self):
        job_id=self.submit()
        self.assertEqual(self.manager.get(job_id)['state'],'queued')
        with self.manager.connect() as db:self.assertIsNotNone(db.execute('SELECT id FROM jobs WHERE id=?',(job_id,)).fetchone())
        self.assertTrue(self.manager.run_once())
        result=self.manager.get(job_id)
        self.assertEqual(result['state'],'succeeded')
        self.assertEqual(result['process_exit_code'],0)
        self.assertEqual(result['duration_clock'],'monotonic')
        for field in ('accepted_at','execution_started_at','execution_finished_at'):
            self.assertIsNotNone(result[field])
        for field in ('queue_seconds','execution_seconds','total_seconds'):
            self.assertGreaterEqual(result[field],0)
        self.assertNotIn('private-known-token',json.dumps(result))
        manifest,files=self.store.load('outbound',result['outbound_transfer_id'])
        self.assertIn(('artifact.txt',b'shareable result'),files)
        self.assertNotIn(b'private-known-token',b''.join(data for _,data in files))
        self.assertNotIn('private-known-token',(self.root/'state'/job_id/'result.json').read_text())
        self.manager.close();self.manager=self.new_manager()
        self.assertEqual(self.manager.get(job_id)['state'],'succeeded')

    def test_failed_exit_is_not_success_and_incomplete_acceptance(self):
        for assignment in ('crash','exit-only','incomplete'):
            job_id=self.submit(assignment);self.manager.run_once()
            self.assertEqual(self.manager.get(job_id)['state'],'failed')

    def test_inbound_verified_at_submission_and_rechecked_for_consumption(self):
        receipt=self.store.accept([encoded('reference.txt',b'reference bytes')])
        job_id=self.submit('consume',inbound_transfer_ids=[receipt['transfer_id']]);self.manager.run_once()
        self.assertEqual(self.manager.get(job_id)['state'],'succeeded')
        self.assertFalse((self.project/'.worker-inputs').exists())
        self.assertTrue((self.root/'state'/job_id/'inputs'/receipt['transfer_id']/'reference.txt').exists())
        job_id=self.submit('consume',inbound_transfer_ids=[receipt['transfer_id']])
        (self.root/'inbound'/receipt['transfer_id']/'reference.txt').write_bytes(b'tampered')
        self.manager.run_once();self.assertEqual(self.manager.get(job_id)['state'],'failed')
        with self.assertRaises(transfer.TransferError):self.submit(inbound_transfer_ids=['a'*32])

    def test_queued_cancellation_and_restart_never_reruns(self):
        queued=self.submit();self.manager.cancel(queued)
        self.assertEqual(self.manager.get(queued)['state'],'cancelled')
        interrupted=self.submit()
        job=self.manager.get(interrupted);job['state']='running';self.manager.save(job)
        queued=self.submit()
        self.manager.close();self.manager=self.new_manager()
        for job_id in (interrupted,queued):
            recovered=self.manager.get(job_id)
            self.assertEqual(recovered['state'],'interrupted')
            self.assertIsNone(recovered['worker_stopped_at'])
            self.assertIsNone(recovered['finished_at'])
            self.assertIsNotNone(recovered['interruption_detected_at'])
        self.assertFalse(self.manager.run_once())

    def test_same_project_serialization_and_single_supervisor(self):
        with self.assertRaises(jobs.JobError):self.new_manager()
        first=self.submit('sleep');second=self.submit()
        thread=threading.Thread(target=self.manager.run_once);thread.start()
        self.wait_for(self.root/'state'/first/'workspace'/'started')
        self.assertFalse(self.manager.run_once())
        self.assertEqual(self.manager.get(second)['state'],'queued')
        self.manager.cancel(first);thread.join(5);self.assertFalse(thread.is_alive())
        self.assertEqual(self.manager.get(first)['state'],'cancelled')
        self.manager.run_once();self.assertEqual(self.manager.get(second)['state'],'succeeded')

    def wait_for(self,path):
        until=time.monotonic()+5
        while not path.exists() and time.monotonic()<until:time.sleep(.02)
        self.assertTrue(path.exists())

    def test_process_tree_cancellation_and_partial_changes_preserved(self):
        job_id=self.submit('tree');thread=threading.Thread(target=self.manager.run_once);thread.start()
        stage=self.root/'state'/job_id/'workspace'
        self.wait_for(stage/'grandchild.pid')
        pid=int((stage/'grandchild.pid').read_text());self.manager.cancel(job_id)
        thread.join(5);self.assertFalse(thread.is_alive())
        result=self.manager.get(job_id);self.assertEqual(result['state'],'cancelled')
        self.assertIsNotNone(result['cancel_requested_at'])
        self.assertIsNotNone(result['worker_stopped_at'])
        self.assertTrue((stage/'started').exists())
        self.assertFalse((self.project/'started').exists())
        self.assertIn('started',result['partial_changes'])
        # A terminated grandchild may briefly remain a zombie until init reaps it.
        state=subprocess.run(['ps','-o','stat=','-p',str(pid)],capture_output=True,text=True).stdout.strip()
        self.assertTrue(not state or state.startswith('Z'),state)

    def test_queue_deadline_and_running_deadline(self):
        job_id=self.submit('sleep');job=self.manager.get(job_id);job['submitted_epoch']=time.time()-1000;self.manager.save(job)
        self.manager.run_once();self.assertEqual(self.manager.get(job_id)['error'],'deadline_exceeded_in_queue')
        job_id=self.submit('sleep');job=self.manager.get(job_id);job['submitted_epoch']=time.time()-599.5;self.manager.save(job)
        self.manager.run_once();self.assertEqual(self.manager.get(job_id)['error'],'deadline_exceeded')

    def test_output_limit_and_private_resource_launcher(self):
        job_id=self.submit('flood');self.manager.run_once()
        result=self.manager.get(job_id);self.assertEqual(result['error'],'output_limit_exceeded')
        launch=json.loads((self.root/'state'/job_id/'launch.json').read_text())
        self.assertEqual(launch['environment']['MODEL_BRIDGE_CHILD'],'1')
        self.assertEqual(launch['environment']['PROJECT_WORKER_CHILD'],'1')
        self.assertNotIn('OPENAI_API_KEY',launch['environment'])

    def test_resource_limits_are_applied_to_real_worker_process(self):
        job_id=self.submit('limits',memory_mb=512,cpu_seconds=10)
        self.manager.run_once()
        job=self.manager.get(job_id)
        self.assertEqual(job['state'],'succeeded')
        limits=json.loads(job['result']['summary'])
        self.assertEqual(limits,{'memory':512*1024**2,'cpu':10,'core':0,'nofile':256})

    def test_nested_launcher_refuses_before_reading_launch_file(self):
        result=subprocess.run([sys.executable,str(jobs.PROJECT/'model_bridge'/'project_worker.py'),'missing-launch.json'],
                   env={**os.environ,'PROJECT_WORKER_CHILD':'1'},capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Nested project workers are disabled',result.stderr)

    def test_cancel_flag_cannot_be_lost_by_a_stale_save(self):
        job_id=self.submit();stale=self.manager.get(job_id)
        self.manager.cancel(job_id)
        stale['state']='running';self.manager.save(stale)
        self.assertTrue(self.manager.get(job_id)['cancel_requested'])

    def test_unsafe_artifact_fails_with_durable_failure_report(self):
        job_id=self.submit()
        original=self.manager.validate_result
        def unsafe(result,criteria):
            original(result,criteria)
            result['artifact_paths']=['../outside.txt']
        with patch.object(self.manager,'validate_result',side_effect=unsafe):self.manager.run_once()
        result=self.manager.get(job_id)
        self.assertEqual(result['state'],'failed')
        self.assertIsNotNone(result['outbound_transfer_id'])
        self.store.load('outbound',result['outbound_transfer_id'])

    def test_worker_configuration_enforces_policy_and_keeps_consultation_unchanged(self):
        before=codex_runner.CONFIG_OVERRIDES
        with patch.object(codex_runner,'executable',return_value='/usr/bin/codex'):
            settings=self.manager.worker_settings(self.root/'state'/'job'/'workspace',self.root/'state'/'job')
        text='\n'.join(settings)
        self.assertIn(str(self.root/'state'/'job'/'inputs')+'"="read"',text)
        self.assertIn(str(self.project)+'"="deny"',text)
        self.assertIn(str(self.manager.state_dir)+'"="deny"',text)
        for required in ('approval_policy="never"','mcp_servers={}','network.enabled=false','":root"="deny"','":slash_tmp"="deny"','features.multi_agent=false'):
            self.assertIn(required,text)
        self.assertEqual(before,codex_runner.CONFIG_OVERRIDES)
        self.assertIn('sandbox_mode="read-only"',before)

    def test_per_job_inputs_retained_without_clearing_another_job(self):
        first=self.root/'state'/'first';second=self.root/'state'/'second'
        with self.manager.input_workspace(first) as inputs:
            (inputs/'reference.txt').write_bytes(b'first')
            with self.manager.input_workspace(second) as other:
                (other/'reference.txt').write_bytes(b'second')
        self.assertEqual((first/'inputs'/'reference.txt').read_bytes(),b'first')
        self.assertEqual((second/'inputs'/'reference.txt').read_bytes(),b'second')


class RegistrationTests(unittest.TestCase):
    def test_actual_mcp_upload_handler_converts_schema_and_child_guard(self):
        with tempfile.TemporaryDirectory(dir=codex_runner.temporary_root(),prefix='handler-test-') as t:
            p=Path(t);store=transfer.TransferStore(p/'inbound',p/'outbound')
            with patch.object(bridge,'project_runtime',SimpleNamespace(transfers=store)):
                result=asyncio.run(bridge.mcp.call_tool('transfer_upload',{'files':[encoded('x',b'bytes')]}))
                blocks=result[0] if isinstance(result,tuple) else result
                payload=json.loads(next(block.text for block in blocks if hasattr(block,'text')))
                self.assertEqual(payload['status'],'ok')
                self.assertEqual(store.load('inbound',payload['transfer_id'])[1],[('x',b'bytes')])
                with patch.dict(os.environ,{'MODEL_BRIDGE_CHILD':'1'}):
                    result=asyncio.run(bridge.mcp.call_tool('transfer_upload',{'files':[encoded('x',b'bytes')]}))
                blocks=result[0] if isinstance(result,tuple) else result
                payload=json.loads(next(block.text for block in blocks if hasattr(block,'text')))
                self.assertEqual(payload['error']['code'],'recursive_bridge_call')

    def test_tools_registered_with_separate_submission_contract(self):
        tools=asyncio.run(bridge.mcp.list_tools())
        mapping={tool.name:tool.inputSchema for tool in tools}
        for name in ('transfer_upload','transfer_manifest','transfer_read','project_submit','project_status','project_result','project_cancel'):
            self.assertIn(name,mapping)
        self.assertNotIn('project_id',mapping['transfer_upload']['properties'])
        self.assertIn('authority',mapping['project_submit']['required'])

    def test_authenticated_streaming_body_limit(self):
        called=[];sent=[]
        async def app(*args):called.append(True)
        messages=iter([{'type':'http.request','body':b'123','more_body':True},{'type':'http.request','body':b'456','more_body':False}])
        async def receive():return next(messages)
        async def send(message):sent.append(message)
        scope={'type':'http','method':'POST','headers':[(b'authorization',b'Bearer test-token')]}
        with patch.object(bridge,'REQUEST_BYTES',5):asyncio.run(bridge.BearerGate(app,'test-token')(scope,receive,send))
        self.assertFalse(called);self.assertEqual(sent[0]['status'],413)


if __name__=='__main__':unittest.main()
