"""Root-owned parent gate binding; one attempt, one direct-owner watchdog. Not run during preparation.

Installs the exact lease in the MAIN resource ledger (null beforehand, cleared only by audit.py after the durable audit).
Launch as `/usr/bin/caffeinate -ims <env/python> -B launch.py ...` from the native root session. On battery the pinned
explicit user override record is required by the owned power guard; AC is not required for this campaign only.
"""
from __future__ import annotations
import argparse
import datetime
import os
from pathlib import Path
import subprocess
import time
import binding as b
import power_guard

PENDING = 'state.uniform2-continuation600.pending.json'


def replace_state(path, state):
    staged = Path(path).with_name(PENDING)
    b.save(staged, state); os.replace(staged, path)
    directory = os.open(Path(path).parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def main_state_free(reg):
    b.need(not os.path.lexists(Path(reg['state_path']).with_name(PENDING)), 'shared state pending path present')
    state = b.read(reg['state_path'])
    b.need(state.get('active_long_campaign') is None and all(state.get(k) is None for k in
           ('active_inference_diagnostic', 'active_inference_campaign', 'active_inference_lease')), 'conflicting campaign in main ledger')
    b.need(not state.get('training_hold', {}).get('active', False), 'user training hold is active')
    return state


def install_lease(reg):
    state = main_state_free(reg)
    state['active_long_campaign'] = reg['expected_lease']
    state['last_update_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    replace_state(reg['state_path'], state)


def main(registration, registration_sha, gate_path, gate_sha, source_acceptance, source_acceptance_sha):
    b.check_pins({registration: registration_sha, gate_path: gate_sha, source_acceptance: source_acceptance_sha})
    reg = b.read(registration); b.validate_static(reg, streams=True, startup=True)
    gates = b.read(gate_path)
    b.need(gates == b.approval_document(registration_sha, reg['source_manifest_sha256'], gates.get('pins')),
           'exact parent gates missing')
    b.check_pins(gates['pins'])
    b.need(b.read(source_acceptance) == b.source_acceptance_document(reg['source_manifest_sha256']),
           'independent source acceptance differs')
    for name in ('launch-envelope.json', 'parent-execution.json', 'execution-exit.json', 'observer.log'):
        b.need(not os.path.lexists(b.HERE/name), 'parent output already spent: '+name)
    control = b.HERE/'dispatch'/reg['run_id']; b.need(not control.exists(), 'dispatch already spent')
    override = b.read(reg['authorization']['battery_override_path'])
    power = power_guard.check(override=override)
    power['battery_override_sha256'] = reg['authorization']['battery_override_sha256']
    started = time.monotonic()
    install_lease(reg)
    pins = {**{str(b.HERE/n): d for n, d in b.read(b.HERE/'source-manifest.json')['files'].items()},
            str(b.HERE/'source-manifest.json'): reg['source_manifest_sha256'], **gates['pins']}
    envelope = dict(schema=b.ENVELOPE_SCHEMA, status='parent_bound_exactly_one_run',
        registration=str(Path(registration).resolve()), registration_sha256=registration_sha,
        launch_approval=str(Path(gate_path).resolve()), launch_approval_sha256=gate_sha,
        source_acceptance=str(Path(source_acceptance).resolve()), source_acceptance_sha256=source_acceptance_sha,
        control=str(control), cancel_path=str(b.HERE/'cancel'), started=started, pins=pins,
        interpreter_resolved=str(Path(reg['interpreter']).resolve()), interpreter_sha256=b.sha(Path(reg['interpreter']).resolve()))
    path = b.HERE/'launch-envelope.json'; b.save(path, envelope); digest = b.sha(path)
    b.save(reg['launch_marker_path'], dict(schema=b.MARKER_SCHEMA, registration_sha256=registration_sha,
                                           run_id=reg['run_id'], started=started))
    e, _ = b.load_envelope(path, digest); b.verify_bound(e, reg, preflight=True)
    env = os.environ.copy(); env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONPYCACHEPREFIX=reg['import_policy']['pycache_prefix'])
    command = [reg['interpreter'], '-B', str(b.HERE/'observe.py'), '--envelope', str(path), '--envelope-sha256', digest]
    with (b.HERE/'observer.log').open('x') as log:
        process = subprocess.Popen(command, cwd=b.ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        b.save(b.HERE/'parent-execution.json', dict(observer_pid=process.pid, observer_pgid=process.pid, command=command,
            started=started, registration_sha256=registration_sha, envelope_sha256=digest, power_guard=power))
        print('continuation_launched_exactly_once', process.pid, flush=True)
        code = process.wait()
    b.save(b.HERE/'execution-exit.json', dict(raw_observer_exit_code=code, observer_directly_reaped=True,
        elapsed_seconds=time.monotonic()-started, registration_sha256=registration_sha, parent_terminal_audit_pending=True))
    print('continuation_terminal_parent_audit_pending', code, flush=True)
    return int(code != 0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('registration', 'registration-sha256', 'gate', 'gate-sha256', 'source-acceptance', 'source-acceptance-sha256'):
        parser.add_argument('--'+name, required=True)
    a = parser.parse_args()
    raise SystemExit(main(a.registration, a.registration_sha256, a.gate, a.gate_sha256, a.source_acceptance, a.source_acceptance_sha256))
