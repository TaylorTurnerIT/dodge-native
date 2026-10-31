"""Real file/HTTP/process boundaries, scripted account transport; zero cloud work."""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

EXPERIMENTS = Path(__file__).resolve().parents[1]/'experiments'


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, EXPERIMENTS/filename)
    value = importlib.util.module_from_spec(spec); sys.modules[name] = value; spec.loader.exec_module(value)
    return value


c = module('training_controller_test', 'teacher_colab_training_dispatch_20261031_r2.py')
t = module('training_transport_test', 'teacher_colab_training_transport_20261031_r2.py')
b = module('training_budget_test', 'teacher_colab_training_budget_20261031_r2.py')


class FakeClock:
    def __init__(self): self.value = 0.
    def now(self): return self.value


class FakeTransport:
    def __init__(self):
        self.endpoint = 'owned'; self.controls = []; self.count = 1; self.rate = 6.73
        self.balance = 100.; self.block = None; self.entered = threading.Event()
    def snapshot(self, timeout):
        return dict(raw=dict(currentBalance=self.balance, consumptionRateHourly=self.rate, assignmentsCount=self.count),
            assignments=[] if not self.count else [dict(endpoint=self.endpoint,accelerator='A100')], session=None)
    def put_json(self, remote, value, timeout):
        self.entered.set()
        if self.block is not None: self.block.wait(3)
        self.controls.append(dict(value))
    def prepare_control(self,timeout):pass
    def close_control(self):pass


class FenceTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport(); self.clock = FakeClock()
        self.reg = dict(record='DODGE-062', job_nonce='nonce', registration_sha256='r'*64, expected_lease_sha256='l'*64)
        self.fence = c.LiveFence(self.reg,self.transport,b.TrainingBudget(100.,0.),self.clock,io.StringIO(),lease_check=lambda _:None)
        # The production writer fsyncs a real journal. Tests use a real temp file.
        self.journal = tempfile.TemporaryFile(mode='w+')
        self.fence.journal = self.journal
        self.fence.meter_once()
    def tearDown(self):
        self.fence.close(); self.journal.close()
    def test_issued_control_has_exact_identity_TTL_and_increasing_sequence(self):
        self.fence.renew_once(); self.fence.renew_once()
        first,second=self.transport.controls
        self.assertEqual(first['expires_at_utc']-first['issued_at_utc'],45)
        self.assertEqual(first['job_nonce'],'nonce');self.assertEqual(second['sequence'],2)
        self.assertEqual(second['allowed_stage'],'build')
    def test_stale_financial_permit_never_renews(self):
        self.clock.value=36
        with self.assertRaisesRegex(ValueError,'Financial permit expired'):self.fence.renew_once()
        self.assertEqual(self.transport.controls,[])
    def test_lease_loss_never_renews(self):
        self.fence.lease_check=lambda _:c.need(False,'lease lost')
        with self.assertRaisesRegex(ValueError,'lease lost'):self.fence.renew_once()
    def test_bad_live_rate_cannot_admit_work(self):
        self.transport.rate=7.1
        with self.assertRaisesRegex(ValueError,'over-ceiling'):self.fence.meter_once()
    def test_missing_assignment_cannot_admit_work(self):
        self.transport.count=0
        with self.assertRaisesRegex(ValueError,'Exactly one'):self.fence.meter_once()
    def test_suspend_counts_against_total_setup(self):
        self.clock.value=1201;self.fence.permit_at=1201
        with self.assertRaisesRegex(ValueError,'setup cap'):self.fence.check()
    def test_train_requires_admission_and_binds_its_actual_bytes_digest(self):
        self.fence.train('a'*64)
        self.assertEqual(self.transport.controls[-1]['runtime_admission_sha256'],'a'*64)
        self.assertEqual(self.transport.controls[-1]['allowed_stage'],'train')
    def test_transition_drains_old_control_before_train(self):
        self.transport.block=threading.Event()
        writer=threading.Thread(target=self.fence.renew_once);writer.start()
        self.assertTrue(self.transport.entered.wait(1))
        changer=threading.Thread(target=lambda:self.fence.train('a'*64));changer.start()
        self.assertTrue(changer.is_alive())
        self.transport.block.set();writer.join(2);changer.join(2)
        self.assertFalse(writer.is_alive());self.assertFalse(changer.is_alive())
        self.assertEqual([v['allowed_stage'] for v in self.transport.controls],['build','train'])
    def test_stop_is_permanent(self):
        self.fence.close()
        with self.assertRaisesRegex(ValueError,'stopped'):self.fence.renew_once()
    def test_first_monitor_failure_is_preserved(self):
        self.fence.fail('first');self.fence.fail('second')
        self.assertEqual(self.fence.error,'first')
        with self.assertRaisesRegex(ValueError,'first'):self.fence.check()
    def test_loop_fault_sets_stop_without_external_error_text(self):
        class Once:
            stopped=False
            def wait(self,_):return self.stopped
            def set(self):self.stopped=True
        self.fence.stop=Once()
        def action():raise ValueError('secret-token-must-not-escape')
        self.fence.loop(action)
        self.assertEqual(self.fence.error,'Live action failed: ValueError')


class BoundaryTests(unittest.TestCase):
    def test_output_symlink_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);queue=root/'queue';queue.mkdir();elsewhere=root/'outside';elsewhere.mkdir()
            (queue/'redirect').symlink_to(elsewhere,target_is_directory=True)
            with patch.object(c,'PARENT',queue),self.assertRaisesRegex(ValueError,'direct real'):
                c.output_path(queue/'redirect',create=True)
            self.assertEqual(list(elsewhere.iterdir()),[])
    def test_shared_CAS_preserves_unrelated_state_and_durable_order(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'state.json';state.write_text(json.dumps(dict(active_long_campaign=None,other={'x':1})))
            reg=dict(state_path=str(state)); lease={'owner':'058'}
            c.lease_cas(reg,None,lease)
            def before():
                self.assertEqual(c.read(state)['active_long_campaign'],lease)
                c.save(Path(directory)/'accepted.json',{'status':'accepted'})
            c.lease_cas(reg,lease,None,before=before)
            self.assertTrue((Path(directory)/'accepted.json').exists())
            self.assertEqual(c.read(state),dict(active_long_campaign=None,other={'x':1}))
    def test_CAS_mismatch_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'state.json';state.write_text('{"active_long_campaign":{"owner":"foreign"}}')
            original=state.read_bytes()
            with self.assertRaisesRegex(ValueError,'CAS differs'):c.lease_cas(dict(state_path=str(state)),None,{'owner':'058'})
            self.assertEqual(state.read_bytes(),original)
    def test_failed_durable_acceptance_retains_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'state.json';state.write_text('{"active_long_campaign":{"owner":"058"}}')
            def fail():raise OSError('disk full')
            with self.assertRaises(OSError):c.lease_cas(dict(state_path=str(state)),{'owner':'058'},None,before=fail)
            self.assertEqual(c.read(state)['active_long_campaign'],{'owner':'058'})
    def test_nonchunked_PUT_preserves_exact_text(self):
        class Contents:
            def _request(self,*args,**kwargs):return args,kwargs
        data=b'{"accepted":true}\n'
        args,kwargs=t.put_text(Contents(),'/content/dodge062/runtime-admission.json',data)
        self.assertEqual(args,('PUT','/content/dodge062/runtime-admission.json'))
        self.assertNotIn('chunk',kwargs['json_data'])
        self.assertEqual(kwargs['json_data']['content'].encode(),data)
    def test_official_ContentsClient_real_request_gets_nonchunked_body(self):
        sys.path.insert(0,'/tmp/dodge-colab-cli-20261031-venv/lib/python3.12/site-packages')
        from colab_cli.contents import ContentsClient
        from types import SimpleNamespace
        client=ContentsClient(SimpleNamespace(url='https://offline.invalid',token='private-fixture'))
        class Response:
            status_code=200
            def raise_for_status(self):pass
            def json(self):return {'type':'file'}
        with patch('requests.request',return_value=Response()) as request:
            t.put_text(client,'/content/dodge062/control.json',b'{"sequence":1}')
        self.assertEqual(request.call_args.args[0],'PUT')
        self.assertNotIn('chunk',request.call_args.kwargs['json'])
        self.assertEqual(request.call_args.kwargs['json']['content'],'{"sequence":1}')
    def test_bounded_real_process_timeout_reaps_group(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            t.bounded([sys.executable,'-B','-c','import time;time.sleep(30)'],dict(os.environ),.03)
    def test_unknown_external_failure_text_never_printed(self):
        with self.assertRaisesRegex(ValueError,'Bounded Colab operation failed'):
            t.bounded([sys.executable,'-B','-c','print("secret");raise SystemExit(1)'],dict(os.environ),3)
    def test_wall_clock_counts_suspend(self):
        with patch.object(c.time,'time',side_effect=[100,500]),patch.object(c.time,'monotonic',side_effect=[1,2]):
            clock=c.Clock();self.assertEqual(clock.now(),400)


class CampaignFailureTests(unittest.TestCase):
    def exercise(self,fault):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);output=root/'dispatch';state=root/'state.json'
            state.write_text('{"active_long_campaign":{"owner":"058"},"other":42}')
            pool=root/'CPU-dummy-pool';pool.write_bytes(b'fixture-no-seeds')
            reg=dict(record='DODGE-062',registration_sha256='a'*64,job_nonce='persisted-CPU-fixture',
                expected_lease={'owner':'062'},previous_lease={'owner':'058'},expected_lease_sha256='c'*64,state_path=str(state),
                pool_sha256=c.sha(pool),deferred_training_pool={'local':str(pool)},session_name='CPU-fixture',
                uploads=[{'local':'CPU-dummy','remote':'/content/dodge062/source-input.tar'}],
                unpack_script='CPU-unpack',stage_script='CPU-stage',stage_timeout_seconds={'build':1100,'train':22320})
            disposition=dict(record='DODGE-058',campaign_success=False,exact_lease=reg['previous_lease'])
            failure_disposition=root/'reviewed-disposition.json';failure_disposition.write_text(json.dumps(disposition))
            reg['failure_disposition_path']=str(failure_disposition)
            class Transport(FakeTransport):
                def __init__(self):
                    super().__init__();self.count=0;self.allocations=0;self.releases=0;self.downloads=0
                def allocate(self,nonce,timeout):
                    self.allocations+=1;self.count=1
                    owned=dict(notebook_hash=nonce,name='CPU-fixture',endpoint='owned',accelerator='A100')
                    if fault!='ambiguous_allocation':c.save(output/'owned-endpoint.json',owned)
                    if fault in ['ambiguous_allocation','lost_allocation_response']:raise TimeoutError('private error')
                    return owned
                def mkdir(self,*args,**kwargs):pass
                def upload(self,*args,**kwargs):
                    if fault=='upload':raise TimeoutError('upload failed')
                def start(self,*args,**kwargs):
                    if fault=='provider_removal':self.count=0
                    return subprocess.Popen([sys.executable,'-B','-c','raise SystemExit(7)'],start_new_session=True)
                def download(self,*args,**kwargs):
                    self.downloads+=1;raise FileNotFoundError('no archive emitted')
                def stop_local(self,process):t.kill_local(process)
                def unassign(self,*args,**kwargs):
                    self.releases+=1;self.count=0
                    if fault=='lost_unassign_response':raise TimeoutError('response lost')
                def put_json(self,*args,**kwargs):
                    if fault=='control':raise TimeoutError('control PUT failed')
            transport=Transport()
            with (patch.object(c,'PARENT',root),patch.object(c.time,'sleep'),
                  patch.object(c,'failed058_disposition',return_value=disposition),
                  self.assertRaisesRegex(ValueError,'preserve exact lease')):
                c.Controller(reg,{'review_sha256':'review','registration_path':'CPU-registration'},
                    output,transport,b.TrainingBudget).run()
            self.assertEqual(transport.allocations,1)
            self.assertEqual(c.read(state)['active_long_campaign'],reg['expected_lease'])
            self.assertEqual(c.read(state)['other'],42)
            self.assertTrue((output/'first-failure.json').exists())
            self.assertFalse((output/'lease-release.json').exists())
            if fault=='ambiguous_allocation':
                self.assertEqual(transport.releases,0)
                self.assertEqual(c.read(output/'cleanup-first-failure.json')['status'],'allocation_outcome_ambiguous_no_unowned_stop')
            elif fault=='provider_removal':
                self.assertEqual(transport.releases,0)
                self.assertEqual(c.read(output/'teardown.json')['removal_classification'],'assignment_absent_before_our_release_request')
            else:
                self.assertEqual(transport.releases,1)
                self.assertEqual(c.read(output/'teardown.json')['status'],'owned_assignment_absent')
    def test_ambiguous_allocation_never_retries_or_stops_unowned_VM(self):self.exercise('ambiguous_allocation')
    def test_lost_allocation_response_uses_durable_exact_endpoint(self):self.exercise('lost_allocation_response')
    def test_upload_failure_releases_only_owned_VM_and_holds_lease(self):self.exercise('upload')
    def test_control_failure_prevents_work_then_tears_down(self):self.exercise('control')
    def test_nonzero_real_child_retains_failure_and_lease(self):self.exercise('worker')
    def test_provider_removal_is_not_reported_as_our_release(self):self.exercise('provider_removal')
    def test_lost_release_response_still_checks_absence_once(self):self.exercise('lost_unassign_response')


class OfficialAdapterTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0,'/tmp/dodge-colab-cli-20261031-venv/lib/python3.12/site-packages')
        from colab_cli.client import Accelerator
        self.directory=tempfile.TemporaryDirectory();self.root=Path(self.directory.name)
        self.nonce=str(uuid.uuid4());self.calls=[];self.unassignments=[]
        self.reg=dict(job_nonce=self.nonce,session_name='CPU-fixture',registration_sha256='a'*64,
            expected_lease={'owner':'058'},state_path=str(self.root/'state.json'),
            cli_config_path=str(self.root/'private.json'),input_pins={str(p):c.sha(p) for p in
                Path('/tmp/dodge-colab-cli-20261031-venv/lib/python3.12/site-packages/colab_cli').rglob('*.py')})
        (self.root/'state.json').write_text(json.dumps({'active_long_campaign':self.reg['expected_lease']}))
        c.save(self.root/'dispatch.claimed',dict(notebook_hash=self.nonce,expected_lease=self.reg['expected_lease'],registration_sha256='a'*64))
        c.save(self.root/'allocation.claimed',dict(notebook_hash=self.nonce))
        response=SimpleNamespace(endpoint='owned',accelerator=Accelerator.A100,
            runtime_proxy_info=SimpleNamespace(token='PRIVATE-TOKEN',url='https://PRIVATE.invalid',expires_at=lambda:None))
        def assign(*args,**kwargs):self.calls.append((args,kwargs));return response
        def add(session):(self.root/'private.json').write_text('{}')
        self.store=SimpleNamespace(get=lambda _:None,add=add,remove=lambda _:None)
        self.state=SimpleNamespace(client=SimpleNamespace(assign=assign,unassign=self.unassignments.append),store=self.store)
        self.state_patch=patch('colab_cli.common.State',return_value=self.state);self.state_patch.start()
        self.environment=patch.dict(os.environ,COLAB_CLI_ASSIGN_RETRIES='0',COLAB_CLI_REQUEST_TIMEOUT='15');self.environment.start()
        self.network=patch('requests.request',side_effect=AssertionError('Network forbidden'));self.network.start()
    def tearDown(self):
        self.network.stop();self.environment.stop();self.state_patch.stop();self.directory.cleanup()
    def allocate(self):return t.sdk_adapter(self.reg,self.root,'allocate',nonce=self.nonce)
    def test_actual_session_model_accepts_only_persisted_UUID_and_A100(self):
        from colab_cli.client import Accelerator,Variant,Shape
        owned=self.allocate()
        self.assertEqual(str(self.calls[0][0][0]),self.nonce)
        self.assertEqual(self.calls[0][1],dict(accelerator=Accelerator.A100,variant=Variant.GPU,shape=Shape.STANDARD))
        self.assertEqual(owned,c.read(self.root/'owned-endpoint.json'))
        self.assertNotIn('PRIVATE',json.dumps(owned))
    def test_private_store_failure_still_leaves_owned_endpoint(self):
        def failed(_):raise OSError('fixture disk failure')
        self.store.add=failed
        with self.assertRaises(OSError):self.allocate()
        self.assertEqual(c.read(self.root/'owned-endpoint.json')['endpoint'],'owned')
    def test_second_assignment_is_blocked_by_real_exclusive_marker(self):
        self.allocate()
        with self.assertRaises(FileExistsError):self.allocate()
        self.assertEqual(len(self.calls),1)
    def test_unassign_checks_durable_endpoint_without_private_store(self):
        self.allocate()
        t.sdk_adapter(self.reg,self.root,'unassign',endpoint='owned')
        self.assertEqual(self.unassignments,['owned'])
        with self.assertRaisesRegex(ValueError,'exact owned'):
            t.sdk_adapter(self.reg,self.root,'unassign',endpoint='foreign')
        self.assertEqual(self.unassignments,['owned'])
    def test_retry_environment_blocks_before_assignment(self):
        with patch.dict(os.environ,COLAB_CLI_ASSIGN_RETRIES='3'),self.assertRaisesRegex(ValueError,'retries'):
            self.allocate()
        self.assertEqual(self.calls,[])
    def test_actual_official_assign_sends_no_second_POST_after_timeout(self):
        from colab_cli.client import Client
        import requests
        client=object.__new__(Client)
        with (patch.object(Client,'_get_assignment',return_value=SimpleNamespace(token='fixture')) as get,
              patch.object(Client,'_post_assignment',side_effect=requests.exceptions.ReadTimeout('fixture')) as post):
            with self.assertRaises(requests.exceptions.ReadTimeout):client.assign(uuid.UUID(self.nonce))
            self.assertEqual(get.call_count,1);self.assertEqual(post.call_count,1)
    def test_snapshot_refreshes_owned_proxy_privately_from_existing_inventory(self):
        from colab_cli.client import Accelerator
        from colab_cli.state import SessionState
        session=SessionState(name='CPU-fixture',endpoint='owned',accelerator='A100',token='PRIVATE-old',url='https://old.invalid')
        self.store.get=lambda _:session
        captured=[];self.store.add=captured.append
        self.state.client.colab_domain='https://offline.invalid'
        self.state.client._issue_request=lambda *a,**k:SimpleNamespace(model_dump=lambda **_:dict(currentBalance=100.,consumptionRateHourly=6.73,assignmentsCount=1))
        self.state.client.list_assignments=lambda:[SimpleNamespace(endpoint='owned',accelerator=Accelerator.A100,
            runtime_proxy_info=SimpleNamespace(token='PRIVATE-new',url='https://new.invalid',expires_at=lambda:None))]
        result=t.sdk_adapter(self.reg,self.root,'snapshot')
        self.assertEqual(captured[0].token,'PRIVATE-new')
        self.assertNotIn('PRIVATE',json.dumps(result));self.assertNotIn('new.invalid',json.dumps(result))
    def test_dead_control_client_cannot_rearm_or_restart(self):
        transport=object.__new__(t.Transport);transport.control_started=True
        transport.control=SimpleNamespace(poisoned=True)
        with self.assertRaisesRegex(ValueError,'no restart'):transport.prepare_control()
        with self.assertRaisesRegex(ValueError,'no rearm'):
            transport.put_json('/content/dodge062/control.json',{},8)


if __name__=='__main__':unittest.main(verbosity=2)
