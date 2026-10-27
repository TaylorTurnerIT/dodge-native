"""Accept the completed frozen run, then atomically retain its audited best."""
import datetime
import hashlib
import json
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OWN = Path(__file__).resolve().parent
REG_PATH = ROOT / 'learning/runs/v2/D2-retained204-lr1e4-prepare-luna-20261026-r3/registration.json'
REG_SHA = '68063348dede3050c4a8852c6314f4c95fd3a623e89c9499413f2325f4edad44'
OBS_DIR = ROOT / 'learning/runs/v2/D2-retained204-lr1e4-execution-observer-luna-20261026-r1'


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


assert sha(REG_PATH) == REG_SHA
reg = read(REG_PATH)
out = Path(reg['output'])
full = read(OWN / 'full-audit.json')
assert sha(OWN / 'full-audit.json') == '4beebd3ffc223cadefad95f619121a2e166f571c9cf6275c669bcb1734407cd2'
assert full['mode'] == 'full_parent_only'
assert full['audit']['status'] == 'all_candidates_audited_pending_parent_terminal_acceptance'
assert full['audit']['updates_audited'] == [204, 216, 228, 240, 252, 264, 276]
assert full['audit']['proposed_best_update'] == 276
assert full['registration']['pins_checked_before_and_after'] == 13770
assert full['bytecode']['empty_after'] is True
obs = read(OBS_DIR / 'observation.json')
execution = read(out / 'execution-result.json')
worker = read(out / 'worker-result.json')
meta = read(OWN / 'selected-checkpoint-metadata.json')
assert obs['launch_count'] == execution['actual_worker_launch_count'] == 1
assert obs['outer_raw_exit'] == obs['worker_raw_exit'] == execution['observed_worker_raw_exit'] == 0
assert obs['success_authoritative'] is True and obs['first_event'] is None
assert execution['status'] == 'passed' and worker['status'] == 'completed' and worker['first_failure'] is None
assert 0 < obs['outer_inclusive_wall_seconds'] <= 1800 and 0 < worker['work_elapsed_seconds'] < 1790
for value in (obs['max_aggregate_rss_bytes'], worker['peak_rss_bytes'], worker['peak_mps_driver_bytes']):
    assert 0 < value <= 6442450944
for key in ('outer_process_absent', 'worker_process_absent', 'worker_group_absent'):
    assert obs[key] is True
for pid in (obs['observer_pid'], obs['outer_pid'], execution['worker_pid']):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        continue
    raise AssertionError(('Owned PID still exists', pid))
for group in (obs['outer_process_group'], execution['owned_pgid']):
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        continue
    raise AssertionError(('Owned group still exists', group))
assert obs['postflight']['pins']['checked'] == 13770 and obs['postflight']['pins']['failures'] == []
assert obs['postflight']['cache_empty_after'] is True
assert obs['postflight']['publication_failure_absent'] is True and not (out / 'publication-failure.json').exists()
assert not any(Path(reg['import_policy']['pycache_prefix']).iterdir())
for key, name in (('resources_sha256', 'resources.jsonl'), ('stdout_sha256', 'stdout.log'), ('stderr_sha256', 'stderr.log')):
    assert obs['postflight'][key] == sha(OBS_DIR / name)
for path, expected in reg['pins'].items():
    assert sha(path) == expected, path

state_path = ROOT / 'learning/runs/v2-orchestration/state.json'
state = read(state_path)
assert state['active_long_campaign'] == reg['expected_lease']
assert state['active_inference_diagnostic'] is None
assert state['training_parent_selection_policy']['current_parent_sha256'] == reg['parent']['sha256']
save(OWN / 'state-before-clear-and-select.json', state)
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
performance = {}
for update in reg['limits']['eval_updates']:
    cert_path = out / f'development-{update:06d}.json'
    cert = read(cert_path)
    rows = cert['evaluation']['rows']
    alive = sorted(row['alive_frames'] for row in rows)
    assert len(alive) == 64
    item = {'update': update, 'checkpoint_sha256': cert['checkpoint_sha256'],
            'q1_bottom16_mean': sum(alive[:16]) / 16, 'q4_top16_mean': sum(alive[-16:]) / 16,
            'mean_alive_frames': sum(alive) / 64, 'mean_score': cert['evaluation']['mean_score'],
            'episodes': 64, 'deaths': cert['evaluation']['deaths'], 'caps': cert['evaluation']['caps'],
            'death_causes': {k: v for k, v in cert['evaluation']['death_causes'].items() if v},
            'certificate_sha256': sha(cert_path)}
    assert cert['performance']['alive_frames'] == {
        'Q1': item['q1_bottom16_mean'], 'Q4': item['q4_top16_mean'], 'mean': item['mean_alive_frames']}
    assert full['audit']['candidates'][str(update)]['checkpoint_sha256'] == item['checkpoint_sha256']
    assert full['audit']['candidates'][str(update)]['certificate_sha256'] == item['certificate_sha256']
    performance[str(update)] = item
selected = performance['276']
assert selected['checkpoint_sha256'] == meta['checkpoint_sha256'] == sha(meta['checkpoint_path'])
assert meta['counters'] == worker['counters'] and meta['cumulative_counters'] == worker['cumulative_counters']
assert meta['next_episode_indices'] == worker['final_resume_next_episode_indices']
assert selected['mean_alive_frames'] == max(p['mean_alive_frames'] for p in performance.values()) > 1921.171875
assert selected['mean_alive_frames'] < 3060 and selected['caps'] == 0
samples = [json.loads(line) for line in (OBS_DIR / 'resources.jsonl').read_text().splitlines()]
assert max(row['aggregate_rss_bytes'] for row in samples) == obs['max_aggregate_rss_bytes']
times = [row['monotonic'] for row in samples]
resource = {
    'status': 'passed', 'raw_exits': {'outer': 0, 'worker': 0},
    'outer_wall_seconds': obs['outer_inclusive_wall_seconds'], 'worker_work_seconds': worker['work_elapsed_seconds'],
    'aggregate_current_RSS_peak_bytes': obs['max_aggregate_rss_bytes'],
    'worker_highwater_RSS_peak_bytes': worker['peak_rss_bytes'], 'MPS_driver_peak_bytes': worker['peak_mps_driver_bytes'],
    'outer_resource_samples': len(samples), 'outer_resource_max_gap_seconds': max(b - a for a, b in zip(times, times[1:])),
    'owned_processes_and_groups_absent': True, 'cache_empty_at_training_postflight_and_current_audit': True,
    'postflight_cache_reconciliation_sha256': sha(OWN / 'cache-contamination-reconciliation.json'),
    'observation_sha256': sha(OBS_DIR / 'observation.json'), 'execution_result_sha256': sha(out / 'execution-result.json'),
    'worker_result_sha256': sha(out / 'worker-result.json'),
}
save(OWN / 'resource-postflight.json', resource)
audit = {
    'schema': 'retained204_lr1e4_parent_terminal_audit_v1', 'status': 'passed', 'at_utc': now,
    'run_id': reg['run_id'], 'registration_sha256': REG_SHA, 'pins_verified_before_and_after': 13770,
    'actual_evaluations_checked': 7, 'independent_full_audit_path': str(OWN / 'full-audit.json'),
    'independent_full_audit_sha256': sha(OWN / 'full-audit.json'),
    'resource_postflight_path': str(OWN / 'resource-postflight.json'),
    'resource_postflight_sha256': sha(OWN / 'resource-postflight.json'),
    'selected_metadata_sha256': sha(OWN / 'selected-checkpoint-metadata.json'),
    'raw_exits': {'outer': 0, 'worker': 0}, 'owned_processes_and_groups_absent': True,
    'performance': performance, 'selected_update': 276, 'worker_counters': worker['counters'],
    'cumulative_counters': worker['cumulative_counters'], 'qualification_claim': False,
    'reporting_convention': 'Q1/Q4 rank alive frames independently; child score-ranked survival tails are not these metrics.',
}
save(OWN / 'audit.json', audit)

# Saved checkpoint timing precedes its evaluation. The endpoint's entire accepted
# outer run belongs to the future selected-branch high-water, while older discarded
# branches remain accounted only in complete campaign resource cost.
wall = {
    'definition': 'Saved-checkpoint clock, accepted selected-branch terminal high-water, and complete campaign resource cost are distinct.',
    'selected_checkpoint_reported_trajectory_wall_seconds': meta['cumulative_selected_checkpoint_trajectory_wall_seconds'],
    'selected_checkpoint_reported_iteration_wall_seconds': meta['current_iteration_observed_outer_seconds'],
    'future_checkpoint_trajectory_baseline_seconds': 3352.0462366251204 + obs['outer_inclusive_wall_seconds'],
    'successful_ancestor_and_completed_campaign_cost_seconds': 4129.756859292152 + obs['outer_inclusive_wall_seconds'],
    'whole_completed_iteration_observed_outer_seconds': obs['outer_inclusive_wall_seconds'],
    'worker_reported_trajectory_end_seconds': worker['cumulative_selected_checkpoint_trajectory_wall_seconds'],
    'worker_reported_complete_campaign_cost_seconds': worker['cumulative_successful_ancestor_and_completed_campaign_cost_seconds'],
    'future_baseline_reason': 'Selected276 is the completed endpoint, so all current-run evaluation and finalization time is included; no later current-run learner updates were discarded.',
}
receipt = {
    'schema': 'd2_normal_training_parent_terminal_receipt_v1',
    'status': 'accepted_completed_normal_training_iteration', 'at_utc': now, 'run_id': reg['run_id'], 'phase': 'D2',
    'authority_scope': 'This exact accepted endpoint may parent a NEW registered D2 continuation. No D3, B/E, student, competence, or qualification authority.',
    'training_continuation_eligible': True, 'stage_promotion_eligible': False, 'competence_passed': False,
    'checkpoint_metadata_unchanged': True, 'all_seven_candidates_independently_audited': True,
    'checkpoint_path': meta['checkpoint_path'], 'checkpoint_sha256': meta['checkpoint_sha256'],
    'checkpoint_sidecar_sha256': sha(Path(meta['checkpoint_path'] + '.json')),
    'evaluation_path': str(out / 'development-000276.json'), 'evaluation_sha256': sha(out / 'development-000276.json'),
    'evaluation_jsonl_path': str(out / 'development-000276.jsonl'), 'evaluation_jsonl_sha256': sha(out / 'development-000276.jsonl'),
    'registration_path': str(REG_PATH), 'registration_sha256': REG_SHA,
    'identity_sha256': meta['identity_sha256'], 'config_sha256': meta['config_sha256'],
    'native_sha256': meta['native_sha256'], 'runtime_sha256': meta['runtime_sha256'], 'policy_sha256': meta['policy_sha256'],
    'parent_checkpoint_sha256': reg['parent']['sha256'], 'parent_registration_sha256': meta['parent_registration_sha256'],
    'parent_terminal_receipt_path': reg['parent']['terminal_receipt_path'],
    'parent_terminal_receipt_sha256': reg['parent']['terminal_receipt_sha256'],
    'completed_phase_updates': 276, 'completed_local_updates': 72,
    'counters': meta['counters'], 'inherited_counters': meta['inherited_counters'], 'cumulative_counters': meta['cumulative_counters'],
    'next_episode_indices': meta['next_episode_indices'], 'learner_fingerprints': meta['learner_fingerprints'],
    'effective_learning_rate': 0.0001, 'performance': selected, 'wall_accounting': wall,
    'audit_path': str(OWN / 'audit.json'), 'audit_sha256': sha(OWN / 'audit.json'),
    'raw_exits': {'outer': 0, 'worker': 0}, 'owned_processes_and_groups_absent': True,
}
save(OWN / 'parent-terminal-receipt.json', receipt)
receipt_sha = sha(OWN / 'parent-terminal-receipt.json')
previous_policy = dict(state['training_parent_selection_policy'])
selection = {
    'schema': 'd2_retained_best_selection_v2', 'at_utc': now,
    'rule': 'Strictly higher independently audited mean alive frames on the same64 deterministic D2 development seeds after whole-run parent acceptance.',
    'previous': previous_policy,
    'current': {'phase_update': 276, 'checkpoint_path': meta['checkpoint_path'], 'checkpoint_sha256': meta['checkpoint_sha256'],
                'terminal_receipt_path': str(OWN / 'parent-terminal-receipt.json'), 'terminal_receipt_sha256': receipt_sha,
                'parent_receipt_schema': receipt['schema'], 'performance': selected},
    'candidate_means': {u: item['mean_alive_frames'] for u, item in performance.items()},
    'qualification_claim': False,
}
save(OWN / 'retained-best-selection.json', selection)
assert state['active_long_campaign'] == reg['expected_lease']
state['active_long_campaign'] = None
state['training_parent_selection_policy'].update(
    current_parent_phase_update=276, current_parent_sha256=meta['checkpoint_sha256'],
    current_parent_receipt=str((OWN / 'parent-terminal-receipt.json').relative_to(ROOT)),
    current_parent_receipt_sha256=receipt_sha, parent_receipt_schema=receipt['schema'],
    path=str((OWN / 'retained-best-selection.json').relative_to(ROOT)), sha256=sha(OWN / 'retained-best-selection.json'))
reference = {'phase_update': 276, 'run_id': reg['run_id'], 'checkpoint_sha256': meta['checkpoint_sha256'],
             'mean_alive_frames': selected['mean_alive_frames'], 'Q1_bottom16_mean': selected['q1_bottom16_mean'],
             'Q4_top16_mean': selected['q4_top16_mean'],
             'parent_terminal_receipt': str((OWN / 'parent-terminal-receipt.json').relative_to(ROOT)),
             'parent_terminal_receipt_sha256': receipt_sha}
reporting = state['performance_reporting_policy']
reporting['previous_best_reference'] = reporting['best_reference']
reporting.update(best_reference=reference, latest=reference,
                 current_cohort=str((OWN / 'audit.json').relative_to(ROOT)),
                 current_death_causes=str((out / 'development-000276.jsonl').relative_to(ROOT)),
                 death_attribution='Accepted LR1e-4 endpoint276:64 fixed D2 development games; first fatal contact.')
work = state['postcritic_training_work']
work.update(status='LR1e4_run_completed_parent_accepted_retained276', best_observed_current_lineage_reference=reference,
            latest_performance=selected, latest_completed_phase_updates=276, latest_completed_cumulative_updates=324,
            latest_parent_terminal_audit=str((OWN / 'audit.json').relative_to(ROOT)),
            latest_parent_terminal_receipt=reference['parent_terminal_receipt'], latest_parent_terminal_receipt_sha256=receipt_sha,
            lease_cleared_at_utc=now, cumulative_D2_inclusive_wall_seconds=wall['future_checkpoint_trajectory_baseline_seconds'],
            cumulative_D2_wall_semantics='Selected-branch trajectory through accepted terminal high-water; full resource cost is separate.',
            completed_campaign_resource_cost_seconds=wall['successful_ancestor_and_completed_campaign_cost_seconds'])
task = state['tasks']['retained204_lr1e4_execution_luna_20261026_r1']
task.update(status='completed', workState='result_available', result_ingested=True, result_ingested_at_utc=now,
            parent_reconciled=True, parent_terminal_audit=str((OWN / 'audit.json').relative_to(ROOT)),
            parent_terminal_receipt=reference['parent_terminal_receipt'], lease_cleared_at_utc=now,
            verdict='One72update run accepted after independent all7audit/provenance/resource/rawexit checks. Retained276; oldmetadata unchanged; no qualification.')
state['tasks']['retained204_lr1e4_parent_audit_wrapper_haiku_20261026_r1'].update(
    status='completed', workState='result_available', result_ingested=True, result_ingested_at_utc=now, parent_reconciled=True,
    parent_full_audit=str((OWN / 'full-audit.json').relative_to(ROOT)),
    verdict='14tests independently passed with PYTHONDONTWRITEBYTECODE=1. Five post-run helper pycs reproduced and archived; full strict-origin all7audit passed unchanged wrapper/auditor.')
state['tasks']['current_pair_calibration_r3_repair_luna_20261026_r1'].update(
    status='completed', workState='result_available', result_ingested=True, result_ingested_at_utc=now,
    verdict='FrozenCPUproposal eighttests and CPUpreflight; independentreviewpending; nohardwarelaunch.')
state['tasks']['retained204_lr1e4_auditor_r2_frozen_review_luna_20261026_r1'].update(
    parent_reconciliation=str((OWN / 'full-audit.json').relative_to(ROOT)),
    verdict='Currentuse interpreter/cache/runtime-origin gap closed by strict parent wrapper; full all7audit passed, source unchanged.')
state['paired_action_eval_work']['current_targets_status'] = 'R6 comparison204 versus previous252 is historical after retained276; no automatic512campaign launch.'
state['parallel_acceleration_work'].update(status='retained276_parent_accepted_next_bounded_D2_iteration_supported',
    canonical_report=str((OWN / 'report.md').relative_to(ROOT)))
state['next_actions'] = [
    'Prepare new bounded72update D2 continuation from accepted276 model/Adam/RNG at unchanged LR1e-4, seed3791628419; exact new authority/config/pins/test/review before one launch.',
    'Review representative calibrationR3 proposal independently; no overlapping MPS jobs and no automatic stale R6 paired campaign.',
    'Preserve all checkpoints, audit attempts, post-run cache evidence, original child score-ranked report and canonical alive-ranked tail correction.'
]
state['suggested_next_work'] = state['next_actions'][0]
state['last_update_at_utc'] = now
state['completed_long_campaigns'].append({'run_id': reg['run_id'], 'status': 'parent_accepted_normal_training',
    'retained_phase_update': 276, 'audit': str((OWN / 'audit.json').relative_to(ROOT)), 'wall_seconds': obs['outer_inclusive_wall_seconds']})
save(OWN / 'state-after-clear-and-select.json', state)
temporary = state_path.with_suffix('.json.parent-tmp')
temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + '\n')
os.replace(temporary, state_path)
print(json.dumps({'status': 'parent_accepted_retained276', 'checkpoint_sha256': meta['checkpoint_sha256'],
                  'receipt_sha256': receipt_sha, 'performance': selected, 'wall_accounting': wall}))
