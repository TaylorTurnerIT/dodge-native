"""Independent read-only receipt audit; never import or execute audited source."""
import ast
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
import tarfile
import traceback

ROOT = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
OUT = Path(__file__).resolve().parent
BASE = ROOT / 'learning/runs/v2/milestone2-supervisor-repair-r1'
PIN = '3dce6a14fef6754781683965ac9f470dd2e4735c09fc129f7e9d9193b1b364bb'
OLD = 'b5554b544afc304240a728cb7b81c98e08732cc0a87e783147b3a1b220391db6'
NEW = '980a9a08b5561350346a3984cf8b9fae3ec47591a8a907d9b915fdcbb428fa44'
checks = []
failures = []
counts = {}


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text())


def require(value, message):
    if not value:
        raise AssertionError(message)


def verify_hash(path, expected):
    require(path.is_file(), f'Missing file: {path}')
    actual = sha(path)
    require(actual == expected, f'Hash mismatch: {path}: {actual} != {expected}')


def check(name, action):
    try:
        detail = action()
        checks.append({'check': name, 'passed': True, 'detail': detail})
    except Exception as error:
        failures.append({'check': name, 'error': repr(error), 'traceback': traceback.format_exc()})
        checks.append({'check': name, 'passed': False})


def frozen():
    verify_hash(BASE / 'frozen-result-manifest.json', PIN)
    manifest = read(BASE / 'frozen-result-manifest.json')
    references = {
        'artifact-sha256.json': 'artifact_manifest_sha256',
        'before-manifest.json': 'before_manifest_sha256',
        'result.json': 'result_sha256',
        'source-manifest.json': 'source_manifest_sha256',
        'source.patch': 'source_patch_sha256',
        'source.tar.gz': 'source_archive_sha256',
    }
    for name, field in references.items():
        verify_hash(BASE / name, manifest[field])
    require(manifest['runner_sha256'] == NEW, 'New source pin differs')
    require(manifest['original_runner_sha256'] == OLD, 'Original source pin differs')
    counts['frozen_manifest_references'] = len(references)
    return references


def artifacts():
    declared = read(BASE / 'artifact-sha256.json')
    actual = {str(p.relative_to(BASE)) for p in BASE.rglob('*') if p.is_file()}
    require(set(declared) == actual - {'artifact-sha256.json', 'frozen-result-manifest.json'}, 'Artifact coverage differs')
    for name, expected in declared.items():
        path = BASE / name
        require(path.resolve().is_relative_to(BASE.resolve()), f'Escaping artifact path: {name}')
        verify_hash(path, expected)
    require(len(declared) == read(BASE / 'frozen-result-manifest.json')['artifact_count'] == 665, 'Artifact count differs')
    json_paths = sorted(p for p in BASE.rglob('*.json') if p.is_file())
    for path in json_paths:
        read(path)
    for line in (BASE / 'commands.jsonl').read_text().splitlines():
        json.loads(line)
    counts.update(artifact_files=len(declared), json_files_parsed=len(json_paths))
    return {'exact_file_coverage': True, 'artifact_files': len(declared), 'json_files': len(json_paths)}


def sources():
    manifest = read(BASE / 'source-manifest.json')
    before = read(BASE / 'before-manifest.json')
    require(manifest['changed_live_source'] == {'learning/scripts/v2_validate_environment.py': NEW}, 'Unexpected source changes declared')
    for name, expected in manifest['changed_live_source'].items():
        verify_hash(ROOT / name, expected)
    for name, expected in manifest['frozen_sources_sha256'].items():
        verify_hash(BASE / name, expected)
    for name, expected in before['snapshot_sha256'].items():
        verify_hash(BASE / name, expected)
    old_path = BASE / 'snapshots/learning/scripts/v2_validate_environment.py'
    new_path = BASE / 'source/learning/scripts/v2_validate_environment.py'
    verify_hash(old_path, OLD)
    verify_hash(new_path, NEW)
    rebuilt = ''.join(difflib.unified_diff(old_path.read_text().splitlines(keepends=True), new_path.read_text().splitlines(keepends=True), fromfile='a/learning/scripts/v2_validate_environment.py', tofile='b/learning/scripts/v2_validate_environment.py')).encode()
    require(rebuilt == (BASE / 'source.patch').read_bytes(), 'Patch does not exactly represent source change')
    expected_members = set(manifest['frozen_sources_sha256']) | {'source.patch', 'source-manifest.json', 'before-manifest.json', 'static-preservation-check.json'}
    with tarfile.open(BASE / 'source.tar.gz', 'r:gz') as archive:
        members = archive.getmembers()
        require(len(members) == len(expected_members) and {m.name for m in members} == expected_members, 'Archive membership differs')
        for member in members:
            require(member.isfile(), f'Non-file archive entry: {member.name}')
            require(archive.extractfile(member).read() == (BASE / member.name).read_bytes(), f'Archive bytes differ: {member.name}')
    counts.update(frozen_source_files=len(manifest['frozen_sources_sha256']), before_snapshots=len(before['snapshot_sha256']), archive_members=len(expected_members))
    return {'exact_patch_reconstruction': True, 'live_runner_sha256': NEW, 'archive_members': len(expected_members)}


def preservation():
    before = read(BASE / 'before-manifest.json')
    for name, expected in before['protected_sha256'].items():
        path = Path(name)
        require(path.is_absolute(), f'Protected path unexpectedly relative: {name}')
        verify_hash(path, expected)
    require(len(before['protected_sha256']) == 166, 'Protected count differs')
    identity_path = ROOT / 'learning/runs/v2/milestone2-integration-r2/frozen-identity.json'
    verify_hash(identity_path, '8a0065bfdf292c3112bb9026d28aae2ebbc174ab4c25c0100151eb091a5dca64')
    identity = read(identity_path)
    for name, expected in identity['binary_and_receipt_sha256'].items():
        verify_hash(Path(name), expected)
    verify_hash(Path(identity['runtime']['extension_path']), '967c7249acd52339d1818dcbe94e63ee734aea914c3497eb59a7e945a6e95583')
    compiled = {name: expected for name, expected in identity['source_sha256'].items() if name.startswith('crates/') or name in {'Cargo.toml', 'Cargo.lock', '.cargo/config.toml', 'assets/dodge.p8'}}
    for name, expected in compiled.items():
        verify_hash(ROOT / name, expected)
    verify_hash(ROOT / 'learning/.cache/v2-m2-campaign-review-r1/manifest.json', '701d153e7281ec1a97c1b648a9abe031757659e8c1d9e78a38a915c8c1b16539')
    counts.update(protected_files=len(before['protected_sha256']), old_identity_compiled_inputs=len(compiled), old_identity_binary_receipt_files=len(identity['binary_and_receipt_sha256']))
    return {'protected_files': 166, 'compiled_inputs_unchanged': len(compiled), 'old_identity_unchanged': True, 'old_build_receipt_binary_and_extension_unchanged': True}


def static_workloads():
    old_tree = ast.parse((BASE / 'snapshots/learning/scripts/v2_validate_environment.py').read_text())
    new_tree = ast.parse((BASE / 'source/learning/scripts/v2_validate_environment.py').read_text())
    def dump(node):
        return ast.dump(node, include_attributes=False)
    def functions(tree):
        return {node.name: dump(node) for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    old_funcs, new_funcs = functions(old_tree), functions(new_tree)
    changed = sorted(name for name in old_funcs if name in new_funcs and old_funcs[name] != new_funcs[name])
    added = sorted(set(new_funcs) - set(old_funcs))
    require(changed == ['campaign', 'check_identity', 'main', 'stop_owned', 'worker'], f'Unexpected changed functions: {changed}')
    require(added == ['assert_campaign_guard'] and set(old_funcs) <= set(new_funcs), 'Unexpected added/removed functions')
    old_assign = [dump(node) for node in old_tree.body if isinstance(node, (ast.Assign, ast.AnnAssign))]
    new_assign = [dump(node) for node in new_tree.body if isinstance(node, (ast.Assign, ast.AnnAssign))]
    require(old_assign == new_assign, 'Top-level assignments changed')
    must_unchanged = ['worker_trajectory', 'worker_memory', 'worker_throughput', 'read_plan', 'assert_cutoff_budget', 'assert_lease', 'load_baselines', 'parse_native_output', 'memory_plateau', 'base_config', 'audit_info', 'audit_step']
    for name in must_unchanged:
        require(old_funcs[name] == new_funcs[name], f'Workload/criterion changed: {name}')
    plan_path = ROOT / 'learning/runs/v2/milestone2-validation-harness-r1/campaign-plan.json'
    plan = read(plan_path)
    identity = read(ROOT / 'learning/runs/v2/milestone2-integration-r2/frozen-identity.json')
    verify_hash(plan_path, identity['plan_sha256'])
    require(plan['campaign_wall_seconds'] == 1800 and plan['receipt_reserve_seconds'] == 600, 'Budget changed')
    require(plan['observed_worker_peak_rss_limit_bytes'] == 6442450944, 'RSS limit changed')
    stages = {stage['name']: stage for stage in plan['stages']}
    walls = {name: stage['wall_seconds'] for name, stage in stages.items()}
    require(walls == {'native_parity': 900, 'trajectory': 120, 'memory': 600, 'throughput': 120}, 'Phase limits differ')
    mem = stages['memory']
    require((mem['warmup_step_calls'], mem['measured_step_calls'], mem['plateau_median_growth_max_bytes']) == (5000, 100000, 67108864), 'Memory workload changed')
    require(plan['effective_reserved_ranges'] == [[0xB0000000, 0xB00003E7], [0xD0000000, 0xD000007F], [0xE0000000, 0xE00003E7]], 'Seed reservations changed')
    require(plan['automatic_retries'] == 0 and plan['sequential_stop_first_failure'] is True, 'Retry/failure policy changed')
    require(stages['native_parity']['episodes_per_difficulty'] == 1000 and stages['native_parity']['difficulties'] == [2, 3], 'Native campaign count differs')
    counts.update(unchanged_functions=sum(old_funcs[n] == new_funcs[n] for n in old_funcs), changed_functions=len(changed))
    return {'unchanged_workload_functions': must_unchanged, 'changed_functions': changed, 'added_functions': added, 'module_assignments_unchanged': True, 'campaign_seconds': 1800, 'receipt_reserve_seconds': 600, 'phase_seconds': walls, 'RSS_limit_bytes': 6442450944, 'memory_warmup_calls': 5000, 'memory_measured_calls': 100000, 'plateau_limit_bytes': 67108864, 'reservations': plan['effective_reserved_ranges']}


def test_receipts():
    records = [json.loads(line) for line in (BASE / 'commands.jsonl').read_text().splitlines()]
    require(len(records) == 3, 'Unexpected command count')
    expected = {'repaired-pure-r1': (37, 0), 'existing-nine-r1': (9, 0), 'original-discrimination-r1': (12, 1)}
    parsed = {}
    for label, (count, exit_code) in expected.items():
        receipt = read(BASE / 'checks' / (label + '.json'))
        require(receipt in records, f'Command ledger missing receipt: {label}')
        log_path = ROOT / receipt['log']
        verify_hash(log_path, receipt['log_sha256'])
        for name, digest in receipt['test_sources_sha256'].items():
            verify_hash(ROOT / name, digest)
        command = receipt['command']
        index = command.index('python/.venv/bin/python')
        require(command[index + 1:index + 4] == ['-B', '-W', 'error'], f'Test flags differ: {label}')
        require(receipt['exit_code'] == exit_code and receipt['pure_only'] is True and receipt['campaign_executed'] is False, f'Exit/scope differs: {label}')
        log = log_path.read_text()
        require(re.search(r'Ran ' + str(count) + r' tests in [0-9.]+s', log), f'Test count differs: {label}')
        outcomes = re.findall(r'^(test_\S+.*?) \.\.\. (ok|FAIL|ERROR)$', log, flags=re.M)
        require(len(outcomes) == count, f'Per-test log count differs: {label}')
        outcome_counts = {kind: sum(status == kind for _, status in outcomes) for kind in ['ok', 'FAIL', 'ERROR']}
        if exit_code == 0:
            require(outcome_counts == {'ok': count, 'FAIL': 0, 'ERROR': 0} and log.rstrip().endswith('OK'), f'Not all tests passed: {label}')
        else:
            require(outcome_counts == {'ok': 0, 'FAIL': 10, 'ERROR': 2}, 'Original discrimination result differs')
            require(log.rstrip().endswith('FAILED (failures=10, errors=2)'), 'Original result summary differs')
            original_arg = 'SUPERVISOR_UNDER_TEST=learning/runs/v2/milestone2-supervisor-repair-r1/snapshots/learning/scripts/v2_validate_environment.py'
            require(original_arg in command, 'Original source selector absent')
            require('ProcessLookupError' in log and 'snapshots/learning/scripts/v2_validate_environment.py' in log, 'Original cleanup trace absent')
            require('was not raised' in log or 'not raised' in log, 'Original semantic discrimination absent')
        parsed[label] = {'tests': count, 'exit_code': exit_code, 'outcomes': outcome_counts, 'log_sha256': receipt['log_sha256']}
    loader = (BASE / 'test_supervisor.py').read_text()
    require('os.environ.get("SUPERVISOR_UNDER_TEST"' in loader, 'Original source selection unsupported')
    require('"expected_identity_hash" in inspect.signature(H.check_identity).parameters' in loader, 'Old-signature adaptation absent')
    require('patch.object(H.subprocess, "Popen"' in loader and 'patch.object(H.os, "killpg"' in loader, 'Mock boundary absent')
    counts.update(new_mocked_tests_passed=37, existing_mocked_tests_passed=9, original_controls=12, original_expected_assertion_failures=10, original_expected_cleanup_errors=2)
    return parsed


for name, action in [('frozen_manifest', frozen), ('exact_artifact_coverage_and_json', artifacts), ('sources_archive_patch', sources), ('protected_files_and_compiled_identity', preservation), ('unchanged_workloads_budgets_reservations', static_workloads), ('retained_mocked_test_receipts', test_receipts)]:
    check(name, action)

audit = {
    'schema': 'm2_supervisor_repair_receipt_audit_v1',
    'created_at_utc': datetime.now(timezone.utc).isoformat(),
    'status': 'passed_with_provenance_caveat' if not failures else 'failed',
    'scope': 'Independent byte/hash, archive, AST, and retained-log verification only. No audited project code was imported or executed.',
    'checker_sha256': sha(Path(__file__)),
    'target_frozen_manifest': str((BASE / 'frozen-result-manifest.json').relative_to(ROOT)),
    'target_frozen_manifest_sha256': PIN,
    'verified_counts': counts,
    'checks': checks,
    'failures': failures,
    'findings': [{'severity': 'informational', 'id': 'original_control_receipt_live_source_field', 'detail': 'Original-discrimination receipt source_sha256 and its retained -source.py capture the repaired live runner, while the command explicitly selects the separately pinned original snapshot via SUPERVISOR_UNDER_TEST. The test loader honors that variable and original-path tracebacks support the executed-source claim. Do not treat this source_sha256 field as the original source identity; use the command plus original snapshot pin.'}],
    'limitations': [
        'Retained mocked tests establish guard behavior only; this audit did not rerun them.',
        'No native executable, extension, project source, training, evaluation, network operation, or subagent was run.',
        'No full M2 campaign qualification or teacher-training readiness is established.',
        'The parent must reconcile new build receipts/identity and complete independent frozen-source review before any campaign.',
        'Preservation verifies current bytes against recorded pre-repair pins; it does not prove historical execution or eliminate cooperative-check races.',
    ],
}
path = OUT / 'audit.json'
with path.open('x') as stream:
    json.dump(audit, stream, indent=2, sort_keys=True, allow_nan=False)
    stream.write('\n')
print(json.dumps({'status': audit['status'], 'audit': str(path.relative_to(ROOT)), 'audit_sha256': sha(path), 'counts': counts, 'failed_checks': failures}, indent=2))
