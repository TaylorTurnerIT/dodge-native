"""Targeted CPU-only fault checks; no native constructors, Torch or MPS."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from owner import audit_child
import common as c
from analysis import summary,validate_rows,forecast


class FaultTests(unittest.TestCase):
    def fixture(self):
        reg=dict(models=[dict(name='r1-rays',sha256='hash')],seeds=[1,2,3,4])
        rows=[dict(model='r1-rays',seed=s,gameplay_frames=101,alive_frames=100,decisions=101,terminated=True,
                   truncated=False,condition='clean',action_repeat=1,startup_frames=13,checkpoint_sha256='hash') for s in reg['seeds']]
        return reg,rows
    def test_terminal_coverage(self):
        reg,rows=self.fixture();self.assertEqual(validate_rows(rows,reg),404)
        for bad in [rows[:-1],rows+[rows[0]]]:
            with self.assertRaises(ValueError):validate_rows(bad,reg)
    def test_identity_failures(self):
        reg,rows=self.fixture()
        for key,value in [('seed',99),('alive_frames',101),('checkpoint_sha256','other'),('truncated',True),('action_repeat',4),('startup_frames',0)]:
            bad=copy.deepcopy(rows);bad[0][key]=value
            with self.assertRaises(ValueError):validate_rows(bad,reg)
    def test_marginal_quartile(self):
        self.assertEqual(summary([40,10,30,20])['Q1'],10)
        with self.assertRaises(ValueError):summary([1,2,3])
    def test_forecast_uses_worst_model_full_cap(self):
        batches=[dict(rounds=1000,frames=64000,wall_seconds=10,max_window_seconds_per_round=.02),dict(rounds=1000,frames=64000,wall_seconds=40,max_window_seconds_per_round=.03)]
        self.assertEqual(forecast(100,batches,5),100+1.2*.04*18000*5+240)
        with self.assertRaises(ValueError):forecast(0,[],5)
        self.assertGreater(forecast(100,batches,200),7200)
    def test_first_receipt_is_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'receipt.json';c.save(p,dict(first=True))
            with self.assertRaises(FileExistsError):c.save(p,dict(first=False))
            self.assertTrue(c.read(p)['first'])
    def test_parent_rejects_forged_terminal_reap(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);(directory/'launch.json').write_text(json.dumps(dict(pid=123)))
            original=dict(raw_exit_code=0,observed_exit_code=0,directly_reaped=True,group_absent=True,
                          peak_group_RSS_bytes=100,reason=None,pid=123,pgid=123)
            def write(row):(directory/'exit.json').write_text(json.dumps(row))
            with patch('owner.group_members',return_value=[]):
                write(original);audit_child(directory,dict(rss_bytes=1000))
                for key,value in [('raw_exit_code',1),('observed_exit_code',1),('directly_reaped',False),('group_absent',False),('peak_group_RSS_bytes',1000),('pid',124),('reason','failure')]:
                    write(dict(original,**{key:value}))
                    with self.assertRaises(ValueError):audit_child(directory,dict(rss_bytes=1000))
            write(original)
            with patch('owner.group_members',return_value=[dict(pid=123)]):
                with self.assertRaises(ValueError):audit_child(directory,dict(rss_bytes=1000))
    def test_exact_shared_cas_preserves_other_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'state.json';p.write_text(json.dumps(dict(active_long_campaign=None,protected=123)))
            reg=dict(state_path=str(p));lease=dict(record='fixture')
            c.cas_ledger(reg,None,lease)
            with self.assertRaises(ValueError):c.cas_ledger(reg,None,dict(record='other'))
            self.assertEqual(c.read(p),dict(active_long_campaign=lease,protected=123))
            c.cas_ledger(reg,lease,None);self.assertEqual(c.read(p),dict(active_long_campaign=None,protected=123))


if __name__=='__main__':unittest.main()
