"""One-time migration of the frozen 2026-10-28 plan and two completed studies into a portable snapshot.

This reads committed research/evaluation evidence only. It does not import learner code or inspect live scores.
Use research_log.py init to restore the resulting snapshot into the local SQLite notebook.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from research_log import DEFAULT_SNAPSHOT, Store, encoded, now, require

ROOT = Path(__file__).resolve().parents[2]
PLAN_COMMIT = '3d43988'
PLAN_PATH = 'docs/dodge-research-iteration-plan.md'
RUNS = Path('learning/runs/v2')
CURRICULUM = RUNS / 'progressive1000-full-run-evaluator-parent-20261027-r2'
PRIORITY = RUNS / 'fullgame-priority-D4-last-three-evaluator-sonnet-20261028-r1'
FIRST_PRIORITY = RUNS / 'fullgame-priority-D4-first-three-evaluator-sonnet-20261028-r1'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(relative):
    return json.loads((ROOT / relative).read_text())


def evidence(identity, relative, kind, label):
    return dict(id=identity, kind=kind, label=label, uri=relative.as_posix(),
                sha256=digest((ROOT / relative).read_bytes()))


def measurements(policies, evidence_id, cohort):
    result = []
    for model, summary in sorted(policies.items()):
        count = summary['episodes']
        for metric, value in sorted(summary['performance'].items()):
            result.append(dict(model=model, metric=metric, value=value, unit='game_frames', cohort=cohort,
                               evidence_id=evidence_id, sample_count=count // 4 if metric in {'Q1', 'Q4'} else count))
        for milestone in ('1000', '2000', '4000', '8000', '12000', '18000'):
            value = summary['milestones'][milestone]
            result.append(dict(model=model, metric='survival_at_' + milestone,
                               value=value['numerator'] / value['denominator'], unit='fraction', cohort=cohort,
                               evidence_id=evidence_id, sample_count=value['denominator']))
    return result


def migrate(output):
    require(not output.exists(), 'Migration refuses to replace an existing snapshot; update the database instead.')
    commit = subprocess.check_output(['git', 'rev-parse', PLAN_COMMIT], cwd=ROOT, text=True).strip()
    raw_plan = subprocess.check_output(['git', 'show', f'{commit}:{PLAN_PATH}'], cwd=ROOT)
    plan_uri = f'git:{commit}:{PLAN_PATH}'
    parts = re.split(r'^## (\d+)\. (.+)\n', raw_plan.decode(), flags=re.MULTILINE)
    require(len(parts) == 25, 'Expected eight experiments in the frozen plan.')
    curriculum = read(CURRICULUM / 'result-summary.json')
    curriculum_audit = evidence('curriculum-audit', CURRICULUM / 'parent-terminal-audit.json', 'audit', 'Parent terminal audit')
    require(curriculum['audit_sha256'] == curriculum_audit['sha256'], 'Curriculum audit hash differs.')
    require(read(CURRICULUM / 'parent-terminal-audit.json')['status'] == 'accepted_complete_fixed_endpoint_evaluation',
            'Curriculum evidence is not accepted.')
    priority = read(PRIORITY / 'six-model-merge.json')
    audits = [evidence('priority-audit-' + key, path / 'parent-terminal-audit.json', 'audit', key + ' three-model parent audit')
              for key, path in (('first', FIRST_PRIORITY), ('last', PRIORITY))]
    for key, audit in zip(('first', 'last'), audits):
        require(priority['parts'][key]['terminal_audit_sha256'] == audit['sha256'], 'Priority audit hash differs.')
        require(read(Path(audit['uri']))['status'] == 'accepted_complete_fixed_terminal60_d4_evaluation',
                'Priority evidence is not accepted.')
    with tempfile.TemporaryDirectory(prefix='dodge-research-migration-') as directory:
        store = Store(Path(directory) / 'migration.sqlite3', initialize=True)
        try:
            store.create(dict(id='DODGE-009', project='dodge-native', title='Progressive 1,000-frame curriculum pilot',
                status='completed', actual_kind='audited', prediction_timing='retrospective',
                doing='Compare progressive 1,000-frame curriculum against current PPO from parent324 with unchanged architecture and reward. '
                      'Three matched training-randomness pairs; evaluate complete normal-start games on 1,024 shared fresh game seeds per model.',
                expected='Retrospective framing: more opening practice might improve opening reliability and Q1. '
                         'This backfill does not claim a recovered preregistered prediction.',
                actual='Across three training pairs, 1,000-frame success rose from 70.37760416666666% to 72.29817708333334% '
                       '(+1.92057291666667 percentage points). Mean paired Q1 difference: +13.77734375 frames; '
                       'Mean survival: -9.2333984375; Q4: -180.30989583333334. '
                       'Q1 improved in one pair and declined in two. No replica mastered the first curriculum stage. '
                       'The pilot did not show a consistent method advantage; parent324 remained retained.',
                why='Possible explanations include insufficient training, exposure changes, optimization, or interference. '
                    'The three pairs do not identify a cause or rule out curricula.',
                next_step='Compare full-game uniform sampling with a fixed hard-seed priority rule; keep reward unchanged.',
                tags=['curriculum', 'opening', 'Q1', 'completed'],
                metadata={'historical_backfill': True, 'training_pairs': 3, 'no_checkpoint_promotion': True,
                          'interpretation': 'Descriptive development evidence, not proof of method superiority.'},
                evidence=[evidence('curriculum-results', CURRICULUM / 'result-summary.json', 'result', 'Complete-game pilot results'), curriculum_audit],
                measurements=measurements(curriculum['policies'], 'curriculum-results', 'curriculum-pilot-shared-1024')),
                actor='migration', reason='Backfill measured pilot with original evidence and retrospective prediction label')
            store.create(dict(id='DODGE-010', project='dodge-native', parent_id='DODGE-009',
                title='Full-game uniform versus static hard-seed priority', status='completed', actual_kind='audited',
                prediction_timing='retrospective',
                doing='Train six models from parent324, 60 PPO updates each, in three matched training-randomness pairs. '
                      'Randomness matches within each pair and differs between pairs. All use the same 512-seed pool '
                      '(256 historical failures before 1,000 frames and 256 survivors). Uniform samples the full pool; '
                      'priority mixes 50% uniform and 50% hard-only, giving 75% expected hard starts versus 50%. '
                      'Use complete games without a 1,000-frame practice cutoff. Evaluate 1,024 shared D4 seeds per model with sampled actions.',
                expected='Retrospective framing: extra difficult-opening exposure might raise worst-quarter survival. '
                         'This backfill does not claim a recovered preregistered prediction.',
                actual='Priority Q1 was lower in all three matched pairs; average difference -35.438802083333336 game frames. '
                       'Mean survival difference: -65.32161458333333. Uniform #2 had the highest Q1, 663.9921875 frames. '
                       'The user selected Uniform #2 for exploratory continuation by Q1 after the first three evaluations. '
                       'Parent324 was not evaluated on D4, so this comparison establishes no gain over the parent. No checkpoint was promoted.',
                why='Historical hard labels may identify poor learning opportunities, become outdated, or alter training exposure. '
                    'Shared-policy interference is another hypothesis. These results do not distinguish those mechanisms.',
                next_step='Continue Uniform #2 for 600 updates, then test action selection and control frequency before changing the recipe.',
                tags=['seed-priority', 'uniform', 'opening', 'Q1', 'completed'],
                metadata={'historical_backfill': True, 'training_pairs': 3, 'development_cohort': 'D4',
                          'selection': 'Exploratory; Uniform #2 is not the retained parent.', 'no_checkpoint_promotion': True},
                evidence=[evidence('priority-results', PRIORITY / 'six-model-merge.json', 'result', 'Six-model complete-game comparison'), *audits],
                measurements=measurements({k: v['summary'] for k, v in priority['policies'].items()}, 'priority-results', 'D4')),
                actor='migration', reason='Backfill six-model comparison with audited evidence')
            for offset in range(1, len(parts), 3):
                number, title, body = parts[offset:offset + 3]
                # The final section includes prose after the eighth experiment; only its four fields belong here.
                body = body.split('\n## How this becomes real iteration')[0]
                fields = re.split(r'^\*\*(.+?)\*\*\s*', body.strip(), flags=re.MULTILINE)
                require(len(fields) == 9, f'Expected four research fields in experiment {number}.')
                values = dict(zip(fields[1::2], (text.strip() for text in fields[2::2])))
                index = int(number)
                store.create(dict(id=f'DODGE-{index:03}', project='dodge-native', title=title,
                    status='running' if index == 1 else ('conditional' if index >= 6 else 'planned'),
                    doing=values["What we're doing:"], expected=values['What we expect to happen:'],
                    actual=values['What actually happened:'] if index == 1 else None,
                    actual_kind='progress' if index == 1 else 'unobserved', why=values['Why might it have happened?'],
                    prediction_timing='during_run' if index == 1 else 'before_run',
                    parent_id='DODGE-010' if index in (1, 7) else None,
                    tags=['research-plan', 'Q1', ('continuation' if index == 1 else 'diagnostic' if index in (2, 3, 4) else 'intervention')],
                    metadata={'imported_from': plan_uri, 'source_section': index,
                              'unobserved_result_prompt': None if index == 1 else values['What actually happened:'],
                              'why_is_hypothesis': True},
                    evidence=[dict(id=f'plan-{index}', kind='plan', label='Original four-question iteration plan',
                                   uri=plan_uri, sha256=digest(raw_plan))]),
                    actor='migration', reason='Preserve agreed plan; distinguish predictions from unobserved results')
            decisions = {
                'primary_metric': {'value': 'Q1 is mean survival in the worst 25% of games; use it to choose exploratory continuations.',
                                   'also_report': ['Worst', 'Mean', 'Q4', 'Best', 'score', 'milestone success']},
                'research_workflow': {'value': 'Discuss concepts, competing hypotheses, and useful theoretical connections in chat. '
                                     'Use the cheapest discriminating experiment; record predictions before execution and measured results afterward. '
                                     'The notebook supports discussion rather than replacing it.'},
                'checkpoint_roles': {'value': 'At migration, retained parent is checkpoint324; Uniform #2 is the exploratory continuation starting model. '
                                     'Verify current acceptance before relying on this time-stamped context.'},
                'launch_authority': {'value': 'Records do not authorize training, retries, opening seed cohorts, or checkpoint promotion. '
                                     'Preserve existing registration, review, seed-exclusion, resource, exactly-once, and parent acceptance requirements.'},
                'local_memory': {'value': 'SQLite is the working research notebook; JSON is its versioned restore snapshot. '
                                'Use local full-text retrieval first. Embeddings or an LLM memory framework can be added if retrieval proves insufficient.'},
            }
            with store.transaction():
                for key, value in decisions.items():
                    store.db.execute('INSERT INTO project_context VALUES (?,?,?,?,?)',
                        ('dodge-native', key, encoded(value), 'conversation:518b8c2d-01fb-4f39-acc3-f2d9f1f35c4e', now()))
            store.check()
            store.export(output)
            return {'snapshot': str(output), 'experiments': len(store.list()), 'status': 'imported'}
        finally:
            store.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_SNAPSHOT)
    print(json.dumps(migrate(parser.parse_args().output), indent=2))
