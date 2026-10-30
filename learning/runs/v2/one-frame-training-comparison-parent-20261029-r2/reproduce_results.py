"""Recompute published survival summaries and bootstrap from compact saved values.

Standard library only. Does not import training code or run any native games.
The compact values are derived after strict acceptance; original raw-file hashes
are retained in survival-vectors.json and the independently reviewed summary.
"""
import hashlib
import json
from pathlib import Path
import random

HERE = Path(__file__).resolve().parent


def percentile(values, probability):
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def main():
    data = json.loads((HERE / 'survival-vectors.json').read_bytes())
    summary_path = HERE / 'results-summary.json'
    assert hashlib.sha256(summary_path.read_bytes()).hexdigest() == data['summary_sha256']
    summary = json.loads(summary_path.read_bytes())
    assert len(data['seeds']) == len(set(data['seeds'])) == 1024
    vectors = {}
    for name, group in data['groups'].items():
        source = next(path for path in summary['input_pins'] if path.endswith('/' + name + '.json'))
        assert group['source_sha256'] == summary['input_pins'][source]
        values = group['alive_frames']
        assert len(values) == 1024 and all(type(v) is int and v >= 0 for v in values)
        ordered = sorted(values)
        stats = dict(Worst=ordered[0], Q1=sum(ordered[:256]) / 256,
                     Mean=sum(ordered) / 1024, Q4=sum(ordered[-256:]) / 256,
                     Best=ordered[-1], episodes=1024)
        assert stats == summary['groups'][name]['survival_frames'], name
        for threshold, milestone in summary['groups'][name]['milestones'].items():
            count = sum(value >= int(threshold) for value in values)
            assert milestone == dict(count=count, episodes=1024, fraction=count / 1024)
        vectors[name] = values
    pairs = {
        'primary_repeat1_final_minus_repeat4_final_repeat1':
            ('repeat1_final_repeat1_sampled', 'repeat4_final_repeat1_sampled'),
        'repeat1_final_minus_starting420_repeat1':
            ('repeat1_final_repeat1_sampled', 'starting420_repeat1_sampled'),
        'repeat1_final_minus_starting420_repeat4':
            ('repeat1_final_repeat4_sampled', 'starting420_repeat4_sampled'),
        'repeat4_final_minus_starting420_repeat1':
            ('repeat4_final_repeat1_sampled', 'starting420_repeat1_sampled'),
        'repeat4_final_minus_starting420_repeat4':
            ('repeat4_final_repeat4_sampled', 'starting420_repeat4_sampled'),
    }
    bootstrap = summary['bootstrap']
    assert bootstrap['paired_indices_shared_across_models_and_repeats'] is True
    rng = random.Random(bootstrap['seed'])
    draws = {name: [] for name in pairs}
    for _ in range(bootstrap['draws']):
        indices = [rng.randrange(1024) for _ in range(1024)]
        q1 = {name: sum(sorted(values[i] for i in indices)[:256]) / 256
              for name, values in vectors.items()}
        for name, (left, right) in pairs.items():
            draws[name].append(q1[left] - q1[right])
    for name, (left, right) in pairs.items():
        recorded = summary['contrasts'][name]
        observed = (summary['groups'][left]['survival_frames']['Q1']
                    - summary['groups'][right]['survival_frames']['Q1'])
        assert observed == recorded['observed'], name
        for field, probability in [('low', .025), ('median', .5), ('high', .975)]:
            assert percentile(draws[name], probability) == recorded[field], (name, field)
    primary = summary['contrasts']['primary_repeat1_final_minus_repeat4_final_repeat1']
    assert summary['primary_success'] == (primary['observed'] > 0 and primary['low'] > 0)
    print(json.dumps(dict(status='all_summaries_milestones_and_bootstrap_contrasts_match',
                          groups=len(vectors), contrasts=len(pairs), draws=bootstrap['draws'])))


if __name__ == '__main__':
    main()
