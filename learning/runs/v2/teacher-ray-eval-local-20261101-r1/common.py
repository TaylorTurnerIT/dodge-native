"""Durable local evaluation helpers; no training or cohort allocation."""
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



def load_registration(path,digest):
    need(sha(path)==digest,'Registration hash differs')
    reg=read(path)
    need(reg['schema']=='dodge_local_fixed_endpoint_evaluation_v1' and reg['record']=='DODGE-068'
         and Path(reg['package']).resolve()==HERE,'Evaluation identity differs')
    need(reg['work_seconds']==7200 and reg['receipt_seconds']==180 and reg['total_seconds']==7380
         and reg['rss_bytes']==reg['mps_bytes']==6*1024**3,'Finite budget differs')
    need(reg['no_retry'] and reg['no_resume'] and not reg['training'] and not reg['promotion'],'Scope differs')
    need([m['name'] for m in reg['models']]==['r1-control','r1-rays','r2-rays','r2-control','420']
         and reg['seeds']==list(range(3657433088,3657433216)) and reg['games']==640,'Frozen panel differs')
    need(reg['controller']=='sampled_per_game_cpu_generator_K1_no_shield_clean' and reg['batch_size']==64,'Controller differs')
    verify_pins(reg);verify_runtime_members(reg)
    need(not list(Path(reg['cache']).rglob('*')),'Bytecode cache must remain empty')
    accepted=read(reg['training_acceptance_path'])
    need(accepted['status']=='accepted_training_campaign' and accepted['record']=='DODGE-066'
         and accepted['registration_sha256']=='6a15523b444345b73ff632cc420687ab68e4a5292c2b2c3b0e83e47134e11f45'
         and accepted['campaign_success'] and not accepted['promoted'],'Accepted066 required')
    release=read(reg['training_release_path'])
    need(release['lease_value_after_release'] is None and release['accepted_audit_sha256']==sha(reg['training_acceptance_path']),'Accepted066 release differs')
    terminal=read(reg['training_terminal_path'])
    need(sha(reg['training_terminal_path'])==accepted['parent_terminal_sha256'],'Terminal binding differs')
    endpoints={t['job']:t['final_checkpoint'] for t in terminal['trajectories']}
    for model in reg['models']:
        if model['name']!='420':
            need(endpoints[model['name']]['path']==model['path'] and endpoints[model['name']]['sha256']==model['sha256']
                 and endpoints[model['name']]['update']==36,'Predeclared final endpoint differs')
    provenance=read(reg['seed_provenance_path'])
    need(provenance['role']=='exposed_development_diagnostic_not_confirmation'
         and provenance['status']=='already_consumed_recorded_retrospectively'
         and provenance['range_inclusive']==[3657433088,3657435135],'Consumed provenance differs')
    return reg


def review_gate(reg,digest):
    path=HERE/'review.json';review=read(path)
    need(review['status']=='accepted' and review['registration_sha256']==digest
         and review['source_pins']==reg['source_pins'] and review['blockers']==[], 'Exact independent review required')
    return sha(path)


def cas_ledger(reg,expected,replacement):
    path=Path(reg['state_path'])
    with (path.parent/'horizon-ledger.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state=read(path);need(state.get('active_long_campaign')==expected,'Exact shared ledger CAS differs')
        state['active_long_campaign']=replacement
        tmp=path.parent/('.eval068-state-'+str(os.getpid()))
        with tmp.open('x') as f:
            json.dump(state,f,sort_keys=True,allow_nan=False);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path);sync_directory(path.parent)
