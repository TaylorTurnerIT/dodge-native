"""Freeze a new consumed-seed evaluation; never execute native work."""
import json
from pathlib import Path
import common as c

root=Path(__file__).resolve().parents[4]
old=root/'learning/runs/v2/teacher-ray-local-20261031-r1'
parent=root/'learning/runs/v2/teacher-local-parent-20261031-r1/dispatch-DODGE066-local-r1'
reg066=c.read(old/'registration-r1.json');terminal=c.read(old/'parent-terminal-audit.json')
for name in ['output','output/worker','output/supervisor','empty-pycache']:(c.HERE/name).mkdir()
authority=dict(schema='dodge_specific_local_evaluation_authority_v1',record='DODGE-068',training_record='DODGE-066',
    user_directive="Taylor now says 'Go' to testing the CURRENT saved wall-ray checkpoints locally after the budget discussion.",
    authorized='One fixed-weight local evaluation of all four predeclared final066 endpoints plus420; no optimizer, training, selection, promotion or cloud.',
    cohort_authority='Specifically reuse the first128 ascending seeds of recorded consumed telemetry3657433088..3657435135. Exploratory development only; no heldout opening.',
    work_seconds=7200,receipt_seconds=180,total_seconds=7380,no_retry=True,
    training_registration_sha256=c.sha(old/'registration-r1.json'),training_acceptance_sha256=c.sha(parent/'coordinator-terminal-audit.json'),
    accepted_training_release_sha256=c.sha(parent/'lease-release.json'))
c.save(c.HERE/'authority.json',authority)
predictions=dict(timing='before_any_evaluation_outcome',point_prediction_rays_minus_control_frames=dict(r1=dict(Mean=0,Q1=0),r2=dict(Mean=0,Q1=0)),
    hypothesis='A ray benefit is plausible, but direction and magnitude remain unknown; centered zero point predictions avoid assuming efficacy.',
    qualification='After first64 counted games for EACH model, forecast elapsed +1.2*max full-path round cost*18000*remaining batches +240s IO/analysis <7200. No outcome-based stopping.',
    stopping='Deadline, resource, identity, native/device, first failure, missing receipt or forecast failure stops once and preserves partials and exact held lease. No retries or sample changes.')
c.save(c.HERE/'predictions.json',predictions)
models=[]
for t in terminal['trajectories']:
    if t['job'] in ['r1-control','r1-rays','r2-rays','r2-control']:
        a=t['final_checkpoint'];models.append(dict(name=t['job'],path=a['path'],sha256=a['sha256'],model_fingerprint=a['model_fingerprint']))
models.sort(key=lambda x:['r1-control','r1-rays','r2-rays','r2-control'].index(x['name']))
models.append(dict(name='420',path=reg066['checkpoint_path'],sha256=reg066['checkpoint_sha256'],model_fingerprint=reg066['model_fingerprint']))
provenance=root/'learning/runs/v2/track-a-review-scaling-parent-20261030-r1/consumed-death-telemetry-cohort.json'
inputs={**reg066['input_pins'],**reg066['source_pins']}
files=[old/'registration-r1.json',old/'parent-terminal-audit.json',old/'CPU-runtime-preflight.json',
       parent/'coordinator-terminal-audit.json',parent/'lease-release.json',parent/'coordinator-preaccept-proof.json',
       parent/'training-completion.json',provenance,c.HERE/'authority.json',c.HERE/'predictions.json',c.HERE/'source-qualification.json',
       root/'learning/runs/v2/control-frequency-confirmation-parent-20261029-r1/calibration.json']
for name in ['r1-control','r1-rays','r2-rays','r2-control']:
    files.extend(old/'outputs'/name/f for f in ['parent-job-audit.json','result.json','exit.json'])
files.extend(Path(m['path']) for m in models)
for p in files:inputs[str(p)]=c.sha(p)
reg=dict(schema='dodge_local_fixed_endpoint_evaluation_v1',record='DODGE-068',package=str(c.HERE),project_root=str(root),
    interpreter=reg066['interpreter'],runtime_root=reg066['runtime_root'],runtime_members=reg066['runtime_members'],
    source_pins={str(p):c.sha(p) for p in sorted(c.HERE.glob('*.py'))},input_pins=inputs,
    training_acceptance_path=str(parent/'coordinator-terminal-audit.json'),training_release_path=str(parent/'lease-release.json'),
    training_terminal_path=str(old/'parent-terminal-audit.json'),seed_provenance_path=str(provenance),
    seeds=list(range(3657433088,3657433216)),models=models,games=640,batch_size=64,
    controller='sampled_per_game_cpu_generator_K1_no_shield_clean',
    controller_seed_domain='sha256(dodge068/paired-policy-v1/{seed}/clean) first8bytes bigendian; same stream across models',
    conditions=['clean'],action_repeat=1,raw_frame_cap=18000,startup_frames=13,difficulty=2,patterns_enabled=True,powerups_enabled=True,
    model_inputs=['global_feats','entity_feats','entity_types','entity_mask'],
    observability='Identical accepted066 native/runtime four buffers for both arms; rays derive geometry only from these arrays. No hidden state, seeds, death telemetry or future RNG enters the model.',
    work_seconds=7200,receipt_seconds=180,total_seconds=7380,IO_analysis_reserve_seconds=240,
    rss_bytes=6*1024**3,mps_bytes=6*1024**3,allocator_bytes=reg066['allocator_bytes'],threads=reg066['threads'],
    minimum_free_disk_bytes=1024**3,exclusions=reg066['exclusions'],cache=str(c.HERE/'empty-pycache'),
    state_path=reg066['state_path'],expected_lease=dict(kind='fixed_endpoint_local_evaluation',record='DODGE-068',owner_token='eval068-local-20261101-r1',package=str(c.HERE),promoted=False),
    no_retry=True,no_resume=True,training=False,promotion=False,battery_operation_allowed=True,AC_required=False,
    bootstrap_draws=10000,bootstrap_seed=20261101068,early_death_max_frames=600,
    panel_decision='Clean-first128 consumed shared seeds/model,640 games,exploratory. Full10240 panel lacks a compatible qualified timing forecast; historical K4 rate4.1206242359344675e-5s/rawframe times4 K1 cost and1.2 margin implies36455s all-cap before ray overhead.128 clean seeds leaves substantial headroom; actual all-model counted prefix must qualify. No noise or fresh confirmation.',
    acceptance='Strict parent recomputes declared coverage, frame identities, paired bootstrap, hashes, bounded resources and direct worker/supervisor/helper reap and group absence, then durable accepted audit BEFORE exact shared-lock release.')
c.save(c.HERE/'registration-r1.json',reg)
print(c.sha(c.HERE/'registration-r1.json'))
