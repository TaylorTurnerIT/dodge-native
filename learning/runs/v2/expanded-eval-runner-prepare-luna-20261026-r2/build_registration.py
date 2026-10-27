"""Draft builder only. Emits evaluator-compatible shape; parent pins remain pending."""
from __future__ import annotations
import hashlib,json,math
from pathlib import Path
ROOT=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79');V2=ROOT/'learning/runs/v2'
SCHEMA='expanded_D2_evaluation_registration_v1'
PROPOSAL=V2/'expanded-evaluation-registration-proposal-parent-20261026-r5/proposal.json';PROPOSAL_SHA='187e0464ba966b29124b29cf606c831d7097adeea99ccfc0e336598ad3fc9765'
ACCEPTED=V2/'D2-retained324-linear-parent-terminal-audit-20261026-r1/retained-best-candidate-receipt.json';ACCEPTED_SHA='cb3645899b5cb660d26d44645e00b3f53c5d0c8341b645b3b78af6b651d8b016'
TRAINING=V2/'D2-retained324-linear-integrated-luna-20261026-r4/registration-final-r2.json';TRAINING_SHA='0a6bf98221689ffcf62a28289dae7bb98eb89bc8d3c02b93127f4a04df75cb4e'
GOLDEN=V2/'D2-retained324-linear-lr-20261026-r1/development-000348.jsonl';GOLDEN_SHA='d6e914345dcc955f678db41eb08d9f20af8e77490652f8d25f7ee09550a63a03'
EVALUATOR=V2/'expanded-evaluator-publication-repair-parent-20261026-r4/expanded_eval.py';EVALUATOR_SHA='a3439c33152b082471cd9f9a36ef4bb03783b9544ae7c1e3fe1878e607b128aa'
NATIVE_SHA='022d41dde9bace0b4f4c4c06b9b4ed007bc2c60013cd98734086e587d7bb997e'
RANKING_FRAMES=110592000;CONFIRMATION_FRAMES=73728000;CLEANUP=10

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def dump(p,d):Path(p).write_text(json.dumps(d,sort_keys=True,indent=2)+'\n')
def successful_receipt(path,pin):
 if not path or not pin or sha(path)!=pin:raise ValueError('successful byte-pinned old-dev64 receipt required')
 d=json.loads(Path(path).read_text());reps=d.get('repeats')
 if d.get('schema')!='expanded_eval_dev64_benchmark_receipt_v1' or d.get('candidate_update')!=348 or d.get('cohort_name')!='benchmark_dev64':raise ValueError('receipt identity must be successful update-348 benchmark_dev64')
 if d.get('complete') is not True or not isinstance(reps,list) or len(reps)!=2:raise ValueError('receipt must prove two successful repeats')
 golden={json.loads(line)['seed']:json.loads(line) for line in GOLDEN.read_text().splitlines() if line}
 fields=('seed','episode_index','alive_frames','gameplay_frames','score_raw_fixed','score','objective_return','terminated','truncated','death_cause','fatal_gameplay_frame','death_observed_lethal_contacts')
 seen=[]
 for r in reps:
  if r.get('candidate_update')!=348 or r.get('cohort_name')!='benchmark_dev64':raise ValueError('repeat identity differs from update-348 benchmark_dev64')
  if r.get('complete') is not True or len(r.get('rows',[]))!=64 or not isinstance(r.get('raw_frames'),int) or r['raw_frames']<=0 or not isinstance(r.get('elapsed_seconds'),(int,float)) or not math.isfinite(r['elapsed_seconds']) or r['elapsed_seconds']<=0:raise ValueError('both repeats need actual rows, raw frames, and elapsed timing')
  if sum(int(x.get('alive_frames',-1)) for x in r['rows'])!=r['raw_frames']:raise ValueError('raw frame count differs from rows')
  by={x.get('seed'):x for x in r['rows']}
  if set(by)!=set(golden) or any(any(by[k].get(f)!=golden[k].get(f) for f in fields) for k in golden):raise ValueError('benchmark repeat differs from accepted golden rows')
  seen.append(by)
 if any(seen[0][k]!=seen[1][k] for k in golden):raise ValueError('benchmark repeat rows differ')
 return d

def make_draft(outdir,*,mode='benchmark',evaluator_path=None,worker_path=None,launcher_path=None,review_records=None,benchmark_receipt_path=None,benchmark_receipt_sha256=None,backend=None,pycache_prefix=None,selection_record=None):
 if mode not in {'benchmark','ranking','confirmation'}:raise ValueError('invalid mode')
 for p,w,label in ((PROPOSAL,PROPOSAL_SHA,'proposal'),(ACCEPTED,ACCEPTED_SHA,'accepted incumbent receipt'),(TRAINING,TRAINING_SHA,'training registration')):
  if sha(p)!=w:raise ValueError(w+' '+label+' pin mismatch')
 proposal=json.loads(PROPOSAL.read_text());training=json.loads(TRAINING.read_text())
 lineage=V2/'expanded-seed-lineage-parent-validation-20261026-r5/receipt.json';lineage_sha=sha(lineage)
 if proposal['seed_gate']['candidate_ancestry_training_disjointness']['sha256']!=lineage_sha:raise ValueError('lineage proof pin mismatch')
 sources={}
 evaluator_path=evaluator_path or EVALUATOR
 for name,p in [('evaluator',evaluator_path),('worker',worker_path),('launcher',launcher_path)]:
  if not p or not Path(p).is_file():raise ValueError('source path required: '+name)
  sources[name+'_path']=str(Path(p).resolve());sources[name+'_sha256']=(EVALUATOR_SHA if name=='evaluator' and Path(p).resolve()==EVALUATOR.resolve() and sha(p)==EVALUATOR_SHA else None)
 out=Path(outdir).resolve();out.mkdir(parents=True,exist_ok=True)
 reviews=[{'path':str(Path(p).resolve()),'sha256':None} for p in (review_records or [])]
 # Explicit review-record extensions keep top-level registration and evaluator limits exact.
 reviews += [{'kind':'runtime_executable','path':training['interpreter'],'sha256':None}]
 if mode in ('ranking','confirmation'):
  receipt=successful_receipt(benchmark_receipt_path,benchmark_receipt_sha256)
  reviews.append({'kind':'old_dev64_benchmark_receipt','path':str(Path(benchmark_receipt_path).resolve()),'sha256':benchmark_receipt_sha256})
  raw=sum(x['raw_frames'] for x in receipt['repeats']);elapsed=sum(float(x['elapsed_seconds']) for x in receipt['repeats'])
  cap=RANKING_FRAMES if mode=='ranking' else CONFIRMATION_FRAMES
  work=math.ceil(2*elapsed/raw*cap+CLEANUP);outer=work+CLEANUP
 else:work=170;outer=180;raw=elapsed=None
 candidates={str(c['phase_update']):c for c in proposal['candidates']}
 rt=training['runtime_continuity'];root=Path(training['runtime_root'])
 if len(rt['member_sha256'])!=13 or rt['member_sha256'].get('dodge_rl/_native.cpython-312-darwin.so')!=NATIVE_SHA:raise ValueError('frozen 13-member runtime/native pins mismatch')
 runtime={'root':str(root),'member_sha256':rt['member_sha256'],'native_relative_path':'dodge_rl/_native.cpython-312-darwin.so','backend':backend,'torch_version':training['runtime_versions']['torch'],'numpy_version':training['runtime_versions']['numpy'],'pycache_prefix':str(Path(pycache_prefix).resolve()) if pycache_prefix else None}
 bm=V2/'expanded-eval-parent-integration-20261026-r1/benchmark-dev64-seed-manifest.json'
 cohorts={'benchmark_dev64':{'manifest_path':str(bm),'manifest_sha256':sha(bm),'count':64},'ranking':{'manifest_path':proposal['cohorts']['ranking']['path'],'manifest_sha256':proposal['cohorts']['ranking']['sha256'],'count':1024},'confirmation':{'manifest_path':proposal['cohorts']['confirmation']['path'],'manifest_sha256':proposal['cohorts']['confirmation']['sha256'],'count':2048}}
 if mode in ('ranking','confirmation'):
  limits['ranking_projected_work_seconds']=math.ceil(2*elapsed/raw*RANKING_FRAMES+CLEANUP)
  limits['confirmation_projected_work_seconds']=math.ceil(2*elapsed/raw*CONFIRMATION_FRAMES+CLEANUP)
 reg={'schema':SCHEMA,'run_id':'PENDING_PARENT_UNIQUE_RUN_ID','mode':mode,'source':sources,'runtime':runtime,'candidates':candidates,'cohorts':cohorts,'selection_record':selection_record,'limits':{'outer_seconds':outer,'work_seconds':work,'cleanup_seconds':CLEANUP,'RSS_bytes':6442450944,'MPS_driver_bytes':6442450944,'guard_poll_seconds':.2,'heartbeat_stale_seconds':2.0,'startup_grace_seconds':12,'projection_multiplier':2.0},'output_dir':str(out/'outputs'),'cancel_path':str(out/'CANCEL'),'one_shot_marker':str(out/'one-shot.claimed'),'state_path':None,'expected_lease':None,'review_records':reviews,'benchmark_reference':{'certificate_path':str(GOLDEN),'certificate_sha256':GOLDEN_SHA},'provenance':{'proposal_path':str(PROPOSAL),'proposal_sha256':PROPOSAL_SHA,'accepted_incumbent_path':str(ACCEPTED),'accepted_incumbent_sha256':ACCEPTED_SHA,'lineage_proof_path':str(lineage),'lineage_proof_sha256':lineage_sha,'training_registration_path':str(TRAINING),'training_registration_sha256':TRAINING_SHA,'evaluator_review_status':'pending','evaluator_candidate_path':str(EVALUATOR),'evaluator_candidate_sha256':EVALUATOR_SHA},'observer':{'sampling_interval_seconds':0.2,'heartbeat_stale_seconds':2.0,'startup_grace_seconds':12,'aggregate_rss_cap_bytes':6442450944,'worker_mps_driver_cap_bytes':6442450944},**({'benchmark_measurement':{'receipt_path':str(Path(benchmark_receipt_path).resolve()),'receipt_sha256':benchmark_receipt_sha256,'raw_frames':raw,'elapsed_seconds':elapsed}} if mode in ('ranking','confirmation') else {})}
 p=out/'registration-draft.json';dump(p,reg);return p

def validate_final(reg):
 required={'schema','run_id','mode','source','runtime','candidates','cohorts','selection_record','limits','output_dir','cancel_path','one_shot_marker','state_path','expected_lease','review_records','benchmark_reference'}
 if not required.issubset(reg) or set(reg)-required-{'provenance','observer','benchmark_measurement'} or reg.get('schema')!=SCHEMA or reg.get('mode') not in {'benchmark','ranking','confirmation'}:raise ValueError('registration interface field set/schema/mode mismatch')
 if set(reg['limits'])-{'outer_seconds','work_seconds','cleanup_seconds','RSS_bytes','MPS_driver_bytes','guard_poll_seconds','heartbeat_stale_seconds','startup_grace_seconds','ranking_projected_work_seconds','confirmation_projected_work_seconds','projection_multiplier'} or not {'outer_seconds','work_seconds','cleanup_seconds','RSS_bytes','MPS_driver_bytes','guard_poll_seconds','heartbeat_stale_seconds'}.issubset(reg['limits']):raise ValueError('evaluator limits field set mismatch')
 if reg.get('provenance',{}).get('evaluator_review_status')!='accepted':raise ValueError('independent evaluator source review is still pending')
 for k in ('evaluator','worker','launcher'):
  p=Path(reg['source'][k+'_path']);pin=reg['source'].get(k+'_sha256')
  if not isinstance(pin,str) or len(pin)!=64 or sha(p)!=pin:raise ValueError(k+' external source pin absent/mismatch')
 for rr in reg['review_records']:
  if not rr.get('sha256') or sha(rr['path'])!=rr['sha256']:raise ValueError('external review/executable/receipt pin absent/mismatch')
 if not any(x.get('kind')=='runtime_executable' for x in reg['review_records']):raise ValueError('runtime executable pin required')
 rt=reg['runtime']
 if len(rt.get('member_sha256') or {})!=13 or rt.get('backend') not in ('cpu','mps'):raise ValueError('13-member runtime and pinned backend required')
 for k in ('torch_version','numpy_version','pycache_prefix'):
  if not rt.get(k):raise ValueError('runtime '+k+' required')
 if not reg['expected_lease'] or not reg['state_path']:raise ValueError('parent lease/ledger required')
 if set(reg['candidates'])!={'180','204','276','300','324','348'} or set(reg['cohorts'])!={'benchmark_dev64','ranking','confirmation'}:raise ValueError('exact candidate/cohort inventories required')
 if not all(Path(reg[k]).is_absolute() for k in ('output_dir','cancel_path','one_shot_marker','state_path')):raise ValueError('parent state/output paths must be absolute')
 if reg['mode']!='confirmation' and reg['selection_record'] is not None:raise ValueError('selection record only valid for confirmation')
 if reg['mode']=='confirmation' and not reg['selection_record']:raise ValueError('confirmation needs exact parent selection record')
 if reg['limits']['outer_seconds']!=reg['limits']['work_seconds']+CLEANUP or reg['limits']['cleanup_seconds']!=CLEANUP:raise ValueError('outer/work cleanup budgets mismatch')
 if reg['mode']=='benchmark':
  if reg['limits']['work_seconds']!=170 or reg['limits']['outer_seconds']!=180:raise ValueError('benchmark budget must be 170/180 seconds')
  if reg['benchmark_reference']!={'certificate_path':str(GOLDEN),'certificate_sha256':GOLDEN_SHA} or sha(GOLDEN)!=GOLDEN_SHA:raise ValueError('accepted 348 JSONL pin mismatch')
 if reg['mode'] in ('ranking','confirmation'):
  refs=[x for x in reg['review_records'] if x.get('kind')=='old_dev64_benchmark_receipt']
  if len(refs)!=1:raise ValueError('one pinned old-dev64 receipt required')
  receipt=successful_receipt(refs[0]['path'],refs[0]['sha256'])
  frames=sum(x['raw_frames'] for x in receipt['repeats']);elapsed=sum(float(x['elapsed_seconds']) for x in receipt['repeats'])
  measurement=reg.get('benchmark_measurement') or {}
  if measurement!={'receipt_path':refs[0]['path'],'receipt_sha256':refs[0]['sha256'],'raw_frames':frames,'elapsed_seconds':elapsed}:raise ValueError('benchmark measurement summary differs from receipt')
  rank=math.ceil(2*elapsed/frames*RANKING_FRAMES+CLEANUP);confirm=math.ceil(2*elapsed/frames*CONFIRMATION_FRAMES+CLEANUP)
  if reg['limits'].get('ranking_projected_work_seconds')!=rank or reg['limits'].get('confirmation_projected_work_seconds')!=confirm or reg['limits'].get('projection_multiplier')!=2.0:raise ValueError('full-cap projections differ from pinned measurement')
  expected=rank if reg['mode']=='ranking' else confirm
  if reg['limits']['work_seconds']!=expected:raise ValueError('work budget differs from selected full-cap projection')
 return True
