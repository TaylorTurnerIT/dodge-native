"""CPU-only tests. Fake evaluator/process fixtures are never qualification evidence."""
from __future__ import annotations
import hashlib,json,os,shutil,subprocess,sys,tempfile,time,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,obj):Path(p).write_text(json.dumps(obj,sort_keys=True)+'\n')
def fixture(td,*,sleep_seconds=0,large_log=0,preexisting=False,low_cap=False,wrong_golden=False,heartbeat_stale=.5):
 d=Path(td); run=d/'run';run.mkdir();outdir=run/'outputs';runtime=d/'runtime';(runtime/'dodge_rl').mkdir(parents=True);native=runtime/'dodge_rl/_native.cpython-312-darwin.so';native.write_bytes(b'FAKE NATIVE FIXTURE')
 worker=d/'worker.py';launcher=d/'execute_once.py';evaluator=d/'fake_eval.py'
 shutil.copy(HERE/'worker.py',worker);shutil.copy(HERE/'execute_once.py',launcher)
 native_sha=sha(native)
 for fp in (worker,launcher):
  txt=fp.read_text().replace('022d41dde9bace0b4f4c4c06b9b4ed007bc2c60013cd98734086e587d7bb997e',native_sha).replace('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained324-linear-lr-20261026-r1/development-000348.jsonl',str(d/'golden.jsonl')).replace('d6e914345dcc955f678db41eb08d9f20af8e77490652f8d25f7ee09550a63a03','GOLDEN_SHA_TEST')
  if fp==launcher:txt=txt.replace('VERIFY_FROZEN_RUNTIME=True','VERIFY_FROZEN_RUNTIME=False').replace('VERIFY_PROPOSAL_CANDIDATES=True','VERIFY_PROPOSAL_CANDIDATES=False')
  if low_cap: txt=txt.replace('CAP=6*1024**3','CAP=100')
  fp.write_text(txt)
 evaluator.write_text('''import json,os,time\nfrom pathlib import Path\ndef evaluate_registered(*,registration_path,registration_sha256,candidate_update,cohort_name,output_path,check_guard):\n check_guard()\n print('EVAL_START',flush=True)\n time.sleep(SLEEP)\n reg=json.loads(Path(registration_path).read_text())\n manifest=json.loads(Path(reg['cohorts'][cohort_name]['manifest_path']).read_text());seeds=manifest['seeds']\n candidate=reg['candidates'][str(candidate_update)]\n rows=[{'seed':seed,'episode_index':i,'alive_frames':100+i,'gameplay_frames':101+i,'score_raw_fixed':65536,'score':1.0,'objective_return':1.0,'terminated':True,'truncated':False,'death_cause':'normal_enemy','fatal_gameplay_frame':101+i,'death_observed_lethal_contacts':{}} for i,seed in enumerate(seeds)]\n if BAD_ROW: rows[0]['score']=9.0
 result={'schema':'expanded_D2_candidate_evaluation_v1','complete':True,'candidate_update':candidate_update,'cohort_name':cohort_name,'cohort_sha256':reg['cohorts'][cohort_name]['manifest_sha256'],'checkpoint_sha256':candidate['checkpoint_sha256'],'episodes':len(rows),'rows':rows,'performance':{'mean':123.0},'death_causes':{},'caps':0,'elapsed_seconds':1.0}\n p=Path(output_path);p.parent.mkdir(parents=True,exist_ok=True);fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)\n with os.fdopen(fd,'w') as f:json.dump(result,f,sort_keys=True);f.write('\\n')\n print('X'*LARGE,flush=True)\n return result\n'''.replace('SLEEP',str(sleep_seconds)).replace('LARGE',str(large_log)).replace('BAD_ROW',str(bool(wrong_golden))))
 rows=[{'seed':0xD0000000+i,'episode_index':i,'alive_frames':100+i,'gameplay_frames':101+i,'score_raw_fixed':65536,'score':1.0,'objective_return':1.0,'terminated':True,'truncated':False,'death_cause':'normal_enemy','fatal_gameplay_frame':101+i,'death_observed_lethal_contacts':{}} for i in range(64)]
 cert=d/'golden.jsonl';cert.write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in rows))
 golden_sha=sha(cert)
 for fp in (worker,launcher):fp.write_text(fp.read_text().replace('GOLDEN_SHA_TEST',golden_sha))
 state=d/'ledger.json';lease={'run_id':'fake','kind':'active_inference_diagnostic'};write(state,{'active_inference_diagnostic':lease,'active_long':None,'active_inference':None})
 manifest=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/expanded-eval-parent-integration-20261026-r1/benchmark-dev64-seed-manifest.json')
 proposal=json.loads(Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/expanded-evaluation-registration-proposal-parent-20261026-r5/proposal.json').read_text())
 reviews=d/'review.json';write(reviews,{'review':'synthetic test fixture'})
 members={'dodge_rl/_native.cpython-312-darwin.so':sha(native)}
 for n in range(12):
  rel=f'dodge_rl/fake-{n}.py';(runtime/rel).write_text(str(n));members[rel]=sha(runtime/rel)
 candidates={}
 for n in (180,204,276,300,324,348):
  cp=d/f'cp-{n}';cp.write_bytes(f'cp{n}'.encode());receipt=d/f'receipt-{n}';write(receipt,{'status':'accepted_complete_candidate_from_completed_normal_training_iteration','checkpoint_sha256':sha(cp),'checkpoint_path':str(cp)})
  candidates[str(n)]={'phase_update':n,'checkpoint_path':str(cp),'checkpoint_sha256':sha(cp),'source_receipt_path':str(receipt),'source_receipt_sha256':sha(receipt)}
 source={'worker_path':str(worker),'worker_sha256':sha(worker),'evaluator_path':str(evaluator),'evaluator_sha256':sha(evaluator),'launcher_path':str(launcher),'launcher_sha256':sha(launcher)}
 reg={'schema':'expanded_D2_evaluation_registration_v1','run_id':'fake-run','mode':'benchmark','source':source,'runtime':{'root':str(runtime),'member_sha256':members,'native_relative_path':'dodge_rl/_native.cpython-312-darwin.so','backend':'cpu','torch_version':'fake','numpy_version':'fake','pycache_prefix':str(d/'empty-pycache')},'candidates':candidates,'cohorts':{'benchmark_dev64':{'manifest_path':str(manifest),'manifest_sha256':sha(manifest),'count':64},'ranking':{'manifest_path':proposal['cohorts']['ranking']['path'],'manifest_sha256':proposal['cohorts']['ranking']['sha256'],'count':1024},'confirmation':{'manifest_path':proposal['cohorts']['confirmation']['path'],'manifest_sha256':proposal['cohorts']['confirmation']['sha256'],'count':2048}},'selection_record':None,'benchmark_reference':{'certificate_path':str(cert),'certificate_sha256':sha(cert)},'limits':{'cleanup_seconds':10,'outer_seconds':180,'work_seconds':170,'guard_poll_seconds':.2,'heartbeat_stale_seconds':heartbeat_stale,'RSS_bytes':100 if low_cap else 6442450944,'MPS_driver_bytes':100 if low_cap else 6442450944},'expected_lease':lease,'cancel_path':str(run/'CANCEL'),'one_shot_marker':str(run/'one-shot.claimed'),'output_dir':str(outdir),'state_path':str(state),'review_records':[{'path':str(reviews),'sha256':sha(reviews)},{'kind':'runtime_executable','path':sys.executable,'sha256':sha(sys.executable)}]}
 rp=d/'registration.json';write(rp,reg)
 return {'d':d,'reg':rp,'regsha':sha(rp),'worker':worker,'launcher':launcher,'evaluator':evaluator,'out':outdir/'stage.json','marker':run/'one-shot.claimed','state':state,'lease':lease,'log':outdir/'worker.log'}
def invoke(f,timeout=25):
 return subprocess.run([sys.executable,str(f['launcher']),'--registration',str(f['reg']),'--registration-sha256',f['regsha'],'--worker',str(f['worker']),'--evaluator',str(f['evaluator']),'--stage',f.get('stage','benchmark'),'--candidate-update',str(f.get('update',348)),'--cohort',f.get('cohort','benchmark_dev64'),'--output',str(f['out'])],capture_output=True,text=True,timeout=timeout)

def confirmation_setup(f):
 reg=json.loads(f['reg'].read_text()); reg['mode']='confirmation'
 rankrefs=[]
 for update,c in reg['candidates'].items():
  rp=f['d']/f'rank-{update}.json';write(rp,{'complete':True,'candidate_update':int(update),'cohort_name':'ranking','checkpoint_sha256':c['checkpoint_sha256']});rankrefs.append({'path':str(rp),'sha256':sha(rp)})
 sel=f['d']/'selection.json';write(sel,{'winner_update':180,'winner_checkpoint_sha256':reg['candidates']['180']['checkpoint_sha256'],'incumbent_checkpoint_sha256':reg['candidates']['348']['checkpoint_sha256'],'ranking_results':rankrefs})
 reg['selection_record']={'path':str(sel),'sha256':sha(sel),'winner_update':180,'winner_checkpoint_sha256':reg['candidates']['180']['checkpoint_sha256'],'incumbent_checkpoint_sha256':reg['candidates']['348']['checkpoint_sha256']}
 reps=[]
 for _ in range(2):
  rows=[json.loads(x) for x in (f['d']/'golden.jsonl').read_text().splitlines()];reps.append({'complete':True,'candidate_update':348,'cohort_name':'benchmark_dev64','rows':rows,'raw_frames':sum(x['alive_frames'] for x in rows),'elapsed_seconds':.0001})
 receipt=f['d']/'benchmark-receipt.json';write(receipt,{'schema':'expanded_eval_dev64_benchmark_receipt_v1','complete':True,'candidate_update':348,'cohort_name':'benchmark_dev64','repeats':reps})
 reg['review_records'].append({'kind':'old_dev64_benchmark_receipt','path':str(receipt),'sha256':sha(receipt)})
 raw=sum(x['raw_frames'] for x in reps);elapsed=sum(x['elapsed_seconds'] for x in reps)
 rank=__import__('math').ceil(2*elapsed/raw*110592000+10);confirm=__import__('math').ceil(2*elapsed/raw*73728000+10);work=rank if reg['mode']=='ranking' else confirm
 reg['benchmark_measurement']={'receipt_path':str(receipt),'receipt_sha256':sha(receipt),'raw_frames':raw,'elapsed_seconds':elapsed}
 reg['limits'].update({'work_seconds':work,'outer_seconds':work+10,'ranking_projected_work_seconds':rank,'confirmation_projected_work_seconds':confirm,'projection_multiplier':2.0,'startup_grace_seconds':1})
 write(f['reg'],reg);f['regsha']=sha(f['reg']);f['stage']='confirmation';f['update']=180;f['cohort']='confirmation'
 f['out']=Path(reg['output_dir'])/'confirm.json';return sel


def ranking_setup(f):
 reg=json.loads(f['reg'].read_text());reg['mode']='ranking'
 rows=[json.loads(x) for x in (f['d']/'golden.jsonl').read_text().splitlines()]
 reps=[{'complete':True,'candidate_update':348,'cohort_name':'benchmark_dev64','rows':rows,'raw_frames':sum(x['alive_frames'] for x in rows),'elapsed_seconds':.0001} for _ in range(2)]
 receipt=f['d']/'benchmark-receipt.json';write(receipt,{'schema':'expanded_eval_dev64_benchmark_receipt_v1','complete':True,'candidate_update':348,'cohort_name':'benchmark_dev64','repeats':reps})
 reg['review_records'].append({'kind':'old_dev64_benchmark_receipt','path':str(receipt),'sha256':sha(receipt)})
 reg['benchmark_measurement']={'receipt_path':str(receipt),'receipt_sha256':sha(receipt),'raw_frames':sum(x['raw_frames'] for x in reps),'elapsed_seconds':sum(x['elapsed_seconds'] for x in reps)}
 rank=__import__('math').ceil(2*sum(x['elapsed_seconds'] for x in reps)/sum(x['raw_frames'] for x in reps)*110592000+10);confirm=__import__('math').ceil(2*sum(x['elapsed_seconds'] for x in reps)/sum(x['raw_frames'] for x in reps)*73728000+10)
 reg['limits'].update({'work_seconds':rank,'outer_seconds':rank+10,'ranking_projected_work_seconds':rank,'confirmation_projected_work_seconds':confirm,'projection_multiplier':2.0,'startup_grace_seconds':1})
 write(f['reg'],reg);f['regsha']=sha(f['reg']);f['stage']='ranking';f['update']=348;f['cohort']='ranking';f['out']=Path(reg['output_dir'])/'ranking.json'

class RunnerTests(unittest.TestCase):
 def test_benchmark_bootstraps_without_prior_measurement_and_runs_worker(self):
  with tempfile.TemporaryDirectory() as td:
   f=fixture(td,large_log=250000)
   p=invoke(f)
   self.assertEqual(p.returncode,0,p.stderr+p.stdout+'\nLOG\n'+(f['log'].read_text() if f['log'].exists() else 'none'))
   self.assertTrue(f['marker'].exists());self.assertTrue(f['log'].stat().st_size>200000)
   receipt=json.loads(f['out'].read_text())
   self.assertEqual(receipt['schema'],'expanded_eval_dev64_benchmark_receipt_v1')
   self.assertEqual(len(receipt['repeats']),2)
   self.assertTrue(f['out'].with_suffix('.json.outer-receipt.json').exists())
 def test_preflight_failure_leaves_marker_unspent(self):
  with tempfile.TemporaryDirectory() as td:
   f=fixture(td);f['state'].write_text('{}')
   p=invoke(f);self.assertNotEqual(p.returncode,0);self.assertFalse(f['marker'].exists())
 def test_registration_change_rejected_before_claim(self):
  with tempfile.TemporaryDirectory() as td:
   f=fixture(td); f['reg'].write_text(f['reg'].read_text()+' ')
   p=invoke(f);self.assertNotEqual(p.returncode,0);self.assertFalse(f['marker'].exists())
 def test_existing_output_rejected_before_claim(self):
  with tempfile.TemporaryDirectory() as td:
   f=fixture(td);f['out'].parent.mkdir();f['out'].write_text('preserve')
   p=invoke(f);self.assertNotEqual(p.returncode,0);self.assertFalse(f['marker'].exists());self.assertEqual(f['out'].read_text(),'preserve')
 def test_stale_worker_heartbeat_stops_and_receipt_survives(self):
  with tempfile.TemporaryDirectory() as td:
   f=fixture(td,sleep_seconds=3)
   p=invoke(f,timeout=15);self.assertNotEqual(p.returncode,0)
   rec=f['out'].with_suffix('.json.outer-receipt.json');self.assertTrue(rec.exists())
   self.assertIn('heartbeat',json.loads(rec.read_text())['stop_reason'])
 def test_lease_change_stops_worker_and_keeps_raw_exit_receipt(self):
  with tempfile.TemporaryDirectory() as td:
   f=fixture(td,sleep_seconds=3,heartbeat_stale=5)
   proc=subprocess.Popen([sys.executable,str(f['launcher']),'--registration',str(f['reg']),'--registration-sha256',f['regsha'],'--worker',str(f['worker']),'--evaluator',str(f['evaluator']),'--stage',f.get('stage','benchmark'),'--candidate-update',str(f.get('update',348)),'--cohort',f.get('cohort','benchmark_dev64'),'--output',str(f['out'])],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
   deadline=time.time()+6
   while not f['marker'].exists() and time.time()<deadline:time.sleep(.02)
   write(f['state'],{'active_inference_diagnostic':{'run_id':'changed'},'active_long':None,'active_inference':None})
   _,err=proc.communicate(timeout=10);self.assertNotEqual(proc.returncode,0,err)
   rec=f['out'].with_suffix('.json.outer-receipt.json');self.assertTrue(rec.exists());self.assertTrue(json.loads(rec.read_text())['process_group_absent'])
 def test_source_pin_change_fails_before_marker(self):
  with tempfile.TemporaryDirectory() as td:
   f=fixture(td);f['worker'].write_text(f['worker'].read_text()+'\n# changed')
   p=invoke(f);self.assertNotEqual(p.returncode,0);self.assertFalse(f['marker'].exists())
 def test_source_pin_change_during_worker_stops_run(self):
  with tempfile.TemporaryDirectory() as td:
   f=fixture(td,sleep_seconds=3)
   proc=subprocess.Popen([sys.executable,str(f['launcher']),'--registration',str(f['reg']),'--registration-sha256',f['regsha'],'--worker',str(f['worker']),'--evaluator',str(f['evaluator']),'--stage','benchmark','--candidate-update','348','--cohort','benchmark_dev64','--output',str(f['out'])],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
   deadline=time.time()+6
   while (not f['log'].exists() or 'EVAL_START' not in f['log'].read_text()) and time.time()<deadline:time.sleep(.02)
   f['evaluator'].write_text(f['evaluator'].read_text()+'\n# mutated during evaluation')
   _,err=proc.communicate(timeout=10);self.assertNotEqual(proc.returncode,0,err)
   rec=f['out'].with_suffix('.json.outer-receipt.json');self.assertTrue(rec.exists());self.assertIn('source_or_marker_invalid',json.loads(rec.read_text())['stop_reason'])
 def test_golden_truth_mismatch_stops_after_claim(self):
  with tempfile.TemporaryDirectory() as td:
   f=fixture(td,wrong_golden=True);reg=json.loads(f['reg'].read_text());reg['source']['evaluator_sha256']=sha(f['evaluator']);write(f['reg'],reg);f['regsha']=sha(f['reg'])
   # A source pin change is external in a registered fixture, so refresh dependent hash only.
   p=invoke(f);self.assertNotEqual(p.returncode,0);self.assertTrue(f['marker'].exists())
   rec=f['out'].with_suffix('.json.outer-receipt.json');self.assertTrue(rec.exists());self.assertTrue(json.loads(rec.read_text())['process_group_absent'])
 def test_candidate_input_pin_mutation_fails_before_marker(self):
  with tempfile.TemporaryDirectory() as td:
   f=fixture(td);reg=json.loads(f['reg'].read_text());Path(reg['candidates']['180']['checkpoint_path']).write_bytes(b'changed');write(f['reg'],reg)
   f['regsha']=sha(f['reg']);p=invoke(f);self.assertNotEqual(p.returncode,0);self.assertFalse(f['marker'].exists())
 def test_low_resource_cap_stops_and_preserves_receipt(self):
  with tempfile.TemporaryDirectory() as td:
   f=fixture(td,low_cap=True,sleep_seconds=2);p=invoke(f);self.assertNotEqual(p.returncode,0,p.stderr+p.stdout+'\n'+(f['log'].read_text() if f['log'].exists() else 'no log'))
   rec=f['out'].with_suffix('.json.outer-receipt.json');self.assertTrue(rec.exists());self.assertEqual(json.loads(rec.read_text())['stop_reason'],'rss_limit')
 def test_mps_driver_cap_is_enforced_from_worker_heartbeat(self):
  with tempfile.TemporaryDirectory() as td:
   f=fixture(td,sleep_seconds=3,heartbeat_stale=5)
   proc=subprocess.Popen([sys.executable,str(f['launcher']),'--registration',str(f['reg']),'--registration-sha256',f['regsha'],'--worker',str(f['worker']),'--evaluator',str(f['evaluator']),'--stage','benchmark','--candidate-update','348','--cohort','benchmark_dev64','--output',str(f['out'])],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
   hb=f['out'].parent/'worker-heartbeat.json';deadline=time.time()+6
   while (not hb.exists() or not f['log'].exists() or 'EVAL_START' not in f['log'].read_text()) and time.time()<deadline:time.sleep(.02)
   h=json.loads(hb.read_text());h['timestamp_ns']=time.time_ns();h['mps_driver_bytes']=6442450945;write(hb,h)
   _,err=proc.communicate(timeout=10);self.assertNotEqual(proc.returncode,0,err)
   rec=f['out'].with_suffix('.json.outer-receipt.json');self.assertEqual(json.loads(rec.read_text())['stop_reason'],'mps_limit')
 def test_ranking_uses_one_worker_for_six_serial_calls(self):
  with tempfile.TemporaryDirectory() as td:
   f=fixture(td);ranking_setup(f);p=invoke(f);self.assertEqual(p.returncode,0,p.stderr+p.stdout)
   bundle=json.loads(f['out'].read_text());self.assertEqual({r['candidate_update'] for r in bundle['candidate_results']},{180,204,276,300,324,348})
   self.assertEqual(len(list(f['out'].parent.glob('ranking-candidate-*.json'))),6)
 def test_confirmation_runs_only_locked_winner_and_348(self):
  with tempfile.TemporaryDirectory() as td:
   f=fixture(td);confirmation_setup(f);p=invoke(f);self.assertEqual(p.returncode,0,p.stderr+p.stdout)
   bundle=json.loads(f['out'].read_text());self.assertEqual([r['candidate_update'] for r in bundle['results']],[180,348])
 def test_confirmation_selection_file_tamper_leaves_marker_unspent(self):
  with tempfile.TemporaryDirectory() as td:
   f=fixture(td);sel=confirmation_setup(f);sel.write_text(sel.read_text()+' ')
   f['regsha']=sha(f['reg']);p=invoke(f);self.assertNotEqual(p.returncode,0);self.assertFalse(f['marker'].exists())
 def test_benchmark_draft_needs_no_prior_throughput_measurement(self):
  import build_registration
  with tempfile.TemporaryDirectory() as td:
   d=Path(td); files=[]
   for n in ('worker.py','launcher.py','review.json'):
    q=d/n;q.write_text('fixture');files.append(q)
   draft=build_registration.make_draft(d/'draft',worker_path=files[0],launcher_path=files[1],review_records=[files[2]],backend=None,pycache_prefix=d/'pycache')
   reg=json.loads(draft.read_text());self.assertEqual((reg['limits']['work_seconds'],reg['limits']['outer_seconds']),(170,180))
   self.assertEqual(len(reg['runtime']['member_sha256']),13)
   self.assertEqual(reg['source']['evaluator_path'],str(build_registration.EVALUATOR))
   self.assertEqual(reg['source']['evaluator_sha256'],build_registration.EVALUATOR_SHA)
   self.assertEqual(reg['provenance']['evaluator_review_status'],'pending')
   with self.assertRaisesRegex(ValueError,'source review'):build_registration.validate_final(reg)
if __name__=='__main__':unittest.main(verbosity=2)
