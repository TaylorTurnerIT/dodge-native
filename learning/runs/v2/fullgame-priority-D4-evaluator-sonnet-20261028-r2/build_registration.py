"""Hash-only builder: refuses until six accepted producer audits exist. Writes only an inert draft.

Never installs a lease, writes a marker, imports Torch/native modules, or deserializes checkpoints.
"""
from __future__ import annotations
import argparse
import importlib
from pathlib import Path
import uuid
import binding as b


class NotReady(RuntimeError):
    pass


def readiness():
    """Existence of predeclared terminal receipts only; never lists partial training output."""
    rows = []
    for layout in b.predeclared_layouts():
        needed = ('audit_path', 'lease_release_path', 'parent_execution_path', 'execution_exit_path',
                  'artifact_manifest_path', 'worker_result_path', 'registration_path', 'checkpoint_path', 'sidecar_path')
        missing = [name for name in needed if not Path(layout[name]).is_file()]
        accepted = None
        if Path(layout['audit_path']).is_file():
            accepted = b.read(layout['audit_path']).get('status') == 'accepted_complete_global_update60_training_receipt'
        rows.append(dict(policy_id=layout['policy_id'], run_id=layout['run_id'], checkpoint_path=layout['checkpoint_path'],
                         audit_present=Path(layout['audit_path']).is_file(), audit_accepted=accepted, missing=missing,
                         ready=not missing and accepted is True))
    return rows


def policy_entry(layout, c):
    registration = Path(layout['registration_path']); reg = b.read(registration)
    worker = b.read(layout['worker_result_path']); endpoint = worker['formal_comparison_endpoint']
    source = Path(reg['runtime_root']).parent
    paths = [layout[k] for k in ('registration_path', 'audit_path', 'worker_result_path', 'sidecar_path',
             'artifact_manifest_path', 'lease_release_path', 'parent_execution_path', 'execution_exit_path')]
    paths += [str(source/'source-manifest.json'), str(source/'runtime-manifest.json')]
    producer = dict(**{k: layout[k] for k in ('registration_path', 'audit_path', 'worker_result_path', 'sidecar_path',
            'artifact_manifest_path', 'lease_release_path', 'parent_execution_path', 'execution_exit_path')},
        source_manifest_sha256=reg['source_manifest_sha256'], runtime_manifest_sha256=reg['runtime_manifest_sha256'],
        expected_identity=b.learner_identity(reg, b.sha(registration), c), pins={p: b.sha(p) for p in paths})
    b.need(endpoint['path'] == layout['checkpoint_path'], 'worker endpoint is not the predeclared terminal60 path')
    return dict(id=layout['policy_id'], checkpoint_path=layout['checkpoint_path'],
                checkpoint_sha256=endpoint['sha256'], producer=producer), reg


def build(*, runtime_files=True):
    state = readiness()
    if not all(row['ready'] for row in state):
        raise NotReady('accepted terminal audits missing: '+', '.join(row['policy_id'] for row in state if not row['ready']))
    c = b.contracts(); importlib.import_module('successor_identity')
    policies, regs = [], []
    for layout in b.predeclared_layouts():
        policy, reg = policy_entry(layout, c); policies.append(policy); regs.append(reg)
    for reg in regs[1:]:
        for key in ('runtime_versions', 'interpreter', 'training_pool_sha256'):
            b.need(reg[key] == regs[0][key], 'producers disagree on '+key)
    parent = c.read(b.ROOT/b.PARENT_RECEIPT)
    policies.append(dict(id=b.PARENT_ID, checkpoint_path=parent['checkpoint_path'],
                         checkpoint_sha256=c.references.ACCEPTED_CHECKPOINT_SHA256, producer=None))
    registry = b.read(b.REGISTRY)
    pins = {str(b.ROOT/b.PARENT_RECEIPT): b.sha(b.ROOT/b.PARENT_RECEIPT), str(b.REGISTRY): b.sha(b.REGISTRY),
            registry['immutable_history_inputs_path']: registry['immutable_history_inputs_sha256'],
            registry['training_pool_path']: registry['training_pool_file_sha256'], **registry['pins']}
    for path in (b.SOURCE/'source-manifest.json', b.SOURCE/'runtime-manifest.json', b.SOURCE/'input-manifest.json',
                 b.HERE/'policy-plan.json', b.V2/'rl-next-experiments-parent-20261027-r1/experiments.json'):
        pins[str(path)] = b.sha(path)
    prior = b.PRIOR_EVALUATOR/'worker-output/worker-result.json'
    prior_audit = b.PRIOR_EVALUATOR/'parent-terminal-audit.json'
    cost = b.read(prior)
    b.need(cost['status'] == 'completed' and cost['rows_completed'] == 7168, 'prior evaluator cost basis not a completed run')
    pins[str(prior)] = b.sha(prior); pins[str(prior_audit)] = b.sha(prior_audit)
    measurement = dict(elapsed_seconds=cost['elapsed_seconds'], raw_frames=cost['raw_frames_including_startup'],
                       receipt_path=str(prior), receipt_sha256=b.sha(prior), terminal_audit_path=str(prior_audit),
                       peak_rss_bytes=cost['peak_rss_bytes'], peak_mps_driver_bytes=cost['peak_mps_driver_bytes'])
    work = b.projected_work_seconds(measurement['elapsed_seconds'], measurement['raw_frames'])
    reg = dict(schema='fullgame_priority_d4_terminal60_registration_v1', status='source_review_pending',
        run_id=b.EVAL_RUN_ID, study_id=b.STUDY, backend='mps', backend_pins=b.BACKEND_PINS,
        source_manifest_sha256=b.sha(b.HERE/'source-manifest.json'), evaluator_source=str(b.SOURCE),
        runtime_root=str(b.SOURCE/'runtime'), runtime_manifest_sha256=b.RUNTIME_SHA,
        input_manifest_sha256=b.sha(b.SOURCE/'input-manifest.json'), runtime_versions=regs[0]['runtime_versions'],
        policies=policies, seeds=b.SEEDS, cohort=dict(name='D4', range=list(b.D4), count=1024, d5_range=list(b.D5),
            d5_state='unopened'), exclusion_union=b.normalize_union([r['exclusion_union'] for r in regs]), evaluation_rng_seed=b.EVAL_RNG_SEED,
        bootstrap=b.BOOTSTRAP, semantics=b.SEMANTICS,
        limits=dict(work_seconds=work, total_seconds=b.total_seconds(work), cleanup_seconds=10, rss_bytes=b.CAP, mps_bytes=b.CAP,
                    raw_frames=b.RAW_CAP, constructors=b.EPISODES, native_steps=b.STEP_CAP, resets=0, retries=0),
        output=str(b.HERE/'worker-output'), attempt_claim_path=str(b.HERE/'attempt.claimed'),
        launch_marker_path=str(b.HERE/'launch.claimed'), state_path=str(b.ROOT/'learning/runs/v2-orchestration/state.json'),
        expected_lease=dict(kind=b.LEASE_KIND, run_id=b.EVAL_RUN_ID, owner_token=uuid.uuid4().hex,
                            RSS_bytes=b.CAP, MPS_driver_bytes=b.CAP),
        interpreter=regs[0]['interpreter'],
        import_policy=dict(dont_write_bytecode=True, pycache_prefix=str(b.HERE/'empty-pycache')),
        input_pins=pins, cohort_state='reserved_parent_approved', history_state='freshness_parent_approved',
        reservation_state='parent_reserved', provenance=b.PROVENANCE,
        calibration=dict(parent_accepted=False, parent_acceptance_path=None, parent_acceptance_sha256=None,
            proposed_work_seconds=work, projection_factor=b.WALL_FACTOR,
            postflight_allowance_seconds=b.POSTFLIGHT_SECONDS,
            postflight_basis='total=work+cleanup(10)+postflight; prior observer-minus-worker 9.40 s x (RAW_CAP/prior frames 8.34) = 78.4 s; 120 s allowance. Worst-case bound, not expected runtime.', prior_measurement=measurement,
            projection='ceil(factor*prior_elapsed/prior_raw_frames*maximum_raw_frames+10)',
            limitation='Same evaluator flow and runtime but different policies; wall time scales with surviving frames and '
                       'small late batches. Factor 3 covers that, not a fresh per-policy calibration. Hard SIGALRM stop at work_seconds.'))
    b.validate_static(reg, require_registered=False, runtime_files=runtime_files)
    return reg


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='print terminal-receipt readiness only')
    parser.add_argument('--output')
    args = parser.parse_args()
    if args.check:
        rows = readiness()
        for row in rows:
            print(row['policy_id'], 'ready' if row['ready'] else 'NOT_READY', row['missing'] or '')
        raise SystemExit(0 if all(r['ready'] for r in rows) else 3)
    b.need(args.output is not None, '--output required')
    path = Path(args.output).resolve(); b.need(path.parent == b.HERE, 'builder output must be owned')
    try:
        draft = build()
    except NotReady as error:
        print('REFUSED', error); raise SystemExit(3)
    b.save(path, draft); print(str(path), flush=True)
