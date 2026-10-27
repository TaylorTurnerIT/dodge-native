"""Package owned R5 artifacts; never register, claim, lease or launch real work."""
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
BASE=RUN.parent
OLD=BASE/'confirmed324-probe-signal-postflight-repair-sol-20261026-r4'
PARENTS=[BASE/f'confirmed324-rng-reference-parent-20261026-r{i}'/'registration-final.json' for i in (1,2)]
PARENT_PINS=['e0e94321c17dbfc69cbde7da689bab43f8d7088a9c59cda6f30be9727b58f56b','34b35307a9559ca2a7f74f0ca4567c3d30590af4e285b6295e21bbc8ae898895']


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p): return json.loads(Path(p).read_text())
def info(p): return {'path':str(Path(p).absolute()),'bytes':Path(p).stat().st_size,'sha256':sha(p)}
def save(name,obj): (RUN/name).write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n')


def main():
    assert Path(sys.executable).absolute()==ROOT/'python/.venv/bin/python'
    assert sys.prefix==str(ROOT/'python/.venv') and sys.version.split()[0]=='3.12.15'
    assert sys.dont_write_bytecode and os.environ['PYTHONDONTWRITEBYTECODE']=='1'
    assert os.environ['PYTHONPYCACHEPREFIX']==str(RUN/'empty-pycache')
    assert all(sha(p)==pin for p,pin in zip(PARENTS,PARENT_PINS))
    original,successor=[load(p) for p in PARENTS]

    sources=sorted(RUN.glob('*.py'))
    for p in sources: ast.parse(p.read_bytes(),filename=str(p))
    tested=load(RUN/'tested-source-before.json')
    assert all(sha(row['path'])==row['sha256'] for row in tested['files'])
    tested_paths={row['path'] for row in tested['files']}
    assert {str(p) for p in sources}-tested_paths=={str(RUN/'finalize_preparation.py')}
    unchanged_names=('worker_cli.py','probe.py','build_registration.py','fake_runtime.py','test_campaign.py','test_probe.py')
    assert all(sha(RUN/name)==sha(OLD/name) for name in unchanged_names)

    log=(RUN/'tests.log').read_text()
    match=re.search(r'Ran (\d+) tests in ([0-9.]+)s\n\nOK\s*$',log)
    assert match and int(match[1])==48 and log.count(' ... ok')==48
    methods=re.findall(r'^(test_\w+) \(([^)]+)\)',log,re.MULTILINE)
    assert len(methods)==48 and len(set(methods))==48
    previous=load(OLD/'test-results.json')['tests']
    prior={(r['method'],r['class']) for r in previous}
    assert len(prior)==33 and prior<=set(methods)
    added=set(methods)-prior
    assert len(added)==15 and all(c.startswith('test_finalization_controls.') for m,c in added)
    save('test-results.json',{'schema':'synthetic_control_results_v1','passed':48,'failed':0,'r4_controls_replayed':33,'original_r3_controls_included':7,'new_first_signal_controls':15,'elapsed_seconds':float(match[2]),'test_exit_code':0,'attempts':1,'tests':[{'method':m,'class':c} for m,c in methods],'r4_assertion_adjustment':'Exactly nine signals observed before outcome freeze; three publication-time signals now ignored. Child TERM delivery and raw -SIGKILL exit retained.','real_generator_reference_proof':False})

    receipts=[]; focused=[]
    for p in sorted((RUN/'test-tmp').glob('*/out/outer-receipt.json')):
        rec=load(p)
        assert rec['process_group_absent']
        receipts.append(dict(info(p),status=rec['status'],stop_reason=rec['stop_reason'],raw_worker_exit_code=rec['raw_worker_exit_code'],process_group_absent=rec['process_group_absent'],handled_signals=rec['handled_signals']))
        driver_path=p.parent.parent/'driver-result.json'
        if not p.parent.parent.name.startswith('finalization-'): continue
        evidence=load(driver_path)
        assert evidence['injections']==1 and evidence['handlers_restored'] and evidence['trace_restored']
        assert rec['raw_worker_exit_code']==0 and rec['process_group_remaining']==[]
        assert len(rec['postflight'])==19 and all(row['status']=='pass' for row in rec['postflight'].values())
        assert evidence['post_return_group_rows']==[] and not evidence['post_return_group_error']
        assert evidence['publication_sha256']==evidence['receipt_sha256_after_return']==sha(p)
        if evidence['phase']=='before_freeze':
            assert rec['status']=='partial_failure_preserved' and not evidence['returned']
            assert rec['stop_reason']=='supervisor_signal:'+evidence['signal']
            assert rec['handled_signals']==[evidence['signal']]
        else:
            assert rec['status']=='accepted_pending_parent_postflight' and evidence['returned']
            assert rec['stop_reason'] is None and rec['handled_signals']==[]
            assert evidence['returned_result']==rec
        focused.append({'phase':evidence['phase'],'signal':evidence['signal'],'returned':evidence['returned'],'handlers_restored':True,'raw_worker_exit_code':0,'process_group_absent':True,'status':rec['status'],'stop_reason':rec['stop_reason'],'handled_signals':rec['handled_signals'],'receipt':info(p),'driver_evidence':info(driver_path)})
    assert len(focused)==15
    assert len({(r['phase'],r['signal']) for r in focused})==15
    save('synthetic-receipt-index.json',{'scope':'Owned stdlib synthetic fixtures only; no real parent outputs','receipts':receipts,'first_signal_controls':focused})

    sys.path.insert(0,str(RUN))
    import build_registration
    lease=copy.deepcopy(original['expected_lease'])
    lease.update(run_id='PENDING_PARENT_UNIQUE_RUN_ID',owner_token='PENDING_PARENT_OWNER_TOKEN',registration_path=str(RUN/'proposed-parent'/'registration-final.json'))
    draft=build_registration.build(state_path=original['state_path'],expected_lease=lease,marker_path=RUN/'proposed-parent'/'one-shot.claimed',cancel_path=RUN/'proposed-parent'/'CANCEL',output_path=RUN/'proposed-parent'/'outputs',python_path=original['runtime']['python_path'],runtime_root=original['runtime']['runtime_root'],empty_cache_path=RUN/'empty-pycache',expected_venv_prefix=original['runtime']['expected_venv_prefix'])
    preserved=('schema','study_id','vectors_path','vectors_sha256','vectors','checkpoint_path','checkpoint_sha256','parent_receipt_path','parent_receipt_sha256','acceptance_path','acceptance_sha256','state_path','limits','references')
    assert set(draft)==set(original)==set(successor)
    for old in (original,successor):
        assert all(draft[k]==old[k] for k in preserved)
        assert {k:v for k,v in draft['runtime'].items() if k!='empty_cache_path'}=={k:v for k,v in old['runtime'].items() if k!='empty_cache_path'}
        assert all(draft['source'][k]==old['source'][k] for k in ('fingerprint_path','fingerprint_sha256','cleanup_primitives_sha256'))
    assert draft['status']=='draft_parent_review_required'
    assert not (RUN/'proposed-parent').exists()
    save('registration-template.json',draft)

    def diff(paths):
        result=[]
        for p in paths:
            old=OLD/p.name
            result.extend(difflib.unified_diff(old.read_text().splitlines(keepends=True) if old.exists() else [],p.read_text().splitlines(keepends=True),fromfile=str(old.relative_to(ROOT)) if old.exists() else '/dev/null',tofile=str(p.relative_to(ROOT))))
        return ''.join(result)
    (RUN/'production-diff.patch').write_text(diff([RUN/'supervisor_cli.py',RUN/'worker_cli.py',RUN/'probe.py',RUN/'build_registration.py']))
    (RUN/'exact-diff.patch').write_text(diff(sources+[RUN/'README.md',RUN/'registration-template.json']))
    external=[Path(original['source']['fingerprint_path']),BASE/'confirmation-proof-binding-parent-repair-20261026-r4'/'execute_once.py']
    save('source-hashes.json',{'schema':'confirmed324_probe_r5_authoritative_source_manifest_v1','authoritative':True,'hash_algorithm':'sha256','source_directory':str(RUN),'files':[dict(info(p),validation='48-control suite; exact bytes match tested-source-before.json' if str(p) in tested_paths else 'artifact-packaging helper; AST parsed and run after tests') for p in sources],'external_pinned_source':[info(p) for p in external],'byte_identical_to_R4':list(unchanged_names),'only_production_change':'supervisor finalization outcome flag and signal-handler guard','interpreter_invocation':info(ROOT/'python/.venv/bin/python')})

    before=load(RUN/'preservation-before.json')
    observed=[]
    for row in before['files']:
        actual=sha(row['path'])
        observed.append(dict(row,after_sha256=actual,unchanged=actual==row['sha256']))
    state=next(row for row in observed if row['path']==original['state_path'])
    immutable=all(row['unchanged'] for row in observed if row['path']!=original['state_path'])
    parents=[]
    for path,reg in zip(PARENTS,(original,successor)):
        paths_exist={k:Path(reg[k]).exists() for k in ('one_shot_marker','cancel_path','output_dir')}
        cache=Path(reg['runtime']['empty_cache_path'])
        assert not any(paths_exist.values()) and cache.is_dir() and not any(cache.iterdir())
        parents.append({'registration':info(path),'paths_exist':paths_exist,'cache':str(cache),'cache_entries':[]})
    assert immutable and (RUN/'empty-pycache').is_dir() and not any((RUN/'empty-pycache').iterdir())
    save('preservation-after.json',{'files':observed,'enumerated_files':len(observed),'immutable_read_set_unchanged':immutable,'state_writes_by_this_task':0,'independently_managed_state':state,'parent_observations':parents,'owned_cache_empty':True})

    boundary=next(i for i,line in enumerate((RUN/'supervisor_cli.py').read_text().splitlines(),1) if line.strip()=='outcome_frozen=True')
    artifacts=['README.md','production-diff.patch','exact-diff.patch','source-hashes.json','registration-template.json','tests.log','tested-source-before.json','test-results.json','synthetic-receipt-index.json','preservation-before.json','preservation-after.json']
    save('receipt.json',{'schema':'confirmed324_probe_finalization_repair_preparation_v1','status':'source_prepared_not_registered_not_runtime_qualified','created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'role':'implementation_sub_agent','owned_output':str(RUN),'repaired_finding':'Fresh R4 review R1/P2: first handled signal during otherwise-successful receipt publication could diverge verdict/history/terminal outcome','source_manifest':info(RUN/'source-hashes.json'),'source_predecessor':str(OLD),'reviews':[info(BASE/name/'review.md') for name in ('confirmed324-probe-r3-frozen-registration-review-sol-20261026-r1','confirmed324-probe-r4-frozen-review-sol-20261026-r2')],'frozen_parent_registrations':[info(p) for p in PARENTS],'outcome_policy':{'path':str(RUN/'supervisor_cli.py'),'boundary_line':boundary,'assignment':'outcome_frozen=True','prerequisites':'Worker cleanup/reap, all 19 checks and decisions, artifact inventory and decisions complete','before_boundary':'Handled signals establish failure and append history','after_boundary':'Installed supervisor handler ignores SIGTERM/SIGHUP/SIGINT without changing reason/history/result','restoration':'Policy stays frozen until each original handler is restored; that original policy then resumes','child_signal_mask_changed':False,'published_receipt_mutated':False,'I/O_failure_semantics':'Unchanged: exclusive publication may fail or leave partial JSON; no hard finalization watchdog'},'test_summary':load(RUN/'test-results.json'),'actual_interpreter':dict(tested['interpreter'],version_short=sys.version.split()[0],interpreter_sha256=sha(sys.executable),owned_cache_empty=True),'test_command':tested['planned_test_command'],'test_environment':{'PYTHONDONTWRITEBYTECODE':'1','PYTHONPYCACHEPREFIX':str(RUN/'empty-pycache')},'contract_fields_preserved':list(preserved),'accepted_checkpoint_sha256':original['checkpoint_sha256'],'accepted_integrity_receipt_sha256':original['parent_receipt_sha256'],'accepted_parent_record_sha256':original['acceptance_sha256'],'runtime_contract_preserved_except_owned_cache_path':True,'limits_unchanged':draft['limits'],'preservation':{'enumerated_files':len(observed),'immutable_read_set_unchanged':immutable,'root_README_unchanged':True,'parent_markers_cancel_outputs_absent':True,'parent_registered_caches_empty':True,'state_writes_by_this_task':0,'independently_managed_state_unchanged':state['unchanged']},'execution_scope':{'stdlib_and_inert_owned_source_only':True,'Torch_NumPy_native_project_imports':0,'actual_RNG_MPS_calls':0,'checkpoint_deserializations':0,'models_environments_training_evaluation':0,'actual_campaign_launches':0,'actual_parent_marker_claims':0,'actual_lease_writes':0,'subdelegations':0,'writes_outside_owned_output':0},'evidence_limits':['Synthetic controls and source preparation only; no real CPU/MPS references, dependency/runtime qualification, or resource/timing qualification.','55-second worker/cleanup decisions do not hard-bound blocking filesystem/hash/fsync/receipt finalization.','Startup imports precede the first MPS heartbeat.','Exclusive final JSON writes can leave partial files; no atomic visibility or directory-fsync crash durability.','Package bytes unpinned; runtime_root remains metadata.','Preservation equality covers the enumerated read set, not every file in the repository.'],'remaining_parent_gates':['Exact-source review','Successor identity/destination and final registration freeze','Fresh state/precondition audit and exact lease installation','Separately authorized exactly-once real run','Parent output acceptance'],'artifacts':[info(RUN/name) for name in artifacts]})
    print(json.dumps({'status':'prepared_not_registered','controls_passed':48,'original_R4_replayed':33,'new_controls':15,'source_manifest_sha256':sha(RUN/'source-hashes.json'),'receipt_sha256':sha(RUN/'receipt.json'),'immutable_read_set_unchanged':immutable,'independently_managed_state_unchanged':state['unchanged']},sort_keys=True))


if __name__=='__main__': main()
