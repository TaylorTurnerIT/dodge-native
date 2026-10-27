"""Read-only terminal ranking audit; never imports the game or starts evaluation."""
import hashlib
import importlib.util
import json
import math
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REG_SHA = '5f617d7c412b0ff177e6ae05be39c2eb179c1a8dfa73981a27537f691de46d59'
SELECTOR = ROOT.parent / 'selection-cap-proof-repair-luna-20261026-r3/selection.py'
SELECTOR_SHA = 'd35614e5f3d65836f0b3943622701322297bc201a0d07a2e547f5bd2a2b64e66'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def pinned(path, expected):
    require(sha(path) == expected, 'hash drift: ' + str(path))


def audit(supervisor_exit):
    require(type(supervisor_exit) is int and supervisor_exit == 0, 'raw supervisor exit failed or unavailable')
    registration = ROOT / 'registration-final.json'
    pinned(registration, REG_SHA)
    reg = read(registration)
    outer_path = ROOT / 'outputs/ranking.json.outer-receipt.json'
    require(outer_path.is_file(), 'terminal receipt absent; do not inspect quality')
    outer = read(outer_path)
    expected = {'schema': 'expanded_eval_outer_receipt_v1', 'run_id': reg['run_id'],
                'registration_sha256': REG_SHA, 'raw_exit_code': 0, 'stop_reason': None,
                'stage': 'ranking', 'candidate_update': 348, 'cohort': 'ranking',
                'process_group_absent': True, 'process_group_remaining': []}
    require(all(outer.get(k) == v for k, v in expected.items()), 'outer lifecycle/identity failed')
    require(0 < outer['elapsed_seconds'] <= reg['limits']['outer_seconds'], 'wall bound failed')
    marker = read(reg['one_shot_marker'])
    heartbeat = read(ROOT / 'outputs/worker-heartbeat.json')
    for item in (marker, heartbeat):
        require(item['run_id'] == reg['run_id'] and item['registration_sha256'] == REG_SHA,
                'marker/heartbeat identity drift')
    pids = {marker['pid'], heartbeat['pid']}
    require(all(type(pid) is int and pid > 1 for pid in pids) and len(pids) == 2, 'invalid process identities')
    proc = subprocess.run(['ps', '-axo', 'pid=,ppid=,pgid=,rss='], check=True,
                          text=True, capture_output=True, timeout=5)
    rows = [[int(v) for v in line.split()] for line in proc.stdout.splitlines() if line.strip()]
    require(not any(row[0] in pids or row[1] in pids or row[2] in pids for row in rows),
            'owned PID, child, or process group remains')
    require(heartbeat['phase'] == 'runtime' and heartbeat['driver_initialized'] is True,
            'final runtime heartbeat invalid')
    for key, cap in (('rss_bytes', 'RSS_bytes'), ('mps_driver_bytes', 'MPS_driver_bytes')):
        require(type(heartbeat[key]) is int and 0 < heartbeat[key] <= reg['limits'][cap], 'memory bound failed')
    ledger_path = Path(reg['state_path'])
    require(sha(ledger_path) == read(ROOT / 'continuation-work.json')['live_ledger_sha256'], 'live ledger changed during campaign')
    ledger = read(ledger_path)
    require(ledger.get('active_inference_diagnostic') == reg['expected_lease'], 'exact lease missing')
    require(all(ledger.get(k) in (None, False) for k in ('active_long', 'active_long_campaign', 'active_inference')),
            'conflicting lease')
    require(not Path(reg['cancel_path']).exists(), 'cancellation exists')
    cache = Path(reg['runtime']['pycache_prefix'])
    require(cache.is_dir() and not any(cache.iterdir()), 'cache absent or nonempty')
    pinned(ROOT.parents[3] / 'README.md', 'be478416b33c772a7ff9c28f2c974f767c205f7df77bcf7346ab36133d384652')
    for name in ('launcher', 'worker', 'evaluator'):
        pinned(reg['source'][name + '_path'], reg['source'][name + '_sha256'])
    for relative, pin in reg['runtime']['member_sha256'].items():
        pinned(Path(reg['runtime']['root']) / relative, pin)
    for candidate in reg['candidates'].values():
        pinned(candidate['checkpoint_path'], candidate['checkpoint_sha256'])
        pinned(candidate['source_receipt_path'], candidate['source_receipt_sha256'])
    for cohort in reg['cohorts'].values():
        pinned(cohort['manifest_path'], cohort['manifest_sha256'])
    for review in reg['review_records']:
        pinned(review['path'], review['sha256'])
    pinned(reg['benchmark_measurement']['receipt_path'], reg['benchmark_measurement']['receipt_sha256'])
    artifacts = outer['output_artifacts']
    require(len({item['path'] for item in artifacts}) == len(artifacts), 'duplicate output bindings')
    for item in artifacts:
        pinned(item['path'], item['sha256'])
        require(Path(item['path']).stat().st_size == item['bytes'], 'output size drift')
    # Quality opens only after every terminal lifecycle and input-integrity gate above passed.
    pinned(SELECTOR, SELECTOR_SHA)
    spec = importlib.util.spec_from_file_location('parent_selection_adapter', SELECTOR)
    selector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(selector)
    summary_path = ROOT / 'outputs/ranking.json'
    bindings = {u: (str(ROOT / f'outputs/ranking-candidate-{u}.json'),
                    sha(ROOT / f'outputs/ranking-candidate-{u}.json')) for u in selector.UPDATES}
    proof = selector._derive_proof(str(registration), REG_SHA, str(summary_path), sha(summary_path),
                                   str(outer_path), sha(outer_path), bindings)
    results = [read(bindings[u][0]) for u in selector.UPDATES]
    total_frames = sum(row['gameplay_frames'] for result in results for row in result['rows'])
    require(total_frames <= 110592000, 'campaign raw-frame cap exceeded')
    report = {'schema': 'parent_expanded_ranking_terminal_audit_v1',
              'status': 'accepted_ranking_only_no_promotion', 'launches': 1,
              'registration_sha256': REG_SHA, 'raw_supervisor_exit': supervisor_exit,
              'raw_worker_exit': outer['raw_exit_code'], 'outer_receipt_sha256': sha(outer_path),
              'summary_sha256': sha(summary_path), 'all_input_and_output_pins_verified': True,
              'independent_owned_process_absence': True, 'exact_matching_lease': True,
              'ledger_unchanged_through_audit': True, 'cache_empty': True, 'cancel_absent': True,
              'episodes': 6144, 'ranking_seeds_per_checkpoint': 1024, 'raw_gameplay_frames': total_frames,
              'elapsed_supervisor_seconds': outer['elapsed_seconds'],
              'final_worker_peak_RSS_bytes': heartbeat['rss_bytes'],
              'final_MPS_driver_bytes': heartbeat['mps_driver_bytes'],
              'winner_update': proof['winner_update'], 'selection_adapter_sha256': SELECTOR_SHA,
              'candidates': [{'update': r['candidate_update'], 'performance': r['performance'],
                              'death_causes': r['death_causes'], 'caps': r['caps'],
                              'result_sha256': bindings[r['candidate_update']][1]} for r in results],
              'promotion': False, 'confirmation_opened': False, 'qualification': False,
              'limits': ['MPS allocation is final sampled memory; no independently stored peak trace.',
                         'Source guards enforced separate 6 GiB RSS/MPS caps; no stop reported.',
                         'Ranking is selection-only; accepted checkpoint 348 remains unchanged.']}
    destination = ROOT / 'parent-postflight.json'
    with destination.open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--supervisor-exit', required=True, type=int)
    args = parser.parse_args()
    print(json.dumps(audit(args.supervisor_exit), indent=2))
