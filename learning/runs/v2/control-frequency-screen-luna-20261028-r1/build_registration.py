"""Build inert DODGE-002 registration from parent-pinned inputs; never launch."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
import binding as b


def validate_inputs():
    p=b.protocol();auth=b.read(b.PARENT/'user-authorization.json');cohort=b.read(b.PARENT/'cohort-reservation.json');cal=b.read(b.PARENT/'calibration.json');runtime=b.read(b.PARENT/'runtime-binding.json')
    b.verify_pins(p['input_pins'])
    b.need(auth['schema']=='control_frequency_screen_authorization_v1' and auth['status']=='authorized_inference_only' and auth['experiment']=='DODGE-002','inference authorization missing')
    b.need(all(auth.get(k)is True for k in ('no_training','no_optimizer','no_checkpoint_write','no_policy_adoption_or_promotion')),'authorization boundaries differ')
    b.need(cohort['schema']=='control_frequency_screen_cohort_v1' and cohort['status']=='parent_reserved' and cohort['name']=='D7' and cohort['outcomes_read'] is False,'cohort reservation differs')
    seeds=p['seeds'];b.need(seeds==cohort['seeds'] and len(seeds)==256 and seeds==sorted(set(seeds)),'protocol/reservation seeds differ')
    b.need(p['limits']==auth['limits']==cal['limits'],'authorization/calibration limits differ')
    b.need(auth['checkpoint_sha256']==p['checkpoint']['sha256'] and auth['selected_checkpoint_update']==420,'selected checkpoint identity differs')
    b.need(runtime['schema']=='control_frequency_screen_runtime_binding_v1' and runtime['status']=='native_parity_accepted_actual_MPS_startup_pending'
        and runtime['both_repeat_arms_use_this_same_runtime'] is True,'common native runtime not parent-bound')
    b.verify_pins(runtime['pins'])
    interpreter=b.ROOT/'python/.venv/bin/python'
    b.need(sys.version.split()[0]==runtime['runtime_versions']['python'] and Path(sys.executable).resolve()==interpreter.resolve(),'registration builder must use the pinned project Python')
    return p,auth,cohort,cal,runtime


def build():
    p,auth,cohort,cal,runtime=validate_inputs()
    source_path=b.HERE/'source-manifest.json';b.need(source_path.is_file(),'source manifest must be sealed first')
    source_sha=b.sha(source_path)
    manifest=b.read(source_path)
    for name,digest in manifest['files'].items():b.need(b.sha(b.HERE/name)==digest,'source drift: '+name)
    b.need(runtime['runtime_manifest_sha256']==b.sha(runtime['runtime_manifest_path']),'runtime manifest digest differs')
    seed_bytes=b''.join(int(seed).to_bytes(4,'big') for seed in p['seeds'])
    b.need(__import__('hashlib').sha256(seed_bytes).hexdigest()==cohort['seed_vector_sha256_u32be'],'cohort seed-vector hash differs')
    state=b.read(p['state_path']);work=state.get('control_frequency_screen_work')
    expected_work=dict(candidate_update=420,official_parent_unchanged=324,protocol_path=str(b.PROTOCOL_PATH),protocol_sha256=b.sha(b.PROTOCOL_PATH),cohort_reservation_path=str(b.PARENT/'cohort-reservation.json'),cohort_reservation_sha256=b.sha(b.PARENT/'cohort-reservation.json'),runtime_binding_path=str(b.PARENT/'runtime-binding.json'))
    b.need(type(work)is dict and all(work.get(k)==v for k,v in expected_work.items()),'main ledger work record differs')
    model=auth['checkpoint_sha256']
    death_helper=b.HERE/'death_telemetry.py';death_sha=b.sha(death_helper)
    sidecar=Path(p['checkpoint']['sidecar_path'])
    b.need(b.sha(p['checkpoint']['path'])==model and b.sha(sidecar)==p['checkpoint']['sidecar_sha256'],'candidate checkpoint/sidecar pin differs')
    condition_map={item['id']:dict(action_mode=item['action_mode'],action_repeat=item['action_repeat'],repetitions=item['repetitions']) for item in p['conditions']}
    pins=dict(p['input_pins']);pins.update(runtime['pins']);pins[str(b.PARENT/'runtime-binding.json')]=b.sha(b.PARENT/'runtime-binding.json')
    pins[str(source_path)]=source_sha;pins[str(runtime['runtime_manifest_path'])]=runtime['runtime_manifest_sha256'];pins[str(death_helper)]=death_sha;pins[str(b.PROTOCOL_PATH)]=b.sha(b.PROTOCOL_PATH)
    pins[p['checkpoint']['path']]=model;pins[p['checkpoint']['sidecar_path']]=p['checkpoint']['sidecar_sha256']
    reg=dict(schema='control_frequency_screen_registration_v1',status='source_review_pending',launch_authority=False,run_id=p['run_id'],experiment_id=p['experiment_id'],
        parent_protocol_path=str(b.PROTOCOL_PATH),protocol_sha256=b.sha(b.PROTOCOL_PATH),authorization_path=str(b.PARENT/'user-authorization.json'),
        authorization_sha256=b.sha(b.PARENT/'user-authorization.json'),cohort_reservation_path=str(b.PARENT/'cohort-reservation.json'),
        cohort_reservation_sha256=b.sha(b.PARENT/'cohort-reservation.json'),calibration_path=str(b.PARENT/'calibration.json'),calibration_sha256=b.sha(b.PARENT/'calibration.json'),
        runtime_binding_path=str(b.PARENT/'runtime-binding.json'),
        source_manifest_path=str(source_path),source_manifest_sha256=source_sha,runtime_root=runtime['runtime_root'],
        runtime_manifest_path=runtime['runtime_manifest_path'],runtime_manifest_sha256=runtime['runtime_manifest_sha256'],
        runtime_versions=runtime['runtime_versions'],backend=p['backend'],dtype=p['dtype'],torch_num_threads=p['torch_num_threads'],
        checkpoint_path=p['checkpoint']['path'],checkpoint_sha256=model,checkpoint_sidecar_path=p['checkpoint']['sidecar_path'],checkpoint_sidecar_sha256=p['checkpoint']['sidecar_sha256'],
        checkpoint_global_update=420,model_fingerprint=p['checkpoint']['model_fingerprint'],fingerprint_helper_path=runtime['fingerprint_helper_path'],fingerprint_helper_sha256=runtime['fingerprint_helper_sha256'],death_telemetry_path=str(death_helper),death_telemetry_sha256=death_sha,
        seeds=p['seeds'],cohort_name=p['cohort'],cohort_range=cohort['range'],cohort_sha256=b.sha(b.PARENT/'cohort-reservation.json'),
        evaluation_exclusions=p['evaluation_exclusions'],condition_map=condition_map,conditions=p['conditions'],condition_limits=p['condition_limits'],order=p['order'],controller_seeds=p['controller_seeds'],
        bootstrap=dict(seed=p['statistics']['bootstrap']['seed'],draws=p['statistics']['bootstrap']['draws'],confidence=p['statistics']['bootstrap']['confidence'],contrasts=p['statistics']['contrasts']),
        limits=p['limits'],batch_size=p['batch_size'],neural_inputs=p['neural_inputs'],environment=p['environment'],expected_lease=p['expected_lease'],lease_key=p['lease_key'],state_path=p['state_path'],expected_parent_work_identity=expected_work,
        interpreter=str(b.ROOT/'python/.venv/bin/python'),interpreter_sha256=b.sha((b.ROOT/'python/.venv/bin/python').resolve()),import_policy=dict(pycache_prefix=str(b.HERE/'empty-pycache')),
        output=str(b.HERE/'worker-output'),attempt_claim_path=p['attempt_claim_path'],launch_marker_path=p['launch_marker_path'],
        no_training=True,no_optimizer=True,no_checkpoint_write=True,automatic_selection=False,promoted=False,training_eligible=False,
        input_pins=pins,calibration_projection=dict(estimated_all_capped_seconds=cal['estimated_all_capped_seconds'],margin_included_seconds=cal['margin_included_seconds'],margin_factor=cal['margin_factor']))
    b.need(reg['expected_lease']==p['expected_lease'],'lease identity must come from parent protocol')
    return reg


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    path=Path(args.output).resolve();b.need(path.parent==b.HERE,'registration output must be owned')
    b.save(path,build());print(str(path))
