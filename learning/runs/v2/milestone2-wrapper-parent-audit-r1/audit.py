"""Independent retained-receipt audit; never runs native simulation or edits inputs."""
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import ast
import hashlib
import json
import math
import re
import tarfile
import traceback

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
WRAPPER = ROOT / 'learning/runs/v2/milestone2-wrapper-r1'
HASHES = {}
CHECKS = []

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def verify(path, expected, category):
    actual = sha(path)
    assert actual == expected, (category, str(path), expected, actual)
    HASHES.setdefault(category, {})[str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)] = actual

def load(path):
    return json.loads(path.read_text())

def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]

def check(name, data=True):
    CHECKS.append({'name': name, 'result': data})

def parse_prefixed(path, prefix):
    return [json.loads(line.split(prefix, 1)[1]) for line in path.read_text().splitlines() if prefix in line]

def audit():
    source = load(WRAPPER / 'source-manifest.json')
    evidence = load(WRAPPER / 'evidence-manifest.json')
    inputs = load(WRAPPER / 'input-manifest.json')
    verification = load(WRAPPER / 'verification.json')
    commands = rows(WRAPPER / 'commands.jsonl')
    for path, digest in evidence['files'].items():
        verify(WRAPPER / path, digest, 'wrapper_evidence')
    for path, digest in source['source_sha256'].items():
        verify(ROOT / path, digest, 'final_source')
    for path, digest in source['frozen_input_pins_unchanged'].items():
        verify(ROOT / path, digest, 'frozen_pin')
    assert source['frozen_input_pins_unchanged'] == inputs['frozen_pins']
    for path, digest in inputs['files'].items():
        verify(WRAPPER / 'inputs' / path, digest, 'archived_initial_input')
    core = load(ROOT / 'learning/runs/v2/milestone2-core-r1/source-manifest.json')
    assert len(core['source_sha256']) == 7
    for path, digest in core['source_sha256'].items():
        assert source['frozen_input_pins_unchanged'][path] == digest
        verify(ROOT / path, digest, 'accepted_core')
    verify(WRAPPER / source['patch'], source['patch_sha256'], 'wrapper_patch_archive')
    verify(WRAPPER / source['source_archive'], source['source_archive_sha256'], 'wrapper_patch_archive')
    verify(WRAPPER / 'source-manifest.json', verification['source_manifest_sha256'], 'verification_references')
    with tarfile.open(WRAPPER / 'source.tar.gz', 'r:gz') as archive:
        names = [member.name for member in archive if member.isfile()]
        assert set(names) == set(source['source_sha256']) and len(names) == len(set(names))
        for path, digest in source['source_sha256'].items():
            assert hashlib.sha256(archive.extractfile(path).read()).hexdigest() == digest, path
    check('archive_matches_all_final_sources', len(names))
    fixture = (ROOT / 'learning/runs/v2/milestone2-math-r1/fixtures.rs').read_bytes()
    promoted = (ROOT / 'crates/dodge-rl-env/tests/primitives.rs').read_bytes()
    fixture_body = fixture[fixture.index(b'use geometry::{'):]
    promoted_body = promoted[promoted.index(b'use geometry::{'):]
    assert fixture_body == promoted_body
    assert hashlib.sha256(fixture_body).hexdigest() == source['promoted_fixture_body_sha256'] == source['original_fixture_body_sha256']
    promotion = load(ROOT / 'learning/runs/v2-orchestration/m2-test-promotion.json')
    verify(Path(promotion['policy_source']), promotion['policy_sha256'], 'original_policy')
    verify(Path(promotion['test_policy']), promotion['policy_sha256'], 'original_policy')
    check('all_35_primitive_bodies_and_original_policy_unchanged')
    parsed = 0
    for path in WRAPPER.rglob('*'):
        if path.suffix == '.json': load(path); parsed += 1
        elif path.suffix == '.jsonl': rows(path); parsed += 1
    check('retained_json_and_jsonl_parse', parsed)
    for command in commands:
        verify(WRAPPER / command['log'], command['log_sha256'], 'command_logs')
    qualified = {}
    for name in ('test', 'fmt', 'clippy', 'replay'):
        command = [r for r in commands if r['name'] == name and r['exit_code'] == 0][-1]
        assert command['source_changed'] is False
        for path, digest in source['source_sha256'].items():
            assert command['source_sha256'][path] == digest, (name, path)
        assert {k: v for k, v in command.items() if k != 'source_sha256'} == verification['checks'][name]
        qualified[name] = command
    check('all_final_sources_match_successful_check_receipts', list(qualified))
    test_counts = re.findall(r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', (WRAPPER / qualified['test']['log']).read_text())
    assert test_counts == [('33', '0', '1'), ('35', '0', '0'), ('0', '0', '0')]
    assert re.findall(r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', (WRAPPER / qualified['replay']['log']).read_text()) == [('1', '0', '0')]
    check('ordinary_crate_test_count', {'unit_passed': 33, 'promoted_primitives_passed': 35, 'total_passed': 68, 'replay_ignored_in_ordinary_run': 1, 'release_replay_separate': 1, 'prior_core_86_tests_rerun': False})
    failures = load(WRAPPER / 'failure-ledger.json')
    actual_failures = [{k: r[k] for k in ('name', 'command', 'exit_code', 'log', 'source_changed')} for r in commands if r['exit_code']]
    assert failures['failed_command_attempts'] == actual_failures and len(actual_failures) == 3
    assert sum(c['name'] == 'replay' for c in commands) == 1
    assert sum(c['name'] == 'trajectory' for c in commands) == 1
    assert all(c['elapsed_seconds'] <= c['timeout_seconds'] for c in commands)
    check('failures_preserved_and_native_campaign_attempts_once', {'failed_command_receipts': 3, 'replay_attempts': 1, 'trajectory_native_attempts': 1, 'parser_failure_log_retained': (WRAPPER / 'trajectory-checker-failure.log').is_file()})
    mirror = ROOT / 'learning/runs/v2/milestone0-campaign-r2/native-results'
    mirror_manifest = load(mirror / 'copy-manifest.json')
    for name in ('baselines/episodes.jsonl', 'baselines/manifest.json'):
        item = mirror_manifest['files'][name]
        verify(mirror / name, item['sha256'], 'original_baseline')
        verify(Path(item['original']), item['sha256'], 'original_baseline')
    selection = load(WRAPPER / 'baseline-selection.json')
    verify(ROOT / selection['source'], selection['source_sha256'], 'original_baseline')
    original = rows(ROOT / selection['source'])
    assert len(original) == 3000
    selected = [r for r in original if 0 <= r['episode_index'] <= 9]
    assert len(selected) == 30 and selected == selection['episodes']
    baseline_manifest = load(mirror / 'baselines/manifest.json')
    assert baseline_manifest['action_repeat'] == 4 and baseline_manifest['max_raw_gameplay_frames'] == 18000
    replay = load(WRAPPER / 'baseline-replay.json')
    logged_replay = parse_prefixed(WRAPPER / 'replay-01.log', 'REPLAY_EPISODE ')
    assert logged_replay == replay['episodes'] and len(logged_replay) == 30
    logged_total = parse_prefixed(WRAPPER / 'replay-01.log', 'REPLAY_TOTAL ')
    assert logged_total == [replay['total']]
    patterns_text = next(line.split('REPLAY_PATTERN_FRAMES ', 1)[1] for line in (WRAPPER / 'replay-01.log').read_text().splitlines() if 'REPLAY_PATTERN_FRAMES ' in line)
    patterns = {str(k): v for k, v in ast.literal_eval(patterns_text).items()}
    assert patterns == replay['active_pattern_frames_by_catalog_id']
    assert len(patterns) == 22 and sum(patterns.values()) == replay['active_pattern_frames'] == 28395
    lookup = {(r['policy'], r['seed']): r for r in selected}
    fields = {'score_raw_fixed': lambda r: r['scores']['final_score_raw_fixed'], 'raw_frames': lambda r: r['gameplay_native_frames'], 'alive_frames': lambda r: r['raw_survival_frames'], 'terminated': lambda r: r['death'], 'truncated': lambda r: r['cap_truncation'], 'death_events': lambda r: r['frame_event_counts_enemy_spawn_collision_death_pattern_active_terminal'][2], 'full_state_hash': lambda r: r['final_state_hash']}
    for row in logged_replay:
        prior = lookup[(row['policy'], row['seed'])]
        assert row['seed'] == 0xB0000000 + prior['episode_index']
        assert prior['startup_native_frames_excluded'] == 13
        assert prior['native_config'] == baseline_manifest['native_config']
        assert prior['episode_status'] == 'complete' and not prior['run_deadline_truncation']
        for field, extract in fields.items(): assert row[field] == extract(prior), (row['policy'], row['seed'], field)
        expected_reward = row['score_raw_fixed'] / 65536 + 0.01 * row['alive_frames'] - 5 * row['terminated']
        assert math.isclose(row['objective_return'], expected_reward, abs_tol=1e-10)
        assert math.isclose(row['objective_return'], prior['score_survival_objective_return'], abs_tol=1e-10)
    assert Counter(r['policy'] for r in logged_replay) == Counter({'random': 10, 'neutral': 10, 'nearest_lethal_aabb_safe_powerup': 10})
    assert sum(r['raw_frames'] for r in logged_replay) == replay['total']['raw_frames_per_path'] == 69326
    for policy in replay['per_policy']:
        selected_rows = [r for r in logged_replay if r['policy'] == policy]
        summary = {'episodes': len(selected_rows), 'raw_frames': sum(r['raw_frames'] for r in selected_rows), 'alive_frames': sum(r['alive_frames'] for r in selected_rows), 'score_sum': sum(r['score_raw_fixed'] for r in selected_rows) / 65536, 'deaths': sum(r['terminated'] for r in selected_rows), 'caps': sum(r['truncated'] for r in selected_rows)}
        assert summary == replay['per_policy'][policy]
    check('30_replay_rows_match_original_M0_not_expected_rs', {'original_rows': 3000, 'matched_rows': 30, 'raw_frames_per_path': 69326, 'catalog_ids': 22, 'active_pattern_frames': 28395, 'all_30_terminated': all(r['terminated'] for r in logged_replay), 'fields': list(fields) + ['objective_return', 'startup_frames', 'native_config', 'policy', 'seed']})
    trajectory = load(WRAPPER / 'trajectory.json')
    assert parse_prefixed(WRAPPER / 'trajectory-02.log', 'TRAJECTORY ') == [trajectory['results']]
    vectors = parse_prefixed(WRAPPER / 'trajectory-02.log', 'SEED_REFERENCE ')
    assert vectors == trajectory['seed_vectors'] and len(vectors) == 16
    mask = (1 << 64) - 1
    def mix(z):
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & mask
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & mask
        return z ^ (z >> 31)
    for row in vectors:
        base = mix(row['run'] ^ 0x444F4447455F5632) ^ mix((row['slot'] + 0x9E3779B97F4A7C15) & mask) ^ mix((row['episode'] + 0xD1B54A32D192ED03) & mask)
        counter = 0
        while True:
            actual = mix(base ^ mix((counter + 0x94D049BB133111EB) & mask)) >> 32
            if not 0xB0000000 <= actual <= 0xB00003E7: break
            counter += 1
        assert actual == row['actual_seed'] and counter == row['counter']
    trajectory_input = load(WRAPPER / 'trajectory-inputs.json')
    verify(WRAPPER / 'trajectory_probe.rs', trajectory_input['source_sha256'], 'trajectory_identity')
    verify(Path(trajectory_input['rlib']), trajectory_input['rlib_sha256'], 'trajectory_identity')
    trajectory_command = next(r for r in commands if r['name'] == 'trajectory')
    assert trajectory_command['exit_code'] == 0 and not trajectory_command['source_changed']
    check('trajectory_summary_and16_seed_vectors_independently_verified', trajectory['results'])
    for path, digest in source['source_sha256'].items(): verify(ROOT / path, digest, 'final_source_after_audit')
    return {'status': 'passed', 'findings': [], 'limitations': ['Receipt audit only: no tests, compiler, native simulation, or benchmark rerun.', 'Native equality assertions are source-backed retained execution evidence, not reconstructed full per-frame logs.', 'Original baseline final-state fingerprints verify only retained terminal states; per-frame parity relies on executed test assertions.', 'Wrapper normal tests passed 68 plus one separate release replay; earlier 86 core tests were not rerun here.', 'Supplemental thread/chunk run has no cap endings, only short populated episodes; its source compares public owned outputs and partial resets.', 'Full 1000-episode D2+D3 heuristic parity, PyO3/GIL/NumPy behavior, 100000-step memory and actual throughput remain unvalidated.']}

if __name__ == '__main__':
    started = datetime.now(timezone.utc).isoformat()
    try:
        result = audit()
    except BaseException as error:
        result = {'status': 'failed', 'error': repr(error), 'traceback': traceback.format_exc()}
    result.update(started_at_utc=started, completed_at_utc=datetime.now(timezone.utc).isoformat(), checks=CHECKS, verified_hashes=HASHES, counts={k: len(v) for k, v in HASHES.items()}, checker_sha256=sha(Path(__file__)))
    target = OUT / 'audit.json'
    assert not target.exists(), 'Never overwrite an audit attempt'
    target.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': result['status'], 'audit': str(target.relative_to(ROOT)), 'sha256': sha(target), 'counts': result['counts'], 'error': result.get('error')}, indent=2))
