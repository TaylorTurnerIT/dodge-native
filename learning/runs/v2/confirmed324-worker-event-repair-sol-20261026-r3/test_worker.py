"""Worker repairs checked with stdlib payloads and explicit fake instances."""
import copy
import hashlib
import inspect
import json
from pathlib import Path
import random
import tempfile
import time
import types
import unittest
from unittest.mock import patch

import build_registration
import contracts as c
import driver_binding as binding
import fingerprints as fp
import rng_reference as rr
import runtime_adapter as runtime
import test_regressions
import test_transition as fixtures
import transition
import worker
import worker_cli


class WorkerTests(unittest.TestCase):
    def fixture(self):
        value=fixtures.TransitionTests('test_success_saved_lr_noop_preserves_full_and_content_hash')
        value.setUp()
        self.addCleanup(value.doCleanups)
        return value

    def pins(self,value):
        return patch.object(transition,'_sha256_file',side_effect=lambda path: (
            rr.ACCEPTED_CHECKPOINT_SHA256 if str(path)==str(value.checkpoint) else rr.PARENT_RECEIPT_SHA256))

    def fake_bound_adapter(self,value):
        """Run real bootstrap and accepted binding builder against fake modules."""
        case=test_regressions.RegressionTests()
        root,checkpoint,runner=case._binding_fixtures()
        events=value.events
        old_random=random.getstate()
        self.addCleanup(random.setstate,old_random)
        # Real capture/restore bodies need clone/cpu operations; payloads stay bytes.
        class State(fixtures.ToyArray):
            def clone(self): return State(self.payload)
            def cpu(self): return self
        cpu=State(b'constructor-cpu'); mps=State(b'constructor-mps')
        numpy_state={'value':'constructor-numpy'}
        torch=__import__('sys').modules['torch']; numpy=__import__('sys').modules['numpy']
        saved_torch=dict(torch.__dict__); saved_numpy=dict(numpy.__dict__)
        def cleanup_modules():
            torch.__dict__.clear();torch.__dict__.update(saved_torch)
            numpy.__dict__.clear();numpy.__dict__.update(saved_numpy)
        self.addCleanup(cleanup_modules)
        def cpu_seed(seed):
            events.append('torch_cpu'); cpu.payload=f'cpu:{seed}'.encode(); torch.seed=seed
        def mps_seed(seed):
            events.append('torch_mps'); mps.payload=f'mps:{seed}'.encode()
        def set_cpu(state): events.append('restore_cpu'); cpu.payload=state.payload
        def set_mps(state): events.append('restore_mps'); mps.payload=state.payload
        torch.backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda:True))
        torch.manual_seed=cpu_seed;torch.initial_seed=lambda:torch.seed
        torch.get_rng_state=lambda:cpu;torch.set_rng_state=set_cpu
        torch.device=lambda value:types.SimpleNamespace(type=value)
        torch.float32='fake-float32'
        torch.mps=types.SimpleNamespace(manual_seed=mps_seed,get_rng_state=lambda:mps,set_rng_state=set_mps)
        numpy.random=types.SimpleNamespace(seed=lambda seed:(events.append('numpy'),numpy_state.update(value=seed)),
            get_state=lambda:numpy_state['value'],set_state=lambda value:numpy_state.update(value=value),
            RandomState=lambda seed:types.SimpleNamespace(get_state=lambda:seed))
        parent_model=copy.deepcopy(value.model.state_dict()); parent_adam=copy.deepcopy(value.optimizer.state_dict())
        class Model(fixtures.ToyModel):
            def __init__(self):
                events.append('construct_model');super().__init__();self.weights={'w':fixtures.ToyArray(b'disposable')}
            def to(self,**kw): return self
            def architecture_description(self): return {'fake':'architecture'}
            def parameters(self): return ['w']
            def load_state_dict(self,state,strict):
                self_test.assertTrue(strict);self_test.assertTrue(claim.exists());events.append('restore_model');self.weights=copy.deepcopy(state)
        class Adam(fixtures.ToyOptimizer):
            def __init__(self,parameters,lr,eps):
                events.append('construct_adam');super().__init__();self.state={}
            def load_state_dict(self,state):
                self_test.assertTrue(claim.exists());events.append('restore_adam')
                self.param_groups=copy.deepcopy(state['param_groups']);self.state=copy.deepcopy(state['state'])
        self_test=self
        claim=value.path/'worker.claimed'
        torch.optim=types.SimpleNamespace(Adam=Adam)
        parent_rng=dict(python=random.getstate(),numpy_global='parent-numpy',numpy_generator=None,
                        torch_cpu=State(b'parent-cpu'),torch_mps=State(b'parent-mps'),sampling_backend='torch_global_mps')
        adapter=runtime.RuntimeAdapter.__new__(runtime.RuntimeAdapter)
        adapter.parent=dict(model=parent_model,optimizer=parent_adam,rng=parent_rng,
                            identity={'architecture':{'fake':'architecture'}},tag='candidate',update_progress={'complete':True,'in_update':False})
        adapter.reg=dict(run_id='fake-bound-run',study_id=c.STUDY,replica=1,arm=c.ARMS[0],pair_id='fake-pair',
                         backend='mps',vector={'seeds':dict(fixtures.SEEDS),'vector_sha256':value.vector_hash},
                         attempt_claim_path=str(claim),reference={'receipt_path':str(value.reference_path),'receipt_sha256':value.ref_hash,'vector_sha256':value.vector_hash},
                         runtime_versions={'torch':fixtures.VERSION})
        adapter.torch=torch;adapter.np=numpy;adapter.teacher=types.SimpleNamespace(OmniscientEntityTeacher=Model)
        adapter.ckpt=checkpoint;adapter.runner=runner.__dict__
        adapter.context={'parent':{'checkpoint_path':str(value.checkpoint)}}
        # Source receipt verification is exercised independently in registration
        # tests; synthetic parent file pins below never deserialize accepted bytes.
        expected=dict(model=fp.fingerprint(parent_model),Adam=fp.fingerprint(parent_adam),RNG=fp.fingerprint(parent_rng))
        adapter.source=lambda:dict(receipt_sha256=rr.PARENT_RECEIPT_SHA256,checkpoint_sha256=rr.ACCEPTED_CHECKPOINT_SHA256,
            checkpoint_path=str(value.checkpoint),receipt_path=str(value.receipt_path),checkpoint_fingerprints=expected,learner_fingerprints=expected)
        # Rebind fake measured reference to the fake typed array representation.
        reference=json.loads(value.reference_path.read_bytes())
        reference['study_id']=c.STUDY
        reference['vector_sha256']=rr.canonical_vector_sha256(c.STUDY,1,fixtures.SEEDS)
        reference['cpu_rng_state_sha256']=fp.fingerprint(State(f'cpu:{fixtures.SEEDS["torch_cpu_global_seed"]}'.encode()))
        reference['mps_rng_state_sha256']=fp.fingerprint(State(f'mps:{fixtures.SEEDS["action_sampler_torch_mps_seed"]}'.encode()))
        value.reference_path.write_text(json.dumps(reference))
        adapter.reg['vector']['vector_sha256']=reference['vector_sha256']
        adapter.reg['reference'].update(receipt_sha256=c.sha(value.reference_path),vector_sha256=reference['vector_sha256'])
        return adapter,expected,claim,checkpoint

    def test_real_bootstrap_pinned_zeroarg_restore_claim_and_actual_return(self):
        value=self.fixture();adapter,expected,claim,checkpoint=self.fake_bound_adapter(value)
        with self.pins(value),patch.object(transition,'EXPECTED_PARENT',expected):
            result=worker.run_transition(adapter.reg,adapter)
        self.assertTrue(claim.exists())
        self.assertNotIn('status',result)
        self.assertEqual(result['parent_fingerprints'],expected)
        self.assertEqual(inspect.signature(adapter.callbacks['restore_trusted']).parameters,{})
        self.assertEqual(value.events.count('restore_model'),1)
        self.assertEqual(value.events.count('restore_adam'),1)
        self.assertLess(value.events.index('construct_adam'),value.events.index('restore_model'))
        self.assertLess(value.events.index('restore_model'),value.events.index('restore_cpu'))
        self.assertEqual(value.events[-3:],['numpy','torch_cpu','torch_mps'])
        self.assertEqual(result['seed_evidence']['torch_cpu_initial_seed'],fixtures.SEEDS['torch_cpu_global_seed'])
        # Callback globals stay private after caller namespace mutation.
        checkpoint.capture_rng=lambda *a:None
        self.assertEqual(set(adapter.callbacks['rng_capture']()),binding.RAW_RNG_KEYS)
        with self.pins(value),patch.object(transition,'EXPECTED_PARENT',expected),self.assertRaises(FileExistsError):
            worker.run_transition(adapter.reg,adapter)
        self.assertEqual(value.events.count('restore_model'),1)

    def test_post_transition_raw_rng_binding_failure_consumes_claim(self):
        value=self.fixture();adapter,expected,claim,checkpoint=self.fake_bound_adapter(value)
        original=transition.transition
        def corrupt(**kwargs):
            result=original(**kwargs)
            adapter.np.random.set_state('corrupted after reseed')
            return result
        with self.pins(value),patch.object(transition,'EXPECTED_PARENT',expected),patch.object(transition,'transition',side_effect=corrupt):
            with self.assertRaisesRegex(ValueError,'Python/NumPy readback'):
                worker.run_transition(adapter.reg,adapter)
        self.assertTrue(claim.exists())
        self.assertEqual(value.events.count('restore_model'),1)

    def test_mutating_restore_failure_spends_claim_and_never_double_invokes(self):
        value=self.fixture();adapter,expected,claim,checkpoint=self.fake_bound_adapter(value)
        # Fail the bound model state restore; no alternate callback is installed.
        def fail(state,strict):
            self.assertTrue(claim.exists());value.events.append('restore_failed');raise RuntimeError('fake restore failure')
        with patch.object(adapter.teacher.OmniscientEntityTeacher,'load_state_dict',side_effect=fail),self.pins(value),patch.object(transition,'EXPECTED_PARENT',expected):
            with self.assertRaisesRegex(RuntimeError,'fake restore failure'):
                worker.run_transition(adapter.reg,adapter)
            self.assertTrue(claim.exists())
            with self.assertRaises(FileExistsError):
                worker.run_transition(adapter.reg,adapter)
        self.assertEqual(value.events.count('restore_failed'),1)

    def registered_fake(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);path=Path(tmp.name)
        reg=copy.deepcopy(build_registration.template(1,c.ARMS[0]))
        reg['status']='parent_registered';reg['source_manifest_sha256']=c.sha(c.HERE/'source-manifest.json')
        reg['state_path']=str(path/'state.json');reg['launch_marker_path']=str(path/'marker.json')
        (path/'state.json').write_text(json.dumps({'active_long_campaign':reg['expected_lease']}))
        (path/'marker.json').write_text('{}')
        return reg,path

    def test_registered_status_accepted_not_draft_and_two_real_initial_digests(self):
        reg,path=self.registered_fake()
        context=c.verify_registration(reg)
        self.assertEqual(context['vector'],reg['vector'])
        self.assertEqual(len(rr.load_bound_reference(receipt_path=reg['reference']['receipt_path'],expected_receipt_sha256=reg['reference']['receipt_sha256'],expected_study_id=c.STUDY,expected_replica=1,expected_seed_vector=reg['vector']['seeds'],expected_vector_sha256=reg['vector']['vector_sha256'],expected_torch_version=reg['runtime_versions']['torch'])),2)
        reg['status']='parent_review_required_not_launchable'
        with self.assertRaisesRegex(ValueError,'unregistered'):
            c.verify_registration(reg)

    def test_bad_registration_bindings_before_bootstrap_claim_or_environment(self):
        reg,path=self.registered_fake()
        cases=[('backend','cpu'),('study_id','other'),('parent_checkpoint_sha256','0'*64),
               ('parent_receipt_sha256','0'*64),('replica',True),('schema','wrong')]
        for key,value in cases:
            with self.subTest(key=key),self.assertRaises(ValueError):
                c.verify_registration({**reg,key:value})
        for mutation in ('reference','vector','exclusions','indices','ppo'):
            bad=copy.deepcopy(reg)
            if mutation=='reference':bad['reference']['receipt_path']=str(path/'wrong-reference')
            if mutation=='vector':bad['vector']['seeds']['env_master_seed']+=1
            if mutation=='exclusions':bad['exclusion_union']=bad['exclusion_union'][:-1]
            if mutation=='indices':bad['initial_episode_indices'][0]+=1
            if mutation=='ppo':bad['ppo']['target_kl']=.04
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):c.verify_registration(bad)
        self.assertFalse(Path(reg['attempt_claim_path']).exists())
        self.assertFalse(Path(reg['output']).exists())

    def test_six_digests_or_wrong_measured_provenance_fail_before_claim(self):
        value=self.fixture()
        original=json.loads(value.reference_path.read_bytes())
        changes=[{'schema':'wrong'},{'backend':'cpu'},{'parent_receipt_sha256':'0'*64},
                 {'accepted_checkpoint_sha256':'0'*64},{'torch_version':'other'},
                 {'study_id':'curriculum-independent-other-study'},{'replica':2},
                 {'extra_digest':'0'*64},{'vector_sha256':'0'*64}]
        for change in changes:
            value.reference_path.write_text(json.dumps({**original,**change}))
            with self.subTest(change=change),self.pins(value),patch.object(transition,'EXPECTED_PARENT',value.expected),self.assertRaises(ValueError):
                value.call(reference={'receipt_path':value.reference_path,'receipt_sha256':c.sha(value.reference_path),'vector_sha256':value.vector_hash})
            self.assertFalse((value.path/'durable-attempt.claimed').exists())
            self.assertEqual(value.restores,0)

    def test_new_loop_counters_lr_metrics_candidates_no_selection(self):
        for arm in c.ARMS:
            tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);out=Path(tmp.name)
            parent=dict(updates=372,optimizer_steps=46496,environment_decisions=6094848,raw_frames=24345721)
            adapter=runtime.RuntimeAdapter.__new__(runtime.RuntimeAdapter)
            adapter.parent={'abandoned_current_episodes':[{'fake':'abandoned'}]}
            adapter.context={'parent':{'candidate_cumulative_counters':parent}}
            adapter.optimizer=fixtures.ToyOptimizer();adapter.runner=runtime.runner_namespace()
            adapter.env=types.SimpleNamespace(episode_info=lambda:[],batch_info=lambda:{'next_episode_indices':[1]*64})
            events=[];lrs=[];saved=[]
            adapter.make_env=lambda:events.append('env')
            batch=types.SimpleNamespace(actions=types.SimpleNamespace(numel=lambda:16384),elapsed_raw_frames=types.SimpleNamespace(sum=lambda:types.SimpleNamespace(item=lambda:65536)))
            def update(guard,progress,journal_collection_events):
                lrs.append(adapter.optimizer.param_groups[0]['lr']);progress.update(complete=True,in_update=False,optimizer_steps=32)
                journal_collection_events([],[])
                return dict(optimizer_steps=32,actor_grad_norm=1,critic_grad_norm=1,raw_fake_metric=7),types.SimpleNamespace(batch=batch,completed_episodes=[],reset_info=[])
            def candidate(out,local,counters,progress,*args):
                self.assertEqual(progress['completed_updates'],local);saved.append(local)
                return dict(checkpoint=f'checkpoint-{324+local:06d}-candidate.pt',local_update=local)
            adapter.update=update;adapter.candidate=candidate
            result=worker.study_loop({'arm':arm},adapter,out,types.SimpleNamespace(check=lambda:None),'fake-registration',time.monotonic())
            self.assertEqual(saved,[12,24,36,48,60]);self.assertEqual(result['cumulative_counters']['updates'],432)
            self.assertEqual(result['cumulative_counters']['optimizer_steps'],46496+60*32)
            self.assertEqual(result['cumulative_counters']['environment_decisions'],6094848+60*16384)
            self.assertEqual(result['cumulative_counters']['raw_frames'],24345721+60*65536)
            self.assertEqual(lrs[0],3e-5);self.assertEqual(lrs[-1],3e-5 if arm==c.ARMS[0] else 1e-5)
            self.assertFalse(result['automatic_selection']);self.assertEqual(result['evaluated_updates'],[])
            rows=[json.loads(line) for line in (out/'training-metrics.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows),60);self.assertEqual(rows[0]['phase_update'],325);self.assertEqual(rows[-1]['phase_update'],384)
            self.assertEqual(rows[-1]['metrics']['raw_fake_metric'],7)

    def test_unregistered_cli_stops_before_any_runtime_factory(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);path=Path(tmp.name)/'draft.json'
        path.write_text(json.dumps(build_registration.template(1,c.ARMS[0])))
        with patch.object(worker,'RuntimeAdapter',side_effect=AssertionError('must not import runtime')):
            with self.assertRaisesRegex(ValueError,'unregistered'):
                worker_cli.validate(path,c.sha(path),path,c.sha(path),time.monotonic())

    def test_no_duck_transition_adapter(self):
        with self.assertRaisesRegex(ValueError,'concrete runtime'):
            worker.run_transition({},types.SimpleNamespace(bootstrap=lambda:None))


class AdditionalWorkerTests(unittest.TestCase):
    fixture=WorkerTests.fixture
    pins=WorkerTests.pins
    registered_fake=WorkerTests.registered_fake

    def test_validation_only_cli_accepts_exact_synthetic_parent_gates(self):
        reg,path=self.registered_fake()
        started=time.monotonic()
        reg['import_policy']=dict(pycache_prefix=str(c.HERE/'empty-pycache'),dont_write_bytecode=True)
        registered=path/'synthetic-registration.json';registered.write_text(json.dumps(reg))
        digest=c.sha(registered)
        Path(reg['launch_marker_path']).write_text(json.dumps(dict(schema='paired_worker_parent_launch_marker_v2',run_id=reg['run_id'],registration_sha256=digest,started=started)))
        accepted=path/'synthetic-source-acceptance.json'
        accepted.write_text(json.dumps(dict(schema='paired_worker_parent_source_acceptance_v2',status='accepted_for_one_registered_worker',registration_sha256=digest,source_manifest_sha256=reg['source_manifest_sha256'],run_id=reg['run_id'])))
        with patch.object(worker,'RuntimeAdapter',side_effect=AssertionError('validation must stay stdlib')):
            actual,context=worker_cli.validate(registered,digest,accepted,c.sha(accepted),started)
            self.assertEqual(actual,reg)
            with self.assertRaisesRegex(ValueError,'source acceptance SHA'):
                worker_cli.validate(registered,digest,accepted,'0'*64,started)
            Path(reg['launch_marker_path']).write_text('{}')
            with self.assertRaisesRegex(ValueError,'launch marker'):
                worker_cli.validate(registered,digest,accepted,c.sha(accepted),started)
        self.assertFalse(Path(reg['attempt_claim_path']).exists())

    def test_model_mutation_during_reseed_and_wrong_rng_readback_spend_claim(self):
        for failure in ('model','cpu','mps','raw_capture'):
            value=self.fixture()
            if failure=='model':
                original=value.fake_torch.mps.manual_seed
                def mutate(seed):
                    original(seed);value.model.weights['w']=fixtures.ToyArray(b'changed')
                value.fake_torch.mps.manual_seed=mutate
            elif failure=='cpu':value.fake_torch.get_rng_state=lambda:b'wrong-cpu-state'
            elif failure=='mps':value.fake_torch.mps.get_rng_state=lambda:b'wrong-mps-state'
            else:value.capture_rngpayload=lambda:{'normalized':'not raw six keys'}
            with self.subTest(failure=failure),self.pins(value),patch.object(transition,'EXPECTED_PARENT',value.expected),self.assertRaises(ValueError):
                value.call()
            self.assertTrue((value.path/'durable-attempt.claimed').exists())
            self.assertEqual(value.restores,1)

    def test_exclusion_and_all64_seed_controls_before_environment(self):
        for replica in (1,2,3):
            reg=build_registration.template(replica,c.ARMS[0])
            rows=c.episode_controls(reg['vector'])
            self.assertEqual(len(rows),64)
            adapter=runtime.RuntimeAdapter.__new__(runtime.RuntimeAdapter)
            adapter.reg=copy.deepcopy(reg);adapter.context={'controls':rows}
            adapter.game=types.SimpleNamespace(VecDodgeEnv=lambda **kw:self.fail('environment must not be constructed'))
            adapter.reg['vector']['env_control']['all_slots_actual_seed_sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'all-slot seed digest'):
                adapter.make_env()

    def test_actual_candidate_method_saves_complete_bound_state_once(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);out=Path(tmp.name)
        adapter=runtime.RuntimeAdapter.__new__(runtime.RuntimeAdapter)
        adapter.reg=build_registration.template(1,c.ARMS[1])
        receipt=c.read(c.ROOT/c.PARENT_RECEIPT)
        adapter.context={'parent':receipt}
        adapter.parent={'identity':{'version':'fake-source-identity','config':c.read(c.read(c.HERE/'input-manifest.json')['config_path'])},'abandoned_current_episodes':[]}
        adapter.model=fixtures.ToyModel();adapter.optimizer=fixtures.ToyOptimizer()
        adapter.optimizer.param_groups[0]['lr']=1e-5
        adapter.env=types.SimpleNamespace(episode_info=lambda:[],batch_info=lambda:{'next_episode_indices':[2]*64})
        adapter.callbacks={'rng_capture':lambda:dict(python=1,numpy_global=2,numpy_generator=None,torch_cpu=b'cpu',torch_mps=b'mps',sampling_backend='torch_global_mps')}
        adapter.runner=runtime.runner_namespace()
        adapter.identity_module=types.SimpleNamespace(identity_hash=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest())
        captured=[]
        def save_checkpoint(path,state):
            captured.append(copy.deepcopy(state))
            with path.open('xb') as stream:stream.write(b'CPU fake checkpoint; not an accepted model')
            return c.sha(path)
        adapter.ckpt=types.SimpleNamespace(episode_resume_state=lambda env,count:([2]*64,[]),_cpu_copy=copy.deepcopy,save_checkpoint=save_checkpoint)
        counters=dict(updates=60,optimizer_steps=1920,environment_decisions=983040,raw_frames=3932160)
        progress=dict(complete=True,in_update=False,completed_updates=60)
        result=adapter.candidate(out,60,counters,progress,'f'*64,time.monotonic())
        state=captured[0]
        self.assertEqual(state['phase_update'],384);self.assertEqual(state['local_update'],60)
        self.assertEqual(state['cumulative_counters']['updates'],432)
        self.assertEqual(state['optimizer']['param_groups'][0]['lr'],1e-5)
        self.assertEqual(state['rng']['sampling_backend'],'torch_global_mps')
        self.assertEqual(state['parent_checkpoint_sha256'],rr.ACCEPTED_CHECKPOINT_SHA256)
        self.assertEqual(state['identity']['paired_study']['seed_vector'],adapter.reg['vector']['seeds'])
        self.assertFalse(result['automatic_selection']);self.assertFalse(state['training_eligible']);self.assertFalse(state['promoted'])
        with self.assertRaises(FileExistsError):adapter.candidate(out,60,counters,progress,'f'*64,time.monotonic())
        with self.assertRaisesRegex(ValueError,'incomplete'):
            adapter.candidate(out,60,counters,{**progress,'in_update':True},'f'*64,time.monotonic())

    def test_incomplete_update_retains_progress_and_saves_no_candidate(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);out=Path(tmp.name)
        adapter=runtime.RuntimeAdapter.__new__(runtime.RuntimeAdapter)
        adapter.parent={'abandoned_current_episodes':[]}
        adapter.optimizer=fixtures.ToyOptimizer()
        adapter.env=types.SimpleNamespace(episode_info=lambda:[],batch_info=lambda:{})
        adapter.make_env=lambda:None
        def fail(guard,progress,journal_collection_events):
            progress.update(complete=False,in_update=True,optimizer_steps=1)
            raise RuntimeError('synthetic partial optimizer failure')
        adapter.update=fail
        adapter.candidate=lambda *args:self.fail('partial update must never save')
        result={}
        with self.assertRaisesRegex(RuntimeError,'partial optimizer failure'):
            worker.study_loop({'arm':c.ARMS[0]},adapter,out,types.SimpleNamespace(check=lambda:None),'f'*64,time.monotonic(),result)
        self.assertTrue(result['update_progress']['in_update'])
        self.assertFalse(result['update_progress']['complete'])
        self.assertEqual(result['counters']['updates'],0)
        self.assertEqual(result['candidates'],[])


if __name__=='__main__':unittest.main(verbosity=2)
