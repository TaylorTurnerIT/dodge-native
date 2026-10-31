"""Integrated real custody/worker/supervisor/writer CPU fixtures. Zero cloud/GPU."""
import base64,contextlib,hashlib,importlib.util,io,json,os,shutil,subprocess,sys,tarfile,tempfile,threading,time,unittest,uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from learning.tests.test_teacher_colab_result_safety_20261031_r1 import contents_server


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m


EX=ROOT/'learning/experiments';SOURCE=EX/'teacher_ray_colab_training_r3'
c=module('durable_parent_cpu',EX/'teacher_colab_durable_dispatch_20261031_r1.py')
b=module('durable_budget_cpu',EX/'teacher_colab_durable_budget_20261031_r1.py')
t=module('durable_adapter_cpu',EX/'teacher_colab_durable_transport_20261031_r1.py')
FIXTURE=ROOT/'learning/tests/fixtures/durable_colab_cpu.py'


class OfflineTransport:
    def __init__(self,root,reg,url):
        self.root,self.reg,self.url=Path(root),reg,url;self.endpoint='owned-fixture';self.count=0;self.allocations=0;self.releases=0
        self.children=[];self.control_closed=False
    def snapshot(self,timeout):
        return dict(raw=dict(currentBalance=100.,consumptionRateHourly=6.73,assignmentsCount=self.count),
                    assignments=[dict(endpoint=self.endpoint,accelerator='A100')] if self.count else [],session=None)
    def allocate(self,nonce,timeout):
        self.allocations+=1;self.count=1
        owned=dict(endpoint=self.endpoint,notebook_hash=nonce,name=self.reg['session_name'],accelerator='A100')
        c.save(self.root/'dispatch/owned-endpoint.json',owned)
        Path(self.reg['cli_config_path']).write_text(json.dumps({self.reg['session_name']:dict(endpoint=self.endpoint,url=self.url,token='PRIVATE_CPU_ONLY')}))
        return owned
    def prepare_control(self,timeout):pass
    def put_json(self,remote,value,timeout,**kw):
        target=self.remote(remote);target.parent.mkdir(parents=True,exist_ok=True)
        tmp=target.with_name(target.name+'.overwrite');tmp.write_bytes(kw.get('exact_bytes') or json.dumps(value).encode());os.replace(tmp,target)
    def mkdir(self,remote,timeout):self.remote(remote).mkdir(parents=True,exist_ok=True)
    def upload(self,local,remote,timeout):
        target=self.remote(remote);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(local,target)
    def download(self,remote,local,timeout):
        if remote.endswith('.so'):Path(local).write_bytes(b'CPU-fixture-not-ELF')
        else:shutil.copyfile(self.remote(remote),local)
    def remote(self,path):return self.root/'remote'/Path(path).relative_to('/content/dodge064')
    def start(self,script,stage,timeout):
        if stage=='unpack':command=[sys.executable,'-B','-c','pass']
        else:command=[sys.executable,'-B',str(FIXTURE),'stage',stage]
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',DODGE064_RUN_ROOT=str(self.root/'remote'),DODGE064_EXECUTION_ADMITTED='true',
            DURABLE_FIXTURE_SOURCE=str(SOURCE),DURABLE_FIXTURE_REG=self.reg['fixture_local_reg'])
        with (self.root/(stage+'.stderr')).open('wb') as stderr:
            process=subprocess.Popen(command,env=env,stdout=subprocess.DEVNULL,stderr=stderr,start_new_session=True)
        self.children.append(process);return process
    def stop_local(self,process):t.kill_local(process)
    def unassign(self,endpoint,timeout):
        assert endpoint==self.endpoint;self.releases+=1;self.count=0
    def close_control(self):self.control_closed=True


class FixtureController(c.Controller):
    def prepare_receiver(self):
        actual=self.wire_module.ContentsTransport
        with patch.object(self.wire_module,'ContentsTransport',lambda **kw:actual(**kw,fixture_only=True)):
            super().prepare_receiver()


class IntegratedTests(unittest.TestCase):
    def exercise(self,*,fail_job=None):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();remote=root/'remote';remote.mkdir();(remote/'exports').mkdir()
            state=root/'state.json';state.write_text(json.dumps(dict(active_long_campaign={'owner':'old062'},other=42)))
            pool=root/'CPU-dummy-pool';pool.write_bytes(b'CPU fixture has no seeds')
            challenge=root/'challenge.bin';challenge.write_bytes(os.urandom(32*1024**2));chunks=[];uploads=[]
            for n in range(32):
                path=root/('chunk-%02d.bin'%n);path.write_bytes(challenge.read_bytes()[n*1048576:(n+1)*1048576])
                item=dict(local=str(path),remote='/content/dodge064/inputs/challenge/'+path.name,sha256=c.sha(path));chunks.append(item);uploads.append(item)
            jobs=[dict(id=name,arm='rays' if 'rays' in name else 'control',replica='1' if name.startswith('r1') else '2') for name in ['r1-control','r1-rays','r2-rays','r2-control']]
            reg=dict(record='DODGE-064',job_nonce=str(uuid.uuid4()),registration_sha256='a'*64,payload_sha256='b'*64,
                expected_lease={'owner':'new064'},previous_lease={'owner':'old062'},expected_lease_sha256='c'*64,state_path=str(state),
                pool_sha256=c.sha(pool),deferred_training_pool={'local':str(pool)},session_name='CPU-dummy-session',cli_config_path=str(root/'private.json'),
                uploads=uploads,unpack_script='CPU-source-assembly',stage_script='CPU-stage',stage_timeout_seconds=dict(preflight=180,build=1100,train=21320),
                jobs=jobs,storage_challenge=dict(sha256=c.sha(challenge),chunks=chunks),owner_source_root=str(SOURCE),
                source_pins={str(p):c.sha(p) for p in SOURCE.rglob('*') if p.is_file()},sdk_python=sys.executable,
                financial_limits=vars(b.Config()),result_safety=dict(checkpoint_ack_seconds=60,job_ack_seconds=60,recovery_seconds=3,teardown_seconds=180),
                envs=1,rollout=1,updates=36,frame_target=36,total_actual_frames=144,effective_minibatch=1,microbatch=1,
                checkpoint_updates=[12,24,36],prefix_updates=2,work_seconds=60,receipt_seconds=10,campaign_total_seconds=21320,IO_reserve_seconds=0,
                rss_bytes=6*1024**3,cuda_driver_bytes=6*1024**3,arms={arm:dict(gamma=.99,gae_lambda=.90) for arm in ('control','rays')},
                ppo=dict(update_epochs=1,learning_rate=3e-5,target_kl=.03,reward_scale=.1),fixture_local_reg=str(root/'fixture.json'))
            # Fixture worker avoids hashing self-referential reg metadata by
            # using the actual frozen document digest set outside its bytes.
            saved=dict(reg);saved.pop('registration_sha256');Path(reg['fixture_local_reg']).write_text(json.dumps(saved))
            reg['registration_sha256']=c.sha(reg['fixture_local_reg'])
            disposition=dict(record='DODGE-062',campaign_success=False,exact_lease=reg['previous_lease'])
            with contents_server(remote/'exports') as url:
                transport=OfflineTransport(root,reg,url)
                def build(*args):return dict(native_binary_sha256='0'*64)
                def decode(path,reg,admission):
                    owner=c.owner_reader(reg)
                    return owner.decode_archive(path,c.sha(path),reg,require_complete=True,allow_fixtures=True)
                with patch.object(c,'PARENT',root),patch.object(c,'failed062_disposition',return_value=disposition),patch.object(c,'validate_build',build),patch.object(c,'validate_boundary',lambda *a,**k:None),patch.object(c,'validate_training',decode):
                    controller=FixtureController(reg,dict(review_sha256='fixture-only',registration_path=reg['fixture_local_reg']),root/'dispatch',transport,b.TrainingBudget)
                    if fail_job:
                        with patch.dict(os.environ,{'DURABLE_FIXTURE_FAIL_JOB':fail_job}),self.assertRaisesRegex(ValueError,'DODGE-064 failed'):controller.run()
                    else:
                        try:result=controller.run()
                        except BaseException:
                            for log in root.rglob('*.stderr'):print(log.name,log.read_text()[-1800:])
                            if (root/'dispatch/first-failure.json').exists():print((root/'dispatch/first-failure.json').read_text())
                            for fp in remote.rglob('*first-failure.json'):
                                data=json.loads(fp.read_text());print(fp.name,{key:data.get(key) for key in ['error','traceback','status','exception_type','child_returncode','completed_updates','training_frames']})
                            raise
                        self.assertEqual(result['status'],'training_complete_pending_coordinator_acceptance')
                # CPU fixture artifacts are local and never training evidence.
                self.assertEqual(transport.allocations,1);self.assertEqual(transport.releases,1)
                self.assertEqual(json.loads(state.read_text())['active_long_campaign'],reg['expected_lease'])
                self.assertEqual(json.loads(state.read_text())['other'],42)
                self.assertTrue(all(child.poll() is not None for child in transport.children))
                if fail_job:
                    failure=json.loads((root/'dispatch/first-failure.json').read_text())
                    self.assertEqual(failure['phase'],'training')
                    self.assertTrue((root/'dispatch/durable-results/exports/000009/backup-receipt.json').exists())
                    self.assertFalse((remote/'artifacts/outputs/r2-control').exists())
                else:
                    self.assertTrue((root/'dispatch/durable-results/normal-release-permit.json').exists())
                    self.assertEqual(len(list((root/'dispatch/durable-results/exports').iterdir())),18)
                    with self.assertRaisesRegex(ValueError,'CPU fixture cannot qualify'):
                        c.owner_reader(reg).decode_archive(root/'dispatch/training-artifacts.tar',c.sha(root/'dispatch/training-artifacts.tar'),reg,require_complete=True,allow_fixtures=False)

    def test_full_real_CPU_campaign_and_backup_release_pipeline(self):self.exercise()
    def test_failed_worker_preserves_earlier_backup_and_no_later_job(self):self.exercise(fail_job='r2-rays')


if __name__=='__main__':unittest.main()
