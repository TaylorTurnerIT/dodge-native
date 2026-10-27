"""Pure/synthetic controller tests. No teacher/native/MPS imports or ML updates.

AST-loaded unchanged legacy validators execute in explicit synthetic namespaces;
only dependency bindings are fake, never their function bodies. Integration
fixtures run the actual new supervisor against an OS-owned stdlib fake worker.
"""
import ast
import builtins
import copy
from contextlib import contextmanager, nullcontext
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch, Mock

HERE=Path(__file__).resolve().parent
source=Path(os.environ.get('LONG_D2_TEST_SOURCE',str(HERE/'long_d2.py')))
spec=importlib.util.spec_from_file_location('long_d2_under_test',source)
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
ROOT=c.ORIGINAL_ROOT
PROTOCOL=c.registered_protocol(ROOT/c.PROTOCOL_REL)
CONFIG=c.read_json(ROOT/PROTOCOL['config_path'])
BASE=c.read_json(ROOT/PROTOCOL['base_config_path'])
OLD=c.read_json(ROOT/'docs/v2-m3-run-protocol.json')


class Clock:
    def __init__(self,at=0):self.at=at
    def __call__(self):return self.at
    def advance(self,n):self.at+=n


class FakeGuard:
    def __init__(self,deadline=7140,*args,clock=None,**kwargs):
        self.deadline=deadline;self.clock=clock or Clock();self.failure=None
    def check(self,force=False):
        c.require(self.clock()<self.deadline,'fixture wall','wall_guard')
    def start(self):pass
    def sample(self,force=False):pass
    def close(self):self.check()
    def receipt(self):return {}


class FakeLearner:
    def __init__(self,clock,guard,*,gate=10000,update_wall=1,entry_wall=1,periodic_wall=0):
        self.clock,self.guard,self.gate=clock,guard,gate
        self.update_wall,self.entry_wall,self.periodic_wall=update_wall,entry_wall,periodic_wall
        self.counters=dict(phase_updates=0)
        self.records=[];self.evaluations=[];self.updates=[]
    def checkpoint(self,tag):
        self.records.append(dict(tag=tag,evaluated=False,phase=self.counters['phase_updates']))
        if tag=='long_periodic':self.clock.advance(self.periodic_wall)
        return self.records[-1]
    def evaluate_checkpoint(self,entry=False):
        self.evaluations.append(self.counters['phase_updates'])
        r=self.checkpoint('long_evaluated');r['evaluated']=True
        self.clock.advance(self.entry_wall)
        return r,self.counters['phase_updates']>=self.gate,self.entry_wall
    def update_once(self):
        self.guard.check()
        self.clock.advance(self.update_wall)
        self.counters['phase_updates']+=1;self.updates.append(self.counters['phase_updates'])
    def report(self):return dict(phase_updates=self.counters['phase_updates'])


def lease():
    return c.expected_lease(PROTOCOL,'a'*64,'b'*64,Path('/capsule'),'c'*64)


def legacy_functions(relative,names,namespace):
    tree=ast.parse((ROOT/relative).read_text())
    nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),relative,'exec'),namespace)
    return namespace


class ConfigTests(unittest.TestCase):
    def test_exact_registered(self):
        self.assertIs(c.validate_long_config(CONFIG,BASE,PROTOCOL,OLD),CONFIG)
    def test_every_config_leaf_mutation(self):
        leaves=[]
        def walk(value,path=()):
            if isinstance(value,dict):
                for k,v in value.items():walk(v,path+(k,))
            elif isinstance(value,list):
                for k,v in enumerate(value):walk(v,path+(k,))
                if not value:leaves.append(path)
            else:leaves.append(path)
        walk(CONFIG)
        for path in leaves:
            with self.subTest(path=path):
                bad=copy.deepcopy(CONFIG);target=bad
                for key in path[:-1]:target=target[key]
                old=target[path[-1]]
                target[path[-1]]=(not old if type(old) is bool else old+1 if type(old) in (int,float)
                                  else old+'x' if isinstance(old,str) else ['extra'])
                with self.assertRaises(c.Stop):c.validate_long_config(bad,BASE,PROTOCOL,OLD)
    def test_every_config_key_missing_and_extra(self):
        for key in CONFIG:
            with self.subTest(key=key):
                bad=copy.deepcopy(CONFIG);del bad[key]
                with self.assertRaises(c.Stop):c.validate_long_config(bad,BASE,PROTOCOL,OLD)
        bad={**CONFIG,'unknown':1}
        with self.assertRaises(c.Stop):c.validate_long_config(bad,BASE,PROTOCOL,OLD)
    def test_budget_7199_7201_and_bool_type(self):
        for seconds in (7199,7201,True):
            bad=copy.deepcopy(CONFIG);bad['phase_settings']['budget_seconds']=seconds
            with self.assertRaises(c.Stop):c.validate_long_config(bad,BASE,PROTOCOL,OLD)
    def test_all_registered_seed_collisions(self):
        for row in OLD['seed_namespace_table'].values():
            for key in ('run_seed','initialization_seed'):
                if key not in row:continue
                bad=copy.deepcopy(CONFIG);bad['phase_settings']['run_seed']=row[key]
                # Even a proposed authority agreeing with the seed cannot collide.
                p=copy.deepcopy(PROTOCOL);p['config']=bad
                with self.assertRaises(c.Stop):c.validate_long_config(bad,BASE,p,OLD)
    def test_changed_base_learner_rejected(self):
        for key in set(BASE)-{'version','phase','phase_settings'}:
            bad=copy.deepcopy(BASE);bad[key]=None
            with self.assertRaises(c.Stop):c.validate_long_config(CONFIG,bad,PROTOCOL,OLD)
    def test_duplicate_nonfinite_json(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.json'
            for raw in ('{"a":1,"a":2}','{"a":NaN}'):
                p.write_text(raw)
                with self.assertRaises(c.Stop):c.read_json(p)


class LeaseTests(unittest.TestCase):
    def check(self,value):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'state.json';p.write_text(json.dumps({'active_long_campaign':value}))
            return c.assert_lease(p,lease())
    def test_exact(self):self.assertEqual(self.check(lease()),lease())
    def test_each_lease_key_missing(self):
        for k in lease():
            bad=lease();del bad[k]
            with self.subTest(key=k),self.assertRaises(c.Stop):self.check(bad)
    def test_each_lease_field_tamper(self):
        for k in lease():
            bad=lease();bad[k]='changed'
            with self.subTest(key=k),self.assertRaises(c.Stop):self.check(bad)
    def test_extra_and_legacy_kind(self):
        for bad in ({**lease(),'taskId':'outside-only'},{**lease(),'kind':'M3_teacher'}):
            with self.assertRaises(c.Stop):self.check(bad)
    def test_all_eight_anchor_fields(self):
        for k in lease()['parent_terminal_receipt']:
            bad=copy.deepcopy(lease());bad['parent_terminal_receipt'][k]='tamper'
            with self.subTest(key=k),self.assertRaises(c.Stop):self.check(bad)
    def test_cancellation_outcome(self):
        with self.assertRaises(c.Stop) as e:self.check({**lease(),'cancel_requested':True})
        self.assertEqual(e.exception.outcome,'cancelled')


class IdentityTests(unittest.TestCase):
    def test_raw_and_semantic_distinct(self):
        self.assertNotEqual(c.sha(ROOT/PROTOCOL['config_path']),c.semantic_hash(CONFIG))
        self.assertEqual(c.sha(ROOT/PROTOCOL['config_path']),c.CONFIG_SHA256)
    def test_each_legacy_byte_pin(self):
        self.assertEqual(len(PROTOCOL['base_identity']['sources']),75)
        c.verify_files({str(ROOT/k):v for k,v in PROTOCOL['base_identity']['sources'].items()})
    def test_module_origins_and_mirrors(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve();original=root/'original.py';original.write_text('pinned')
            mirror=root/'mirror.py';mirror.write_text('pinned')
            i={'legacy_module_origins':{str(original):dict(sha256=c.sha(original),mirror='mirror.py')}}
            modules={'dodge_rl.fake':types.SimpleNamespace(__file__=str(original))}
            self.assertIn('dodge_rl.fake',c.check_module_origins(i,root,modules))
            mirror.write_text('changed')
            with self.assertRaises(c.Stop):c.check_module_origins(i,root,modules)
            mirror.write_text('pinned')
            modules['dodge_rl.fake'].__file__=str(mirror)
            with self.assertRaises(c.Stop):c.check_module_origins(i,root,modules)
    def test_namespace_without_origin_rejected(self):
        with self.assertRaises(c.Stop):c.check_module_origins({'legacy_module_origins':{}},Path('/x'),{'dodge_rl':object()})
    def test_readonly_inventory_permissions_and_escape(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve()/'capsule';root.mkdir()
            (root/'x').write_text('x');(root/'capsule-manifest.json').write_text('{}')
            m={'version':'long_d2_capsule_v1','files':{'x':c.sha(root/'x')}}
            with self.assertRaises(c.Stop):c.assert_readonly_capsule(root,m)
            for p in root.iterdir():p.chmod(0o444)
            root.chmod(0o555)
            try:c.assert_readonly_capsule(root,m)
            finally:root.chmod(0o755)
            (root/'extra').write_text('unexpected');(root/'extra').chmod(0o444);root.chmod(0o555)
            try:
                with self.assertRaises(c.Stop):c.assert_readonly_capsule(root,m)
            finally:root.chmod(0o755)
            with self.assertRaises(c.Stop):c.safe_member(root,'../escape')
    def test_freeze_and_preflight_import_purity(self):
        for file in ('long_d2.py','freeze.py'):
            tree=ast.parse((HERE/file).read_text())
            top=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))]
            names=[a.name for n in top if isinstance(n,ast.Import) for a in n.names]
            self.assertFalse(set(names)&{'torch','numpy','dodge_rl'})


class LegacyTests(unittest.TestCase):
    def namespace(self):
        def require(ok,message):
            if not ok:raise ValueError(message)
        return dict(Path=Path,json=json,math=__import__('math'),require=require,read_protocol=lambda:OLD,
                    file_hash=c.sha,ROOT=ROOT,STATE_PATH=Path('/fake'),_UNSET=object(),GuardStop=RuntimeError,
                    copy=copy,identity_hash=c.semantic_hash)
    def test_old_lease_rejects_new_kind(self):
        ns=self.namespace();legacy_functions('python/dodge_rl/supervision.py',{'assert_lease'},ns)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'state';path.write_text(json.dumps({'active_long_campaign':lease()}))
            with self.assertRaisesRegex(ValueError,'not authorized'):
                ns['assert_lease'](PROTOCOL['run_id'],'c'*64,c.CONFIG_SHA256,path)
    def test_old_config_unknown_long_phase(self):
        ns=self.namespace();original_import=builtins.__import__
        def imports(name,*args,**kwargs):
            if name=='ppo':return types.SimpleNamespace(PPOConfig=object)
            return original_import(name,*args,**kwargs)
        ns['__builtins__']={**vars(builtins),'__import__':imports}
        legacy_functions('python/dodge_rl/identity.py',{'default_config','validate_config'},ns)
        with self.assertRaisesRegex(ValueError,'Unknown registered phase'):ns['validate_config'](CONFIG)
    def test_old_terminal_rejects_long_anchor_before_load(self):
        ns=self.namespace();legacy_functions('python/dodge_rl/checkpoints.py',{'validate_terminal_receipt'},ns)
        anchor={**PROTOCOL['parent_terminal_receipt'],'phase':'long_D2'}
        with self.assertRaisesRegex(ValueError,'not a registered'):ns['validate_terminal_receipt'](Path('/no-output'),anchor)
    def test_failed_D2_terminal_and_transition_before_load(self):
        ns=self.namespace();ns['load_checkpoint']=Mock(side_effect=AssertionError('must not deserialize'))
        legacy_functions('python/dodge_rl/checkpoints.py',{'validate_terminal_receipt','validate_transition'},ns)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve();path=root/'run-result.json';path.write_text(json.dumps({'status':'failed'}))
            anchor={**PROTOCOL['parent_terminal_receipt'],'phase':'D2','run_result_sha256':c.sha(path)}
            for name in ('checkpoint-000022-candidate.pt','checkpoint-000023-periodic.pt','checkpoint-000024-interrupted_mid_update.pt'):
                with self.assertRaisesRegex(ValueError,'did not finish successfully'):
                    ns['validate_transition'](root/name,PROTOCOL['base_identity'],terminal_anchor=anchor)
            ns['load_checkpoint'].assert_not_called()
    def test_partial_parent_rejected(self):
        ns=self.namespace();legacy_functions('python/dodge_rl/checkpoints.py',{'require_complete_update'},ns)
        for state in ({'tag':'interrupted_mid_update'},{'tag':'candidate','update_progress':{'in_update':True}},
                      {'tag':'candidate','update_progress':{'complete':False}}):
            with self.assertRaises(ValueError):ns['require_complete_update'](state)
    def test_legacy_budget_and_cutoff_unchanged(self):
        from datetime import datetime,timedelta,timezone
        ns=self.namespace();ns.update(datetime=datetime,timedelta=timedelta,
              CUTOFF=datetime(2026,10,24,13,tzinfo=timezone.utc))
        legacy_functions('python/dodge_rl/supervision.py',{'check_budget'},ns)
        with self.assertRaisesRegex(ValueError,'Invalid experiment budget'):
            ns['check_budget'](datetime(2026,10,24,0,tzinfo=timezone.utc),7200)


class ScheduleTests(unittest.TestCase):
    def run_fake(self,remaining,**kwargs):
        clock=Clock();guard=FakeGuard(remaining,clock=clock);learner=FakeLearner(clock,guard,**kwargs)
        result=c.run_schedule(learner,guard,io.StringIO(),clock=clock)
        return result,learner,clock
    def test_admission_boundary(self):
        for delta,updates in ((0,16),(-0.0001,0)):
            result,l,_=self.run_fake(611+delta)
            self.assertEqual(len(l.updates),updates)
            self.assertEqual(c.result_code(result),2)
    def test_pre_entry_reserve_inclusive(self):
        result,l,_=self.run_fake(195,entry_wall=0)
        self.assertEqual(l.evaluations,[0]);self.assertEqual(c.result_code(result),2)
        with self.assertRaises(c.Stop):self.run_fake(194.999)
    def test_gate_pass_stops_at_16(self):
        r,l,_=self.run_fake(2000,gate=16)
        self.assertEqual(l.evaluations,[0,16]);self.assertEqual(len(l.updates),16)
        self.assertEqual(c.result_code(r),0);self.assertTrue(r['progression_gate_passed'])
        self.assertFalse(r['training_parent_eligible']);self.assertFalse(r['teacher_qualified'])
    def test_budget_closure_not_pass(self):
        r,l,_=self.run_fake(610)
        self.assertEqual(l.evaluations,[0]);self.assertEqual(c.result_code(r),2)
        self.assertFalse(r['progression_gate_passed']);self.assertTrue(r['final_checkpoint_evaluated'])
    def test_slowdown_closes_without_offcadence_eval(self):
        r,l,_=self.run_fake(700,update_wall=100)
        self.assertEqual(l.evaluations,[0]);self.assertEqual(len(l.updates),1)
        self.assertEqual(l.records[-1]['tag'],'long_closure_unevaluated')
        self.assertFalse(r['final_checkpoint_evaluated']);self.assertEqual(c.result_code(r),2)
    def test_periodic_checkpoint_in_update_bound(self):
        r,l,_=self.run_fake(1000,periodic_wall=100)
        self.assertEqual(l.evaluations,[0]);self.assertEqual(len(l.updates),8)
        self.assertEqual(l.records[-2]['tag'],'long_periodic')
        self.assertGreater(r['schedule']['U'],125)
    def test_reserves_only_grow(self):
        s=c.Schedule();s.update_wall(30);s.evaluation_wall(60)
        self.assertEqual((s.U,s.E),(37.5,180))
        s.update_wall(1);s.evaluation_wall(1)
        self.assertEqual((s.U,s.E),(37.5,180))
    def test_remaining_checkpoint_counts(self):
        s=c.Schedule()
        self.assertEqual(s.remaining_cost(0),610)
        self.assertEqual(s.remaining_cost(7),435)
        self.assertEqual(s.remaining_cost(8),395)
        self.assertEqual(s.remaining_cost(15),220)
    def test_no_eval_when_postblock_reserve_unavailable(self):
        clock=Clock();guard=FakeGuard(2000,clock=clock);l=FakeLearner(clock,guard)
        original=l.update_once
        def final_slow():
            original()
            if l.counters['phase_updates']==16:clock.at=1900
        l.update_once=final_slow
        r=c.run_schedule(l,guard,io.StringIO(),clock=clock)
        self.assertEqual(l.evaluations,[0]);self.assertEqual(l.records[-1]['tag'],'long_closure_unevaluated')
        self.assertEqual(c.result_code(r),2)


class StateTests(unittest.TestCase):
    def test_bitwise_model_adam_rng_changes(self):
        parent={'model':{'w':b'\x01'},'Adam':{'moments':b'\x02','step':6144},
                'RNG':{'python':(1,2),'numpy_global':b'\x03','torch_cpu':b'\x04','torch_mps':b'\x05'}}
        for key in parent:
            self.assertEqual(c.assert_equal_tree(parent[key],copy.deepcopy(parent[key]),key),
                             c.semantic_hash(c.tree_fingerprint(parent[key])))
            bad=copy.deepcopy(parent[key]);bad[next(iter(bad))]=b'changed'
            with self.subTest(field=key),self.assertRaises(c.Stop):c.assert_equal_tree(bad,parent[key],key)
        for key in parent['RNG']:
            bad=copy.deepcopy(parent['RNG']);bad[key]=b'one-byte-change'
            with self.subTest(RNG=key),self.assertRaises(c.Stop):c.assert_equal_tree(bad,parent['RNG'],'RNG')
    def test_type_and_float_bits_matter(self):
        with self.assertRaises(c.Stop):c.assert_equal_tree(1,True,'type')
        self.assertNotEqual(c.semantic_hash(c.tree_fingerprint(-0.0)),c.semantic_hash(c.tree_fingerprint(0.0)))
    def test_control_all_fields_and_completion_order(self):
        rows=c.read_json(ROOT/PROTOCOL['entry_control'])['evaluations']['D2']['rows']
        self.assertTrue(c.compare_control(list(reversed(rows)),rows)['matched'])
        for key in c.ROW_KEYS:
            bad=copy.deepcopy(rows);value=bad[0][key]
            bad[0][key]=not value if type(value) is bool else value+1
            with self.subTest(field=key),self.assertRaises(c.Stop):c.compare_control(bad,rows)
        with self.assertRaises(c.Stop):c.compare_control(rows[:-1]+[rows[0]],rows)
    def test_fresh_seed_and_exclusions(self):
        ns=dict(Path=Path,require=c.require,validate_config=lambda config:config)
        legacy_functions('python/dodge_rl/identity.py',{'training_env_config','verify_training_env'},ns)
        ns['read_protocol']=lambda:OLD
        old=ns['training_env_config'](BASE,[0]*64)
        fresh=c.environment_kwargs(old,CONFIG)
        self.assertEqual([k for k in old if old[k]!=fresh[k]],['run_seed'])
        infos=[dict(seed=dict(slot=i,episode=0,evaluation=False,actual_seed=i+10),
                    startup_frames=13,gameplay_frames=0) for i in range(64)]
        metadata=dict(effective_excluded_seed_ranges=CONFIG['excluded_seed_ranges'],
                      seed_stream_version=OLD['seed_stream_version'],seed_exclusion_version=OLD['seed_exclusion_version'],
                      seed_mode=dict(mode='training',run_seed=CONFIG['phase_settings']['run_seed']),
                      initial_episode_indices=[0]*64,batch_size=64,action_repeat=4)
        env=types.SimpleNamespace(batch_info=lambda:metadata,episode_info=lambda:infos)
        ns['verify_training_env'](env,CONFIG,[0]*64)
        infos[0]['seed']['actual_seed']=2952790016
        with self.assertRaises(c.Stop):ns['verify_training_env'](env,CONFIG,[0]*64)
        infos[0]['seed']['actual_seed']=10;metadata['seed_mode']['run_seed']=BASE['phase_settings']['run_seed']
        with self.assertRaises(c.Stop):ns['verify_training_env'](env,CONFIG,[0]*64)
    def test_inherited_phase_and_partial_optimizer_accounting(self):
        counters={**c.PARENT_COUNTERS,'phase_updates':2,'updates':50,'optimizer_steps':6400,
                  'environment_decisions':819200,'raw_frames':3270624}
        r=c.counter_report(counters,c.PARENT_COUNTERS,dict(in_update=True,optimizer_steps=7))
        self.assertEqual(r['phase']['updates'],2);self.assertEqual(r['phase']['optimizer_steps'],256)
        self.assertEqual(r['actual_optimizer_steps_including_partial'],6407)
        self.assertEqual(r['partial_optimizer_steps'],7)
        self.assertEqual(c.counter_report(counters,c.PARENT_COUNTERS,dict(in_update=False,optimizer_steps=128))
                         ['partial_optimizer_steps'],0)
    def test_nonfinite_nested_metrics(self):
        for n in (float('nan'),float('inf'),-float('inf')):
            with self.assertRaises(c.Stop) as e:c.require_finite({'a':[n]})
            self.assertEqual(e.exception.outcome,'safety_stop')


def learner_fixture(output,*,rng_change=False,weight_change=False,adam_change=False,control_change=False):
    parent=dict(counters=copy.deepcopy(c.PARENT_COUNTERS),model={'w':b'weight'},optimizer={'moment':b'Adam'},
                rng={'python':b'p','numpy_global':b'n','torch_cpu':b'c','torch_mps':b'm'},
                abandoned_episodes=[dict(slot=i) for i in range(64)],run_context={})
    class Model:
        def __init__(self):self.weights={'w':b'initial'}
        def to(self,**kwargs):return self
        def parameters(self):return [types.SimpleNamespace(numel=lambda:321290)]
        def architecture_description(self):return PROTOCOL['base_identity']['architecture']
        def state_dict(self):return copy.deepcopy(self.weights)
    class Adam:
        def __init__(self):self.state={'moment':b'initial'}
        def state_dict(self):return copy.deepcopy(self.state)
    class Inner:
        def __init__(self,**kwargs):self.kwargs=kwargs;self.resets=0
        def episode_info(self):return [dict(slot=i,episode=0) for i in range(64)]
        def batch_info(self):return dict(next_episode_indices=[1]*64)
        def observations(self):return object()
    current_rng=copy.deepcopy(parent['rng'])
    def restore(state,model,optimizer,device):
        model.weights=copy.deepcopy(state['model']);optimizer.state=copy.deepcopy(state['optimizer'])
        if weight_change:model.weights['w']=b'corrupt'
        if adam_change:optimizer.state['moment']=b'corrupt'
        if rng_change:current_rng['torch_mps']=b'corrupt'
    def make_state(model,optimizer,identity,counters,**kwargs):
        return dict(counters=copy.deepcopy(counters),next_episode_indices=[1]*64,
                    abandoned_episodes=[dict(slot=i) for i in range(64)])
    def checkpoint(path,state):
        path.write_text(repr(state));return c.sha(path)
    ckpt=types.SimpleNamespace(restore_learner=restore,capture_rng=lambda device:copy.deepcopy(current_rng),
                               make_state=make_state,save_checkpoint=checkpoint)
    def evaluate(*args,**kwargs):
        result=copy.deepcopy(c.read_json(ROOT/PROTOCOL['entry_control'])['evaluations']['D2'])
        if control_change:result['rows'][0]['score']+=1
        return result
    ns=dict(Path=Path,require=c.require,validate_config=lambda config:config)
    legacy_functions('python/dodge_rl/identity.py',{'training_env_config'},ns)
    a=types.SimpleNamespace(torch=types.SimpleNamespace(float32='float32'),ckpt=ckpt,teacher=Model,
        seed_initialization=Mock(),make_optimizer=lambda *args:Adam(),PPOConfig=lambda **kwargs:kwargs,
        base=BASE,training_env_config=ns['training_env_config'],
        TrainingEnvLog=lambda env,*args:env,env_factory=Mock(side_effect=Inner),
        verify_training_env=Mock(return_value={}),absolute_deadline=7200,
        evaluate=evaluate,validate_summary=Mock(),progress_passed=Mock(return_value=False),
        collect_rollout=Mock(),require_raw_diagnostics=Mock(),ppo_update=Mock())
    g=FakeGuard(7140)
    l=c.Learner(a,CONFIG,{'config':CONFIG},parent,g,output,PROTOCOL,clock=g.clock)
    a.rng=current_rng
    return l,a


class LearnerTests(unittest.TestCase):
    def test_all_entry_perturbations_before_environment(self):
        for field in ('rng_change','weight_change','adam_change'):
            with tempfile.TemporaryDirectory() as td:
                l,a=learner_fixture(Path(td),**{field:True})
                with self.subTest(field=field),self.assertRaises(c.Stop):l.initialize()
                a.env_factory.assert_not_called();a.collect_rollout.assert_not_called()
    def test_entry_control_mismatch_before_collect(self):
        with tempfile.TemporaryDirectory() as td:
            l,a=learner_fixture(Path(td),control_change=True)
            try:
                l.initialize()
                with self.assertRaises(c.Stop):l.evaluate_checkpoint(entry=True)
                a.collect_rollout.assert_not_called();a.ppo_update.assert_not_called()
            finally:l.close()
    def test_evaluation_rng_and_weight_perturbation(self):
        for field in ('RNG','model','Adam'):
            with tempfile.TemporaryDirectory() as td:
                l,a=learner_fixture(Path(td));l.initialize();original=a.evaluate
                def changed(*args,**kwargs):
                    r=original(*args,**kwargs)
                    if field=='RNG':a.rng['torch_mps']=b'change'
                    if field=='model':l.model.weights['w']=b'change'
                    if field=='Adam':l.optimizer.state['moment']=b'change'
                    return r
                a.evaluate=changed
                try:
                    with self.subTest(field=field),self.assertRaises(c.Stop):l.evaluate_checkpoint(entry=True)
                    a.collect_rollout.assert_not_called()
                finally:l.close()
    def test_checkpoint_eval_preserves_live_env_and_observation_rng(self):
        with tempfile.TemporaryDirectory() as td:
            l,a=learner_fixture(Path(td));l.initialize()
            env,observation=l.env,l.observation;before=copy.deepcopy(a.rng)
            try:
                r,passed,wall=l.evaluate_checkpoint(entry=True)
                self.assertTrue(r['evaluated']);self.assertFalse(passed)
                self.assertIs(l.env,env);self.assertIs(l.observation,observation)
                self.assertEqual(env.resets,0);self.assertEqual(a.rng,before)
                self.assertEqual(a.env_factory.call_count,1)
                lines=(Path(td)/'training-episodes.jsonl').read_text().splitlines()
                self.assertEqual(sum(json.loads(x).get('reason')=='long_D2_namespace_transition' for x in lines),64)
            finally:l.close()
    def setup_update(self,l,a,*,kl=0.01,partial=None):
        batch=types.SimpleNamespace(transitions=16384,elapsed_raw_frames=types.SimpleNamespace(
                  sum=lambda:types.SimpleNamespace(item=lambda:65536)))
        next_observation=object()
        a.collect_rollout.return_value=types.SimpleNamespace(batch=batch,observations=next_observation,
                                                     completed_episodes=[],reset_info=[])
        def update(*args,**kwargs):
            progress=kwargs['progress']
            if partial is not None:
                progress.update(in_update=True,complete=False,optimizer_steps=partial)
                raise c.Stop('fixture update interruption','wall_guard')
            progress.update(in_update=False,complete=True,optimizer_steps=128)
            return dict(optimizer_steps=128,actor_grad_norm=1.,critic_grad_norm=1.,approx_kl=kl,entropy=0.2)
        a.ppo_update.side_effect=update
        return next_observation
    def test_observation_carried_and_only_complete_steps_counted(self):
        with tempfile.TemporaryDirectory() as td:
            l,a=learner_fixture(Path(td));l.initialize();first=l.observation
            try:
                second=self.setup_update(l,a);l.update_once()
                self.assertIs(a.collect_rollout.call_args.kwargs['observation'],first)
                self.assertIs(l.observation,second)
                l.update_once();self.assertIs(a.collect_rollout.call_args.kwargs['observation'],second)
                self.assertEqual(l.report()['phase']['updates'],2)
                self.assertEqual(l.report()['phase']['optimizer_steps'],256)
                self.assertTrue(l.context['D1_competence_demonstrated'])  # entropy 0.2 remains inert
            finally:l.close()
    def test_partial_optimizer_not_complete_update(self):
        with tempfile.TemporaryDirectory() as td:
            l,a=learner_fixture(Path(td));l.initialize();self.setup_update(l,a,partial=7)
            try:
                with self.assertRaises(c.Stop):l.update_once()
                self.assertEqual(l.counters['updates'],48);self.assertEqual(l.counters['phase_updates'],0)
                self.assertEqual(l.report()['actual_optimizer_steps_including_partial'],6151)
                r=l.checkpoint('interrupted_mid_update',emergency=True)
                self.assertFalse(r['complete_update']);self.assertEqual(r['update_progress']['optimizer_steps'],7)
            finally:l.close()
    def test_KL_three_consecutive_and_reset(self):
        with tempfile.TemporaryDirectory() as td:
            l,a=learner_fixture(Path(td));l.initialize()
            try:
                self.setup_update(l,a,kl=.11);l.update_once();l.update_once()
                self.assertEqual(l.kl_count,2)
                self.setup_update(l,a,kl=.1);l.update_once();self.assertEqual(l.kl_count,0)
                self.setup_update(l,a,kl=.11);l.update_once();l.update_once()
                with self.assertRaises(c.Stop) as e:l.update_once()
                self.assertEqual(e.exception.outcome,'safety_stop');self.assertEqual(l.counters['phase_updates'],6)
            finally:l.close()
    def test_checkpoint_absolute_deadline_inclusive(self):
        with tempfile.TemporaryDirectory() as td:
            l,a=learner_fixture(Path(td));l.initialize();l.clock.at=7200
            try:
                with self.assertRaises(c.Stop):l.checkpoint('timeout',emergency=True)
            finally:l.close()


class GuardTests(unittest.TestCase):
    def test_resource_and_wall_inclusive_boundaries(self):
        clock=Clock();value=[c.LIMIT]
        g=c.Guard(10,lambda:None,lambda:None,io.StringIO(),clock=clock,
                  rss=lambda:value[0],peak=lambda:0,mps=lambda:value[0])
        g.sample();value[0]+=1
        with self.assertRaises(c.Stop) as e:g.sample()
        self.assertEqual(e.exception.outcome,'resource_stop')
        clock.at=10
        with self.assertRaises(c.Stop) as e:g.check()
        self.assertEqual(e.exception.outcome,'wall_guard')
    def test_mps_limit_separate_from_rss(self):
        g=c.Guard(10,lambda:None,lambda:None,io.StringIO(),clock=Clock(),
                  rss=lambda:c.LIMIT,peak=lambda:c.LIMIT,mps=lambda:c.LIMIT)
        g.sample()  # Not an additive 18 GiB limit.
        g.mps=lambda:c.LIMIT+1
        with self.assertRaises(c.Stop):g.sample()
    def test_lease_latched_midrun(self):
        failure=c.Stop('cancel','cancelled')
        g=c.Guard(10,lambda:(_ for _ in ()).throw(failure),lambda:None,io.StringIO(),clock=Clock())
        g.failure=failure
        with self.assertRaises(c.Stop) as e:g.check()
        self.assertEqual(e.exception.outcome,'cancelled')
    def test_sample_and_full_pin_max_gaps(self):
        clock=Clock();calls=[]
        g=c.Guard(10,lambda:calls.append('lease'),lambda:calls.append('pins'),io.StringIO(),
                  clock=clock,rss=lambda:0,peak=lambda:0,mps=lambda:0)
        g.sample();clock.at=.5;g.sample()
        clock.at=1.00001
        with self.assertRaises(c.Stop):g.sample()
        self.assertEqual(calls.count('pins'),1)
    def test_force_checks_inputs_each_boundary(self):
        verify=Mock();g=c.Guard(10,Mock(),verify,io.StringIO(),clock=Clock(),
                               rss=lambda:0,peak=lambda:0,mps=lambda:0)
        g.sample();g.check(force=True);self.assertEqual(verify.call_count,2)
    def test_background_latches_verification_failure(self):
        def fail():raise c.Stop('pin changed')
        g=c.Guard(time.monotonic()+5,lambda:None,lambda:None,io.StringIO(),rss=lambda:0,peak=lambda:0)
        g.start();g.verify=fail;g.last_full=-100
        deadline=time.monotonic()+1
        while g.failure is None and time.monotonic()<deadline:time.sleep(.02)
        self.assertIsNotNone(g.failure)
        with self.assertRaises(c.Stop):g.close()


class FinalizationTests(unittest.TestCase):
    def publish(self,path,result=None,clock=None,stable=True):
        return c.publish_terminal(path,result or c.outcome_fields('budget_closed_below_gate',True),0,7200,
                                  stable,clock=clock or Clock(10))
    def test_budgetclosure_exit2_bindings(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td);(out/'closed.log').write_text('closed')
            self.assertEqual(self.publish(out),2)
            terminal=c.read_json(out/'finalization-result.json');manifest=c.read_json(out/'artifact-manifest.json')
            self.assertEqual(terminal['artifact_manifest_sha256'],c.sha(out/'artifact-manifest.json'))
            self.assertEqual(terminal['run_result_sha256'],c.sha(out/'long-run-result.json'))
            self.assertFalse(terminal['progression_gate_passed']);self.assertFalse(terminal['teacher_qualified'])
            self.assertNotIn('finalization-result.json',manifest);self.assertNotIn('artifact-manifest.json',manifest)
    def test_gatepass_exit0_separate(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td);r=c.outcome_fields('D2_progress_gate_passed',True)
            self.assertEqual(self.publish(out,r),0)
            t=c.read_json(out/'finalization-result.json')
            self.assertTrue(t['D3_parent_candidate_pending_separate_parent_audit'])
            self.assertFalse(t['training_parent_eligible'])
    def test_unproven_owned_group_blocks_all_hashes(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)
            with patch.object(c,'sha',side_effect=AssertionError('mutable artifacts must not hash')) as hashing:
                self.assertEqual(self.publish(out,stable=False),1)
                hashing.assert_not_called()
            self.assertFalse((out/'artifact-manifest.json').exists())
            self.assertEqual(c.read_json(out/'finalization-result.json')['experiment_status'],'failed')
    def test_late_write_and_hash_revoke_success(self):
        for stage in ('long-run-result.json','artifact-manifest.json','finalization-result.json','hash'):
            with self.subTest(stage=stage),tempfile.TemporaryDirectory() as td:
                out=Path(td);clock=Clock(7199);save=c.replace_json;sha=c.sha;late_hashes=[]
                def late_save(path,value):
                    save(path,value)
                    if path.name==stage:clock.at=7200
                def late_hash(path):
                    if clock.at>=7200:late_hashes.append(str(path))
                    value=sha(path)
                    if stage=='hash':clock.at=7200
                    return value
                with patch.object(c,'replace_json',side_effect=late_save),patch.object(c,'sha',side_effect=late_hash):
                    self.assertEqual(self.publish(out,clock=clock),1)
                self.assertFalse((out/'artifact-manifest.json').exists())
                self.assertEqual(c.read_json(out/'finalization-result.json')['experiment_status'],'failed')
                self.assertEqual(late_hashes,[], 'No normal artifact hash may begin after deadline')
    def test_cancel_publication_and_deferred_latch(self):
        for sig in (signal.SIGINT,signal.SIGTERM):
            for stage in ('long-run-result.json','artifact-manifest.json','finalization-result.json'):
                with self.subTest(signal=sig,stage=stage),tempfile.TemporaryDirectory() as td:
                    out=Path(td);save=c.replace_json;sent=[False]
                    def signal_write(path,value):
                        save(path,value)
                        if path.name==stage and not sent[0]:
                            sent[0]=True;os.kill(os.getpid(),sig)
                    with patch.object(c,'replace_json',side_effect=signal_write):
                        self.assertEqual(self.publish(out),1)
                    self.assertFalse((out/'artifact-manifest.json').exists())
                    self.assertEqual(c.read_json(out/'finalization-result.json')['outcome'],'cancelled')
    def test_cancel_while_already_deferring_counts_every_request(self):
        for sig in (signal.SIGINT,signal.SIGTERM):
            with c.cancellation_signals() as cancel:
                cancel();os.kill(os.getpid(),sig);os.kill(os.getpid(),sig)
            self.assertEqual(cancel.cancellation_requests,2);self.assertEqual(cancel.requested_signal,sig)


class SupervisorTests(unittest.TestCase):
    def execute(self,mode='closure',*,hook=None,signal_number=signal.SIGTERM,expired=False):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve();state=root/'state.json';output=root/'campaign'
            state.write_text(json.dumps({'active_long_campaign':lease()}))
            (root/'capsule-manifest.json').write_text('{"files":{}}')
            p={**PROTOCOL,'output':'campaign'}
            context=(p,CONFIG,BASE,{}, {},lease())
            args=types.SimpleNamespace(output=output,state_path=state)
            def command(*args):
                return [sys.executable,'-B',str(HERE/'fake_worker.py'),'--output',str(output),'--mode',mode]
            real_stop=c.stop_owned
            real_popen=subprocess.Popen
            sent=[False]
            def send_once():
                if not sent[0]:sent[0]=True;os.kill(os.getpid(),signal_number)
            class FixtureGuard(FakeGuard):
                def close(self):
                    if hook=='guard_close':send_once()
            def stop(process):
                receipt=real_stop(process)
                if hook=='cleanup':send_once()
                if hook=='unproven_group':receipt['group_empty']=False
                return receipt
            def verify(pins):
                if hook=='final_verify':send_once()
            def popen(*args,**kwargs):
                process=real_popen(*args,**kwargs)
                if hook=='spawn_assignment':
                    mask=signal.pthread_sigmask(signal.SIG_BLOCK,set())
                    self.assertTrue({signal.SIGINT,signal.SIGTERM,signal.SIGALRM}.issubset(mask))
                    send_once()
                return process
            real_open=Path.open
            class ClosingStream:
                def __init__(self,inner):self.inner=inner
                def __getattr__(self,name):return getattr(self.inner,name)
                def __enter__(self):return self
                def __exit__(self,*args):
                    send_once()
                    return self.inner.__exit__(*args)
            def opening(path,*args,**kwargs):
                stream=real_open(path,*args,**kwargs)
                if hook=='stream_close' and path.name=='supervisor-guard.jsonl':return ClosingStream(stream)
                return stream
            started=time.monotonic()-(7199.8 if expired else 0)
            with patch.object(c,'ORIGINAL_ROOT',root),patch.object(c,'ROOT',root),patch.object(c,'STATE_PATH',state), \
                 patch.object(c,'assert_readonly_capsule'),patch.object(c,'verify_files',side_effect=verify), \
                 patch.object(c,'stop_owned',side_effect=stop),patch.object(Path,'open',opening), \
                 patch.object(c.subprocess,'Popen',side_effect=popen):
                code=c.supervise(args,context_provider=lambda root:context,command_factory=command,
                                 guard_factory=FixtureGuard,started=started)
            result=c.read_json(output/'long-run-result.json');terminal=c.read_json(output/'finalization-result.json')
            manifest=c.read_json(output/'artifact-manifest.json') if (output/'artifact-manifest.json').exists() else None
            if manifest:
                for name,digest in manifest.items():self.assertEqual(c.sha(output/name),digest,name)
                self.assertEqual(terminal['run_result_sha256'],c.sha(output/'long-run-result.json'))
            self.assertTrue(result['owned_process_stop']['reaped'])
            with self.assertRaises(ProcessLookupError):os.killpg(result['owned_process_stop']['owned_pgid'],0)
            self.assertLessEqual(result['cleanup_seconds'],10)
            return code,result,terminal,manifest
    def test_actual_supervisor_fake_budget_closure_exit2(self):
        code,r,t,m=self.execute()
        self.assertEqual(code,2);self.assertEqual(r['worker_exit_code'],2)
        self.assertEqual(t['experiment_status'],'complete');self.assertEqual(t['outcome'],'budget_closed_below_gate')
        self.assertIn('worker.stdout.log',m);self.assertIn('supervisor-guard.jsonl',m)
    def test_actual_supervisor_gatepass_exit0(self):
        code,r,t,m=self.execute('pass')
        self.assertEqual(code,0);self.assertTrue(t['progression_gate_passed']);self.assertFalse(t['training_parent_eligible'])
    def test_exit_outcome_mismatch_fails(self):
        code,r,t,m=self.execute('wrong-exit')
        self.assertEqual(code,1);self.assertEqual(t['experiment_status'],'failed')
        self.assertEqual(t['outcome'],'publication_failure')
    def test_signals_blocked_through_owned_PID_assignment(self):
        for sig in (signal.SIGINT,signal.SIGTERM):
            code,r,t,m=self.execute(hook='spawn_assignment',signal_number=sig)
            self.assertEqual(code,1);self.assertEqual(t['outcome'],'cancelled')
            self.assertTrue(r['owned_process_stop']['group_empty'])
    def test_owned_descendant_cleaned_and_reaped(self):
        code,r,t,m=self.execute('descendant')
        self.assertEqual(code,2);self.assertTrue(r['owned_process_stop']['group_empty'])
    def test_unproven_group_blocks_manifest_in_actual_supervisor(self):
        code,r,t,m=self.execute(hook='unproven_group')
        self.assertEqual(code,1);self.assertIsNone(m)
    def test_signal_latched_through_cleanup_close_verify_streamclose(self):
        for sig in (signal.SIGINT,signal.SIGTERM):
            for hook in ('cleanup','guard_close','final_verify','stream_close'):
                with self.subTest(signal=sig,hook=hook):
                    code,r,t,m=self.execute(hook=hook,signal_number=sig)
                    self.assertEqual(code,1);self.assertEqual(r['outcome'],'cancelled')
                    self.assertGreater(r['cancellation_requests'],0);self.assertEqual(t['experiment_status'],'failed')
    def test_blocked_worker_outer_wall_no_inference_extension(self):
        code,r,t,m=self.execute('blocked',expired=True)
        self.assertEqual(code,1);self.assertEqual(t['outcome'],'wall_guard')
        self.assertIsNone(m);self.assertTrue(r['owned_process_stop']['group_empty'])


# unittest discovery finds these definitions despite the earlier CLI-only guard.
class TensorRepresentationTests(unittest.TestCase):
    def test_raw_tensor_byte_dtype_shape_fingerprint(self):
        class Tensor:
            def __init__(self,raw,dtype='float32',shape=(1,)):
                self.raw,self.dtype,self.shape=raw,dtype,shape
            def detach(self):return self
            def cpu(self):return self
            def contiguous(self):return self
            def numpy(self):return self
            def tobytes(self):return self.raw
        original=Tensor(struct.pack('<f',1.0))
        self.assertEqual(c.assert_equal_tree(original,Tensor(struct.pack('<f',1.0)),'tensor'),
                         c.semantic_hash(c.tree_fingerprint(original)))
        for bad in (Tensor(struct.pack('<f',1.00001)),Tensor(original.raw,'int32'),Tensor(original.raw,shape=(1,1))):
            with self.assertRaises(c.Stop):c.assert_equal_tree(bad,original,'tensor')
    def test_pure_preflight_rejects_imported_ml_without_model(self):
        with patch.dict(sys.modules,{'torch':types.SimpleNamespace()}):
            with self.assertRaisesRegex(c.Stop,'Pure preflight imported ML'):
                c.pure_preflight(Path('/not-needed'))


if __name__=='__main__':
    unittest.main(verbosity=2)
