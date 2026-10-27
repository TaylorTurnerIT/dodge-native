"""New-adapter tests: no Torch/native imports, model use, or checkpoint loads."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

import binding as b
import terminal
import paired_statistics as stats

BOOTSTRAP=dict(seed=2026102701,draws=2000,confidence=.95,unit='paired_evaluation_seed',
    training_seed_uncertainty='three_training_pairs_descriptive_only')


def row(index=0,alive=3):
    return dict(episode_index=index,seed=b.SEEDS[index],score_raw_fixed=0,score=0.0,
        alive_frames=alive,gameplay_frames=alive+1,startup_frames=13,
        objective_return=alive/100-5,score_delta_sum_raw_fixed=0,terminated=True,truncated=False,
        death_cause='normal_enemy',fatal_gameplay_frame=alive+1,
        death_observed_lethal_contacts=dict(normal_enemy=1,kamikaze_enemy=0,kamikaze_explosion=0,
            static_pattern_rect=0,moving_pattern_rect=0,unknown=0))


class AdapterTests(unittest.TestCase):
    def test_supervisor_copies_unchanged(self):
        original=b.ROOT/'learning/runs/v2/progressive1000-opening-maintenance-supervisor-parent-20261027-r1'
        for name in ('observe.py','execute_once.py'):
            self.assertEqual(b.sha(b.HERE/name),b.sha(original/name))

    def test_limits(self):
        value=dict(work_seconds=100,total_seconds=110,cleanup_seconds=10,rss_bytes=b.CAP,
            mps_bytes=b.CAP,raw_frames=b.RAW_CAP,resets=0,retries=0)
        b.validate_limits(value)
        for key in ('rss_bytes','mps_bytes','raw_frames','cleanup_seconds','retries','resets','total_seconds'):
            bad=dict(value);bad[key]+=1
            with self.subTest(key=key),self.assertRaises(ValueError):b.validate_limits(bad)

    def test_draft_rejected_before_inputs(self):
        with self.assertRaisesRegex(ValueError,'field set'):
            b.validate_static(dict(status='parent_registered'))

    def test_checkpoint_uses_actual_producer(self):
        expected=dict(registration_sha256='producer-registration',successor_runtime=dict(
            source_manifest_sha256='legacy-control1-source',runtime_manifest_sha256='legacy-control1-runtime'))
        policy=dict(id='replica-1-control_constant_3e-5',producer=dict(expected_identity=expected))
        state=dict(schema='progressive1000_integrity_checkpoint_v1',global_update=60,phase_update=384,
            cumulative_update=432,identity=expected,identity_sha256=hashlib.sha256(b.canonical(expected)).hexdigest(),
            promoted=False,automatic_selection=False,training_eligible=False,formal_comparison_endpoint=True)
        b.validate_checkpoint(state,policy)
        bad=copy.deepcopy(state);bad['identity']['successor_runtime']['runtime_manifest_sha256']=b.RUNTIME_SHA
        with self.assertRaisesRegex(ValueError,'actual producer'):b.validate_checkpoint(bad,policy)

    def test_checkpoint_integrity(self):
        policy=dict(id='replica-2-control_constant_3e-5',producer=dict(expected_identity={}))
        state=dict(schema='progressive1000_integrity_checkpoint_v1',global_update=60,phase_update=384,
            cumulative_update=432,identity={},identity_sha256=hashlib.sha256(b.canonical({})).hexdigest(),
            promoted=False,automatic_selection=False,training_eligible=False,formal_comparison_endpoint=True)
        for field,value in [('global_update',48),('phase_update',385),('identity_sha256','a'*64),('promoted',True)]:
            with self.subTest(field=field),self.assertRaises(ValueError):b.validate_checkpoint(dict(state,**{field:value}),policy)

    def test_accounting_exact_cost(self):
        with tempfile.TemporaryDirectory(dir=b.HERE) as temp:
            p=Path(temp);policy=b.POLICIES[0]
            events=[dict(kind='evaluation_constructor',policy_id=policy,episode_index=0,startup_frames=13,seed=b.SEEDS[0]),
                dict(kind='evaluation_step',policy_id=policy,episode_index=0,elapsed_raw_frames=4),
                dict(kind='evaluation_completed',policy_id=policy,row=row())]
            (p/'evaluation-events.jsonl').write_text(''.join(json.dumps(v)+'\n' for v in events))
            a=terminal.accounting(p,{},strict=True,include_rows=True)
            self.assertEqual((a['constructors'],a['completed_episodes'],a['raw_frames_including_startup']),(1,1,17))
            self.assertEqual(a['rows'][policy],[row()])

    def test_accounting_duplicate_and_frame_mismatch(self):
        policy=b.POLICIES[0]
        initial=dict(kind='evaluation_constructor',policy_id=policy,episode_index=0,startup_frames=13,seed=b.SEEDS[0])
        cases=[[initial,initial],[initial,dict(kind='evaluation_step',policy_id=policy,episode_index=0,elapsed_raw_frames=3),
            dict(kind='evaluation_completed',policy_id=policy,row=row())]]
        with tempfile.TemporaryDirectory(dir=b.HERE) as temp:
            p=Path(temp)
            for events in cases:
                (p/'evaluation-events.jsonl').write_text(''.join(json.dumps(v)+'\n' for v in events))
                with self.assertRaises(ValueError):terminal.accounting(p,{},strict=True)

    def test_torn_journal_preserved(self):
        with tempfile.TemporaryDirectory(dir=b.HERE) as temp:
            p=Path(temp)/'evaluation-events.jsonl';p.write_text('{"unfinished":')
            self.assertEqual(list(terminal.rows(p)),[])
            with self.assertRaisesRegex(ValueError,'torn'):list(terminal.rows(p,strict=True))
            self.assertEqual(p.read_text(),'{"unfinished":')

    def test_exclusive_durable_save(self):
        with tempfile.TemporaryDirectory(dir=b.HERE) as temp:
            p=Path(temp)/'receipt.json';b.save(p,dict(first=True))
            with self.assertRaises(FileExistsError):b.save(p,dict(first=False))
            self.assertEqual(b.read(p),dict(first=True))

    def test_sampling_and_quarter_summary(self):
        analysis=b.analysis();data=[row(i,i+1) for i in range(1024)]
        v=analysis.summarize(data,b.SEEDS)['performance']
        self.assertEqual(v,dict(Worst=1,Q1=128.5,Mean=512.5,Q4=896.5,Best=1024))

    def test_full_pair_requirement(self):
        analysis=b.analysis()
        with self.assertRaises(ValueError):analysis.compare({},b.SEEDS)

    def test_conditional_bootstrap_exact_known_shift(self):
        data={name:[dict(alive_frames=10+index) for _ in b.SEEDS] for index,name in enumerate(b.POLICIES)}
        result=stats.paired_intervals(data,BOOTSTRAP)
        self.assertEqual(result['comparisons']['replica-1-curriculum_minus_control']['performance'],
            {key:dict(low=1.0,high=1.0) for key in stats.KEYS})
        self.assertIn('three training pairs remain descriptive',result['interpretation'])

    def test_bootstrap_rejects_unregistered_draws(self):
        data={name:[dict(alive_frames=1) for _ in b.SEEDS] for name in b.POLICIES}
        with self.assertRaises(ValueError):stats.paired_intervals(data,dict(BOOTSTRAP,draws=1))

    def test_no_runtime_imports(self):
        self.assertFalse(any(name=='torch' or name.startswith('torch.') or name=='dodge_rl' or
            name.startswith('dodge_rl.') for name in sys.modules))


if __name__=='__main__':unittest.main()
