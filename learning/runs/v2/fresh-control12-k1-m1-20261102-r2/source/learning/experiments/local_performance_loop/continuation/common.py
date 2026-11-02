"""Warm-start profile. Reuse frozen control helpers without editing them."""
import importlib.util
import importlib.metadata
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

CODE = Path(__file__).resolve().parent
sys.path.insert(1, str(CODE.parent))
spec = importlib.util.spec_from_file_location('_accepted_loop_common', CODE.parent / 'common.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
for name in dir(base):
    if not name.startswith('_') and name not in ('CODE', 'HERE', 'RUN'):
        globals()[name] = getattr(base, name)
HERE = CODE
RUN = None


def machine_identity():
    raw = subprocess.check_output(['/usr/sbin/ioreg', '-rd1', '-c', 'IOPlatformExpertDevice'], text=True)
    uuid = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', raw).group(1)
    return dict(environment_id='20659a2f-1b36-4ab6-9cd6-b191b8f5dd09',
                platform_uuid_sha256=hashlib.sha256(uuid.encode()).hexdigest(), architecture=os.uname().machine)


def machine_state(reg, state):
    need(state['schema'] == 'dodge_machine_accelerator_v1' and state['machine'] == reg['machine'],
         'Machine-bound host ledger differs')


def check_lease(reg):
    state = read(reg['state_path'])
    machine_state(reg, state)
    need(state['active_long_campaign'] == reg['expected_lease'] and state['active_inference_diagnostic'] is None,
         'Exact machine lease lost')
    need(not (RUN / 'cancel.requested').exists(), 'User cancelled continuation')


base.check_lease = check_lease


def cas_ledger(reg, expected, replacement):
    path = Path(reg['state_path'])
    need(path.is_file() and not path.is_symlink(), 'Existing M1 ledger required; never initialize/reset')
    with (path.parent / 'horizon-ledger.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read(path)
        machine_state(reg, state)
        need(state['active_long_campaign'] == expected and state['active_inference_diagnostic'] is None,
             'Exact shared accelerator CAS differs')
        state['active_long_campaign'] = replacement
        temporary = path.parent / ('.continuation-state-' + str(os.getpid()))
        with temporary.open('x') as stream:
            json.dump(state, stream, sort_keys=True)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path); sync_directory(path.parent)


def load_registration(path, digest):
    global RUN
    need(sha(path) == digest, 'Config hash differs')
    reg = read(path); RUN = Path(reg['run_dir']).resolve(); base.RUN = RUN
    need(reg['schema'] == 'local_performance_continuation_v1' and Path(reg['runner']).resolve() == CODE,
         'Continuation profile identity differs')
    need(reg['execution_authorized'] and reg['training_authorized'] and not reg['cloud_authorized']
         and not reg['promotion'] and reg['job_order'] == ['control'], 'Exact one-control scope differs')
    need(reg['envs'] == 64 and reg['rollout'] == 1024 and reg['action_repeat'] == 1
         and reg['effective_minibatch'] == 2048 and reg['microbatch'] == 512, 'Accepted K1 batch shape differs')
    need(reg['initial_updates'] == 72 and reg['segment_updates'] == 12 and reg['prefix_updates'] == 2,
         'Counted/observation horizons differ')
    need(reg['work_seconds'] is None and reg['total_seconds'] is None and not reg['forecast_fit_gate'],
         'No elapsed-time cancellation or forecast admission')
    need(reg['rss_bytes'] == reg['mps_bytes'] == 6 * 1024**3 and reg['no_retry'] and reg['no_automatic_resume'],
         'Resource/first-attempt controls differ')
    need(reg['evaluation_seeds'] == list(range(3657433088, 3657433600))
         and reg['evaluation_controller_domain'] == 'dodge068/paired-policy-v1', 'Consumed development controller differs')
    accepted_recipe = read(reg['source_config_path'])
    expected = dict(accepted_recipe['ppo'], learning_rate=1e-5)
    need(reg['ppo'] == expected and reg['arms']['control'] == accepted_recipe['arms']['control'],
         'Only LR may change the learning recipe')
    need(reg['exclusions'] == accepted_recipe['exclusions'], 'Seed support exclusions changed')
    need(reg['warmstart']['sha256'] == '04171886ad1d200f58579952519e972610f9518ddd32af54d25b817204d072b8'
         and reg['checkpoint_sha256'] == '7e0de8640f1337261412d91cde6bc692772ff212fbd360f5aad415dc6bc7ed4b',
         'Exact control12/420 identities differ')
    verify_pins(reg); verify_runtime_members(reg)
    need(not list(Path(reg['cache']).rglob('*')), 'Bytecode cache changed')
    need(read(reg['accepted067_path'])['status'] == 'accepted_local_performance_loop'
         and read(reg['accepted_M1_path'])['status'] == 'accepted_M1_import_tiny_device_only', 'Accepted input proof missing')
    provenance = read(reg['development_provenance'])
    need(provenance['role'] == 'exposed_development_diagnostic_not_confirmation'
         and provenance['range_inclusive'] == [3657433088,3657435135], 'Development reuse provenance differs')
    return reg


def verify_environment(reg):
    need(machine_identity() == reg['machine'] and sys.platform == 'darwin' and os.uname().machine == 'arm64',
         'Registered M1 required')
    need(sys.version_info[:3] == (3,12,15) and Path(sys.executable).absolute() == Path(reg['interpreter']).absolute(),
         'Prepared interpreter identity differs')
    for name, version in reg['versions'].items():
        need(importlib.metadata.version(name) == version, 'Exact installed dependency differs: ' + name)


def protected_identities():
    rows = subprocess.check_output(['/bin/ps','-axo','pid=,command='],text=True)
    pids = [int(line.split(None,1)[0]) for line in rows.splitlines()
            if len(line.split(None,1)) == 2 and any(x in line.lower() for x in ('phonon-dictation/venv/bin/python','voxtype-bin'))]
    return [subprocess.check_output(['/bin/ps','-p',str(pid),'-o','pid=,lstart=,comm='],text=True).strip()
            for pid in sorted(set(pids))]
