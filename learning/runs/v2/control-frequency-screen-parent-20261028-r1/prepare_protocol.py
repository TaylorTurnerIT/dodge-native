"""Register the approved inference-only screen without opening a game or importing model libraries."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
V2 = HERE.parent
RUN_ID = 'control-frequency-screen-luna-20261028-r1'
RECOVERY = V2 / 'uniform2-recovery240-luna-20261028-r1'
RECOVERY_PARENT = V2 / 'uniform2-recovery240-parent-20261028-r1'
sys.path.insert(0, str(RECOVERY))
import binding as b


def main():
    old_reservation_path = V2 / 'uniform2-continuation600-parent-20261028-r1/development-cohort-reservation.json'
    old = b.read(old_reservation_path)
    b.check_pins(old['pins'])
    history_path = V2 / 'progressive1000-seed-history-closure-sol-20261026-r2/merged-conservative-seeds.json'
    reconciliation_path = V2 / 'rl-followup-seed-reservation-parent-20261027-r1/seed-reconciliation.json'
    pool_path = V2 / 'rl-next-experiments-parent-20261027-r1/training-pool512-accepted.json'
    historical = set(b.read(history_path)['sorted_unique_seed_values'])
    for row in b.read(reconciliation_path)['postclosure_actual_constructors']:
        historical.update(row['actual_seeds_sorted'])
    pool = b.read(pool_path)
    historical.update(row['seed'] for row in pool['seeds'])
    for lo, hi in old['exclusion_union']:
        historical.update(range(lo, hi + 1))
    seeds = list(range(0xD7000000, 0xD7000100))
    b.need(not historical.intersection(seeds), 'D7 intersects accepted-family recorded history or reservations.')
    b.need(all(not (lo <= seeds[-1] and hi >= seeds[0]) for lo, hi in old['exclusion_union']), 'Reserved range overlap.')
    original_reg_path = V2 / 'uniform2-continuation600-luna-20261028-r2/registration-final.json'
    original = b.read(original_reg_path)
    recovery_reg_path = RECOVERY / 'registration-final.json'
    recovery = b.read(recovery_reg_path)
    # Both intervening training attempts are pinned to the same known training pool and D6 evaluation vector.
    b.need(original['streams']['training_pool_file_sha256'] == recovery['streams']['training_pool_file_sha256'] == b.sha(pool_path),
           'Intervening training pool differs.')
    b.need(original['cohort']['range'] == recovery['cohort']['range'] == old['range'], 'Intervening evaluation cohort differs.')
    chosen_path = RECOVERY_PARENT / 'recovered-study-result.json'
    chosen = b.read(chosen_path)
    b.need(chosen['selected']['global_update'] == 420 and chosen['promoted'] is False, 'Expected development candidate changed.')
    checkpoint = RECOVERY / 'worker-output/checkpoint-global-420.pt'
    checkpoint_sha = b.sha(checkpoint)
    sidecar_path = Path(str(checkpoint) + '.json')
    sidecar = b.read(sidecar_path)
    b.need(sidecar['sha256'] == checkpoint_sha == chosen['selected']['checkpoint_sha256'], 'Candidate bytes differ.')
    identity = b.learner_identity(recovery, b.sha(recovery_reg_path))
    b.need(b.identity_hash(identity) == sidecar['identity_sha256'], 'Candidate identity derivation differs.')
    now = datetime.now(timezone.utc).isoformat()
    provenance_paths = [history_path, reconciliation_path, pool_path, old_reservation_path,
                        original_reg_path, recovery_reg_path, RECOVERY / 'parent-terminal-audit.json',
                        RECOVERY_PARENT / 'original-prefix-stream-audit.json', RECOVERY_PARENT / 'incident-audit.json',
                        chosen_path, checkpoint, sidecar_path]
    pins = {str(path): b.sha(path) for path in provenance_paths}
    cohort = dict(schema='control_frequency_screen_cohort_v1', status='parent_reserved', name='D7',
        seeds=seeds, count=256, range=[seeds[0], seeds[-1]],
        seed_vector_sha256_u32be=hashlib.sha256(b''.join(struct.pack('>I', seed) for seed in seeds)).hexdigest(),
        role='New development screen shared by all four conditions; not confirmation.',
        historical_overlap=0, known_history_seed_count=len(historical),
        claim_scope=old['claim_scope'], inherited_limits=old['inherited_history_limits'],
        intervening_exposure='Original and recovery training used only the pinned pool; evaluations used the recorded D6 vector. Native qualification uses training-pool seeds only.',
        evaluation_exclusions=old['exclusion_union'],
        future_training_exclusions=sorted([*old['exclusion_union'], [seeds[0], seeds[-1]]]),
        outcomes_read=False, universal_workspace_nonuse_claim=False, d5_b_e_opened=False,
        reserved_at_utc=now, pins=pins)
    b.save(HERE / 'cohort-reservation.json', cohort)
    sample_seeds = [202610280401, 202610280402, 202610280403]
    conditions = [dict(id='argmax_r4', action_mode='argmax', action_repeat=4, repetitions=1),
                  dict(id='argmax_r1', action_mode='argmax', action_repeat=1, repetitions=1),
                  dict(id='sampled_r4', action_mode='sampled_categorical', action_repeat=4, repetitions=3),
                  dict(id='sampled_r1', action_mode='sampled_categorical', action_repeat=1, repetitions=3)]
    order = [dict(condition='argmax_r4', repetition=0, controller_seed=None),
             dict(condition='argmax_r1', repetition=0, controller_seed=None)]
    for repetition, controller_seed in enumerate(sample_seeds):
        for repeat in ((4, 1) if repetition != 1 else (1, 4)):
            order.append(dict(condition=f'sampled_r{repeat}', repetition=repetition, controller_seed=controller_seed))
    calibration_sources = []
    for path in sorted((RECOVERY / 'worker-output').glob('evaluation-*.json')):
        receipt = b.read(path)
        calibration_sources.append(dict(path=str(path), sha256=b.sha(path),
            elapsed_seconds=receipt['elapsed_seconds'], raw_frames=receipt['raw_frames_including_startup']))
    rate = max(row['elapsed_seconds'] / row['raw_frames'] for row in calibration_sources)
    condition_limits = {}
    for condition in conditions:
        episodes = 256 * condition['repetitions']
        repeat = condition['action_repeat']
        condition_limits[condition['id']] = dict(episodes=episodes, constructors=episodes,
            raw_frames=episodes * 18013, native_steps=episodes * math.ceil(18000 / repeat), resets=0,
            projected_all_capped_seconds=math.ceil(rate * episodes * 18013 * (4 / repeat)))
    worst_projection = sum(row['projected_all_capped_seconds'] for row in condition_limits.values())
    b.need(worst_projection * 1.5 < 7200, 'Conservative timing estimate exceeds proposed work cap.')
    limits = dict(work_seconds=7200, cleanup_seconds=10, postflight_seconds=120, total_seconds=7330,
                  rss_bytes=6 * 1024**3, mps_bytes=6 * 1024**3, retries=0,
                  episodes=2048, constructors=2048, raw_frames=2048 * 18013, native_steps=23040000, resets=0)
    calibration = dict(schema='control_frequency_screen_calibration_v1', status='parent_accepted_projection',
        measured_sources=calibration_sources, maximum_measured_seconds_per_raw_frame=rate,
        one_frame_cost_multiplier=4, estimated_all_capped_seconds=worst_projection,
        margin_factor=1.5, margin_included_seconds=math.ceil(worst_projection * 1.5), limits=limits,
        interpretation='Empirical planning estimate, not a guaranteed runtime bound. Frequency multiplier applies to the entire observed rate conservatively; the supervisor enforces the absolute work deadline.',
        expected_scope='About 2048 full games; most observed games previously lasted far less than the 18000-frame cap.',
        no_new_throughput_games=True)
    b.save(HERE / 'calibration.json', calibration)
    authorization = dict(schema='control_frequency_screen_authorization_v1', status='authorized_inference_only',
        user_reply='Interesting that after six hundred it had the highest mean. Go ahead with your recommendation for next steps.',
        experiment='DODGE-002', selected_checkpoint_update=420, checkpoint_sha256=checkpoint_sha,
        selection_basis='The user chose mean survival in the worst 25% of games; update420 won that predeclared development criterion. Update600 remains the mean-survival leader.',
        conditions=4, groups=8, episodes=2048, new_game_seeds=256, sampler_repetitions=3,
        no_optimizer=True, no_training=True, no_checkpoint_write=True, official_parent=324,
        no_policy_adoption_or_promotion=True, limitations='Frozen-policy screen; a one-frame training effect is a separate experiment.',
        limits=limits, recorded_at_utc=now)
    b.save(HERE / 'user-authorization.json', authorization)
    lease = dict(kind='control_frequency_screen', run_id=RUN_ID, owner_token=uuid.uuid4().hex,
                 RSS_bytes=limits['rss_bytes'], MPS_driver_bytes=limits['mps_bytes'])
    protocol = dict(schema='control_frequency_screen_protocol_v1', run_id=RUN_ID, experiment_id='DODGE-002',
        checkpoint=dict(path=str(checkpoint), sha256=checkpoint_sha, sidecar_path=str(sidecar_path),
            sidecar_sha256=b.sha(sidecar_path), expected_identity=identity, identity_sha256=sidecar['identity_sha256'],
            model_fingerprint=sidecar['model_fingerprint'], global_update=420, phase_update=804, cumulative_update=852),
        seeds=seeds, cohort='D7', controller_seeds=sample_seeds, conditions=conditions, order=order,
        backend='mps', dtype='float32', torch_num_threads=4, batch_size=64,
        environment=dict(difficulty=2, patterns_enabled=True, powerups_enabled=True,
                         normal_start=True, cutoff_enabled=False, raw_frame_cap=18000),
        neural_inputs=['global_feats', 'entity_feats', 'entity_types', 'entity_mask'],
        evaluation_exclusions=cohort['evaluation_exclusions'], limits=limits, condition_limits=condition_limits,
        statistics=dict(primary='Q1: mean survival in the worst25% of pooled complete games per condition; sampled bottom192/768, argmax bottom64/256.',
            per_repetition='Also report each sampled repetition separately on256 seeds; these are controller repetitions, not training replicas.',
            bootstrap=dict(unit='256 paired game-seed clusters; retain all controller repetitions within each seed', draws=2000, seed=202610280404, confidence=0.95),
            contrasts=['argmax_r4 - sampled_r4', 'argmax_r1 - sampled_r1', 'sampled_r1 - sampled_r4', 'argmax_r1 - argmax_r4',
                       '(argmax_r1 - argmax_r4) - (sampled_r1 - sampled_r4)'],
            uncertainty='Conditional on this one chosen checkpoint; repeated development evidence, not training-replica or confirmation uncertainty.'),
        prediction='A selector-by-frequency interaction is plausible: faster decisions can improve reaction while creating more opportunities for a harmful sampled action.',
        interpretation='Selector effects do not identify entropy as their cause. Repeat effects include feedback timing and closed-loop observation distribution changes. No one-frame inference gain does not rule out one-frame training.',
        state_path=str(ROOT / 'learning/runs/v2-orchestration/state.json'), lease_key='active_inference_diagnostic', expected_lease=lease,
        attempt_claim_path=str(V2 / RUN_ID / 'attempt.claimed'), launch_marker_path=str(V2 / RUN_ID / 'launch.claimed'),
        no_training=True, no_promotion=True, input_pins={**pins, **{str(HERE / name): b.sha(HERE / name)
            for name in ('cohort-reservation.json', 'calibration.json', 'user-authorization.json')}})
    b.save(HERE / 'protocol.json', protocol)
    print(json.dumps(dict(cohort='D7', seeds=256, groups=8, episodes=2048,
                         estimated_all_capped_seconds=worst_projection, hard_work_seconds=7200)))


if __name__ == '__main__':
    main()
