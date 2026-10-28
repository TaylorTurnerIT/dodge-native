"""Terminal60 summaries and priority-minus-uniform comparison; stdlib only."""
from __future__ import annotations
import statistics

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
           'incomplete pair or shared parent; seven endpoints required')
    summaries = {name: summarize(policy_rows[name], seeds) for name in b.POLICIES}
    pairs = []
    for replica in (1, 2, 3):
        uniform = f'replica-{replica}-uniform'; priority = f'replica-{replica}-opening_priority'
        comparisons = {}
        for label, left, right in [('priority_minus_uniform', priority, uniform),
                                   ('uniform_minus_parent', uniform, b.PARENT_ID),
                                   ('priority_minus_parent', priority, b.PARENT_ID)]:
            a, c = policy_rows[left], policy_rows[right]; sl, sr = summaries[left], summaries[right]
            comparisons[label] = dict(
                role='primary_matched_pair' if label == 'priority_minus_uniform' else 'descriptive_parent_comparison',
                metric_differences={k: sl['performance'][k]-sr['performance'][k] for k in sl['performance']},
                milestone_numerator_differences={h: sl['milestones'][h]['numerator']-sr['milestones'][h]['numerator']
                                                 for h in sl['milestones']},
                death_cause_count_differences={k: sl['death_causes'][k]-sr['death_causes'][k] for k in sl['death_causes']},
                cap_count_difference=sl['caps']-sr['caps'],
                per_seed=[dict(seed=seed, alive_frames=a[i]['alive_frames']-c[i]['alive_frames'],
                    milestones={str(h): int(a[i]['alive_frames'] >= h)-int(c[i]['alive_frames'] >= h)
                                for h in b.MILESTONES}) for i, seed in enumerate(seeds)])
        pairs.append(dict(replica=replica, comparisons=comparisons))
    across = {}
    for label in pairs[0]['comparisons']:
        across[label] = {}
        first = pairs[0]['comparisons'][label]
        for metric in list(first['metric_differences'])+['milestone_'+h for h in first['milestone_numerator_differences']]:
            values = [pair['comparisons'][label]['milestone_numerator_differences'][metric.removeprefix('milestone_')]
                      if metric.startswith('milestone_') else pair['comparisons'][label]['metric_differences'][metric]
                      for pair in pairs]
            across[label][metric] = dict(values=values, mean=statistics.mean(values), min=min(values),
                                         max=max(values), sample_stddev=statistics.stdev(values))
    return dict(schema='fullgame_priority_d4_terminal60_paired_comparison_v1', complete=True,
        planned_episodes=b.EPISODES, cohort='D4', policies=summaries, paired_replicas=pairs,
        across_three_descriptive=across, parent_evaluations=1, parent_independent_samples=1,
        automatic_selection=False, promoted=False,
        interpretation='Descriptive three-pair pilot on a development cohort; shared parent baseline; no method '
            'superiority, selection, promotion or D5 confirmation claim.')
