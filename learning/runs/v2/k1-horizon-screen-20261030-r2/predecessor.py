"""Read-only disposition of the failed attempt before an exact lease handoff."""
import common as c
from lifecycle import group_members


def audit(reg):
    p = reg['predecessor']; root = c.Path(p['package'])
    c.need(c.sha(p['registration_path']) == p['registration_sha256'], 'Predecessor registration differs')
    old = c.read(p['registration_path']); c.verify_pins(old)
    c.need(old['expected_lease'] == p['expected_lease'], 'Predecessor lease registration differs')
    unchanged = ['arms', 'jobs', 'replicas', 'exclusions', 'envs', 'rollout', 'frame_target', 'updates',
        'microbatch', 'effective_minibatch', 'threads', 'prefix_updates', 'checkpoint_updates', 'ppo',
        'work_seconds', 'receipt_seconds', 'campaign_total_seconds', 'IO_reserve_seconds',
        'rss_bytes', 'mps_bytes', 'allocator_bytes', 'AC_required', 'one_MPS_job', 'checkpoint_path',
        'checkpoint_sha256', 'model_fingerprint', 'adam_fingerprint', 'runtime_root', 'pool_path', 'interpreter']
    c.need(all(reg[k] == old[k] for k in unchanged), 'Restart recipe/input/limits changed')
    failure = c.read(root / 'first-failure.json')
    disposition = c.read(p['disposition_path'])
    launch = c.read(root / 'launch.claimed')
    out = root / 'outputs' / 'r1-matched'
    child = c.read(out / 'launch.json'); exit_receipt = c.read(out / 'exit.json')
    c.need(failure['status'] == 'first_failure_preserved_lease_held'
           and failure['completed_jobs'] == [] and failure['lease_value'] == p['expected_lease'],
           'Predecessor failure disposition differs')
    c.need(exit_receipt['raw_exit_code'] == exit_receipt['observed_exit_code'] == 1
           and exit_receipt['directly_reaped'] and exit_receipt['group_absent']
           and exit_receipt['reason'] == "ValueError('AC power required')"
           and child['pid'] == child['pgid'] == exit_receipt['pid'] == exit_receipt['pgid'],
           'Predecessor power failure/reap differs')
    c.need(disposition['completed_updates'] == 20 and disposition['completed_gameplay_frames'] == 1310720
           and disposition['partial_update']['partial_gameplay_frames'] == 448
           and disposition['evaluation_games'] == 0 and not disposition['promoted'],
           'Predecessor partial-work record differs')
    for artifact in disposition['preserved_artifacts']:
        path = c.HERE.parents[3] / artifact['path']
        c.need(str(path) in reg['input_pins'] and c.sha(path) == artifact['sha256'], 'Predecessor artifact changed')
    c.need(not (root / 'parent-terminal-audit.json').exists() and not (root / 'lease-release.json').exists(),
           'Predecessor unexpectedly accepted/released')
    c.need((root / 'empty-pycache').is_dir() and not list((root / 'empty-pycache').iterdir()),
           'Predecessor empty cache changed')
    c.need(all(not list((root / 'outputs' / j['id']).iterdir()) for j in old['jobs'][1:]),
           'Unstarted predecessor trajectory changed')
    c.need(not group_members(launch['pid']) and not group_members(exit_receipt['pgid']),
           'Predecessor process group remains')
    return dict(status='acknowledged_failed_attempt_not_success',
        registration_sha256=p['registration_sha256'], failure_sha256=c.sha(root / 'first-failure.json'),
        exit_sha256=c.sha(out / 'exit.json'), disposition_sha256=c.sha(p['disposition_path']),
        predecessor_lease=p['expected_lease'], successor_lease=reg['expected_lease'],
        artifacts_preserved=True, groups_absent=True, failed_cache_exists_empty=True,
        failed_attempt_accepted=False, partial_weights_used=False, recipe_inputs_limits_unchanged=True)
