"""Create a distinct immutable config for the reusable runner; no native work."""
import argparse
import math
from pathlib import Path
import common as c


def main():
    p=argparse.ArgumentParser();p.add_argument('--run-dir',required=True);p.add_argument('--record',default='DODGE-067');args=p.parse_args()
    run=Path(args.run_dir).resolve();run.mkdir();root=c.CODE.parents[2]
    source=root/'learning/runs/v2/teacher-ray-local-20261031-r1';pilot=root/'learning/runs/v2/teacher-ray-eval-local-20261101-r1'
    old=c.read(source/'registration-r1.json');previous=c.read(pilot/'registration-r1.json')
    for name in ['output','output/worker','output/supervisor','empty-pycache']:(run/name).mkdir()
    authority=dict(record=args.record,user_directive='Good. Trim. I love that loop.',
        scope='Explicit approval to implement and RUN local train -> measure -> keep best -> continue; one matched entity-control/R0-ray pair from420+Adam,initial72updates/model,current accepted K1 recipe. No duplicate seeds/automatic confirmation/cloud/other experiments or public promotion.',
        no_wall_clock_cutoff=True,large_evaluation_remains_held=True)
    c.save(run/'authority.json',authority)
    max_checks=math.ceil(math.log(18000*512/4)/math.log(1.02))*3+8
    config=dict(old)
    config.update(schema='local_performance_loop_config_v1',record=args.record,runner=str(c.CODE),run_dir=str(run),project_root=str(root),
        execution_authorized=True,training_authorized=True,cloud_authorized=False,promotion=False,no_retry=True,no_automatic_resume=True,
        job_order=['control','rays'],jobs=[dict(id='control',arm='control',replica='1'),dict(id='rays',arm='rays',replica='1')],
        replicas={'1':dict(constructor_seed=2026110100,python_seed=2026110101,numpy_seed=2026110102,torch_cpu_seed=2026110103,torch_mps_seed=2026110104,branch_seed=2026110105,environment_seed=2026110106)},
        initial_updates=72,segment_updates=12,max_updates=max_checks*12,frame_target=max_checks*12*65536,
        policy=dict(initial_updates=72,segment_updates=12,patience_checks=3,gain_fraction=.02,max_checks=max_checks,
            purpose='Practical development selection, not significance or repeatability proof. Mean/Q1/early deaths drive choices; EV/KL never substitute for play.',
            early_cull='After at least72updates,three consecutive play checks below80% referenceQ1 AND90% referenceMean stop the arm.',
            continuation='At/after72 continue only with a meaningful gain within last3 checks AND either competitive play(Q1/Mean>=95%reference) or strong recovery(Q1>=110%firstcheck,>=85%reference,Mean>=90%reference). Otherwise stop.',
            retention='Select higher observedQ1 only if Mean>=95%reference and earlydeaths<=reference+ceil(2%games). Keep all prior checkpoints; best starts at functional420. No automatic promotion.',
            finiteness='max_checks follows bounded18000-frameQ1,minimum positive quarter-mean4/512,and>=2% meaningful gains with3-check patience. Not a wall-clock or initial72 cap.'),
        work_seconds=None,total_seconds=None,campaign_total_seconds=None,forecast_fit_gate=False,cache=str(run/'empty-pycache'),
        minimum_free_disk_bytes=2*1024**3,training_components=str(source),
        evaluation_seeds=list(range(3657433088,3657433600)),evaluation_controller_domain='dodge068/paired-policy-v1',
        cached_420_episodes=str(pilot/'output/worker/episodes.jsonl'),
        development_provenance=str(root/'learning/runs/v2/track-a-review-scaling-parent-20261030-r1/consumed-death-telemetry-cohort.json'),
        accepted066_path=str(root/'learning/runs/v2/teacher-local-parent-20261031-r1/dispatch-DODGE066-local-r1/coordinator-terminal-audit.json'),
        accepted068_path=str(pilot/'output/parent-terminal-audit.json'),authority_path=str(run/'authority.json'),authority_sha256=c.sha(run/'authority.json'),
        expected_lease=dict(kind='local_performance_training_loop',record=args.record,owner_token=run.name,package=str(run),promoted=False),
        evaluation_selection='512 fixed consumed development seeds,repeated for intentional performance selection. Baseline reuses128 exact068 rows and adds384 with identical sampler. Development results are not independent confirmation.')
    inputs={**old['input_pins'],**old['source_pins'],**previous['input_pins'],**previous['source_pins']}
    for path in [source/'registration-r1.json',pilot/'registration-r1.json',pilot/'review.json',pilot/'source-qualification.json',
        Path(config['accepted066_path']),Path(config['accepted068_path']),Path(config['cached_420_episodes']),pilot/'output/worker/result.json',
        pilot/'output/lease-release.json',Path(config['development_provenance']),run/'authority.json']:
        inputs[str(path)]=c.sha(path)
    c.save(run/'source-qualification.json',dict(status='nine_targeted_delta_checks_passed',tests=9,native_work=False,
        reused='Frozen066 PreparedUpdates,telemetry,runtime19/native,Adam migration and068 sampledK1/native/resource/lifecycle proof; no native rebuild or unchanged suite rerun.',
        source_pins={str(p):c.sha(p) for p in sorted(c.CODE.glob('*.py'))}))
    inputs[str(run/'source-qualification.json')]=c.sha(run/'source-qualification.json')
    config['input_pins']=inputs;config['source_pins']={str(p):c.sha(p) for p in sorted(c.CODE.glob('*.py'))}
    c.save(run/'config.json',config)
    print(c.sha(run/'config.json'))


if __name__=='__main__':main()
