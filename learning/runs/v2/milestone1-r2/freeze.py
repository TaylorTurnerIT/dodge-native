"""Freeze the completed M1 r2 repair and its exact-source evidence."""
from pathlib import Path
from datetime import datetime, timezone
import difflib
import hashlib
import io
import json
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
BEFORE = json.loads((OUT / 'before.json').read_text())
OWNED = BEFORE['owned_paths']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


checks = json.loads((OUT / 'checks.json').read_text())
coverage = json.loads((OUT / 'coverage.json').read_text())
owned_hashes = {p: sha(ROOT / p) for p in OWNED}
for name, check in checks.items():
    assert check['exit_code'] == 0 and not check['source_changed_during_check'], name
    assert all(check['source_sha256'][p] == value for p, value in owned_hashes.items()), name
    assert all(sha(ROOT / p) == value for p, value in check['source_sha256'].items()), name
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == BEFORE['head']
changed_owned = [p for p in OWNED if owned_hashes[p] != BEFORE['owned_sha256'][p]]
assert changed_owned == ['crates/dodge-core/src/headless_tests.rs']
assert all(sha(ROOT / p) == value for p, value in BEFORE['immutable_r1_sha256'].items())

repair = ''
full = ''
for p in OWNED:
    after = (ROOT / p).read_text().splitlines(True)
    old = (OUT / 'before' / p).read_text().splitlines(True)
    repair += ''.join(difflib.unified_diff(old, after, fromfile='a/' + p, tofile='b/' + p))
    prior = subprocess.run(['git', 'show', 'HEAD:' + p], cwd=ROOT, capture_output=True)
    prior_lines = prior.stdout.decode().splitlines(True) if prior.returncode == 0 else []
    full += ''.join(difflib.unified_diff(prior_lines, after, fromfile='a/' + p if prior_lines else '/dev/null', tofile='b/' + p))
(OUT / 'repair.patch').write_text(repair)
(OUT / 'milestone1.patch').write_text(full)
diff_check = subprocess.run(['git', 'diff', '--check', '--', *OWNED], cwd=ROOT, capture_output=True, text=True)
(OUT / 'diff-check.log').write_text(diff_check.stdout + diff_check.stderr)
assert diff_check.returncode == 0
assert not any(line.rstrip() != line for line in (ROOT / 'crates/dodge-core/src/headless_tests.rs').read_text().splitlines())
with tarfile.open(OUT / 'source.tar.gz', 'w:gz') as archive:
    for p in OWNED:
        archive.add(ROOT / p, arcname=p)
with tarfile.open(OUT / 'source.tar.gz', 'r:gz') as archive:
    assert sorted(archive.getnames()) == sorted(OWNED)
    for p in OWNED:
        assert hashlib.sha256(archive.extractfile(p).read()).hexdigest() == owned_hashes[p]

# Record concurrent shared-worktree changes without editing or reverting them.
changed_preexisting = {
    p: {'before_sha256': value, 'current_sha256': sha(ROOT / p) if (ROOT / p).is_file() else None}
    for p, value in BEFORE['visible_checkout_sha256'].items()
    if not (ROOT / p).is_file() or sha(ROOT / p) != value
}
concurrent = [p for p in changed_preexisting if p not in changed_owned]
write('scope-observation.json', {
    'utc': datetime.now(timezone.utc).isoformat(),
    'agent_source_edits': changed_owned,
    'agent_artifact_writes': str(OUT.relative_to(ROOT)),
    'changed_preexisting_paths': changed_preexisting,
    'concurrent_out_of_scope_changes': concurrent,
    'r1_artifacts_changed': [],
    'note': 'Only headless_tests.rs and new milestone1-r2 artifacts were written by this repair. Concurrent changes elsewhere were neither edited nor reverted.',
})
status = subprocess.check_output(['git', 'status', '--short'], cwd=ROOT, text=True)
(OUT / 'git-status-final.log').write_text(status)
inputs = ['docs/SPEC_PRIVILEGED_VIT_RL.md', 'docs/implementation-plan-v2.md', 'docs/v2-source-audit.md']
write('source-manifest.json', {
    'utc': datetime.now(timezone.utc).isoformat(), 'head': BEFORE['head'],
    'owned_paths': OWNED, 'source_sha256': owned_hashes,
    'changed_owned_paths_from_r1': changed_owned,
    'runtime_and_example_source_unchanged_from_r1': [p for p in OWNED if p not in changed_owned],
    'workspace_check_source_sha256': checks['test-workspace']['source_sha256'],
    'input_sha256_at_freeze': {p: sha(ROOT / p) for p in inputs},
    'input_sha256_at_start': {p: BEFORE['visible_checkout_sha256'][p] for p in inputs},
    'repair_patch_sha256': sha(OUT / 'repair.patch'),
    'full_m1_patch_sha256': sha(OUT / 'milestone1.patch'),
    'archive_sha256': sha(OUT / 'source.tar.gz'),
    'concurrent_out_of_scope_changes': concurrent, 'status': status,
})
old = ROOT / 'learning/runs/v2/milestone1-r1'
benchmark = json.loads((old / 'benchmark.json').read_text())
benchmark_receipt = json.loads((old / 'benchmark-receipt.json').read_text())
write('benchmark-provenance.json', {
    'rerun': False, 'reason': 'Only test source changed; runtime and benchmark example match r1 exactly.',
    'measurement_source_identity': benchmark_receipt['source_sha256'],
    'original_benchmark': str((old / 'benchmark.json').relative_to(ROOT)),
    'original_benchmark_sha256': sha(old / 'benchmark.json'),
    'original_benchmark_receipt': str((old / 'benchmark-receipt.json').relative_to(ROOT)),
    'original_benchmark_receipt_sha256': sha(old / 'benchmark-receipt.json'),
    'original_source_manifest': str((old / 'source-manifest.json').relative_to(ROOT)),
    'original_source_manifest_sha256': sha(old / 'source-manifest.json'),
    'scope': '64 matched short alive, death-stopped episodes; 16,142 raw frames per round; five rounds. Modified full path versus headless. Not a pattern-heavy throughput claim or a new r2 measurement.',
    'episodes': benchmark['episodes'], 'deaths': benchmark['deaths'],
    'raw_frames_per_round': benchmark['raw_frames_per_round'], 'rounds': benchmark['rounds'],
    'original_headless_speedup': benchmark['headless_speedup'],
})
write('verification.json', {
    'milestone': 'v2 M1 acceptance repair r2',
    'utc': datetime.now(timezone.utc).isoformat(),
    'status': 'Locally verified and frozen; ready for parent free Beam review.',
    'changed_source_paths': changed_owned,
    'source_manifest': 'source-manifest.json', 'source_archive': 'source.tar.gz',
    'repair_diff_from_r1': 'repair.patch', 'full_m1_diff_from_HEAD': 'milestone1.patch',
    'coverage_receipt': 'coverage.json', 'artifact_hashes': 'artifact-sha256.json',
    'checks': checks,
    'workspace_test_totals': coverage['workspace_test_totals'],
    'headless_fixture_test_count_from_log': coverage['fixture_test_count_from_log'],
    'random_coverage': coverage['random_100x2000'],
    'catalog_coverage': {
        'entry_count': len(coverage['catalog_by_index']),
        'all_indices_positive_active_frames': all(row['active_frames'] > 0 for row in coverage['catalog_by_index']),
        'active_frames': sum(row['active_frames'] for row in coverage['catalog_by_index']),
        'completed_count': coverage['catalog_completed_total'],
        'unique_ids_observed': coverage['catalog_unique_id_count'],
        'all_entries_completed_is_not_an_acceptance_requirement': True,
    },
    'mechanic_case_counts': coverage['mechanic_case_counts'],
    'semantics_verified': [
        'Full/headless live FullState parity after every paired step; only physical_screen excluded. Config, frame audio, returned reward, score, delta, mode, flags, input, and RNG compare.',
        'Four co-located normal lethal plus freeze/shrink pickup cases cover both list orders: exact PicoFixed score delta ONE while dead, raw score 4.5, legacy reward ZERO, no survival increment.',
        'Death saves ceil highscore before subsequent pickups; pickup-first saves 5, lethal-first saves 4. A following dead frame gives no repeated score, reward, or survival credit.',
        'Existing death/retry, powerup expiration, explode/kamikaze, frozen charging, static/moving collision, settings, configurations, legacy capture fingerprints, and post-method render assertions remain.',
        'Render cadence compares 2,000 raw frames for never, twice every frame, and twice every fourth frame. Rendering preserves current and future logical state and RNG.',
        'Each successful fixture emits one M1_COVERAGE_JSON line; ordinary Rust tests perform no filesystem evidence writes.',
    ],
    'runtime_source_unchanged_from_r1': True,
    'benchmark': {'rerun': False, 'provenance': 'benchmark-provenance.json', 'new_r2_throughput_claim': False},
    'external_pemsa_runtime_parity_run': False,
    'r1_artifacts_unchanged': True,
    'diff_check_exit_code': diff_check.returncode,
    'owned_archive_hashes_verified': True,
    'current_source_hashes_match_checked_source': True,
    'concurrent_out_of_scope_changes': concurrent,
    'limits': [
        'Native Rust equivalence and local Rust tests only; no external Pemsa runtime parity.',
        'Random dead residence is reported separately and is not active gameplay or catalog coverage.',
        'Catalog sweep is bounded to 900 frames per index with collision disabled. It reports actual completions without imposing all-pattern completion.',
        'Synthetic smooth fixture remains synthetic; no catalog smooth-support claim.',
        'No PPO, student, M2, publishing, commits, PRs, nested agents, reviews, or benchmark campaigns were performed.',
    ],
})
# Validate every evidence JSON before computing the artifact manifest.
json_paths = sorted(OUT.rglob('*.json'))
validation = []
for path in json_paths:
    if path.name == 'artifact-sha256.json':
        continue
    with open('/dev/null', 'w') as sink:
        result = subprocess.run(['python3', '-m', 'json.tool', str(path)], stdout=sink)
    assert result.returncode == 0, path
    validation.append(str(path.relative_to(OUT)))
(OUT / 'json-validation.log').write_text('\n'.join('PASS python3 -m json.tool ' + p for p in validation) + '\n')
write('artifact-sha256.json', {
    'algorithm': 'sha256', 'excludes': ['artifact-sha256.json'],
    'files': {str(p.relative_to(OUT)): sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name != 'artifact-sha256.json'},
})
with open('/dev/null', 'w') as sink:
    assert subprocess.run(['python3', '-m', 'json.tool', str(OUT / 'artifact-sha256.json')], stdout=sink).returncode == 0
assert owned_hashes == {p: sha(ROOT / p) for p in OWNED}
print(json.dumps({
    'artifact_manifest_sha256': sha(OUT / 'artifact-sha256.json'),
    'source_sha256': owned_hashes,
    'workspace_tests': coverage['workspace_test_totals'],
    'fixture_tests': coverage['fixture_test_count_from_log'],
    'concurrent_out_of_scope_changes': concurrent,
}))
