from pathlib import Path
import json,hashlib,datetime,subprocess,sys,ast
O=Path(__file__).resolve().parent;R=Path.cwd();H=O.parent/'postovernight-long-D2-guard-prepare-r1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
v=read(O/'verification.json');i=read(H/'long-identity.json');old=read(O.parent/'postovernight-long-D2-prepare-r4/long-identity.json');full=read(H/'expanded-inventory.json')['full_pins']
older=old['retained_r3_union'];assert len(older)==9675 and all(full.get(k)==d for k,d in older.items())
# Correct a local review label. 9691 was R4's original-input collection, not its retained R3 union.
supp={'retained_older_union':len(older),'retained_older_union_verified':True,'local_review_label_correction':{'file':'verification.json','field':'retained_older_original_union','recorded_value':9691,'actual_meaning':'R4 original_input_pins count','correct_9675_union_source':'postovernight-long-D2-prepare-r4/long-identity.json:retained_r3_union','candidate_evidence_error':False}}
matdir=H/'attempts/matrix-01-cases';matrix=read(matdir/'summary.json');tested=read(matdir/'tested-sources.json');sup_sources={n:sha(matdir/'sources'/n)==d for n,d in tested.items()};assert all(sup_sources.values())
supp.update(matrix_source_snapshot_hashes_valid=sup_sources,matrix_current_controller_executor_equal=all(sha(matdir/'sources'/n)==sha(H/n) for n in ['long_d2.py','long_d2_executor.py']),matrix_case_count=len(matrix['results']),matrix_expected_raw_exits_match=all(row['expected']==row['raw_wait']['returncode'] for row in matrix['results']),matrix_harness_kills=sum(bool(row['harness_kill_required']) for row in matrix['results']),matrix_injections_reached=all(row['injection_reached'] for row in matrix['results']),matrix_acceptance_matches_expected=all(row['observed_acceptance']==(row['expected'] in [0,2]) for row in matrix['results']))
assert supp['matrix_current_controller_executor_equal'] and supp['matrix_expected_raw_exits_match'] and supp['matrix_acceptance_matches_expected']
clock=read(H/'clock-correction.json');final=read(H/'implementation-result-final.json');a=datetime.datetime.fromisoformat(clock['parent_task_registered_at_utc']);b=datetime.datetime.fromisoformat(clock['observed_at_utc']);supp['clock_correction']={'UTC_upper_bound_recomputed':(b-a).total_seconds(),'final_matches':final['preparation_elapsed_seconds_upper_bound']==(b-a).total_seconds(),'invalid_502789_subtraction_retained_only_in_superseded_evidence':True,'guard_stress_clock_scope':'one registered interpreter; no cross-interpreter subtraction used here'}
# Record source chronology, without treating aggregate stdout as new execution.
supp['attempts']={}
for name in ['units-01','units-02','units-03','units-04','units-05','stress-01','postfreeze-ordering-01']:
 p=H/'attempts'/name/'command-result.json'
 if p.exists():supp['attempts'][name]=read(p)
# Hash every review input subsequently quoted or used; inventory recursively binds candidate contents.
inputs=read(O/'input-hashes.json')
for p in list(H.glob('*.py'))+list(H.glob('*.json'))+[H/'README.md',R/'learning/runs/v2/postovernight-long-D2-guard-parent-preflight-r1/verification.json']:
 inputs[str(p.relative_to(R))]=sha(p)
for p in (H/'attempts').rglob('command-result.json'):inputs[str(p.relative_to(R))]=sha(p)
for rel in ['attempts/units-05/raw.log','attempts/units-05/unit-result.json','attempts/matrix-01-cases/summary.json','attempts/matrix-01-cases/tested-sources.json','attempts/stress-01/stress-result.json','attempts/postfreeze-ordering-01/raw.log','attempts/stress-01/stress-registration.json','attempts/stress-01/legacy-substitutions.json']:
 inputs[str((H/rel).relative_to(R))]=sha(H/rel)
for p in [O.parent/'postovernight-long-D2-prepare-r4/long_d2.py',O.parent/'postovernight-long-D2-prepare-r4/long_d2_executor.py',O.parent/'postovernight-long-D2-prepare-r4/long-identity.json']:
 inputs[str(p.relative_to(R))]=sha(p)
for p in [O/'input-hashes-final.json',O/'verification-supplement.json']:
 data=inputs if p.name=='input-hashes-final.json' else supp;p.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:v for k,v in supp.items() if k not in ['matrix_source_snapshot_hashes_valid','attempts']},indent=2));print('attempt raw exits:',{k:v['raw_exit'] for k,v in supp['attempts'].items()})
