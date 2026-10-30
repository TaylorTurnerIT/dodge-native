"""Independently sort accepted D9 rows and preserve a compact result summary."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PACKAGE = ROOT / 'learning/runs/v2/one-frame-training-comparison-luna-20261029-r2'


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    audit = read(PACKAGE / 'parent-terminal-audit.json')
    release = read(PACKAGE / 'lease-release.json')
    assert audit['status'] == 'parent_terminal_audit_accepted' and audit['phase'] == 'formal'
    assert release['parent_terminal_audit_sha256'] == sha(PACKAGE / 'parent-terminal-audit.json')
    assert release['lease_value_after_release'] is None
    report = read(PACKAGE / 'worker-output/comparison.json')
    worker = read(PACKAGE / 'worker-output/worker-result.json')
    seeds = read(HERE / 'protocol.json')['evaluation']['seeds']
    assert len(seeds) == len(set(seeds)) == 1024
    groups = {}
    input_pins = {}
    for name, recorded in report['groups'].items():
        path = PACKAGE / 'worker-output' / (name + '.json')
        assert sha(path) == audit['artifact_manifest'][path.name]
        document = read(path)
        rows = document['rows']
        assert len(rows) == 1024 and len({row['seed'] for row in rows}) == 1024
        assert {row['seed'] for row in rows} == set(seeds)
        ordered = sorted(row['alive_frames'] for row in rows)
        assert all(type(value) is int and value >= 0 for value in ordered)
        stats = dict(Worst=ordered[0], Q1=sum(ordered[:256]) / 256,
                     Mean=sum(ordered) / 1024, Q4=sum(ordered[-256:]) / 256,
                     Best=ordered[-1], episodes=1024)
        assert stats == recorded, (name, stats, recorded)
        milestones = {str(frame): {'count': sum(v >= frame for v in ordered), 'episodes': 1024,
            'fraction': sum(v >= frame for v in ordered) / 1024}
            for frame in range(1000, 18001, 1000)}
        diagnostics = {
            'mean_score': sum(row['score'] for row in rows) / 1024,
            'mean_logged_undiscounted_objective_return': sum(row['objective_return'] for row in rows) / 1024,
            'terminated_games': sum(row['terminated'] for row in rows),
            'truncated_games': sum(row['truncated'] for row in rows),
            'scope': 'Descriptive diagnostics, not additional preregistered efficacy tests.'}
        groups[name] = dict(model=document['model'], inference_action_repeat=document['action_repeat'],
                           survival_frames=stats, milestones=milestones, diagnostics=diagnostics)
        input_pins[str(path.resolve())] = sha(path)
    for filename in ['comparison.json', 'worker-result.json']:
        path = PACKAGE / 'worker-output' / filename
        assert sha(path) == audit['artifact_manifest'][filename]
        input_pins[str(path.resolve())] = sha(path)
    primary = report['contrasts']['primary_repeat1_final_minus_repeat4_final_repeat1']
    observed = (groups['repeat1_final_repeat1_sampled']['survival_frames']['Q1']
                - groups['repeat4_final_repeat1_sampled']['survival_frames']['Q1'])
    assert primary['observed'] == observed
    assert report['primary_success'] == (observed > 0 and primary['low'] > 0)
    one = groups['repeat1_final_repeat1_sampled']['survival_frames']
    four = groups['repeat4_final_repeat1_sampled']['survival_frames']
    starting = groups['starting420_repeat1_sampled']['survival_frames']
    summary = {
        'schema': 'dodge013_independently_verified_formal_results_v1',
        'run_id': PACKAGE.name, 'status': 'strict_parent_audit_accepted_raw_summaries_verified',
        'parent_terminal_audit_sha256': sha(PACKAGE / 'parent-terminal-audit.json'),
        'lease_release_sha256': sha(PACKAGE / 'lease-release.json'),
        'registration_sha256': audit['registration_sha256'],
        'source_manifest_sha256': worker['source_manifest_sha256'],
        'runtime_manifest_sha256': worker['runtime_manifest_sha256'],
        'evaluation_games': 6144, 'evaluation_seed_count': 1024,
        'q1_definition': 'Average of the lowest256 alive_frames among1024 games, sorted separately for each model/controller.',
        'groups': groups, 'contrasts': report['contrasts'], 'bootstrap': report['bootstrap'],
        'primary_success': report['primary_success'],
        'relative_changes_common_one_frame_inference': {
            'one_frame_training_vs_four_frame_training_Q1_percent': 100 * (one['Q1'] / four['Q1'] - 1),
            'one_frame_training_vs_starting420_Q1_percent': 100 * (one['Q1'] / starting['Q1'] - 1),
            'four_frame_training_vs_starting420_Q1_percent': 100 * (four['Q1'] / starting['Q1'] - 1),
            'one_frame_training_vs_starting420_Mean_percent': 100 * (one['Mean'] / starting['Mean'] - 1),
        },
        'training': [{k: arm[k] for k in ('id', 'action_repeat', 'updates', 'gameplay_frames',
            'startup_frames', 'optimizer_steps', 'policy_decisions', 'update_metrics', 'checkpoint')}
            for arm in worker['arms']],
        'timing_seconds': {'worker_total': worker['elapsed_seconds'],
            'evaluation': worker['evaluation_seconds'],
            'supervised_total': read(PACKAGE / 'execution-exit.json')['elapsed_seconds']},
        'resources': audit['worker_resources'],
        'frame_difference': worker['paired_actual_gameplay_frames_difference'],
        'scope': 'One paired training trajectory, equal game exposure rather than equal decisions or compute. Seed-cluster intervals condition on these trained policies, not training replicas.',
        'hypotheses_not_established': [
            'Finer control may require different optimization, credit assignment or value-learning settings.',
            'Additional ordinary training can degrade weak-game survival under this recipe.',
            'The observed regression does not establish that one-frame training is inherently worse.'],
        'interpretation': 'One-frame training substantially worsened Q1 under the common one-frame controller. Four-frame training did not show a clear Q1 improvement over starting420. The earlier inference-only benefit of one-frame control remains distinct from learning under that control.',
        'official_parent_unchanged': 324, 'promotion': False, 'new_training_authorized_by_result': False,
        'input_pins': input_pins,
    }
    with (HERE / 'results-summary.json').open('x') as stream:
        json.dump(summary, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'primary_success': summary['primary_success'], 'primary': primary,
        'common_one_frame_Q1': {'starting420': starting['Q1'], 'four_frame_trained': four['Q1'],
                               'one_frame_trained': one['Q1']},
        'relative_changes': summary['relative_changes_common_one_frame_inference']}, indent=2))


if __name__ == '__main__':
    main()
