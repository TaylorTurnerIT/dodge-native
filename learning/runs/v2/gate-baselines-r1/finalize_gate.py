"""Verify retained copies and complete evidence syntax; write one final inventory."""
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode=True
E=Path(__file__).resolve().parent
ROOT=E.parents[3]
spec=importlib.util.spec_from_file_location('gate_audit',E/'audit_gate.py')
a=importlib.util.module_from_spec(spec); spec.loader.exec_module(a)
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write_new(path,value):
    with path.open('x') as handle:
        json.dump(value,handle,indent=2,sort_keys=True,allow_nan=False); handle.write('\n')
supervisor=a.m0.parse((E/'supervisor.json').read_text())
assert supervisor['status']=='D3_gate_baselines_and_D1_sanity_receipts_independently_verified'
assert sha(E/'audit_gate.py')==supervisor['checker_sha256']
assert sha(E/'run_gate.py')==supervisor['runner_sha256']
assert sha(ROOT/'learning/scripts/v2_run_m0_campaign.py')==supervisor['helper_sha256']
assert sha(ROOT/'docs/v2-gate-baseline-campaign.md')==supervisor['plan_sha256']
assert sha(ROOT/'learning/scripts/v2_audit_m0.py')==a.EXPECTED_AUDITOR_SHA
assert (E/'pre-d3-state-at-read.json').read_bytes() and sha(E/'pre-d3-state-at-read.json')==supervisor['state_sha256_at_launch']
reports={name:a.m0.parse((E/f'{name}-audit-r1.json').read_text()) for name in a.RUNS}
assert all(r['status']=='registered_receipts_verified' for r in reports.values())
assert sum(r['completed_records'] for r in reports.values())==3300
for report in reports.values():
    for path,expected in report['artifact_sha256'].items():
        assert sha(Path(path))==expected, 'audited artifact changed: '+path
copies=a.m0.parse((E/'native-results/copy-manifest.json').read_text())['files']
assert len(copies)==6
for row in copies:
    assert row['sha256']==row['copy_sha256']==sha(Path(row['source']))==sha(Path(row['copy']))
    assert Path(row['source']).read_bytes()==Path(row['copy']).read_bytes()
for phase in supervisor['phases']:
    assert phase['owned_pid']>0 and phase['exit_code']==0 and 'supervisor_failure' not in phase
    assert phase['elapsed_seconds']<=phase['native_wall_limit_seconds']+15
assert len(supervisor['phases'])==2
assert dt.datetime.fromisoformat(supervisor['phases'][0]['finished_at_utc'])<=dt.datetime.fromisoformat(supervisor['phases'][1]['started_at_utc'])
summary={'status':'passed_all_3300_registered_records', 'checks':sum(r['checks'] for r in reports.values()),
    'completed_records':3300,'parent_reconciliation_pending':True,'teacher_qualification':False,
    'provenance':{k:supervisor[k] for k in ['head','executable_sha256','plan_sha256','runner_sha256','checker_sha256','helper_sha256','state_sha256_at_launch']},
    'frozen_D2_auditor_sha256':a.EXPECTED_AUDITOR_SHA,'native_mirror_file_count':len(copies),
    'native_source_directories':[r['native_directory'] for r in reports.values()],
    'native_process_ownership':'Each helper.phase used start_new_session=True; owned_pid is the new process-group ID. No process terminated.',
    'failed_checker_attempts':[], 'native_retries':0,'profile_runs':0,'nested_agents':0,
    'registered_runs':{name:{'settings':r['registered_settings'],'records':r['completed_records'],
        'checks':r['checks'],'resources':r['resources'],'policies':r['policies']} for name,r in reports.items()},
    'capacity_observation':{'enemy_family_max':max(p['max_active_enemy_family_count']['max'] for r in reports.values() for p in r['policies'].values()),
        'active_rect_max':max(p['max_active_pattern_rect_count']['max'] for r in reports.values() for p in r['policies'].values()),
        'enemy_capacity':64,'rect_capacity':16,
        'enemy_overflow_frames':sum(p['enemy_overflow_frames_above_64'] for r in reports.values() for p in r['policies'].values()),
        'rect_overflow_frames':sum(p['rect_overflow_frames_above_16'] for r in reports.values() for p in r['policies'].values()),
        'D3_pattern_ids':sorted({i for p in reports['d3']['policies'].values() for i in p['pattern_ids']}),
        'D1_pattern_ids':sorted({i for p in reports['d1']['policies'].values() for i in p['pattern_ids']})},
    'limitations':reports['d3']['limitations'],
    'source_mutation_boundary':'Only owned evidence scripts/files and the two new native target directories written. Parent dynamic state read and snapshotted, never written by this task.'}
write_new(E/'results-summary.json',summary)
validated={}
for base in (E,*(a.WORKTREE/r['output'] for r in a.RUNS.values())):
    for path in sorted(base.rglob('*')):
        if not path.is_file(): continue
        if path.suffix=='.json':
            a.m0.parse(path.read_text())
            subprocess.run([sys.executable,'-m','json.tool',str(path)],stdout=subprocess.DEVNULL,check=True)
            validated[str(path)]={'kind':'json','sha256':sha(path)}
        elif path.suffix=='.jsonl':
            raw=path.read_bytes(); assert raw.endswith(b'\n')
            lines=raw.decode().splitlines(); assert all(lines)
            for line in lines: a.m0.parse(line)
            validated[str(path)]={'kind':'jsonl','records':len(lines),'sha256':sha(path)}
now=dt.datetime.now(dt.timezone.utc)
elapsed=(now-dt.datetime.fromisoformat(supervisor['full_task_started_at_utc'])).total_seconds()
assert elapsed<=1500
report={'status':'passed','verified_at_utc':now.isoformat(),'full_task_elapsed_seconds':elapsed,'full_task_budget_seconds':1500,
    'all_JSON_and_JSONL_finite_complete_and_duplicate_key_free':True,'validated_json_jsonl':validated,
    'evidence_files_sha256':{str(p.relative_to(E)):sha(p) for p in sorted(E.rglob('*')) if p.is_file()},
    'native_copy_inventory_sha256':sha(E/'native-results/copy-manifest.json'),
    'final_source_identity':supervisor['final_identity'],'current_dynamic_state_not_used_as_static_proof':True}
write_new(E/'final-verification.json',report)
subprocess.run([sys.executable,'-m','json.tool',str(E/'final-verification.json')],stdout=subprocess.DEVNULL,check=True)
print(json.dumps({'status':report['status'],'checks':summary['checks'],'records':3300,'verified_json_jsonl':len(validated)+1,
    'full_task_elapsed_seconds':elapsed,'capacity':summary['capacity_observation']},sort_keys=True),flush=True)
