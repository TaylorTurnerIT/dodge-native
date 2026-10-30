"""Reviewed, exactly-once failed-owner handoff for the authorized teacher screens.

No games, imports of a learning runtime, null lease clearing, or process launch.
The coordinator launches the returned immutable dispatch exactly once afterward.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import traceback

ROOT = Path(__file__).resolve().parents[2]
QUEUE = ROOT / 'learning/runs/v2/teacher-training-queue-parent-20261030-r1'
PREDECESSOR = ROOT / 'learning/runs/v2/k1-horizon-screen-20261030-r2'
PREDECESSOR_SHA = '6bf2ea8860a33bf891ae08e63bfd70093f4256ed0f58774497630c6e9d55633c'


def need(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save(path, value):
    path = Path(path)
    temporary = Path(str(path) + '.partial')
    with temporary.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.link(temporary, path)
    fsync_dir(path.parent)
    temporary.unlink(); fsync_dir(path.parent)
    return sha(path)


def exact_handoff(state_path, expected, replacement):
    """Preserve unrelated ledger data; never pass through an unowned/null state."""
    need(expected is not None and replacement is not None and expected != replacement,
         'An exact non-null old-to-new lease is required')
    path = Path(state_path)
    with (path.parent / 'horizon-ledger.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read(path)
        need(state.get('active_long_campaign') == expected, 'Exact predecessor lease differs')
        state['active_long_campaign'] = replacement
        temporary = path.parent / ('.coordinator-state-' + str(os.getpid()))
        with temporary.open('x') as f:
            json.dump(state, f, indent=2, sort_keys=True, allow_nan=False)
            f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(temporary, path); fsync_dir(path.parent)


def failed_predecessor_audit():
    path = PREDECESSOR / 'registration-r1.json'
    need(sha(path) == PREDECESSOR_SHA, 'Failed predecessor registration changed')
    old = read(path)
    for pin, digest in {**old['source_pins'], **old['input_pins']}.items():
        need(sha(pin) == digest, 'Failed predecessor pin changed: ' + pin)
    parent = read(PREDECESSOR / 'first-failure.json')
    worker = read(PREDECESSOR / 'outputs/r1-shorter/first-failure.json')
    exit_receipt = read(PREDECESSOR / 'outputs/r1-shorter/exit.json')
    accepted = read(PREDECESSOR / 'outputs/r1-matched/parent-job-audit.json')
    need(worker['error'] == "ValueError('AC power required')"
         and parent['completed_jobs'] == [accepted['evidence']]
         and accepted['status'] == 'accepted_training_trajectory', 'Failure evidence differs')
    need(exit_receipt['raw_exit_code'] == exit_receipt['observed_exit_code'] == 1
         and exit_receipt['directly_reaped'] and exit_receipt['group_absent'], 'Failure child not reaped')
    need(parent['lease_value'] == old['expected_lease'], 'Failed lease evidence differs')
    need(not (PREDECESSOR / 'parent-terminal-audit.json').exists()
         and not (PREDECESSOR / 'lease-release.json').exists(), 'Failure unexpectedly accepted/released')
    cache = PREDECESSOR / 'empty-pycache'
    need(cache.is_dir() and not list(cache.iterdir()), 'Failed cache changed')
    rows = subprocess.check_output(['/bin/ps', '-axo', 'pid=,pgid='], text=True).splitlines()
    old_groups = {read(PREDECESSOR / 'launch.claimed')['pid'],
                  read(PREDECESSOR / 'outputs/r1-matched/exit.json')['pgid'], exit_receipt['pgid']}
    need(not any(len(row.split()) == 2 and int(row.split()[1]) in old_groups for row in rows),
         'Failed predecessor group remains')
    return dict(schema='reviewed_failed_campaign_successor_disposition_v1',
        status='accepted_failure_disposition_for_exact_handoff', record='DODGE-051',
        old_campaign_failed=True, retry_authorized=False, all_owned_processes_absent=True,
        old_pins_unchanged=True, exact_old_lease=old['expected_lease'],
        old_registration_sha256=PREDECESSOR_SHA,
        parent_first_failure_sha256=sha(PREDECESSOR / 'first-failure.json'),
        worker_first_failure_sha256=sha(PREDECESSOR / 'outputs/r1-shorter/first-failure.json'),
        child_exit_sha256=sha(PREDECESSOR / 'outputs/r1-shorter/exit.json'),
        state_path=old['state_path'], failed_campaign_accepted_as_success=False)


def validate(plan):
    for key in ['registration', 'review', 'readiness', 'authority']:
        need(sha(plan[key + '_path']) == plan[key + '_sha256'], key + ' hash differs')
    reg = read(plan['registration_path']); review = read(plan['review_path'])
    authority = read(plan['authority_path']); readiness = read(plan['readiness_path'])
    need(reg['record'] in ['DODGE-053', 'DODGE-054', 'DODGE-055']
         and plan['record'] == reg['record'], 'Unapproved training record')
    need(review['status'] == 'no_blocking_findings'
         and review['registration_sha256'] == plan['registration_sha256'], 'Exact review absent')
    need(review['coordinator_source_pins'][str(Path(__file__).resolve())] == sha(__file__),
         'Coordinator handoff source is not independently reviewed')
    need(readiness['registration_sha256'] == plan['registration_sha256'], 'Readiness differs')
    need(authority['schema'] == 'teacher_training_queue_authority_v2'
         and authority['limits']['AC_required'] is False
         and authority['first_screens_only'] and authority['no_claim_or_lease_reset'],
         'Battery-allowed bounded authority absent')
    need(Path(plan['authority_path']).resolve() == QUEUE.resolve() / 'authority-r2.json', 'Wrong authority')
    authority_key = 'coordinator_authority' if 'coordinator_authority_path' in reg else 'authority'
    need(reg[authority_key + '_path'] == plan['authority_path']
         and reg[authority_key + '_sha256'] == plan['authority_sha256'],
         'Registration authority differs from dispatch')
    need(len(reg['jobs']) == 4 and reg['frame_target'] == (
        11796480 if reg['record'] == 'DODGE-053' else 2359296), 'Screen exposure differs')
    need(reg['work_seconds'] == 5400 and reg['receipt_seconds'] == 180
         and reg['campaign_total_seconds'] == 22320
         and reg['rss_bytes'] == reg['mps_bytes'] == 6 * 2**30, 'Screen limits differ')
    for path, digest in {**reg['source_pins'], **reg['input_pins']}.items():
        need(sha(path) == digest, 'Successor pin changed: ' + path)
    package = Path(reg['package'])
    need(not (package / 'launch.claimed').exists() and not (package / 'attempt.claimed').exists(),
         'Successor already consumed')
    cache = package / 'empty-pycache'
    need(cache.is_dir() and not list(cache.iterdir()), 'Successor existing empty cache required')
    template = plan['dispatch_template']
    need(template['record'] == reg['record'] and template['expected_lease'] == reg['expected_lease'],
         'Dispatch record/lease differs')
    for key in ['registration', 'review', 'readiness', 'authority']:
        need(template[key + '_path'] == plan[key + '_path']
             and template[key + '_sha256'] == plan[key + '_sha256'], 'Dispatch binding differs: ' + key)
    return reg


def dispatch(plan, directory):
    reg = validate(plan)
    disposition = failed_predecessor_audit()
    need(read(disposition['state_path']).get('active_long_campaign') == disposition['exact_old_lease'],
         'Exact failed lease not held')
    directory = Path(directory)
    need(directory.parent.resolve() == QUEUE.resolve(), 'Dispatch evidence must be coordinator-owned')
    directory.mkdir(exist_ok=True)
    need(not list(directory.iterdir()), 'Dispatch evidence directory already consumed')
    save(directory / 'dispatch.claimed', dict(record=reg['record'], pid=os.getpid(),
         registration_sha256=plan['registration_sha256']))
    try:
        disposition['successor_registration_sha256'] = plan['registration_sha256']
        disposition['review_sha256'] = plan['review_sha256']
        disposition_path = directory / 'failure-disposition.json'
        disposition_sha = save(disposition_path, disposition)
        exact_handoff(disposition['state_path'], disposition['exact_old_lease'], reg['expected_lease'])
        handoff_path = directory / 'lease-handoff.json'
        handoff_sha = save(handoff_path, dict(previous_lease=disposition['exact_old_lease'],
            replacement_lease=reg['expected_lease'], never_cleared_to_null=True,
            registration_sha256=plan['registration_sha256'], failure_disposition_sha256=disposition_sha))
        document = dict(plan['dispatch_template'], failure_disposition_path=str(disposition_path),
            failure_disposition_sha256=disposition_sha, handoff_path=str(handoff_path), handoff_sha256=handoff_sha)
        path = directory / 'dispatch.json'
        digest = save(path, document)
        return dict(dispatch_path=str(path), dispatch_sha256=digest, exact_lease=reg['expected_lease'])
    except BaseException as error:
        save(directory / 'first-failure.json', dict(error=repr(error), traceback=traceback.format_exc(),
            lease_value=read(disposition['state_path']).get('active_long_campaign'), retry=False))
        raise


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--plan', required=True)
    parser.add_argument('--plan-sha256', required=True); parser.add_argument('--output', required=True)
    args = parser.parse_args()
    need(sha(args.plan) == args.plan_sha256, 'Dispatch plan hash differs')
    print(json.dumps(dispatch(read(args.plan), args.output), sort_keys=True))


if __name__ == '__main__':
    main()
