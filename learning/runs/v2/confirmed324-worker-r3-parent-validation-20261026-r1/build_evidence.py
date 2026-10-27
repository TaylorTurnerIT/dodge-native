"""Owned stdlib source preparation/freeze; verify mode performs read-only checks."""
import ast
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
R2 = ROOT / 'learning/runs/v2/confirmed324-paired-worker-contract-repair-sol-20261026-r2'
R5 = ('attempt_claim.py', 'driver_binding.py', 'fingerprints.py', 'rng_reference.py', 'transition.py')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def write(name, value):
    with (HERE / name).open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def inputs():
    manifest = read(HERE / 'input-manifest.json')
    assert (HERE / 'input-manifest.json').read_bytes() == (R2 / 'input-manifest.json').read_bytes()
    assert len(manifest['pins']) == 58
    for name, digest in manifest['pins'].items():
        assert sha(ROOT / name) == digest, name
    preflight = read(HERE / 'preflight.json')
    for name, digest in preflight['frozen_predecessor_and_review_files'].items():
        assert sha(ROOT / name) == digest, name
    for name in R5:
        assert (HERE / name).read_bytes() == (R2 / name).read_bytes(), name
    assert not any((HERE / 'empty-pycache').iterdir())
    assert not any((HERE / 'tmp').iterdir())
    return dict(original_input_pins_unchanged=58,
        frozen_predecessor_and_review_files_unchanged=len(preflight['frozen_predecessor_and_review_files']),
        R5_copies_byte_identical=list(R5), cache_empty=True, temporary_outputs_removed=True)


def source_names():
    return sorted([p.name for p in HERE.glob('*.py')] +
        ['README.md', 'input-manifest.json', 'interpreter.json'] +
        [p.name for p in HERE.glob('registration-template-*.json')])


def exact_diff():
    index, result = [], ''
    for name in source_names():
        new, old = HERE / name, R2 / name
        before = old.read_text().splitlines(keepends=True) if old.exists() else []
        after = new.read_text().splitlines(keepends=True)
        index.append(dict(file=name, baseline=str(old) if old.exists() else None,
            baseline_sha256=sha(old) if old.exists() else None,
            sha256=sha(new), unchanged=before == after))
        result += ''.join(difflib.unified_diff(before, after,
            fromfile=str(old.relative_to(ROOT)) if old.exists() else '/dev/null',
            tofile=str(new.relative_to(ROOT))))
    return index, result


def verify_source():
    manifest = read(HERE / 'source-manifest.json')
    assert set(manifest['files']) == set(source_names()) | {'diff-index.json', 'exact-diff.patch'}
    for name, digest in manifest['files'].items():
        assert sha(HERE / name) == digest, name
    index, patch = exact_diff()
    assert read(HERE / 'diff-index.json') == index
    assert (HERE / 'exact-diff.patch').read_bytes() == patch.encode()
    for path in HERE.glob('*.py'):
        ast.parse(path.read_bytes(), filename=str(path))
    templates = [read(path) for path in HERE.glob('registration-template-*.json')]
    assert len(templates) == 6
    assert all(row['status'] == 'parent_review_required_not_launchable' and
               row['source_manifest_sha256'] == '{{PARENT_PIN_FINAL_SOURCE_MANIFEST}}' and
               row['input_manifest_sha256'] == sha(HERE / 'input-manifest.json') for row in templates)
    return dict(source_members_verified=len(manifest['files']),
                python_sources_parsed=len(list(HERE.glob('*.py'))),
                exact_R2_diff_verified=True, inert_templates_verified=6)


def prepare():
    inputs()
    import build_registration
    import contracts as c
    for replica in (1, 2, 3):
        for label, arm in zip(('A', 'B'), c.ARMS, strict=True):
            write(f'registration-template-replica-{replica}-{label}.json',
                  build_registration.template(replica, arm))
    index, patch = exact_diff()
    write('diff-index.json', index)
    with (HERE / 'exact-diff.patch').open('x') as stream:
        stream.write(patch)
    write('source-manifest.json', dict(schema='owned_paired_worker_source_manifest_v3',
        authority='content inventory only; parent acceptance required',
        files={name: sha(HERE / name) for name in source_names()+['diff-index.json', 'exact-diff.patch']}))
    print(json.dumps(verify_source(), sort_keys=True))


def freeze(log_name, exit_code):
    checks = {**inputs(), **verify_source()}
    summary = read(HERE / 'fake-test-summary.json')
    assert exit_code == 0 and summary['tests_run'] == 43
    assert summary['errors'] == summary['failures'] == 0
    assert summary['unexpected_runtime_import_requests'] == []
    assert summary['executable'] == str(ROOT / 'python/.venv/bin/python')
    assert summary['pycache_prefix'] == str(HERE / 'empty-pycache')
    with (HERE / 'tests.log').open('xb') as stream:
        stream.write((HERE / log_name).read_bytes())
    preflight = read(HERE / 'preflight.json')
    ledger = preflight['mutable_ledger_outside_immutable_hashset']
    checks.update(mutable_ledger=dict(path=ledger, outside_immutable_hashset=True,
        preflight_sha256=preflight['mutable_ledger_observed_sha256'],
        postflight_sha256=sha(ROOT / ledger),
        policy='Concurrent parent changes permitted; never edited by this repair.'))
    write('postflight.json', checks)
    write('receipt.json', dict(schema='confirmed324_worker_event_source_repair_receipt_v3',
        at_utc=datetime.now(timezone.utc).isoformat(), owned_directory=str(HERE),
        status='source_frozen_pending_parent_acceptance_not_launched', repaired_finding='R2-01/P2',
        parent_accepted=False, runtime_qualified=False,
        R2_source_manifest_sha256=sha(R2 / 'source-manifest.json'),
        source_manifest_sha256=sha(HERE / 'source-manifest.json'),
        input_manifest_sha256=sha(HERE / 'input-manifest.json'),
        exact_R2_diff_sha256=sha(HERE / 'exact-diff.patch'),
        interpreter=read(HERE / 'interpreter.json'),
        validation=dict(original_controls=37, focused_event_controls=6, tests=summary,
            final_exit_code=exit_code, tests_log='tests.log', tests_log_sha256=sha(HERE / 'tests.log'),
            attempt_logs=[dict(path=p.name, sha256=sha(p)) for p in sorted(HERE.glob('tests-pass*.log'))],
            postflight=checks),
        event_contract='One synchronous worker-owned callback immediately after collection; detached event payloads; each record flush/fsync before PPO; exceptions propagate; return ignored; no retries or post-success replay.',
        adapter_boundary='Disposable constructor bootstrap precedes the R5 claim. Only unchanged R5 restores accepted state, exactly once after the durable claim; reseeding and LR override follow.',
        scope=dict(pairs=3, claim_limit='exploratory n=3; no formal methods claim',
            phase_parent=324, cumulative_parent=372, phase_updates=[325,384], cumulative_updates=[373,432],
            updates_per_arm=60, constant_lr=3e-5, linear_lr=[3e-5,1e-5],
            curriculum='untouched', selection=False),
        actual_execution=dict(real_torch_numpy_native_mps_imports=False,
            accepted_checkpoint_deserialization=False, accepted_model_or_environment_construction=False,
            training_evaluation_study_cohort_or_campaign_launch=False,
            claim_scope='owned synthetic R5/stdlib controls only',
            parent_runtime_checkpoint_ledger_lease_marker_reference_or_curriculum_edits=False,
            subdelegation=False, commit_or_push=False),
        remaining_parent_gates=[
            'Independent source acceptance and supervision/watchdog/cancellation/cleanup integration',
            'Resource calibration/caps and six final registrations with final source pins and launch gates',
            'Real loaded runtime/class/backend and accepted model/Adam/RNG restoration qualification',
            'Native seed readbacks, rollout/PPO/diagnostics, true candidate serialization and terminal audit',
            'Separate full normal-start evaluation and selection; no launch authority from this output']))
    write('artifact-manifest.json', dict(schema='confirmed324_worker_event_frozen_artifact_manifest_v3',
        parent_acceptance=False, policy='Read-only handoff. No edits or reruns in place; use a successor.',
        excluded_empty_directories=['empty-pycache','tmp'],
        files={str(p.relative_to(HERE)):sha(p) for p in sorted(HERE.rglob('*')) if p.is_file()}))
    verify()


def verify():
    checks = {**inputs(), **verify_source()}
    manifest = read(HERE / 'artifact-manifest.json')
    assert {str(p.relative_to(HERE)) for p in HERE.rglob('*') if p.is_file()} == set(manifest['files']) | {'artifact-manifest.json'}
    for name, digest in manifest['files'].items():
        assert sha(HERE / name) == digest, name
    assert read(HERE / 'receipt.json')['source_manifest_sha256'] == sha(HERE / 'source-manifest.json')
    print(json.dumps(dict(**checks, artifact_members_verified=len(manifest['files']),
                         source_manifest_sha256=sha(HERE / 'source-manifest.json')), sort_keys=True))


if __name__ == '__main__':
    assert sys.dont_write_bytecode and sys.pycache_prefix == str(HERE / 'empty-pycache')
    mode = sys.argv[1]
    if mode == 'prepare':
        prepare()
    elif mode == 'freeze':
        freeze(sys.argv[2], int(sys.argv[3]))
    elif mode == 'verify':
        verify()
    else:
        raise ValueError('expected prepare, freeze or verify')
