"""Accept the zero-compute r1 failure only after explicit user disposition approval."""
import argparse
import os
from pathlib import Path

from run_s1 import HERE, read, save, sha, state_write


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--approval', required=True)
    parser.add_argument('--approval-sha256', required=True)
    args = parser.parse_args()
    assert sha(args.approval) == args.approval_sha256
    approval = read(args.approval)
    successor = read(HERE / 'S1-registration.json')
    assert approval['approved_run_id'] == successor['run_id']
    assert approval['one_disposable_profiling_attempt'] is True
    assert approval['failed_r1_lease_disposition_authorized'] is True
    old = HERE.parent / 'track-a-review-scaling-parent-20261030-r1'
    registered = read(old / 'S1-registration.json')
    failure = read(old / 'S1-first-failure.json')
    exit_receipt = read(old / 'S1-output/cell-00-exit.json')
    cell = read(old / 'S1-output/cell-00.json')
    assert failure['status'] == 'first_failure_preserved_lease_held'
    assert len(failure['receipts']) == 1
    assert exit_receipt['raw_exit_code'] == 1 and exit_receipt['directly_reaped'] is True
    assert exit_receipt['group_absent'] is True
    assert exit_receipt['receipt_sha256'] == sha(old / 'S1-output/cell-00.json')
    assert cell['failure'] == 'ModuleNotFoundError("No module named \'torch\'")'
    assert cell['partial_timings_seconds'] == {} and cell['saved_weights'] is False
    try:
        os.killpg(exit_receipt['pgid'], 0)
    except ProcessLookupError:
        pass
    else:
        raise RuntimeError('Failed worker group is present; disposition refused')
    for path, digest in registered['input_pins'].items():
        assert sha(path) == digest, path
    assert not list((old / 'empty-pycache').iterdir())
    state_path = Path(registered['state_path'])
    state = read(state_path)
    assert state['active_long_campaign'] == registered['expected_lease']
    receipts = [old / 'S1-registration.json', old / 'S1-first-failure.json',
                old / 'S1-output/cell-00-exit.json', old / 'S1-output/cell-00.json']
    audit = dict(schema='dodge_track_a_s1_failed_attempt_disposition_v1',
        status='accepted_failed_zero_compute_attempt',
        authority_sha256=args.approval_sha256, input_pins={str(path): sha(path) for path in receipts},
        first_failure_preserved=True, games_constructed=0, optimizer_steps=0,
        performance_result=False, retry_of_original=False, lease_cleared=False,
        successor_run_id=successor['run_id'])
    audit_path = HERE / 'S1-r1-failure-disposition-audit.json'
    save(audit_path, audit)
    state = read(state_path)
    assert state['active_long_campaign'] == registered['expected_lease']
    state['active_long_campaign'] = None
    state_write(state_path, state)
    save(HERE / 'S1-r1-disposition-lease-release.json',
         dict(parent_audit_sha256=sha(audit_path), exact_lease=registered['expected_lease'],
              lease_value_after_release=None))


if __name__ == '__main__':
    main()
