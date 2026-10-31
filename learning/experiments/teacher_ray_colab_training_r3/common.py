"""Owned remote058 helpers. The parent owns the sole global ledger and allocator."""
import hashlib,json,math,os,struct,time
from pathlib import Path
HERE=Path(os.environ.get("DODGE064_RUN_ROOT",Path(__file__).resolve().parent))
STREAM_DOMAIN=b'dodge_ray_uniform512_v1\0'

class GuardError(ValueError):
    def __init__(self, reason):
        self.safe_reason=reason
        super().__init__(reason)


def need(ok, message):
    if not ok:
        raise GuardError(message)


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


_LAST_CONTROL=None

def check_lease(reg):
    """Only expiring coordinator liveness, never a second ledger or launch grant."""
    need(os.environ.get('DODGE064_EXECUTION_ADMITTED')=='true','Execution admission absent')
    need(not (HERE/'cancel.requested').exists(),'Coordinator cancellation requested')
    control=read(HERE/'control.json')
    for key in ('record','job_nonce','registration_sha256','expected_lease_sha256'):
        need(control.get(key)==reg[key],'Coordinator control identity differs: '+key)
    global _LAST_CONTROL
    issued,expires,sequence=(control.get(k) for k in ('issued_at_utc','expires_at_utc','sequence'))
    now=time.time()
    need(type(issued) in (float,int) and type(expires) in (float,int) and math.isfinite(issued)
         and math.isfinite(expires) and issued<=now and 0<expires-issued<=60 and 0<expires-now<=60,
         'Coordinator control expired/future or TTL exceeds60s')
    need(type(sequence) is int and sequence>=1,'Coordinator control sequence absent')
    encoded=canonical(control)
    if _LAST_CONTROL is not None and _LAST_CONTROL[0]==reg['job_nonce']:
        need(sequence>=_LAST_CONTROL[1],'Coordinator control sequence reversed')
        need(sequence!=_LAST_CONTROL[1] or encoded==_LAST_CONTROL[2],'Same control sequence changed content')
        need(issued>=_LAST_CONTROL[3],'Coordinator issued timestamp reversed')
    need(control.get('allowed_stage') in ('build','train'),'Coordinator stage absent')
    if reg.get('control_stage') is not None:need(control['allowed_stage']==reg['control_stage'],'Coordinator stage changed')
    if control['allowed_stage']=='train':
        need(control.get('runtime_admission_sha256')==sha(HERE/'runtime-admission.json'),'Runtime admission control binding absent/different')
    _LAST_CONTROL=(reg['job_nonce'],sequence,encoded,issued)

def verify_pins(reg):
    for path,digest in reg['remote_input_pins'].items():
        need(sha(path)==digest,'Remote input changed: '+path)

def load_registration(path,digest):
    need(sha(path)==digest,'Registration digest differs')
    reg=read(path)
    need(reg['schema']=='dodge_colab_native_training_registration_v1' and reg['record']=='DODGE-064','Training registration schema/record differs')
    reg['registration_sha256']=digest
    recipe=read(Path(__file__).resolve().parent/'scientific_recipe.json')
    for key,value in recipe.items():
        if key not in ('schema','record','launch_authority','pool_path','CUDA_seed_mapping'):
            need(reg.get(key)==value,'Scientific recipe differs: '+key)
    need(reg['accelerator']=='A100' and reg['device']=='cuda:0','A100 CUDA0 required')
    need(reg['no_retry'] and reg['no_resume'] and reg['promotion'] is False,'Lifecycle contract differs')
    need(Path(reg['output_root']).resolve()==HERE.resolve(),'Owned output root differs')
    for name in ('runtime_root','vendor_root','checkpoint_path','pool_path'):
        need(Path(reg[name]).resolve().is_relative_to(HERE.resolve()),'Remote path escaped owned root: '+name)
    need(reg['training_stage_authorized'] is True,'Separate training-stage authority absent')
    verify_pins(reg);check_lease(reg)
    return reg

def read_json_line(line):
    return json.loads(line)
