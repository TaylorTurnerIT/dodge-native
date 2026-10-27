"""Reviewer-owned source/hash/AST/JSON inspection; never imports target code."""
import ast
import hashlib
import json
import os
from pathlib import Path

OWN = Path(__file__).resolve().parent
ROOT = OWN.parents[3]
RUNS = ROOT / 'learning/runs/v2'
TARGET = RUNS / 'progressive1000-supervisor-race-repair-sol-20261026-r2'
ORIGINAL = RUNS / 'progressive1000-existing-supervisor-binding-sol-20261026-r1'
PREVIOUS = RUNS / 'progressive1000-final-supervisor-registration-review-sol-20261026-r1'
WORKER = RUNS / 'progressive1000-shared-runtime-staticmethod-repair-sol-20261026-r2'
ASSEMBLY = RUNS / 'progressive1000-matched-run-parent-assembly-20261026-r1'


def read(path):
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate key: ' + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_bytes(), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            result.update(block)
    return result.hexdigest()


def save(name, value):
    path = OWN / name
    assert path.parent == OWN
    with path.open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def states(registrations):
    result = {}
    for item in registrations:
        reg = read(item['registration'])
        cache = Path(reg['import_policy']['pycache_prefix'])
        result[reg['run_id']] = {
            'output_lexists': os.path.lexists(reg['output']),
            'attempt_claim_lexists': os.path.lexists(reg['attempt_claim_path']),
            'launch_marker_lexists': os.path.lexists(reg['launch_marker_path']),
            'launch_approval_lexists': os.path.lexists(Path(item['registration']).parent / 'launch-approval.json'),
            'cache_is_dir': cache.is_dir(),
            'cache_members': sorted(p.name for p in cache.iterdir()) if cache.is_dir() else None,
        }
    result['target_dispatch_lexists'] = os.path.lexists(TARGET / 'dispatch')
    return result


def function_map(path):
    tree = ast.parse(Path(path).read_bytes(), filename=str(path))
    return {node.name: ast.dump(node, include_attributes=False)
            for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def inspect():
    checks = []
    pins = {}

    def pin(path, expected=None, label=None):
        path = Path(path)
        actual = sha(path)
        pins[str(path)] = actual
        if expected is not None:
            checks.append(dict(label=label or str(path), expected=expected, actual=actual, matches=actual == expected))
        return actual

    # These manifests are decoded as identity metadata. Members are byte-hashed;
    # expected outcome tables and checkpoint bytes are never decoded.
    for base, expected in (
        (TARGET, 'df65bb051c9232497d223dc4a73c41e90af9556323d6a16b0aa378724931b12a'),
        (ORIGINAL, '8351fabd8a54685007e74a050200f2e25ac19e2e6ae3a4b11cf98535ef4c3d4f'),
        (WORKER, 'be7b8b3c9ef90d1e820df417f54863b6943fb746c451105078923916f19a04a2'),
    ):
        pin(base / 'source-manifest.json', expected)
        for rel, expected_member in read(base / 'source-manifest.json')['files'].items():
            member = base / rel
            assert member.resolve().is_relative_to(base) and not member.is_symlink()
            pin(member, expected_member)

    for name in ('runtime-manifest.json', 'input-manifest.json'):
        manifest = read(WORKER / name)
        pin(WORKER / name)
        if name == 'runtime-manifest.json':
            for rel, digest in manifest['files'].items():
                pin(WORKER / 'runtime' / rel, digest)
        else:
            for path, digest in manifest['pins'].items():
                pin(path, digest)

    inherited = read(TARGET / 'preservation-before.json')['pins']
    for path, digest in inherited.items():
        pin(path, digest)
    for base in (TARGET, ORIGINAL, PREVIOUS):
        for path in base.rglob('*'):
            if path.is_file():
                pin(path)

    binding = read(TARGET / 'dependency-binding.json')
    pin(binding['inventory_path'], binding['inventory_sha256'])
    pin(binding['registration_path'], binding['registration_sha256'])
    inventory = read(binding['inventory_path'])
    old = read(binding['registration_path'])
    for path, item in inventory['pins'].items():
        pin(path, item['sha256'])
        checks.append(dict(label='inherited dependency inventory/registration: ' + path,
                           matches=old['pins'].get(path) == item['sha256']))

    index_path = ASSEMBLY / 'final-registration-index.json'
    index_sha = pin(index_path, '7144e7ab3852eac4307e64fecf884d1dc8b21a769f48267d065cf679b3bedaef')
    registrations = read(index_path)['registrations']
    previous = read(PREVIOUS / 'receipt.json')
    checks.append(dict(label='six final registrations equal prior review',
                       matches=registrations == previous['reviewed']['registrations']))
    template_checks = []
    registration_summaries = []
    for item in registrations:
        pin(item['registration'], item['sha256'])
        reg = read(item['registration'])
        template_path = TARGET / 'templates' / (item['run_id'] + '.envelope.json')
        template = read(template_path)
        pin(template_path)
        expected_code_pins = {str(TARGET / rel): digest for rel, digest in read(TARGET / 'source-manifest.json')['files'].items()
                              if rel in ('binding.py', 'observe.py', 'execute_once.py', 'terminal.py', 'dependency-binding.json')}
        row = dict(run_id=item['run_id'], final_registration_path=template['registration'] == item['registration'],
                   final_registration_sha=template['registration_sha256'] == item['sha256'],
                   inert=template['status'] == 'DRAFT_NO_LAUNCH' and template['started'] is None and template['launch_approval_sha256'] is None,
                   owned_control=template['control'] == str(TARGET / 'dispatch' / item['run_id']),
                   exact_R2_pins=all(template['pins'].get(path) == digest for path, digest in expected_code_pins.items()),
                   manifest_pin=template['pins'].get(str(TARGET / 'source-manifest.json')) == sha(TARGET / 'source-manifest.json'),
                   launch_and_source_acceptance_distinct=template['launch_approval'] != template['source_acceptance'],
                   launch_approval_path=template['launch_approval'] == str(Path(item['registration']).parent / 'launch-approval.json'),
                   controls_outside_worker_output=not Path(template['control']).is_relative_to(Path(reg['output']))
                        and not Path(reg['output']).is_relative_to(Path(template['control'])),
                   cancel_outside_worker_output=not Path(template['cancel_path']).is_relative_to(Path(reg['output'])))
        template_checks.append(row)
        for path, digest in template['pins'].items():
            pin(path, digest)
        pin(template['source_acceptance'], template['source_acceptance_sha256'])
        pin(reg['state_path'])  # Opaque bytes only; do not inspect live state or lease content.
        pin(reg['reference']['receipt_path'], reg['reference']['receipt_sha256'])
        pin(reg['reference_approval']['path'], reg['reference_approval']['sha256'])
        registration_summaries.append({key: reg[key] for key in
            ('run_id', 'pair_id', 'replica', 'arm', 'backend', 'curriculum_enabled', 'limits', 'ppo', 'schedule',
             'parent_checkpoint_sha256', 'source_manifest_sha256', 'runtime_manifest_sha256')})
    pin(ASSEMBLY / 'prelaunch-evidence-scope.json', '333d3aada22ddf2959b155160e92d97bb162b95247a1cdac16e6bad089885d6c')
    # Its previously resolved interpretation is supplied in the brief and R1 review.
    # Hash only here; do not reopen historical evidence or study outcome content.

    parsed = []
    for base in (TARGET, ORIGINAL):
        for rel in read(base / 'source-manifest.json')['files']:
            if rel.endswith('.py'):
                ast.parse((base / rel).read_bytes(), filename=str(base / rel))
                parsed.append(str(base / rel))
    for name in ('binding.py', 'terminal.py', 'execute_once.py', 'observe.py'):
        functions = function_map(TARGET / name)
        assert functions

    old_tests = function_map(ORIGINAL / 'tests/test_bindings.py')
    new_tests = function_map(TARGET / 'tests/test_bindings.py')
    claimed = read(TARGET / 'control-reuse.json')
    unchanged = sorted(name for name in old_tests if name.startswith('test_') and old_tests[name] == new_tests.get(name))
    adapted = sorted(name for name in old_tests if name.startswith('test_') and old_tests[name] != new_tests.get(name))
    reuse_ok = unchanged == sorted(claimed['unchanged_tests']) and adapted == sorted(claimed['adapted_tests'])
    fake = read(TARGET / 'test-receipt.json')
    real = read(TARGET / 'real-test-receipt.json')
    real_summary = {key: real[key] for key in ('tests_run', 'successful', 'raw_exit', 'errors', 'failures',
        'elapsed_seconds', 'cpu_seconds_bound', 'wall_seconds_bound', 'remaining_owned_handles', 'scope')}
    real_summary['direct_helpers'] = [process for case in real['evidence'] for process in case['processes']]
    real_summary['descendant_reaps'] = [case['descendant_reap'] for case in real['evidence'] if 'descendant_reap' in case]
    real_summary['reviewer_replayed'] = False

    result = dict(schema='progressive1000_R2_source_hash_AST_JSON_review_checks_v1',
        checks=checks, failed_checks=[row for row in checks if not row['matches']],
        source_manifests={str(base): sha(base / 'source-manifest.json') for base in (TARGET, ORIGINAL, WORKER)},
        final_registration_index_sha256=index_sha, dependency_pins_checked=len(inventory['pins']),
        ast_parsed=parsed, terminal_unchanged=(TARGET / 'terminal.py').read_bytes() == (ORIGINAL / 'terminal.py').read_bytes(),
        dependency_binding_unchanged=(TARGET / 'dependency-binding.json').read_bytes() == (ORIGINAL / 'dependency-binding.json').read_bytes(),
        binding_functions_unchanged_except_save=all(value == function_map(ORIGINAL / 'binding.py').get(name)
            for name, value in function_map(TARGET / 'binding.py').items() if name != 'save'),
        templates=template_checks, registrations=registration_summaries,
        control_reuse=dict(unchanged=unchanged, adapted=adapted, matches_claim=reuse_ok),
        author_fake_receipt=fake, author_real_receipt=real_summary,
        reviewer_tests_run=0, target_imports=False, source_execution=False, process_probes=0,
        scope='Named source and identity metadata only; byte hashes for dependencies, checkpoints, state and outcome tables.')
    save('input-pin-checks.json', result)
    save('preservation-before.json', dict(pins=pins, path_states=states(registrations),
        scope='Named immutable pins and registered path states only; no whole-workspace snapshot.'))
    print(json.dumps(dict(pin_count=len(pins), failed_checks=len(result['failed_checks']),
        ast_parsed=len(parsed), templates=len(template_checks), template_failures=[row for row in template_checks if not all(v for k,v in row.items() if k != 'run_id')],
        dependency_pins=len(inventory['pins']), terminal_unchanged=result['terminal_unchanged'],
        dependency_binding_unchanged=result['dependency_binding_unchanged'], control_reuse=result['control_reuse']), sort_keys=True))


def finish():
    before = read(OWN / 'preservation-before.json')
    drift = []
    for path, digest in before['pins'].items():
        actual = sha(path) if Path(path).is_file() else None
        if actual != digest:
            drift.append(dict(path=path, before=digest, after=actual))
    after_states = states(read(ASSEMBLY / 'final-registration-index.json')['registrations'])
    save('preservation-after.json', dict(pins_checked=len(before['pins']), drift=drift,
        registered_path_states_unchanged=before['path_states'] == after_states,
        path_states=after_states, scope=before['scope']))
    print(json.dumps(dict(pins_checked=len(before['pins']), drift=drift,
                         path_states_unchanged=before['path_states'] == after_states)))


if __name__ == '__main__':
    import sys
    {'inspect': inspect, 'finish': finish}[sys.argv[1]]()
