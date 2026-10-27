"""Evidence closeout only; never changes reviewed inputs."""
from pathlib import Path
import datetime,hashlib,json,sys,subprocess
H=Path(__file__).resolve().parent
ROOT=Path.cwd();C=H.parent/'postovernight-long-D2-boundary-prepare-r10'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for block in iter(lambda:f.read(1048576),b''):h.update(block)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def save(name,v):(H/name).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
inputs=read(H/'input-manifest.json')['files']
checks={name:sha(ROOT/name)==row['sha256'] for name,row in inputs.items() if not row.get('mutable_context')}
pins=read(H/'parent-frozen-pins.snapshot.json')
pin_checks={name:sha(ROOT/name)==digest for name,digest in pins.items()}
cap=C/'capsule-final';manifest=read(cap/'capsule-manifest.json')
actual={str(p.relative_to(cap)) for p in cap.rglob('*') if p.is_file()}
capchecks={name:sha(cap/name)==digest for name,digest in manifest['files'].items()}
assert all(checks.values()) and all(pin_checks.values()) and all(capchecks.values())
assert actual==set(manifest['files'])|{'capsule-manifest.json'}
graph=read(C/'hash-DAG.json')['edges'];active=set();visited=set()
def visit(n):
 assert n not in active,'cyclic hash DAG'
 if n in visited:return
 active.add(n)
 for child in graph.get(n,[]):visit(child)
 active.remove(n);visited.add(n)
for n in graph:visit(n)
save('end-verification.json',dict(immutable_inputs=checks,parent_pins=pin_checks,capsule_members=capchecks,capsule_exact_membership=True,hash_DAG_acyclic=True,mutable_context_excluded=True))
finding=dict(id='BOUNDARY-R10-IPC-ENDPOINT-STARVATION',severity='P2',
 path='learning/runs/v2/postovernight-long-D2-boundary-prepare-r10/long_d2_executor.py',line=327,end_line=330,
 title='A failing supervisor endpoint prevents reading an already-readable worker failure',
 trigger='Both private endpoints are readable. The supervisor endpoint, visited first, repeatedly raises an unexpected ConnectionResetError or the actual Channel.receive zero-byte-packet error; the valid worker endpoint already holds an earlier failure packet.',
 mechanism='pump iterates supervisor before worker. An unexpected reset fails require at line330; other receive errors propagate at line327. The single IPC monitor_duty catches outside the entire pump. The failing channel stays eligible on later calls, so every pump and the unchanged final drain can abort before the second ready endpoint.',
 consequence='Independent cleanup duties now run, but valid peer failure evidence and its failure_ack can still be starved. Exact source-extracted monitor/pump proofs keep the inner direct-wait source99.75 and pool109.75 after ten passes while a readable worker source99.5 remains unread. The same exact path with only the valid endpoint ready consumes it, ACKs once and tightens the existing pool to109.5. No raw1 acceptance bypass, survivor, actual kernel schedule or measured OS overrun is claimed.',
 fix_direction='Keep unexpected endpoint loss fatal, but isolate per-endpoint receive/handling failures so another already-readable valid endpoint can still be processed under the same absolute deadline. Preserve one-shot sends, exact ownership checks, no blanket close relaxation and earliest-source pool tightening; no transport redesign or new allowance is supported.',
 proofs=[dict(script='proof_endpoint_starvation.py',command='endpoint-starvation-command.json',results='endpoint-starvation-results.json',stdout='endpoint-starvation.stdout.log',stderr='endpoint-starvation.stderr.log',raw_exit=0),dict(script='proof_zero_packet_starvation.py',command='zero-packet-starvation-command.json',results='zero-packet-starvation-results.json',stdout='zero-packet-starvation.stdout.log',stderr='zero-packet-starvation.stderr.log',raw_exit=0)],
 proof_limits='Exact AST-extracted production Execution.monitor/pump/fail, FailurePool, observed_failure and (second proof) Channel.receive. Fake readiness, sockets, clocks, direct reports, process groups, signals and absence. Persistent endpoint failure is an explicit fixture condition; no claim it caused the retained production transport failure. This is deterministic control-flow starvation of an endpoint already reported readable, not a queued-delivery guarantee.')
save('findings.json',dict(schema='frozen_boundary_r10_source_review_v1',verdict='changes_required',findings=[finding]))
(H/'audit.md').write_text("""# Frozen r10 boundary source audit

One P2 finding: BOUNDARY-R10-IPC-ENDPOINT-STARVATION. Exact trigger, lines, consequence, scope and proof receipts appear in findings.json. The remaining gap is inside the IPC duty: the repaired monitor isolates IPC from safety/reap/group/deadline duties, but pump still lets the first endpoint prevent reading the other endpoint. Both endpoints are already reported readable in each failing proof pass. The proof's persistent error schedule is synthetic and is not attributed to the historical production transport failure.

The reset proof and a distinct exact Channel.receive zero-byte-packet proof each retain the inner wait observation at99.75/deadline109.75 while the valid worker failure at99.5 stays unread across ten monitor passes. Controls process the valid worker endpoint, send one failure_ack, and tighten the same pool to109.5. Mocked positive absence allows cleanup_complete=true in both schedules; that is a fixture input, not OS evidence. No successful acceptance bypass or measured overrun is asserted. Per-endpoint isolation must preserve fatal unexpected channel loss, exact message ownership, single-send state and existing deadlines.

The original r9 abnormal-worker timestamp defect is repaired in the actual supervisor. An exact extracted supervise_owned proof retains99.75 handled100 and produces109.75, attempts immutable mandatory inner-failure before later worker_wait, and sends worker_wait once. Source retains the successful direct wait observation, never an inferred physical exit. Outer worker_wait validates before recovering the same source. Earlier guard, latch and peer comparison helpers remain exact historical bytes. The monitor now isolates cancellation, guard, cutoffs, reap, each group's TERM/KILL/absence and cleanup; bounded diagnostic recording and deadline checks remain outside the IPC duty. The new finding does not reopen those repaired independent duties.

The exact one-shot start_ack discriminator attempts once across eleven pump calls, leaves gate_acked strictly false and gate_ack_failed true, and latches failure. An exact early accept_observed check rejects actual raw1 despite accepted=true. The actual successful validate_wait_reports, accept_observed, validate_artifacts, checked_registration and worker_command blocks remain byte equal to r6. Producer gate verification uses is True. Full successful consumer acceptance was not re-executed in this review.

Fixture preconditions predeclare all15 original cases, exact NORMAL/DEFER phases and positive prerequisites. Pure exact-predicate controls accept correct positive entry and reject wrong FAILURE phase, earlier pool failure and missing milestones. Source hooks record pre-mutation state and accepted-publication/handshake/direct-wait milestones. Startup cancellation requires actual worker Popen only. The deliberate blocked-parent crash keeps live/no-prior-wait/raw7/positive-absence/unproven-orphan requirements. Post-injection ordering remains an ordering claim, not exclusive causality.

All eight target pins matched before proofs and at closeout. Five current authority/protocol pins matched. All87 source-manifest and368 implementation-evidence members matched actual bytes. Fresh static reads verified all255 active B bindings (including raw byte hashing of the interpreter and checkpoint inputs, never loading them), all75 original semantic sources, all129 capsule manifest members plus the manifest itself, exact capsule file membership and readonly regular-file/directory permissions, and actual registration pins. B255/R37/A9998 counts were measured from current maps. All10091 historical path/hash/class bindings remain covered, with retained_R3=9675 and retained_R4=9870. Full installed R37/archive A9998 endpoint hashing, runtime/cache execution and native discovery were not rerun. Those maps and root digests are static provenance evidence only. Hash-DAG edges are acyclic. Source still calls full actual endpoints and forced B/legacy/check_frozen/origin/runtime/cache checks.

Protected Learner/Schedule/run_schedule and worker ML try bytes match the approved guard/r4/r3 bases. Lifecycle, processes, boundary_integrity and freeze bytes equal r9; the fresh single scandir and transport/descriptor-close order remain unchanged. Source restores model/Adam/RNG before environment construction and requires64 rows/nine fields before gradients. Config2ac814d3842228017d09669364a8391344722da56ad19f41ad9030dbb930c2db, seed5562873868232098305 and D1ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f match current authorities. Caps7200/7140/7170, shared min(previous,earliest+10,T0+7210), inner1.0/outer.25 internal reserves, independent .05/.15/max.5 sampling and separate6GiB RSS/MPS remain source invariants. No five-second byte watchdog was reintroduced.

Complete requested plan/specification, original broad briefs, state snapshot, prior findings/audits/proof sources/raw results, parent reconciliations, full candidate.diff, actual production/fixture sources and source manifests were read as static inputs. Parent qualifications govern historical r7=0pass1fail68unrun and r8=1pass1ERROR67unrun; the known handoff prose error is not a new finding. Transport cause remains unknown. No parent-owned partial runtime attempt was used as final proof. The state snapshot is mutable context only.

Two reviewer setup failures are retained: initial pin attempt assumed capsule-final/manifest.json instead of capsule-final/capsule-manifest.json and exited1 before any proof; corrected parent path matched all eight pins. First static audit exited1 because its input inventory assumed every B member was inside the workspace; the interpreter lives outside it. Distinct static_audit_r2.py records external absolute paths and passed. Neither failure is a candidate defect or acceptance bypass. All four source-extracted proof commands exited0; no entire candidate suite was run. The supplied91-method result is parent-owned historical evidence for this frozen candidate, not reviewer-executed methods.

No OS/lifecycle/probe/stress/startup rerun, ML/project/native-runtime import, checkpoint decode, environment, inference, training, lease, scheduler, source edit, commit, PR, deployment, message, provider call or delegation occurred. Writes stayed in the new owned review directory. Filesystem hashes do not constitute universal OS write attestation. Parent owns reconciliation of this finding and final runtime validation before training.
""")
commands=[read(p) for p in sorted(H.glob('*-command.json'))]
save('command-receipts.json',dict(executed_evidence_commands=commands,initial_pin_failure=read(H/'initial-pin-attempt-failure.json'),failed_static_attempt='static-audit-command.json',read_and_authoring_commands='Full shell commands and raw exits remain in the enclosing tool transcript; this inventory pins all discriminator/static evidence invocations.'))
now=datetime.datetime.now(datetime.timezone.utc)
elapsed=(now-datetime.datetime(2026,10,25,2,44,49,tzinfo=datetime.timezone.utc)).total_seconds()
assert elapsed<=900
save('review-receipt.json',dict(schema='frozen_boundary_r10_review_receipt_v1',verdict='changes_required',findings=1,severity_counts={'P2':1},candidate=str(C.relative_to(ROOT)),owned_output=str(H.relative_to(ROOT)),budget_seconds=900,elapsed_seconds_conservative=elapsed,finished_at_utc=now.isoformat(),source_modified=False,source_write_scope='new owned review directory only',receipt_excludes_own_hash=True,proof_commands=4,proof_raw_exits=[0,0,0,0],static_audit_attempts=2,reviewer_setup_failures=2,verified_frozen_pins=8,verified_actual_B=255,verified_capsule_members=129,verified_immutable_inputs=len(checks),input_manifest_sha256=sha(H/'input-manifest.json'),end_verification_sha256=sha(H/'end-verification.json'),findings_sha256=sha(H/'findings.json'),audit_sha256=sha(H/'audit.md'),limitations=['Source/synthetic evidence only; no runtime/OS/performance/training acceptance.','No full R/A endpoint rerun.','Persistent endpoint error schedule is a synthetic condition, not a production transport cause claim.'],output_manifest_generated_after_command_closes=True))
validations=[]
for p in sorted(H.rglob('*.json')):
 command=[sys.executable,'-B','-m','json.tool',str(p)]
 result=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
 validations.append(dict(argv=command,raw_exit=result.returncode,stderr=result.stderr,path=str(p.relative_to(H))))
 assert result.returncode==0
save('json-validation.json',dict(schema='review_JSON_validation_v1',commands=validations,all_passed=True,excludes_itself=True))
# The wrapper records observed raw exit and hashes outputs only after logs close.
print(json.dumps(dict(verdict='changes_required',findings=1,immutable_inputs=len(checks),elapsed_seconds=elapsed,JSON_documents_validated=len(validations))))
