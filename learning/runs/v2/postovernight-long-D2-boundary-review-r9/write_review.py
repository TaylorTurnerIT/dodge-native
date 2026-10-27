"""Retain the read-only review, recheck immutable inputs, and inventory output."""
from pathlib import Path
import datetime,hashlib,json,os,stat,subprocess,sys,time
H=Path(__file__).resolve().parent;ROOT=Path.cwd();C=ROOT/'learning/runs/v2/postovernight-long-D2-boundary-prepare-r9'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for raw in iter(lambda:f.read(1024*1024),b''):h.update(raw)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def save(p,v):Path(p).write_text(json.dumps(v,indent=2,sort_keys=True,allow_nan=False)+'\n')
proofs=[]
for stem,script,result in [('worker-raw-proof-r4','proof_worker_raw_time_r4.py','worker-raw-proof-results.json'),('worker-raw-signal-proof-r2','proof_worker_raw_signal_r2.py','worker-raw-signal-proof-results.json'),('outer-worker-packet','proof_outer_worker_packet.py','outer-worker-packet-results.json')]:
 command=read(H/(stem+'-command.json'));assert command['raw_exit']==0
 proofs.append(dict(script=script,result=result,command=stem+'-command.json',stdout=stem+'.stdout.log',stderr=stem+'.stderr.log',raw_exit=command['raw_exit']))
finding=dict(id='BOUNDARY-R9-WORKER-RAW-OBSERVATION-TIME',severity='P2',title='Retain the abnormal worker wait observation before later IPC and file IO',
 path='learning/runs/v2/postovernight-long-D2-boundary-prepare-r9/long_d2.py',line=1292,end_line=1306,
 trigger='Worker exits with raw returncode outside (0,2), without an earlier worker failure packet, guard, latch, or peer descriptor. Its live supervisor obtains a direct wait report before later worker_wait IPC, group probing, or result-file reading.',
 mechanism='supervise_owned takes child.report, sends worker_wait, checks absence and reads long-worker-result.json before checking the abnormal raw outcome. No source-stamped error is made from report.observed_monotonic. A missing result (normal for abrupt death) or another intervening error enters observed_failure with no descriptor, so it selects the later catch time. Execution.pump validates and retains the worker_wait but does not fail the pool for its abnormal returncode, so the outer does not recover the earlier source time.',
 consequence='The first-global descriptor and shared cleanup deadline can start later than the retained successful waitpid observation, violating protocol terminal_lifecycle.failure_observation_time and earliest_failure+10. Exact extracted supervisor/notify/pool proofs retain a worker report at 99.75 but produce first_failure=100.0/until=110.0, instead of 99.75/109.75. Both rc=1 and raw status 9/rc=-9 discriminate. No accepted receipt, actual OS overrun, survivor, performance, or training failure is claimed.',
 fix_direction='Preserve the validated abnormal worker direct-wait source timestamp through the inner failure path before later IPC/probe/file operations; keep earlier guard/latch/peer sources, existing cap, ACK/write rules, mandatory-first ordering and single worker_wait send semantics.',
 proofs=proofs,proof_limits='Small exact AST extractions with fake child, clock, channel and absence inputs. The signaled-worker case uses the real extracted read_json on an actually missing owned fixture file. No real signal, waitpid, process-group or ML execution.')
save(H/'findings.json',dict(schema='frozen_boundary_r9_source_review_v1',verdict='changes_required',findings=[finding]))
commands={p.name:read(p) for p in H.glob('*-command.json')}
failures=[dict(command=name,raw_exit=v['raw_exit']) for name,v in commands.items() if v['raw_exit']!=0]
save(H/'command-receipts.json',dict(commands=commands,failed_attempts=failures,
 initial_pin_snapshot_command='python3 - [pin snapshot verifier]; raw_exit=0; exact result in pin-verification.json',
 discovery_failures=[dict(command='wc -l ... state.json; ls ... postovernight-long-D2-boundary-repair-r7',raw_exit=1,reason='Initial discovery used nonexistent root state.json and repair-r7 directory; actual state is learning/runs/v2-orchestration/state.json and implementation directory is boundary-prepare-r7.'),dict(command='python3 - [classification schema inspection]',raw_exit=1,reason="Reviewer schema inspection accessed classification['R']; actual native and archive manifests hold R/A.")],
 runtime_commands_executed=False,proof_processes_are_stdlib_interpreters_only=True))
# Original pins and their retained snapshots must still match.
pins=read(H/'pin-verification.json')['files'];pin_checks=[]
for row in pins:
 actual=sha(ROOT/row['path']);snapshot=sha(ROOT/row['snapshot']);pin_checks.append(dict(path=row['path'],expected=row['sha256'],actual=actual,snapshot=snapshot))
 assert actual==snapshot==row['sha256']
inputs=read(H/'input-manifest.json')['files'];drift={}
for name,row in inputs.items():
 if row.get('mutable_context'):continue
 actual=sha(ROOT/name)
 if actual!=row['sha256']:drift[name]=dict(expected=row['sha256'],actual=actual)
assert not drift
cap=C/'capsule-final';manifest=read(cap/'capsule-manifest.json');actual={str(p.relative_to(cap)) for p in cap.rglob('*') if p.is_file()}
assert actual==set(manifest['files'])|{'capsule-manifest.json'}
for name,digest in manifest['files'].items():assert sha(cap/name)==digest
save(H/'end-verification.json',dict(pin_checks=pin_checks,all_matched=True,immutable_input_drift=drift,capsule_manifest_members=len(manifest['files']),capsule_files_including_manifest=len(actual),all_capsule_member_hashes_match=True,mutable_parent_state_and_attempts_excluded=True,at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
audit='''# Frozen boundary r9 source audit

One P2 finding is retained in findings.json: BOUNDARY-R9-WORKER-RAW-OBSERVATION-TIME. This is the worker-to-supervisor analogue of the repaired inner-to-executor source-time defect, not a reopening of the already repaired executor call sites. It applies only when no earlier failure descriptor exists. The precise trigger, source lines, consequence, correction boundary and successful discriminators appear in the finding.

All eight supplied target pins and four external authority/protocol pins matched before source review and again at closeout. Source snapshots remain under snapshot/. The full implementation plan, specification, original r6 broad brief and inherited r4 contract, r6 findings/audit/proof scripts/results and parent reconciliation, independent Sonnet diagnosis/plan and parent-qualified reconciliation, accepted policy, and r7 implementation brief/result/diff/handoff informed the review. state.context.snapshot.json preserves the complete mutable state read for context; its changing status is not frozen-source or runtime evidence. No parent-owned partial validation attempt was read as final proof.

The exact current monitor discriminator preserves the abnormal inner report at 99.75/deadline 109.75, chooses the actual alarm at 99.5 before cancellation at 99.75, chooses cancellation in reverse order, and preserves an earlier peer at 99.25/deadline 109.25. The actual main branch calls the same validated raw_inner_failure before its terminal drain. This reconciles the original r6 RAW-OBSERVATION-TIME and ALARM-CANCEL-SOURCE sites. It does not clear the separate worker source-time finding.

The startup direct-reap repair is present in the actual supervise_owned failure path: mandatory immutable inner receipt first; nonblocking closes; guarded own-child fallback; successful failure ACK required for extended wait; same pool minus 1.0 internal reserve; existing worker_wait schema with attempt marked before send; no retry or inner group signal. Missing ACK skips the wait. The first receipt stays honest about pending reap. Later optional diagnostic publication does not rewrite it. The outer attempts four bounded pumps inside until-.25 and derives reaping statuses only after validate_report. Group absence remains an independent cleanup fact. These are source observations, not fresh OS closure proof.

Success validate_wait_reports, accept_observed, validate_artifacts, checked_registration and worker_command are byte equal to r6. Their raw 0/2, exact PID/parent/group, direct wait, finite time/order/deadline, registration/summary/actual byte and parent raw/wall predicates remain present. All r9 controller function/class blocks equal r7; executor, lifecycle, integrity and process helper bytes equal r7. Protected Learner/Schedule/run_schedule, worker ML try body, environment/config/origin helpers match the named historical approved sources. Source ordering still restores model/Adam/RNG before environment creation and requires the 64-row nine-field entry control before updates. No checkpoint decoding or model execution occurred.

Static bytes and envelopes establish B245/R37/A9998; all 10091 original path/hash/class bindings remain mapped, with retained_R3_count=9675 and retained_R4_count=9870. All 75 original source bytes match actual files and B classification. Config SHA256, seed 5562873868232098305, and D1 identity match. All 124 manifest members plus the capsule manifest itself match actual bytes and exact file membership, regular-file/directory types and readonly permissions. Registration pins match actual bytes. The unchanged fresh scandir implementation retains canonical root/ancestor types, no symlinks, strict names, exact membership and permissions; no cache or skipped forced boundary is introduced. B/legacy/check_frozen/origin/runtime/cache calls and full R/A pre/post endpoint calls remain in source. This review did not rerun those installed-runtime/archive endpoints or measure scandir performance.

All proof commands, environment values/digests, raw exits and logs are retained. Reviewer fixture failures remain failures: first worker-time attempt omitted life.OWNED; r2 additionally reused an existing owned fixture path; r3 exposed the omitted OWNED dependency; distinct r4 supplied it and passed. The first signaled-worker real-read_json fixture omitted json from its extraction namespace; distinct r2 supplied it and passed. The first static audit swapped the historical R3/R4 count labels; distinct r2 used the actual 9675/9870 labels and passed. No candidate bytes were changed for any proof correction. Failed attempts are never claimed as candidate failures, acceptance bypasses or successful evidence.

No full candidate unit suite, lifecycle/OS matrix, stress, startup rehearsal, ML/native/project import, checkpoint decode, inference, environment, training, lease, scheduler, commit, PR, deployment, message, provider call or nested delegation occurred. Parent owns validation reconciliation and any launch. This audit establishes no OS closure, performance, training acceptance or teacher qualification.
'''
(H/'audit.md').write_text(audit)
start=datetime.datetime.fromisoformat(read(H/'pin-verification.json')['time_utc'].replace('Z','+00:00'))
now=datetime.datetime.now(datetime.timezone.utc)
receipt=dict(schema='frozen_boundary_r9_review_receipt_v1',verdict='changes_required',findings=1,severity_counts=dict(P2=1),
 candidate=str(C.relative_to(ROOT)),owned_output=str(H.relative_to(ROOT)),source_modified=False,
 source_write_scope='new owned review directory only',no_universal_OS_write_attestation=True,
 first_retained_pin_snapshot_utc=start.isoformat(),finished_at_utc=now.isoformat(),elapsed_since_pin_snapshot_seconds=(now-start).total_seconds(),budget_seconds=900,
 input_manifest_sha256=sha(H/'input-manifest.json'),findings_sha256=sha(H/'findings.json'),audit_sha256=sha(H/'audit.md'),
 command_receipts_sha256=sha(H/'command-receipts.json'),end_verification_sha256=sha(H/'end-verification.json'),
 proof_attempts=len(commands),failed_reviewer_attempts=len(failures),receipt_excludes_own_hash=True,
 output_manifest_generated_after_receipt=True,limitations=['Source/synthetic evidence only; no runtime/OS/performance/training acceptance.','No full R/A endpoint rerun.','Mutable state and parent attempts are not final proof.'])
assert receipt['elapsed_since_pin_snapshot_seconds']<900
save(H/'review-receipt.json',receipt)
# Validate every retained JSON with the requested stdlib JSON CLI, and keep raw exits.
validation=[]
for p in sorted(H.rglob('*.json')):
 if p.name in ('json-validation.json','output-manifest.json'):continue
 json.loads(p.read_bytes())
 argv=[sys.executable,'-m','json.tool',str(p)]
 v=subprocess.run(argv,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
 validation.append(dict(path=str(p.relative_to(H)),argv=argv,raw_exit=v.returncode,stderr=v.stderr.decode()))
assert all(v['raw_exit']==0 for v in validation)
save(H/'json-validation.json',dict(method='stdlib json.loads and python3 -m json.tool',results=validation,all_passed=True,excludes_itself=True,output_manifest_validated_after_generation=True))
files={str(p.relative_to(H)):sha(p) for p in sorted(H.rglob('*')) if p.is_file() and p!=H/'output-manifest.json'}
save(H/'output-manifest.json',dict(schema='frozen_boundary_r9_review_output_manifest_v1',files=files,excludes_itself=True,receipt_included=True))
json.loads((H/'output-manifest.json').read_bytes())
v=subprocess.run([sys.executable,'-m','json.tool',str(H/'output-manifest.json')],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
assert v.returncode==0,v.stderr
print(json.dumps(dict(verdict='changes_required',findings=1,output_files=len(files),json_files_validated=len(validation),output_manifest_json_raw_exit=v.returncode,elapsed_seconds=receipt['elapsed_since_pin_snapshot_seconds'],immutable_inputs_unchanged=True),indent=2))
