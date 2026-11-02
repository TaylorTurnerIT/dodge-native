"""One import/tiny-device qualification; never constructs a game or learner."""
import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import resource
import signal
import subprocess
import sys
import tempfile

OUT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--accepted-code', required=True)
parser.add_argument('--self-test', action='store_true')
parser.add_argument('--worker', action='store_true')
args = parser.parse_args()
CODE = Path(args.accepted_code).resolve()
sys.path.insert(0, str(CODE))
import common as c
from lifecycle import run_child, group_members
c.RUN = OUT


def machine():
    raw = subprocess.check_output(['/usr/sbin/ioreg', '-rd1', '-c', 'IOPlatformExpertDevice'], text=True)
    uuid = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', raw).group(1)
    return dict(environment_id='20659a2f-1b36-4ab6-9cd6-b191b8f5dd09',
                platform_uuid_sha256=hashlib.sha256(uuid.encode()).hexdigest(),
                architecture=os.uname().machine)


def validate_state(state, identity):
    c.need(state['schema'] == 'dodge_machine_accelerator_v1' and state['machine'] == identity,
           'Host ledger identity differs')


def initialize(reg, identity):
    path = Path(reg['state_path'])
    path.parent.mkdir(parents=True, exist_ok=True)
    c.need(not path.is_symlink() and not path.parent.is_symlink(), 'Ledger symlink forbidden')
    with (path.parent / 'horizon-ledger.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not path.exists():
            c.save(path, dict(schema='dodge_machine_accelerator_v1', machine=identity,
                   active_long_campaign=None, active_inference_diagnostic=None))
        validate_state(c.read(path), identity)


def release(reg, identity, audit_path):
    path = Path(reg['state_path'])
    with (path.parent / 'horizon-ledger.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = c.read(path)
        validate_state(state, identity)
        c.need(state['active_long_campaign'] == reg['expected_lease'], 'Exact release holder differs')
        audit = c.read(audit_path)
        c.need(audit['status'] == 'accepted_M1_import_tiny_device_only'
               and audit['machine'] == identity and audit['lease'] == reg['expected_lease']
               and audit['worker_exit']['directly_reaped'] and audit['worker_exit']['group_absent'],
               'Accepted durable cleanup audit required before release')
        state['active_long_campaign'] = None
        tmp = path.parent / ('.M1-qualification-release-' + str(os.getpid()))
        with tmp.open('x') as stream:
            json.dump(state, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        c.sync_directory(path.parent)
        return c.sha(audit_path)


def guard(reg):
    validate_state(c.read(reg['state_path']), machine())
    c.check_lease(reg)


def protected_processes():
    rows = subprocess.check_output(['/bin/ps', '-axo', 'pid=,comm='], text=True)
    pids = [int(row.split(None, 1)[0]) for row in rows.splitlines()
            if len(row.split(None, 1)) == 2 and 'voxtype' in row.lower()]
    pids.append(32167)  # Readiness identified the protected Phonon server.
    result = []
    for pid in sorted(set(pids)):
        r = subprocess.run(['/bin/ps', '-p', str(pid), '-o', 'pid=,lstart=,comm='],
                           text=True, capture_output=True)
        if r.returncode == 0 and r.stdout.strip():
            result.append(dict(pid=pid, identity=r.stdout.strip()))
    return result


def worker(reg):
    guard(reg)
    import numpy as np
    import dodge_rl
    import dodge_rl._native as native
    import torch
    c.need(Path(native.__file__).resolve() == Path(reg['runtime_root']) / 'dodge_rl/_native.cpython-312-darwin.so',
           'Native module origin differs')
    c.need(Path(dodge_rl.__file__).resolve() == Path(reg['runtime_root']) / 'dodge_rl/__init__.py',
           'Runtime package origin differs')
    c.need(torch.__version__ == reg['versions']['torch'] and np.__version__ == reg['versions']['numpy'],
           'Imported dependency version differs')
    c.need(torch.backends.mps.is_available(), 'Actual MPS unavailable')
    guard(reg)
    torch.set_num_threads(1)
    torch.set_grad_enabled(False)
    x = torch.arange(16, dtype=torch.float32, device='mps').reshape(4, 4)
    y = x @ torch.eye(4, dtype=torch.float32, device='mps')
    torch.mps.synchronize()
    finite = bool(torch.isfinite(y).all().item())
    exact = torch.equal(y.cpu(), torch.arange(16, dtype=torch.float32).reshape(4, 4))
    rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    driver = int(torch.mps.driver_allocated_memory())
    c.need(finite and exact and y.device.type == 'mps', 'Finite/device/exact result differs')
    c.need(rss < reg['rss_bytes'] and driver < reg['mps_bytes'], 'Separate memory ceiling exceeded')
    guard(reg)
    c.save(OUT / 'worker/result.json', dict(status='finite_exact_4x4_MPS_matmul_and_native_import',
           native_path=native.__file__, torch_path=torch.__file__, numpy_path=np.__file__,
           device=str(y.device), finite=finite, exact=exact, rss_bytes=rss, mps_driver_bytes=driver,
           gameplay_frames=0, optimizer_steps=0, checkpoint_loads=0, models_constructed=0))


def self_test():
    identity = dict(environment_id='fixture', platform_uuid_sha256='fixture', architecture='arm64')
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'state.json'
        reg = dict(state_path=str(path), expected_lease=dict(owner_token='fixture'))
        initialize(reg, identity)
        try:
            initialize(reg, dict(identity, environment_id='foreign'))
        except ValueError:
            pass
        else:
            raise AssertionError('Foreign host accepted')
        c.cas_ledger(reg, None, reg['expected_lease'])
        try:
            c.cas_ledger(reg, None, dict(owner_token='contender'))
        except ValueError:
            pass
        else:
            raise AssertionError('Contender accepted')
        try:
            release(reg, identity, Path(directory) / 'absent-audit.json')
        except FileNotFoundError:
            pass
        else:
            raise AssertionError('Unaudited release accepted')
        assert c.read(path)['active_long_campaign'] == reg['expected_lease']
    print('Three targeted admission/release delta checks passed; no device work.')


def main():
    reg = c.read(OUT / 'qualification-registration.json')
    c.verify_pins(reg)
    c.need(reg['no_wallclock_deadline'] and reg['gameplay_frames'] == 0 and reg['optimizer_steps'] == 0,
           'Preparation scope differs')
    if args.worker:
        worker(reg)
        return
    review = c.read(OUT / 'qualification-review.json')
    c.need(review['status'] == 'accepted' and review['registration_sha256'] == c.sha(OUT / 'qualification-registration.json')
           and review['source_sha256'] == c.sha(__file__) and review['blockers'] == [], 'Exact review required')
    identity = machine()
    c.need(identity == reg['machine'], 'Registered M1 identity differs')
    c.need(os.uname().machine == 'arm64' and sys.platform == 'darwin', 'Darwin arm64 required')
    for name, version in reg['versions'].items():
        c.need(importlib.metadata.version(name) == version, 'Installed dependency differs: ' + name)
    c.need(not (OUT / 'qualification.claimed').exists(), 'No qualification retry')
    for name in ['worker', 'empty-pycache']:
        (OUT / name).mkdir()
    def cancel(*_):
        raise c.CampaignStop('User cancelled qualification')
    signal.signal(signal.SIGTERM, cancel)
    signal.signal(signal.SIGINT, cancel)
    protected = protected_processes()
    process_text = subprocess.check_output(['/bin/ps', '-axo', 'pid=,command='], text=True)
    c.need(not any(pattern in process_text for pattern in ['local_performance_loop/owner.py',
           'local_performance_loop/worker.py', 'train_teacher.py --', 'teacher_ray_training_worker.py --']),
           'Existing project accelerator command requires coordination')
    pressure = subprocess.check_output(['/usr/bin/memory_pressure', '-Q'], text=True)
    percent = re.search(r'System-wide memory free percentage:\s*(\d+)%', pressure)
    c.need(percent is not None and int(percent.group(1)) >= 20, 'Host pressure lacks qualification headroom')
    c.save(OUT / 'qualification.claimed', dict(owner_pid=os.getpid(), registration_sha256=c.sha(OUT / 'qualification-registration.json')))
    try:
        initialize(reg, identity)
        c.cas_ledger(reg, None, reg['expected_lease'])
        c.save(OUT / 'admission.json', dict(machine=identity, lease=reg['expected_lease'],
               state_path=reg['state_path'], protected=protected, pressure=pressure, no_claim_of_GPU_idle=True))
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPYCACHEPREFIX=str(OUT / 'empty-pycache'),
                           PYTHONPATH=reg['runtime_root'], PYTORCH_ENABLE_MPS_FALLBACK='0', OMP_NUM_THREADS='1')
        def monitor(members):
            guard(reg)
            c.need(sum(r['rss_bytes'] for r in members) + resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                   < reg['rss_bytes'], 'Aggregate RSS ceiling exceeded')
        exit_receipt = run_child([sys.executable, '-B', str(Path(__file__).resolve()), '--accepted-code', str(CODE), '--worker'],
                                 OUT / 'worker', environment, monitor, timeout=None)
        guard(reg)
        c.verify_pins(reg)
        c.need(not group_members(exit_receipt['pgid']) and protected_processes() == protected,
               'Owned group/protected process identity changed')
        result = c.read(OUT / 'worker/result.json')
        c.need(result['finite'] and result['exact'] and result['device'].startswith('mps')
               and result['mps_driver_bytes'] < reg['mps_bytes'] and result['rss_bytes'] < reg['rss_bytes'],
               'Strict tiny-device result differs')
        c.need(not list((OUT / 'empty-pycache').rglob('*')), 'Bytecode cache changed')
        c.need(not any('failure' in p.name or p.name.endswith('.partial') for p in OUT.rglob('*')),
               'Failure or partial forbids acceptance')
        audit_path = OUT / 'qualification-audit.json'
        c.save(audit_path, dict(status='accepted_M1_import_tiny_device_only', machine=identity,
               lease=reg['expected_lease'], worker_exit=exit_receipt, worker_result=result,
               worker_result_sha256=c.sha(OUT / 'worker/result.json'),
               worker_exit_sha256=c.sha(OUT / 'worker/exit.json'),
               registration_sha256=c.sha(OUT / 'qualification-registration.json'),
               limits='No game constructor, model/checkpoint load, optimizer, survival evaluation, or training-workload qualification.'))
        audit_hash = release(reg, identity, audit_path)
        c.save(OUT / 'lease-release.json', dict(accepted_audit_sha256=audit_hash, machine=identity,
               previous_lease=reg['expected_lease'], lease_value_after_release=None))
        print(json.dumps(dict(status='accepted_M1_import_tiny_device_only', audit_sha256=audit_hash,
                             release_sha256=c.sha(OUT / 'lease-release.json'))))
    except BaseException as error:
        c.save(OUT / 'qualification-first-failure.json', dict(status='blocked_preserve_first_failure_no_retry',
               error_class=type(error).__name__, reason=str(error), no_lease_clear=True))
        raise


if __name__ == '__main__':
    self_test() if args.self_test else main()
