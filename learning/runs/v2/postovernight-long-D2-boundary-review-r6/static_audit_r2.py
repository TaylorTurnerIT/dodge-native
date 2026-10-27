"""Read-only byte/AST review; never execute candidate validation or import ML."""
from pathlib import Path
import ast,hashlib,json
H=Path(__file__).resolve().parent;ROOT=H.parents[3];B=H.parent/'postovernight-long-D2-boundary-prepare-r6'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for x in iter(lambda:f.read(1024*1024),b''):h.update(x)
    return h.hexdigest()
def load(p):return json.loads(p.read_bytes())
def save(p,v):p.write_text(json.dumps(v,indent=2,sort_keys=True,allow_nan=False)+'\n')
def blocks(p):
    s=p.read_text();ls=s.splitlines(True)
    return {n.name:''.join(ls[n.lineno-1:n.end_lineno]) for n in ast.parse(s).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
def ml(p):
    s=p.read_text();ls=s.splitlines(True);w=next(n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef) and n.name=='worker')
    t=next(n for n in w.body if isinstance(n,ast.With)).body[0]
    return ''.join(ls[t.body[0].lineno-1:t.body[-1].end_lineno])
protected=['Learner','Schedule','run_schedule','environment_kwargs','counter_report','compare_control','tree_fingerprint','assert_equal_tree','validate_long_config','expected_lease','assert_lease','check_module_origins','outcome_fields','result_code']
current=blocks(B/'long_d2.py');comparisons={}
for name in ['postovernight-long-D2-prepare-r4','postovernight-long-D2-guard-prepare-r1','postovernight-long-D2-boundary-prepare-r3']:
    old=H.parent/name/'long_d2.py';before=blocks(old)
    checks={k:current[k]==before[k] for k in protected};checks['worker_ML_try']=ml(old)==ml(B/'long_d2.py')
    assert all(checks.values()),checks
    comparisons[name]=checks
p=load(ROOT/'learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r5.json');identity=load(B/'long-identity.json');cl=load(B/'classification.json');archive=load(B/'archive-manifest.json');native=load(B/'native-manifest.json')
classes={'B':cl['B'],'R':native['files'],'A':archive['files']};union={};duplicates=[]
for label,m in classes.items():
    for name,digest in m.items():
        if name in union:duplicates.append(name)
        union[name]=digest
assert not duplicates
old=archive['original_bindings'];assert len(old)==10091
assert all(union.get(k)==v['sha256'] and classes[v['classification']].get(k)==v['sha256'] for k,v in old.items())
assert archive['original_union_count']==10091 and archive['retained_R3_count']==9675 and archive['retained_R4_count']==9870
legacy={name:{'expected':digest,'actual':sha(ROOT/name),'B':classes['B'].get(str(ROOT/name))==digest} for name,digest in p['base_identity']['sources'].items()}
assert len(legacy)==75 and all(v['expected']==v['actual'] and v['B'] for v in legacy.values())
config_sha=sha(ROOT/p['config_path']);d1_sha=sha(ROOT/p['parent_checkpoint'])
assert config_sha=='2ac814d3842228017d09669364a8391344722da56ad19f41ad9030dbb930c2db'
assert d1_sha=='ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f'
assert identity['config']['phase_settings']['run_seed']==5562873868232098305
manifest=load(B/'capsule-final/capsule-manifest.json');capsule={name:sha(B/'capsule-final'/name) for name in manifest['files']}
assert len(capsule)==119 and capsule==manifest['files']
actual={str(x.relative_to(B/'capsule-final')) for x in (B/'capsule-final').rglob('*') if x.is_file()}
assert actual==set(capsule)|{'capsule-manifest.json'}
# Record source and metadata, excluding parent-owned validation outputs entirely.
sourcefiles=[x for x in B.iterdir() if x.is_file() and x.suffix in ('.py','.json') and x.name not in ('parent-result-r6.json','parent-evidence-manifest-r6.json')]
source_inventory={str(x.relative_to(ROOT)):sha(x) for x in sourcefiles}
snapshot=H/'source-snapshot';snapshot.mkdir()
for name in ['long_d2.py','long_d2_executor.py','lifecycle.py','boundary_integrity.py','processes.py','fixture_guards.py']:(snapshot/name).write_bytes((B/name).read_bytes())
inputs=[ROOT/'docs/implementation-plan-v2.md',ROOT/'docs/SPEC_PRIVILEGED_VIT_RL.md',ROOT/'learning/runs/v2-orchestration/postovernight-long-D2-boundary-repair-r4-task.md']
for dirname,names in [('postovernight-long-D2-boundary-review-r3',['findings.json','audit.md']),('postovernight-long-D2-boundary-failure-diagnosis-sonnet-r1',['findings.json','diagnosis.md']),('postovernight-long-D2-boundary-prepare-r4',['implementation-result.json','candidate.diff','PARENT-NEXT.md'])]:
    inputs.extend(H.parent/dirname/name for name in names)
for name in ['postovernight-long-D2-boundary-review-r3-parent-reconciliation.json','postovernight-long-D2-failure-diagnosis-sonnet-r1-parent-reconciliation.json','postovernight-long-D2-boundary-policy-parent-reconciliation-r1.json','postovernight-long-D2-r2-protocol-r5.json']:inputs.append(ROOT/'learning/runs/v2-orchestration'/name)
save(H/'review-input-hashes.json',{'source':source_inventory,'capsule':capsule,'required_documents':{str(x.relative_to(ROOT)):sha(x) for x in inputs},'state_context_snapshot_sha256':sha(H/'state.context.snapshot.json'),'mutable_attempts_excluded':True})
save(H/'static-source-audit.json',dict(protected_comparisons=comparisons,legacy75=legacy,class_counts={k:len(v) for k,v in classes.items()},historical_bindings=len(old),historical_R3=9675,historical_R4=9870,duplicate_classes=duplicates,config_sha256=config_sha,D1_sha256=d1_sha,master_seed=5562873868232098305,capsule_files=len(capsule),capsule_hashes_and_membership_match=True,checkpoint_decoded=False,full_R_A_endpoint_executed=False))
print('Protected blocks/ML try equal;75 source hashes;10091/9870/9675 bindings;B235/R37/A9998;119 capsule members verified.')
