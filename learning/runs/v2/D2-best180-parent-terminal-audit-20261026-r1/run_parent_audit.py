"""Parent terminal audit with explicit invocation, baseline, and origin gates."""
import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[4]
OWN = Path(__file__).resolve().parent
REG = ROOT / 'learning/runs/v2/D2-best180-branch-registration-luna-20261026-r2/registration-proposed.json'
REG_SHA = 'd6a5aa8cbdd889728b79486f09673215847b6d8e27f93f1ce80eb1cf3e8cc7ba'
AUDITOR = ROOT / 'learning/runs/v2/D2-best180-all-candidate-auditor-luna-20261026-r2'
OBS = ROOT / 'learning/runs/v2/D2-best180-branch-execution-observer-luna-20261026-r1'


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


assert sha(REG) == REG_SHA
reg = load(REG)
assert sys.dont_write_bytecode and sys.flags.dont_write_bytecode
assert sys.pycache_prefix == reg['import_policy']['pycache_prefix']
assert os.environ['PYTHONPYCACHEPREFIX'] == sys.pycache_prefix
assert Path(sys.executable).resolve() == Path(reg['interpreter']).resolve()
assert not any(Path(sys.pycache_prefix).iterdir())
for path, expected in reg['pins'].items():
    assert sha(path) == expected, path

# The archived JSON is not in the registration. Bind it independently to its
# previously verified bytes, accepted JSONL, and accepted parent performance.
base = ROOT / 'learning/runs/v2/D2-gradient-alignment-20261025-r2'
base_json = base / 'development-000180.json'
base_rows = base / 'development-000180.jsonl'
assert sha(base_json) == '2456bef85e7203d60496a6600631613a7dbc2987467d63d467dfec048f3d5680'
assert sha(base_rows) == '33e7859274c65cbefb627e595006e4c64650a653ccace1e059bc9e46a8df76f1'
original_rows = [json.loads(line) for line in base_rows.read_text().splitlines()]
assert sorted(load(base_json)['evaluation']['rows'], key=lambda row: row['seed']) == sorted(original_rows, key=lambda row: row['seed'])
parent_receipt = load(reg['parent']['terminal_receipt_path'])
assert sum(row['alive_frames'] for row in original_rows) / 64 == parent_receipt['performance']['mean_alive_frames']

assert sha(AUDITOR / 'audit_candidates.py') == '26d1e21c3ddf6d5ace6f95157b3caae0053d999d90f6af4b50538800839dd7a5'
sys.path.insert(0, str(AUDITOR))
import audit_candidates

full = audit_candidates.audit(provisional=False)
assert full['audited_evaluations'] == 7
out = Path(reg['output'])
summaries = {}
for update in audit_candidates.UPDATES:
    certificate = load(out / f'development-{update:06d}.json')
    assert certificate['phase_update'] == update
    assert certificate['local_update'] == update - 180
    evaluation = certificate['evaluation']
    alive = sorted(row['alive_frames'] for row in evaluation['rows'])
    summary = {'Q1': sum(alive[:16]) / 16, 'Q4': sum(alive[-16:]) / 16,
               'mean': sum(alive) / 64}
    assert summary == certificate['performance']['alive_frames']
    summaries[str(update)] = {'alive_frames': summary, 'death_causes': evaluation['death_causes'],
                              'caps': evaluation['caps'], 'checkpoint_sha256': certificate['checkpoint_sha256']}
assert sorted(load(out / 'development-000180.json')['evaluation']['rows'], key=lambda row: row['seed']) == sorted(original_rows, key=lambda row: row['seed'])

runtime = Path(reg['runtime_root']).resolve()
origins = {}
for name in ('dodge_rl', 'dodge_rl.checkpoints', 'dodge_rl.identity', 'dodge_rl._native'):
    module = __import__(name, fromlist=['__file__'])
    origin = Path(module.__file__).resolve()
    assert origin.is_relative_to(runtime), (name, origin)
    assert sha(origin) == reg['pins'][str(origin)]
    origins[name] = str(origin)
assert Path(sys.modules['runner'].__file__).resolve() == Path(reg['runner_path']).resolve()

observation = load(OBS / 'observation.json')
execution = load(out / 'execution-result.json')
worker = load(out / 'worker-result.json')
assert observation['launch_count'] == execution['actual_worker_launch_count'] == 1
assert observation['outer_raw_exit'] == observation['worker_raw_exit'] == execution['observed_worker_raw_exit'] == 0
assert execution['status'] == 'passed' and worker['status'] == 'completed'
assert worker['first_failure'] is None and observation['first_event'] is None
assert 0 < observation['outer_inclusive_wall_seconds'] <= 1800
assert observation['max_aggregate_rss_bytes'] <= 6442450944
assert worker['peak_rss_bytes'] <= 6442450944 and worker['peak_mps_driver_bytes'] <= 6442450944
assert observation['postflight']['pins']['failures'] == []
assert observation['postflight']['cache_empty_after'] is True
for key in ('outer_process_absent', 'worker_process_absent', 'worker_group_absent'):
    assert observation[key] is True
for pid in (observation['observer_pid'], observation['outer_pid'], execution['worker_pid']):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        pass
    else:
        raise AssertionError(('Owned process still exists', pid))
for pgid in (observation['outer_process_group'], execution['owned_pgid']):
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        pass
    else:
        raise AssertionError(('Owned process group still exists', pgid))
for path, expected in reg['pins'].items():
    assert sha(path) == expected, path
assert not any(Path(sys.pycache_prefix).iterdir())

observer_error = load(OBS / 'observer-error.json')
assert observer_error['error'] == 'SystemExit(0)'
result = {
    'schema': 'best180_branch_parent_terminal_audit_v1', 'status': 'passed',
    'at_utc': datetime.now(timezone.utc).isoformat(), 'registration_sha256': REG_SHA,
    'pins_checked_before_and_after': len(reg['pins']), 'module_origins': origins,
    'invocation_bytecode_and_interpreter_gates': True,
    'baseline_json_sha256': sha(base_json), 'baseline_jsonl_sha256': sha(base_rows),
    'independent_all_candidate_audit': full, 'performance': summaries,
    'outer_wall_seconds': observation['outer_inclusive_wall_seconds'],
    'peak_aggregate_RSS_bytes': observation['max_aggregate_rss_bytes'],
    'peak_worker_RSS_bytes': worker['peak_rss_bytes'],
    'peak_MPS_driver_bytes': worker['peak_mps_driver_bytes'],
    'owned_processes_and_groups_absent': True, 'raw_exits': {'outer': 0, 'worker': 0},
    'worker_counters': worker['counters'], 'cumulative_counters': worker['cumulative_counters'],
    'actual_evaluations_checked': 7,
    'preserved_launcher_reported_evaluations_checked': execution['evidence_checks']['evaluations_checked'],
    'observer_wrapper_error_disposition': 'Wrapper caught its own successful SystemExit(0); observed exits and all independent gates pass. Original error artifact preserved.',
    'observer_receipt_sha256': sha(OBS / 'observation.json'),
    'execution_result_sha256': sha(out / 'execution-result.json'),
    'worker_result_sha256': sha(out / 'worker-result.json'),
    'best_selection_authority': 'Parent must issue separate exact candidate receipt; this audit never edits checkpoint metadata.',
}
with (OWN / 'audit.json').open('x') as stream:
    json.dump(result, stream, indent=2, sort_keys=True)
    stream.write('\n')
print(json.dumps({'status': 'passed', 'candidates': 7, 'proposed_best_update': full['proposed_best_update'],
                  'outer_wall_seconds': result['outer_wall_seconds'], 'pins': len(reg['pins'])}))
