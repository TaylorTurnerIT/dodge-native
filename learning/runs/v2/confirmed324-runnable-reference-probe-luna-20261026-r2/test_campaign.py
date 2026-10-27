import hashlib,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
import probe
import build_registration
RUN=Path(__file__).resolve().parent; BASE=RUN.parent
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
class CampaignCLI(unittest.TestCase):
 def test_builder_pins_dedicated_clis_and_parent_bytes(self):
  with tempfile.TemporaryDirectory() as d:
   reg=build_registration.build(state_path=Path(d)/'state.json',expected_lease={'lease_id':'parent'},marker_path=Path(d)/'marker',cancel_path=Path(d)/'cancel',output_path=Path(d)/'out',python_path=sys.executable,runtime_root=RUN,empty_cache_path=Path(d)/'cache')
   self.assertEqual(Path(reg['source']['worker_path']),RUN/'worker_cli.py')
   self.assertEqual(Path(reg['source']['supervisor_path']),RUN/'supervisor_cli.py')
   self.assertEqual(reg['checkpoint_sha256'],probe.PARENT)
   self.assertEqual(reg['parent_receipt_sha256'],probe.PARENT_RECEIPT)
   self.assertEqual(reg['status'],'draft_parent_review_required')
 def test_full_fake_cli_campaign_and_commit(self):
  vectors_path=BASE/'confirmed324-seed-vectors-parent-20261026-r1'/'seed-vectors.json'
  vectors=json.loads(vectors_path.read_text())
  checkpoint=BASE/'D2-retained300-continuation-20261026-r1'/'checkpoint-000324-candidate.pt'
  receipt=BASE/'D2-retained300-parent-terminal-audit-20261026-r1'/'retained-best-candidate-receipt.json'
  self.assertEqual(sha(checkpoint),probe.PARENT)
  self.assertEqual(sha(receipt),probe.PARENT_RECEIPT)
  with tempfile.TemporaryDirectory() as d:
   d=Path(d); cache=d/'cache'; cache.mkdir(); state=d/'state.json'; state.write_text(json.dumps({'active_inference_diagnostic':{'lease_id':'synthetic'},'active_long_campaign':False,'active_long':False,'active_inference':False}))
   out=d/'out'; marker=d/'marker'; cancel=d/'cancel'
   src={'worker_path':str(RUN/'worker_cli.py'),'worker_sha256':sha(RUN/'worker_cli.py'),'supervisor_path':str(RUN/'supervisor_cli.py'),'supervisor_sha256':sha(RUN/'supervisor_cli.py'),'probe_path':str(RUN/'probe.py'),'probe_sha256':sha(RUN/'probe.py'),'fingerprint_path':str(BASE/'confirmed324-transition-parent-repair-20261026-r3'/'fingerprints.py'),'fingerprint_sha256':sha(BASE/'confirmed324-transition-parent-repair-20261026-r3'/'fingerprints.py'),'cleanup_primitives_sha256':'4a5d084359ee48fe5351c96e0ec4455fdcd95a428a17bbcf59d0653f6922de98'}
   interpreter=Path(sys.executable).resolve()
   reg={'schema':'d2_layerb_rng_reference_probe_registration_v1','status':'synthetic_test_only','authority':'synthetic_test_only','run_id':'synthetic-run','study_id':vectors['study_id'],'source':src,'runtime':{'python_path':str(interpreter),'python_version':'3.12.15','interpreter_sha256':sha(interpreter),'torch_version':'2.14.1','numpy_version':'2.5.4','empty_cache_path':str(cache)},'vectors_path':str(vectors_path),'vectors_sha256':sha(vectors_path),'vectors':vectors,'checkpoint_path':str(checkpoint),'checkpoint_sha256':sha(checkpoint),'parent_receipt_path':str(receipt),'parent_receipt_sha256':sha(receipt),'state_path':str(state),'expected_lease':{'lease_id':'synthetic'},'one_shot_marker':str(marker),'cancel_path':str(cancel),'output_dir':str(out),'limits':{'work_seconds':45,'outer_seconds':55,'cleanup_seconds':10,'startup_grace_seconds':12,'RSS_bytes':6*1024**3,'MPS_driver_bytes':6*1024**3,'guard_poll_seconds':.2,'heartbeat_stale_seconds':2.0},'references':{'required_replicas':[1,2,3],'receipt_fields':sorted(probe.RECEIPT_FIELDS),'same_reference_for_both_arms':True},'synthetic_test_dependencies':{'runtime_path':str(RUN/'fake_runtime.py'),'runtime_sha256':sha(RUN/'fake_runtime.py')}}
   rp=d/'registration.json'; rp.write_text(json.dumps(reg,sort_keys=True)); rsha=sha(rp)
   env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=str(cache),RNG_PROBE_SYNTHETIC_TEST='1')
   p=subprocess.run([str(interpreter),'-B',str(RUN/'supervisor_cli.py'),'--registration',str(rp),'--registration-sha256',rsha],cwd=RUN,env=env,capture_output=True,text=True,timeout=30)
   detail=p.stdout+'\n'+p.stderr+'\n'+((out/'worker.log').read_text() if (out/'worker.log').exists() else '')
   self.assertEqual(p.returncode,0,detail)
   commit=json.loads((out/'COMMITTED.json').read_text()); self.assertEqual(commit['references'],3)
   refs=[]
   for i in (1,2,3):
    row=json.loads((out/f'replica-{i}.json').read_text()); self.assertEqual(set(row),probe.RECEIPT_FIELDS); refs.append(row)
   self.assertEqual([r['replica'] for r in refs],[1,2,3]); self.assertTrue(all(r['status']=='measured' for r in refs))
   outer=json.loads((out/'outer-receipt.json').read_text()); self.assertEqual(outer['raw_worker_exit_code'],0); self.assertTrue(outer['process_group_absent']); self.assertEqual(outer['stop_reason'],None)
   self.assertTrue(marker.exists())
 def test_bool_replica_and_seed_bounds_rejected(self):
  v=json.loads((BASE/'confirmed324-seed-vectors-parent-20261026-r1'/'seed-vectors.json').read_text()); v['vectors'][0]['replica']=True
  with self.assertRaises(ValueError): probe.validate_vectors(v)
  v=json.loads((BASE/'confirmed324-seed-vectors-parent-20261026-r1'/'seed-vectors.json').read_text()); v['vectors'][0]['seeds']['numpy_global_seed']=2**32
  with self.assertRaises(ValueError): probe.validate_vectors(v)
if __name__=='__main__': unittest.main()
