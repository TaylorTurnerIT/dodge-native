"""Exact local-only successor handoff and terminal acceptance. No cloud API."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / 'learning/runs/v2/teacher-local-parent-20261031-r1'
FAILED = ROOT / 'learning/runs/v2/teacher-cloud-bootstrap-parent-20261031-r1'
FAILED_REG_SHA = '406550cb35a57557cd42ec153732fcddde627382a18c2e42ca5825ba3f55e0c0'
INCIDENT_SHA = 'e92946b7d620dd43ca2938f0b0240895e3884ccd02239b3ce5d19a86ace70a4f'
BASE = ROOT / 'learning/experiments/coordinator_dispatch_v2.py'
BASE_SHA = '77655f4e200ccce33950cd53201ef509394f8bff81e92fdd208c52668890fa16'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda: f.read(1024 * 1024), b''): h.update(data)
    return h.hexdigest()


def read(path): return json.loads(Path(path).read_bytes())


def need(ok, message):
    if not ok: raise ValueError(message)


need(sha(BASE) == BASE_SHA, 'Immutable coordinator dependency differs')
spec = importlib.util.spec_from_file_location('local066_base', BASE)
base = importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
save = base.save


def failed_disposition():
    path = FAILED / 'DODGE-065-A100-bootstrap-registration-r1.json'
    out = FAILED / 'dispatch-DODGE065-A100-bootstrap-r1'
    need(sha(path) == FAILED_REG_SHA and sha(out/'monitor-blocking-incident.json') == INCIDENT_SHA,
         'Failed065 identity differs')
    reg, incident = read(path), read(out/'monitor-blocking-incident.json')
    for name, digest in incident['receipt_sha256'].items():
        need(sha(out/name) == digest, 'Failed065 receipt differs')
    for name, digest in {**reg['source_pins'], **reg['input_pins']}.items():
        need(name != reg['deferred_training_pool']['local'], 'Deferred pool forbidden in failure audit')
        need(sha(name) == digest, 'Failed065 frozen pin differs')
    need(incident['campaign_success'] is False and incident['native_games'] == incident['training_frames'] == 0
         and incident['local_groups_absent'] is True and incident['assignment_absence_confirmed'] is True,
         'Failed065 terminal proof incomplete')
    need(not (out/'lease-release.json').exists() and not (out/'coordinator-terminal-audit.json').exists(),
         'Failed065 unexpectedly accepted')
    return dict(status='acknowledged_failed_campaign', record='DODGE-065', campaign_success=False,
                registration_sha256=FAILED_REG_SHA, exact_lease=reg['expected_lease'],
                incident_sha256=INCIDENT_SHA, assignment_absence_previously_confirmed=True)


def validate(plan, *, require_review=True):
    for kind in ('registration', 'authority', 'readiness'):
        need(sha(plan[kind+'_path']) == plan[kind+'_sha256'], kind+' binding differs')
    reg, authority = read(plan['registration_path']), read(plan['authority_path'])
    ready = read(plan['readiness_path'])
    need(reg['record'] == authority['successor_record'] == 'DODGE-066'
         and authority['predecessor_record'] == 'DODGE-065'
         and authority['schema'] == 'teacher_local_authority_v1'
         and authority['fresh_successor_attempts_authorized'] == 1
         and authority['execution_location'] == 'local_machine_only'
         and authority['no_claim_or_lease_reset'] is True, 'Local authority differs')
    need(reg['authority_path'] == plan['authority_path'] and reg['authority_sha256'] == plan['authority_sha256'],
         'Registration authority differs')
    need(reg['work_seconds'] == 7200 and reg['receipt_seconds'] == 180
         and reg['campaign_total_seconds'] == 29520
         and reg['rss_bytes'] == reg['mps_bytes'] == 6 * 2**30
         and reg['frame_target'] == 2359296 and reg['updates'] == 36
         and reg['no_retry'] and reg['no_automatic_resume'] and not reg['promotion']
         and reg['evaluation_games'] == 0, 'Frozen local scope differs')
    need(ready['status'] == 'CPU_source_and_420_migration_ready'
         and ready['registration_sha256'] == plan['registration_sha256'], 'Local readiness differs')
    preflight = read(ready['CPU_preflight_path'])
    need(sha(ready['CPU_preflight_path']) == ready['CPU_preflight_sha256']
         and preflight['status'] == 'CPU_runtime_import_and_420_migration_passed'
         and preflight['registration_sha256'] == plan['registration_sha256'], 'CPU migration proof differs')
    for filename, digest in {**reg['source_pins'], **reg['input_pins']}.items():
        need(sha(filename) == digest, 'Local frozen pin differs: '+filename)
    need(reg['coordinator_source_pins'][str(Path(__file__).resolve())] == sha(__file__)
         and reg['coordinator_source_pins'][str(BASE)] == BASE_SHA, 'Coordinator pin differs')
    if require_review:
        need(sha(plan['review_path']) == plan['review_sha256'], 'Independent review binding differs')
        review = read(plan['review_path'])
        need(review['status'] == 'no_blocking_findings'
             and review['registration_sha256'] == plan['registration_sha256']
             and review['coordinator_source_pins'] == reg['coordinator_source_pins'], 'Exact local review absent')
    disposition = failed_disposition()
    need(reg['failed_predecessor']['expected_lease'] == disposition['exact_lease'], 'Exact failed owner differs')
    need(not list((Path(reg['package'])/'empty-pycache').iterdir()), 'Local cache changed')
    return reg, disposition


def dispatch(plan, directory):
    reg, disposition = validate(plan)
    directory = Path(directory)
    need(not directory.exists() and not directory.is_symlink() and directory.parent.resolve() == PARENT.resolve(),
         'Fresh confined dispatch output required')
    need(read(reg['state_path'])['active_long_campaign'] == disposition['exact_lease'], 'Exact failed065 lease not held')
    packet = Path(reg['package'])
    need(not (packet/'launch.claimed').exists() and not (packet/'first-failure.json').exists()
         and all(not list((packet/'outputs'/j['id']).iterdir()) for j in reg['jobs']), 'Local attempt consumed')
    directory.mkdir()
    save(directory/'dispatch.claimed', dict(record='DODGE-066', registration_sha256=plan['registration_sha256']))
    disposition.update(review_sha256=plan['review_sha256'], authority_sha256=plan['authority_sha256'])
    fp = directory/'failure-disposition.json'; fs = save(fp, disposition)
    base.exact_handoff(reg['state_path'], disposition['exact_lease'], reg['expected_lease'])
    hp = directory/'lease-handoff.json'
    hs = save(hp, dict(status='exact_non_null_failed_campaign_handoff', previous_lease=disposition['exact_lease'],
        replacement_lease=reg['expected_lease'], failure_disposition_sha256=fs,
        registration_sha256=plan['registration_sha256'], authority_sha256=plan['authority_sha256'], never_cleared_to_null=True))
    gate = dict(plan, schema='coordinator_exact_training_dispatch_v1', status='dispatched_once', stage='training',
        coordinator_thread=reg['coordinator_thread'], expected_lease=reg['expected_lease'], record='DODGE-066',
        failure_disposition_path=str(fp), failure_disposition_sha256=fs, lease_handoff_path=str(hp), lease_handoff_sha256=hs)
    path = directory/'dispatch.json'; digest = save(path, gate)
    return dict(dispatch_path=str(path), dispatch_sha256=digest)


def accept(plan, directory):
    reg, _ = validate(plan); directory = Path(directory)
    need(directory.parent.resolve() == PARENT.resolve() and not directory.is_symlink(), 'Confined audit path required')
    need(not (directory/'coordinator-terminal-audit.json').exists(), 'Accepted audit already exists')
    exited = read(directory/'coordinator-exit.json'); packet = Path(reg['package'])
    launch = read(packet/'launch.claimed'); terminal = read(packet/'parent-terminal-audit.json')
    need(exited['directly_reaped'] is True and exited['observed_exit_code'] == 0
         and exited['coordinator_pid'] == launch['pid'] and exited['local_groups_absent'] is True, 'Direct local reap absent')
    rows = subprocess.check_output(['/bin/ps', '-axo', 'pid=,pgid='], text=True).splitlines()
    need(not any(int(row.split()[0]) == launch['pid'] or int(row.split()[1]) == launch['pid'] for row in rows), 'Observer still present/reused')
    need(terminal['status'] == 'training_complete_pending_coordinator_acceptance'
         and terminal['registration_sha256'] == plan['registration_sha256'] and len(terminal['trajectories']) == 4,
         'Strict four-job terminal evidence absent')
    need(not any('failure' in p.name or '.partial' in p.name for p in packet.rglob('*')), 'Failed/partial packet cannot be accepted')
    import sys
    sys.path.insert(0, str(packet))
    import common as c
    import run_once
    gatepath = directory/'dispatch.json'; gate, loaded = run_once.validate_dispatch(gatepath, sha(gatepath))
    audited = [run_once.audit_job(loaded, plan['registration_sha256'], j) for j in reg['jobs']]
    need(audited == terminal['trajectories'], 'Terminal trajectory audit differs')
    with (Path(reg['state_path']).parent/'horizon-ledger.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read(reg['state_path']); need(state['active_long_campaign'] == reg['expected_lease'], 'Exact local lease lost')
        auditsha = save(directory/'coordinator-terminal-audit.json', dict(status='accepted_training_campaign',
            record='DODGE-066', registration_sha256=plan['registration_sha256'], campaign_success=True,
            parent_terminal_sha256=sha(packet/'parent-terminal-audit.json'), evaluation_games=0, promoted=False))
        state['active_long_campaign'] = None
        path = Path(reg['state_path']); temporary = path.parent/('.local066-release-'+str(os.getpid()))
        with temporary.open('x') as f:
            json.dump(state, f, sort_keys=True); f.flush(); os.fsync(f.fileno())
        os.replace(temporary, path); base.fsync_dir(path.parent)
    return save(directory/'lease-release.json', dict(record='DODGE-066', accepted_audit_sha256=auditsha,
        previous_lease=reg['expected_lease'], lease_value_after_release=None))


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--plan', required=True)
    parser.add_argument('--sha256', required=True); parser.add_argument('--output')
    parser.add_argument('--check-only', action='store_true'); parser.add_argument('--accept-terminal', action='store_true')
    args = parser.parse_args(); need(sha(args.plan) == args.sha256, 'Plan hash differs'); plan = read(args.plan)
    if args.check_only:
        validate(plan, require_review=False); print(json.dumps(dict(status='local_CPU_preparation_verified', execution_authorized=False))); return
    print(json.dumps(accept(plan, args.output) if args.accept_terminal else dispatch(plan, args.output)))


if __name__ == '__main__': main()
