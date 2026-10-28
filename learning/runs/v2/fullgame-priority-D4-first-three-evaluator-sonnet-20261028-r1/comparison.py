"""Terminal60 summaries and the replica-1 priority-minus-uniform comparison; stdlib only."""
from __future__ import annotations

import binding as b


def summarize(rows, seeds):
    analysis = b.analysis()
    rows = analysis.validate_full_rows(rows, seeds)
    ordered = sorted(row['alive_frames'] for row in rows)
    deaths = {cause: sum(row['terminated'] and row['death_cause'] == cause for row in rows)
              for cause in analysis.DEATH_CAUSES}
    caps = sum(row['truncated'] for row in rows)
    analysis._require(sum(deaths.values())+caps == 1024, 'death/cap conservation differs')
    return dict(complete=True, episodes=1024, missing_rows=0, invalid_rows=0,
        performance=dict(Worst=ordered[0], Q1=sum(ordered[:256])/256, Mean=sum(ordered)/1024,
                         Q4=sum(ordered[768:])/256, Best=ordered[-1]),
        milestones={str(h): dict(numerator=sum(row['alive_frames'] >= h for row in rows), denominator=1024)
                    for h in b.MILESTONES},
        death_causes=deaths, caps=caps)


def compare(policy_rows, seeds):
    b.need(type(policy_rows) is dict and set(policy_rows) == set(b.POLICIES),
           'exactly the three fixed policies required')
    summaries = {name: summarize(policy_rows[name], seeds) for name in b.POLICIES}
    left, right = b.PRIMARY_PAIR
    a, c = policy_rows[left], policy_rows[right]; sl, sr = summaries[left], summaries[right]
    pair = dict(replica=1, label='priority_minus_uniform', role='primary_matched_pair', minuend=left, subtrahend=right,
        metric_differences={k: sl['performance'][k]-sr['performance'][k] for k in sl['performance']},
        milestone_numerator_differences={h: sl['milestones'][h]['numerator']-sr['milestones'][h]['numerator']
                                         for h in sl['milestones']},
        death_cause_count_differences={k: sl['death_causes'][k]-sr['death_causes'][k] for k in sl['death_causes']},
        cap_count_difference=sl['caps']-sr['caps'],
        per_seed=[dict(seed=seed, alive_frames=a[i]['alive_frames']-c[i]['alive_frames'],
            milestones={str(h): int(a[i]['alive_frames'] >= h)-int(c[i]['alive_frames'] >= h)
                        for h in b.MILESTONES}) for i, seed in enumerate(seeds)])
    return dict(schema='fullgame_priority_d4_first3_terminal60_paired_comparison_v1', complete=True,
        planned_episodes=b.EPISODES, cohort='D4', policies=summaries, primary_pair=pair,
        descriptive_only={b.DESCRIPTIVE_ONLY: 'summary only; its opening_priority partner is not among these three'},
        incomplete_pair_2=True, pool_of_three_training_replicates=False, parent_evaluations=0,
        automatic_selection=False, promoted=False,
        interpretation='One matched training pair (replica 1) over 1024 shared evaluation seeds on a development '
            'cohort; replica-2 uniform is descriptive only. No pair-2 or three-replicate pool is fabricated; no '
            'method superiority, selection, promotion or D5 confirmation claim.')
