"""Only the fresh-bank bridge, recipe binding and unchanged-Adam delta."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch
from pathlib import Path
import common as c
from seed_stream import StreamSpec,seed_for
from seed_bank import bank,audit_assignments,build_streams
from warmstart import verify_optimizer_unchanged


def spec():
    return StreamSpec('synthetic-only','one',2,'a'*64,bits=8,additional_exclusions=((5,20),))


def assignment(s,slot,episode,index=0,size=4):
    value=seed_for(s,slot,index*size+episode)['actual_seed']
    return dict(slot=slot,seed=dict(slot=slot,episode=episode,counter=0,actual_seed=value,evaluation=True),sampling_component='uniform')


def initial(s,segment):
    return dict(kind='initial_assignments',simulator_segment=segment,fresh_stream_identity=s.identity,
                bank_episode_offset=(segment-1)*4,assignments=[assignment(s,i,0,segment-1) for i in range(2)])


def native_reset(row):
    return dict(kind='returned_reset',indices=row['indices'],info=[dict(seed=r['seed']) for r in row['assignments']])


class Delta(unittest.TestCase):
    def test_disjoint_banks_and_exclusion_with_toy_domain(self):
        s=spec();a=bank(s,0,4);b=bank(s,1,4)
        self.assertEqual(len(set(a[0]+b[0])),16)
        self.assertFalse(any(5 <= v <= 20 or v == 0 for v in a[0]+b[0]))
        self.assertEqual(a,bank(s,0,4))
        self.assertEqual(a[2][1][2],seed_for(s,1,2)['actual_seed'])
        with self.assertRaises(ValueError):bank(s,s.capacity,4)

    def test_no_production_lookup_from_source_only_candidate(self):
        with patch('seed_bank.specification',side_effect=AssertionError('must not reach seed metadata')):
            with self.assertRaises(ValueError):build_streams(dict(execution_authorized=False), '1', 0)

    def test_consumed_assignments_skip_unused_bank_entries(self):
        s=spec();reset=dict(kind='seeded_reset',indices=[1],assignments=[assignment(s,1,1)])
        events=[initial(s,1),native_reset(reset),reset,initial(s,2)]
        result=audit_assignments(events,s,4)
        self.assertEqual(result['consumed_unique_training_seeds'],5)
        self.assertEqual(result['assignments_per_segment'],[3,2])

    def test_native_flags_stale_duplicate_and_wrong_slot_fail(self):
        s=spec();start=initial(s,1)
        good=dict(kind='seeded_reset',indices=[1],assignments=[assignment(s,1,1)])
        for mutate in [lambda e:e['assignments'][0]['seed'].update(evaluation=False),
                       lambda e:e['assignments'][0]['seed'].update(episode=0),
                       lambda e:e['assignments'][0]['seed'].update(actual_seed=0),
                       lambda e:e.update(indices=[0])]:
            row=copy.deepcopy(good);mutate(row)
            with self.assertRaises(ValueError):audit_assignments([start,native_reset(row),row],s,4)
        with self.assertRaises(ValueError):audit_assignments([start,native_reset(good),good,native_reset(good),good],s,4)
        with self.assertRaises(ValueError):audit_assignments([start,native_reset(good)],s,4)
        with self.assertRaises(ValueError):audit_assignments([start,good],s,4)
        wrong=copy.deepcopy(good);wrong['assignments'][0]['seed']['actual_seed']=0
        with self.assertRaises(ValueError):audit_assignments([start,native_reset(wrong),good],s,4)

    def test_full_source_adam_preserved_including_lr(self):
        fp=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()
        before=dict(param_groups=[dict(params=[0],lr=3e-5)],state={'0':dict(step=1536,exp_avg=[1,2])})
        verify_optimizer_unchanged(before,copy.deepcopy(before),fp)
        changed=copy.deepcopy(before);changed['param_groups'][0]['lr']=1e-5
        with self.assertRaises(ValueError):verify_optimizer_unchanged(before,changed,fp)
        changed=copy.deepcopy(before);changed['state']['0']['step']=0
        with self.assertRaises(ValueError):verify_optimizer_unchanged(before,changed,fp)

    def test_preparation_cannot_enter_runtime_before_claim(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'candidate.json';path.write_text(json.dumps(dict(execution_authorized=False)))
            with patch.object(c,'verify_environment',side_effect=AssertionError('runtime forbidden')):
                with self.assertRaisesRegex(ValueError,'Source-only candidate'):c.load_registration(path,c.sha(path))
            self.assertEqual([p.name for p in Path(tmp).iterdir()],['candidate.json'])

    def test_only_seed_policy_may_change_in_candidate(self):
        root=Path(__file__).resolve().parents[4]
        path=root/'learning/runs/v2/fresh-seed-performance-preparation-20261102-r1'
        reg=c.read(path/'candidate-config.json');recipe=c.read(root/'learning/runs/v2/performance-loop-20261101-r1/config.json')
        c.validate_shape(reg,recipe)
        for key,value in [('envs',128),('work_seconds',7200),('action_repeat',4)]:
            changed=dict(reg,**{key:value})
            with self.assertRaises(ValueError):c.validate_shape(changed,recipe)
        for key,value in [('learning_rate',1e-5),('ent_coef',.02)]:
            changed=copy.deepcopy(reg);changed['ppo'][key]=value
            with self.assertRaises(ValueError):c.validate_shape(changed,recipe)
        changed=copy.deepcopy(reg);changed['arms']['control']['gamma']=.99
        with self.assertRaises(ValueError):c.validate_shape(changed,recipe)

    def test_baseline_reuse_requires_exact_machine_runtime_controller(self):
        root=Path(__file__).resolve().parents[4]
        reg=c.read(root/'learning/runs/v2/fresh-seed-performance-preparation-20261102-r1/candidate-config.json')
        prior=c.read(root/'learning/runs/v2/control12-lr1e5-m1-20261102-r2/config.json')
        c.validate_baseline_binding(reg,prior)
        for key,value in [('machine',{'fixture':'anotherMac'}),('evaluation_controller_domain','changed')]:
            changed=dict(reg,**{key:value})
            with self.assertRaises(ValueError):c.validate_baseline_binding(changed,prior)
        changed=copy.deepcopy(reg);path=str(Path(reg['runtime_root'])/reg['runtime_members'][0])
        changed['input_pins'][path]='0'*64
        with self.assertRaises(ValueError):c.validate_baseline_binding(changed,prior)


if __name__=='__main__':unittest.main()
