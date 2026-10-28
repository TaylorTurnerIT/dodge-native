"""Rank audited six-model results under the user's explicit lower-quarter directive."""
from pathlib import Path
import html
import json
import sys

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent / 'fullgame-priority-D4-last-three-evaluator-sonnet-20261028-r1'
sys.path.insert(0, str(PACKAGE))
import binding as b
from prepare_launch import common_contract


def main():
    common = common_contract()
    original = b.read(HERE / 'common-training-contract.json')
    b.need(common == original, 'training contract changed before actual merge')
    report_path = PACKAGE / 'six-model-merge.json'
    report = b.read(report_path)
    b.need(report['status'] == 'merged_offline_descriptive_development_d4', 'accepted merge required')
    directive_path = b.V2 / 'fullgame-priority-three-run-execution-parent-20261028-r1/lower-tail-selection-directive.json'
    directive = b.read(directive_path)
    ranked = sorted(report['policies'], key=lambda name: (
        -report['policies'][name]['summary']['performance']['Q1'],
        -report['policies'][name]['summary']['performance']['Mean'], name))
    first, second = [report['policies'][name]['summary']['performance'] for name in ranked[:2]]
    b.need((first['Q1'], first['Mean']) != (second['Q1'], second['Mean']), 'exact tie requires explicit decision')
    selected = ranked[0]
    registrations = [b.read(b.FIRST_PART / 'registration-final.json'), b.read(PACKAGE / 'registration-final.json')]
    policy = next(policy for reg in registrations for policy in reg['policies'] if policy['id'] == selected)
    rows = [dict(rank=i+1, model=name, **report['policies'][name]['summary']['performance'],
                 milestones=report['policies'][name]['summary']['milestones']) for i, name in enumerate(ranked)]
    selection = dict(schema='dodge_six_model_exploratory_lower_quarter_selection_v1',
        status='selected_for_continuation_preparation_only', directive_path=str(directive_path),
        directive_sha256=b.sha(directive_path), merge_path=str(report_path), merge_sha256=b.sha(report_path),
        metric='Q1: mean alive frames in the worst 256 of 1024 complete games',
        ranking=rows, selected_model=selected, selected_policy=policy,
        exploratory_after_first_three_results=True, preregistered_primary_inference=False,
        method_superiority_claim=False, parent324_evaluated_on_d4=False,
        official_retained_parent=324, promoted=False, training_launched=False,
        d5_b_e_opened=False, training_contract_reverified=True,
        uncertainty=report['uncertainty'])
    b.save(HERE / 'lower-quarter-selection.json', selection)
    producer_reg = b.read(policy['producer']['registration_path'])
    proposal = dict(schema='dodge_lower_quarter_winner_continuation_proposal_v1',
        status='concrete_recipe_pending_restore_integration_registration_and_review', launch_authority=False,
        selected_model=selected, parent_checkpoint_path=policy['checkpoint_path'],
        parent_checkpoint_sha256=policy['checkpoint_sha256'], parent_sidecar_path=policy['producer']['sidecar_path'],
        parent_audit_path=policy['producer']['audit_path'], parent_audit_sha256=b.sha(policy['producer']['audit_path']),
        selection_sha256=b.sha(HERE / 'lower-quarter-selection.json'),
        proposed_budget=dict(updates=60, decisions_per_update=64*256, decisions_total=64*256*60,
                             maximum_action_repeat=4, cumulative_first=433, cumulative_last=492,
                             phase_first=385, phase_last=444),
        recipe=dict(architecture=producer_reg['shared_config']['model'], ppo=producer_reg['ppo'],
                    reward=producer_reg['shared_config']['reward'], environment=producer_reg['shared_config']['environment'],
                    training_pool_path=producer_reg['training_pool_path'],
                    training_pool_file_sha256=producer_reg['training_pool_file_sha256'],
                    sampling_arm=producer_reg['arm'], sampling_change=False, restore_optimizer=True,
                    reset_optimizer=False, learning_rate=3e-5),
        rationale='Continue the model ranked highest on the user-selected worst-quarter mean; keep recipe fixed to isolate added training.',
        evaluation=dict(primary='worst-quarter mean survival', also=['Worst', 'Mean', 'Q4', 'Best', 'milestone success'],
                        normal_full_runs=True, sampled_actions=True,
                        development_cohort='Reserve a new excluded development cohort before launch; D4 has informed selection.',
                        compare_against='Selected saved model evaluated on the same new cohort',
                        d5_b_e='Remain closed; no automatic qualification or promotion'),
        remaining_requirements=[
            'Successor-only adapter must validate and restore the selected terminal60 model and Adam state; existing parent324-only loader stays frozen.',
            'Register continuation RNG and exact pool slot-stream suffix; include all evaluation seed exclusions.',
            'Inspect actual checkpoint metadata and reproduce model/Adam fingerprints before any launch.',
            'Freeze source/runtime, calibration, native caffeinate supervision, exact-once marker, resource lease, independent review and parent acceptance.',
            'Keep outputs and weights isolated; publish source and compact evidence only.'],
        official_retained_parent=324, promoted=False, training_launched=False)
    b.save(HERE / 'continuation-proposal.json', proposal)
    table = ''.join('<tr'+(' class="winner"' if i == 0 else '')+'><td>'+html.escape(row['model'].replace('replica-', '#').replace('-opening_priority', ' Priority').replace('-uniform', ' Uniform'))+'</td>'+''.join(
        '<td>'+format(row[key], ',.1f')+'</td>' for key in ('Worst', 'Q1', 'Mean', 'Q4', 'Best'))+'</tr>' for i, row in enumerate(rows))
    pairs = ''.join('<tr><td>'+key.replace('_',' ').title()+'</td><td>'+format(value['metric_differences']['Q1'], '+.1f')+'</td><td>'+format(value['metric_differences']['Mean'], '+.1f')+'</td></tr>' for key,value in report['pairs'].items())
    page = '''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{font:14px var(--font-sans,system-ui);color:var(--foreground);margin:0}h2{font-size:19px;margin:0 0 8px}p{line-height:1.5;margin:8px 0 16px;color:var(--muted-foreground)}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;margin:12px 0 20px}th,td{text-align:right;padding:10px 5px;border-bottom:1px solid var(--border,#8885)}th:first-child,td:first-child{text-align:left}th{font-size:12px;color:var(--muted-foreground)}.winner{background:var(--accent-surface,#7772);font-weight:650}small{display:block;line-height:1.5;color:var(--muted-foreground)}@media(max-width:480px){body{font-size:12px}th,td{padding:9px 3px}th{font-size:10px}}
</style></head><body><h2>Six saved models, ranked by weakest-quarter survival</h2>
<p>1,024 identical full-game seeds per model. All scores in frames. Q1 averages each model’s worst 256 games.</p>
<table><thead><tr><th>Model</th><th>Worst</th><th>Q1 ↑</th><th>Mean</th><th>Q4</th><th>Best</th></tr></thead><tbody>'''+table+'''</tbody></table>
<h2>Extra hard-opening practice versus uniform sampling</h2><p>Matched training pairs; positive means Priority scored higher.</p>
<table><thead><tr><th>Pair</th><th>Q1 difference</th><th>Mean difference</th></tr></thead><tbody>'''+pairs+'''</tbody></table>
<small>Three training pairs, six fixed models. Exploratory development ranking; no method-superiority or improvement-versus-parent claim. Q4 averages the best quarter. Official parent remains checkpoint 324.</small></body></html>'''
    with (HERE / 'six-model-results.html').open('x') as stream:
        stream.write(page)
    print(json.dumps(dict(selected_model=selected, ranking=rows, pair_average=report['pair_average'])))


if __name__ == '__main__':
    main()
