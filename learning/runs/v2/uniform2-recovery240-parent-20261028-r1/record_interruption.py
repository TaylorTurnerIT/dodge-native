"""Preserve the dead campaign and release only its exact stale lease after durable incident evidence."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'uniform2-continuation600-luna-20261028-r2'
sys.path.insert(0, str(OLD))
import binding as b
import terminal


def main():
    b.need(not (HERE / 'incident-audit.json').exists(), 'Incident receipt already exists; inspect rather than repeat.')
    reg_path = OLD / 'registration-final.json'
    reg_sha = b.sha(reg_path)
    b.need(reg_sha == '5d3032f30a6793f3322beb30bafe904859424975a551d80127a3e1fa85602d97', 'Original registration drift')
    reg = b.read(reg_path)
    execution = b.read(OLD / 'parent-execution.json')
    launch = b.read(OLD / 'dispatch' / b.RUN_ID / 'worker-launch.json')
    b.check_owned_source()
    b.check_pins(reg['input_pins'])
    processes = subprocess.check_output(['/bin/ps', '-axo', 'pid=,ppid=,pgid=,command='], text=True)
    identities = [int(value) for value in (execution['observer_pid'], execution['observer_pgid'],
                                          launch['worker_pid'], launch['owned_pgid'],
                                          execution['power_guard']['dispatcher_pid'],
                                          execution['power_guard']['caffeinate_helper_pid'])]
    for line in processes.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        pid, _ppid, pgid = map(int, parts[:3])
        b.need(pid not in identities and pgid not in identities, 'Original process identity or group still exists.')
        b.need(str(OLD) not in parts[3], 'A process still references the original campaign.')
    for group in (execution['observer_pgid'], launch['owned_pgid']):
        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            pass
        else:
            raise ValueError('Original process group absence is not established.')
    events = list(terminal.rows(OLD / 'worker-output/training-events.jsonl', strict=True))
    updates = [r['global_update'] for r in events if r['kind'] == 'update_metrics']
    b.need(updates == list(range(1, 401)), 'Unexpected completed-update prefix.')
    collections = [r['update'] for r in events if r['kind'] == 'collection_complete_before_PPO']
    b.need(collections == list(range(1, 402)), 'Unexpected collection prefix.')
    accounting = terminal.accounting(OLD / 'worker-output', {}, strict=True)
    checkpoint = OLD / 'worker-output/checkpoint-global-360.pt'
    sidecar = b.read(Path(str(checkpoint) + '.json'))
    b.need(b.sha(checkpoint) == sidecar['sha256'] == 'f0f651b8aa87c73b64b9f855c794925a278bb7fac82b7b05ae6f6918cd9898bb',
           'Latest checkpoint bytes differ.')
    b.need(sidecar['global_update'] == 360 and not checkpoint.stat().st_mode & 0o222, 'Saved boundary differs.')
    b.need(not list((OLD / 'worker-output').glob('checkpoint-global-4*.pt')), 'A later checkpoint exists.')
    b.need(all((OLD / name).is_file() for name in ('attempt.claimed', 'launch.claimed')), 'Original spent marker missing.')
    missing = [str(path.relative_to(OLD)) for path in (OLD / 'execution-exit.json',
               OLD / 'dispatch' / b.RUN_ID / 'observation.json', OLD / 'worker-output/worker-result.json',
               OLD / 'parent-terminal-audit.json') if not path.exists()]
    b.need(len(missing) == 4, 'A terminal receipt appeared; reconcile it before incident disposition.')
    files = {str(path.relative_to(OLD)): b.sha(path) for path in sorted(OLD.rglob('*')) if path.is_file()}
    b.save(HERE / 'original-artifact-manifest.json', files)
    state_path = Path(reg['state_path'])
    state_sha = b.sha(state_path)
    state = b.read(state_path)
    b.need(state.get('active_long_campaign') == reg['expected_lease'], 'Another campaign owns the lease.')
    b.save(HERE / 'state-before-lease-release.json', state)
    result = dict(schema='uniform2_recovery240_incident_v1', status='interrupted_incomplete_not_qualified',
        checked_at_utc=datetime.now(timezone.utc).isoformat(), predecessor_run_id=b.RUN_ID,
        registration_sha256=reg_sha, reason='User reports Mac lost power; T3 reports cancelled background work.',
        causal_limit='Power loss is user-reported. Journal and process absence are directly verified; raw exits are unavailable.',
        completed_updates=400, completed_collections=401, latest_durable_checkpoint=sidecar,
        lost_completed_updates=40, next_collection_may_have_partial_optimizer_work=True,
        checkpoint_choice='Latest durable boundary by update number, without inspecting evaluation scores.',
        original_pids_and_groups_absent=identities, process_listing_sha256=b.identity_hash(processes),
        raw_worker_exit_code=None, raw_observer_exit_code=None, missing_terminal_receipts=missing,
        spent_markers_preserved=True, original_artifact_manifest_sha256=b.sha(HERE / 'original-artifact-manifest.json'),
        returned_prefix_accounting=accounting, old_lease=reg['expected_lease'], state_before_sha256=state_sha,
        evaluation_scores_read=False, promoted=False, training_eligible=False,
        recovery_authorization='User: My computer sure did just die. Can we resume training?',
        retry_authorization='A separate registered recovery from checkpoint360; original exact-once attempt remains spent.',
        recovery_updates=240, recovered_effective_global_last=600,
        attempted_completed_updates_if_recovery_finishes=640,
        evaluation_policy='D6 remains repeated development evaluation, not fresh confirmation; no early result selection.')
    b.save(HERE / 'incident-audit.json', result)
    # Release only after publishing the incident. Check again against concurrent ledger writes.
    b.need(b.sha(state_path) == state_sha, 'Ledger changed during incident audit; do not replace it.')
    after = dict(state, active_long_campaign=None, last_update_at_utc=datetime.now(timezone.utc).isoformat())
    fd, staging = tempfile.mkstemp(prefix='.recovery240-state-', dir=state_path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(after, stream, indent=2, sort_keys=True); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(staging, state_path)
        directory = os.open(state_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(staging):
            os.unlink(staging)
    b.need(all(b.sha(OLD / path) == sha for path, sha in files.items()), 'An original artifact changed.')
    b.save(HERE / 'lease-release.json', dict(status='dead_exact_lease_released_after_incident',
        incident_sha256=b.sha(HERE / 'incident-audit.json'), released_lease=reg['expected_lease'],
        state_after_sha256=b.sha(state_path), original_artifacts_preserved=True, original_markers_cleared=False))
    print('interruption_recorded_400_updates_checkpoint360_preserved_exact_dead_lease_released')


if __name__ == '__main__':
    main()
