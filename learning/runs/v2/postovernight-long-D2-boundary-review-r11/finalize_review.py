"""Close readonly review evidence; no reviewed input is modified."""
from pathlib import Path
import datetime,hashlib,json,stat,time
H=Path(__file__).resolve().parent;ROOT=Path.cwd()
C=H.parent/'postovernight-long-D2-boundary-prepare-r11'
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):h.update(block)
    return h.hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def save(name,value):(H/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')

inputs=read(H/'input-manifest.json')['files']
checks={name:sha(ROOT/name)==row['sha256'] for name,row in inputs.items() if not row.get('mutable_context')}
pins=read(H/'parent-frozen-pins.snapshot.json')
pin_checks={name:sha(ROOT/name)==digest for name,digest in pins.items()}
cap=C/'capsule-final';manifest=read(cap/'capsule-manifest.json')
for ancestor in (cap,*cap.parents):assert stat.S_ISDIR(ancestor.lstat().st_mode)
assert not cap.stat().st_mode&0o222
actual=set()
for p in cap.rglob('*'):
    mode=p.lstat().st_mode
    assert not stat.S_ISLNK(mode) and not mode&0o222
    assert stat.S_ISREG(mode) or stat.S_ISDIR(mode)
    if stat.S_ISREG(mode):actual.add(str(p.relative_to(cap)))
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
assert not any((H/'proof-cache').iterdir())
commands={p.name:read(p) for p in H.glob('*-command.json') if p.name!='closeout-command.json'}
assert len(commands)==4 and all(v['raw_exit']==0 for v in commands.values())
save('end-verification.json',dict(immutable_inputs=checks,parent_pins=pin_checks,
    capsule_members=capchecks,capsule_exact_membership=True,capsule_root_ancestors_types_permissions=True,
    hash_DAG_acyclic=True,mutable_state_context_excluded=True,proof_cache_empty=True))
save('findings.json',dict(schema='frozen_boundary_r11_source_review_v1',verdict='no_findings',findings=[]))
(H/'result.txt').write_text('No findings\n')
(H/'audit.md').write_text('''# Frozen r11 source review

No findings. This is a source and bounded synthetic review of the specified frozen r11 target. It does not accept an experiment or predict that a future OS, stress, startup, native or training stage will pass. The parent owns reconciliation of final validation and the unused D2 authorization.

All eight parent-held target pins matched before any discriminator and at closeout. Four exact authority/protocol pins matched, including protocol-r8 fe11c08159bdb9ca1f03cb0fb96ffd133ad144d107b2a854d19fc49159aa2db2. The complete plan/specification, inherited broad briefs, current state snapshot, r10 findings/audit/proof sources and raw artifacts, Sonnet diagnosis/plan/model/proposed diff, qualified parent reconciliations, r11 implementation/completion/handoff/diff, actual controller/executor/lifecycle/process/integrity/fixture sources and manifests were read. State is mutable context and excluded from immutable rechecks. No concurrent parent-owned runtime attempt was treated as a final verdict.

Fresh static checks matched all 267 actual B path/hash bindings, including hashing checkpoint and interpreter bytes without decoding or loading them, all 75 original semantic sources, 125 source-manifest members, 478 implementation-evidence members, 135 capsule manifest members plus the manifest itself, exact capsule membership, readonly types/permissions, registration pins and an acyclic hash DAG. R37/A9998 counts were measured from their current maps, with all 10091 original path/hash/class bindings and retained 9870/9675 coverage checked. Full installed R/archive A endpoint hashing, native discovery, runtime/cache execution and loaded-memory attestation were not performed. Source still performs required full endpoint and forced B/genuine check_frozen/origin/runtime/cache checks. Static map coverage is not actual R/A runtime evidence.

Every controller function/class, including the whole supervise_owned, worker and protected Learner/Schedule/run_schedule bodies, remains byte equal to r10. Successful checked_registration/worker_command/validate_artifacts/validate_wait_reports/accept_observed and Execution.run remain byte equal to r10. Lifecycle, processes, boundary_integrity, freeze, synthetic fixtures, all 15 scenario options/limits, fixture preconditions and consumer predicates remain byte equal. Protected learner and worker ML try bytes also match approved earlier guard/r4/r3 sources. Config2ac814d3842228017d09669364a8391344722da56ad19f41ad9030dbb930c2db, seed5562873868232098305 and D1ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f match current authority. Model/Adam/RNG restoration precedes environment construction; 64 rows and nine fields precede gradients.

Changed executor methods are exactly monitor, monitor_duty and pump, plus new kill_due. Per-endpoint receive/parser/packet/ACK-send errors latch before readable siblings. Normal start ACK requires no latched failure; attempted/acked/failed booleans and one-send behavior remain. Expected-close retirement proves no direct reap. Current failure deadline and final-drain .25 reserve are recomputed after each peer; mandatory immutable inner failure publication, ACK-gated child reap, single worker_wait and no post-missing-ACK worker writes remain intact. Transport/socket type/.2s timeout/descriptor order are unchanged. No interpretation of the inconclusive earlier close-order treatment was adopted.

The independent mixed-endpoints discriminator used exact extracted Channel/Execution/FailurePool/observation/report-validation blocks with fake datagrams and readiness. Both endpoint directions covered reset, empty raw packet, partial/list/duplicate JSON, schema/sequence/sender/clock/future-time/FD/truncation rejection, failed ACK and partial ACK writes, in both normal and final-drain calls: 56 combinations. Each valid readable sibling supplied its earlier 99.5 source, tightened the pool to109.5, and received one ACK. Injected bad packets remained fatal; gate_acked/recovery stayed false. A separate schedule filled all eight diagnostic rows with repeated empty packets; later valid seq1 source99.25 was still consumed and ACKed once, tightening to109.25. These are discriminator combinations, not unit methods or OS transport evidence.

The independent escalation discriminator checked 16 gate rows plus a permanently failing gate through the actual monitor. Child None, absent registration and unknown worker state did not authorize an early supervisor KILL. Only actual-format validated matching worker/supervisor reports released the earlier gate; malformed identity/raw/time evidence was rejected. Late earlier peers tightened current worker/latest bounds. A cap-truncated window remained truthful. Gate exceptions before first+5 caused no early KILL; both role attempts occurred at105 for source100 and the independent failure deadline exited at110, with worker_wait null and cleanup incomplete. All times and signals are synthetic, not exact OS timing claims.

The independent old/new monitor discriminator used exact old/r11 monitor/pump/fail and new kill_due with an explicitly modeled responsive supervisor poll. Old code KILLed both roles at105 and retained no worker report. R11 kept worker KILL at105, consumed a matching modeled direct worker report at105.02 and attempted supervisor KILL at105.04. With no report it used109.5, retaining worker_wait null. This demonstrates control-flow ordering under the documented model assumptions. The modeled process table supplies no real direct-reap, absence or delivery evidence.

The existing 112-method raw0/.7900596669642255s result is supplied child/parent-owned evidence. This reviewer did not rerun that suite or transfer its count. Historical r10 OS failure, Sonnet18 assertion scope and over-budget result remain unchanged. The disclosed child bootstrap /tmp write-location deviation remains recorded, not retroactively compliant and not itself a runtime defect.

The 7200/7140/7170 limits, shared min(previous,earliest+10,T0+7210), .05/.15/max.5 resource/lease timing, separate6GiB RSS/MPS, inner1.0/outer.25 reserves, explicit unproven reaping and raw0/2/exit-wall/mandatory-summary/current-byte acceptance checks remain. No new allowance, signal owner, retry, five-second byte watchdog, cadence skip or acceptance relaxation was found.

One independent static command and three bounded source-extracted discriminator commands exited0. No failed proof command occurred; expected injected exceptions remain in raw evidence. No entire unit/OS/probe/stress/startup rerun, project/ML/native-runtime import, checkpoint decode, environment/inference/training, lease, scheduler, commit, PR, deployment, message, provider call or nested delegation occurred. Writes were confined to this new review directory. No universal OS write audit is claimed. Logs close before output hashing; JSON validation and final input/pin rechecks accompany the receipt.
''')
save('command-receipts.json',dict(executed_evidence_commands=commands,
    scope='Three narrow discriminators and one static audit; no target validation suite rerun.',
    failed_proof_commands=[],authoring_and_read_commands='Exact calls and raw exits retained in enclosing tool transcript.'))
initial=read(H/'pin-verification.json')['started_epoch']
elapsed=time.time()-(initial-120.)
assert elapsed<=900
save('review-receipt.json',dict(schema='frozen_boundary_r11_review_receipt_v1',verdict='no_findings',
    findings=0,candidate=str(C.relative_to(ROOT)),owned_output=str(H.relative_to(ROOT)),
    budget_seconds=900,elapsed_seconds_conservative=elapsed,
    timing_basis='Clock starts 120 seconds before first retained pin-verification epoch to include initial reading.',
    finished_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    reviewed_target_modified=False,write_scope='new owned review output only',receipt_excludes_own_hash=True,
    proof_commands=3,proof_raw_exits=[0,0,0],static_audit_commands=1,static_raw_exit=0,
    reviewer_setup_failures=0,verified_frozen_pins=8,verified_actual_B=267,
    verified_capsule_manifest_members=135,verified_source_manifest_members=125,
    verified_implementation_evidence_members=478,verified_immutable_inputs=len(checks),
    supplied_unit_methods_not_rerun=112,input_manifest_sha256=sha(H/'input-manifest.json'),
    end_verification_sha256=sha(H/'end-verification.json'),findings_sha256=sha(H/'findings.json'),
    audit_sha256=sha(H/'audit.md'),limitations=['Source and synthetic evidence only; no OS/native/runtime/performance/training acceptance.','No full R/A endpoint rerun.','No production transport-cause claim.'],
    output_manifest_generated_only_after_logs_close=True))
print(json.dumps(dict(verdict='no_findings',immutable_inputs=len(checks),elapsed_seconds_conservative=elapsed)))
