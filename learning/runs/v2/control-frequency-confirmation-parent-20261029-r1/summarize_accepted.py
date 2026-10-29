"""Independently sort accepted raw survival values before publishing compact results."""
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent / 'control-frequency-confirmation-luna-20261029-r1'
sys.path.insert(0, str(PACKAGE))
import binding as b


def main():
    acceptance = b.read(HERE / 'parent-terminal-audit.json')
    b.need(acceptance['status'] == 'accepted_complete_2048_episode_confirmation',
           'Parent acceptance is required before result inspection.')
    path = Path(acceptance['comparison_path'])
    b.need(b.sha(path) == acceptance['comparison_sha256'], 'Accepted comparison changed.')
    comparison = b.read(path)
    reg = b.read(PACKAGE / 'registration-final.json')
    conditions = {}
    for name in ('sampled_r4', 'argmax_r4', 'sampled_r1', 'argmax_r1'):
        repetitions = 3 if name.startswith('sampled') else 1
        rows = []
        per_repetition = []
        for rep in range(repetitions):
            receipt = b.read(path.parent / f'{name}-rep{rep}.json')
            b.need([r['seed'] for r in receipt['rows']] == reg['seeds'], 'Raw seed order differs.')
            rows.extend(receipt['rows'])
            per_repetition.append(receipt['summary']['performance'])
        values = sorted(r['alive_frames'] for r in rows)
        expected_count = 768 if repetitions == 3 else 256
        b.need(len(values) == expected_count, 'Raw sample count differs.')
        quarter = len(values) // 4
        measured = dict(Worst=values[0], Q1=sum(values[:quarter])/quarter,
                        Mean=sum(values)/len(values), Q4=sum(values[-quarter:])/quarter, Best=values[-1])
        published = comparison['conditions'][name]
        if repetitions == 3:
            published = published['pooled']
        b.need(measured == published['performance'], 'Independent survival sorting differs.')
        milestones = {str(h): dict(numerator=sum(v >= h for v in values), denominator=len(values))
                      for h in range(1000, 18001, 1000)}
        b.need(milestones == published['milestones'], 'Independent milestone counts differ.')
        conditions[name] = dict(episodes=len(values), bottom_quarter_games=quarter,
                               performance=measured, milestones=milestones,
                               per_repetition=per_repetition)
    result = dict(schema='control_frequency_confirmation_independent_summary_v1',
                  acceptance_sha256=b.sha(HERE / 'parent-terminal-audit.json'),
                  comparison_sha256=b.sha(path), checkpoint_update=420,
                  conditions=conditions, contrasts=comparison['contrasts'],
                  bootstrap=comparison['bootstrap'],
                  wall_seconds=acceptance['outer_elapsed_seconds'],
                  condition_wall_seconds=comparison['condition_wall_seconds'],
                  caveats=['One frozen checkpoint and 256 shared game seeds.',
                           'Controller repetitions are not independent training replicas.',
                           'Strict existing-empty bytecode-cache and original non-cache terminal checks passed.',
                           'No controller adoption or official checkpoint promotion.'])
    primary = comparison['contrasts']['repeat1_minus_repeat4_sampled']
    result['primary_replication'] = dict(
        contrast='sampled_r1_Q1_minus_sampled_r4_Q1',
        difference_frames=primary['metric_differences']['Q1'],
        bootstrap_95=primary['q1_cluster_bootstrap_95'],
        success=primary['metric_differences']['Q1'] > 0 and primary['q1_cluster_bootstrap_95']['low'] > 0,
        criterion='Positive observed difference and strictly positive prespecified 95% seed-cluster bootstrap lower bound.',
        selected_before_D8=True)
    b.save(HERE / 'results-summary.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
