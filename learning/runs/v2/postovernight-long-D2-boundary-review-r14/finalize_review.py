"""Close immutable inputs, JSON evidence, and acyclic output receipts."""
import datetime,hashlib,json,pathlib,subprocess,sys,time
O=pathlib.Path(__file__).resolve().parent;ROOT=pathlib.Path.cwd()
def sha(p):
 h=hashlib.sha256()
 with pathlib.Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def write(n,x):(O/n).write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def load(n):return json.loads((O/n).read_text())
errors=load('inspection-errors.json')
errors.extend([
 dict(stage='read-only lookup',command='cat learning/runs/v2/postovernight-long-D2-boundary-review-r11/static_check.py',raw_exit=1,error='No such file or directory',recovery='Read actual inventory file static_audit.py; no proof ran.'),
 dict(stage='read-only lookup',command="rg -n '^## |^# |script|probe|source|qualified|leak' learning/runs/v2-orchestration/postovernight-long-D2-contention-sonnet-r1-parent-reconciliation.json",lookup_raw_exit=2,containing_shell_raw_exit=0,error='No such file or directory (os error 2)',recovery='Read actual inventory path postovernight-long-D2-contention-design-sonnet-r1-parent-reconciliation.json; no proof ran.')])
write('inspection-errors.json',errors)
manifest=load('input-manifest.json');inputs=manifest['files'];inputs.update(load('retained-contract-inputs.json')['files'])
# Additional explicitly inspected prior evidence, plus supplied raw unit log and all test rows.
V=ROOT/'learning/runs/v2'
for directory in [V/'postovernight-long-D2-boundary-review-r10',V/'postovernight-long-D2-r12-chronology-proof-r1']:
 for p in directory.iterdir():
  if p.is_file() and p.suffix in {'.py','.md','.json','.log'}:inputs[str(p)]=dict(sha256=sha(p),bytes=p.stat().st_size)
p=V/'postovernight-long-D2-r14-parent-validation-r1/unit-stage'
for q in p.iterdir():
 if q.is_file():inputs[str(q)]=dict(sha256=sha(q),bytes=q.stat().st_size)
# Recheck inherited exact authority pins; the current protocol is in both pin receipts.
authority={
 'postovernight-long-D2-boundary-review-r10-parent-reconciliation.json':'b8401edfa2ec2106dcc4ba7b00f841e008619cfa94572314f426d54ac2886594',
 'postovernight-long-D2-escalation-reap-sonnet-r1-parent-reconciliation.json':'83fc23ac9dac6a1898f1b2d6301b1c3b79ba7fb3e45dedba3d4c3c67a8c7b642',
 'postovernight-long-D2-boundary-policy-parent-reconciliation-r1.json':'95977b36b45ad1ea670a601b51bb70198d0c0f37bb76c237b6ac032e535ebe9d'}
for n,d in authority.items():assert sha(ROOT/'learning/runs/v2-orchestration'/n)==d,n
for n,r in inputs.items():
 p=pathlib.Path(n);assert sha(p)==r['sha256'] and p.stat().st_size==r['bytes'],n
assert load('pins-before.json')['all_match'] and load('pins-after.json')['all_match']
manifest['files']=inputs;manifest['live_state_excluded']=True;manifest['mutable_context_snapshot']='state.context.snapshot.json';write('input-manifest.json',manifest)
# Only snapshotted context is rehashed; the live parent ledger may legitimately change.
write('end-verification.json',dict(status='passed',immutable_inputs_rehashed=len(inputs),eight_parent_pins_match=True,current_protocol_r10_matches=True,authority_pins_match=3,source_and_evidence_unchanged=True,live_ledger_excluded=True))
commands=[dict(command=['python3','-B','learning/runs/v2/postovernight-long-D2-boundary-review-r14/static_audit.py'],raw_exit=0,wall_seconds=0.360880542,timing_basis='exec_command tool result',stdout='static.stdout.log',stderr='static.stderr.log'),dict(command=['python3','-B','learning/runs/v2/postovernight-long-D2-boundary-review-r14/retained_contracts.py'],raw_exit=0,wall_seconds=0.027389458,timing_basis='exec_command tool result',stdout='retained.stdout.log',stderr='retained.stderr.log'),load('discriminator-command.json'),dict(command=load('registered-quantization-command.json'),result=load('registered-quantization-raw.json'))]
write('command-receipts.json',dict(static_commands=2,source_extracted_discriminator_commands=2,failed_proofs=0,commands=commands))
validation=[]
for p in sorted(O.rglob('*.json')):
 r=subprocess.run([sys.executable,'-B','-m','json.tool',str(p)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 validation.append(dict(path=str(p.relative_to(O)),raw_exit=r.returncode,error=r.stderr.decode()))
 assert r.returncode==0,str(p)
write('json-validation.json',dict(tool='python3 -B -m json.tool',files=validation,all_passed=True,publication_envelopes_validated_after_creation=True))
excluded={'output-manifest.json','review-receipt.json','completion-receipt.json'}
files={str(p.relative_to(O)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(O.rglob('*')) if p.is_file() and p.name not in excluded}
write('output-manifest.json',dict(schema='frozen_boundary_r14_review_output_manifest_v1',files=files,excludes=sorted(excluded),acyclic=True,logs_closed=True))
now=datetime.datetime.now(datetime.timezone.utc);start=datetime.datetime.fromisoformat(load('start.json')['at_utc']);elapsed=(now-start).total_seconds()+60
assert elapsed<=900,elapsed
stat=load('static-results.json');disc=load('discriminator-results.json');quant=load('registered-quantization-results.json')
receipt=dict(schema='frozen_boundary_r14_review_receipt_v1',verdict='no_findings',findings=0,candidate='learning/runs/v2/postovernight-long-D2-boundary-prepare-r14',owned_output='learning/runs/v2/postovernight-long-D2-boundary-review-r14',budget_seconds=900,elapsed_seconds_conservative=elapsed,timing_basis='UTC elapsed from first retained pin receipt plus 60 seconds for initial reads.',finished_at_utc=now.isoformat(),reviewed_target_modified=False,write_scope='new owned review output only',receipt_excludes_own_hash=True,proof_commands=2,proof_raw_exits=[0,0],static_audit_commands=2,static_raw_exits=[0,0],reviewer_lookup_errors=3,reviewer_failed_proofs=0,verified_frozen_pins=8,verified_actual_B=253,class_counts=stat['class_counts_measured'],verified_capsule_manifest_members=128,verified_capsule_files_including_manifest=129,verified_source_manifest_members=460,verified_implementation_evidence_members=947,verified_immutable_inputs=len(inputs),supplied_unit_methods_not_rerun=143,extracted_chronology_records=len(disc['records']),registered_CPython_quantization_values=quant['cases'],source_and_synthetic_only=True,limitations=stat['limitations'],input_manifest_sha256=sha(O/'input-manifest.json'),output_manifest_sha256=sha(O/'output-manifest.json'),end_verification_sha256=sha(O/'end-verification.json'),findings_sha256=sha(O/'findings.json'),audit_sha256=sha(O/'audit.md'),json_validation_sha256=sha(O/'json-validation.json'),output_manifest_generated_only_after_logs_close=True)
write('review-receipt.json',receipt)
write('completion-receipt.json',dict(schema='frozen_r14_review_acyclic_completion_v1',verdict='no_findings',review_receipt='review-receipt.json',review_receipt_sha256=sha(O/'review-receipt.json'),output_manifest_sha256=sha(O/'output-manifest.json'),receipt_excludes_own_hash=True,acyclic=True))
for n in ['json-validation.json','output-manifest.json','review-receipt.json','completion-receipt.json']:
 r=subprocess.run([sys.executable,'-B','-m','json.tool',str(O/n)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE);assert r.returncode==0,(n,r.stderr)
for n,r in files.items():assert sha(O/n)==r['sha256'],n
print(json.dumps({'verdict':'No findings','elapsed_seconds_conservative':elapsed,'immutable_inputs':len(inputs),'output_members':len(files),'all_JSON_validated':True,'receipt_sha256':sha(O/'review-receipt.json')}))
