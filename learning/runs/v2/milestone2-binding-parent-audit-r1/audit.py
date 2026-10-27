from __future__ import annotations

import ast
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
EVIDENCE = ROOT / 'learning/runs/v2/milestone2-binding-r1'
OUT = ROOT / 'learning/runs/v2/milestone2-binding-parent-audit-r1'


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(name: str):
    return json.loads((EVIDENCE / name).read_text())


def checked_hash(path: Path, expected: str, label: str):
    actual = digest(path)
    assert actual == expected, (label, str(path), expected, actual)
    return actual


def archive_entries(name: str):
    with tarfile.open(EVIDENCE / name, 'r:gz') as archive:
        entries = {}
        for member in archive.getmembers():
            if not member.isfile():
                continue
            assert member.name not in entries, member.name
            contents = archive.extractfile(member).read()
            entries[member.name] = hashlib.sha256(contents).hexdigest()
        return entries


started = datetime.datetime.now(datetime.timezone.utc).isoformat()
counts = {}
checks = []
verified = {}
findings = []

inventory = read_json('artifact-inventory.json')['files']
verified['evidence'] = {}
for name, entry in inventory.items():
    path = EVIDENCE / name
    verified['evidence'][name] = checked_hash(path, entry['sha256'], 'evidence')
    assert path.stat().st_size == entry['bytes'], name
counts['evidence_files'] = len(inventory)
actual = {str(p.relative_to(EVIDENCE)) for p in EVIDENCE.rglob('*') if p.is_file()}
assert actual - {'artifact-inventory.json'} == set(inventory), sorted(actual ^ set(inventory))
checks.append({'name': 'evidence_inventory_covers_all_files_except_itself', 'result': True})

source = read_json('source-manifest.json')
owned = read_json('owned-source-manifest.json')
inputs = read_json('input-manifest.json')
for group, entries in [('final_source', source), ('owned_source', owned)]:
    verified[group] = {}
    for name, sha in entries.items():
        verified[group][name] = checked_hash(ROOT / name, sha, group)
counts['final_source'] = len(source)
counts['owned_source'] = len(owned)
assert set(owned) <= set(source)
assert archive_entries('source-final.tar.gz') == source
assert archive_entries('inputs.tar.gz') == inputs
counts['archived_initial_inputs'] = len(inputs)
checks.append({'name': 'archives_equal_declared_input_and_final_manifests', 'result': True})

frozen = {name: sha for name, sha in inputs.items()
          if name not in owned and name != 'learning/runs/v2-orchestration/state.json'}
verified['frozen_inputs'] = {}
for name, sha in frozen.items():
    verified['frozen_inputs'][name] = checked_hash(ROOT / name, sha, 'frozen')
counts['frozen_unowned_static_inputs'] = len(frozen)
declared_frozen = read_json('frozen-input-audit.json')
assert not declared_frozen['unowned_source_changes']
assert declared_frozen['frozen_unowned_files_checked'] == len(frozen) + 1
assert set(declared_frozen['externally_changed_dynamic_inputs']) == {'learning/runs/v2-orchestration/state.json'}
core = json.loads((ROOT / 'learning/runs/v2/milestone2-core-r1/source-manifest.json').read_text())['source_sha256']
for name, sha in core.items():
    assert source[name] == sha
    checked_hash(ROOT / name, sha, 'accepted_core')
counts['accepted_core'] = len(core)
acceptance_name = 'learning/runs/v2-orchestration/milestone2-wrapper-acceptance-r2.json'
checked_hash(ROOT / acceptance_name, '38dd2aadf8d6a78e5e9511957157356baea125dcb69e2e9293de3ccbb7648319', 'parent_acceptance')
for name in ['crates/dodge-rl-env/src/features.rs', 'crates/dodge-rl-env/src/geometry.rs',
             'crates/dodge-rl-env/src/raster.rs', 'crates/dodge-rl-env/src/tests.rs',
             'crates/dodge-rl-env/tests/primitives.rs', 'crates/dodge-rl-env/tests/support/m0_policy.rs']:
    assert inputs[name] == source[name], name
checks.append({'name': 'accepted_core_math_features_tests_and_policy_unchanged', 'result': True})

commands = [json.loads(line) for line in (EVIDENCE / 'commands.jsonl').read_text().splitlines()]
assert len({r['label'] for r in commands}) == len(commands)
verified['command_logs'] = {}
for record in commands:
    name = record['label'] + '.log'
    verified['command_logs'][name] = checked_hash(EVIDENCE / name, record['log_sha256'], 'command_log')
counts['command_logs'] = len(commands)
labels = ['build-python-final-r2', 'pytest-final-r2', 'rust-default-final-r2',
          'fmt-final-r2', 'clippy-final-r2', 'wheel-final-r2']
for label in labels:
    record = next(r for r in commands if r['label'] == label)
    assert record['exit_code'] == 0, label
    for name, sha in record['source_sha256'].items():
        assert source[name] == sha, (label, name)
    assert set(owned) <= set(record['source_sha256']), label
checks.append({'name': 'final_six_successful_commands_match_final_owned_sources', 'result': labels})

rust_log = (EVIDENCE / 'rust-default-final-r2.log').read_text()
assert '41 passed; 0 failed; 1 ignored' in rust_log
assert '35 passed; 0 failed; 0 ignored' in rust_log
unit_lines = [line for line in rust_log.splitlines() if line.startswith('test ') and line.endswith(' ... ok')]
assert len(unit_lines) == 76, len(unit_lines)
assert sum('seed_extension_tests::' in line for line in unit_lines) == 5
assert sum('seed::reservation_tests::' in line for line in unit_lines) == 2
xml = ET.fromstring((EVIDENCE / 'pytest-final-r2.xml').read_text())
cases = xml.findall('.//testcase')
assert len(cases) == 68, len(cases)
assert not xml.findall('.//failure') and not xml.findall('.//error') and not xml.findall('.//skipped')
pytest_log = (EVIDENCE / 'pytest-final-r2.log').read_text()
assert '68 passed' in pytest_log
result = read_json('result.json')
assert result['tests']['rust_unit_passed'] == 41 and result['tests']['rust_primitive_passed'] == 35
assert result['tests']['python_passed'] == 68
assert not result['tests']['whole_workspace_tests_executed']
assert not result['long_campaigns_executed'] and not result['teacher_or_student_work']
checks.append({'name': 'independent_log_and_junit_counts', 'result': {
    'rust_unit_passed': 41, 'rust_primitive_passed': 35, 'rust_total_passed': 76,
    'rust_ignored_replay': 1, 'python_cases_passed': 68, 'new_seed_tests': 7,
    'whole_workspace_rust_tests_not_claimed': True}})

gil = read_json('gil-proof.json')
observed = [ast.literal_eval(text) for text in re.findall(r"\{'gil_call_ns':[^}]+\}", pytest_log)]
assert observed == list(gil['witnesses'].values())
for name, witness in gil['witnesses'].items():
    assert witness['gil_call_ns'] > 0 and witness['witness_after_start_ns'] > 0
    assert (witness['witness_before_return_ns'] < 0) == (name == 'held_gil_negative_control')
    assert witness['witness_after_start_ns'] + witness['witness_before_return_ns'] == witness['gil_call_ns']
checks.append({'name': 'gil_receipt_matches_six_retained_witness_records', 'result': True})

identity = read_json('installed-identity.json')
expected_extension = '967c7249acd52339d1818dcbe94e63ee734aea914c3497eb59a7e945a6e95583'
assert identity['extension_sha256'] == result['extension_sha256'] == expected_extension
verified['binary'] = {}
for name in [identity['extension_import_path'], identity['extension_archive_path']]:
    path = Path(name)
    if not path.is_absolute():
        path = ROOT / path
    verified['binary'][str(path)] = checked_hash(path, expected_extension, 'extension')
for wheel in identity['wheels']:
    path = ROOT / wheel['path']
    checked_hash(path, wheel['sha256'], 'wheel')
    with zipfile.ZipFile(path) as archive:
        extension_names = [n for n in archive.namelist() if n.endswith('.so')]
        assert extension_names == [wheel['extension_member']]
        assert hashlib.sha256(archive.read(wheel['extension_member'])).hexdigest() == expected_extension
        assert archive.read('dodge_rl/__init__.py') == (ROOT / 'python/dodge_rl/__init__.py').read_bytes()
    counts['matching_wheels'] = len(identity['wheels'])
assert result['cargo_lock_sha256'] == source['Cargo.lock'] == identity['cargo_lock_sha256']
checked_hash(EVIDENCE / 'source-final.tar.gz', result['source_archive_sha256'], 'result_archive')
checked_hash(EVIDENCE / 'owned-changes.patch', result['owned_patch_sha256'], 'result_patch')
checks.append({'name': 'installed_archived_wheel_extension_and_package_bytes_match', 'result': True})

prior_source = read_json('pre-comment-correction/source-manifest.json')
prior_owned = read_json('pre-comment-correction/owned-source-manifest.json')
prior_result = read_json('pre-comment-correction/result.json')
prior_identity = read_json('pre-comment-correction/installed-identity.json')
assert archive_entries('pre-comment-correction/source-final.tar.gz') == prior_source
assert all(prior_source[name] == sha for name, sha in prior_owned.items())
checked_hash(EVIDENCE / 'pre-comment-correction/source-final.tar.gz', prior_result['source_archive_sha256'], 'prior_archive')
checked_hash(EVIDENCE / 'pre-comment-correction/owned-changes.patch', prior_result['owned_patch_sha256'], 'prior_patch')
prior_extension = EVIDENCE / 'pre-comment-correction/binary/_native.cpython-312-darwin.so'
checked_hash(prior_extension, prior_identity['extension_sha256'], 'prior_extension')
assert prior_result['extension_sha256'] == prior_identity['extension_sha256']
for wheel in prior_identity['wheels']:
    path = EVIDENCE / 'pre-comment-correction/wheels' / Path(wheel['path']).name
    checked_hash(path, wheel['sha256'], 'prior_wheel')
    with zipfile.ZipFile(path) as archive:
        assert hashlib.sha256(archive.read(wheel['extension_member'])).hexdigest() == prior_identity['extension_sha256']
counts['archived_pre_comment_sources'] = len(prior_source)
checks.append({'name': 'retained_pre_comment_source_archive_binary_and_wheel_match_their_own_receipts', 'result': True})

final_python = {str(p.relative_to(ROOT)) for base in ('python/dodge_rl', 'python/tests')
                for p in (ROOT / base).rglob('*.py')}
crate_sources = {str(p.relative_to(ROOT)) for p in (ROOT / 'crates/dodge-rl-env').rglob('*.rs')}
assert final_python <= set(source), sorted(final_python - set(source))
assert crate_sources <= set(source), sorted(crate_sources - set(source))
counts['current_python_source_files_covered'] = len(final_python)
counts['current_wrapper_rust_files_covered'] = len(crate_sources)
checks.append({'name': 'untracked_package_tests_and_wrapper_source_coverage', 'result': True})

# These read-only comparisons establish current tracked identity, not historical
# build-time identity. They must not be folded into the original build receipt.
missing_build_inputs = ['.cargo/config.toml', 'crates/dodge-core/Cargo.toml', 'assets/dodge.p8']
supplementary = {}
for name in missing_build_inputs:
    assert name not in source and name not in inputs
    data = subprocess.check_output(['git', 'show', 'HEAD:' + name], cwd=ROOT)
    current = (ROOT / name).read_bytes()
    assert current == data, name
    supplementary[name] = {'current_sha256': hashlib.sha256(current).hexdigest(),
                           'current_matches_HEAD': True, 'missing_from_original_binding_manifest_and_archive': True}
findings.append({'id': 'binding_build_input_manifest_scope', 'severity': 'P2',
                 'scope': 'provenance_gap_not_runtime_defect',
                 'detail': 'Binding source/input archives omit compile-consumed .cargo/config.toml, crates/dodge-core/Cargo.toml, and assets/dodge.p8. Core build.rs reads the cartridge to generate gfx data.',
                 'current_tracked_identity': supplementary,
                 'resolution_needed': 'Parent must add a separate complete build-input manifest before campaign freeze. Current HEAD equality does not prove recorded build-time identity; do not rewrite original receipts.',
                 'parent_context': 'Parent reports its independent code-review capsule already contains .cargo/config.toml and core Cargo.toml; cartridge still needs a supplementary parent pin.'})

failures = read_json('failure-ledger.json')
assert failures['evidence_limitations'] == result['evidence_limitations']
assert any('overwritten' in s for s in result['evidence_limitations'])
assert (EVIDENCE / 'freeze-r1.log').is_file() and (EVIDENCE / 'input-audit-r1.log').is_file()
checks.append({'name': 'failed_logs_and_intermediate_binary_limitation_retained', 'result': True})

report = {'status': 'declared_receipts_verified_with_build_input_scope_finding',
          'started_at_utc': started, 'completed_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'checker_sha256': digest(Path(__file__)), 'counts': counts, 'checks': checks,
          'findings': findings, 'verified_hashes': verified,
          'limitations': ['No compiler, native simulation, extension import, tests, or benchmark rerun.',
                          'Final test/build identities are source-backed retained execution receipts, not a fresh independent build.',
                          'Historical intermediate extension binaries were overwritten before hashing; hashes and archives cannot be reconstructed.',
                          'Current tracked build-input equality is distinct from recorded build-time identity.',
                          '76 default crate Rust tests and 68 Python tests are verified; no whole-workspace Rust test count is transferred.',
                          'GIL records verify bounded witnesses and negative control, not throughput, memory behavior, or free-threaded Python.',
                          'Full 1000 paired D2+D3 heuristic episodes, 100k post-warmup memory, actual throughput, and teacher qualification remain pending.']}
(OUT / 'audit.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
print(json.dumps({'status': report['status'], 'counts': counts, 'findings': [f['id'] for f in findings],
                  'audit_sha256': digest(OUT / 'audit.json')}, indent=2))
