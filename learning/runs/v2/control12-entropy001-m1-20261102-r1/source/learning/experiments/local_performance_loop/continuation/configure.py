"""Author a new exact local control continuation registration, without runtime work."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',required=True);parser.add_argument('--record',required=True)
    a=parser.parse_args();root=Path(__file__).resolve().parents[4]
    out=root/'learning/runs/v2'/a.run_id;out.mkdir()
    (out/'inputs').mkdir()
    old_path=root/'learning/runs/v2/performance-loop-20261101-r1/config.json'
    old=json.loads(old_path.read_text())
    stage=root/'learning/runs/v2/m1-stage-tailscale-20261102-r1'
    remote_root=Path('/Users/taylor/Projects/dodge-native')
    remote=remote_root/'learning/runs/v2'/a.run_id
    remote_stage=remote_root/'learning/runs/v2/m1-stage-tailscale-20261102-r1'
    remote_code=remote/'source/learning/experiments/local_performance_loop/continuation'
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    proposal=root/'learning/runs/v2/performance-loop-20261101-r1/next-control-stability-contract.json'
    assert sha(proposal)=='5b25e74c5e03fd342428c441badc5461a35cff52b7ddd35eca04f407e7c2d8ad'
    files={'source-config.json':old_path,'approved-proposal.json':proposal,
        'accepted067.json':root/'learning/runs/v2/performance-loop-20261101-r1/output/parent-terminal-audit.json',
        'training-pool512.json':Path(old['pool_path']),
        'development-provenance.json':Path(old['development_provenance'])}
    for name in ['worker.py','fingerprints.py','update_telemetry.py']:
        source=Path(old['training_components'])/name
        assert sha(source)==old['input_pins'][str(source)]
        files['training-components/'+name]=source
    input_pins={}
    for name,source in files.items():
        target=out/'inputs'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        input_pins[str(remote/'inputs'/name)]=sha(target)
    staged_manifest=json.loads((root/'learning/runs/v2/m1-stage-20261102-r1/manifest.json').read_text())
    for member in staged_manifest['files']:
        input_pins[str(remote_stage/'inputs'/member['path'])]=member['sha256']
    for name in ['qualification-audit.json','lease-release.json','installed-inventory.json','machine-binding.json']:
        input_pins[str(remote_stage/name)]=sha(stage/name)
    authority=dict(direct_user_quote='Act autonomously I have already given the direction. Go forth and prosper.',
        approval='Explicit latest user message authorizes this ONE M1 control12+Adam LR1e-5 continuation with mean-oriented measured-play exploitation.',
        scope='Existing K1 recipe and512 training support; initial72 additional updates,12-update/512 consumed-development play checks,live continuation under frozen policy; no routine replicas,rays,huge held evaluation,cloud or public promotion.',
        fresh_simulator_segment=True,no_arbitrary_local_wallclock_cutoff=True,no_retry=True)
    (out/'authority.json').write_text(json.dumps(authority,indent=2,sort_keys=True)+'\n')
    input_pins[str(remote/'authority.json')]=sha(out/'authority.json')
    machine=json.loads((stage/'machine-binding.json').read_text())
    machine={k:machine[k] for k in ('environment_id','platform_uuid_sha256','architecture')}
    control_meta=json.loads((root/'learning/runs/v2/performance-loop-20261101-r1/output/worker/control/checkpoints/checkpoint-000012.json').read_text())
    max_checks=math.ceil(math.log(18000*512)/math.log(1.02))*3+8
    settings=dict(initial_updates=72,segment_updates=12,patience_checks=3,gain_fraction=.02,max_checks=max_checks,
        minimum_Q1_fraction=.90,early_death_allowance_fraction=.02,
        selection='Higher observed Mean with Q1>=90% same-machine control12 Q1 and early deaths<=control12+ceil(2%games). Preserve all checkpoints and420 fallback.',
        continuation='At/after72: require a2% guarded Mean gain within last36 updates and current guarded play>=95% retained-best Mean,or guarded recovery>=110% first check and>=95% startMean. Three severe checks,stall,or failing competitiveness stops.',
        finiteness='Each guarded mean anchor advances at least2%; bounded18000-frame game and minimum positive mean1/512 imply finitely many gains; three-check patience. This is not a wall-clock cap.',
        uncertainty='Same consumed512 development seeds, paired1000-bootstrap descriptive intervals; no significance/replication gate or independent confirmation.')
    source_pins={}
    source_files=list(Path(__file__).parent.glob('*.py'))+list(Path(__file__).parents[1].glob('*.py'))
    for source in source_files:
        relative=source.relative_to(root)
        source_pins[str(remote/'source'/relative)]=sha(source)
    reg=dict(schema='local_performance_continuation_v1',record=a.record,run_dir=str(remote),runner=str(remote_code),
        project_root=str(remote_root),machine=machine,state_path='/Users/taylor/.local/state/dodge-native/accelerator/state.json',
        expected_lease=dict(kind='local_control12_lowerLR_continuation',record=a.record,owner_token=a.run_id,
            package=str(remote),machine=machine,promoted=False),
        execution_authorized=True,training_authorized=True,cloud_authorized=False,promotion=False,no_retry=True,no_automatic_resume=True,
        input_pins=input_pins,source_pins=source_pins,source_config_path=str(remote/'inputs/source-config.json'),
        accepted067_path=str(remote/'inputs/accepted067.json'),accepted_M1_path=str(remote_stage/'qualification-audit.json'),
        interpreter='/private/tmp/dodge-m1-readiness-20261102-kYIx4A/venv/bin/python',
        versions=json.loads((stage/'installed-inventory.json').read_text())['versions'],
        runtime_root=str(remote_stage/'inputs/runtime'),runtime_members=old['runtime_members'],
        training_components=str(remote/'inputs/training-components'),pool_path=str(remote/'inputs/training-pool512.json'),
        development_provenance=str(remote/'inputs/development-provenance.json'),exclusions=old['exclusions'],
        checkpoint_path=str(remote_stage/'inputs/checkpoints/checkpoint420.pt'),checkpoint_sha256=old['checkpoint_sha256'],
        model_fingerprint=old['model_fingerprint'],adam_fingerprint=old['adam_fingerprint'],
        warmstart=dict(path=str(remote_stage/'inputs/checkpoints/control12.pt'),sha256=control_meta['sha256'],
            model_fingerprint=control_meta['model_fingerprint'],adam_fingerprint=control_meta['adam_fingerprint'],
            registration_sha256='d3241cb8e272bf461487e2e9edcd925351ed9244b4c77a955d1313b03fdb4157',
            parent_updates=12,parent_actual_frames=786432,parent_Adam_steps=1536,restore_source_RNG=True,
            full_simulator_restore=False,new_games_reason='Authorized fresh simulator segment; learner+Adam+RNG retained,LRonly changed.'),
        job_order=['control'],jobs=[dict(id='control',arm='control',replica='1')],
        replicas={'1':dict(old['replicas']['1'],environment_seed=2026110206)},
        arms={'control':old['arms']['control']},ppo=dict(old['ppo'],learning_rate=1e-5),
        action_repeat=1,envs=64,rollout=1024,effective_minibatch=2048,microbatch=512,threads=4,
        initial_updates=72,segment_updates=12,prefix_updates=2,max_updates=max_checks*12,frame_target=max_checks*12*65536,
        policy=settings,evaluation_seeds=old['evaluation_seeds'],evaluation_controller_domain=old['evaluation_controller_domain'],
        baseline_policy='Measure all512 games for420 AND control12 on M1 within this loop. No cross-machine cached numerical rows.',
        source_rng_policy='Restore exact sourcecontrol12 learner sampling RNG; native games start a newly registered master on unchanged512 training support.',
        rss_bytes=6*1024**3,mps_bytes=6*1024**3,allocator_bytes=old['allocator_bytes'],minimum_free_disk_bytes=2*1024**3,
        work_seconds=None,total_seconds=None,forecast_fit_gate=False,cache=str(remote/'empty-pycache'),
        prefix_policy='First TWO actual counted updates qualify real M1 model/Adam/device/resources/passiveGAE/return/native counts; timings are estimates only,never fit-deadline admission.',
        callback=dict(department_thread='mcp:d8b402b6-b02b-4133-9c60-8fe5a0da6dde',mode='auto',
            request_id=a.run_id+'-terminal-call-home-v1',events=['true_completion','material_performance_breakthrough','real_blocker'],no_recurring_schedule=True))
    (out/'config.json').write_text(json.dumps(reg,indent=2,sort_keys=True)+'\n')
    (out/'source-manifest.json').write_text(json.dumps(source_pins,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(run_dir=str(out),remote_run_dir=str(remote),registration_sha256=sha(out/'config.json'),max_checks=max_checks)))


if __name__=='__main__':main()
