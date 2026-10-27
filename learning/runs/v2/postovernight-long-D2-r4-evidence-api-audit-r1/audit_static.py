"""Read-only retained-evidence audit; stdlib only, writes this directory only."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

ROOT = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
HERE = Path(__file__).resolve().parent
B = HERE.parent / 'postovernight-long-D2-prepare-r4'
R3 = HERE.parent / 'postovernight-long-D2-prepare-r3'
PINS = {}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    path = Path(path)
    PINS[str(path)] = sha(path)
    return json.loads(path.read_text())


def save(name, value):
    with (HERE / name).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def nodes(path):
    source = path.read_text()
    PINS[str(path)] = sha(path)
    lines = source.splitlines(keepends=True)
    tree = ast.parse(source)
    return {node.name: ''.join(lines[node.lineno - 1:node.end_lineno])
            for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}, tree


def main():
    result = read(B / 'implementation-result.json')
    assert sha(B / 'long_d2.py') == 'a8f1e9a979f9f1308417924cf2390e538fd01049557502f5bb1cea270df2bd1a'
    assert sha(B / 'long_d2_executor.py') == '6ab9555a7edc63a6f299cb7c3b90dc5441a53b879e0f9c3c2e12bf5c44ab8b52'
    assert sha(B / 'long-identity.json') == 'abd50a467ae9827699648c5509954f96f357725fc50cc33aa15e03bd89884340'
    assert sha(B / 'capsule-final/capsule-manifest.json') == 'f0dac0e0eff869504c7b1f17e37a1fd572b0160e8d4daf774045895e44ba2f8a'
    artifacts = read(B / 'artifact-inventory.json')
    for name, digest in artifacts.items():
        assert sha(B / name) == digest, name
    protected = read(B / 'protected-before.json')
    assert protected == read(B / 'protected-after.json')
    for name, digest in protected.items():
        assert sha(name) == digest, name
    expanded = read(B / 'expanded-inventory.json')
    prior = read(R3 / 'expanded-inventory.json')['full_pins']
    assert len(prior) == 9675
    assert len(expanded['full_pins']) == 9870
    assert all(expanded['full_pins'].get(name) == digest for name, digest in prior.items())
    for name, digest in expanded['full_pins'].items():
        assert sha(name) == digest, name
    identity = read(B / 'long-identity.json')
    canonical = json.dumps(identity, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    assert hashlib.sha256(canonical).hexdigest() == result['identity_semantic_sha256']
    legacy = identity['base_registered_identity']['sources']
    assert len(legacy) == 75
    for name, digest in legacy.items():
        assert sha(ROOT / name) == digest and sha(B / 'capsule-final' / name) == digest
    capsule = read(B / 'capsule-final/capsule-manifest.json')
    for name, digest in capsule['files'].items():
        path = B / 'capsule-final' / name
        assert sha(path) == digest and not path.stat().st_mode & 0o222
    assert not (B / 'capsule-final/capsule-manifest.json').stat().st_mode & 0o222
    for path in (B / 'capsule-final').rglob('*'):
        assert not path.stat().st_mode & 0o222 and not path.is_symlink()
    source = read(B / 'source-manifest.json')
    for name, digest in source.items():
        assert sha(B / name) == digest
        PINS[str(B / name)] = digest
    assert {str(ROOT / name): digest for name, digest in identity['controller_sources'].items()} == {
        str(B / name): digest for name, digest in source.items()}
    a, _ = nodes(R3 / 'long_d2.py')
    b, tree = nodes(B / 'long_d2.py')
    unchanged = ['Learner', 'Schedule', 'run_schedule', 'environment_kwargs', 'counter_report',
                 'compare_control', 'tree_fingerprint', 'assert_equal_tree', 'validate_long_config',
                 'expected_lease', 'assert_lease', 'check_module_origins', 'outcome_fields', 'result_code']
    assert all(a[name] == b[name] for name in unchanged)
    def worker_try(path):
        source = path.read_text(); lines = source.splitlines(keepends=True)
        worker = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == 'worker')
        block = next(node for node in worker.body if isinstance(node, ast.With)).body[0]
        return ''.join(lines[block.body[0].lineno - 1:block.body[-1].end_lineno])
    assert worker_try(R3 / 'long_d2.py') == worker_try(B / 'long_d2.py')
    unit = read(B / 'attempts/units-final/unit-result.json')
    assert unit['methods_run'] == 71 and unit['failures'] == unit['errors'] == 0 and unit['successful']
    for name, digest in unit['sources'].items():
        assert sha(B / name) == digest == sha(B / 'attempts/units-final/sources' / name)
    log = (B / 'attempts/units-final.log').read_text()
    PINS[str(B / 'attempts/units-final.log')] = sha(B / 'attempts/units-final.log')
    cases = re.findall(r'^(test_\S+) \(([^)]+)\) .*ok$', log, re.M)
    assert len(cases) == len(set(cases)) == 71
    worker_cases = list((B / 'attempts/units-final').glob('worker-*.json'))
    assert len(worker_cases) == 7
    observed_worker = {}
    for path in worker_cases:
        value = read(path); events = value['events']
        writes = [event for event in events if event['operation'] in ('checkpoint', 'persistence')]
        if path.name == 'worker-valid.json':
            assert len(writes) == 3 and all(event['deadline'] == 10 for event in writes)
        else:
            assert not writes and value['code'] == 1, path.name
        observed_worker[path.name] = dict(code=value['code'], writes=len(writes), deadline=value['learner_deadline'])
    latch_cases = list((B / 'attempts/units-final').glob('latch-*-command.json'))
    assert len(latch_cases) == 6
    all_rows = []; final_rows = []; source_scope = {}
    for name in ('matrix-01', 'matrix-final'):
        directory = B / 'attempts' / name
        matrix = read(directory / 'summary.json')
        assert matrix['OS_subprocesses'] == len(matrix['results'])
        all_rows += matrix['results']
        tested = read(directory / 'tested-sources.json')
        if name == 'matrix-final':
            final_rows = matrix['results']
            for file, digest in tested.items():
                assert sha(B / file) == digest == sha(directory / 'sources' / file)
            source_scope['after_final_matrix'] = sorted(set(source) - set(tested))
        for row in matrix['results']:
            assert row['raw_wait']['returncode'] == row['expected']
            assert os.waitstatus_to_exitcode(row['raw_wait']['raw_wait_status']) == row['expected']
            assert not row['harness_kill_required'] and not row['ML_imports']
            assert row['elapsed_seconds'] <= row['maximum_wall_seconds']
            assert all(row['positive_group_absence'].values())
            assert row['observed_acceptance'] == (row['expected'] in (0, 2))
            assert all(not event['open_writers'] for event in row['writer_checks'])
    assert len(final_rows) == 62 and len(all_rows) == 122
    assert len({tuple(row['argv']) for row in all_rows}) == 122
    assert source_scope['after_final_matrix'] == ['README.md', 'finalize_preparation.py', 'prepare_checks.py']
    for name in ('attempts/units-final-command.json', 'attempts/freeze-final-command.json',
                 'attempts/volume-final-command.json', 'executor-preflight-command.json'):
        assert read(B / name)['raw_exit'] == 0
    assert read(B / 'preparation-checks.json')['complete']
    assert read(B / 'pure-executor-preflight.json')['verified_pin_count'] == 9870
    registration = read(B / 'registration.json'); lease = read(B / 'required-lease.json')
    for path, digest in registration['pins'].items():
        assert sha(path) == digest
    assert len(lease) == 15 and lease['parent_terminal_receipt'] == identity['parent_terminal_receipt']
    assert lease['identity_sha256'] == sha(B / 'long-identity.json')
    assert lease['controller_sha256'] == sha(B / 'long_d2.py')
    assert lease['capsule_manifest_sha256'] == sha(B / 'capsule-final/capsule-manifest.json')
    groups = read(B / 'owned-groups-final.json')['groups']
    assert len(groups) == 234 and all(groups.values())
    live = subprocess.run(['ps', '-axo', 'pgid='], capture_output=True, text=True, timeout=3, check=True)
    current_groups = {int(value) for value in live.stdout.split()}
    assert not ({int(value) for value in groups} & current_groups)
    (HERE / 'targeted-worker').mkdir()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
               PYTHONPATH=str(B), LONG_D2_TEST_EVIDENCE=str(HERE / 'targeted-worker'))
    argv = [str(ROOT / 'learning/.venv/bin/python'), '-B', '-m', 'unittest', '-v', 'test_worker_ack_contract']
    start = time.monotonic()
    with (HERE / 'targeted-worker.log').open('x') as stream:
        process = subprocess.run(argv, cwd=HERE, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=20)
    assert process.returncode == 0
    targeted_log = (HERE / 'targeted-worker.log').read_text()
    assert 'Ran 6 tests' in targeted_log and targeted_log.rstrip().endswith('OK')
    save('targeted-worker-command.json', dict(argv=argv, raw_exit=process.returncode,
         elapsed_seconds=time.monotonic() - start, methods=6, ML_execution=False))
    verification = dict(status='passed_retained_evidence_and_targeted_ACK_checks',
        artifacts=len(artifacts), protected_current_immutable_files=len(protected), expanded_pins=9870,
        retained_old_pins=9675, legacy_sources=75, capsule_files=len(capsule['files']),
        source_files=len(source), unchanged_source_nodes=unchanged, worker_ML_try_byte_identical=True,
        retained_current_unit_methods=71, retained_final_OS_cases=62, all_fresh_OS_attempt_cases=122,
        retained_worker_AST_scenarios=observed_worker, unit_latch_subprocesses=6,
        targeted_ACK_methods_executed=6, targeted_ACK_API_import_errors=0,
        owned_groups_current_absence_count=len(groups), source_scope=source_scope,
        full_OS_matrix_rerun=False, ML_execution=False)
    save('verification.json', verification)
    for path, digest in PINS.items():
        assert sha(path) == digest, path
    save('input-sha256-manifest.json', dict(files=PINS, rechecked_unchanged=True,
         candidate_artifacts_and_large_protected_inventory_verified_separately=True))
    print(json.dumps({key: value for key, value in verification.items() if key != 'retained_worker_AST_scenarios'}, indent=2))


if __name__ == '__main__':
    main()
