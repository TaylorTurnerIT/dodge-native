"""New policy/ownership/cached-controller checks only. No native or model imports."""
import hashlib
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import lifecycle
import common as c
from policy import advance,summarize
from evaluation import policy_seed
from owner import audit_child,play_rows

S=dict(initial_updates=72,segment_updates=12,patience_checks=3,gain_fraction=.02,max_checks=3000)
R=dict(games=512,Mean=5000,Q1=2000,early_deaths=4,mean_score=50)


class DeltaTests(unittest.TestCase):
    def test_improving_live_direction_continues_beyond72(self):
        state={}
        for u in range(12,97,12):
            state,d=advance(state,dict(R,Q1=2000*(1.03**(u//12))),u,R,S)
        self.assertTrue(d['continue_training']);self.assertEqual(d['best_update'],96)
    def test_stall_stops_and_keeps_earlier_best(self):
        state,d=advance({},dict(R,Q1=2200),12,R,S)
        for u in range(24,73,12):state,d=advance(state,dict(R,Q1=2050),u,R,S)
        self.assertFalse(d['continue_training']);self.assertEqual(d['best_update'],12)
    def test_consistent_severe_underperformance_is_culled(self):
        state={}
        for u in range(12,73,12):state,d=advance(state,dict(R,Q1=1000,Mean=3000),u,R,S)
        self.assertEqual(d['stop_reason'],'persistently_uncompetitive_play')
    def test_no_significance_or_replication_gate_on_selection(self):
        _,d=advance({},dict(R,Q1=2001),12,R,S)
        self.assertTrue(d['selected_as_best'])
    def test_zero_progress_is_not_meaningful_gain(self):
        state={}
        for u in range(12,73,12):state,d=advance(state,dict(R,Q1=0,Mean=0),u,R,S)
        self.assertIsNone(d['last_meaningful_gain_update']);self.assertFalse(d['continue_training'])
    def test_first_observation_is_not_a_gain_and72_is_initial_horizon(self):
        state,d=advance({},dict(R,Q1=1000,Mean=3000),12,R,S)
        self.assertIsNone(d['last_meaningful_gain_update'])
        for u in (24,36,48,60):
            state,d=advance(state,dict(R,Q1=1000,Mean=3000),u,R,S)
            self.assertTrue(d['continue_training'])
        state,d=advance(state,dict(R,Q1=1000,Mean=3000),72,R,S)
        self.assertFalse(d['continue_training'])
    def test_exact_cached_controller_domain(self):
        seed=3657433088
        self.assertEqual(policy_seed(seed),int.from_bytes(hashlib.sha256(f'dodge068/paired-policy-v1/{seed}/clean'.encode()).digest()[:8],'big'))
    def test_no_wall_cutoff_and_resource_failures_remain_terminal(self):
        class Child:
            pid=99123
            def wait(self,timeout):return 0
        for fail in (False,True):
            def monitor(_):
                if fail:raise ValueError('Resource cap violated')
            with tempfile.TemporaryDirectory() as tmp,patch('lifecycle.waitid_function',return_value=None),patch('lifecycle.subprocess.Popen',return_value=Child()),patch('lifecycle.group_members',return_value=[]),patch('lifecycle.observe',return_value=0),patch('lifecycle.time.monotonic',side_effect=[0,10**12,2*10**12]),patch('lifecycle.os.killpg',side_effect=ProcessLookupError):
                if fail:
                    with self.assertRaises(ValueError):lifecycle.run_child(['fixture'],Path(tmp),{},monitor,None)
                    self.assertIn('Resource cap',c.read(Path(tmp)/'exit.json')['reason'])
                else:self.assertIsNone(lifecycle.run_child(['fixture'],Path(tmp),{},monitor,None)['reason'])
    def test_parent_rejects_missing_play_and_unreaped_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'episodes.jsonl').write_text('')
            with self.assertRaises(ValueError):play_rows(p/'episodes.jsonl',[1])
            c.save(p/'launch.json',dict(pid=123));c.save(p/'exit.json',dict(raw_exit_code=0,observed_exit_code=0,directly_reaped=False,group_absent=True,pid=123,pgid=123,reason=None,peak_group_RSS_bytes=1))
            with self.assertRaises(ValueError):audit_child(p,dict(rss_bytes=1000))


if __name__=='__main__':unittest.main()
