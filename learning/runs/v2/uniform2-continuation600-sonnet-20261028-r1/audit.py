"""Root terminal audit; the exact main-ledger lease is cleared only after durable accepted evidence."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import subprocess
import binding as b
import terminal


def check_observer_receipts(execution, exit_record, observation, registration_sha, envelope_sha):
    b.need(execution['registration_sha256'] == exit_record['registration_sha256'] == registration_sha
           and execution['envelope_sha256'] == envelope_sha, 'execution identity differs')
    b.need(exit_record['raw_observer_exit_code'] == 0 and exit_record['observer_directly_reaped'] is True
           and observation['observed_worker_raw_exit'] == 0 and observation['directly_reaped'] is True
           and observation['first_event'] is None and observation['status'] == 'completed_pending_parent_audit'
           and observation['owned_group_absent'] is True, 'supervisor raw completion differs')


def group_absent(pgid, role):
    b.need(type(pgid) is int and pgid > 1 and pgid != os.getpgrp(), 'unsafe '+role+' process group')
    processes = subprocess.run(['/bin/ps', '-axo', 'pid=,ppid=,pgid=,command='], capture_output=True, text=True, check=True).stdout
    b.need(not any(int(line.split(None, 3)[2]) == pgid for line in processes.splitlines() if line.strip()), role+' process group remains')
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        pass
    else:
        raise ValueError(role+' group absence not proven')
    return dict(role=role, pgid=pgid, absent=True)


def check_manifest(control, out):
    manifest = b.read(Path(control)/'artifact-manifest.json')
    actual = {p.name for p in Path(out).iterdir() if p.is_file() and not p.is_symlink()}
    b.need(actual == set(manifest), 'worker output member set differs from observer manifest')
    b.check_pins({str(Path(out)/name): digest for name, digest in manifest.items()})
    return manifest


def clear_lease(reg, audit_path):
    """Clears only this campaign's exact lease in the main ledger; no other ledger field is touched."""
    from launch import replace_state
    state = b.read(reg['state_path'])
    b.need(state.get('active_long_campaign') == reg['expected_lease'], 'refusing another lease')
    state['active_long_campaign'] = None
    import datetime
    state['last_update_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    replace_state(reg['state_path'], state)


def main(envelope_path, envelope_sha):
    e, reg = b.load_envelope(envelope_path, envelope_sha)
    b.need(not (b.HERE/'parent-terminal-audit.json').exists(), 'parent audit already exists; inspect, never duplicate')
    b.check_lease(reg)
    execution, exit_record = b.read(b.HERE/'parent-execution.json'), b.read(b.HERE/'execution-exit.json')
    observation = b.read(Path(e['control'])/'observation.json')
    check_observer_receipts(execution, exit_record, observation, e['registration_sha256'], envelope_sha)
    groups = [group_absent(execution['observer_pgid'], 'observer'), group_absent(observation['owned_pgid'], 'worker')]
    b.verify_bound(e, reg, preflight=False)
    b.validate_static(reg, streams=True)
    cache = Path(reg['import_policy']['pycache_prefix'])
    b.need(cache.is_dir() and not cache.is_symlink() and not any(cache.iterdir()), 'registered bytecode cache is not empty')
    out = Path(reg['output']); worker = b.read(out/'worker-result.json')
    accounting = terminal.validate_outputs(reg, worker, e['registration_sha256'])
    check_manifest(e['control'], out)
    selection = b.read(out/'selection.json')
    audit = dict(schema=b.AUDIT_SCHEMA, status='accepted_complete_600_update_continuation_with_11_evaluations',
        registration_sha256=e['registration_sha256'], source_manifest_sha256=reg['source_manifest_sha256'],
        raw_worker_exit_code=0, raw_observer_exit_code=0, process_groups=groups,
        postflight_inputs_dependencies_cache='passed', accounting=accounting, selection_path=str(out/'selection.json'),
        selection_sha256=b.sha(out/'selection.json'), selected=selection['selected'],
        selected_is_starting_model=selection['selected_is_starting_model'], selection_independently_recomputed=True,
        power=execution['power_guard'], main_ledger_lease_cleared_after_this_audit=True, d5_b_e_opened=False,
        official_parent324_promotion=False, automatic_selection=False, promoted=False, training_eligible=False)
    b.save(b.HERE/'parent-terminal-audit.json', audit)
    clear_lease(reg, b.HERE/'parent-terminal-audit.json')
    b.save(b.HERE/'lease-release.json', dict(status='exact_lease_cleared_after_durable_parent_audit',
        audit_sha256=b.sha(b.HERE/'parent-terminal-audit.json'), released_lease=reg['expected_lease']))
    print('accepted_continuation600_no_promotion', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--envelope', required=True)
    parser.add_argument('--envelope-sha256', required=True); a = parser.parse_args()
    main(a.envelope, a.envelope_sha256)
