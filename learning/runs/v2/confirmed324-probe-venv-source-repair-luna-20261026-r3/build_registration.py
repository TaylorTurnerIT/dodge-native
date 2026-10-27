"""Build a parent-review draft for the dedicated probe supervisor."""
import hashlib,json
from pathlib import Path
RUN=Path(__file__).resolve().parent
VECTORS=RUN.parent/'confirmed324-seed-vectors-parent-20261026-r1'/'seed-vectors.json'
CHECKPOINT=RUN.parent/'D2-retained300-continuation-20261026-r1'/'checkpoint-000324-candidate.pt'
PARENT_RECEIPT=RUN.parent/'D2-retained300-parent-terminal-audit-20261026-r1'/'retained-best-candidate-receipt.json'
ACCEPTANCE=RUN.parent/'expanded-confirmation-parent-20261026-r1'/'parent-acceptance.json'
ACCEPTANCE_SHA='3e84979c4c8da76d0f98666a23f90eb15c1e813ca5edf1001e19daebaf4d5bbd'
FINGERPRINT=RUN.parent/'confirmed324-transition-parent-repair-20261026-r3'/'fingerprints.py'
PRIMITIVE_SHA='4a5d084359ee48fe5351c96e0ec4455fdcd95a428a17bbcf59d0653f6922de98'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def build(*,state_path,expected_lease,marker_path,cancel_path,output_path,python_path,runtime_root,empty_cache_path):
 vraw=VECTORS.read_bytes(); vectors=json.loads(vraw)
 import probe
 probe.validate_vectors(vectors)
 src={'worker_path':str(RUN/'worker_cli.py'),'worker_sha256':sha(RUN/'worker_cli.py'),'supervisor_path':str(RUN/'supervisor_cli.py'),'supervisor_sha256':sha(RUN/'supervisor_cli.py'),'probe_path':str(RUN/'probe.py'),'probe_sha256':sha(RUN/'probe.py'),'fingerprint_path':str(FINGERPRINT),'fingerprint_sha256':sha(FINGERPRINT),'cleanup_primitives_sha256':PRIMITIVE_SHA}
 return {'schema':'d2_layerb_rng_reference_probe_registration_v1','status':'draft_parent_review_required','authority':'none_until_parent_registration_review_and_lease_installation','run_id':'PENDING_PARENT_UNIQUE_RUN_ID','study_id':vectors['study_id'],'source':src,'runtime':{'python_path':str(Path(python_path).absolute()),'python_version':'3.12.15','interpreter_sha256':sha(python_path),'runtime_root':str(Path(runtime_root).resolve()),'torch_version':'2.14.1','numpy_version':'2.5.4','empty_cache_path':str(Path(empty_cache_path).resolve()),'pycache_policy':'PYTHONDONTWRITEBYTECODE=1 -B; ownedemptycache'},'vectors_path':str(VECTORS.resolve()),'vectors_sha256':hashlib.sha256(vraw).hexdigest(),'vectors':vectors,'checkpoint_path':str(CHECKPOINT.resolve()),'checkpoint_sha256':sha(CHECKPOINT),'parent_receipt_path':str(PARENT_RECEIPT.resolve()),'parent_receipt_sha256':sha(PARENT_RECEIPT),'acceptance_path':str(ACCEPTANCE.resolve()),'acceptance_sha256':ACCEPTANCE_SHA,'state_path':str(Path(state_path).resolve()),'expected_lease':expected_lease,'one_shot_marker':str(Path(marker_path).resolve()),'cancel_path':str(Path(cancel_path).resolve()),'output_dir':str(Path(output_path).resolve()),'limits':{'work_seconds':45,'outer_seconds':55,'cleanup_seconds':10,'startup_grace_seconds':12,'RSS_bytes':6*1024**3,'MPS_driver_bytes':6*1024**3,'guard_poll_seconds':.2,'heartbeat_stale_seconds':2.0},'references':{'required_replicas':[1,2,3],'receipt_fields':sorted(probe.RECEIPT_FIELDS),'same_reference_for_both_arms':True}}
if __name__=='__main__': raise SystemExit('Import build() to create a draft; parent must complete and approve registration before execution.')
