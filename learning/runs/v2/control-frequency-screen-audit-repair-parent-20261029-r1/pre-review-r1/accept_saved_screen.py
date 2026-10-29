"""Accept the completed screen and release only its exact inference lease after durable evidence."""
from datetime import datetime, timezone
import os
from pathlib import Path
import sys

REPAIR = Path(__file__).resolve().parent
HERE = REPAIR.parent / 'control-frequency-screen-parent-20261028-r1'
PACKAGE = HERE.parent / 'control-frequency-screen-luna-20261028-r1'
sys.path.insert(0, str(PACKAGE))
import binding as b
import audit
import launch
from repair_contract import validate_contract, require_absent_cache


def absent(group):
    b.need(type(group) is int and group > 1 and group != os.getpgrp(), 'Unsafe process group identity.')
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return dict(pgid=group, absent=True)
    raise ValueError('Recorded process group still exists; do not accept or release the lease.')


def main():
    disposition = validate_contract()
    b.need(not (HERE / 'parent-terminal-audit.json').exists() and not (REPAIR / 'parent-terminal-audit.json').exists(), 'Parent audit already exists; inspect rather than repeat.')
    ready = b.read(HERE / 'authorization-ready.json')
    reg_path = Path(ready['registration_path'])
    reg = b.read(reg_path)
    b.check_lease(reg)
    envelope_path = PACKAGE / 'launch-envelope.json'
    execution = b.read(PACKAGE / 'parent-execution.json')
    envelope, loaded = b.load_envelope(envelope_path, execution['envelope_sha256'])
    b.need(loaded == reg and execution['registration_sha256'] == ready['registration_sha256'], 'Executed registration differs.')
    b.verify_bound(envelope, reg, preflight=True)
    exit_record = b.read(PACKAGE / 'execution-exit.json')
    control = Path(envelope['control'])
    observation = b.read(control / 'observation.json')
    b.need(exit_record['raw_observer_exit_code'] == 0 and exit_record['observer_directly_reaped'] is True
           and exit_record['registration_sha256'] == ready['registration_sha256'], 'Observer completion differs.')
    b.need(observation['status'] == 'completed_pending_parent_audit'
           and observation['observed_worker_raw_exit'] == 0 and observation['directly_reaped'] is True
           and observation['owned_group_absent'] is True and observation['first_event'] is None
           and observation['registration_sha256'] == ready['registration_sha256']
           and observation['envelope_sha256'] == execution['envelope_sha256'], 'Worker completion or cleanup differs.')
    b.need(0 <= exit_record['elapsed_seconds'] <= reg['limits']['total_seconds'], 'Outer wall cap exceeded.')
    b.need(observation['max_aggregate_rss_bytes'] <= reg['limits']['rss_bytes'], 'Aggregate RSS cap exceeded.')
    groups = [absent(execution['observer_pgid']), absent(observation['owned_pgid'])]
    manifest_path = control / 'artifact-manifest.json'
    manifest = b.read(manifest_path)
    out = Path(reg['output'])
    b.need(all(path.is_file() and not path.is_symlink() for path in out.iterdir()), 'Unexpected directory or symlink in flat worker output.')
    members = {path.name for path in out.iterdir() if path.is_file() and not path.is_symlink()}
    b.need(members == set(manifest) and not any(path.is_symlink() for path in out.iterdir()), 'Output member set differs.')
    b.verify_pins({str(out / name): digest for name, digest in manifest.items()})
    cache = Path(reg['import_policy']['pycache_prefix'])
    require_absent_cache(cache)
    local_path = PACKAGE / 'local-terminal-audit.json'
    if local_path.exists():
        local = b.read(local_path)
        b.need(local['registration_sha256'] == ready['registration_sha256'], 'Existing local audit identity differs.')
        audit.terminal.validate_outputs(reg, b.read(out / 'worker-result.json'), ready['registration_sha256'])
    else:
        local = audit.audit(ready['registration_path'], ready['registration_sha256'],
            ready['gate_path'], ready['gate_sha256'], ready['source_acceptance_path'], ready['source_acceptance_sha256'])
    b.need(local['status'] == 'complete_pending_parent_acceptance', 'Local terminal audit did not pass.')
    checks = local['terminal_checks']
    b.need(checks['episodes'] == 2048 and len(checks['groups']) == 8, 'Incomplete registered screen.')
    b.verify_pins({str(out / name): digest for name, digest in manifest.items()})
    decision_path = REPAIR / 'parent-terminal-audit.json'
    b.save(decision_path, dict(schema='control_frequency_screen_parent_terminal_audit_v1',
        status='accepted_complete_2048_episode_development_screen',
        registration_sha256=ready['registration_sha256'], source_manifest_sha256=reg['source_manifest_sha256'],
        local_audit_path=str(local_path), local_audit_sha256=b.sha(local_path),
        artifact_manifest_path=str(manifest_path), artifact_manifest_sha256=b.sha(manifest_path),
        comparison_path=str(out / 'comparison.json'), comparison_sha256=b.sha(out / 'comparison.json'),
        raw_worker_exit_code=0, raw_observer_exit_code=0, process_groups=groups,
        counts=checks, outer_elapsed_seconds=exit_record['elapsed_seconds'],
        power=execution['power_guard'], exact_inference_lease_cleared_after_this_audit=True,
        official_parent=324, automatic_selection=False, promoted=False, training_eligible=False,
        post_run_cache_disposition=disposition,
        original_failed_audit_preserved=True,
        interpretation='One frozen checkpoint, fresh development seeds, repeated controller draws; not training replicas or confirmation. Cache-directory existence requirement waived by a separately reviewed, outcome-blind post-run disposition; all original non-cache acceptance checks retained.'))
    state = b.read(reg['state_path'])
    b.need(state.get(reg['lease_key']) == reg['expected_lease'], 'Another owner holds the lease; do not replace it.')
    state[reg['lease_key']] = None
    state['last_update_at_utc'] = datetime.now(timezone.utc).isoformat()
    launch.replace_state(reg['state_path'], state)
    b.save(REPAIR / 'lease-release.json', dict(status='exact_inference_lease_released_after_durable_parent_acceptance',
        audit_sha256=b.sha(decision_path), released_lease=reg['expected_lease']))
    print('accepted_2048_episode_screen_exact_inference_lease_released_no_promotion')


if __name__ == '__main__':
    main()
