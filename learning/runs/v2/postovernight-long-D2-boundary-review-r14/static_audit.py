"""Fresh read-only bytes/AST/map checks; no candidate imports or validation calls."""
import ast,hashlib,json,stat,pathlib,datetime
ROOT=pathlib.Path.cwd(); O=ROOT/'learning/runs/v2/postovernight-long-D2-boundary-review-r14'; C=ROOT/'learning/runs/v2/postovernight-long-D2-boundary-prepare-r14'; V=ROOT/'learning/runs/v2'; P=ROOT/'learning/runs/v2-orchestration'
inputs={}; result={}
def sha(p):
 h=hashlib.sha256()
 with pathlib.Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def remember(p):
 p=pathlib.Path(p).absolute(); inputs[str(p)]=dict(sha256=sha(p),bytes=p.stat().st_size)
def load(p):remember(p);return json.loads(pathlib.Path(p).read_bytes())
def text(p):remember(p);return pathlib.Path(p).read_text()
def blocks(s):
 lines=s.splitlines(True)
 return {n.name:''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(s).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
def methods(s):
 lines=s.splitlines(True); tree=ast.parse(s); out={}
 for c in tree.body:
  if isinstance(c,ast.ClassDef):
   for n in c.body:
    if isinstance(n,ast.FunctionDef):out[c.name+'.'+n.name]=''.join(lines[n.lineno-1:n.end_lineno])
 return out
# Compare actual historical r11 bytes to the retained snapshot first.
old=text(V/'postovernight-long-D2-boundary-prepare-r11/long_d2.py'); assert old==text(C/'r11-source/long_d2.py')
new=text(C/'long_d2.py'); ob,nb=blocks(old),blocks(new)
assert set(nb)-set(ob)=={'boundary_switch_interval','restore_boundary_switch_interval'}
assert [n for n in ob if ob[n]!=nb[n]]==['Guard']
om,nm=methods(old),methods(new); assert set(om)==set(nm); assert [n for n in om if om[n]!=nm[n]]==['Guard.full_check']
# Construct the sole authorized method change from old bytes, without excluding its body.
a=om['Guard.full_check']; expected=a.replace('            try:\n                observation = self.verify()\n', '''            callback_error = None
            try:
                with boundary_switch_interval():
                    try:
                        observation = self.verify()
                    except BaseException as error:
                        # Latch at the actual callback catch, before interval
                        # cleanup can raise a later error that replaces it.
                        callback_error = error
                        self.failure_at = self.failure_at or self.clock()
                        self.failure = self.failure or (error if isinstance(error, Stop) else Stop(repr(error)))
                        raise
''')
expected=expected.replace('            except BaseException as error:\n                row.update', '''            except BaseException as error:
                if callback_error is not None and error is not callback_error:
                    # Later cleanup failure stays represented and fatal, but
                    # the original callback failure remains primary.
                    row.update(verdict='failed', error=repr(callback_error), cleanup_error=repr(error))
                    raise callback_error from error
                row.update''')
assert expected==nm['Guard.full_check']
# Project whole file only after exact full_check transformation was checked.
projected=new.replace(expected,a)
start=projected.index('\n\ndef restore_boundary_switch_interval(');end=projected.index('class Guard:',start)
oldstart=old.index('\n\nclass Guard:')
projected=projected[:start]+old[oldstart:old.index('class Guard:',oldstart)]+projected[end:]
projected=projected.replace('BOUNDARY_SWITCH_INTERVAL = 0.0001\n','').replace('prepare-r14','prepare-r11').replace('protocol-r10.json','protocol-r8.json').replace('ff160f8faec7c4d9b165e09db38fc3831e20e3f6609f1a82b63df42a307979ec','fe11c08159bdb9ca1f03cb0fb96ffd133ad144d107b2a854d19fc49159aa2db2')
assert projected==old
result['independent_whole_controller_projection']=True
protected=['long_d2_executor.py','lifecycle.py','processes.py','boundary_integrity.py','freeze.py','source_equality.py','synthetic.py','os_checks.py','stress.py','fixture_guards.py','fixture_preconditions.py','parent_command.py','rehearsal.py','model_r11.py']
for n in protected:
 current=text(C/n);assert current==text(C/'r11-source'/n)==text(C/'r12-source'/n)==text(V/'postovernight-long-D2-boundary-prepare-r11'/n),n
result['unchanged_protected_files']=protected
migrated=[]; identical=[]
for n in ['test_r11.py','test_r10.py','test_r7.py','test_repairs.py','test_boundary.py']:
 before=methods(text(C/'r11-source'/n));after=methods(text(C/n)); assert before.keys()==after.keys()
 for name in before:
  if '.test_' in name:(identical if before[name]==after[name] else migrated).append(n+':'+name)
assert len(identical)==108 and len(migrated)==4
assert set(migrated)=={'test_r11.py:R11.test_C01_exact_success_consumers_transport_inner_fixtures_and_old91','test_r11.py:R11.test_C02_protocol_only_candidate_paths_and_qualified_semantics','test_r10.py:R10.test_exact_r9_transport_success_consumers_protected_blocks','test_r7.py:R7.test_success_consumers_and_protected_failure_helpers_byte_equal'}
result.update(unchanged_inherited_methods=len(identical),migrated_methods=migrated)
for n in ['source-manifest.json','evidence-manifest.json']:
 m=load(C/n)
 for name,row in m['files'].items():
  p=C/name;assert sha(p)==row['sha256'] and p.stat().st_size==row['bytes'],str(p);remember(p)
 result[n+'_verified']=len(m['files'])
i=load(C/'long-identity.json'); cl=load(C/'classification.json'); ar=load(C/'archive-manifest.json'); na=load(C/'native-manifest.json'); reg=load(C/'registration.json')
B,R,A=cl['B'],na['files'],ar['files']; counts=dict(B=len(B),R=len(R),A=len(A))
assert counts==dict(B=253,R=37,A=9998)==cl['class_counts']==reg['class_counts']
assert not(set(B)&set(R) or set(B)&set(A) or set(R)&set(A))
for p,d in B.items():assert sha(p)==d,p;remember(p)
assert len(ar['original_bindings'])==ar['original_union_count']==10091
assert (ar['retained_R4_count'],ar['retained_R3_count'])==(9870,9675)
for p,row in ar['original_bindings'].items():assert {'B':B,'R':R,'A':A}[row['classification']][p]==row['sha256']
assert sha(C/'archive-manifest.json')==cl['A_manifest_sha256']==i['class_manifest_hashes']['A']==reg['class_manifest_hashes']['A']
assert sha(C/'native-manifest.json')==cl['R_manifest_sha256']==i['class_manifest_hashes']['R']==reg['class_manifest_hashes']['R']
assert sha(C/'classification.json')==i['classification_sha256']==reg['classification_sha256']
assert sha(C/'long-identity.json')==reg['identity_sha256']
legacy=i['base_registered_identity']['sources'];assert len(legacy)==75
for p,d in legacy.items():assert sha(ROOT/p)==d==B[str(ROOT/p)];remember(ROOT/p)
cap=C/'capsule-final';cm=load(cap/'capsule-manifest.json');actual=set()
for p in [cap,*cap.rglob('*')]:
 mode=p.lstat().st_mode;assert not stat.S_ISLNK(mode) and not mode&0o222 and (stat.S_ISDIR(mode) or stat.S_ISREG(mode)),str(p)
 if p.is_file():actual.add(str(p.relative_to(cap)))
assert actual==set(cm['files'])|{'capsule-manifest.json'} and len(cm['files'])==128
for p,d in cm['files'].items():assert sha(cap/p)==d;remember(cap/p)
for p,d in reg['pins'].items():assert sha(p)==d;remember(p)
assert sha(cap/'capsule-manifest.json')==reg['capsule_manifest_sha256']
for p,d in i['controller_sources'].items():assert cm['files'][p]==d==sha(ROOT/p)
protocol=load(P/'postovernight-long-D2-r2-protocol-r10.json');assert (C/'protocol-r10-proposal.json').read_bytes()==(P/'postovernight-long-D2-r2-protocol-r10.json').read_bytes()
assert sha(ROOT/protocol['config_path'])=='2ac814d3842228017d09669364a8391344722da56ad19f41ad9030dbb930c2db'
assert protocol['config']['phase_settings']['run_seed']==5562873868232098305
assert protocol['parent_checkpoint_sha256']==i['parent_checkpoint_sha256']=='ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f'
r8=load(C/'protocol-r8-proposal.json');r9=load(C/'protocol-r9-proposal.json');r10=dict(protocol)
chronology=r10.pop('first_callback_failure_chronology');r10.pop('registered_at_utc');r9c=dict(r9);r9c.pop('registered_at_utc')
assert json.loads(json.dumps(r10).replace('prepare-r14/','prepare-r12/'))==r9c
r9c=dict(r9);schedule=r9c.pop('boundary_scheduling');r9c['registered_at_utc']=r8['registered_at_utc'];assert json.loads(json.dumps(r9c).replace('prepare-r12/','prepare-r11/'))==r8
assert schedule['interval_seconds']==.0001
# Acyclic declared edges and actual roots, registration excluded from leaves.
dag=load(C/'hash-DAG.json');visiting=set();visited=set()
def visit(n):
 assert n not in visiting,n
 if n in visited:return
 visiting.add(n)
 for m in dag['edges'].get(n,[]):visit(m)
 visiting.remove(n);visited.add(n)
for n in dag['edges']:visit(n)
root_names={'classification.json','long-identity.json','capsule-manifest.json','registration.json'}
assert root_names==set(cl['root_envelope_exclusions'])
for name in root_names:assert str(C/name) not in B
# Supplied parent test records are inspected, never rerun.
PV=V/'postovernight-long-D2-r14-parent-validation-r1'; suite=load(PV/'unit-stage/suite-result.json');raw=load(PV/'unit-stage/raw-result.json')
assert suite['tests_run']==143 and len(suite['per_test_results'])==143 and all(r['status']=='passed' for r in suite['per_test_results'])
assert len(set(suite['planned_tests']))==143 and not suite['unrun_tests'] and not suite['forbidden_imports']
assert suite['existing_method_count']==112 and suite['new_method_count']==31 and not suite['historical_target_rebinding']
assert raw['raw_exit']==0 and raw['invocations']==1 and raw['retries']==0
result.update(class_counts_measured=counts,actual_B_hashes_verified=len(B),original_binding_map_count=10091,retained_R4=9870,retained_R3=9675,capsule_manifest_members=len(cm['files']),capsule_actual_files=len(actual),legacy_source_hashes_verified=75,registration_pins_verified=len(reg['pins']),hash_DAG_acyclic=True,parent_methods_passed_supplied=143,parent_suite_not_rerun=True)
# Snapshot mutable context; only snapshot is frozen in this review.
state=P/'state.json';(O/'state.context.snapshot.json').write_bytes(state.read_bytes());remember(O/'state.context.snapshot.json')
# Pin full context and review artifacts read as source, without executing any.
for d in [C,V/'postovernight-long-D2-boundary-review-r11',V/'postovernight-long-D2-contention-design-sonnet-r1',V/'postovernight-long-D2-escalation-reap-design-sonnet-r1',V/'postovernight-long-D2-switchinterval-probe-r1',V/'postovernight-long-D2-r12-chronology-proof-r1',PV]:
 for p in d.iterdir():
  if p.is_file() and p.suffix in {'.json','.py','.md','.diff','.log'}:remember(p);p.read_bytes()
for p in P.iterdir():
 if p.is_file() and ('postovernight-long-D2' in p.name) and p.suffix in {'.json','.md'} and p.name!='state.json':remember(p);p.read_bytes()
for p in [ROOT/'docs/implementation-plan-v2.md',ROOT/'docs/SPEC_PRIVILEGED_VIT_RL.md']:remember(p)
result['limitations']=['Static actual-B and capsule byte verification only; R/A actual endpoint hashing not executed.','No native/ML/project imports, suite/OS/stress/startup, signal delivery or training validation.','Mutable parent runtime outputs are not acceptance evidence.']
(O/'input-manifest.json').write_text(json.dumps({'files':inputs,'live_state_excluded':True},indent=2)+'\n')
(O/'static-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
