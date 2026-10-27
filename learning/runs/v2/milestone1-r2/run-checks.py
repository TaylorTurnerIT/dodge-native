"""Run M1 repair checks and extract stdout evidence without test-side writes."""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
BEFORE = json.loads((OUT / 'before.json').read_text())
OWNED = BEFORE['owned_paths']
PREFIX = 'M1_COVERAGE_JSON '


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def sources():
    paths = set(OWNED)
    paths.update(str(p.relative_to(ROOT)) for p in (ROOT / 'crates').rglob('*.rs'))
    paths.update(str(p.relative_to(ROOT)) for p in (ROOT / 'crates').rglob('Cargo.toml'))
    paths.update(['Cargo.toml', 'Cargo.lock', 'rust-toolchain.toml', '.cargo/config.toml'])
    return {p: sha(ROOT / p) for p in sorted(paths)}


def run(name, command):
    before = sources()
    started = datetime.now(timezone.utc).isoformat()
    tick = time.monotonic()
    print('START', name, flush=True)
    with (OUT / (name + '.log')).open('wb') as log:
        result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    record = {
        'command': command,
        'utc_start': started,
        'elapsed_seconds': time.monotonic() - tick,
        'exit_code': result.returncode,
        'source_sha256': before,
        'source_changed_during_check': before != sources(),
        'raw_log': name + '.log',
        'raw_log_sha256': sha(OUT / (name + '.log')),
    }
    write(name + '.json', record)
    print('END', name, 'exit', result.returncode, flush=True)
    if result.returncode or record['source_changed_during_check']:
        raise SystemExit('Check failed or source changed: ' + name)
    return record


os.chdir(ROOT)
write('environment.json', {
    'utc': datetime.now(timezone.utc).isoformat(),
    'rustc': subprocess.check_output(['rustc', '+1.97.1', '-Vv'], text=True),
    'cargo': subprocess.check_output(['cargo', '+1.97.1', '-V'], text=True),
    'platform': platform.platform(),
    'machine': platform.machine(),
    'external_pemsa_lookup': shutil.which('pemsa'),
    'external_pemsa_runtime_parity_run': False,
})
checks = {}
checks['fmt-workspace'] = run('fmt-workspace', ['cargo', '+1.97.1', 'fmt', '--all', '--', '--check'])
checks['death-pickup-fixture'] = run('death-pickup-fixture', [
    'cargo', '+1.97.1', 'test', '-p', 'dodge-core',
    'game::headless_tests::headless_death_with_freeze_or_shrink_scores_in_both_collision_orders',
    '--', '--exact', '--nocapture', '--test-threads=1',
])
checks['clippy-workspace'] = run('clippy-workspace', [
    'cargo', '+1.97.1', 'clippy', '--workspace', '--all-targets', '--all-features', '--', '-D', 'warnings',
])
checks['test-workspace'] = run('test-workspace', [
    'cargo', '+1.97.1', 'test', '--workspace', '--', '--nocapture', '--test-threads=1',
])
log = (OUT / 'test-workspace.log').read_text()
rows = [json.loads(line.split(PREFIX, 1)[1]) for line in log.splitlines() if PREFIX in line]
expected = set(re.findall(r'#\[test\]\s*fn (\w+)', (ROOT / 'crates/dodge-core/src/headless_tests.rs').read_text()))
assert len(rows) == len(expected)
assert {row['test'] for row in rows} == expected
assert all(row['schema_version'] == 1 for row in rows)
for row in rows:
    assert row['raw_frames'] == sum(row['mode_frames'].values())
    assert row['raw_frames'] == row['alive_frames'] + row['dead_frames']
    assert row['alive_game_frames'] <= row['alive_frames']
random = next(row for row in rows if row['test'] == 'headless_equivalence_100_seeds_2000_raw_frames')
assert random['raw_frames'] == 100 * 2000
assert random['case_counts']['random_seed'] == 100
assert random['alive_game_frames'] > 1000 and random['dead_frames'] > 0
catalog_row = next(row for row in rows if row['catalog'])
catalog = catalog_row['catalog']
assert [entry['index'] for entry in catalog] == list(range(39))
assert all(0 < entry['active_frames'] <= entry['raw_frames'] <= 900 for entry in catalog)
assert sum(entry['raw_frames'] for entry in catalog) == catalog_row['raw_frames']
assert sum(entry['completed_count'] for entry in catalog) > 0
cases = Counter()
for row in rows:
    cases.update(row['case_counts'])
required_minima = {
    'freeze_pickup': 3, 'shrink_pickup': 3,
    'freeze_expiration': 1, 'shrink_expiration': 1,
    'explode_pickup': 1, 'kamikaze_explosion_growth_expiration': 1,
    'death': 7, 'death_with_pickup': 4,
    'death_then_freeze_pickup': 1, 'freeze_pickup_then_death': 1,
    'death_then_shrink_pickup': 1, 'shrink_pickup_then_death': 1,
    'start_transition': 1, 'settings_roundtrip': 3,
    'render_cadence_never': 1, 'render_cadence_each_frame_twice': 1,
    'render_cadence_every_fourth_frame_twice': 1,
}
assert all(cases[name] >= count for name, count in required_minima.items())
summaries = [dict(zip(('passed', 'failed', 'ignored', 'measured', 'filtered_out'), map(int, match)))
             for match in re.findall(r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out;', log)]
assert summaries and all(row['failed'] == 0 and row['filtered_out'] == 0 for row in summaries)
counts = Counter()
for row in summaries:
    counts.update(row)
# Count actual completed fixture tests independently from coverage rows.
actual_fixtures = re.findall(r'^test game::headless_tests::(\w+) \.\.\.', log, re.M)
assert len(actual_fixtures) == len(expected) and set(actual_fixtures) == expected
write('coverage.json', {
    'schema_version': 1, 'stdout_prefix': PREFIX,
    'raw_log': 'test-workspace.log', 'raw_log_sha256': sha(OUT / 'test-workspace.log'),
    'source_sha256': checks['test-workspace']['source_sha256'],
    'definitions': {
        'raw_frames': 'One observed trajectory per test; paired full/headless executions count once. Fixture setup frames are excluded.',
        'alive_frames': 'Post-method dead flag false, including non-Game modes.',
        'alive_game_frames': 'Post-method mode Game and dead flag false; a boundary count, not survival reward.',
        'dead_frames': 'Post-method dead flag true. Random terminal residence is reported and establishes no active-pattern coverage.',
        'mode_frames': 'Post-method modes; absent keys have zero frames.',
        'catalog_active_frames': 'Catalog sweep only: active index present before an alive Game step with collision disabled. Stops on completion or 900 frames.',
        'catalog_completed_count': 'Actual active-to-none transitions observed in the catalog sweep. Not all entries must complete.',
        'case_counts': 'Named assertion-backed scenarios; render_calls keys count actual calls, not scenarios or active mechanic frames.',
        'render_cadences': 'Never, twice every frame, twice on frames 0,4,...,1996; all three logical states compare after each frame.',
    },
    'fixture_test_count_from_log': len(actual_fixtures),
    'workspace_test_summaries': summaries, 'workspace_test_totals': dict(counts),
    'random_100x2000': random, 'catalog_by_index': catalog,
    'catalog_unique_id_count': len({entry['id'] for entry in catalog}),
    'catalog_completed_total': sum(entry['completed_count'] for entry in catalog),
    'mechanic_case_counts': dict(cases), 'required_mechanic_minima': required_minima,
    'per_test': rows,
})
write('checks.json', checks)
print(json.dumps({
    'workspace_test_totals': dict(counts), 'fixture_test_count': len(actual_fixtures),
    'random': {key: random[key] for key in ['raw_frames', 'alive_frames', 'alive_game_frames', 'dead_frames', 'mode_frames']},
    'catalog_entries': len(catalog), 'catalog_completed_total': sum(entry['completed_count'] for entry in catalog),
}), flush=True)
