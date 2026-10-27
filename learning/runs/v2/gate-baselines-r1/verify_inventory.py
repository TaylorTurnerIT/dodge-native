"""Final inventory audit, retaining the first packaging check and its correction."""
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode=True
E=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('audit',E/'audit_gate.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):
    with p.open('x') as h:json.dump(x,h,indent=2,sort_keys=True,allow_nan=False);h.write('\n')
first=a.m0.parse((E/'final-verification.json').read_text())
mismatches=[{'path':rel,'expected_sha256':expected,'actual_sha256':sha(E/rel)} for rel,expected in first['evidence_files_sha256'].items() if sha(E/rel)!=expected]
assert [x['path'] for x in mismatches]==['finalize.log']
write(E/'inventory-audit-r1.json',{'status':'failed','scope':'first final packaging inventory only','mismatches':mismatches,
    'native_audits_affected':False,'native_rerun':False,'source':str(E/'finalize_gate.py'),
    'cause':'finalize_gate.py inventories finalize.log before printing its final stdout into that same redirected log.'})
write(E/'inventory-correction.json',{'status':'source_backed_packaging_correction',
    'superseded_inventory':'final-verification.json','failed_attempt':'inventory-audit-r1.json',
    'corrected_inventory':'final-verification-r2.json',
    'source_evidence':{'path':'finalize_gate.py','sha256':sha(E/'finalize_gate.py'),
        'inventory_expression':'evidence_files_sha256 iterates every existing evidence file before final print',
        'launch_redirection':'python3 .../finalize_gate.py > .../finalize.log 2>&1'},
    'correction':'Build inventory after redirected finalizer log has closed; write stdout only to tool output. Preserve original report and mismatch.',
    'native_reruns':0,'native_auditor_source_changed':False,'D3_D1_audits_remain_first_attempt_passes':True})
summary=a.m0.parse((E/'results-summary.json').read_text())
summary['failed_checker_attempts']=[{'path':'inventory-audit-r1.json','scope':'packaging only; active stdout log hash','corrected_by':'final-verification-r2.json'}]
summary['supersedes_summary']='results-summary.json'
summary['final_inventory']='final-verification-r2.json'
write(E/'results-summary-r2.json',summary)
# Recheck current immutable identities, without another native experiment.
supervisor=a.m0.parse((E/'supervisor.json').read_text())
for name in ('pre-d3','pre-d1','post-campaign'):
    identity=a.m0.parse((E/f'{name}-identity.json').read_text())
    assert identity['tracked_count']==33
    for rel,expected in identity['all_tracked_head_sha256'].items():assert sha(a.WORKTREE/rel)==expected
    for rel,expected in identity['harness_doc_sha256'].items():assert sha(a.WORKTREE/rel)==expected
    assert sha(Path(identity['executable']))==identity['executable_sha256']
for name in a.RUNS:
    report=a.m0.parse((E/f'{name}-audit-r1.json').read_text())
    assert report['status']=='registered_receipts_verified'
    for path,expected in report['artifact_sha256'].items():assert sha(Path(path))==expected
for row in a.m0.parse((E/'native-results/copy-manifest.json').read_text())['files']:
    assert sha(Path(row['source']))==sha(Path(row['copy']))==row['sha256']==row['copy_sha256']
validated={}
for base in [E]+[a.WORKTREE/r['output'] for r in a.RUNS.values()]:
    for p in sorted(base.rglob('*')):
        if not p.is_file():continue
        if p.suffix=='.json':
            a.m0.parse(p.read_text());subprocess.run([sys.executable,'-m','json.tool',str(p)],stdout=subprocess.DEVNULL,check=True)
            validated[str(p)]={'kind':'json','sha256':sha(p)}
        if p.suffix=='.jsonl':
            raw=p.read_bytes();assert raw.endswith(b'\n');lines=raw.decode().splitlines();assert all(lines)
            for line in lines:a.m0.parse(line)
            validated[str(p)]={'kind':'jsonl','records':len(lines),'sha256':sha(p)}
now=dt.datetime.now(dt.timezone.utc)
elapsed=(now-dt.datetime.fromisoformat(supervisor['full_task_started_at_utc'])).total_seconds();assert elapsed<=1500
inventory={str(p.relative_to(E)):sha(p) for p in sorted(E.rglob('*')) if p.is_file()}
result={'status':'passed','verified_at_utc':now.isoformat(),'full_task_elapsed_seconds':elapsed,'full_task_budget_seconds':1500,
    'completed_native_records':3300,'native_receipt_checks':summary['checks'],
    'all_JSON_and_JSONL_finite_complete_and_duplicate_key_free':True,'validated_json_jsonl':validated,
    'evidence_files_sha256':inventory,'inventory_excludes_only_itself':True,'supersedes':'final-verification.json',
    'retained_failed_inventory_attempt':'inventory-audit-r1.json','source_backed_correction':'inventory-correction.json',
    'native_audit_status':'both_first_attempt_passed_no_rerun','current_source_and_executable_identities':'verified',
    'mutable_parent_state':'snapshotted reads only; current parent state not required to retain old hash'}
write(E/'final-verification-r2.json',result)
subprocess.run([sys.executable,'-m','json.tool',str(E/'final-verification-r2.json')],stdout=subprocess.DEVNULL,check=True)
# Verify again after inventory serialization; no inventoried file remains open for mutation.
for rel,expected in inventory.items():assert sha(E/rel)==expected
print(json.dumps({'status':'passed','records':3300,'checks':summary['checks'],'full_task_elapsed_seconds':elapsed,
    'verified_json_jsonl':len(validated)+1,'stable_inventory_files':len(inventory),'inventory_correction_retained':True},sort_keys=True))
