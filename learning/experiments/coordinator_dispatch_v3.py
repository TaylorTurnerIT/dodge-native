"""One reviewed failed-055 to fresh-056 handoff; no learner or process launch.

The failed capsule is read-only. A durable failure disposition precedes an exact
non-null lease CAS. Any consumed dispatch claim ends this helper's authority.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import traceback

ROOT = Path(__file__).resolve().parents[2]
QUEUE = ROOT / 'learning/runs/v2/teacher-training-queue-parent-20261030-r1'
PREDECESSOR = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-teacher-ray-geometry-20261030/learning/runs/v2/teacher-ray-screen-20261030-r3')
PREDECESSOR_SHA = '58a29434e1e899e6c520674b3b6d8c553596f52baa0c12e4545979a631793e98'
BASE = Path(__file__).with_name('coordinator_dispatch_v2.py')
BASE_SHA = '77655f4e200ccce33950cd53201ef509394f8bff81e92fdd208c52668890fa16'
if hashlib.sha256(BASE.read_bytes()).hexdigest() != BASE_SHA:
    raise ValueError('Immutable coordinator dependency differs')
_spec = importlib.util.spec_from_file_location('coordinator_handoff_dependency', BASE)
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)
need, read, sha, save = _base.need, _base.read, _base.sha, _base.save
exact_handoff = _base.exact_handoff


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def verify_pins(reg):
    pins = {**reg['source_pins'], **reg['input_pins']}
    for path, digest in pins.items():
        need(sha(path) == digest, 'Registered pin changed: ' + path)
    members = {name: pins[str(Path(reg['runtime_root']) / name)]
               for name in reg['runtime_members']}
    root = Path(reg['runtime_root'])
    need(set(members) == {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()},
         'Runtime member inventory differs')
    return hashlib.sha256(canonical(members)).hexdigest()


def failed_predecessor_audit():
    registration = PREDECESSOR / 'registration-r3.json'
    need(sha(registration) == PREDECESSOR_SHA, 'Failed055 registration differs')
    old = read(registration)
    verify_pins(old)
    parent = read(PREDECESSOR / 'first-failure.json')
    out = PREDECESSOR / 'outputs/r1-rays'
    failure = read(out / 'first-failure.json')
    exit_receipt = read(out / 'exit.json')
    accepted = read(PREDECESSOR / 'outputs/r1-control/parent-job-audit.json')
    need(parent['status'] == failure['status'] == 'first_failure_preserved_lease_held'
         and failure['error'] == "ValueError('Player center/size outside admitted physics range')"
         and parent['completed_jobs'] == [accepted['evidence']]
         and accepted['status'] == 'accepted_training_trajectory'
         and accepted['registration_sha256'] == PREDECESSOR_SHA,
         'Failed055 evidence differs')
    need(exit_receipt['raw_exit_code'] == exit_receipt['observed_exit_code'] == 1
         and exit_receipt['directly_reaped'] and exit_receipt['group_absent'],
         'Failed055 child was not directly reaped')
    rows = [json.loads(line) for line in (out / 'updates.jsonl').read_text().splitlines()]
    completed = [row for row in rows if row['kind'] == 'update_complete']
    need(len(completed) == 7 and completed[-1]['gameplay_frames_total'] == 458752
         and rows[-1]['kind'] == 'update_failure'
         and rows[-1]['partial_gameplay_frames'] == 63552
         and failure['observed_gameplay_frames'] == 522304,
         'Failed055 interrupted collection counts differ')
    for name in ['parent-terminal-audit.json', 'lease-release.json']:
        need(not (PREDECESSOR / name).exists(), 'Failed055 unexpectedly accepted/released')
    for job in ['r2-rays', 'r2-control']:
        need(not (PREDECESSOR / 'outputs' / job / 'worker.claimed').exists(),
             'Failed055 later job unexpectedly claimed')
    cache = PREDECESSOR / 'empty-pycache'
    need(cache.is_dir() and not list(cache.iterdir()), 'Failed055 cache differs')
    control_exit = read(PREDECESSOR / 'outputs/r1-control/exit.json')
    need(control_exit['raw_exit_code'] == control_exit['observed_exit_code'] == 0
         and control_exit['directly_reaped'] and control_exit['group_absent'],
         'Failed055 completed control exit differs')
    control_evidence = accepted['evidence']
    control = PREDECESSOR / 'outputs/r1-control'
    for filename, key in [('exit.json', 'exit_sha256'), ('result.json', 'result_sha256'),
                          ('prefix-qualification.json', 'prefix_sha256')]:
        need(sha(control / filename) == control_evidence[key], 'Completed control receipt differs')
    need(sha(control_evidence['final_checkpoint']['path'])
         == control_evidence['final_checkpoint']['sha256'], 'Completed control checkpoint differs')
    groups = {read(PREDECESSOR / 'launch.claimed')['pid'],
              exit_receipt['pgid'], control_exit['pgid']}
    process_rows = subprocess.check_output(['/bin/ps', '-axo', 'pid=,pgid='], text=True)
    need(not any(len(row.split()) == 2 and int(row.split()[1]) in groups
                 for row in process_rows.splitlines()), 'Failed055 group remains')
    return dict(schema='reviewed_failed_campaign_successor_disposition_v2',
        status='acknowledged_failed_campaign', record='DODGE-055', campaign_success=False,
        registration_sha256=PREDECESSOR_SHA, exact_lease=old['expected_lease'],
        all_owned_processes_absent=True, old_pins_unchanged=True, state_path=old['state_path'],
        parent_first_failure_sha256=sha(PREDECESSOR / 'first-failure.json'),
        worker_first_failure_sha256=sha(out / 'first-failure.json'),
        child_exit_sha256=sha(out / 'exit.json'),
        training_journal_sha256=sha(out / 'updates.jsonl'),
        native_journal_sha256=sha(out / 'native-events.jsonl'), retry_failed_capsule=False)


def validate(plan):
    for key in ['registration', 'review', 'readiness', 'authority']:
        need(sha(plan[key + '_path']) == plan[key + '_sha256'], key + ' hash differs')
    reg, review = read(plan['registration_path']), read(plan['review_path'])
    ready, authority = read(plan['readiness_path']), read(plan['authority_path'])
    need(reg['schema'] == 'dodge_ray_training_registration_v1'
         and reg['record'] == plan['record'] == 'DODGE-056', 'Successor identity differs')
    need(review['status'] == 'no_blocking_findings'
         and review['registration_sha256'] == plan['registration_sha256'], 'Exact review absent')
    for path in [Path(__file__).resolve(), BASE.resolve()]:
        need(review['coordinator_source_pins'].get(str(path)) == sha(path),
             'Coordinator source is not independently reviewed')
    need(Path(plan['authority_path']).resolve() == (QUEUE / 'authority-r3.json').resolve()
         and authority['schema'] == 'teacher_training_queue_authority_v3'
         and authority['predecessor_record'] == 'DODGE-055'
         and authority['successor_record'] == 'DODGE-056'
         and authority['fresh_successor_attempts_authorized'] == 1
         and authority['no_claim_or_lease_reset'] is True
         and authority['limits']['battery_operation_allowed'] is True
         and authority['limits']['AC_required'] is False, 'Bounded continuation authority absent')
    need(reg['authority_path'] == plan['authority_path']
         and reg['authority_sha256'] == plan['authority_sha256'], 'Registration authority differs')
    need(ready['status'] == 'CPU_source_and_420_migration_ready'
         and ready['registration_sha256'] == plan['registration_sha256']
         and ready['expected_lease'] == reg['expected_lease'], 'Readiness identity/status differs')
    runtime_digest = verify_pins(reg)
    need(ready['runtime_manifest_sha256'] == runtime_digest, 'Readiness runtime binding differs')
    preflight = read(ready['CPU_preflight_path'])
    need(sha(ready['CPU_preflight_path']) == ready['CPU_preflight_sha256']
         and preflight['registration_sha256'] == plan['registration_sha256']
         and preflight['runtime_manifest_sha256'] == runtime_digest
         and preflight['status'] == 'CPU_runtime_import_and_420_migration_passed',
         'CPU preflight exact runtime binding differs')
    need(ready['runtime_origins'] == preflight['loaded_origins'], 'Loaded origins differ')
    for origin in preflight['loaded_origins'].values():
        need(reg['input_pins'].get(origin['path']) == origin['sha256']
             and sha(origin['path']) == origin['sha256'], 'Unpinned loaded origin')
    need(reg['input_pins'].get(reg['interpreter']) == preflight['interpreter_sha256']
         and preflight['interpreter'] == reg['interpreter'], 'Interpreter binding differs')
    need([j['id'] for j in reg['jobs']] == ['r1-control', 'r1-rays', 'r2-rays', 'r2-control']
         and reg['frame_target'] == 2359296 and reg['updates'] == 36
         and reg['envs'] == 64 and reg['rollout'] == 1024 and reg['action_repeat'] == 1
         and reg['effective_minibatch'] == 2048 and reg['microbatch'] == 512
         and reg['checkpoint_updates'] == [12, 24, 36] and reg['prefix_updates'] == 2,
         'Screen shape/exposure differs')
    need(reg['work_seconds'] == 5400 and reg['receipt_seconds'] == 180
         and reg['campaign_total_seconds'] == 22320
         and reg['rss_bytes'] == reg['mps_bytes'] == 6 * 2**30
         and reg['battery_operation_allowed'] is True and reg['AC_required'] is False
         and reg['evaluation_games'] == 0 and reg['promotion'] is False
         and reg['no_retry'] is True and reg['no_automatic_resume'] is True,
         'Screen limits or safety scope differ')
    old = read(PREDECESSOR / 'registration-r3.json')
    for key in ['checkpoint_sha256', 'model_fingerprint', 'adam_fingerprint', 'replicas',
                'arms', 'ppo', 'exclusions', 'IO_reserve_seconds']:
        need(reg[key] == old[key], 'Scientific recipe/seed pin differs: ' + key)
    package = Path(reg['package'])
    need(package.resolve() != PREDECESSOR.resolve(), 'Failed capsule cannot be reused')
    need(not any((package / name).exists() for name in
                 ['launch.claimed', 'attempt.claimed', 'first-failure.json']), 'Successor already consumed')
    need(all(not list((package / 'outputs' / job['id']).iterdir()) for job in reg['jobs']),
         'Successor outputs are not empty')
    cache = package / 'empty-pycache'
    need(cache.is_dir() and not list(cache.iterdir()), 'Existing empty successor cache required')
    exact = reg['expected_lease']
    need(exact['kind'] == 'teacher_ray_training_screen' and exact['package'] == str(package)
         and exact['run_id'] == reg['run_id'] and exact['promoted'] is False
         and exact != old['expected_lease'], 'Successor exact lease differs')
    template = plan['dispatch_template']
    need(template['schema'] == 'coordinator_exact_training_dispatch_v1'
         and template['status'] == 'dispatched_once' and template['stage'] == 'training'
         and template['one_attempt'] is True and template['record'] == 'DODGE-056'
         and template['coordinator_thread'] == reg['coordinator_thread']
         and template['expected_lease'] == exact, 'Dispatch template identity/status differs')
    for key in ['registration', 'review', 'readiness', 'authority']:
        need(template[key + '_path'] == plan[key + '_path']
             and template[key + '_sha256'] == plan[key + '_sha256'], 'Template binding differs: ' + key)
    need(not any(k in template for k in ['failure_disposition_path', 'failure_disposition_sha256',
                                        'lease_handoff_path', 'lease_handoff_sha256']),
         'Handoff evidence must be created by this dispatch')
    return reg


def dispatch(plan, directory):
    reg = validate(plan)
    disposition = failed_predecessor_audit()
    need(read(disposition['state_path']).get('active_long_campaign') == disposition['exact_lease'],
         'Exact failed055 lease is not held')
    directory = Path(directory)
    def confined_output():
        return (not directory.is_symlink()
                and directory.parent.resolve() == QUEUE.resolve()
                and directory.resolve().parent == QUEUE.resolve())
    need(confined_output(), 'Dispatch output must be a real direct child of coordinator queue')
    directory.mkdir(exist_ok=True)
    need(confined_output(), 'Dispatch output changed while creating coordinator directory')
    need(not list(directory.iterdir()), 'Dispatch evidence directory already consumed')
    save(directory / 'dispatch.claimed', dict(record='DODGE-056', pid=os.getpid(),
         registration_sha256=plan['registration_sha256']))
    try:
        disposition.update(successor_registration_sha256=plan['registration_sha256'],
                           review_sha256=plan['review_sha256'], authority_sha256=plan['authority_sha256'])
        failure_path = directory / 'failure-disposition.json'
        failure_sha = save(failure_path, disposition)
        exact_handoff(disposition['state_path'], disposition['exact_lease'], reg['expected_lease'])
        handoff_path = directory / 'lease-handoff.json'
        handoff_sha = save(handoff_path, dict(status='exact_non_null_failed_campaign_handoff',
            previous_lease=disposition['exact_lease'], replacement_lease=reg['expected_lease'],
            failure_disposition_sha256=failure_sha, registration_sha256=plan['registration_sha256'],
            authority_sha256=plan['authority_sha256'], never_cleared_to_null=True))
        document = dict(plan['dispatch_template'], failure_disposition_path=str(failure_path),
            failure_disposition_sha256=failure_sha, lease_handoff_path=str(handoff_path),
            lease_handoff_sha256=handoff_sha)
        path = directory / 'dispatch.json'
        digest = save(path, document)
        return dict(dispatch_path=str(path), dispatch_sha256=digest, exact_lease=reg['expected_lease'])
    except BaseException as error:
        save(directory / 'first-failure.json', dict(error=repr(error), traceback=traceback.format_exc(),
            lease_value=read(disposition['state_path']).get('active_long_campaign'), retry=False))
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    need(sha(args.plan) == args.plan_sha256, 'Dispatch plan hash differs')
    print(json.dumps(dispatch(read(args.plan), args.output), sort_keys=True))


if __name__ == '__main__':
    main()
