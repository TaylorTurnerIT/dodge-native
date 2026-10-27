from pathlib import Path
import ast,hashlib,json,datetime,stat,sys
O=Path(__file__).resolve().parent; R=Path.cwd(); H=R/'learning/runs/v2/postovernight-long-D2-guard-prepare-r1'; C=H/'capsule-final'
inputs={}
def sha(p):
 p=Path(p);d=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):d.update(b)
 return d.hexdigest()
def read(p):
 p=Path(p);inputs[str(p.relative_to(R))]=sha(p);return json.loads(p.read_text())
def put(n,v): (O/n).write_text(json.dumps(v,sort_keys=True,indent=2)+'\n')
(O/'inputs').mkdir(exist_ok=False)
for n in ['docs/implementation-plan-v2.md','docs/SPEC_PRIVILEGED_VIT_RL.md','learning/runs/v2-orchestration/state.json','learning/runs/v2-orchestration/postovernight-long-D2-r2-plan.json']:
 p=R/n; raw=p.read_bytes();dest=O/'inputs'/p.name;dest.write_bytes(raw);inputs[n]=hashlib.sha256(raw).hexdigest()
inv=read(H/'artifact-inventory-final.json');errors=[]
for n,v in inv['files'].items():
 p=H/n
 if not p.is_file() or sha(p)!=v['sha256'] or p.stat().st_size!=v['bytes']:errors.append(n)
actual={str(p.relative_to(H)) for p in H.rglob('*') if p.is_file()}
assert actual==set(inv['files'])|{'artifact-inventory-final.json'}
identity=read(H/'long-identity.json');m=read(C/'capsule-manifest.json'); protocol=read(R/'learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r1.json')
pins={str(C/n):v for n,v in m['files'].items()};pins.update(identity['original_input_pins']);pins.update({str(R/n):v for n,v in identity['controller_sources'].items()});pins[str(C/'capsule-manifest.json')]=sha(C/'capsule-manifest.json');pins[str(H/'long-identity.json')]=sha(C/'learning/runs/v2/postovernight-long-D2-guard-prepare-r1/long-identity.json')
pin_errors=[p for p,v in pins.items() if not Path(p).is_file() or sha(p)!=v]
reg=read(H/'registration.json');regerrors=[p for p,v in reg['pins'].items() if sha(p)!=v]
assert all(not x.is_symlink() and not x.stat().st_mode&0o222 for x in C.rglob('*')) and not C.stat().st_mode&0o222
assert {str(p.relative_to(C)) for p in C.rglob('*') if p.is_file()}==set(m['files'])|{'capsule-manifest.json'}
legacy=protocol['base_identity']['sources'];legacy_errors=[n for n,v in legacy.items() if sha(R/n)!=v or sha(C/n)!=v]
old=read(R/'learning/runs/v2/postovernight-long-D2-prepare-r4/long-identity.json')
# Older full-pin union is reconstructed from its capsule, original pins, sources and manifest.
oldH=R/'learning/runs/v2/postovernight-long-D2-prepare-r4';oldC=oldH/'capsule-final';oldM=read(oldC/'capsule-manifest.json')
oldpins={str(oldC/n):v for n,v in oldM['files'].items()};oldpins.update(old['original_input_pins']);oldpins.update({str(R/n):v for n,v in old['controller_sources'].items()});oldpins[str(oldC/'capsule-manifest.json')]=sha(oldC/'capsule-manifest.json');oldpins[str(oldH/'long-identity.json')]=sha(oldC/'learning/runs/v2/postovernight-long-D2-prepare-r4/long-identity.json')
assert all(pins.get(n)==v for n,v in oldpins.items())
def blocks(p):
 s=p.read_text();return {n.name:ast.get_source_segment(s,n) for n in ast.parse(s).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
a,b=blocks(oldH/'long_d2.py'),blocks(H/'long_d2.py')
expected=read(H/'source-equality.json');equal={n:a[n]==b[n] for n in expected['protected_source_equal']}
def worker_try(p):
 s=p.read_text();w=next(n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef) and n.name=='worker');t=next(n for n in w.body if isinstance(n,ast.With)).body[0];return '\n'.join(s.splitlines()[t.body[0].lineno-1:t.body[-1].end_lineno])
ml_equal=worker_try(oldH/'long_d2.py')==worker_try(H/'long_d2.py')
units=read(H/'attempts/units-05/unit-result.json');unitcmd=read(H/'attempts/units-05/command-result.json');matrix=read(H/'attempts/matrix-01-cases/summary.json');matrixcmd=read(H/'attempts/matrix-01/command-result.json')
sources={n:sha(H/'attempts/units-05/sources'/n)==v for n,v in units['sources'].items()}
assert all(sources.values())
assert sha(H/'attempts/units-05/sources/long_d2.py')==sha(H/'long_d2.py') and sha(H/'attempts/units-05/sources/long_d2_executor.py')==sha(H/'long_d2_executor.py')
latches=[]
for p in sorted((H/'attempts/units-05').glob('latch-*-command.json')):latches.append({'path':str(p.relative_to(H)),'receipt':read(p)})
results=matrix['results'];reprows=[]
for v in results:
 reprows.append({k:v.get(k) for k in ['expected','elapsed_seconds','harness_kill_required','injection_reached','observed_acceptance','receipt_available','positive_group_absence','raw_wait']})
put('matrix-evidence.json',{'reported_OS_executions':matrix['OS_subprocesses'],'rows':len(results),'results':reprows,'historical_R4_controls_transferred':0,'rerun':False})
ver={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'inventory_entries':len(inv['files']),'inventory_errors':errors,'full_pins':len(pins),'pin_errors':pin_errors,'retained_R4_full_pins':len(oldpins),'retained_older_original_union':len(old['original_input_pins']),'capsule_files':len(m['files']),'capsule_readonly':True,'registration_pin_errors':regerrors,'legacy_original_and_mirror_count':len(legacy),'legacy_errors':legacy_errors,'protected_source_equality':equal,'worker_ML_try_equal':ml_equal,'unit_source_snapshots_valid':sources,'unit_methods':units['methods_run'],'unit_raw_exit':unitcmd['raw_exit'],'matrix_raw_exit':matrixcmd['raw_exit'],'latch_subprocesses_nested_in_unit_method':len(latches),'latch_commands':latches,'test_counts_not_added':True,'sha256':{n:sha(H/n) for n in ['long_d2.py','long_d2_executor.py','long-identity.json','capsule-final/capsule-manifest.json','implementation-result-final.json']}}
put('verification.json',ver);put('input-hashes.json',inputs)
assert not(errors or pin_errors or regerrors or legacy_errors) and all(equal.values()) and ml_equal
print(json.dumps({k:v for k,v in ver.items() if k not in ['latch_commands','unit_source_snapshots_valid']},indent=2))
