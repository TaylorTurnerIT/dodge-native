"""Terminal receipts and returned-native-cost conservation for the continuation; stdlib only."""
from __future__ import annotations
import json
from pathlib import Path

import binding as b
import metrics


def rows(path, *, strict=False):
    if not Path(path).is_file():
        return
    with Path(path).open() as stream:
        for line in stream:
            if not line.endswith('\n'):
                b.need(not strict, 'torn journal'); break
            yield json.loads(line)


def full_accounting(out, worker, *, strict=False):
    """Role-separated costs from the compact journals. Tolerates a returned-prefix journal when not strict."""
    train = dict(raw=0, constructors=0, steps=0, resets=0, initial_startup=0, reset_startup=0, step_raw=0)
    segments = {}; ends = {}; updates = completed_episodes = assignments = 0
    for event in rows(Path(out)/'training-events.jsonl', strict=strict):
        kind = event['kind']
        if kind == 'segment_initial':
            b.need(event['segment'] not in segments, 'duplicate segment')
            segments[event['segment']] = event
            train['constructors'] += 1; train['initial_startup'] += event['initial_startup_frames']
        elif kind == 'returned_step_cost':
            train['steps'] += 1; train['step_raw'] += event['raw']
            b.need(type(event['raw']) is int and 0 <= event['raw'] <= 4*b.SLOTS, 'invalid returned step cost')
        elif kind == 'returned_reset':
            b.need(event['startup_frames'] == b.STARTUP*len(event['slots']), 'reset startup differs from 13*resets')
            train['resets'] += len(event['slots']); train['reset_startup'] += event['startup_frames']
        elif kind == 'update_metrics':
            updates += 1; b.need(event['global_update'] == b.CAMPAIGN_BASE+updates, 'global update journal order differs')
        elif kind == 'episodes_completed':
            completed_episodes += len(event['rows'])
        elif kind == 'assignments':
            assignments += len(event['rows'])
        elif kind == 'segment_end':
            ends[event['segment']] = event
    train['raw'] = train['initial_startup']+train['step_raw']+train['reset_startup']
    b.need(train['raw'] <= b.TRAINING_LIMITS['raw_frames'] and train['constructors'] <= b.TRAINING_LIMITS['constructors']
           and train['steps'] <= b.TRAINING_LIMITS['native_steps'] and train['resets'] <= b.TRAINING_LIMITS['resets'],
           'training journal exceeds registered budgets')
    ev = dict(raw=0, constructors=0, steps=0, resets=0); episodes = {}; receipts = 0
    for event in rows(Path(out)/'evaluation-events.jsonl', strict=strict):
        if event['kind'] == 'evaluation_episode':
            key = (event['global_update'], event['episode_index'])
            b.need(key not in episodes and event['global_update'] in b.EVAL_UPDATES and 0 <= event['episode_index'] < 1024
                   and event['seed'] == b.SEEDS[event['episode_index']] and event['startup_frames'] == b.STARTUP
                   and 1 <= event['steps'] <= event['raw'] <= 18000, 'evaluation journal episode differs')
            episodes[key] = event
            ev['constructors'] += 1; ev['steps'] += event['steps']; ev['raw'] += event['raw']+b.STARTUP
        elif event['kind'] == 'evaluation_receipt':
            receipts += 1
    b.need(ev['raw'] <= b.EVALUATION_LIMITS['raw_frames'] and ev['constructors'] <= b.EVALUATION_LIMITS['constructors']
           and ev['steps'] <= b.EVALUATION_LIMITS['native_steps'], 'evaluation journal exceeds registered budgets')
    result = dict(training=train, evaluation=ev, updates_journaled=updates, segments_started=len(segments),
        segments_ended=len(ends), completed_episodes=completed_episodes, seed_assignments=assignments,
        evaluation_receipts_journaled=receipts,
        evidence_limit='Returned complete journal prefix only; native exceptions without returned results, and episodes in '
                       'flight at a fault, have unknown cost.',
        worker_claimed_updates=worker.get('updates'))
    result['_episodes'], result['_segments'], result['_ends'] = episodes, segments, ends
    return result


def public(report):
    return {k: v for k, v in report.items() if not k.startswith('_')}


def accounting(out, worker, *, strict=False):
    """JSON-safe view used by the observer (also on failure paths)."""
    return public(full_accounting(out, worker, strict=strict))


def validate_outputs(reg, worker, registration_sha):
    out = Path(reg['output'])
    b.need(worker.get('schema') == 'uniform2_recovery240_worker_v1' and worker.get('status') == 'completed'
           and worker.get('run_id') == reg['run_id'] and worker.get('registration_sha256') == registration_sha
           and worker.get('updates') == b.UPDATES and worker.get('no_retry') is True, 'worker identity/completion differs')
    b.need(all(worker.get(k) is False for k in ('training_eligible', 'promoted', 'automatic_selection')), 'worker eligibility differs')
    b.need(0 <= worker['elapsed_seconds'] < reg['limits']['work_seconds'], 'worker work deadline exceeded')
    counters = worker['counters']
    b.need(counters['updates'] == b.UPDATES and counters['environment_decisions'] == b.DECISIONS, 'registered PPO budget differs')
    report = full_accounting(out, worker, strict=True)
    train, ev = report['training'], report['evaluation']
    b.need(report['updates_journaled'] == b.UPDATES and report['segments_started'] == report['segments_ended'] == b.SEGMENTS
           and train['steps'] == b.TRAINING_LIMITS['native_steps'] and train['constructors'] == b.SEGMENTS,
           'update/segment/step conservation differs')
    b.need(counters['raw_frames'] == train['step_raw'], 'worker raw-frame counter differs from returned native costs')
    roles = worker['roles']
    b.need(all(roles['training'][k] == train[k] for k in ('raw', 'constructors', 'steps', 'resets'))
           and all(roles['evaluation'][k] == ev[k] for k in ('raw', 'constructors', 'steps', 'resets'))
           and ev['constructors'] == b.EVAL_EPISODES == len(report['_episodes']), 'role accounting differs from journals')
    # checkpoints, segment chain, identity
    checkpoints = worker['checkpoints']
    b.need([c['global_update'] for c in checkpoints] == b.CHECKPOINT_UPDATES, 'four recovery boundary checkpoints required')
    identity = b.learner_identity(reg, registration_sha); identity_sha = b.identity_hash(identity)
    chain = dict(model=None)
    for index, c in enumerate(checkpoints):
        path = Path(c['path'])
        b.need(path == out/f"checkpoint-global-{c['global_update']:03d}.pt" and b.sha(path) == c['sha256']
               and b.read(path.with_name(path.name+'.json')) == c and c['identity_sha256'] == identity_sha
               and c['segment'] == index and c['abandoned_current_episodes'] == b.SLOTS
               and c['phase_update'] == b.PHASE_BASE+c['global_update'] and c['cumulative_update'] == b.CUMULATIVE_BASE+c['global_update']
               and not path.stat().st_mode & 0o222, 'continuation checkpoint receipt/immutability differs')
        nxt = report['_segments'].get(index+1)
        b.need(nxt is None or nxt['next_episode_indices'] == c['next_episode_indices'], 'segment resume indices differ from checkpoint')
        end = report['_ends'][index]
        b.need(end['next_episode_indices'] == c['next_episode_indices'] and len(end['abandoned']) == b.SLOTS
               and report['_segments'][index]['global_update_base'] == b.CAMPAIGN_BASE+index*b.SEGMENT_UPDATES, 'segment boundary journal differs')
    b.need(report['_segments'][0]['next_episode_indices'] == reg['parent']['initial_episode_indices']
           and report['_segments'][0]['slot_stream_sha256'] == reg['streams']['first_segment_slot_stream_sha256'],
           'first segment does not start from the qualified parent state')
    # evaluations
    analysis = b.frozen()['expanded_eval']; summaries = {}; receipts = {}
    fps = {b.CAMPAIGN_BASE: reg['parent']['restore_fingerprints']}
    for c in checkpoints:
        fps[c['global_update']] = dict(model=c['model_fingerprint'], Adam=c['optimizer_fingerprint'], RNG=c['rng_fingerprint'])
    raw_total = 0
    for g, entry in zip(b.EVAL_UPDATES, worker['evaluations']):
        digest = reg['parent']['checkpoint_sha256'] if g == b.CAMPAIGN_BASE else checkpoints[(g-b.CAMPAIGN_BASE)//b.SEGMENT_UPDATES-1]['sha256']
        r = b.read(out/f'evaluation-{g:03d}.json'); claim = b.read(out/f'evaluation-{g:03d}.claim')
        b.need(claim == dict(global_update=g, checkpoint_sha256=digest, registration_sha256=registration_sha)
               and r['schema'] == 'uniform2_recovery240_evaluation_v1' and r['global_update'] == g
               and r['checkpoint_sha256'] == digest == entry['checkpoint_sha256'] and r['registration_sha256'] == registration_sha
               and r['cohort'] == 'D6' and r['action_mode'] == 'sampled_categorical' and r['normal_start'] is True
               and r['cutoff_enabled'] is False and r['automatic_selection'] is False and r['promoted'] is False
               and b.sha(out/f'evaluation-{g:03d}.json') == entry['receipt_sha256'], 'evaluation receipt identity differs')
        b.need(r['learner_state_restored']['fingerprints'] == fps[g] and r['learner_state_restored']['module_training_flags_equal'] is True,
               'learner RNG/model/Adam/train-mode not exactly preserved across evaluation')
        if g:
            b.need(r['scratch']['model_fingerprint'] == fps[g]['model'], 'evaluated weights differ from the saved checkpoint')
        rows_ = analysis.validate_full_rows(r['rows'], b.SEEDS)
        b.need(metrics.summarize(rows_) == r['summary'], 'evaluation summary differs from rows')
        for row in rows_:
            e = report['_episodes'][(g, row['episode_index'])]
            b.need(e['raw'] == row['gameplay_frames'] and e['alive_frames'] == row['alive_frames']
                   and e['terminated'] == row['terminated'], 'journal/row conservation differs')
        b.need(r['raw_frames_including_startup'] == sum(x['gameplay_frames']+x['startup_frames'] for x in rows_), 'evaluation frame total differs')
        raw_total += r['raw_frames_including_startup']; summaries[g] = r['summary']; receipts[g] = digest
    b.need(raw_total == ev['raw'], 'evaluation role raw total differs')
    selection = metrics.Selection(starting_update=b.CAMPAIGN_BASE)
    for g in b.EVAL_UPDATES:
        selection.add(g, summaries[g], receipts[g])
    stored = b.read(out/'selection.json'); report_sel = selection.report()
    b.need({k: v for k, v in stored.items() if k in report_sel} == report_sel and stored['official_parent324_promotion'] is False
           and stored['promoted'] is False and b.sha(out/'selection.json') == worker['selection_sha256']
           and worker['selected'] == report_sel['selected'], 'selection differs from independent recomputation')
    resources = b.worker_resources(out, strict=True)
    b.need(resources['samples'] > 0 and resources['peak_rss_bytes'] <= b.CAP and resources['peak_mps_driver_bytes'] <= b.CAP,
           'terminal resources missing/over limit')
    return public(report)
