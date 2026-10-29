"""Accept the preserved zero-worker failure before releasing its exact lease."""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OLD_PARENT = ROOT / 'learning/runs/v2/one-frame-training-comparison-parent-20261029-r1'
OLD_PACKAGE = ROOT / 'learning/runs/v2/one-frame-training-comparison-luna-20261029-r1'
STATE = ROOT / 'learning/runs/v2-orchestration/state.json'


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def publish(path, document):
    """Exclusive durable receipt; never replace prior evidence."""
    with Path(path).open('x') as stream:
        json.dump(document, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    descriptor = os.open(Path(path).parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main():
    authorization = read(HERE / 'user-authorization.json')
    need(authorization['fresh_bounded_qualification_authorized'] is True,
         'fresh bounded qualification is not authorized')
    incident_path = OLD_PARENT / 'qualification-first-failure-r6.json'
    need(sha(incident_path) == '429abd6043da4b82264732fcb376e0a25595a408a90491c68901c76bfa107a96',
         'preserved first failure differs')
    incident = read(incident_path)
    for path, digest in incident['pins'].items():
        need(sha(path) == digest, 'preserved failure pin differs: ' + path)
    control = OLD_PACKAGE / 'qualification-control'
    exit_receipt = read(control / 'execution-exit.json')
    execution = read(control / 'dispatch' / incident['run_id'] / 'execution-result.json')
    need(exit_receipt['raw_observer_exit_code'] == 1
         and exit_receipt['observer_directly_reaped'] is True,
         'failed observer was not directly reaped')
    need(execution['actual_worker_launch_count'] == 0
         and execution['worker_ownership_state'] == 'not_launched'
         and execution['first_event'] == incident['first_event'],
         'first zero-worker failure evidence differs')
    need(not (control / 'worker-output').exists(), 'unexpected worker output exists')
    need(not list(control.rglob('worker-launch.json')), 'unexpected worker-launch receipt exists')
    try:
        os.killpg(exit_receipt['observer_pgid'], 0)
    except ProcessLookupError:
        pass
    else:
        raise RuntimeError('old observer process group still exists')
    claims = {str(path): sha(path) for path in control.rglob('*.claimed')}
    need(len(claims) == 4, 'failed attempt claim set differs')
    state_bytes = STATE.read_bytes()
    state = json.loads(state_bytes)
    expected = incident['exact_lease_preserved']
    need(state.get('active_long_campaign') == expected, 'exact failed lease differs')
    for key in ('active_inference_diagnostic', 'active_inference_campaign', 'active_inference_lease'):
        need(state.get(key) is None, 'conflicting lease exists: ' + key)
    pending = STATE.with_name('state.dodge013-failure-disposition.pending.json')
    need(not pending.exists(), 'failure-disposition pending state exists')
    need(not STATE.with_name('state.one-frame-training-comparison.pending.json').exists(),
         'old campaign pending state exists')
    accepted = dict(
        schema='dodge013_failed_qualification_parent_disposition_v1',
        status='failed_zero_worker_attempt_accepted_closed_no_reuse',
        run_id=incident['run_id'], first_failure_sha256=sha(incident_path),
        incident_pins=incident['pins'], preserved_claims=claims,
        raw_observer_exit_code=1, observer_directly_reaped=True,
        observer_process_group_absent=True, actual_worker_launch_count=0,
        training_updates=0, native_games=0, D9_seed_use=False,
        lease_before=expected, state_before_sha256=hashlib.sha256(state_bytes).hexdigest(),
        user_authorization_sha256=sha(HERE / 'user-authorization.json'),
        disposition='Release only the exact failed lease after this durable disposition; preserve source, claims and receipts.',
        failed_attempt_success=False, qualification_passed=False,
        marker_reset=False, retry_of_failed_registration_authorized=False,
        official_parent_unchanged=324,
    )
    publish(HERE / 'failure-disposition.json', accepted)
    need(STATE.read_bytes() == state_bytes, 'state changed before exact lease release')
    state['active_long_campaign'] = None
    state['last_update_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    publish(pending, state)
    need(STATE.read_bytes() == state_bytes, 'state changed during exact lease release')
    os.replace(pending, STATE)
    descriptor = os.open(STATE.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    need(read(STATE) == state, 'state release readback differs')
    need(all(sha(path) == digest for path, digest in claims.items()), 'failed claim changed')
    publish(HERE / 'lease-release.json', dict(
        schema='dodge013_failed_qualification_exact_lease_release_v1',
        run_id=incident['run_id'], lease_before=expected, lease_after=None,
        state_after_sha256=sha(STATE), failure_disposition_sha256=sha(HERE / 'failure-disposition.json'),
        preserved_claims=claims, lease_released=True, qualification_passed=False,
    ))
    print(json.dumps(dict(status='failed_attempt_closed_exact_lease_released',
                          first_failure_preserved=True, qualification_passed=False)))


if __name__ == '__main__':
    main()
