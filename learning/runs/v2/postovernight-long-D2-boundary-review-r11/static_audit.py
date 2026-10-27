"""Read-only bytes/AST/manifest audit. Does not invoke candidate validation."""
from pathlib import Path
import ast,hashlib,json,os,stat,time
H=Path(__file__).resolve().parent;ROOT=Path.cwd();BASE=ROOT/'learning/runs/v2'
C=BASE/'postovernight-long-D2-boundary-prepare-r11'
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for raw in iter(lambda:f.read(1024*1024),b''):h.update(raw)
    return h.hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def blocks(p):
    s=Path(p).read_text();lines=s.splitlines(True)
    return {n.name:''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(s).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
def body(p):
    s=Path(p).read_text();lines=s.splitlines(True)
    worker=next(n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef) and n.name=='worker')
    node=next(n for n in worker.body if isinstance(n,ast.With)).body[0]
    return ''.join(lines[node.body[0].lineno-1:node.body[-1].end_lineno])
result={};inputs={}
def remember(p):
    p=Path(p);inputs[str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)]=dict(sha256=sha(p),bytes=p.stat().st_size)
# Preserve helper source bytes separately; no copying validation outputs.
for name in ('processes.py','fixture_guards.py','synthetic.py','os_checks.py','freeze.py','source_equality.py','test_r7.py','test_repairs.py','test_boundary.py'):
    p=C/name;remember(p);(H/'snapshot'/name).write_bytes(p.read_bytes())
old=blocks(BASE/'postovernight-long-D2-boundary-prepare-r10/long_d2_executor.py');new=blocks(C/'long_d2_executor.py')
consumer_names=('validate_wait_reports','accept_observed','validate_artifacts','checked_registration','worker_command')
result['success_consumers_byte_equal_r10']={k:old[k]==new[k] for k in consumer_names};assert all(result['success_consumers_byte_equal_r10'].values())
result['unchanged_r10_helpers']={name:(C/name).read_bytes()==(C/'r10-source'/name).read_bytes() for name in ('lifecycle.py','boundary_integrity.py','processes.py','freeze.py','synthetic.py','fixture_guards.py','fixture_preconditions.py','os_checks.py')}
assert all(result['unchanged_r10_helpers'].values())
current=blocks(C/'long_d2.py');r10=blocks(C/'r10-source/long_d2.py')
result['controller_blocks_equal_r10']={k:v==current[k] for k,v in r10.items()}
assert all(result['controller_blocks_equal_r10'].values())
a=blocks(C/'long_d2_executor.py')['Execution'];b=blocks(C/'r10-source/long_d2_executor.py')['Execution']
def methods(source):
 lines=source.splitlines(True);node=ast.parse(source).body[0]
 return {x.name:''.join(lines[x.lineno-1:x.end_lineno]) for x in node.body if isinstance(x,ast.FunctionDef)}
ma,mb=methods(a),methods(b)
result['changed_executor_methods']=sorted(k for k in mb if mb[k]!=ma[k]);result['new_executor_methods']=sorted(set(ma)-set(mb))
assert result['changed_executor_methods']==['monitor','monitor_duty','pump'] and result['new_executor_methods']==['kill_due']
result['Execution_run_byte_equal_r10']=ma['run']==mb['run'];assert result['Execution_run_byte_equal_r10']
for manifest_name in ('source-manifest.json','evidence-manifest.json'):
 manifest=read(C/manifest_name)
 for name,row in manifest['files'].items():assert sha(C/name)==row['sha256'] and (C/name).stat().st_size==row['bytes'],name
 result[manifest_name+'_actual_files']=len(manifest['files'])
protected=('Learner','Schedule','run_schedule','environment_kwargs','counter_report','compare_control','tree_fingerprint','assert_equal_tree','validate_long_config','expected_lease','assert_lease','check_module_origins','outcome_fields','result_code')
for label in ('postovernight-long-D2-guard-prepare-r1','postovernight-long-D2-prepare-r4','postovernight-long-D2-boundary-prepare-r3'):
    path=BASE/label/'long_d2.py';remember(path);older=blocks(path)
    entry=dict(protected={k:current[k]==older[k] for k in protected},worker_ML_try_byte_equal=body(C/'long_d2.py')==body(path))
    assert all(entry['protected'].values()) and entry['worker_ML_try_byte_equal'];result[label]=entry
identity=read(C/'long-identity.json');classification=read(C/'classification.json');archive=read(C/'archive-manifest.json');native=read(C/'native-manifest.json');registration=read(C/'registration.json')
for name in ('archive-manifest.json','native-manifest.json','hash-DAG.json','required-lease.json','invocation.json','parent-validation-plan.json'):
    remember(C/name)
B,R,A=classification['B'],native['files'],archive['files']
for name,digest in B.items():assert sha(name)==digest;remember(name)
result['all_actual_B_files']=len(B)
assert not (set(B)&set(R) or set(B)&set(A) or set(R)&set(A))
assert classification['class_counts']==registration['class_counts']==dict(B=len(B),R=len(R),A=len(A))==dict(B=267,R=37,A=9998)
assert archive['original_union_count']==len(archive['original_bindings'])==10091
assert archive['retained_R3_count']==9675 and archive['retained_R4_count']==9870
maps=dict(B=B,R=R,A=A)
for name,row in archive['original_bindings'].items():assert maps[row['classification']][name]==row['sha256']
assert sha(C/'archive-manifest.json')==classification['A_manifest_sha256']==identity['class_manifest_hashes']['A']
assert sha(C/'native-manifest.json')==classification['R_manifest_sha256']==identity['class_manifest_hashes']['R']
assert sha(C/'classification.json')==identity['classification_sha256']==registration['classification_sha256']
assert sha(C/'long-identity.json')==registration['identity_sha256']
legacy=identity['base_registered_identity']['sources'];assert len(legacy)==75
for name,digest in legacy.items():
 p=ROOT/name;assert sha(p)==digest and B[str(p)]==digest;remember(p)
protocol=read(ROOT/'learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r8.json')
assert sha(ROOT/protocol['config_path'])=='2ac814d3842228017d09669364a8391344722da56ad19f41ad9030dbb930c2db'
assert protocol['config']['phase_settings']['run_seed']==5562873868232098305
assert identity['parent_checkpoint_sha256']==protocol['parent_checkpoint_sha256']=='ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f'
remember(ROOT/protocol['config_path'])
cap=C/'capsule-final';manifest=read(cap/'capsule-manifest.json');expected=set(manifest['files'])|{'capsule-manifest.json'};actual=set()
for p in cap.rglob('*'):
 mode=p.lstat().st_mode;assert not stat.S_ISLNK(mode) and not mode&0o222
 assert stat.S_ISDIR(mode) or stat.S_ISREG(mode)
 if p.is_file():actual.add(str(p.relative_to(cap)))
assert actual==expected
for name,digest in manifest['files'].items():assert sha(cap/name)==digest
for name,digest in registration['pins'].items():assert sha(name)==digest
result.update(class_counts=classification['class_counts'],original_binding_count=len(archive['original_bindings']),retained_R3=9675,retained_R4=9870,legacy75_actual_source_bytes_verified=True,capsule_files=len(actual),capsule_manifest_members=len(manifest['files']),capsule_exact_membership=True,capsule_bytes_permissions_and_types=True,registration_pins_actual=True,config_seed_D1_exact=True,
 limitations=['No full installed R/archive A endpoint rerun; original binding mappings and root digests checked statically.','No OS lifecycle/stress/startup, ML/native imports, decoding/inference/training, or qualification evidence.'])
# Read and pin complete requested source context and historical proof artifacts.
required=[ROOT/'docs/implementation-plan-v2.md',ROOT/'docs/SPEC_PRIVILEGED_VIT_RL.md']
for version in ('r3','r6','r9','r10'):
 directory=BASE/('postovernight-long-D2-boundary-review-'+version)
 required += [p for p in directory.iterdir() if p.suffix in ('.py','.json','.md','.log') and p.is_file()]
for dirname in ('postovernight-long-D2-escalation-reap-design-sonnet-r1','postovernight-long-D2-boundary-IPC-diagnosis-sonnet-r1','postovernight-long-D2-IPC-close-order-probe-sonnet-r2','postovernight-long-D2-boundary-startup-reap-diagnosis-sonnet-r1'):
 directory=BASE/dirname
 required += [p for p in directory.iterdir() if p.suffix in ('.py','.json','.md','.diff','.log') and p.is_file()]
for n in ('r4','r7','r10','r11'):
 required += [BASE/('postovernight-long-D2-boundary-prepare-'+n)/f for f in ('candidate.diff','implementation-result.json','PARENT-NEXT.md')]
for p in (ROOT/'learning/runs/v2-orchestration').glob('postovernight-long-D2-*.md'):required.append(p)
for name in ('postovernight-long-D2-boundary-review-r9-parent-reconciliation.json','postovernight-long-D2-IPC-sonnet-r1-parent-reconciliation.json','postovernight-long-D2-IPC-close-order-sonnet-r2-parent-reconciliation.json','postovernight-long-D2-boundary-policy-parent-reconciliation-r1.json','postovernight-long-D2-r10-parent-reconciliation.json','postovernight-long-D2-r11-parent-reconciliation.json','postovernight-long-D2-boundary-review-r10-parent-reconciliation.json','postovernight-long-D2-escalation-reap-sonnet-r1-parent-reconciliation.json','postovernight-long-D2-boundary-review-r6-parent-reconciliation.json','postovernight-long-D2-startup-reap-sonnet-r1-parent-reconciliation.json'):
 required.append(ROOT/'learning/runs/v2-orchestration'/name)
for p in C.glob('*.py'):required.append(p)
for name in ('candidate.diff','implementation-result.json','completion-receipt.json','PARENT-NEXT.md','source-manifest.json','evidence-manifest.json','parent-frozen-pins.json','long-identity.json','classification.json','registration.json'):
 required.append(C/name)
for p in required:
 remember(p)
 if p.suffix=='.json':read(p)
 else:p.read_text()
for p in (H/'snapshot').rglob('*'):
 if p.is_file():remember(p)
expected_authorities={'postovernight-long-D2-boundary-review-r10-parent-reconciliation.json':'b8401edfa2ec2106dcc4ba7b00f841e008619cfa94572314f426d54ac2886594','postovernight-long-D2-escalation-reap-sonnet-r1-parent-reconciliation.json':'83fc23ac9dac6a1898f1b2d6301b1c3b79ba7fb3e45dedba3d4c3c67a8c7b642','postovernight-long-D2-boundary-policy-parent-reconciliation-r1.json':'95977b36b45ad1ea670a601b51bb70198d0c0f37bb76c237b6ac032e535ebe9d','postovernight-long-D2-r2-protocol-r8.json':'fe11c08159bdb9ca1f03cb0fb96ffd133ad144d107b2a854d19fc49159aa2db2'}
for name,digest in expected_authorities.items():
 p=ROOT/'learning/runs/v2-orchestration'/name;assert sha(p)==digest;remember(p)
result['authority_pins_verified']=len(expected_authorities)
inputs['learning/runs/v2-orchestration/state.json']=dict(sha256=sha(H/'state.context.snapshot.json'),bytes=(H/'state.context.snapshot.json').stat().st_size,mutable_context=True,snapshot=str(H/'state.context.snapshot.json'))
(H/'input-manifest.json').write_text(json.dumps(dict(files=inputs,mutable_context_excluded_from_immutable_recheck=True),indent=2)+'\n')
(H/'static-audit-results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
