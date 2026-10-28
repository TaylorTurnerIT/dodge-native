"""Offline six-model D4 merge of the two audited evaluation parts; stdlib only.

Inert unless BOTH parts' terminal audits verify. It never imports Torch/native modules, never deserializes a
checkpoint and never evaluates a model: it only re-verifies hash/JSON chains, then reads the rows already
published by the two once-only runs. It does not choose settings, select a model, or open D5/B/E.
"""
from __future__ import annotations
import argparse
import json
from bisect import bisect_left
from pathlib import Path
import random

import binding as b
import comparison
from paired_statistics import KEYS, metrics, percentile

PART_AUDIT_STATUS = 'accepted_complete_fixed_terminal60_d4_evaluation'
FIXED_REG_FIELDS = ('study_id', 'backend', 'backend_pins', 'evaluator_source', 'runtime_root', 'runtime_manifest_sha256',
                    'input_manifest_sha256', 'runtime_versions', 'seeds', 'cohort', 'exclusion_union', 'evaluation_rng_seed',
                    'bootstrap', 'semantics', 'limits', 'interpreter', 'provenance', 'cohort_state', 'history_state',
                    'reservation_state')
PAIRS = tuple((f'replica-{k}-opening_priority', f'replica-{k}-uniform') for k in (1, 2, 3))
AVERAGE = 'average_of_three_matched_pairs'


class NotReady(RuntimeError):
    pass


def verify_producer(policy, *, reproduce_identity=True):
    """Re-verify one accepted producer's terminal60 chain (hash/JSON only) and return its identity record."""
    p = policy['producer']; b.check_pins(p['pins'])
    reg = b.read(p['registration_path']); audit = b.read(p['audit_path']); worker = b.read(p['worker_result_path'])
    sidecar = b.read(p['sidecar_path']); manifest = b.read(p['artifact_manifest_path']); release = b.read(p['lease_release_path'])
    digest = b.sha(p['registration_path']); endpoint = worker['formal_comparison_endpoint']
    b.need(reg['schema'] == 'dodge_seed_priority_registration_v1' and reg['status'] == 'parent_registered'
           and reg['study_id'] == b.STUDY and reg['run_id'] == f"{b.STUDY}-{policy['id']}"
           and policy['id'] == f"replica-{reg['replica']}-{reg['arm']}" and reg['backend'] == 'mps', 'producer registration identity differs')
    b.need(audit['status'] == 'accepted_complete_global_update60_training_receipt' and audit['registration_sha256'] == digest
           and audit['parent_raw_observer_exit_code'] == 0 and audit['observer_observed_worker_raw_exit'] == 0
           and audit['observer_directly_reaped'] is True and audit['terminal']['terminal_update'] == 60
           and all(audit[k] is False for k in ('automatic_selection', 'promoted', 'training_eligible')), 'producer audit not accepted')
    b.need(release['status'] == 'exact_lease_cleared_after_durable_parent_audit' and release['audit_sha256'] == b.sha(p['audit_path']),
           'producer lease not released after durable audit')
    b.need(audit['output_manifest']['sha256'] == b.sha(p['artifact_manifest_path']), 'producer output manifest differs')
    name = Path(policy['checkpoint_path']).name
    b.need(manifest.get(name) == policy['checkpoint_sha256'] and manifest.get(name+'.json') == b.sha(p['sidecar_path'])
           and manifest.get('worker-result.json') == b.sha(p['worker_result_path']), 'checkpoint not in audited producer manifest')
    b.need(worker['status'] == 'completed' and worker['updates'] == 60 and worker['registration_sha256'] == digest
           and endpoint == sidecar and endpoint['global_update'] == 60 and endpoint['phase_update'] == 384
           and endpoint['cumulative_update'] == 432 and endpoint['formal_comparison_endpoint'] is True
           and endpoint['sha256'] == policy['checkpoint_sha256'] and endpoint['path'] == policy['checkpoint_path']
           and endpoint['identity'] == p['expected_identity'] and endpoint['identity_sha256'] == b.identity_hash(p['expected_identity'])
           and all(endpoint[k] is False for k in ('promoted', 'automatic_selection', 'training_eligible')),
           'producer terminal60 endpoint differs')
    if reproduce_identity:
        b.need(b.learner_identity(reg, digest, b.contracts()) == p['expected_identity'], 'producer identity not reproducible')
    b.need(b.sha(policy['checkpoint_path']) == policy['checkpoint_sha256'], 'checkpoint bytes drift')
    return dict(id=policy['id'], run_id=reg['run_id'], replica=reg['replica'], arm=reg['arm'], registration_sha256=digest,
        terminal_audit_sha256=b.sha(p['audit_path']), checkpoint_sha256=policy['checkpoint_sha256'],
        identity_sha256=endpoint['identity_sha256'], parent_checkpoint_sha256=endpoint['parent_checkpoint_sha256'],
        producer_source_manifest_sha256=p['source_manifest_sha256'], producer_runtime_manifest_sha256=p['runtime_manifest_sha256'])


def journal_counts(path):
    """Cheap journal conservation: constructors and completions per policy, without parsing step rows."""
    counts = {}
    with Path(path).open() as stream:
        for line in stream:
            if '"kind":"evaluation_step"' in line:
                continue
            kind = 'constructors' if '"kind":"evaluation_constructor"' in line else \
                   'completed' if '"kind":"evaluation_completed"' in line else None
            b.need(kind is not None, 'unexpected journal event')
            policy = json.loads(line)['policy_id']
            counts.setdefault(policy, dict(constructors=0, completed=0))[kind] += 1
    return counts


def verify_part(directory, policies, *, pins=None, producers=True, reproduce_identity=True):
    """Audit-chain verification of one evaluation part. Reads NO outcome rows."""
    d = Path(directory); out = d/'worker-output'
    for name in ('parent-terminal-audit.json', 'registration-final.json'):
        if not (d/name).is_file():
            raise NotReady(f'{d.name}: {name} missing')
    audit = b.read(d/'parent-terminal-audit.json')
    if audit.get('status') != PART_AUDIT_STATUS:
        raise NotReady(f'{d.name}: terminal audit not accepted')
    reg = b.read(d/'registration-final.json'); reg_sha = b.sha(d/'registration-final.json')
    audit_sha = b.sha(d/'parent-terminal-audit.json')
    b.need(reg['status'] == 'parent_registered' and audit['registration_sha256'] == reg_sha, 'part registration differs from audit')
    src_sha = b.sha(d/'source-manifest.json')
    b.need(src_sha == reg['source_manifest_sha256'] == audit['source_manifest_sha256'], 'part source manifest differs')
    b.check_pins({str(d/n): h for n, h in b.read(d/'source-manifest.json')['files'].items()})
    comparison_sha = b.sha(out/'comparison.json')
    if pins:
        b.need((src_sha, reg_sha, comparison_sha) == (pins['source_manifest_sha256'], pins['registration_final_sha256'],
               pins['comparison_sha256']), 'part differs from its pinned accepted hashes')
    b.need(audit['raw_worker_exit_code'] == audit['raw_observer_exit_code'] == 0 and audit['comparison_sha256'] == comparison_sha
           and audit['intervals_independently_recomputed'] is True and audit['main_training_state_written'] is False
           and audit['d5_opened'] is False and all(audit[k] is False for k in ('automatic_selection', 'promoted', 'training_eligible')),
           'part audit flags differ')
    acc = audit['accounting']
    b.need(acc['completed_episodes'] == acc['constructors'] == b.EPISODES and acc['native_steps'] <= b.STEP_CAP
           and acc['raw_frames_including_startup'] <= b.RAW_CAP, 'part accounting differs')
    release = b.read(d/'lease-release.json'); ledger = b.read(d/'evaluation-resource-ledger.json')
    b.need(release == dict(status='exact_lease_cleared_after_durable_parent_audit', audit_sha256=audit_sha), 'part lease release differs')
    b.need(ledger['active_evaluation_lease'] is None and ledger['terminal_complete'] is True and ledger['d5_opened'] is False
           and ledger['main_state_written'] is False and ledger['parent_audit_sha256'] == audit_sha
           and ledger['run_id'] == reg['run_id'], 'part own ledger not cleared after audit')
    exit_record = b.read(d/'execution-exit.json'); execution = b.read(d/'parent-execution.json')
    b.need(exit_record['raw_observer_exit_code'] == 0 and exit_record['observer_directly_reaped'] is True
           and exit_record['registration_sha256'] == execution['registration_sha256'] == reg_sha, 'part raw exit differs')
    worker = b.read(out/'worker-result.json')
    b.need(worker['status'] == 'completed' and worker['run_id'] == reg['run_id'] and worker['registration_sha256'] == reg_sha
           and worker['completed_policies'] == list(policies) and worker['rows_completed'] == b.EPISODES
           and worker['comparison_sha256'] == comparison_sha and worker['constructors'] == b.EPISODES
           and all(worker[k] is False for k in ('automatic_selection', 'promoted', 'training_eligible')), 'part worker result differs')
    manifest = b.read(d/'dispatch'/reg['run_id']/'artifact-manifest.json')
    actual = {p.name for p in out.iterdir() if p.is_file() and not p.is_symlink()}
    b.need(actual == set(manifest), 'part worker output member set differs from observer manifest')
    b.check_pins({str(out/n): h for n, h in manifest.items()})
    counts = journal_counts(out/'evaluation-events.jsonl')
    b.need(counts == {name: dict(constructors=1024, completed=1024) for name in policies}, 'part journal policy/episode set differs')
    b.need([p['id'] for p in reg['policies']] == list(policies), 'part registration policy set differs')
    ids = []
    for policy in reg['policies']:
        ids.append(verify_producer(policy, reproduce_identity=reproduce_identity) if producers else dict(id=policy['id']))
        b.need(b.read(out/(policy['id']+'.claim')) == dict(policy_id=policy['id'], registration_sha256=reg_sha,
               checkpoint_sha256=policy['checkpoint_sha256']), 'part policy claim differs')
    return dict(directory=d, reg=reg, reg_sha=reg_sha, audit_sha=audit_sha, source_sha=src_sha, comparison_sha=comparison_sha,
                producers=ids, accounting=acc)


def cross_check(first, last):
    """Same D4/RNG/runtime/settings, six distinct models, no overlap or re-evaluation."""
    fr, lr = first['reg'], last['reg']
    for field in FIXED_REG_FIELDS:
        b.need(fr[field] == lr[field], 'parts differ on fixed field: '+field)
    b.need(fr['seeds'] == b.SEEDS and lr['seeds'] == b.SEEDS and len(set(b.SEEDS)) == 1024, 'D4 seed vector differs from canonical')
    b.need(fr['semantics'] == lr['semantics'] == b.SEMANTICS and fr['bootstrap'] == lr['bootstrap'] == b.BOOTSTRAP
           and fr['evaluation_rng_seed'] == lr['evaluation_rng_seed'] == b.EVAL_RNG_SEED, 'dataset/RNG/bootstrap settings differ')
    b.need(fr['cohort']['d5_state'] == lr['cohort']['d5_state'] == 'unopened', 'D5 not unopened')
    b.need(fr['run_id'] != lr['run_id'] and fr['expected_lease']['owner_token'] != lr['expected_lease']['owner_token']
           and fr['source_manifest_sha256'] != lr['source_manifest_sha256'], 'parts are not distinct evaluations')
    ids = [p['id'] for p in fr['policies']]+[p['id'] for p in lr['policies']]
    b.need(ids == list(b.SIX_POLICIES) and len(set(ids)) == 6, 'six distinct canonical model IDs required')
    producers = first['producers']+last['producers']
    for key in ('checkpoint_sha256', 'run_id', 'registration_sha256', 'identity_sha256', 'terminal_audit_sha256'):
        b.need(len({p[key] for p in producers}) == 6, 'six distinct values required: '+key)
    b.need(len({p['parent_checkpoint_sha256'] for p in producers}) == 1, 'producers disagree on parent checkpoint')
    b.need({(p['replica'], p['arm']) for p in producers} == {(k, a) for k in (1, 2, 3) for a in b.ARMS}, 'three replicas x two arms required')
    staging = lr['staging']['first_part']
    b.need(staging['registration_final_sha256'] == first['reg_sha'] and staging['comparison_sha256'] == first['comparison_sha']
           and staging['parent_terminal_audit_sha256'] == first['audit_sha'] and staging['source_manifest_sha256'] == first['source_sha']
           and lr['staging']['first_part_re_evaluated_by_this_run'] is False, 'last part does not pin the audited first part')
    later = [row['id'] for row in fr['staging']['later_three']]
    b.need(later == [p['id'] for p in lr['policies']] and fr['staging']['later_three_required_by_this_run'] is False,
           'first part did not predeclare exactly the last three')
    b.need([(r['id'], r['checkpoint_path']) for r in fr['staging']['later_three']]
           == [(p['id'], p['checkpoint_path']) for p in lr['policies']], 'predeclared checkpoint paths differ')


def load_rows(part):
    """Published rows, read only after the audit chain verified."""
    out = part['directory']/'worker-output'; rows, receipts = {}, {}
    for policy in part['reg']['policies']:
        receipt = b.read(out/(policy['id']+'.json'))
        b.need(receipt['policy_id'] == policy['id'] and receipt['registration_sha256'] == part['reg_sha']
               and receipt['checkpoint_sha256'] == policy['checkpoint_sha256']
               and receipt['action_mode'] == 'sampled_categorical' and receipt['normal_start'] is True
               and receipt['cutoff_enabled'] is False and receipt['promoted'] is False, 'receipt identity/semantics differ')
        b.need(len(receipt['rows']) == 1024 and [r['seed'] for r in receipt['rows']] == b.SEEDS
               and [r['episode_index'] for r in receipt['rows']] == list(range(1024)), '1024 exact seed rows required per model')
        b.need(comparison.summarize(receipt['rows'], b.SEEDS) == receipt['summary'], 'receipt summary differs from rows')
        rows[policy['id']] = receipt['rows']; receipts[policy['id']] = receipt
    stored = b.read(out/'comparison.json')
    b.need({k: stored['policies'][k] for k in stored['policies']} == {k: receipts[k]['summary'] for k in receipts},
           'stored part comparison differs from receipts')
    return rows, stored


def diff(left, right):
    return dict(metric_differences={k: left['performance'][k]-right['performance'][k] for k in KEYS},
        milestone_numerator_differences={h: left['milestones'][h]['numerator']-right['milestones'][h]['numerator'] for h in left['milestones']},
        milestone_rate_differences={h: (left['milestones'][h]['numerator']-right['milestones'][h]['numerator'])/1024 for h in left['milestones']},
        death_cause_count_differences={k: left['death_causes'][k]-right['death_causes'][k] for k in left['death_causes']},
        cap_count_difference=left['caps']-right['caps'])


def average(items):
    def mean(key):
        return {k: sum(item[key][k] for item in items)/len(items) for k in items[0][key]}
    return dict(metric_differences=mean('metric_differences'), milestone_numerator_differences=mean('milestone_numerator_differences'),
        milestone_rate_differences=mean('milestone_rate_differences'), death_cause_count_differences=mean('death_cause_count_differences'),
        cap_count_difference=sum(item['cap_count_difference'] for item in items)/len(items))


def bootstrap(rows, contract):
    """Shared paired-evaluation-seed resampling: the same indices feed all six policies, three pairs and their average."""
    b.need(contract == b.BOOTSTRAP and set(rows) == set(b.SIX_POLICIES) and all(len(v) == 1024 for v in rows.values()),
           'registered bootstrap and six full policies required')
    n = 1024; values = {k: [r['alive_frames'] for r in v] for k, v in rows.items()}
    labels = [f'replica-{k}-priority_minus_uniform' for k in (1, 2, 3)]+[AVERAGE]
    samples = {l: {k: [] for k in KEYS} for l in labels}; rates = {l: {str(h): [] for h in b.MILESTONES} for l in labels}
    rng = random.Random(contract['seed'])
    for _ in range(contract['draws']):
        indices = [rng.randrange(n) for _ in range(n)]
        sampled = {k: sorted(v[i] for i in indices) for k, v in values.items()}
        calc = {k: metrics(v) for k, v in sampled.items()}
        drawn = []
        for left, right in PAIRS:
            drawn.append(({k: calc[left][k]-calc[right][k] for k in KEYS},
                          {str(h): (bisect_left(sampled[right], h)-bisect_left(sampled[left], h))/n for h in b.MILESTONES}))
        drawn.append(({k: sum(d[0][k] for d in drawn[:3])/3 for k in KEYS}, {str(h): sum(d[1][str(h)] for d in drawn[:3])/3 for h in b.MILESTONES}))
        for label, (performance, milestone) in zip(labels, drawn):
            for k in KEYS:
                samples[label][k].append(performance[k])
            for h in b.MILESTONES:
                rates[label][str(h)].append(milestone[str(h)])
    tail = (1-contract['confidence'])/2
    interval = lambda x: dict(low=percentile(x, tail), high=percentile(x, 1-tail))
    return {l: dict(performance={k: interval(x) for k, x in samples[l].items()},
                    milestone_rate_differences={h: interval(x) for h, x in rates[l].items()}) for l in labels}


def check_against_stored(intervals, first_stored, last_stored):
    """The merge's pair 1 and pair 3 intervals must reproduce each part's own audited, independently recomputed intervals."""
    for label, stored in (('replica-1-priority_minus_uniform', first_stored), ('replica-3-priority_minus_uniform', last_stored)):
        mine = intervals[label]; theirs = stored['paired_conditional_seed_intervals']['comparisons'][label]
        b.need(mine['performance'] == theirs['performance'] and mine['milestone_rate_differences'] == theirs['milestone_rate_differences'],
               'merge interval differs from the part audited interval: '+label)


UNCERTAINTY = dict(kind='conditional_evaluation_seed_resampling_only', resampling_unit='paired_evaluation_seed',
    conditional_on='the six fixed trained policies, each with one sampled-action realization on the 1024 D4 seeds',
    training_population_inference=False, training_replicas=3, training_runs=6, evaluation_seeds=1024,
    evaluation_episodes_per_policy=1024, evaluation_episodes_total=6144,
    note='The 1024 evaluation seeds are not training replicates: independent training replicates remain 3, not 3072. '
         'Intervals describe evaluation-seed variation for these exact checkpoints, not variation across training runs, '
         'and are not evidence about the training method. The three-pair average and its interval are descriptive only.')


def merge(first_dir, last_dir, *, first_pins=None, producers=True, reproduce_identity=True):
    first = verify_part(first_dir, b.FIRST_PART_POLICIES, pins=first_pins, producers=producers, reproduce_identity=reproduce_identity)
    last = verify_part(last_dir, b.POLICIES, producers=producers, reproduce_identity=reproduce_identity)
    if producers:
        cross_check(first, last)
    # Only now, with both audit chains accepted, are the published rows read.
    first_rows, first_stored = load_rows(first); last_rows, last_stored = load_rows(last)
    rows = {name: (first_rows if name in first_rows else last_rows)[name] for name in b.SIX_POLICIES}
    summaries = {name: comparison.summarize(rows[name], b.SEEDS) for name in b.SIX_POLICIES}
    pair_diffs = {f'replica-{k}': diff(summaries[left], summaries[right]) for k, (left, right) in zip((1, 2, 3), PAIRS)}
    intervals = bootstrap(rows, b.BOOTSTRAP)
    check_against_stored(intervals, first_stored, last_stored)
    ordered = [pair_diffs[f'replica-{k}'] for k in (1, 2, 3)]
    producer_map = {p['id']: p for p in first['producers']+last['producers']}
    return dict(schema='fullgame_priority_d4_six_model_merge_v1',
        status='merged_offline_descriptive_development_d4', launch_authority=False, automatic_selection=False, promoted=False,
        d5_opened=False, new_native_or_model_evaluation=False,
        cohort=dict(name='D4', range=list(b.D4), count=1024, d5_state='unopened', role='development cohort, not confirmation'),
        settings=dict(semantics=b.SEMANTICS, evaluation_rng_seed=b.EVAL_RNG_SEED, bootstrap=b.BOOTSTRAP),
        parts=dict(first=dict(run_id=first['reg']['run_id'], registration_sha256=first['reg_sha'], terminal_audit_sha256=first['audit_sha'],
                              comparison_sha256=first['comparison_sha'], policies=list(b.FIRST_PART_POLICIES)),
                   last=dict(run_id=last['reg']['run_id'], registration_sha256=last['reg_sha'], terminal_audit_sha256=last['audit_sha'],
                             comparison_sha256=last['comparison_sha'], policies=list(b.POLICIES))),
        policies={name: dict(summary=summaries[name], producer=producer_map[name]) for name in b.SIX_POLICIES},
        pairs={k: dict(minuend=left, subtrahend=right, label='priority_minus_uniform', **pair_diffs[f'replica-{n}'])
               for n, (left, right), k in zip((1, 2, 3), PAIRS, ('pair_1', 'pair_2', 'pair_3'))},
        pair_average=dict(role='descriptive_average_of_three_matched_pairs', pairs=3, **average(ordered)),
        conditional_paired_seed_intervals=dict(contract=b.BOOTSTRAP, comparisons=intervals, uncertainty=UNCERTAINTY,
            method='paired percentile bootstrap; shared index draws across all six policies; linear-interpolated quantiles',
            reproduces_part_intervals=['replica-1-priority_minus_uniform', 'replica-3-priority_minus_uniform']),
        uncertainty=UNCERTAINTY,
        interpretation='Descriptive D4 development result for six fixed terminal60 checkpoints (3 matched priority/uniform '
                       'training pairs). No selection, promotion, method-superiority or D5 confirmation claim; '
                       'training-population inference is not made.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--first-dir', default=str(b.FIRST_PART)); parser.add_argument('--last-dir', default=str(b.HERE))
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    path = Path(args.output).resolve(); b.need(path.parent == b.HERE and path.name != 'merge.py', 'merge output must be owned and new')
    try:
        report = merge(args.first_dir, args.last_dir, first_pins=b.FIRST_PART_PINS)
    except NotReady as error:
        print('REFUSED', error); raise SystemExit(3)
    b.save(path, report); print(b.sha(path), flush=True)
