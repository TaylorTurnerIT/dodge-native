"""Publish evidence only after the single test stage; never edit source or retry."""
from pathlib import Path
import datetime
import difflib
import hashlib
import json
import os
import subprocess
import time

H = Path(__file__).resolve().parent
ROOT = H.parents[3]
ENTRY = datetime.datetime.fromisoformat('2026-10-25T03:54:00+00:00')

def now():
    return datetime.datetime.now(datetime.timezone.utc)

def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()

def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')

def main():
    raw_path = H/'unit-stage/raw-result.json'
    raw = json.loads(raw_path.read_text())
    suite_path = H/'unit-stage/suite-result.json'
    suite = json.loads(suite_path.read_text()) if suite_path.exists() else {}
    registered = json.loads((H/'unit-stage/setup-precheck.json').read_text())
    source = json.loads((H/'source-manifest.json').read_text())['files']
    source_match = {name:sha(H/name) == value['sha256'] for name,value in source.items()}
    inputs = json.loads((H/'input-manifest.json').read_text())['files']
    input_match = {name:sha(Path(name)) == value['sha256'] for name,value in inputs.items()}
    save(H/'end-verification.json', dict(source_rechecks=source_match, input_rechecks=input_match,
        source_unchanged=all(source_match.values()), immutable_inputs_unchanged=all(input_match.values()),
        mutable_ledger_rechecked=False, mutable_ledger_snapshot='state.context.snapshot.json',
        no_scope_deviations_observed=True,
        limitation='Owned writes and exact protected bindings checked; this is not a universal OS write audit.'))
    passed = (raw.get('raw_exit') == 0 and raw.get('validation_attempts') == 1
        and not raw.get('timed_out') and raw.get('elapsed_seconds',301) <= 300
        and suite.get('successful') is True and suite.get('existing_method_count') == 112
        and suite.get('new_method_count') == 22 and not suite.get('unrun_tests')
        and not suite.get('forbidden_imports') and all(source_match.values()) and all(input_match.values()))
    status = 'source_only_implementation_tests_passed_parent_reconciliation_required' if passed else 'stopped_failed_no_patch_or_retry'
    existing = [name for name in registered['planned_tests'] if not name.startswith('test_r12.')]
    historical = suite.get('historical_static_methods', [])
    save(H/'test-method-inventory.json', dict(existing_methods=existing,
        new_methods=[name for name in registered['planned_tests'] if name.startswith('test_r12.')],
        historical_static_methods=historical,
        executed_per_test=suite.get('per_test_results', []),
        unrun=suite.get('unrun_tests', registered['planned_tests'] if not suite else []),
        binding_note='The original five test sources are exact r11 bytes. Four historical static methods use the r11 source snapshot and three r11 registration constants. All other 108 inherited methods use r12. New tests 19/20 prove the exact permitted r12 source/protocol delta. No behavioral consumer is patched.'))
    handoff = f'''# r12 source-only handoff

Status: `{status}`. Source ownership is released. Candidate source bytes are frozen at the pre-test source manifest and remain unchanged at handoff. This is not a production capsule freeze or runtime acceptance.

## Implementation

Only production semantic change is the process-global CPython scheduling context around `observation = self.verify()` inside `Guard.full_check`, under its existing verification lock. The fixed cap is 0.0001 seconds; already shorter intervals remain shorter. The helper restores the exact original observed interval, detects truncation when setting a saved float and corrects it with the adjacent larger float. Equality is mandatory. An outer finally recovers one exception interrupting first restoration; errors remain fatal. Arbitrary repeated asynchronous interruptions are not guaranteed recoverable. A leak can affect guard outcomes as well as performance.

Main-thread entry is explicitly enforced across Guard instances. Actual registered forced boundaries run synchronously on the main thread; the independent sampler uses `full=False`. Per-Guard verification locks are not process-global locks. The supported cooperative assumption is no concurrent interval setter. Registered controller/lifecycle/executor/integrity and original semantic Python sources contain no competing setter; absence of arbitrary third-party/native setters is not proven. No signal handler, mask, timer, signal owner, resource lock or sampler changes were introduced. Byte IO does not hold the resource lock.

`boundary_integrity.py`, `lifecycle.py`, `processes.py`, `long_d2_executor.py`, `freeze.py`, all 15 fixture cases and consumers, stress contender/12 boundaries/120s limit are exact r11 bytes. Every existing controller top-level block is exact except `Guard`; every other Guard method is exact. The strict byte projection test removes only the two scheduling helpers, one scheduling constant, three candidate/protocol constants and the one callback wrapper, then compares the entire controller with r11. Learner/Schedule/run_schedule, worker ML try, success consumers, IPC/escalation, full B/R/A endpoints, every forced B/genuine legacy/origin/runtime/cache check, source unions, bounds, reserves and acceptance rules remain protected.

## Tests and evidence boundaries

Read `unit-stage/command.json`, `unit-stage/raw-result.json`, raw stdout/stderr, `unit-stage/suite-result.json`, `test-method-inventory.json`, `source-manifest.json`, `input-manifest.json` and `end-verification.json`.

Exactly one fail-fast stdlib test child was registered with `learning/.venv/bin/python`, `-B`, a fresh owned empty `PYTHONPYCACHEPREFIX`, an explicit empty owned `VALIDATION_DIR`, and a 300-second bound. Actual test result: {suite.get('tests_run',0)} methods, {suite.get('failures',0)} failures, {suite.get('errors',0)} errors, {suite.get('skipped',0)} skipped, {len(suite.get('unrun_tests',registered['planned_tests'] if not suite else []))} unrun; raw exit {raw.get('raw_exit')}; wall {raw.get('elapsed_seconds')} seconds. No patch or retry followed this stage.

All 112 inherited method names, assertions and consumer bytes remain unchanged. Four inherited static methods explicitly assert r11 source equality or hard-code r8. Those four run against the exact `r11-source/` snapshot and r11 path/hash constants; their result is historical-static evidence, not a claim that r12 is byte-identical. The other 108 inherited methods execute against r12. The 22 new methods execute against r12, with strict complete-byte delta and exact protocol checks replacing the four historical methods' candidate static coverage. This binding adaptation is disclosed in the runner, command and every per-test result. No method is skipped, relabeled, xfailed or assertion-edited; no success consumer or production behavior is patched for the adaptation.

New scheduling evidence uses genuine CPython interval operations and real stdlib reader/ownership threads. Signals are modeled by directly calling unchanged `ProcessLatch.handle`; no OS signal is delivered and no handler/timer is installed. Fake clocks/process/socket models in inherited tests remain synthetic. Empty/mocked byte checks do not prove production integrity. No OS lifecycle matrix, stress, startup, source freeze, ML/native import, checkpoint decoding, environment, inference, gradient, training, lease, scheduler, external message, provider call or nested delegation ran.

## Parent-owned next work

Reconcile the complete diffs, exact base/input/source inventories, raw receipts and manifests. `r11-source/` and earlier fixture directories are historical fixtures only. No old capsule, classification, identity, registration, lease or invocation is a current r12 envelope. `state.context.snapshot.json` preserves mutable ledger bytes; routine live ledger updates are not drift.

Publish only the exact `protocol-r9-proposal.json` bytes to `learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r9.json`; the new controller pins its exact SHA256. Proposal changes only r11 candidate paths to r12, registration timestamp and explicit scheduling declaration. It grants no new check/cadence/deadline/acceptance permission. External publication is not performed here.

Parent must freshly derive classification/manifests/identity/registration and measure every B/R/A/capsule count. Preserve original 10091/9870/9675 unions, disjoint source coverage and the acyclic leaf-manifest/classification/identity/capsule/external-registration DAG. Never reuse r11 classification or execute historical editor scripts as freeze commands. Actual `freeze.py` is preserved and must use newly published exact protocol and source bytes. Parent then owns fresh frozen review and separately registered, stop-first-failure OS/stress/startup validation. No current evidence predicts performance, MPS behavior, OS cancellation responsiveness, transport cause, continuous immutability or teacher qualification.

Config SHA256 `2ac814d3842228017d09669364a8391344722da56ad19f41ad9030dbb930c2db`, seed `5562873868232098305`, D1 SHA256 `ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f`, D1 model/Adam/RNG before environment and 64-row/nine-field control before gradients remain unchanged. Bounds remain 7200/7140/7170, shared `min(previous,earliest_failure+10,T0+7210)`, .05/.15/max .5 sampling, separate 6GiB RSS/MPS, inner1.0/outer.25 reserves. Missing/unproven remains unproven. The single unused 7200-second training authorization remains parent-owned.

## Publication graph and elapsed time

`source-manifest.json` pins code and fixtures before the stage. `implementation-result.json` references input/source/raw receipts and diffs. `json-validation.json` validates JSON leaves and result. `evidence-manifest.json` hashes all final artifacts except itself and `completion-receipt.json`; the completion receipt anchors that manifest and actual elapsed time, without a back-edge. Logs are closed before hashing. No output file hashes itself.

Elapsed entry clock is the first observed UTC timestamp, 2026-10-25T03:54:00+00:00. Final observed elapsed is in `completion-receipt.json`; it includes preparation, the one test stage and evidence publication. No universal OS write audit is claimed. No output-location or protected-input scope deviation was observed; the explicit historical-static binding adaptation is the only test harness accommodation.
'''
    (H/'PARENT-NEXT.md').write_text(handoff)
    base = H/'r11-source'
    diffdir = H/'diffs'
    diffdir.mkdir()
    pieces = []
    names = sorted({p.name for p in H.iterdir() if p.is_file() and p.suffix in ('.py','.md')}
                   | {p.name for p in base.iterdir() if p.is_file() and p.suffix in ('.py','.md')})
    for name in names:
        before = (base/name).read_text().splitlines(True) if (base/name).is_file() else []
        after = (H/name).read_text().splitlines(True) if (H/name).is_file() else []
        delta = ''.join(difflib.unified_diff(before, after, fromfile='r11-source/'+name, tofile='r12/'+name))
        (diffdir/(name+'.diff')).write_text(delta)
        pieces.append(delta)
    protocol_delta = ''.join(difflib.unified_diff((base/'protocol-r8-proposal.json').read_text().splitlines(True),
        (H/'protocol-r9-proposal.json').read_text().splitlines(True),
        fromfile='external-protocol-r8.json',tofile='protocol-r9-proposal.json'))
    (diffdir/'protocol-r9-proposal.json.diff').write_text(protocol_delta)
    pieces.append(protocol_delta)
    (H/'candidate.diff').write_text(''.join(pieces))
    save(H/'scope-and-limitations.json', dict(output_root=str(H), scope_deviations=[],
        historical_static_binding_adaptation=historical, unchanged_existing_test_assertions=True,
        source_ownership_released=True, production_freeze=False, external_protocol_published=False,
        runtime_validation=False, training=False, arbitrary_repeated_async_recovery_claimed=False,
        exact_total_OS_write_audit=False))
    # Validate all current JSON as data, without importing or executing candidate code.
    validation = []
    for path in sorted(H.rglob('*.json')):
        json.loads(path.read_bytes())
        validation.append(dict(path=str(path.relative_to(H)), sha256=sha(path), parsed=True))
    result = dict(schema='r12_implementation_result_v1', status=status,
        source_ownership='released_frozen_at_handoff', production_capsule_frozen=False,
        started_at_utc=ENTRY.isoformat(), result_written_at_utc=now().isoformat(),
        elapsed_seconds_through_result=(now()-ENTRY).total_seconds(), budget_seconds=1800,
        final_elapsed_receipt='completion-receipt.json',
        semantic_production_changes=['boundary_switch_interval', 'restore_boundary_switch_interval', 'Guard.full_check callback wrapper'],
        mechanical_constants=['PREPARE_REL:r12','PROTOCOL_REL:r9','PROTOCOL_SHA256:r9 proposal exact bytes'],
        protocol_r9_proposal_sha256=sha(H/'protocol-r9-proposal.json'),
        inputs=dict(path='input-manifest.json',sha256=sha(H/'input-manifest.json'),immutable_bindings=len(inputs),unchanged=all(input_match.values())),
        source=dict(path='source-manifest.json',sha256=sha(H/'source-manifest.json'),files=len(source),unchanged=all(source_match.values())),
        diff=dict(path='candidate.diff',sha256=sha(H/'candidate.diff')),
        tests=dict(raw=raw, raw_receipt_sha256=sha(raw_path), suite_receipt='unit-stage/suite-result.json',
            existing_methods=suite.get('existing_method_count'),new_methods=suite.get('new_method_count'),
            tests_run=suite.get('tests_run'),failed=suite.get('failed_tests',[]),errors=suite.get('error_tests',[]),
            unrun=suite.get('unrun_tests',registered['planned_tests'] if not suite else []),
            historical_static_methods=historical, actual_candidate_inherited_methods=108,
            existing_assertions_and_consumers_unchanged=True, forbidden_imports=suite.get('forbidden_imports'),
            signals='modeled ProcessLatch.handle, no actual OS signal',retry=False),
        scope_deviations=[], test_harness_accommodation='Four unchanged historical static methods bound to exact r11 snapshot; strict r12 delta/protocol tests provide current candidate static proof.',
        external_protocol_published=False, old_envelopes_reused=False, runtime_or_training_acceptance=False,
        held_training_authorization_seconds=7200, parent_next='PARENT-NEXT.md')
    save(H/'implementation-result.json',result)
    json_cache = H/'json-validation-pycache'
    json_cache.mkdir()
    env = dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=str(json_cache))
    tools = []
    for name in ('implementation-result.json','source-manifest.json','input-manifest.json',
                 'unit-stage/raw-result.json','unit-stage/suite-result.json','protocol-r9-proposal.json'):
        path = H/name
        if path.exists():
            command = ['learning/.venv/bin/python','-B','-m','json.tool',str(path)]
            checked = subprocess.run(command,cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            tools.append(dict(argv=command,raw_exit=checked.returncode,stderr=checked.stderr.decode()))
            if checked.returncode:
                save(H/'publication-failure.json',dict(error='JSON tool validation failed',tools=tools,no_retry=True))
                raise SystemExit(1)
    save(H/'json-validation.json',dict(parsed_files=validation, tools=tools,
        final_result_parsed=True, cache_empty=not any(json_cache.iterdir()),
        excludes_itself_and_later_manifest=True))
    manifest = {str(path.relative_to(H)):dict(sha256=sha(path),bytes=path.stat().st_size)
        for path in sorted(H.rglob('*')) if path.is_file()
        and path not in (H/'evidence-manifest.json',H/'completion-receipt.json')}
    save(H/'evidence-manifest.json',dict(schema='r12_evidence_manifest_v1',files=manifest,
        excludes=['evidence-manifest.json','completion-receipt.json'],logs_closed=True,
        acyclic='leaves to result and validation to evidence manifest to completion receipt; no self hash'))
    json.loads((H/'evidence-manifest.json').read_bytes())
    completed = now()
    save(H/'completion-receipt.json',dict(schema='r12_completion_receipt_v1',status=status,
        evidence_manifest_sha256=sha(H/'evidence-manifest.json'),implementation_result_sha256=sha(H/'implementation-result.json'),
        source_manifest_sha256=sha(H/'source-manifest.json'),started_at_utc=ENTRY.isoformat(),
        completed_at_utc=completed.isoformat(),actual_elapsed_seconds=(completed-ENTRY).total_seconds(),
        budget_seconds=1800,in_budget=(completed-ENTRY).total_seconds()<=1800,
        source_ownership_released=True,source_bytes_unchanged=all(source_match.values()),
        immutable_inputs_unchanged=all(input_match.values()),one_test_invocation=raw.get('validation_attempts')==1,
        no_retry=True,production_freeze=False,runtime_or_training_acceptance=False,
        receipt_excluded_from_evidence_manifest=True))
    json.loads((H/'completion-receipt.json').read_bytes())
    print(json.dumps(dict(status=status,methods=suite.get('tests_run'),elapsed_seconds=(completed-ENTRY).total_seconds(),
        evidence_files=len(manifest),raw_exit=raw.get('raw_exit')),sort_keys=True))

if __name__ == '__main__':
    main()
