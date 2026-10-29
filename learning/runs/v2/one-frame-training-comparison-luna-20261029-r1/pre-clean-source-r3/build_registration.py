"""Build an inert DODGE-013 registration from parent-owned immutable inputs."""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import binding as b
import seeds


def validate_inputs():
    p = b.protocol()
    d = b.design()
    q = b.read(b.PARENT/'qualification-protocol.json')
    b.verify_pins(p['input_pins'])
    b.need(p['status'] == 'parent_approved_pre_run_protocol' and p['launch_authority'] is False,
           'parent protocol is not inert and approved')
    b.need(d['status'] == 'pre_run_design_source_and_resource_qualification_pending'
           and d['training_launched'] is False and d['no_promotion'] is True,
           'registered design state differs')
    b.need(q['status'] == 'preparation_pending_source_acceptance' and q['launch_authority'] is False,
           'qualification protocol is not inert')
    b.need(q['run_id'] == 'one-frame-training-resource-qualification-20261029-r1'
           and q['design_sha256'] == b.sha(b.DESIGN)
           and q['checkpoint_sha256'] == p['checkpoint']['sha256'], 'qualification identity differs')
    reservation = b.read(p['evaluation']['reservation_path'])
    b.need(reservation['schema'] == 'one_frame_training_evaluation_cohort_v1'
           and reservation['status'] == 'parent_reserved' and reservation['outcomes_read'] is False
           and reservation['name'] == 'D9', 'D9 reservation is not closed and unread')
    b.need(reservation['seeds'] == p['evaluation']['seeds']
           and len(reservation['seeds']) == p['evaluation']['seed_count']
           and reservation['seed_vector_sha256_u32be'] == p['evaluation']['seed_vector_sha256'],
           'protocol/reservation seed vector differs')
    b.need(b.sha(p['evaluation']['reservation_path']) == p['evaluation']['reservation_sha256'],
           'D9 reservation hash differs')
    expected_interpreter = b.ROOT/'python/.venv/bin/python'
    b.need(Path(sys.executable).resolve() == expected_interpreter.resolve()
           and expected_interpreter.is_file(), 'registration builder must use project Python')
    b.need(p['training_episode_streams']['capacity_per_slot'] == seeds.frame_stream_capacity(
        p['gameplay_frame_target_per_arm'])
        and p['training_episode_streams']['qualification_capacity_per_slot'] == seeds.frame_stream_capacity(
            q['gameplay_frame_target_per_arm']), 'registered stream capacities differ')
    return p, d, q, reservation


def build():
    p, d, q, reservation = validate_inputs()
    source_path = b.SOURCE_MANIFEST
    runtime_path = b.RUNTIME_MANIFEST
    b.need(source_path.is_file() and runtime_path.is_file(), 'source/runtime manifests must be sealed first')
    source = b.read(source_path)
    b.need(source.get('schema') == 'one_frame_training_comparison_source_manifest_v1'
           and source.get('run_id') == b.RUN_ID, 'source manifest identity differs')
    for name, digest in source['files'].items():
        path = b.HERE/name
        b.need(path.is_file() and not path.is_symlink() and b.sha(path) == digest,
               'source drift: '+name)
    runtime, runtime_root = b.runtime_files()
    b.need(runtime.get('schema') == 'one_frame_training_comparison_runtime_manifest_v1'
           and runtime.get('runtime_root') == str(b.RUNTIME_ROOT.resolve()), 'runtime manifest identity differs')
    b.need(runtime['runtime_root'] == str(runtime_root), 'runtime path differs')
    pool = seeds.validate_pool(b.read(b.TRAINING_POOL))
    seeds.verify_exclusions(pool, p['exclusion_union'])
    stream_seeds, stream_components, stream_digests = seeds.materialize(
        pool, p['training_pair_seed'], p['training_episode_streams']['capacity_per_slot'])
    q_capacity = p['training_episode_streams']['qualification_capacity_per_slot']
    _, _, qualification_digests = seeds.materialize(pool, p['training_pair_seed'], q_capacity)

    state = b.read(p['state_path'])
    work = state.get('one_frame_training_comparison_work')
    expected_work = dict(p['expected_parent_work_identity'])
    expected_work['protocol_path'] = str(b.PROTOCOL_PATH)
    expected_work['protocol_sha256'] = b.sha(b.PROTOCOL_PATH)
    b.need(type(work) is dict and all(work.get(k) == value for k, value in expected_work.items()),
           'main ledger parent work binding differs')

    expected_sources = sorted(source['files'])
    input_pins = dict(p['input_pins'])
    input_pins.update({str(source_path): b.sha(source_path), str(runtime_path): b.sha(runtime_path),
                       str(b.PROTOCOL_PATH): b.sha(b.PROTOCOL_PATH),
                       str(b.PARENT/'qualification-protocol.json'): b.sha(b.PARENT/'qualification-protocol.json'),
                       str(p['evaluation']['reservation_path']): p['evaluation']['reservation_sha256']})
    for name, digest in runtime['files'].items():
        input_pins[str(runtime_root/name)] = digest
    reg = dict(
        schema=b.PACKAGE_SCHEMA, status='source_review_pending', launch_authority=False,
        run_id=b.RUN_ID, experiment_id=b.EXPERIMENT_ID,
        protocol_path=str(b.PROTOCOL_PATH), protocol_sha256=b.sha(b.PROTOCOL_PATH),
        design_sha256=p['design_sha256'], preparation_sha256=p['preparation_sha256'],
        reuse_audit_sha256=p['reuse_audit_sha256'],
        source_manifest_path=str(source_path), source_manifest_sha256=b.sha(source_path),
        source_files=source['files'], source_members=expected_sources,
        runtime_root=str(runtime_root), runtime_manifest_path=str(runtime_path),
        runtime_manifest_sha256=b.sha(runtime_path), runtime_files=runtime['files'],
        checkpoint_path=p['checkpoint']['path'], checkpoint_sha256=p['checkpoint']['sha256'],
        checkpoint_metadata_path=p['checkpoint']['metadata_path'],
        checkpoint_metadata_sha256=p['checkpoint']['metadata_sha256'],
        checkpoint_global_update=p['checkpoint']['global_update'],
        checkpoint_phase_update=p['checkpoint']['phase_update'],
        checkpoint_cumulative_update=p['checkpoint']['cumulative_update'],
        model_fingerprint=p['checkpoint']['model_fingerprint'],
        adam_fingerprint=p['checkpoint']['adam_fingerprint'],
        arms=p['arms'], gameplay_frame_target_per_arm=p['gameplay_frame_target_per_arm'],
        training_pair_seed=p['training_pair_seed'], evaluation=d['evaluation'],
        evaluation_seeds=p['evaluation']['seeds'], evaluation_reservation_sha256=b.sha(p['evaluation']['reservation_path']),
        exclusion_union=p['exclusion_union'],
        streams=dict(schema='one_frame_training_comparison_paired_pool_stream_v1',
            training_pool_path=str(b.TRAINING_POOL), training_pool_file_sha256=b.sha(b.TRAINING_POOL),
            training_pool_sha256=pool['pool_sha256'], capacity_per_slot=len(stream_seeds[0]),
            initial_episode_indices=[0]*64, slot_stream_digests=stream_digests,
            qualification_capacity_per_slot=q_capacity,
            qualification_slot_stream_digests=qualification_digests),
        limits=dict(work_seconds=p['limits']['work_seconds'], total_seconds=p['limits']['total_seconds'],
            cleanup_seconds=p['limits']['cleanup_seconds'], postflight_seconds=p['limits']['postflight_seconds'],
            rss_bytes=p['limits']['rss_bytes'], mps_bytes=p['limits']['mps_bytes'],
            per_arm_gameplay_frames=p['limits']['per_arm_gameplay_frames'],
            max_updates_per_arm=q['max_PPO_updates_per_arm'],
            qualification=q),
        no_promotion=True, automatic_selection=False, training_eligible=False,
        expected_lease=p['expected_lease'], lease_key=p['lease_key'], state_path=p['state_path'],
        expected_parent_work_identity=expected_work,
        interpreter=str(b.ROOT/'python/.venv/bin/python'),
        interpreter_sha256=b.sha((b.ROOT/'python/.venv/bin/python').resolve()),
        import_policy=dict(pycache_prefix=str(b.HERE/'empty-pycache')),
        output=str(b.HERE/'worker-output'), attempt_claim_path=str(b.HERE/'attempt.claimed'),
        launch_marker_path=str(b.HERE/'launch.claimed'),
        input_pins=input_pins,
    )
    b.validate_static(reg)
    return reg


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    path = Path(args.output).resolve()
    b.need(path.parent == b.HERE, 'registration output must be package-owned')
    b.need(not path.exists(), 'registration output already exists')
    b.save(path, build())
    print(str(path))
