"""Strict stdlib control helpers for the separately registered horizon screen."""
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import time

HERE = Path(__file__).resolve().parent
STREAM_DOMAIN = b'dodge_ray_uniform512_v1\0'


class CampaignStop(BaseException):
    """Deadline/cancellation must not be swallowed as a passive probe error."""


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


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def publish(path, writer):
    path = Path(path)
    temporary = Path(str(path) + '.partial')
    with temporary.open('xb') as f:
        writer(f)
        f.flush()
        os.fsync(f.fileno())
    os.link(temporary, path)
    sync_directory(path.parent)
    temporary.unlink()
    sync_directory(path.parent)
    return sha(path)


def save(path, value):
    data = json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode() + b'\n'
    return publish(path, lambda f: f.write(data))


class Journal:
    def __init__(self, path):
        self.f = Path(path).open('x', buffering=1)

    def emit(self, value):
        self.f.write(canonical(value).decode() + '\n')

    def sync(self):
        self.f.flush()
        os.fsync(self.f.fileno())

    def close(self):
        self.sync()
        self.f.close()


def verify_pins(reg):
    for path, digest in {**reg['input_pins'], **reg['source_pins']}.items():
        need(sha(path) == digest, 'Pinned input changed: ' + path)


def load_registration(path, digest):
    need(sha(path) == digest, 'Registration hash differs')
    reg = read(path)
    need(reg['schema'] == 'dodge_ray_training_registration_v1'
         and Path(reg['package']).resolve() == HERE, 'Registration package/schema differs')
    need(reg['no_retry'] and reg['no_automatic_resume'] and not reg['promotion'], 'Lifecycle policy differs')
    need(reg['envs'] == 64 and reg['rollout'] == 1024 and reg['frame_target'] == 2359296
         and reg['updates'] == 36 and reg['microbatch'] == 512 and reg['effective_minibatch'] == 2048,
         'Registered screen shape differs')
    need(reg['record'] == 'DODGE-066' and reg['action_repeat'] == 1, 'Wrong record/K')
    need(reg['state_path'] == reg['coordinator_state_path'], 'Independent ledger forbidden')
    need(reg['AC_required'] is False and reg['battery_operation_allowed'] is True,
         'Future packet requires battery-allowed policy')
    verify_pins(reg)
    verify_runtime_members(reg)
    return reg


def verify_runtime_members(reg):
    members = {str(p.relative_to(reg['runtime_root'])) for p in Path(reg['runtime_root']).rglob('*') if p.is_file()}
    need(members == set(reg['runtime_members']), 'Runtime member set drift')


def check_lease(reg):
    need(read(reg['state_path']).get('active_long_campaign') == reg['expected_lease'], 'Campaign lease lost')
    need(not (HERE / 'cancel.requested').exists(), 'Parent cancellation requested')


def passive_power():
    """Power source/percentage never authorize stopping or changing a recipe."""
    try:
        text = subprocess.run(['/usr/bin/pmset','-g','batt'],check=True,
            capture_output=True,text=True,timeout=3).stdout
        first = text.splitlines()[0] if text.splitlines() else ''
        source = next((s for s in ('AC Power','Battery Power') if s in first),None)
        if source is None:
            raise ValueError('Unrecognized power-probe output')
        percentage = re.search(r'\b(\d{1,3})%',text)
        percentage = int(percentage.group(1)) if percentage else None
        if percentage is not None and not 0 <= percentage <= 100:
            raise ValueError('Invalid battery percentage')
        return dict(status='available',source=source,battery_percentage=percentage,
                    raw=text[:4096])
    except Exception as error:
        return dict(status='unavailable',source=None,battery_percentage=None,error=repr(error))


def record_power(journal, *, sleep=None):
    journal.emit(dict(kind='passive_power_observation',monotonic=time.monotonic(),
                      power=passive_power(),sleep=sleep))


def process_rss(pid):
    text = subprocess.run(['/bin/ps','-p',str(pid),'-o','rss='],check=True,
        capture_output=True,text=True,timeout=3).stdout.strip()
    need(text.isdigit(),'Owned helper RSS unavailable')
    return int(text)*1024


def check_observer_resources(reg,members,observer_rss,helper_pid):
    check_lease(reg)
    need(sum(x['rss_bytes'] for x in members)+observer_rss+process_rss(helper_pid)
         < reg['rss_bytes'],'Aggregate observer/worker/helper RSS ceiling')


def check_worker_resources(reg,rss,mps):
    check_lease(reg)
    need(rss < reg['rss_bytes'] and mps < reg['mps_bytes'],'Separate6GiB resource ceiling')


def power_assertions(parent_pid):
    rows = subprocess.run(['/bin/ps', '-axo', 'pid=,ppid=,pgid=,command='], check=True,
                          capture_output=True, text=True, timeout=3).stdout
    helpers = []
    for line in rows.splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4 and parts[1] == str(parent_pid) and parts[3].startswith('/usr/bin/caffeinate -ims '):
            helpers.append(int(parts[0]))
    need(len(helpers) == 1, 'One owned caffeinate -ims helper required')
    try:
        assertions = subprocess.run(['/usr/bin/pmset', '-g', 'assertions'], check=True,
                                   capture_output=True, text=True, timeout=3).stdout
        if not assertions.strip():
            raise ValueError('Empty sleep-assertion probe output')
    except Exception as error:
        # The owned, live -i helper is still required. Probe unavailability is
        # logged, not treated as evidence that its assertion disappeared.
        return dict(helper_pid=helpers[0],assertions=[],status='unavailable',error=repr(error))
    held = set()
    for line in assertions.splitlines():
        match = re.search(r'pid (\d+)\(caffeinate\).*?\b(Prevent\w+)\b', line)
        if match and int(match.group(1)) == helpers[0]:
            held.add(match.group(2))
    need('PreventUserIdleSystemSleep' in held, 'Owned idle-sleep assertion absent')
    return dict(helper_pid=helpers[0], assertions=sorted(held),status='available')


def build_streams(reg, replica):
    doc = read(reg['pool_path'])
    need(doc['role'] == 'training_only' and not doc['evaluation_seeds_used_for_selection'], 'Training-only pool required')
    pool = sorted(row['seed'] for row in doc['seeds'])
    need(len(pool) == len(set(pool)) == 512, 'Unique512 pool required')
    need(not any(a <= seed <= z for seed in pool for a, z in reg['exclusions']), 'Reserved seed in pool')
    strata = {row['seed']: row['stratum'] for row in doc['seeds']}
    capacity = (reg['frame_target'] + reg['envs'] - 1) // reg['envs'] + 1
    master = reg['replicas'][replica]['environment_seed']
    streams, digest = [], hashlib.sha256()
    for slot in range(reg['envs']):
        row = []
        for episode in range(capacity):
            key = hashlib.sha256(STREAM_DOMAIN + struct.pack('>QQQ', master, slot, episode)).digest()
            seed = pool[int.from_bytes(key[:8], 'big') % 512]
            row.append(seed); digest.update(struct.pack('>I', seed))
        streams.append(row)
    return pool, strata, streams, digest.hexdigest()


def validate_telemetry(rows, reg, job):
    need(len(rows) == reg['updates'], 'Every completed update required')
    count = reg['envs'] * reg['rollout']
    for index, row in enumerate(rows, 1):
        need(row['schema'] == 'dodge_control_rate_update_telemetry_v2' and row['kind'] == 'update_complete'
             and row['arm_id'] == job['id'] and row['action_repeat'] == 1
             and row['local_update'] == index, 'Telemetry identity/order differs')
        need(row['gameplay_frames_delta'] == row['policy_decisions_delta'] == count
             and row['gameplay_frames_total'] == row['policy_decisions_total'] == index * count
             and row['environment_count'] == reg['envs']
             and row['actual_rollout_decisions_per_slot'] == reg['rollout'], 'Telemetry exposure differs')
        for key in ['gamma', 'gae_lambda']:
            need(row[key] == reg['arms'][job['arm']][key], 'Horizon differs: ' + key)
        need(row['maximum_epochs'] == reg['ppo']['update_epochs']
             and row['effective_minibatch_size'] == reg['effective_minibatch']
             and row['microbatch_size'] == reg['microbatch'], 'Optimizer shape differs')
        for key in ['learning_rate', 'target_kl', 'reward_scale']:
            need(row[key] == reg['ppo'][key], 'Optimizer contract differs: ' + key)
        epochs = row['epochs_completed']
        need(type(epochs) is int and 0 < epochs <= row['maximum_epochs']
             and row['optimizer_steps'] == epochs * (count // reg['effective_minibatch']), 'Adam count differs')
        need(len(row['epoch_approx_kls']) == epochs and row['approx_kl'] == row['epoch_approx_kls'][-1]
             and row['early_stop_kl'] == (row['approx_kl'] > row['target_kl']), 'KL accounting differs')
        need(all(math.isfinite(x) and x >= 0 for x in row['epoch_approx_kls'])
             and all(x <= row['target_kl'] for x in row['epoch_approx_kls'][:-1]), 'Epoch KL history differs')
        need(row['epochs_avoided'] == row['maximum_epochs'] - epochs
             and row['kl_threshold_hit'] == row['early_stop_kl']
             and row['stopped_before_maximum_epochs'] == (row['early_stop_kl'] and epochs < row['maximum_epochs']),
             'Early-stop work accounting differs')
        need(0 <= row['action_switches'] <= row['eligible_action_comparisons'] <= count, 'Switch counts differ')
        n = row['eligible_action_comparisons']
        need(row['action_switch_rate'] == (None if n == 0 else row['action_switches'] / n), 'Switch rate differs')
        need(row['action_switches_per_1000_gameplay_frames'] == 1000 * row['action_switches'] / count,
             'Frame-normalized switch rate differs')
        for key in ['entropy', 'value_loss', 'approx_kl', 'clip_fraction']:
            need(math.isfinite(row[key]) and row[key] >= 0, 'Nonfinite optimization metric')
        need(row['clip_fraction'] <= 1, 'Clip fraction differs')
        ev = row['explained_variance']
        need(row['explained_variance_defined'] == (ev is not None)
             and (ev is None or math.isfinite(ev)), 'EV definedness differs')
        need(row['explained_variance_undefined_reason'] == (
            'PPO reports target population variance <= 1e-12' if ev is None else None), 'EV null reason differs')
        for key in ['raw_advantages_before_minibatch_normalization', 'gae_returns', 'rollout_values',
                    'raw_reward', 'learner_reward']:
            need(row[key]['count'] == count and all(math.isfinite(row[key][v]) for v in
                 ['mean', 'population_std', 'rms', 'minimum', 'maximum']), 'Moment coverage differs')
    return dict(updates=len(rows), frames=len(rows) * count,
                Adam_steps=sum(row['optimizer_steps'] for row in rows))
