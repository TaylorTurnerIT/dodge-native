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
    c.need(c.sha(out / 'migration.json') == result['migration_sha256'], 'Migration receipt differs')
    prefix = c.read(out / 'prefix-qualification.json')
    c.need(prefix['status'] == 'accepted_counted_prefix' and prefix['updates'] == reg['prefix_updates']
           and prefix['counted_frames'] == reg['prefix_updates'] * reg['envs'] * reg['rollout']
           and prefix['forecast_seconds'] < reg['work_seconds'] and prefix['full_path_forecast_seconds'] < reg['campaign_total_seconds']
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


def validate_dispatch(path, digest, stage='training'):
    c.need(c.sha(path) == digest, 'Coordinator dispatch hash differs')
    gate = c.read(path)
    c.need(gate['status'] == 'dispatched_once' and gate['stage'] == stage
           and gate['coordinator_thread'] == '518b8c2d-01fb-4f39-acc3-f2d9f1f35c4e', 'Wrong dispatch scope')
    reg = c.load_registration(gate['registration_path'], gate['registration_sha256'])
    expected = reg['expected_lease'] if stage == 'training' else reg['evaluation_expected_lease']
    c.need(gate['expected_lease'] == expected and gate['record'] == reg['record'], 'Dispatch lease/record differs')
    for kind in ('review', 'authority', 'readiness'):
        c.need(c.sha(gate[kind+'_path']) == gate[kind+'_sha256'], kind+' binding differs')
    review = c.read(gate['review_path'])
    c.need(review['status'] == 'no_blocking_findings'
           and review['registration_sha256'] == gate['registration_sha256'], 'Independent exact-registration review required')
    readiness = c.read(gate['readiness_path'])
    c.need(readiness['status'] == 'CPU_source_and_420_migration_ready'
           and readiness['registration_sha256'] == gate['registration_sha256'], 'CPU readiness binding differs')
    authority = c.read(gate['authority_path'])
    c.need(authority['schema'] == 'teacher_training_queue_authority_v1'
           and authority['first_screens_only'] and authority['no_claim_or_lease_reset'], 'Training queue authority differs')
    reg = dict(reg,expected_lease=expected)
    c.check_lease(reg)
    return gate, reg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dispatch', required=True)
    parser.add_argument('--sha256', required=True)
    args = parser.parse_args()
    gate, reg = validate_dispatch(args.dispatch, args.sha256)
    digest, path = gate['registration_sha256'], c.Path(gate['registration_path'])
    c.need(not (c.HERE/'launch.claimed').exists(), 'Campaign already consumed')
    cache = c.HERE/'empty-pycache'
    c.need(cache.is_dir() and not list(cache.iterdir()), 'Fresh empty cache required')
    c.ac_power()
    helper = subprocess.Popen(['/usr/bin/caffeinate','-ims','-w',str(os.getpid())])
    completed = []
    started = time.monotonic()
    claimed = False
    try:
        # Let assertions register before consuming the one-shot campaign marker.
        power = None
        for _ in range(20):
            try:
                power = c.power_assertions(os.getpid()); break
            except ValueError:
                time.sleep(.1)
        c.need(power is not None and helper.poll() is None, 'Owned caffeinate assertions absent')
        c.save(c.HERE/'launch.claimed',dict(pid=os.getpid(),registration_sha256=digest,
            dispatch_sha256=args.sha256,power=power))
        claimed = True
        cancelled = False
        last_power = float('-inf')

        def cancel(*_):
            nonlocal cancelled
            cancelled = True
        signal.signal(signal.SIGTERM,cancel); signal.signal(signal.SIGINT,cancel)
        def deadline(*_):
            raise TimeoutError('Global observer deadline, bounded cleanup reserve')
        signal.signal(signal.SIGALRM,deadline)
        signal.setitimer(signal.ITIMER_REAL,reg['campaign_total_seconds']-10)

        def monitor(members):
            nonlocal last_power
            now = time.monotonic()
            c.need(not cancelled and now-started < reg['campaign_total_seconds'], 'Campaign deadline/cancellation')
            c.check_lease(reg)
            rss = sum(x['rss_bytes'] for x in members) + int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) + c.process_rss(helper.pid)
            c.need(rss < reg['rss_bytes'], 'Aggregate observer/worker RSS ceiling')
            c.need(helper.poll() is None, 'Caffeinate exited')
            if now-last_power >= 5:
                c.power_assertions(os.getpid()); last_power=now

        environment = dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=str(cache))
        for index,job in enumerate(reg['jobs']):
            monitor([])
            out = c.HERE/'outputs'/job['id']
            c.need(not list(out.iterdir()), 'Job output already consumed')
            c.save(out/'dispatch.json',dict(worker_expected_job=job['id'],parent_pid=os.getpid(),
                registration_sha256=digest,campaign_started_monotonic=started,job_index=index))
            run_child(argv_for(reg,path,digest,job),out,environment,monitor,
                reg['work_seconds']+reg['receipt_seconds'])
            evidence = audit_job(reg,digest,job)
            c.save(out/'parent-job-audit.json',dict(status='accepted_training_trajectory',
                registration_sha256=digest,evidence=evidence,lease_cleared=False))
            completed.append(evidence)
        c.verify_pins(reg); monitor([])
        c.need(not list(cache.iterdir()), 'Frozen cache changed')
        c.need(sum(x['counts']['frames'] for x in completed) == 4*reg['frame_target'], 'Actual campaign frame total differs')
        c.save(c.HERE/'parent-terminal-audit.json',dict(schema='dodge_ray_training_parent_audit_v1',
            status='training_complete_pending_coordinator_acceptance',registration_sha256=digest,
            dispatch_sha256=args.sha256,trajectories=completed,elapsed_seconds=time.monotonic()-started,
            evaluation_games=0,cohort_D13_opened=False,lease_cleared=False,promoted=False))
        return 0
    except BaseException as error:
        if claimed:
            c.save(c.HERE/'first-failure.json',dict(status='first_failure_preserved_lease_held',
                error=repr(error),traceback=traceback.format_exc(),completed_jobs=completed,
                elapsed_seconds=time.monotonic()-started))
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        try:
            helper.terminate()
            helper.wait(timeout=5)
        except BaseException as error:
            if claimed and not (c.HERE/'first-failure.json').exists():
                c.save(c.HERE/'first-failure.json',dict(status='first_failure_preserved_lease_held',error=repr(error)))
            raise


if __name__ == '__main__':
    raise SystemExit(main())

