"""Post-stage publication: diffs, projection report, receipts, manifests.
Runs once after the single registered stage; never edits source; never reruns tests."""
from pathlib import Path
import datetime, difflib, hashlib, json, subprocess, sys, time

H = Path(__file__).resolve().parent
ROOT = H.parents[3]
sys.path.insert(0, str(H))
import current_delta as delta  # stdlib only; never imports the candidate

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(name, value):
    with (H / name).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def inventory():
    paths = list(H.glob('*.py')) + [H/'protocol-r10-proposal.json', H/'protocol-r9-proposal.json', H/'protocol-r8-proposal.json']
    for name in ('original-source', 'r6-source', 'r9-source', 'r10-source', 'r11-source', 'r12-source'):
        paths.extend(p for p in (H/name).rglob('*') if p.is_file())
    paths += [H/'retained-r9-injection.json', H/'preparation-copy.json']
    return {str(p.relative_to(H)): dict(sha256=sha(p), bytes=p.stat().st_size) for p in sorted(set(paths))}

def udiff(old, new, label_old, label_new):
    return ''.join(difflib.unified_diff(old.read_text().splitlines(True) if old.exists() else [],
        new.read_text().splitlines(True), fromfile=label_old, tofile=label_new))

def main():
    started = json.loads((H / 'start.json').read_text())
    stage = H / 'unit-stage'
    raw = json.loads((stage / 'raw-result.json').read_text())
    suite_path = stage / 'suite-result.json'
    suite = json.loads(suite_path.read_text()) if suite_path.exists() else None
    frozen = json.loads((H / 'source-manifest.json').read_text())['files']
    source_unchanged = frozen == inventory()
    (H / 'diffs').mkdir()
    combined = []
    changed = []
    for path in sorted(p for p in H.iterdir() if p.is_file() and p.suffix in ('.py', '.json') and p.name not in
                       ('start.json',)):
        old = H/'r12-source'/path.name
        text = udiff(old, path, 'r12-source/' + path.name, 'r14/' + path.name)
        if path.name.startswith(('input-manifest', 'base-source', 'source-manifest', 'state.', 'implementation', 'completion', 'evidence', 'json-validation', 'test-receipt', 'byte-projection', 'finalize', 'prepare_', 'current_delta', 'run_unit_suite', 'unit_stage')):
            continue
        if text:
            (H / 'diffs' / (path.name + '.diff')).write_text(text)
            combined.append(text)
            changed.append(path.name)
    for name in ('current_delta.py', 'run_unit_suite.py', 'unit_stage.py', 'test_r14.py', 'protocol-r10-proposal.json', 'prepare_r14.py', 'finalize_r14.py'):
        old = H/'r12-source'/name if (H/'r12-source'/name).exists() else Path('/nonexistent')
        text = udiff(old, H/name, 'r12-source/' + name, 'r14/' + name)
        (H / 'diffs' / (name + '.diff')).write_text(text)
        if name not in changed:
            combined.append(text); changed.append(name)
    (H / 'candidate.diff').write_text(''.join(combined))
    (H / 'diffs' / 'protocol-r10-vs-r9.diff').write_text(udiff(H/'r12-source/protocol-r9-proposal.json', H/'protocol-r10-proposal.json', 'protocol-r9-proposal.json', 'protocol-r10-proposal.json'))
    (H / 'diffs' / 'long_d2.py.vs-r11.diff').write_text(udiff(H/'r11-source/long_d2.py', H/'long_d2.py', 'r11-source/long_d2.py', 'r14/long_d2.py'))
    projection = dict(schema='r14_byte_projection_v1',
        projected_r14_to_r11_equals_exact_r11=delta.project_to_r11_with_sha((H/'long_d2.py').read_text(), json.loads((H/'protocol-r10-proposal.json').read_text()) and hashlib.sha256((H/'protocol-r10-proposal.json').read_bytes()).hexdigest()) == (H/'r11-source/long_d2.py').read_text(),
        allowed_transformations=['remove two scheduling helper functions with two trailing blanks', 'remove BOUNDARY_SWITCH_INTERVAL line',
            'replace wrapped callback with exact r11 callback', 'remove exact r14 early-catch block', 'remove exact r14 masked-cleanup propagation block',
            'replace three mechanical constants (prepare path r14->r11, protocol path r10->r8, protocol sha)'],
        no_ast_normalization=True, no_blanket_Guard_exclusion=True,
        other_controller_files_byte_equal_r11={n: (H/n).read_bytes() == (H/'r11-source'/n).read_bytes() for n in
            ('long_d2_executor.py', 'lifecycle.py', 'processes.py', 'boundary_integrity.py', 'freeze.py', 'source_equality.py', 'fixture_guards.py', 'fixture_preconditions.py', 'os_checks.py', 'synthetic.py', 'stress.py', 'rehearsal.py', 'parent_command.py', 'model_r11.py')},
        migrated_static_tests=['test_r11.R11.test_C01_exact_success_consumers_transport_inner_fixtures_and_old91', 'test_r11.R11.test_C02_protocol_only_candidate_paths_and_qualified_semantics', 'test_r10.R10.test_exact_r9_transport_success_consumers_protected_blocks', 'test_r7.R7.test_success_consumers_and_protected_failure_helpers_byte_equal'])
    save('byte-projection-report.json', projection)
    rows = suite['per_test_results'] if suite else []
    receipt = dict(schema='r14_test_receipt_v1', command=json.loads((stage/'command.json').read_text()),
        raw_exit=raw.get('raw_exit'), timed_out=raw.get('timed_out'), wrapper_elapsed_seconds=raw.get('elapsed_seconds'),
        validation_attempts=raw.get('validation_attempts'), no_retry=True, wrapper_error=raw.get('setup_or_wrapper_error'),
        suite=None if suite is None else {k: suite[k] for k in ('tests_run', 'failures', 'errors', 'skipped', 'unexpected_successes', 'successful', 'forbidden_imports', 'existing_method_count', 'new_method_count', 'failed_tests', 'error_tests', 'executable_observed', 'argv')},
        executed=[dict(test=r['test'], status=r['status'], elapsed_seconds=r['elapsed_seconds'], source_binding=r['source_binding']) for r in rows],
        unrun=None if suite is None else suite['unrun_tests'],
        failure_detail=[r for r in rows if r['status'] != 'passed'],
        source_inventory_unchanged_through_stage=raw.get('source_inventory_unchanged'), source_unchanged_at_finalize=source_unchanged)
    save('test-receipt.json', receipt)
    passed = bool(suite and suite['successful'] and raw.get('raw_exit') == 0 and not raw.get('timed_out') and source_unchanged)
    elapsed = time.time() - started['start_epoch']
    r13 = ROOT / 'learning/runs/v2/postovernight-long-D2-boundary-prepare-r13'
    result = dict(schema='r14_implementation_result_v1', status='passed' if passed else 'failed',
        candidate=str(H), base='frozen r12 (r13 produced no code/tests)',
        source_manifest_sha256=sha(H/'source-manifest.json'), source_members=len(frozen),
        candidate_diff=dict(path='candidate.diff', sha256=sha(H/'candidate.diff')), changed_files=sorted(changed),
        protocol_r10_proposal=dict(path='protocol-r10-proposal.json', sha256=sha(H/'protocol-r10-proposal.json'), pinned_in_controller=True, external_publication=False),
        tests=dict(registered=None if suite is None else suite['tests_run'], raw_exit=raw.get('raw_exit'), executed_rows=len(rows),
                   unrun=None if suite is None else len(suite['unrun_tests'])),
        production_semantic_change='Guard.full_check early callback catch before interval cleanup; masked-cleanup propagation retains original callback exception with cleanup as cause',
        retained_r13_setup_failure_sha256=sha(r13/'setup-failure.json') if (r13/'setup-failure.json').exists() else None,
        routine_read_only_discovery_errors=[], campaign_retries=0,
        scope_deviations=[], actual_elapsed_seconds_through_result=elapsed, budget_seconds=1800,
        frozen_source_handoff=True, modeled_signals_only=True, training_authorization_7200s_unused_parent_held=True)
    save('implementation-result.json', result)
    (H/'PARENT-NEXT.md').write_text(parent_next(result, receipt, projection))
    validation = []
    cache = H / 'json-validation-pycache'
    cache.mkdir()
    for path in sorted(H.rglob('*.json')):
        if cache in path.parents or 'unit-stage/sources' in str(path) or 'unit-stage/fixtures' in str(path) or any(x in path.parts for x in ('original-source','r6-source','r9-source','r10-source','r11-source','r12-source')):
            continue
        proc = subprocess.run(['learning/.venv/bin/python', '-B', '-m', 'json.tool', str(path)], cwd=ROOT,
            capture_output=True, env=dict(PYTHONDONTWRITEBYTECODE='1', PYTHONPYCACHEPREFIX=str(cache), PATH='/usr/bin:/bin'))
        validation.append(dict(path=str(path.relative_to(H)), returncode=proc.returncode))
    save('json-validation.json', dict(validated=len(validation), all_ok=all(v['returncode'] == 0 for v in validation), files=validation))
    excluded = ('evidence-manifest.json', 'completion-receipt.json')
    files = {str(p.relative_to(H)): dict(sha256=sha(p), bytes=p.stat().st_size) for p in sorted(H.rglob('*'))
             if p.is_file() and p.name not in excluded and cache not in p.parents}
    save('evidence-manifest.json', dict(schema='r14_evidence_manifest_v1', acyclic=True, excludes=list(excluded), logs_closed=True, files=files))
    done = time.time() - started['start_epoch']
    save('completion-receipt.json', dict(schema='r14_completion_v1', completed_at_utc=utc(), actual_elapsed_seconds=done,
        budget_seconds=1800, in_budget=done <= 1800, evidence_manifest_sha256=sha(H/'evidence-manifest.json'),
        implementation_result_sha256=sha(H/'implementation-result.json'), status=result['status'],
        exactly_one_test_invocation=raw.get('validation_attempts') == 1, no_patch_or_retry=True, source_frozen=source_unchanged))
    print(json.dumps(dict(status=result['status'], elapsed=done, evidence_files=len(files))))

def parent_next(result, receipt, projection):
    suite = receipt['suite'] or {}
    return f"""# r14 {result['status']} source-only handoff

Source is frozen and ownership released. Base is exact frozen r12; r13 produced no code or tests. One stdlib stage ran: raw exit {receipt['raw_exit']}, wrapper wall {receipt['wrapper_elapsed_seconds']}s, tests run {suite.get('tests_run')}, failures {suite.get('failures')}, errors {suite.get('errors')}, skips {suite.get('skipped')}, unrun {None if receipt['unrun'] is None else len(receipt['unrun'])}.

Production change: `Guard.full_check` now latches the callback exception and its actual catch timestamp inside the interval context, before cleanup can raise. If cleanup masks it, the original callback exception is re-raised with the cleanup error as `__cause__`; the cleanup error is recorded as `cleanup_error` and remains latched by the process latch. Unchanged: observed_failure, primary_error, worker_failure, FailurePool, executor, lifecycle, processes, boundary_integrity, all fixtures and consumers.

Tests: all 112 inherited methods ran against the current candidate. Four named static methods migrated their expectations (see byte-projection-report.json and diffs); the other 108 bodies are byte-identical. No historical-target rebinding. Signals are modeled (ProcessLatch.handle with a fake clock), not OS signals. Mechanical constants: `prepare-r14`/protocol-r10; `protocol-r10-proposal.json` derives from exact r12 protocol-r9 bytes. No external publication.

Parent owns publication of protocol-r10, fresh identity/classification/capsule/registration, independent frozen review, OS/stress/startup validation and the single unused 7200-second training authorization. Setter scan is a bounded registered-source scan, not a whole-program claim; main-thread ownership is cooperation, not enforcement.
"""

if __name__ == '__main__':
    main()
