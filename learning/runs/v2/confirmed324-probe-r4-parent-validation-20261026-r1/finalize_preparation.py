"""Generate owned inert preparation artifacts and verify the frozen read set."""
import ast
import copy
import datetime
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import sys

RUN=Path(__file__).absolute().parent
ROOT=RUN.parents[3]
OLD=RUN.parent/'confirmed324-probe-venv-source-repair-luna-20261026-r3'
PARENT=RUN.parent/'confirmed324-rng-reference-parent-20261026-r1'/'registration-final.json'
PARENT_SHA='e0e94321c17dbfc69cbde7da689bab43f8d7088a9c59cda6f30be9727b58f56b'

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p): return json.loads(Path(p).read_text())
def save(name,obj): (RUN/name).write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n')
def info(p): return {'path':str(Path(p).absolute()),'bytes':Path(p).stat().st_size,'sha256':sha(p)}

def main():
    assert Path(sys.executable).absolute()==ROOT/'python/.venv/bin/python'
    assert sys.prefix==str(ROOT/'python/.venv')
    assert sys.dont_write_bytecode and os.environ['PYTHONDONTWRITEBYTECODE']=='1'
    assert os.environ['PYTHONPYCACHEPREFIX']==str(RUN/'empty-pycache')
    assert sha(PARENT)==PARENT_SHA
    before=load(RUN/'preservation-before.json'); original=load(PARENT)
    preservation=[]
    for row in before['files']:
        try:
            actual=sha(row['path'])
            preservation.append(dict(row,after_sha256=actual,unchanged=actual==row['sha256']))
        except OSError as e: preservation.append(dict(row,unchanged=False,error=str(e)))
    parent_states={k:Path(original[k]).exists() for k in ('one_shot_marker','cancel_path','output_dir')}
    caches={str(p):{'exists':p.exists(),'is_directory':p.is_dir(),'entries':sorted(x.name for x in p.iterdir()) if p.is_dir() else None} for p in (RUN/'empty-pycache',OLD/'empty-pycache',Path(original['runtime']['empty_cache_path']))}
    unchanged=all(x['unchanged'] for x in preservation)
    immutable_unchanged=all(x['unchanged'] for x in preservation if x['path']!=original['state_path'])
    state_observation=next(x for x in preservation if x['path']==original['state_path'])
    save('preservation-after.json',{'files':preservation,'all_snapshotted_files_unchanged':unchanged,'immutable_read_set_unchanged':immutable_unchanged,'state_writes_by_this_task':0,'orchestration_state_observation':state_observation,'parent_paths_exist':parent_states,'caches':caches})
    assert immutable_unchanged,'immutable read-set drift: inspect preservation-after.json; do not repair frozen files'
    # The independently managed orchestration state is an observation, never our output.
    # Preserve its before/after hashes; do not reset it to make preservation pass.
    assert not any(parent_states.values())
    assert all(row['exists'] and row['is_directory'] and row['entries']==[] for row in caches.values())

    sys.path.insert(0,str(RUN))
    import build_registration
    lease=copy.deepcopy(original['expected_lease'])
    lease.update(run_id='PENDING_PARENT_UNIQUE_RUN_ID',owner_token='PENDING_PARENT_OWNER_TOKEN',registration_path=str(RUN/'proposed-parent'/'registration-final.json'))
    draft=build_registration.build(state_path=original['state_path'],expected_lease=lease,marker_path=RUN/'proposed-parent'/'one-shot.claimed',cancel_path=RUN/'proposed-parent'/'CANCEL',output_path=RUN/'proposed-parent'/'outputs',python_path=original['runtime']['python_path'],runtime_root=original['runtime']['runtime_root'],empty_cache_path=RUN/'empty-pycache',expected_venv_prefix=original['runtime']['expected_venv_prefix'])
    assert set(draft)==set(original)
    unchanged_contract=('schema','study_id','vectors_path','vectors_sha256','vectors','checkpoint_path','checkpoint_sha256','parent_receipt_path','parent_receipt_sha256','acceptance_path','acceptance_sha256','state_path','limits','references')
    assert all(draft[k]==original[k] for k in unchanged_contract)
    assert {k:v for k,v in draft['runtime'].items() if k!='empty_cache_path'}=={k:v for k,v in original['runtime'].items() if k!='empty_cache_path'}
    assert draft['source']['fingerprint_path']==original['source']['fingerprint_path']
    assert draft['source']['fingerprint_sha256']==original['source']['fingerprint_sha256']
    assert draft['source']['cleanup_primitives_sha256']==original['source']['cleanup_primitives_sha256']
    assert draft['status']=='draft_parent_review_required'
    save('registration-template.json',draft)

    sources=sorted(RUN.glob('*.py'))
    for p in sources: ast.parse(p.read_bytes(),filename=str(p))
    diff=[]
    for p in sources+[RUN/'README.md']:
        old=OLD/p.name
        a=old.read_text().splitlines(keepends=True) if old.exists() else []
        diff.extend(difflib.unified_diff(a,p.read_text().splitlines(keepends=True),fromfile=str(old.relative_to(ROOT)) if old.exists() else '/dev/null',tofile=str(p.relative_to(ROOT))))
    (RUN/'exact-diff.patch').write_text(''.join(diff))
    external=[Path(original['source']['fingerprint_path']),RUN.parent/'confirmation-proof-binding-parent-repair-20261026-r4'/'execute_once.py']
    source_manifest={'schema':'confirmed324_probe_r4_authoritative_source_manifest_v1','authoritative':True,'hash_algorithm':'sha256','source_directory':str(RUN),'files':[info(p) for p in sources],'external_pinned_source':[info(p) for p in external],'probe_unchanged_from_R3':sha(RUN/'probe.py')==sha(OLD/'probe.py'),'interpreter_invocation':info(ROOT/'python/.venv/bin/python')}
    save('source-hashes.json',source_manifest)
    log=(RUN/'tests.log').read_text(); match=re.search(r'Ran (\d+) tests in ([0-9.]+)s\n\nOK\s*$',log)
    assert match and int(match[1])==33
    assert log.count(' ... ok')==33
    methods=re.findall(r'^(test_\w+) \(([^)]+)\) \.\.\. ok$',log,re.MULTILINE)
    save('test-results.json',{'schema':'synthetic_control_results_v1','passed':33,'failed':0,'original_controls_replayed':7,'new_controls':26,'elapsed_seconds':float(match[2]),'tests':[{'method':m,'class':c} for m,c in methods],'final_test_exit_code':0,'initial_development_result':'30 controls; one test-count assertion expected 20 rather than 19; retained tests-initial.log','real_generator_reference_proof':False})
    receipts=[]
    for p in sorted((RUN/'test-tmp').glob('*/out/outer-receipt.json')):
        rec=load(p); receipts.append(dict(info(p),status=rec['status'],stop_reason=rec['stop_reason'],raw_worker_exit_code=rec['raw_worker_exit_code'],process_group_absent=rec['process_group_absent']))
    assert all(row['process_group_absent'] for row in receipts)
    save('synthetic-receipt-index.json',{'scope':'synthetic-only retained initial and final fixtures; no actual parent outputs','receipts':receipts})
    artifacts=['README.md','registration-template.json','exact-diff.patch','source-hashes.json','tests.log','tests-initial.log','test-results.json','synthetic-receipt-index.json','preservation-before.json','preservation-after.json','finalization-initial.log']
    save('receipt.json',{'schema':'confirmed324_probe_signal_postflight_repair_preparation_v1','status':'source_prepared_not_registered_not_runtime_qualified','created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'owned_output':str(RUN),'role':'implementation_sub_agent','findings_repaired':['F1/P1','F2/P1','F3/P2','F4/P2','F5/P2'],'source_manifest':info(RUN/'source-hashes.json'),'original_registration':info(PARENT),'expected_original_registration_sha256':PARENT_SHA,'accepted_checkpoint_sha256':original['checkpoint_sha256'],'accepted_integrity_receipt_sha256':original['parent_receipt_sha256'],'accepted_parent_record_sha256':original['acceptance_sha256'],'contract_fields_preserved':list(unchanged_contract),'runtime_contract_preserved_except_owned_cache_path':True,'limits_unchanged':draft['limits'],'test_summary':load(RUN/'test-results.json'),'actual_interpreter':{'invocation':sys.executable,'version':sys.version,'version_short':sys.version.split()[0],'prefix':sys.prefix,'bytecode_disabled':sys.dont_write_bytecode,'cache':str(RUN/'empty-pycache'),'cache_empty':True},'test_command':'PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX="'+str(RUN/'empty-pycache')+'" '+str(ROOT/'python/.venv/bin/python')+' -B -m unittest discover -s '+str(RUN)+" -p 'test_*.py' -v",'preservation':{'all_snapshotted_files_unchanged':unchanged,'parent_marker_cancel_output_still_absent':True,'root_README_unchanged':True,'parent_state_unchanged':state_observation['unchanged'],'state_writes_by_this_task':0,'immutable_read_set_unchanged':immutable_unchanged,'orchestration_state_drift_observed':not state_observation['unchanged'],'frozen_predecessors_unchanged':True},'execution_scope':{'stdlib_and_inert_source_only':True,'Torch_NumPy_native_project_imports':0,'checkpoint_deserializations':0,'actual_RNG_MPS_calls':0,'models_environments_training_evaluation':0,'actual_campaign_launches':0,'actual_parent_markers_claimed':0,'actual_leases_installed_or_cleared':0,'subdelegations':0,'synthetic_claims_and_subprocesses_only_below_owned_output':True},'evidence_limits':['Synthetic controls and static source preparation only; no real CPU/MPS reference, timing/resource qualification or runtime dependency version verification.','55-second worker/cleanup decisions do not hard-bound blocking filesystem/hash/fsync/receipt finalization.','Startup imports precede first MPS heartbeat; final forced sampling is implemented and fake-cap tested only.','No package-byte pinning claim; runtime_root remains recorded metadata.','Exclusive final JSON writes may leave partial files; no atomic visibility or directory-fsync crash durability claim.','Snapshot equality covers enumerated read set, not every file in the repository.'],'remaining_gates':['Parent review of delivered exact source hashes and controls','Parent successor identity/destination and final registration freeze','Parent fresh live-state audit, exact-lease installation and complete preflight','Separately authorized exactly-once real run and parent output acceptance'],'artifacts':[info(RUN/name) for name in artifacts]})
    print(json.dumps({'status':'prepared','controls_passed':33,'source_files':len(sources),'preservation_observations':len(preservation),'immutable_read_set_unchanged':immutable_unchanged,'orchestration_state_unchanged':state_observation['unchanged'],'source_manifest_sha256':sha(RUN/'source-hashes.json'),'receipt_sha256':sha(RUN/'receipt.json')},sort_keys=True))

if __name__=='__main__': main()
