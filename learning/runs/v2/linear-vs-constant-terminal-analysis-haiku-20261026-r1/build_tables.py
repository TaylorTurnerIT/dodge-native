import json, csv, statistics as st, math, sys
from collections import Counter
R = '/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/'
OUT = sys.argv[1]
FIX = 'D2-retained324-continuation-20261026-r1'
LIN = 'D2-retained324-linear-lr-20261026-r1'
PH = [324, 336, 348, 360, 372, 384]
dev = {a: {p: json.load(open(f'{R}{r}/development-{p:06d}.json')) for p in PH} for a, r in (('fixed', FIX), ('linear', LIN))}
# 1. phase table
with open(f'{OUT}/phase-metrics.csv', 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['arm', 'phase_update', 'local_update', 'checkpoint_sha256', 'mean_alive_frames', 'q1_alive', 'q4_alive', 'mean_score', 'q1_score', 'q4_score', 'deaths', 'competence_passed_recorded', 'n_alive_ge_3060', 'death_normal_enemy', 'death_kamikaze_enemy', 'death_kamikaze_explosion', 'death_moving_pattern_rect', 'death_static_pattern_rect', 'promoted', 'training_eligible', 'raw_frames'])
    for a in ('fixed', 'linear'):
        for p in PH:
            d = dev[a][p]; e = d['evaluation']; pf = d['performance']
            dc = Counter(r['death_cause'] for r in e['rows'])
            w.writerow([a, p, p - 324, d['checkpoint_sha256'], round(e['mean_alive_frames'], 5), pf['alive_frames']['Q1'], pf['alive_frames']['Q4'], round(e['mean_score'], 5), pf['score']['Q1'], pf['score']['Q4'], e['deaths'], d['competence_passed'], sum(r['alive_frames'] >= 3060 for r in e['rows']), dc['normal_enemy'], dc['kamikaze_enemy'], dc['kamikaze_explosion'], dc['moving_pattern_rect'], dc['static_pattern_rect'], d['promoted'], d['training_eligible'], e['raw_frames']])
# 2. per-seed paired
with open(f'{OUT}/paired-per-seed.csv', 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['phase_update', 'episode_index', 'seed', 'fixed_alive', 'linear_alive', 'diff_linear_minus_fixed', 'fixed_score', 'linear_score', 'fixed_death_cause', 'linear_death_cause'])
    for p in PH:
        for f, l in zip(dev['fixed'][p]['evaluation']['rows'], dev['linear'][p]['evaluation']['rows']):
            assert f['seed'] == l['seed'] and f['episode_index'] == l['episode_index']
            w.writerow([p, f['episode_index'], f['seed'], f['alive_frames'], l['alive_frames'], l['alive_frames'] - f['alive_frames'], f['score'], l['score'], f['death_cause'], l['death_cause']])
# 3. per-update training
F = [json.loads(x) for x in open(f'{R}{FIX}/training-metrics.jsonl')]
L = [json.loads(x) for x in open(f'{R}{LIN}/training-metrics.jsonl')]
cols = ['local_update', 'phase_update', 'lr_fixed', 'lr_linear', 'optimizer_steps_per_update', 'epochs_completed', 'approx_kl_fixed', 'approx_kl_linear', 'clip_fraction_fixed', 'clip_fraction_linear', 'entropy_fixed', 'entropy_linear', 'ev_pre_fixed', 'ev_pre_linear', 'ev_post_fixed', 'ev_post_linear', 'target_variance_fixed', 'target_variance_linear', 'residual_mse_fixed', 'residual_mse_linear', 'value_loss_fixed', 'value_loss_linear', 'policy_loss_fixed', 'policy_loss_linear', 'actor_grad_norm_fixed', 'actor_grad_norm_linear', 'critic_grad_norm_fixed', 'critic_grad_norm_linear', 'grad_alignment_cos_fixed', 'grad_alignment_cos_linear', 'early_stop_kl_fixed', 'early_stop_kl_linear', 'finite_fixed', 'finite_linear']
with open(f'{OUT}/training-per-update.csv', 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(cols)
    for f, l in zip(F, L):
        mf, ml = f['metrics'], l['metrics']
        cd = lambda m, ph, k: m['critic_diagnostics'][ph][k]
        w.writerow([l['local_update'], l['phase_update'], f.get('optimizer_group_lrs', ['const?'])[0] if 'optimizer_group_lrs' in f else 'not_recorded', l['optimizer_group_lrs'][0], ml['optimizer_steps'], ml['epochs_completed'],
                    mf['approx_kl'], ml['approx_kl'], mf['clip_fraction'], ml['clip_fraction'], mf['entropy'], ml['entropy'],
                    cd(mf, 'pre_update', 'explained_variance'), cd(ml, 'pre_update', 'explained_variance'), cd(mf, 'post_update', 'explained_variance'), cd(ml, 'post_update', 'explained_variance'),
                    cd(mf, 'pre_update', 'target_variance'), cd(ml, 'pre_update', 'target_variance'), cd(mf, 'post_update', 'residual_mse'), cd(ml, 'post_update', 'residual_mse'),
                    mf['value_loss'], ml['value_loss'], mf['policy_loss'], ml['policy_loss'], mf['actor_grad_norm'], ml['actor_grad_norm'], mf['critic_grad_norm'], ml['critic_grad_norm'],
                    mf['gradient_alignment_diagnostics']['cosine'], ml['gradient_alignment_diagnostics']['cosine'], mf['early_stop_kl'], ml['early_stop_kl'], mf['finite'], ml['finite']])
print('ok')
