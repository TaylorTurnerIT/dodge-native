"""Independent retained-union and protected-source comparison; read-only."""
import ast,json,pathlib,hashlib
R=pathlib.Path.cwd();O=pathlib.Path(__file__).resolve().parent;V=R/'learning/runs/v2';C=V/'postovernight-long-D2-boundary-prepare-r14';inputs={}
def read(p):
 raw=p.read_bytes();inputs[str(p)]=dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw));return raw.decode()
def blocks(p):
 s=read(p);lines=s.splitlines(True);return {n.name:''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(s).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
def worker_body(p):
 s=read(p);lines=s.splitlines(True);w=next(n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef) and n.name=='worker');tr=next(n for n in w.body if isinstance(n,ast.With)).body[0]
 return ''.join(lines[tr.body[0].lineno-1:tr.body[-1].end_lineno])
base=V/'postovernight-long-D2-guard-prepare-r1'; expanded=json.loads(read(base/'expanded-inventory.json'))['full_pins']; prior=json.loads(read(base/'long-identity.json'));archive=json.loads(read(C/'archive-manifest.json'))
assert len(expanded)==10091 and {p:r['sha256'] for p,r in archive['original_bindings'].items()}==expanded
for key,count in [('retained_r4_union',9870),('retained_r3_union',9675)]:
 assert len(prior[key])==count and all(expanded[p]==d for p,d in prior[key].items())
protected=('Learner','Schedule','run_schedule','environment_kwargs','counter_report','compare_control','tree_fingerprint','assert_equal_tree','validate_long_config','expected_lease','assert_lease','check_module_origins','outcome_fields','result_code')
current=blocks(C/'long_d2.py');checks={}
for label in ['postovernight-long-D2-guard-prepare-r1','postovernight-long-D2-prepare-r4','postovernight-long-D2-boundary-prepare-r3']:
 p=V/label/'long_d2.py';old=blocks(p);row={k:current[k]==old[k] for k in protected};row['worker_ML_try']=worker_body(C/'long_d2.py')==worker_body(p);assert all(row.values());checks[label]=row
success=('validate_wait_reports','accept_observed','validate_artifacts','checked_registration','worker_command')
current=blocks(C/'long_d2_executor.py')
for version in ['r6','r9','r10','r11']:
 p=V/('postovernight-long-D2-boundary-prepare-'+version)/'long_d2_executor.py';old=blocks(p);row={k:current[k]==old[k] for k in success};assert all(row.values());checks[version+'_success_consumers']=row
# Read current import/worker integration and barriers as source only.
record=dict(status='passed',actual_original_union=10091,retained_R4=9870,retained_R3=9675,protected_source=checks)
(O/'retained-contract-results.json').write_text(json.dumps(record,indent=2)+'\n');(O/'retained-contract-inputs.json').write_text(json.dumps({'files':inputs},indent=2)+'\n');print(json.dumps(record,indent=2))
