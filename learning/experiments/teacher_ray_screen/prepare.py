"""Freeze an owned future R0 packet; never launch, claim or mutate global state."""

import argparse
import copy
import shutil
from pathlib import Path

import common as c

ROOT = Path(__file__).resolve().parents[3]
PARENT = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
QUEUE = PARENT / 'learning/runs/v2/teacher-training-queue-parent-20261030-r1'
SEED_SHA = 'bd6beac7bda62fb5a00affa9b4cc953d6c6447e373669ebe4c464ffa5f62879a'
RESUMPTION_SHA = 'a057090cfd5ea90ffba1457012ed20762e1c356a7b589bb7db1e302bdd6f2245'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--revision',type=int,default=1)
    parser.add_argument('--supersedes',type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    c.need(out.is_relative_to(ROOT / 'learning/runs/v2') and not out.exists(), 'Fresh owned packet required')
    base_path = PARENT / 'learning/runs/v2/k1-horizon-screen-20261030-r2/registration-r1.json'
    old = c.read(base_path)
    registry_path = QUEUE / 'seed-registry-r1.json'
    c.need(c.sha(registry_path) == SEED_SHA, 'Seed registry differs')
    registry = c.read(registry_path)
    authority_path=QUEUE/'authority-r2.json'
    power_path=QUEUE/'power-policy-r2.json'
    queue_path=QUEUE/'queue-r5.json'
    authority=c.read(authority_path);power=c.read(power_path);queue=c.read(queue_path)
    c.need(c.sha(authority_path)==queue['authority_sha256']
           and c.sha(power_path)==queue['power_policy_sha256']==authority['power_policy_sha256'],
           'Current authority/power binding differs')
    c.need(power['AC_required'] is False and power['battery_operation_allowed'] is True
           and power['sleep_prevention']['required_assertions']==['PreventUserIdleSystemSleep'],
           'Battery-allowed power policy required')
    resumption_path = QUEUE/'source-resumption-disposition-r1.json'
    c.need(c.sha(resumption_path) == RESUMPTION_SHA, 'Source resumption disposition differs')
    history = c.read(registry['fresh_training_additional_exclusions']['seed_values_paths'][0])
    c.need(history['count'] == len(history['sorted_unique_seed_values']) == 189743, 'History coverage differs')
    reg = {key: copy.deepcopy(old[key]) for key in (
        'IO_reserve_seconds','adam_fingerprint','allocator_bytes','checkpoint_path',
        'checkpoint_sha256','effective_minibatch','envs','frame_target','interpreter','microbatch',
        'model_fingerprint','mps_bytes','pool_path','ppo','prefix_updates','receipt_seconds','rollout',
        'rss_bytes','state_path','threads','updates','work_seconds','campaign_total_seconds')}
    reg.update(schema='dodge_ray_training_registration_v1', record='DODGE-055',
        run_id=out.name, package=str(out), revision=args.revision,
        runtime_root=str(out / 'runtime'), runtime_members=[], source_pins={}, input_pins={},
        coordinator_state_path=old['state_path'], coordinator_thread='518b8c2d-01fb-4f39-acc3-f2d9f1f35c4e',
        action_repeat=1, no_retry=True, no_automatic_resume=True, promotion=False,
        one_MPS_job=True, launch_authority=False, evaluation_games=0,
        review_scope='training_only',evaluation_requires_separate_frozen_review=True,
        AC_required=False,battery_operation_allowed=True,power_policy_path=str(power_path),
        power_policy_sha256=c.sha(power_path),authority_path=str(authority_path),
        authority_sha256=c.sha(authority_path),queue_path=str(queue_path),queue_sha256=c.sha(queue_path),
        exclusions=registry['future_training_exclusion_ranges'],
        checkpoint_updates=[12,24,36],
        arms={name:dict(gamma=0.9987476493904754,gae_lambda=0.9872585449014338) for name in ('control','rays')},
        jobs=[dict(id=f'r{r}-{arm}',replica=str(r),arm=arm) for r,arm in
              ((1,'control'),(1,'rays'),(2,'rays'),(2,'control'))],
        replicas={str(r):dict(constructor_seed=202610305100+r,python_seed=202610305200+r,
            numpy_seed=746855000+r,torch_cpu_seed=202610305400+r,torch_mps_seed=202610305500+r,
            environment_seed=202610305600+r,branch_seed=202610305900+r) for r in (1,2)},
        expected_lease=dict(kind='teacher_ray_training_screen',run_id=out.name,
            package=str(out),owner_token=f'rays055-20261030-first-screen-r{args.revision}',promoted=False),
        qualification='First two updates count toward each trajectory; actual frames, passive GAE parity, device/migration and full-path 20%+IO forecast. Failure preserves first evidence and holds exact global lease.',
        checkpoint_limit='Model/Adam/RNG and adapter metadata only; no full simulator restore, resume or promotion.',
        evaluation=dict(cohort='D13',range_inclusive=[3724541952,3724542975],count=1024,
            status='reserved_unopened_until_strict_training_parent_acceptance',
            models=['420','r1-control','r1-rays','r2-rays','r2-control'],conditions=['clean','epsilon0.01','epsilon0.05','delay1','delay4'],
            noise_subset_count=256,clean_games=5120,noise_games=5120,
            worker_work_seconds=7200,receipt_seconds=180,overall_seconds_ceiling=29700,
            IO_analysis_reserve_seconds=240,bootstrap_draws=2000,bootstrap_seed=202610305777,
            action_mode='sampled_CPU_per_game_policy_generator',raw_frame_cap=18000,
            noise_subset='first256 ascending D13 seeds; clean recomputed on same rows',
            epsilon_definition='Per K1 decision, replace requested action by uniform nine-action draw including original; log realized changes.',
            delay_definition='Causal FIFO in raw frames (K1); start neutral action0, hold last applied until due, clear at episode boundary.',
            RNG_definition='SHA256 ray055_eval_v1/policy_or_executor/game_seed/condition; independent CPU policy torch generator and executor Python Random. Neither reads native RNG.',
            milestones=[1000,2000,5000,10000,18000],early_death_max_frames=600,
            groups=[dict(model=model,condition=condition,count=1024 if condition=='clean' else 256)
                for model in ['420','r1-control','r1-rays','r2-rays','r2-control']
                for condition in ['clean','epsilon0.01','epsilon0.05','delay1','delay4']],
            endpoint_rule='Only registered final update36 for all four trajectories, plus unchanged420; no outcome-based selection.',
            uncertainty='Marginal Q1/Q4 sorted per condition; paired game-seed bootstrap, 2000 shared draws. Replicas separate; this is not training-replica uncertainty.',
            separate_coordinator_dispatch_required=True),
        evaluation_expected_lease=dict(kind='teacher_ray_D13_evaluation',run_id=f'teacher-ray-D13-20261030-r{args.revision}',
            package=str(out),owner_token=f'rays055-D13-20261030-first-eval-r{args.revision}',promoted=False))
    pins = dict(registry['pins'])
    pins.update({str(p):c.sha(p) for p in [base_path,authority_path,queue_path,power_path,registry_path,resumption_path,
        Path(reg['checkpoint_path']),Path(reg['interpreter'])]})
    if args.supersedes:
        prior=args.supersedes.resolve(); prior_reg=c.read(prior)
        c.need(not (prior.parent/'launch.claimed').exists() and
               not list((prior.parent/'outputs').rglob('worker.claimed')) and
               not list((prior.parent/'evaluation-output').iterdir()),'Cannot supersede a consumed candidate')
        pins[str(prior)]=c.sha(prior)
        reg['supersedes_unclaimed_candidate']=dict(registration_path=str(prior),sha256=c.sha(prior),
            reason='Reset per-attempt collection receipts; implement battery-allowed passive power policy. CPU/source resumption only; no training or qualification attempted.')
    for p,h in pins.items():
        c.need(c.sha(p) == h, 'Input pin differs: '+p)
    out.mkdir(parents=True)
    (out/'evaluation-output').mkdir()
    runtime = out / 'runtime/dodge_rl'; runtime.mkdir(parents=True)
    old_root = Path(old['runtime_root'])
    for path,digest in old['input_pins'].items():
        p = Path(path)
        if p.is_relative_to(old_root):
            c.need(c.sha(p) == digest, 'Trusted runtime input differs')
            dest = out/'runtime'/p.relative_to(old_root)
            dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(p,dest)
            pins[str(p)] = digest
    overlays = ['clearance_rays.py','ray_frontend.py','ray_migration.py','models/teacher.py','models/ray_teacher.py']
    for name in overlays:
        src = ROOT/'python/dodge_rl'/name
        shutil.copyfile(src,runtime/name); pins[str(src)] = c.sha(src)
    shutil.copyfile(c.HERE/'ppo_runtime.py',runtime/'ppo.py')
    for src in c.HERE.glob('*.py'):
        shutil.copyfile(src,out/src.name); reg['source_pins'][str(src)] = c.sha(src)
        reg['source_pins'][str(out/src.name)] = c.sha(out/src.name)
    for p in (out/'runtime').rglob('*'):
        if p.is_file():
            pins[str(p)] = c.sha(p); reg['runtime_members'].append(str(p.relative_to(out/'runtime')))
    reg['runtime_members'].sort(); reg['input_pins'] = pins
    for r in reg['replicas']:
        *_,digest = c.build_streams(reg,r); reg['replicas'][r]['stream_sha256'] = digest
    c.save(out/'predictions.json',dict(record='DODGE-055',timing='before_execution',
        doing='Two checkpoint420 warm-start replicas each: entity control vs static R0 residual, fixed K1 matched anchor.',
        expected='R0 may raise D13 Q1 by exposing wall/represented-hazard escape clearance; no gain is assumed. Both replica contrasts, Mean and noisy tails matter. Rays can miss oblique corridors, over-avoid benign rectangles or fail because horizon/exploration is limiting.',
        why='Derived spatial bias only; no new information, expert output, CNN, horizon or reward change.',
        actual=None,promotion=False,original_proposal=str(ROOT/'docs/teacher-ray-geometry-proposal-20261030.md')))
    reg['input_pins'][str(out/'predictions.json')] = c.sha(out/'predictions.json')
    registration=out/f'registration-r{args.revision}.json'
    c.save(registration,reg)
    (out/'empty-pycache').mkdir(); (out/'outputs').mkdir()
    for job in reg['jobs']:
        (out/'outputs'/job['id']).mkdir()
    c.verify_pins(reg)
    print(c.canonical(dict(packet=str(out),registration_sha256=c.sha(registration),
        frames=4*reg['frame_target'],training_games=0,launch_claimed=False,lease_mutated=False)).decode())


if __name__ == '__main__':
    main()
