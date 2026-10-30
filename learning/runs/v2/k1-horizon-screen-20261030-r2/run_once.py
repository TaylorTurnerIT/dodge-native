"""One campaign claim, serial children, strict audit before exact lease release."""
import argparse
import hashlib
import json
import os
import resource
import signal
import subprocess
import time
import traceback

import common as c
from lifecycle import group_members, run_child
import predecessor


def argv_for(reg, path, digest, job):
    return [reg['interpreter'], '-B', str(c.HERE / 'worker.py'), '--registration', str(path),
            '--sha256', digest, '--job', job['id']]


def audit_job(reg, digest, job):
    out = c.HERE / 'outputs' / job['id']
    result = c.read(out / 'result.json'); exit_receipt = c.read(out / 'exit.json')
    launch = c.read(out / 'launch.json'); worker = c.read(out / 'worker.claimed')
    c.need(exit_receipt['raw_exit_code'] == exit_receipt['observed_exit_code'] == 0
           and exit_receipt['directly_reaped'] and exit_receipt['group_absent']
           and launch['pid'] == worker['pid'] == exit_receipt['pid'], 'Direct child evidence differs')
    c.need(not group_members(exit_receipt['pgid']), 'Group remains')
    c.need(result['status'] == 'complete' and result['job'] == job
           and result['registration_sha256'] == worker['registration_sha256'] == digest
           and result['evaluation_games'] == 0 and not result['promoted'], 'Worker identity/status differs')
    c.need(c.sha(out / 'prefix-qualification.json') == result['prefix_sha256']
           and c.sha(out / 'updates.jsonl') == result['telemetry_sha256']
           and c.sha(out / 'native-events.jsonl') == result['native_journal_sha256'], 'Journal/qualification artifact differs')
    prefix = c.read(out / 'prefix-qualification.json')
    c.need(prefix['status'] == 'accepted_counted_prefix' and prefix['updates'] == reg['prefix_updates']
           and prefix['counted_frames'] == reg['prefix_updates'] * reg['envs'] * reg['rollout']
           and prefix['forecast_seconds'] < reg['work_seconds']
           and prefix['passive_GAE_and_return_identity_checks'] == [True] * reg['prefix_updates'], 'Counted prefix qualification differs')
    with (out / 'updates.jsonl').open() as f:
        counts = c.validate_telemetry([json.loads(line) for line in f], reg, job)
    c.need(result['counts'] == counts and counts['frames'] == reg['frame_target'], 'Training counts differ')
    pool = {r['seed'] for r in c.read(reg['pool_path'])['seeds']}
    c.need(set(result['consumed_seeds']) <= pool and result['consumed_seeds'], 'Non-pool seed consumed')
    c.need(result['stream_sha256'] == reg['replicas'][job['replica']]['stream_sha256'], 'Stream differs')
    c.need(result['elapsed_seconds'] < reg['work_seconds']
           and result['resources']['peak_rss_bytes'] < reg['rss_bytes']
           and result['resources']['peak_mps_driver_bytes'] < reg['mps_bytes'], 'Worker resource bound differs')
    c.need([x['update'] for x in result['checkpoints']] == reg['checkpoint_updates'], 'Checkpoint boundaries missing')
    c.need({str(p) for p in out.glob('*.pt')} == {x['path'] for x in result['checkpoints']}, 'Unexpected/missing checkpoint')
    for artifact in result['checkpoints']:
        path = c.Path(artifact['path'])
        c.need(path.parent.resolve() == out.resolve() and c.sha(path) == artifact['sha256']
               and path.stat().st_mode & 0o222 == 0, 'Checkpoint path/hash/immutability differs')
    c.need(not list(out.glob('*.partial')) and not (out / 'first-failure.json').exists(), 'Partial/failure evidence present')
    return dict(job=job['id'], counts=counts, result_sha256=c.sha(out / 'result.json'),
                exit_sha256=c.sha(out / 'exit.json'), final_checkpoint=result['checkpoints'][-1],
                prefix_sha256=result['prefix_sha256'], resources=result['resources'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gate', required=True)
    args = parser.parse_args()
    gate = c.read(args.gate)
    c.need(gate['status'] == 'source_accepted_for_one_registered_screen', 'Source gate absent')
    path, digest = c.Path(gate['registration_path']), gate['registration_sha256']
    reg = c.load_registration(path, digest)
    review = c.read(gate['review_path'])
    c.need(c.sha(gate['review_path']) == gate['review_sha256']
           and review['status'] == 'no_blocking_findings'
           and review['registration_sha256'] == digest, 'Independent review differs')
    c.need(c.sha(gate['runtime_preflight_path']) == gate['runtime_preflight_sha256']
           and c.read(gate['runtime_preflight_path'])['status'] == 'runtime_import_preflight_passed',
           'Runtime import preflight differs')
    c.need(c.sha(gate['authority_path']) == gate['authority_sha256'], 'Authority differs')
    authority = c.read(gate['authority_path'])
    c.need(authority['approved_run_id'] == reg['run_id'] and authority['one_attempt']
           and authority['training_trajectories'] == len(reg['jobs'])
           and authority['registration_sha256'] == digest
           and authority['exact_predecessor_lease_handoff'] == reg['predecessor']['expected_lease'],
           'Wrong execution scope')
    cache = c.HERE / 'empty-pycache'
    c.need(cache.is_dir() and not list(cache.iterdir()), 'Existing empty cache required')
    c.need(not (c.HERE / 'launch.claimed').exists() and not (c.HERE / 'parent-terminal-audit.json').exists(), 'Campaign already consumed')
    power = c.power_assertions(os.getpid())
    prior_lease = reg['predecessor']['expected_lease']
    c.need(c.read(reg['state_path']).get('active_long_campaign') == prior_lease, 'Exact predecessor lease absent')
    disposition = predecessor.audit(reg)
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPYCACHEPREFIX=str(cache))
    c.save(c.HERE / 'launch.claimed', dict(pid=os.getpid(), registration_sha256=digest,
           authority_sha256=gate['authority_sha256'], power=power))
    started = time.monotonic(); last_power = float('-inf'); cancelled = False
    completed = []

    def cancel(*_):
        nonlocal cancelled
        cancelled = True
    signal.signal(signal.SIGTERM, cancel); signal.signal(signal.SIGINT, cancel)

    def monitor(members):
        nonlocal last_power
        now = time.monotonic()
        c.need(not cancelled and now - started < reg['campaign_total_seconds'], 'Campaign cancelled/deadline')
        c.check_lease(reg)
        rss = sum(x['rss_bytes'] for x in members) + int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        c.need(rss < reg['rss_bytes'], 'Aggregate parent/child RSS ceiling')
        if now - last_power >= 5:
            c.power_assertions(os.getpid()); last_power = now

    try:
        c.save(c.HERE / 'predecessor-disposition-audit.json', dict(disposition,
            registration_sha256=digest, authority_sha256=gate['authority_sha256']))
        c.lease_change(reg, prior_lease, reg['expected_lease'])
        c.save(c.HERE / 'lease-handoff.json', dict(previous_lease=prior_lease,
            replacement_lease=reg['expected_lease'], never_cleared_to_null=True,
            predecessor_audit_sha256=c.sha(c.HERE / 'predecessor-disposition-audit.json'),
            authority_sha256=gate['authority_sha256'], registration_sha256=digest))
        for job in reg['jobs']:
            monitor([])
            out = c.HERE / 'outputs' / job['id']
            c.need(not list(out.iterdir()), 'Job output already claimed')
            c.save(out / 'dispatch.json', dict(worker_expected_job=job['id'], parent_pid=os.getpid(),
                   registration_sha256=digest))
            run_child(argv_for(reg, path, digest, job), out, environment, monitor,
                      reg['work_seconds'] + reg['receipt_seconds'])
            accepted = audit_job(reg, digest, job)
            c.save(out / 'parent-job-audit.json', dict(status='accepted_training_trajectory',
                   registration_sha256=digest, evidence=accepted, lease_cleared=False))
            completed.append(accepted)
            print(c.canonical(dict(job=job['id'], status='trajectory_accepted', frames=accepted['counts']['frames'])).decode(), flush=True)
        c.verify_pins(reg); monitor([]); predecessor.audit(reg)
        c.need(not list(cache.iterdir()), 'Cache changed')
        c.need(sum(x['counts']['frames'] for x in completed) == len(reg['jobs']) * reg['frame_target'], 'Campaign exposure differs')
        c.save(c.HERE / 'parent-terminal-audit.json', dict(schema='dodge_K1_horizon_parent_audit_v1',
               status='accepted_training_screen_no_evaluation', registration_sha256=digest,
               authority_sha256=gate['authority_sha256'], trajectories=completed,
               predecessor_audit_sha256=c.sha(c.HERE / 'predecessor-disposition-audit.json'),
               lease_handoff_sha256=c.sha(c.HERE / 'lease-handoff.json'),
               elapsed_seconds=time.monotonic() - started, exact_inputs_unchanged=True,
               cache_exists_empty=True, lease_cleared=False, evaluation_games=0, promoted=False))
        c.lease_change(reg, reg['expected_lease'], None)
        c.save(c.HERE / 'lease-release.json', dict(parent_terminal_audit_sha256=c.sha(c.HERE / 'parent-terminal-audit.json'),
               registration_sha256=digest, exact_lease=reg['expected_lease'], lease_value_after_release=None))
        return 0
    except BaseException as error:
        c.save(c.HERE / 'first-failure.json', dict(status='first_failure_preserved_lease_held',
               error=repr(error), traceback=traceback.format_exc(), completed_jobs=completed,
               lease_value=c.read(reg['state_path']).get('active_long_campaign'),
               elapsed_seconds=time.monotonic() - started))
        raise


if __name__ == '__main__':
    raise SystemExit(main())
