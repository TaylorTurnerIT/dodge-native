"""Close audit provenance after the receipt-only audit log has closed."""
import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
BASE = ROOT/'learning/runs/v2'
OUT = BASE/'postovernight-long-D2-failure-parent-audit-r1'
CAM = BASE/'postovernight-long-D2-campaign-r1'
OBS = BASE/'postovernight-long-D2-execution-observer-r1'
PREP = BASE/'postovernight-long-D2-prepare-r4'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def load(p):
    return json.loads(p.read_text())

def save(p,v):
    p.write_text(json.dumps(v,indent=2,sort_keys=True,allow_nan=False)+'\n')

audit = load(OUT/'audit.json')
reported = load(OBS/'execution-result-final.json')
identity = load(CAM/'long-identity.json')
origins = load(CAM/'actual-import-origins.json')
manifest = load(OUT/'input-sha256-manifest.json')
pins = load(OBS/'sourcehashes-before.json')['pins']
supplement = {
    'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'runtime_import_origins_count':len(origins),
    'runtime_import_origins_exact_allowlist':len(origins)==10 and all(
        identity['legacy_module_origins'][v['origin']]=={'mirror':v['mirror'],'sha256':v['sha256']}
        for v in origins.values()),
    'retained_r2_and_r3_pin_union_preserved':all(pins[k]==v for label in ['retained_r2_union','retained_r3_union'] for k,v in identity[label].items()),
    'observer_canonical_counters_match_independent_audit':reported['counters']==audit['counters'],
    'observer_canonical_evaluations_match_independent_audit':all(all(r[k]==s[k] for k in s) for r,s in zip(reported['evaluation_table'],audit['evaluation_table'])) and len(reported['evaluation_table'])==len(audit['evaluation_table']),
    'observer_canonical_status_matches_failed_gate':reported['status']=='failed' and not any(reported[k] for k in ['teacher_qualified','training_parent_eligible','parent_acceptance_condition','progress_gate_passed']),
    'historical_checkpoint_qualification_not_transferred':True,
    'audit_attempts':[{'attempt':1,'outcome':'receipt_parser_error','error':"KeyError('owned')",'script':'audit_stdlib-attempt1.py','stderr':'audit.stderr.log','training_reexecuted':False},{'attempt':2,'outcome':'failure_evidence_consistent','script':'audit_stdlib.py','stderr':'audit-attempt2.stderr.log','training_reexecuted':False}],
    'limits':'JSON receipts and checkpoint-byte hashes only. No checkpoint deserialization, ML/native imports, inference, evaluation, training, source edits, or run acceptance.'
}
for key in ['runtime_import_origins_exact_allowlist','retained_r2_and_r3_pin_union_preserved','observer_canonical_counters_match_independent_audit','observer_canonical_evaluations_match_independent_audit','observer_canonical_status_matches_failed_gate']:
    assert supplement[key],key
save(OUT/'audit-supplement.json',supplement)
assert audit['failure_evidence_consistent'] and not audit['accepted_successful_training']
for p in OUT.glob('*.json'):
    load(p)
save(OUT/'artifact-manifest.json',{'schema':'independent_audit_artifact_manifest_v1','manifest_excludes_itself':True,'logs_closed_before_hashing':True,'files':{str(p.relative_to(OUT)):sha(p) for p in OUT.rglob('*') if p.is_file() and p.name!='artifact-manifest.json'}})
print(json.dumps({'audit_sha256':sha(OUT/'audit.json'),'input_manifest_sha256':sha(OUT/'input-sha256-manifest.json'),'supplement_sha256':sha(OUT/'audit-supplement.json'),'artifact_manifest_sha256':sha(OUT/'artifact-manifest.json'),'checks_passed':len(audit['checks'])},sort_keys=True))
