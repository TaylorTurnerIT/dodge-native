"""Reviewed exact-once owner for the disposable S1 profiling campaign."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import traceback

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def state_write(path, value):
    fd, temporary = tempfile.mkstemp(prefix='.track-a-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    reg_path = HERE / 'S1-registration.json'
    reg = read(reg_path)
    gate = read(HERE / 'S1-source-acceptance.json')
    assert gate['status'] == 'accepted_source_for_disposable_profile'
    assert gate['registration_sha256'] == sha(reg_path)
    assert gate['review_sha256'] == sha(gate['review_path'])
    assert read(gate['review_path'])['status'] == 'no_blocking_findings'
    assert not list((HERE / 'empty-pycache').iterdir())
    for path, digest in reg['input_pins'].items():
        assert sha(path) == digest, path
    ledger = Path(reg['state_path'])
    state = read(ledger)
    assert state.get('active_long_campaign') is None, 'Another campaign owns the lease'
    assert not (HERE / 'S1-launch.claimed').exists(), 'Campaign already claimed; no retry'
    state['active_long_campaign'] = reg['expected_lease']
    state_write(ledger, state)
    save(HERE / 'S1-launch.claimed', dict(pid=os.getpid(), registration_sha256=sha(reg_path)))
    started = time.monotonic()
    child = None
    receipts = []
    peaks = dict(aggregate_rss_bytes=0)
    cancellation = None

    def cancel(number, _frame):
        nonlocal cancellation
        cancellation = number

    signal.signal(signal.SIGTERM, cancel)
    signal.signal(signal.SIGINT, cancel)
    try:
        for index, cell in enumerate(reg['cells']):
            if cancellation or time.monotonic() - started > reg['work_wall_seconds']:
                raise RuntimeError('Campaign cancellation or work wall bound before cell')
            environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                               PYTHONPYCACHEPREFIX=str(HERE / 'empty-pycache'))
            child_started = time.monotonic()
            log = (HERE / 'S1-output' / ('cell-%02d.log' % index)).open('x')
            child = subprocess.Popen([reg['interpreter'], '-B', str(HERE / 'profile_s1.py'),
                                      '--cell', str(index)], env=environment, stdout=log,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            save(HERE / 'S1-output' / ('cell-%02d-launch.json' % index),
                 dict(pid=child.pid, pgid=child.pid, cell=cell, start_monotonic=child_started))
            try:
                while child.poll() is None:
                    elapsed = time.monotonic() - started
                    if cancellation or elapsed > reg['work_wall_seconds'] or time.monotonic() - child_started > reg['cell_wall_seconds'] + 10:
                        raise RuntimeError('Campaign cancellation or wall bound during cell')
                    measured = subprocess.run(['ps', '-o', 'rss=', '-p', str(child.pid) + ',' + str(os.getpid())],
                                              capture_output=True, text=True, timeout=3)
                    if measured.returncode == 0:
                        rss = sum(int(line) for line in measured.stdout.split()) * 1024
                        peaks['aggregate_rss_bytes'] = max(peaks['aggregate_rss_bytes'], rss)
                        if rss >= reg['resource_limit_bytes']:
                            raise RuntimeError('Aggregate6GiB RSS bound reached')
                    time.sleep(.5)
                code = child.wait()
                pid = child.pid
                try:
                    os.killpg(pid, 0)
                except ProcessLookupError:
                    absent = True
                else:
                    absent = False
                receipt = HERE / 'S1-output' / ('cell-%02d.json' % index)
                observed = dict(cell_index=index, raw_exit_code=code, directly_reaped=True,
                                pgid=pid, group_absent=absent, receipt_path=str(receipt),
                                receipt_sha256=sha(receipt) if receipt.exists() else None)
                save(HERE / 'S1-output' / ('cell-%02d-exit.json' % index), observed)
                receipts.append(observed)
                if code != 0 or not absent or not receipt.exists():
                    raise RuntimeError('First failed/missing profiling receipt; no retries')
                value = read(receipt)
                assert value['status'] == 'complete' and value['completed_updates_discarded'] == 1
                assert value['saved_weights'] is False and value['actual_saved_boundary'] is None
                assert value['resources']['rss_bytes'] < reg['resource_limit_bytes']
                assert value['resources']['mps_driver_bytes'] < reg['resource_limit_bytes']
                assert value['policy_decisions'] == cell['envs'] * cell['rollout_steps']
                print(json.dumps(dict(cell=index, config=cell, frames_per_second=value['raw_frames_per_second'],
                                      seconds=value['update_seconds'])), flush=True)
            finally:
                log.close()
        assert len(receipts) == len(reg['cells'])
        assert not list((HERE / 'empty-pycache').iterdir())
        assert not list((HERE / 'S1-output').glob('*.pt'))
        for path, digest in reg['input_pins'].items():
            assert sha(path) == digest, path
        assert read(ledger)['active_long_campaign'] == reg['expected_lease']
        audit = dict(schema='dodge_track_a_s1_terminal_audit_v1', status='accepted_disposable_profile',
            registration_sha256=sha(reg_path), receipts=receipts, completed_cells=len(receipts),
            elapsed_seconds=time.monotonic() - started, resources=peaks,
            checkpoint_unchanged=True, empty_cache_verified=True, no_trained_weights_saved=True,
            training_campaign_launched=False, disposable_update_count=len(receipts),
            promoted=False, lease_cleared=False)
        audit_path = HERE / 'S1-terminal-audit.json'
        save(audit_path, audit)
        state = read(ledger)
        assert state['active_long_campaign'] == reg['expected_lease']
        state['active_long_campaign'] = None
        state_write(ledger, state)
        save(HERE / 'S1-lease-release.json', dict(parent_audit_sha256=sha(audit_path),
            exact_lease=reg['expected_lease'], lease_value_after_release=None))
        return 0
    except BaseException as exc:
        cleanup = None
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)
            cleanup = dict(pid=child.pid, directly_reaped=True, raw_exit_code=child.returncode)
        save(HERE / 'S1-first-failure.json', dict(status='first_failure_preserved_lease_held',
            failure=repr(exc), traceback=traceback.format_exc(), receipts=receipts, cleanup=cleanup,
            elapsed_seconds=time.monotonic() - started, resources=peaks,
            lease_value=read(ledger).get('active_long_campaign')))
        raise


if __name__ == '__main__':
    sys.exit(main())
