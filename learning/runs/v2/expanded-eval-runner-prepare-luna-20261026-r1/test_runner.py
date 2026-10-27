import hashlib, json, os, sys, tempfile, time, unittest
from pathlib import Path
import execute_once
import build_registration


def sh(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

class RunnerTests(unittest.TestCase):
 def test_preflight_failure_does_not_consume_marker(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'marker'
   with self.assertRaisesRegex(RuntimeError,'bad preflight'):
    execute_once.execute_once(registration=Path('x'),worker=Path('x'),evaluator=Path('x'),stage='benchmark',candidate_update=348,cohort='benchmark_dev64',output=Path(td)/'out',marker=p,preflight=lambda:(_ for _ in ()).throw(RuntimeError('bad preflight')),observe=lambda *_:{},wall_seconds=20)
   self.assertFalse(p.exists())
 def test_cancel_kills_reaps_and_keeps_receipt(self):
  with tempfile.TemporaryDirectory() as td:
   d=Path(td); worker=d/'fake_worker.py'; evaluator=d/'fake_eval.py'; marker=d/'once'; out=d/'result.json'; reg=d/'reg.json'
   worker.write_text('import time; time.sleep(30)\n'); evaluator.write_text('# fake evaluator pin\n')
   reg.write_text(json.dumps({'schema':'expanded_D2_evaluation_registration_v1','source':{'worker_sha256':sh(worker),'evaluator_sha256':sh(evaluator)},'expected_lease':{'run_id':'fake'},'state_path':str(d/'ledger'),'limits':{'outer_seconds':30}}))
   t0=time.monotonic()
   with self.assertRaisesRegex(RuntimeError,'cancelled'):
    execute_once.execute_once(registration=reg,worker=worker,evaluator=evaluator,stage='benchmark',candidate_update=348,cohort='benchmark_dev64',output=out,marker=marker,preflight=lambda:None,observe=lambda *_:{'cancelled':True,'lease_valid':True},wall_seconds=30)
   self.assertTrue(marker.exists()); self.assertTrue(out.with_suffix('.json.outer-receipt.json').exists()); self.assertLess(time.monotonic()-t0,10)
 def test_builder_refuses_unreviewed_or_missing_pins(self):
  with tempfile.TemporaryDirectory() as td:
   with self.assertRaisesRegex(ValueError,'review records'):
    build_registration.make_draft(Path(td)/'out',review_records=[],measured_dev64_seconds=2)
 def test_frozen_source_pins_refuse_mutation(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'src'; p.write_text('a')
   reg={'schema':build_registration.SCHEMA,'mode':'ranking','expected_lease':{'id':'x'},'state_path':'/tmp/ledger'}
   reg['source']={x:y for k in ['evaluator','worker','launcher'] for x,y in [(k+'_path',str(p)),(k+'_sha256',sh(p))]}; reg['review_records']=[{'path':'review','sha256':'x'}]
   p.write_text('b')
   with self.assertRaisesRegex(ValueError,'mismatched'): build_registration.validate_final(reg)

if __name__=='__main__': unittest.main()
