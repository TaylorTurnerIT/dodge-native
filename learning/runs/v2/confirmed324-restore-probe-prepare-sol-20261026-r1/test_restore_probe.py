"""Strict stdlib controls. Toy learner/RNG only; no runtime imports."""
import copy
import inspect
import json
from pathlib import Path
import random
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import probe as p
import build_registration

class FakeTorch:
    __version__='2.14.1'
    def __init__(self):
        self.cpu=b'cpu-parent'; self.mps_state=b'mps-parent'; self.seed=None
        self.backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda:True))
        self.mps=types.SimpleNamespace(manual_seed=self.mps_seed,get_rng_state=lambda:self.mps_state,synchronize=lambda:None,empty_cache=lambda:None)
    def manual_seed(self,seed): self.seed=seed; self.cpu=str(seed).encode()
    def mps_seed(self,seed): self.mps_state=str(seed).encode()
    def get_rng_state(self): return self.cpu
    def initial_seed(self): return self.seed
class FakeNumpyRandom:
    def __init__(self): self.value=5
    def seed(self,seed): self.value=seed
    def get_state(self): return ('numpy_fake',self.value)
    def RandomState(self,seed): return types.SimpleNamespace(get_state=lambda:('numpy_fake',seed))
class Model:
    def __init__(self): self.value='disposable'
    def state_dict(self): return {'weights':self.value}
class Adam:
    def __init__(self): self.param_groups=[dict(lr=3e-5,params=[0])]; self.value='disposable'
    def state_dict(self): return dict(state={0:dict(moment=self.value,step=324)},param_groups=self.param_groups)

class ProbeControls(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=p.HERE/'tmp'); self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name)
        self.saved_rng=random.getstate(); self.addCleanup(random.setstate,self.saved_rng)
        self.modules=p.private_modules(); self.t=self.modules['transition']; self.fp=self.modules['fingerprints'].fingerprint
        self.reg=build_registration.build(self.root); self.reg['run_id']='confirmed324-restore-probe-toy'
        self.reg['attempt_claim_path']=str(self.root/'toy.restore.claimed')
        self.reg['runtime']['empty_cache_path']=str(p.HERE/'empty-pycache')
        cls=self.modules['runtime_adapter'].RuntimeAdapter; self.adapter=cls.__new__(cls)
        self.adapter.reg=self.reg; self.adapter.env=None
        self.adapter.torch=FakeTorch(); self.adapter.np=types.SimpleNamespace(random=FakeNumpyRandom())
        self.adapter.model=Model(); self.adapter.optimizer=Adam()
        self.parent_model='parent'; self.parent_Adam='parent'
        self.parent_python=random.Random(6).getstate()
        self.parent_raw=dict(python=self.parent_python,numpy_global=('numpy_fake',5),numpy_generator=None,torch_cpu=b'cpu-parent',torch_mps=b'mps-parent',sampling_backend='torch_global_mps')
        self.adapter.model.value=self.parent_model; self.adapter.optimizer.value=self.parent_Adam
        self.expected=dict(model=self.fp(self.adapter.model.state_dict()),Adam=self.fp(self.adapter.optimizer.state_dict()),RNG=self.fp(self.parent_raw))
        self.adapter.model.value='disposable'; self.adapter.optimizer.value='disposable'
        self.events=[]; self.mutate=False; self.forbid=None; self.restore_calls=0
        self.checkpoint=self.root/'checkpoint'; self.checkpoint.write_bytes(b'fake never deserialized')
        self.receipt=self.root/'receipt'; self.receipt.write_bytes(b'fake')
        def capture():
            return dict(python=random.getstate(),numpy_global=self.adapter.np.random.get_state(),numpy_generator=None,torch_cpu=self.adapter.torch.cpu,torch_mps=self.adapter.torch.mps_state,sampling_backend='torch_global_mps')
        def restore_learner():
            self.restore_calls+=1
            self.assertTrue(Path(self.reg['attempt_claim_path']).is_file())
            if self.forbid:
                def forward(): pass
                def ppo_update(): pass
                def make_env(): pass
                {'forward':forward,'ppo_update':ppo_update,'make_env':make_env}[self.forbid]()
            self.adapter.model.value=self.parent_model
            self.adapter.optimizer.value='mutated' if self.mutate else self.parent_Adam
            random.setstate(self.parent_python); self.adapter.np.random.value=5
            self.adapter.torch.cpu=b'cpu-parent'; self.adapter.torch.mps_state=b'mps-parent'
        def restore_trusted(): return restore_learner()
        self.adapter.callbacks=dict(restore_trusted=restore_trusted,rng_capture=capture)
        self.adapter.bootstrap=lambda:None
        self.adapter.source=lambda:dict(receipt_sha256=p.PARENT_RECEIPT,checkpoint_sha256=p.PARENT,checkpoint_path=str(self.checkpoint),receipt_path=str(self.receipt),checkpoint_fingerprints=self.expected,learner_fingerprints=self.expected)
        seeds=self.reg['vector']['seeds']; rr=self.modules['rng_reference']
        reference=dict(schema=rr.SCHEMA,status='measured',backend='mps',torch_version='2.14.1',accepted_checkpoint_sha256=p.PARENT,parent_receipt_sha256=p.PARENT_RECEIPT,study_id=p.STUDY,replica=1,complete_seed_vector=seeds,vector_sha256=rr.canonical_vector_sha256(p.STUDY,1,seeds),cpu_rng_state_sha256=self.fp(str(seeds['torch_cpu_global_seed']).encode()),mps_rng_state_sha256=self.fp(str(seeds['action_sampler_torch_mps_seed']).encode()))
        self.reference_path=self.root/'reference.json'; self.reference_path.write_text(json.dumps(reference))
        self.reg['reference']=dict(receipt_path=str(self.reference_path),receipt_sha256=p.sha(self.reference_path),vector_sha256=self.reg['vector']['vector_sha256'])
    def call(self):
        with patch.object(p,'EXPECTED',self.expected),patch.object(self.t,'EXPECTED_PARENT',self.expected),patch.object(self.t,'_sha256_file',side_effect=lambda path:p.PARENT_RECEIPT if Path(path)==self.receipt else p.PARENT):
            return p.run_claimed(self.reg,{},self.modules,self.adapter,self.events.append)
    def test_success_single_claimed_restore_raw_states_and_noop(self):
        result=self.call(); self.assertEqual(self.restore_calls,1)
        self.assertEqual(result['counts']['restores'],1)
        self.assertTrue(all(v==0 for k,v in result['counts'].items() if k!='restores'))
        self.assertEqual(result['snapshots']['reseeded_before_lr'],result['snapshots']['post_lr'])
        self.assertEqual(result['snapshots']['post_lr']['Adam'],self.expected['Adam'])
        self.assertEqual(self.events,['disposable_bootstrap_complete','accepted_restore_enter','accepted_restore_verified','study_reseed_verified_before_lr','lr_noop_verified_stop_before_environment'])
        self.assertIsNone(self.adapter.env)
    def test_spent_subclaim_blocks_new_call_before_bootstrap(self):
        self.call(); self.adapter.bootstrap=lambda:self.fail('bootstrap after spent subclaim')
        with self.assertRaisesRegex(ValueError,'already spent'): self.call()
        self.assertEqual(self.restore_calls,1)
    def test_wrong_reference_rejected_before_claim_restore(self):
        self.reg['reference']['vector_sha256']='f'*64
        with self.assertRaisesRegex(ValueError,'expected vector hash'): self.call()
        self.assertEqual(self.restore_calls,0); self.assertFalse(Path(self.reg['attempt_claim_path']).exists())
    def test_mutating_restore_failure_keeps_spent_claim(self):
        self.mutate=True
        with self.assertRaisesRegex(ValueError,'live accepted restore fingerprint'): self.call()
        self.assertTrue(Path(self.reg['attempt_claim_path']).exists())
        with self.assertRaisesRegex(ValueError,'already spent'): self.call()
        self.assertEqual(self.restore_calls,1)
    def test_forbidden_forward_before_any_forward_body(self):
        self.forbid='forward'
        with self.assertRaisesRegex(RuntimeError,'forbidden probe call: forward'): self.call()
        self.assertTrue(Path(self.reg['attempt_claim_path']).exists())
    def test_forbidden_ppo(self):
        self.forbid='ppo_update'
        with self.assertRaisesRegex(RuntimeError,'forbidden probe call: ppo_update'): self.call()
    def test_forbidden_environment(self):
        self.forbid='make_env'
        with self.assertRaisesRegex(RuntimeError,'forbidden probe call: make_env'): self.call()
    def test_post_reseed_mutation_fails_and_claim_stays_spent(self):
        original=self.adapter.torch.manual_seed
        def mutated(seed): original(seed); self.adapter.optimizer.value='mutated'
        self.adapter.torch.manual_seed=mutated
        with self.assertRaisesRegex(ValueError,'reseeding changed'): self.call()
        self.assertTrue(Path(self.reg['attempt_claim_path']).exists())
    def test_private_modules_preserve_code_globals_and_class_identity(self):
        self.assertIs(self.modules['contracts'].transition,self.t)
        self.assertIs(self.modules['runtime_adapter'].binding,self.modules['driver_binding'])
        self.assertIs(self.t.transition.__globals__,self.t.__dict__)
        self.assertIs(self.modules['runtime_adapter'].RuntimeAdapter.bootstrap.__globals__,self.modules['runtime_adapter'].__dict__)
        self.assertEqual(Path(inspect.getsourcefile(type(self.adapter))),p.R3/'runtime_adapter.py')
        self.assertNotIn('worker',self.modules); self.assertNotIn('worker_cli',self.modules)
        self.assertFalse(any(k.startswith('dodge_rl') or k in ('torch','numpy') for k in sys.modules))
    def test_required_subset_excludes_training_contract_and_limits(self):
        subset=p.adapter_subset(self.reg,{'parent':{'next_episode_indices':[7]*64}})
        self.assertEqual(set(subset),{'runtime_root','runtime_versions','initial_episode_indices','vector'})
        self.assertNotIn('schedule',subset); self.assertNotIn('limits',subset)
    def test_real_input_gates_are_stdlib_only(self):
        reg=build_registration.build(); modules,context=p.verify_immutable(reg)
        self.assertEqual(context['parent']['candidate_phase_update'],324)
        self.assertEqual(modules['contracts'].PPO['adam_eps'],1e-5)
        self.assertFalse(any(k.startswith('dodge_rl') or k in ('torch','numpy') for k in sys.modules))
    def test_cleanup_attempts_every_stage_after_sync_failure(self):
        calls=[]
        def fail(): calls.append('sync'); raise RuntimeError('fake sync failure')
        self.adapter.torch.mps.synchronize=fail
        self.adapter.torch.mps.empty_cache=lambda:calls.append('empty')
        result=p.release(self.adapter)
        self.assertEqual(calls,['sync','sync','empty','sync'])
        self.assertIsNone(self.adapter.model); self.assertIsNone(self.adapter.parent if hasattr(self.adapter,'parent') else None)
        self.assertEqual(result['empty_mps_cache'],{'status':'pass'})
        self.assertEqual(result['synchronize_after_cache']['status'],'fail')

class RegistrationControls(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=p.HERE/'tmp'); self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name)
        self.reg=build_registration.build(self.root)
    def preflight(self):
        rp=self.root/'registration.json'; rp.write_text(json.dumps(self.reg)); return p.preflight(rp,p.sha(rp),self.reg,p.HERE/'worker_cli.py')
    def registered(self):
        r=self.reg; r.update(status='parent_registered',authority='parent_approved_one_shot',run_id='confirmed324-restore-probe-fixture')
        r['expected_lease'].update(run_id=r['run_id'],owner_token='new-owner-token')
        for field,suffix in [('one_shot_marker','.outer.claimed'),('attempt_claim_path','.restore.claimed'),('output_dir','')]: r[field]=str(self.root/(r['run_id']+suffix))
        r['runtime']['empty_cache_path']=str(p.HERE/'empty-pycache')
        r['state_path']=str(self.root/'state.json'); (self.root/'state.json').write_text(json.dumps({'active_inference_diagnostic':r['expected_lease']}))
    def test_inert_template_rejected_without_marker(self):
        with self.assertRaisesRegex(ValueError,'approval absent'): self.preflight()
        self.assertFalse(Path(self.reg['one_shot_marker']).exists())
    def test_old_training_schema_rejected(self):
        self.reg['schema']='paired_confirmed324_worker_registration_v2'
        with self.assertRaisesRegex(ValueError,'approval absent'): self.preflight()
    def test_strict_extra_field(self):
        self.reg['synthetic_test_dependencies']={}
        with self.assertRaisesRegex(ValueError,'fields mismatch'): self.preflight()
    def test_replica_bool_rejected_before_marker(self):
        self.registered(); self.reg['replica']=True
        with self.assertRaisesRegex(ValueError,'replica-1'): self.preflight()
    def test_replica2_rejected(self):
        self.registered(); self.reg['replica']=2
        with self.assertRaisesRegex(ValueError,'replica-1'): self.preflight()
    def test_new_curriculum_study_rejected(self):
        self.registered(); self.reg['study_id']='new-curriculum'
        with self.assertRaisesRegex(ValueError,'replica-1'): self.preflight()
    def test_training_limits_rejected(self):
        self.registered(); self.reg['limits']['work_seconds']=1790
        with self.assertRaisesRegex(ValueError,'limits differ'): self.preflight()
    def test_spent_outer_marker_rejected(self):
        self.registered(); Path(self.reg['one_shot_marker']).write_text('spent')
        with self.assertRaisesRegex(ValueError,'spent marker'): self.preflight()
    def test_spent_subclaim_rejected(self):
        self.registered(); Path(self.reg['attempt_claim_path']).write_text('spent')
        with self.assertRaisesRegex(ValueError,'spent marker'): self.preflight()
    def test_all_real_immutable_gates_before_outer_marker(self):
        self.registered(); self.preflight(); self.assertFalse(Path(self.reg['one_shot_marker']).exists())
    def test_reference_swap_fails_before_outer_marker(self):
        self.registered(); self.reg['reference']['receipt_path']='wrong'
        with self.assertRaisesRegex(ValueError,'reference binding'): self.preflight()
        self.assertFalse(Path(self.reg['one_shot_marker']).exists())

class ResultControls(ProbeControls):
    # Reuse toy setup, but do not inherit the test methods below twice.
    def make_result(self):
        result=self.call(); events=['runtime_authenticated_checkpoint_validated']+self.events+['cleanup_complete']
        row=dict(schema=p.RESULT_SCHEMA,status='verified_pending_parent_audit',run_id=self.reg['run_id'],registration_sha256='a'*64,study_id=p.STUDY,replica=1,arm=p.ARM,vector_sha256=self.reg['vector']['vector_sha256'],reference=self.reg['reference'],parent_fingerprints=self.expected,events=[dict(event=n,sequence=i,monotonic_ns=i) for i,n in enumerate(events)],runtime=__import__('synthetic_payload').runtime_fixture(self.reg),cleanup={k:{'status':'pass'} for k in ('synchronize_before_release','release_learner_and_parent','gc_collect','synchronize_after_release','empty_mps_cache','synchronize_after_cache')},scope=copy.deepcopy(p.SCOPE),resources=[dict(phase='final',elapsed_seconds=1.,rss_high_water_bytes=0,mps_driver_bytes=0)],**result)
        return row
    def validate(self,row):
        with patch.object(p,'EXPECTED',self.expected): return p.validate_result(self.reg,row,'a'*64)
    def test_result_strict_schema(self):
        row=self.make_result(); self.validate(row); row['extra']=True
        with self.assertRaisesRegex(ValueError,'fields differ'): self.validate(row)
    def test_result_event_schema_and_order(self):
        row=self.make_result(); row['events'][2]['sequence']=99
        with self.assertRaisesRegex(ValueError,'event result schema'): self.validate(row)
    def test_result_env_count_rejected(self):
        row=self.make_result(); row['counts']['environment_constructions']=1
        with self.assertRaisesRegex(ValueError,'counts differ'): self.validate(row)
    def test_result_wrong_reference_rehashed_semantics(self):
        row=self.make_result(); row['snapshots']['post_lr']['raw_components']['torch_cpu']='f'*64
        with self.assertRaisesRegex(ValueError,'LR no-op|reference state'): self.validate(row)
    def test_result_cleanup_failure_rejected(self):
        row=self.make_result(); row['cleanup']['empty_mps_cache']['status']='fail'
        with self.assertRaisesRegex(ValueError,'cleanup incomplete'): self.validate(row)
    def test_result_lr_override_mutation_rejected(self):
        row=self.make_result(); row['snapshots']['post_lr']['Adam']='f'*64
        with self.assertRaisesRegex(ValueError,'LR no-op'): self.validate(row)
# ResultControls uses fixture methods without duplicating the inherited controls.
for _name in list(ProbeControls.__dict__):
    if _name.startswith('test_') and _name not in ResultControls.__dict__: setattr(ResultControls,_name,None)

class WorkerCLIControls(unittest.TestCase):
    def run_case(self,mode):
        import os,signal,subprocess,time
        root=Path(tempfile.mkdtemp(prefix='worker-'+mode+'-',dir=p.HERE/'tmp'))
        process=subprocess.Popen([sys.executable,'-B',str(p.HERE/'synthetic_worker_driver.py'),mode,str(root)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=str(p.HERE/'empty-pycache')))
        if mode=='signal-bootstrap':
            deadline=time.monotonic()+6
            while not (root/'ready').exists() and process.poll() is None and time.monotonic()<deadline: time.sleep(.02)
            self.assertTrue((root/'ready').exists(),'synthetic worker failed to reach bootstrap')
            process.send_signal(signal.SIGTERM)
        log,_=process.communicate(timeout=15); (root/'driver.log').write_text(log)
        self.assertEqual(json.loads((root/'driver-scope.json').read_text())['real_runtime_modules'],[])
        return root,process.returncode,log
    def test_worker_cli_success_commits_only_after_cleanup(self):
        root,code,log=self.run_case('success'); self.assertEqual(code,0,log)
        row=json.loads((root/'out/result.json').read_text())
        self.assertEqual(row['counts']['restores'],1)
        self.assertEqual(row['events'][-1]['event'],'cleanup_complete')
        self.assertTrue(all(v['status']=='pass' for v in row['cleanup'].values()))
        self.assertTrue((root/'out/COMMITTED.json').exists())
    def failure(self,mode):
        root,code,log=self.run_case(mode); self.assertNotEqual(code,0,log)
        self.assertFalse((root/'out/COMMITTED.json').exists())
        return json.loads((root/'out/worker-failure.json').read_text())
    def test_worker_constructor_failure_still_releases(self):
        row=self.failure('constructor-failure')
        self.assertIn('constructor failure',row['error']); self.assertFalse(row['subclaim_exists'])
        self.assertEqual(len(row['cleanup']),6)
    def test_worker_mutating_restore_keeps_claim_and_partial_fingerprints(self):
        row=self.failure('mutating-restore'); self.assertTrue(row['subclaim_exists'])
        self.assertEqual(row['partial_probe']['counts']['restores'],1)
        self.assertIn('restored_before_reseed',row['partial_probe']['snapshots'])
    def test_worker_cleanup_failure_has_no_commit(self):
        row=self.failure('cleanup-failure')
        self.assertEqual(row['cleanup']['synchronize_before_release']['status'],'fail')
        self.assertEqual(row['cleanup']['empty_mps_cache']['status'],'pass')
        self.assertEqual(row['cleanup']['synchronize_after_cache']['status'],'fail')
    def test_worker_sigterm_before_claim_releases_and_records_signal(self):
        row=self.failure('signal-bootstrap')
        self.assertEqual(row['handled_signals'],['SIGTERM']); self.assertFalse(row['subclaim_exists'])
        self.assertEqual(len(row['cleanup']),6)

class ConsumerControls(RegistrationControls):
    def setUp(self):
        RegistrationControls.setUp(self); self.registered()
        self.rsha='a'*64
    def bundle(self):
        from synthetic_payload import publish_fixture
        return publish_fixture(self.reg,self.rsha)
    def mutate(self,fn):
        row=self.bundle(); fn(row)
        from synthetic_payload import publish_fixture
        publish_fixture(self.reg,self.rsha,row)
    def claim(self):
        self.modules=p.private_modules(); self.modules['attempt_claim'].AttemptClaim(self.reg['attempt_claim_path'],p.claim_identity(self.reg)).claim()
    def test_committed_bundle_and_raw_claim_pass(self):
        self.bundle(); self.claim(); self.assertEqual(p.committed_check(self.reg,self.rsha)['restores'],1)
    def test_rehashed_result_wrong_reference_rejected(self):
        self.mutate(lambda r:r['reference'].update(receipt_path='wrong')); self.claim()
        with self.assertRaisesRegex(ValueError,'reference/scope'): p.committed_check(self.reg,self.rsha)
    def test_rehashed_result_extra_event_field_rejected(self):
        self.mutate(lambda r:r['events'][0].update(extra=True)); self.claim()
        with self.assertRaisesRegex(ValueError,'event result schema'): p.committed_check(self.reg,self.rsha)
    def test_extra_candidate_artifact_rejected(self):
        self.bundle(); self.claim(); (Path(self.reg['output_dir'])/'checkpoint.pt').write_text('fake')
        with self.assertRaisesRegex(ValueError,'unexpected output'): p.committed_check(self.reg,self.rsha)
    def test_claim_payload_substitution_rejected(self):
        self.bundle(); self.claim(); Path(self.reg['attempt_claim_path']).write_text('{}')
        with self.assertRaisesRegex(ValueError,'subclaim differs'): p.committed_check(self.reg,self.rsha)
    def test_event_journal_divergence_rejected(self):
        self.bundle(); self.claim(); (Path(self.reg['output_dir'])/'events.jsonl').write_text('')
        with self.assertRaisesRegex(ValueError,'event journal differs'): p.committed_check(self.reg,self.rsha)
    def test_native_identity_substitution_rejected(self):
        self.mutate(lambda r:r['runtime']['loaded_modules'][1].update(sha256='f'*64)); self.claim()
        with self.assertRaisesRegex(ValueError,'native/runtime identity'): p.committed_check(self.reg,self.rsha)
    def test_boolean_restore_count_rejected(self):
        self.mutate(lambda r:r['counts'].update(restores=True)); self.claim()
        with self.assertRaisesRegex(ValueError,'strict integers'): p.committed_check(self.reg,self.rsha)
    def test_callback_source_substitution_rejected(self):
        self.mutate(lambda r:r['runtime'].update(trusted_callback_sources={'wrong':True})); self.claim()
        with self.assertRaisesRegex(ValueError,'callback source identities'): p.committed_check(self.reg,self.rsha)
    def test_rehashed_boolean_event_sequence_rejected(self):
        self.mutate(lambda r:r['events'][1].update(sequence=True)); self.claim()
        with self.assertRaisesRegex(ValueError,'event result schema'): p.committed_check(self.reg,self.rsha)
for _name in list(RegistrationControls.__dict__):
    if _name.startswith('test_') and _name not in ConsumerControls.__dict__: setattr(ConsumerControls,_name,None)

class SupervisorControls(RegistrationControls):
    def setUp(self):
        RegistrationControls.setUp(self); self.registered()
        # Retain every supervisor fixture and receipt under own tmp.
        self.temp._finalizer.detach(); self._cleanups=[]
    def run_synthetic(self,mode='success'):
        import os,subprocess
        import supervisor_cli as s
        reg=self.reg; rp=self.root/'registration.json'; rp.write_text(json.dumps(reg)); rsha=p.sha(rp)
        child=self.root/'fake_child.py'
        child.write_text("import sys\nfrom pathlib import Path\nsys.path.insert(0,"+repr(str(p.HERE))+")\nimport json,os,time\nimport probe as p\nfrom synthetic_payload import publish_fixture,semantic_fixture\na=sys.argv; rp=Path(a[a.index('--registration')+1]); reg=p.read(rp); rsha=a[a.index('--registration-sha256')+1]; hb=Path(a[a.index('--heartbeat')+1])\np.private_modules()['attempt_claim'].AttemptClaim(reg['attempt_claim_path'],p.claim_identity(reg)).claim()\nrow=semantic_fixture(reg,rsha)\n"+("row['counts']['forwards']=1\n" if mode=='bad-result' else '')+"publish_fixture(reg,rsha,row)\nhb.write_text(json.dumps(dict(run_id=reg['run_id'],registration_sha256=rsha,pid=os.getpid(),timestamp_ns=time.time_ns(),sequence=time.monotonic_ns(),rss_bytes=0,mps_driver_bytes=0)))\n")
        real_popen=subprocess.Popen
        def injected(cmd,*args,**kwargs):
            changed=list(cmd)
            if len(changed)>2 and changed[2]==str(p.HERE/'worker_cli.py'): changed[2]=str(child)
            return real_popen(changed,*args,**kwargs)
        # Only child executable is replaced. All new production registration,
        # marker, cleanup, process supervision and independent consumer paths run.
        with patch.object(s.subprocess,'Popen',injected):
            if mode=='bad-result':
                with self.assertRaisesRegex(RuntimeError,'postflight_failed'): s.execute(rp,rsha,p.HERE/'worker_cli.py')
            else: s.execute(rp,rsha,p.HERE/'worker_cli.py')
        return p.read(Path(reg['output_dir'])/'outer-receipt.json')
    def test_new_supervisor_lifecycle_and_consumer_success(self):
        row=self.run_synthetic(); self.assertEqual(row['raw_worker_exit_code'],0)
        self.assertTrue(row['process_group_absent']); self.assertTrue(row['claim_write_completed'])
        self.assertTrue(all(v['status']=='pass' for v in row['postflight'].values()))
        self.assertEqual(row['postflight']['restore_subclaim']['status'],'pass')
        self.assertEqual(row['status'],'accepted_pending_parent_postflight')
    def test_new_supervisor_rejects_semantically_bad_zero_exit_worker(self):
        row=self.run_synthetic('bad-result'); self.assertEqual(row['raw_worker_exit_code'],0)
        self.assertEqual(row['postflight']['committed_output']['status'],'fail')
        self.assertEqual(row['status'],'partial_failure_preserved'); self.assertTrue(row['process_group_absent'])
for _name in list(RegistrationControls.__dict__):
    if _name.startswith('test_') and _name not in SupervisorControls.__dict__: setattr(SupervisorControls,_name,None)


if __name__=='__main__': unittest.main(verbosity=2)
