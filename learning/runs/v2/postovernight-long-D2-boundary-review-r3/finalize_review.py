"""Publish review-only findings and a manifest, without touching parent inputs."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
PREPARE='learning/runs/v2/postovernight-long-D2-boundary-prepare-r3/'

def save(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
initial=json.loads((HERE/'input-hashes.json').read_text())
findings=[
 dict(id='BOUNDARY-R3-WORKER-DESCRIPTOR',severity='P2',path=PREPARE+'long_d2.py',line=938,end_line=938,
      title='Ordinary worker exceptions conflict with their own first-failure timestamp',
      trigger='An ordinary worker exception occurs with no previously observed Guard failure, cancellation, or alarm.',
      mechanism='primary_error records catch time in error.first_failure_descriptor at lines 924/837-854. worker_failure then samples a later now at line 928 and explicitly passes that later time to FailurePool.fail at line 938. lifecycle.py:57 rejects it because descriptor.timestamp differs. The call occurs before the ACK try block.',
      consequence='worker_failure raises Failure descriptor timestamp differs before latching its cleanup pool or attempting the executor ACK. The worker unwinds through finally to main; the fallback reports the descriptor-mismatch exception instead of the initiating failure. Worker result/checkpoint failure evidence is lost and the intended first-failure deadline is not started at the initiating observation. Raw failure remains ineligible; no acceptance bypass is claimed.',
      proof={'script':'proof_worker_failure.py','stdout':'proof-worker-failure.stdout.log','stderr':'proof-worker-failure.stderr.log','observation':'descriptor timestamp 100.001; clock 100.00300000000001; pool_first/pool_until null; ACK calls 0; Stop: Failure descriptor timestamp differs','execution_limit':'Deterministic clock, exact extracted functions; no lifecycle signals or ML. The original combined shell raw exit is 0; a separate child exit was not retained.'},
      fix_direction='Reuse the selected descriptor timestamp when initializing the worker pool, rather than sampling a new catch time.'),
 dict(id='BOUNDARY-R3-CONSUMER-REAP',severity='P2',path=PREPARE+'long_d2_executor.py',line=512,end_line=512,
      title='Exact parent consumer accepts missing or failed direct-reap reports',
      trigger='With valid parent registration/summary pins, current artifact hashes, outer raw exit 0, and finite in-budget wall, remove inner_wait and worker_wait from the receipt or change both reports to returncode 1/direct_child_reaped false/raw_wait_status 256.',
      mechanism='accept_observed checks only new_session_verified and group_absent booleans in ownership. It never reads either direct-parent wait report, checks their raw status, ties their PIDs to ownership, or validates their per-role cutoff.',
      consequence='The registered consumer returns True without the mandatory owned-leader reaping/raw-exit proof. This is a consumer-contract hole. The production producer has separate wait checks at lines 392-396; this review does not claim an actual unreaped production process was accepted.',
      proof={'script':'proof_accept_observed.py','command':'proof-consumer-command.json','results':'consumer-proof-results.json','stdout':'proof-consumer.stdout.log','raw_exit':0,'observations':{'control':True,'both_wait_reports_missing':True,'both_reports_raw_failure_and_not_reaped':True,'raw_outer_exit_1_rejected':True},'execution_limit':'Exact source-extracted consumer and real JSON/hash/file/summary validators, with filesystem constants redirected to owned fixtures. No process evidence or ML results fabricated as runtime proof.'},
      fix_direction='Require and validate both direct-parent wait reports against raw status, ownership PIDs, matching normal outcome, and worker/inner deadlines.'),
 dict(id='BOUNDARY-R3-INNER-PUBLICATION-ORDER',severity='P2',path=PREPARE+'long_d2.py',line=1337,end_line=1338,
      title='Inner failure handler still runs optional telemetry before mandatory failure receipt',
      trigger='After an inner failure and cleanup notification, optional inner-verification.jsonl persistence blocks or consumes the remaining shared cleanup allowance.',
      mechanism='The actual supervise_owned exception branch invokes optional_timing at line 1337 before replace_json(inner-failure.json) at line 1338. The new failure_publication helper has no call sites in long_d2.py. Outer uses the helper; inner does not.',
      consequence='The mandatory inner failure receipt is not even attempted until optional telemetry returns. Executor cleanup can terminate the inner process first, losing mandatory failure evidence. Exception swallowing alone does not protect against blocked optional IO. This is the still-unwired inner half of the retained telemetry-before-receipt defect; raw outer failure still rejects.',
      proof={'source_order':'source-publication-order.json','source_snapshot':'source-snapshot/long_d2.py','static_source_confirmed':True,'runtime_suppression_tested':False,'fixture_attempts':['proof-inner-command.json','proof-inner-r2-command.json'],'fixture_limit':'Both extracted attempts observed optional_timing before mandatory replacement. They are not successful end-to-end receipt proofs: first omitted json/os from the extraction namespace; second corrected json but still omitted os and its final assertion failed with raw exit 1. Both attempts and partial files are preserved. No blocked IO, process kill, or acceptance-bypass claim relies on them.'},
      fix_direction='Use mandatory-first failure publication on the actual inner exception path, keeping telemetry independently guarded.')
]
save(HERE/'findings.json',dict(schema='frozen_boundary_r3_source_review_v1',verdict='changes_required',findings=findings))

(HERE/'audit.md').write_text('''# Frozen boundary integrity r3 review

Verdict: **changes required**. Three P2 source/consumer findings appear in `findings.json`.

## Identity and scope

The initial byte inventory was captured before discriminators. All eight supplied candidate hashes and the protocol/policy hashes matched. `input-hashes.json` retains expected and observed values. `context-snapshot/` preserves read-time required authorities, including the complete contextual parent state. Full implementation plan, specification, state, accepted policy, diagnosis and policy plan were read. Latest supplied exact r3 targets take precedence over lagging state fields.

`end-snapshot.json` rechecked 146 frozen candidate/capsule files, excluding parent-owned `attempts/`, and the ten target pins, with no mismatch. Initial broad byte inventory also included metadata hashes of then-existing parent attempt files; those mutable files are not authority, source equality, or final validation evidence. Their content/results were not used to infer parent OS completion. No mutable parent state hash was treated as an immutable execution input.

## Source checks

`static-source-audit.json` independently records exact protected-block equality against both R4 and the rejected guard preparation, including the worker ML try body, unchanged `check_module_origins`, Learner, Schedule, run_schedule, restoration/entry helpers and configuration helpers. Current bytes of all 75 original semantic-source files matched their declarations and B classification. Config hash, master seed and D1 checkpoint hash matched; checkpoint bytes were only hashed, never decoded.

Classification is B=235, R=37, A=9998. All 10091 historical full path/hash bindings appear exactly once, preserving the 9870/9675 retained unions. No canonical class/hash conflict was found. Foundation identity's acceptance, M2 frozen identity, build receipt, executable and interpreter dependencies are B. This is a declaration/source audit plus the specified protected-source hash checks; it is not a new complete R/A endpoint execution.

The source runs actual B bytes/capsule/membership checks at forced boundaries; imported workers call genuine original check_frozen, unchanged project origins and added runtime/path/cache checks. Nonforced callbacks remain safety-only. Full R/A members are checked by the outer endpoint verifier before spawn and after owned absence, with no five-second age predicate. The DAG excludes root envelopes from leaf self-hashing and uses external registration/parent pins. Original paths and the cooperative no-writer assumption remain explicit. Native discovery is bounded Torch/NumPy/CPython/libpython provenance, not a whole-OS/transitive-memory attestation.

Source ordering preserves model/Adam/RNG restoration before environment construction and exact 64-row, nine-field entry control before update/gradient. No runtime restoration, entry behavior, native allowlist adequacy under real imports, performance, training gate, or campaign acceptance was established here.

## Reproducible findings

1. **BOUNDARY-R3-WORKER-DESCRIPTOR**, controller line 938. Exact extracted `worker_failure` rejects its own earlier catch descriptor when handed an ordinary exception. The proof reaches no ACK and initializes no cleanup pool. Logs retain the deterministic source-clock values. Main's fallback remains a raw failure path, but its initiating reason is the newly thrown descriptor error.
2. **BOUNDARY-R3-CONSUMER-REAP**, executor line 512. Exact extracted `accept_observed`, real JSON/hash/summary checks and owned file fixtures return true with both wait reports absent, and separately with both raw reports failed/not reaped. Raw outer exit 1 remains rejected. This demonstrates the actual consumer predicate's missing requirement; the launcher producer independently validates real waits, and no real process was launched by this proof.
3. **BOUNDARY-R3-INNER-PUBLICATION-ORDER**, controller lines 1337-1338. Static AST output shows optional telemetry precedes mandatory inner failure publication. There are zero calls to `failure_publication` in the controller. The outer helper repair therefore does not establish inner wiring. Blocked optional IO can consume the allowance before any mandatory attempt. This is source ordering evidence, not a new OS suppression measurement.

## Execution and limitations

No production unit suite, OS lifecycle case, contention stress, startup rehearsal, ML/native import, checkpoint decoding, inference, gradient, training campaign, lease/scheduler operation, provider/delegation call, commit, PR, deployment or message was performed. All writes belong to this new review directory. Existing 21-method and freeze successes are supplied parent context only. Parent owns final attempt-11 OS reconciliation and every later validation decision.

There were four small source-extracted discriminator attempts: worker timestamp, exact consumer, and two inner-ordering fixtures. Consumer proof has retained raw exit 0. Worker proof's combined shell exit is 0, but its individual Python exit was not independently retained; final confirmation output and empty stderr are preserved. The two inner fixtures are explicitly limited: both traced the relevant order, but omitted dependencies in the extracted namespace prevented the eventual receipt. The second's added final assertion exposed that with raw exit 1. No further inner fixture run followed. These failures are retained, not counted as passing receipt tests, and do not prove acceptance bypass or actual IO suppression. `proof-inner-fixture-correction.md` records the intermediate correction; `findings.json` records the remaining missing os dependency.

The source consumer proof and source finding are distinct from actual runtime/process acceptance. The review cannot accept training, transfer historical pass counts, qualify the teacher, or reconcile the parent's in-flight results. No finding treats the intended removal of fixed five-second integrity/revisit guarantees as a bug.
''')

elapsed=time.time()-initial['timestamp']
save(HERE/'receipt.json',dict(schema='frozen_boundary_r3_review_receipt_v1',status='completed_changes_required',findings=3,severities={'P2':3},output_directory=str(HERE),elapsed_since_initial_snapshot_seconds=elapsed,budget_seconds=900,source_target_matches=True,source_end_snapshot='end-snapshot.json',source_audit='static-source-audit.json',findings_path='findings.json',audit_path='audit.md',campaign_launched=False,production_units_executed=0,OS_lifecycle_cases_executed=0,stress_executed=0,startup_rehearsals_executed=0,ML_native_imports=False,source_discriminator_attempts=4,inner_fixture_attempts_with_unproven_final_receipt=2,output_manifest='output-manifest.json',output_manifest_excludes_itself=True,acceptance_authority=False,parent_reconciliation_required=True))
# Explicit json.tool parsing, with every raw exit retained.
checks=[]
for path in sorted(HERE.rglob('*.json')):
    with open('/dev/null','w') as sink:
        r=subprocess.run([sys.executable,'-m','json.tool',str(path)],stdout=sink,stderr=subprocess.PIPE,text=True)
    checks.append(dict(path=str(path.relative_to(HERE)),raw_exit=r.returncode,stderr=r.stderr))
save(HERE/'json-validation.json',dict(command=[sys.executable,'-m','json.tool','<each listed path>'],checks=checks))
assert all(row['raw_exit']==0 for row in checks)
manifest={str(path.relative_to(HERE)):dict(sha256=sha(path),size=path.stat().st_size) for path in sorted(HERE.rglob('*')) if path.is_file() and path.name!='output-manifest.json'}
save(HERE/'output-manifest.json',dict(schema='review_output_manifest_v1',excludes=['output-manifest.json'],files=manifest))
# Parse final manifest with the explicitly required tool as well.
with open('/dev/null','w') as sink:
    subprocess.run([sys.executable,'-m','json.tool',str(HERE/'output-manifest.json')],stdout=sink,check=True)
print(json.dumps(dict(findings=3,elapsed_seconds=elapsed,manifest_members=len(manifest),json_files_checked=len(checks)+1,verdict='changes_required')))
