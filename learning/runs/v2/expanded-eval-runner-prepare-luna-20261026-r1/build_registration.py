"""Parent interface builder. Draft only; final registration requires reviewed frozen source pins."""
from __future__ import annotations
import hashlib, json, math
from pathlib import Path

SCHEMA='expanded_D2_evaluation_registration_v1'
PROPOSAL=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/expanded-evaluation-registration-proposal-parent-20261026-r5/proposal.json')
PROPOSAL_SHA='187e0464ba966b29124b29cf606c831d7097adeea99ccfc0e336598ad3fc9765'
RECEIPT=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained324-linear-parent-terminal-audit-20261026-r1/retained-best-candidate-receipt.json')
RECEIPT_SHA='cb3645899b5cb660d26d44645e00b3f53c5d0c8341b645b3b78af6b651d8b016'
LINEAGE=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/expanded-seed-lineage-parent-validation-20261026-r5/receipt.json')

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def dump(path,obj): Path(path).write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n')
def make_draft(outdir:Path, *, evaluator_path=None, worker_path=None, launcher_path=None, review_records=None, measured_dev64_seconds=None, mode="benchmark", selection_record=None):
 outdir=Path(outdir).resolve(); outdir.mkdir(parents=True,exist_ok=True)
 if mode not in {'benchmark','ranking','confirmation'}: raise ValueError('invalid mode')
 if mode=='confirmation' and not selection_record: raise ValueError('confirmation needs exact parent selection record')
 if sha(PROPOSAL)!=PROPOSAL_SHA or sha(RECEIPT)!=RECEIPT_SHA: raise ValueError('frozen proposal or accepted incumbent receipt digest mismatch')
 proposal=json.loads(PROPOSAL.read_text()); accepted=json.loads(RECEIPT.read_text())
 lineage=json.loads(LINEAGE.read_text()); lineage_sha=sha(LINEAGE)
 if proposal['seed_gate']['candidate_ancestry_training_disjointness']['sha256']!=lineage_sha: raise ValueError('lineage proof pin mismatch; parent reconciliation required')
 if proposal['seed_gate']['candidate_ancestry_training_disjointness']['path']!=str(LINEAGE): raise ValueError('lineage proof path mismatch')
 if not review_records or not all(Path(x).is_file() for x in review_records): raise ValueError('externally pinned source review records required')
 sources={}
 for key,path in [('evaluator',evaluator_path),('worker',worker_path),('launcher',launcher_path)]:
  if not path or not Path(path).is_file(): raise ValueError(f'frozen {key} source required')
  sources[key+'_path']=str(Path(path).resolve()); sources[key+'_sha256']=sha(path)
 if measured_dev64_seconds is None or not math.isfinite(measured_dev64_seconds) or measured_dev64_seconds<=0: raise ValueError('measured old dev64 throughput required')
 # Conservative 2x measured per-episode elapsed projection plus 10s cleanup; measured run includes two determinism repeats.
 seconds_per_episode=measured_dev64_seconds/(64*2)
 ranking_work=math.ceil(seconds_per_episode*6144*2.0); confirmation_work=math.ceil(seconds_per_episode*4096*2.0)
 candidates={}
 for c in proposal['candidates']:
  candidates[str(c['phase_update'])]={**c,'receipt_path':c['source_receipt_path'],'receipt_sha256':c['source_receipt_sha256']}
 root=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
 old=Path('learning/runs/v2/paired-LR-upperD64-evaluator-luna-20261026-r2/seed-manifest.json')
 bm={'schema':'expanded_dev64_benchmark_manifest_v1','role':'benchmark_dev64','count':64,'seeds':list(range(0xD0000000,0xD0000040)),'outcomes_opened':False,'source_seed_basis':'frozen D0000000..D000003f old development harness only'}
 bm_path=outdir/'benchmark-dev64-manifest.json'; dump(bm_path,bm)
 cohorts={'benchmark_dev64':{'manifest_path':str(bm_path),'manifest_sha256':sha(bm_path),'count':64},'ranking':{'manifest_path':proposal['cohorts']['ranking']['path'],'manifest_sha256':proposal['cohorts']['ranking']['sha256'],'count':1024},'confirmation':{'manifest_path':proposal['cohorts']['confirmation']['path'],'manifest_sha256':proposal['cohorts']['confirmation']['sha256'],'count':2048}}
 active_work=170 if mode=='benchmark' else (ranking_work if mode=='ranking' else confirmation_work)
 registration={'schema':SCHEMA,'run_id':'expanded-layerA-unfrozen','mode':mode,'source':sources,'runtime':{'root':str(root),'member_sha256':{},'native_relative_path':'python/dodge_rl/_native.cpython-312-darwin.so','backend':None,'torch_version':None,'numpy_version':None,'pycache_prefix':str(outdir/'pycache')},'candidates':candidates,'cohorts':cohorts,'selection_record':selection_record,'limits':{'outer_seconds':active_work+10,'work_seconds':active_work,'cleanup_seconds':10,'RSS_bytes':6442450944,'MPS_driver_bytes':6442450944,'guard_poll_seconds':0.2,'heartbeat_stale_seconds':2.0,'ranking_projected_work_seconds':ranking_work,'confirmation_projected_work_seconds':confirmation_work,'projection_multiplier':2.0},'expected_lease':None,'cancel_path':str(outdir/'CANCEL'),'one_shot_marker':str(outdir/'one-shot.claimed'),'output_dir':str(outdir/'outputs'),'state_path':None,'review_records':[{'path':str(Path(x).resolve()),'sha256':sha(x)} for x in review_records],'provenance':{'proposal_path':str(PROPOSAL),'proposal_sha256':PROPOSAL_SHA,'accepted_incumbent_path':str(RECEIPT),'accepted_incumbent_sha256':RECEIPT_SHA,'lineage_proof_path':str(LINEAGE),'lineage_proof_sha256':lineage_sha,'incumbent_348_benchmark_summary':{'Worst':375,'Q1':867.0625,'Mean':3098.125,'Q4':6003.875,'Best':8180},'source_old_dev64_seed_manifest':str(root/old)}}
 # Intentional preparation artifact: missing parent-owned lease/state, runtime inventory, benchmark, review and mode-specific selection.
 dest=outdir/'registration-draft.json'; dump(dest,registration)
 return dest

def validate_final(reg):
 if reg.get('schema')!=SCHEMA: raise ValueError('schema mismatch')
 if reg.get('mode') not in {'benchmark','ranking','confirmation'}: raise ValueError('invalid mode')
 if reg.get('expected_lease') is None or reg.get('state_path') is None: raise ValueError('parent-owned lease and ledger path required')
 if reg.get('mode')=='confirmation' and not reg.get('selection_record'): raise ValueError('exact parent selection record required')
 for k in ('evaluator','worker','launcher'):
  p=Path(reg['source'][k+'_path']); pin=reg['source'][k+'_sha256']
  if len(pin)!=64 or sha(p)!=pin: raise ValueError(f'{k} source pin absent, unreviewed, or mismatched')
 if not reg.get('review_records'): raise ValueError('external source review records required')
 return True
