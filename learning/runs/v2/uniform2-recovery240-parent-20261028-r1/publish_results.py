"""Publish already-audited survival results and update the local research notebook. No simulation or training."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PACKAGE = HERE.parent / 'uniform2-recovery240-luna-20261028-r1'
sys.path.insert(0, str(ROOT / 'learning/scripts'))
from research_log import Store, publish_json


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    result_path = HERE / 'recovered-study-result.json'
    result = json.loads(result_path.read_text())
    assert result['status'] == 'accepted_saved_prefix_plus_independently_audited_recovery_development_comparison'
    assert not result['promoted']
    policies = []
    for source in result['sources']:
        path = Path(source['receipt_path'])
        assert sha(path) == source['receipt_sha256']
        receipt = json.loads(path.read_text())
        policies.append(dict(update=source['global_update'], **receipt['summary']))
    by_update = {row['update']: row for row in policies}
    chosen = result['selected']['global_update']
    baseline, selected = by_update[0], by_update[chosen]
    differences = {
        name: dict(frames=value - baseline['performance'][name],
                   percent=100 * (value / baseline['performance'][name] - 1))
        for name, value in selected['performance'].items()
    }
    summary = dict(schema='uniform2_recovered600_survival_summary_v1',
        status='audited_development_comparison', result_sha256=sha(result_path),
        selected_update=chosen, selection_rule=result['rule'], policies=policies,
        selected_minus_start=differences, episodes_per_policy=1024,
        Q1_definition='Mean survival in the worst 256 of 1024 games.',
        Q4_definition='Mean survival in the best 256 of 1024 games.',
        unit='game frames survived', action_repeat=4, action_mode='sampled_categorical',
        cohort='D6, shared repeated development evaluation; not confirmation',
        uncertainty='One recovered training trajectory; checkpoint chosen among eleven on these same seeds.',
        original_attempt_journaled_updates=400, lost_completed_updates=40,
        recovery_updates=240, effective_continuation_updates=600,
        original_update401_optimizer_work='unknown and not restored',
        repeated_baseline360_summary_equal=result['baseline360_repeat_summary_equal'],
        official_parent=324, promoted=False)
    summary_path = HERE / 'results-summary.json'
    publish_json(summary_path, summary)

    headers = '<tr><th>Model update</th><th>Worst</th><th>Worst 25% avg<br>(Q1)</th><th>Mean</th><th>Best 25% avg<br>(Q4)</th><th>Best</th></tr>'
    def performance_row(row):
        update, values = row['update'], row['performance']
        label = 'Starting model · 0' if update == 0 else f'{update}'
        if update == chosen:
            label += ' · selected'
        cells = ''.join(f'<td>{values[name]:,.1f}</td>' if name in {'Q1', 'Mean', 'Q4'} else f'<td>{values[name]:,}</td>'
                        for name in ('Worst', 'Q1', 'Mean', 'Q4', 'Best'))
        return f'<tr class="{"chosen" if update == chosen else ""}"><th>{label}</th>{cells}</tr>'
    main_rows = ''.join(performance_row(by_update[u]) for u in (0, chosen, 600))
    all_rows = ''.join(performance_row(row) for row in policies)
    milestone_rows = ''
    for milestone in ('1000', '2000', '4000', '8000', '12000', '18000'):
        cells = ''
        for update in (0, chosen, 600):
            count = by_update[update]['milestones'][milestone]
            cells += f'<td>{100 * count["numerator"] / count["denominator"]:.2f}% <small>({count["numerator"]}/1024)</small></td>'
        milestone_rows += f'<tr><th>{int(milestone):,} frames</th>{cells}</tr>'
    html = f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{{margin:0;color:var(--foreground,#222);font:15px/1.5 var(--font-sans,system-ui)}}
h2{{font-size:21px;margin:0 0 8px}}p{{margin:8px 0 16px}}.muted,small{{color:var(--muted-foreground,#687078)}}
table{{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums;margin:12px 0 20px}}
th,td{{padding:9px 7px;text-align:right;border-bottom:1px solid var(--border,#ddd);white-space:nowrap}}
th:first-child{{text-align:left}}thead th{{font-size:12px}}.chosen{{background:var(--accent-surface,#e7f4ec)}}
.scroll{{overflow-x:auto}}details{{margin:12px 0}}summary{{cursor:pointer}}strong{{font-weight:650}}small{{display:block}}</style></head><body>
<h2>600 updates complete. Update {chosen} leads on the weakest games.</h2>
<p>Worst-quarter survival improved <strong>{differences['Q1']['percent']:.1f}%</strong>; mean survival improved
<strong>{differences['Mean']['percent']:.1f}%</strong>. The best-quarter average also rose <strong>{differences['Q4']['percent']:.1f}%</strong>.</p>
<div class="scroll"><table><thead>{headers}</thead><tbody>{main_rows}</tbody></table></div>
<p class="muted">Update 0 is Uniform #2 before this continuation. All survival values are game frames. Each model played 1,024 shared normal-start games, with sampled actions and four frames per decision.</p>
<div class="scroll"><table><thead><tr><th>Survived to</th><th>Starting model</th><th>Update {chosen}</th><th>Update 600</th></tr></thead><tbody>{milestone_rows}</tbody></table></div>
<p>Update 600 has the highest mean. Update {chosen} wins the agreed worst-quarter criterion. Lower-tail performance fluctuated across training.</p>
<details><summary>All eleven evaluated models</summary><div class="scroll"><table><thead>{headers}</thead><tbody>{all_rows}</tbody></table></div></details>
<p class="muted">One recovered training run; these seeds were used repeatedly for development and checkpoint selection. Fresh-seed confirmation is still needed. Official parent remains checkpoint 324.</p>
</body></html>'''
    (HERE / 'results.html').write_text(html)

    store = Store(ROOT / 'learning/research/research.sqlite3')
    try:
        for experiment_id, updates in [('DODGE-001', set(range(0, 601, 60))), ('DODGE-011', {360, 420, 480, 540, 600})]:
            current = store.get(experiment_id)
            assert current['status'] == 'running', 'Do not append duplicate completion; inspect existing record.'
            prefix = experiment_id.lower()
            evidence = [dict(id=prefix + '-survival-summary', kind='result', label='Audited complete-game survival comparison',
                             uri=str(summary_path.relative_to(ROOT)), sha256=sha(summary_path)),
                        dict(id=prefix + '-recovery-audit', kind='audit', label='Accepted recovery terminal audit',
                             uri=str((PACKAGE / 'parent-terminal-audit.json').relative_to(ROOT)), sha256=sha(PACKAGE / 'parent-terminal-audit.json')),
                        dict(id=prefix + '-merged-study', kind='audit', label='Original saved prefix and recovery independently validated',
                             uri=str(result_path.relative_to(ROOT)), sha256=sha(result_path))]
            measurements = []
            for policy in policies:
                if policy['update'] not in updates:
                    continue
                base = dict(evidence_id=prefix + '-survival-summary', model=f'continuation_global_{policy["update"]}', cohort='D6')
                for metric, value in policy['performance'].items():
                    measurements.append(dict(base, metric=metric, value=value, unit='game_frames',
                                             sample_count=256 if metric in {'Q1', 'Q4'} else 1024))
                for milestone, value in policy['milestones'].items():
                    measurements.append(dict(base, metric='survival_at_' + milestone, value=value['numerator'] / value['denominator'],
                                             unit='fraction', sample_count=value['denominator']))
            actual = ('Audited recovery reached 600 updates; update 420 won Q1 selection '
                      '(731.50390625 versus 645.7734375 frames, +13.3%), while Mean improved 21.0% and Q4 improved 17.3%. '
                      'Reaching 1,000 frames rose from 729/1024 to 806/1024; final update 600 raised Mean further but had lower Q1 than 420. '
                      'One selected development trajectory; no confirmation or official promotion.')
            if experiment_id == 'DODGE-011':
                actual = ('Restored checkpoint 360 and completed 240 new updates in 4425.242580542 seconds. '
                          'All four training segments and five evaluations passed audit, the repeated 360 baseline matched the original, '
                          'and the exact lease was released; the original interruption and lost 40 updates remain recorded. '
                          'The combined study selected update 420 by Q1, without official promotion.')
            store.update(experiment_id, dict(status='completed', actual_kind='audited', actual=actual,
                why='The same PPO recipe improved both lower-tail and upper-quarter survival on this development screen, consistent with additional training being useful. '
                    'Q1 fluctuated and peaked before the final checkpoint while Mean kept rising. This does not establish interference, optimal training duration, or population improvement; '
                    'selection among eleven checkpoints on one repeated cohort can overstate the best observed gain.',
                next_step='Discuss update420 as the provisional lower-tail candidate. Prepare the planned frozen-policy action-selection/control-frequency comparison '
                          'and separate fresh-seed validation before broader claims; no new launch or official-parent promotion is granted here.',
                evidence=evidence, measurements=measurements,
                metadata={**current['metadata'], 'selected_development_update': chosen, 'official_parent': 324,
                          'promoted': False, 'result_summary': str(summary_path.relative_to(ROOT))}),
                expected_revision=current['revision'], reason='Record terminal-audited measured results and competing explanations')
        store.check()
        store.export(ROOT / 'learning/research/records.json')
    finally:
        store.close()
    publish_json(HERE / 'monitoring-stop.json', dict(status='deleted_after_terminal_audits',
        recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        scheduled_task_id=json.loads((HERE / 'monitoring-schedule.json').read_text())['scheduledTaskId'],
        result_sha256=sha(result_path)))
    print('audited_results_published_and_both_research_records_completed')


if __name__ == '__main__':
    main()
