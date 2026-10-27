"""Build an inert parent-review draft. Never install a lease or claim a marker."""
import hashlib,json,sys
from pathlib import Path
import probe as p
HERE=Path(__file__).resolve().parent

def build(parent_dir=None):
    parent=Path(parent_dir or HERE/'proposed-parent').absolute()
    old=p.read(p.BASE/'confirmed324-probe-finalization-repair-sol-20261026-r5/registration-template.json')
    source={}
    for name,path in {'worker':HERE/'worker_cli.py','supervisor':HERE/'supervisor_cli.py','probe':HERE/'probe.py','fingerprint':p.R3/'fingerprints.py'}.items():
        source[name+'_path']=str(path); source[name+'_sha256']=p.sha(path)
    source['cleanup_primitives_sha256']='4a5d084359ee48fe5351c96e0ec4455fdcd95a428a17bbcf59d0653f6922de98'
    run='confirmed324-restore-probe-PENDING_PARENT_UNIQUE_ID'
    vector=next(v for v in old['vectors']['vectors'] if v['replica']==1)
    ref=p.read(p.BASE/'confirmed324-rng-reference-parent-20261026-r3/parent-terminal-audit.json')['references'][0]
    lease=dict(run_id=run,study_id=p.STUDY,kind='confirmed324_claimed_restore_probe',owner_token='PENDING_PARENT_NEW_TOKEN',parent_checkpoint_sha256=p.PARENT)
    reg={k:old[k] for k in ('vectors_path','vectors_sha256','vectors','checkpoint_path','checkpoint_sha256','parent_receipt_path','parent_receipt_sha256','acceptance_path','acceptance_sha256','state_path')}
    reg.update(schema=p.SCHEMA,status='draft_parent_review_required',authority='none',run_id=run,study_id=p.STUDY,source=source,runtime=dict(old['runtime'],empty_cache_path=str(parent/'empty-pycache')),expected_lease=lease,one_shot_marker=str(parent/(run+'.outer.claimed')),attempt_claim_path=str(parent/(run+'.restore.claimed')),cancel_path=str(parent/'CANCEL'),output_dir=str(parent/run),limits=p.LIMITS,references={'required_replicas':[1],'kind':'existing_initial_CPU_MPS_state_reference'},replica=1,arm=p.ARM,pair_id=p.STUDY+'-replica-1',vector=vector,reference=dict(receipt_path=ref['path'],receipt_sha256=ref['sha256'],vector_sha256=ref['vector_sha256']),input_manifest_path=str(HERE/'input-manifest.json'),input_manifest_sha256=p.sha(HERE/'input-manifest.json'),expected_parent_fingerprints=p.EXPECTED,scope=p.SCOPE,budget_semantics='45s work within 55s outer decisions; cleanup <=10s remaining; no hard filesystem watchdog')
    assert set(reg)==p.FIELDS
    return json.loads(json.dumps(reg))
if __name__=='__main__': raise SystemExit('Import build() for an inert draft; parent freezes, reviews and authorizes separately.')
