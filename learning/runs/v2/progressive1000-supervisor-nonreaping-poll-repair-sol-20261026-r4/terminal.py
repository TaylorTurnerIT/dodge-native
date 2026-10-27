"""JSON/hash terminal accounting. Embedded checkpoints remain a parent audit gate."""
from __future__ import annotations
from dataclasses import asdict
import importlib.util
import json
from pathlib import Path
import sys

import binding as b


def rows(path, *, strict=False):
    """Retain complete journal prefixes after failure; never repair a torn line."""
    if not Path(path).is_file():
        return
    with Path(path).open() as stream:
        for line in stream:
            if not line.endswith('\n'):
                b.need(not strict, 'torn terminal journal: '+str(path))
                break
            yield json.loads(line)


def accounting(out, worker):
    metrics = list(rows(Path(out)/'training-metrics.jsonl'))
    snapshot = worker.get('final_snapshot') or {}
    env = snapshot.get('environment') or {}
    gameplay = startup = initial_cost = initial_count = steps = decisions = resets = 0
    for event in rows(Path(out)/'training-events.jsonl'):
        if event['kind'] == 'returned_step_cost':
            steps += 1; decisions += len(event['elapsed_raw_frames']); gameplay += sum(event['elapsed_raw_frames'])
        elif event['kind'] == 'returned_reset':
            resets += len(event['indices']); startup += sum(info['startup_frames'] for info in event['info'])
        elif event['kind'] == 'initial':
            initial_count += 1; initial_cost += sum(info['startup_frames'] for info in event['info'])
    return dict(completed_updates_journaled=len(metrics),
        completed_optimizer_steps_journaled=sum(e['metrics']['optimizer_steps'] for e in metrics),
        actual_optimizer_steps_including_failed_update=snapshot.get('actual_optimizer_steps_including_failed_update'),
        last_update_progress=snapshot.get('last_update_progress'),
        optimizer_count_scope='snapshot includes partial PPO; journal includes only published completed updates; missing snapshot is unknown',
        returned_vector_steps=steps,returned_environment_decisions=decisions,
        returned_native_gameplay_frames=gameplay,initial_startup_frames=initial_cost if initial_count else None,
        snapshot_initial_startup_frames=env.get('initial_construction_startup_frames'),
        returned_cost_scope='Complete journal prefix only; absent construction journal or unreturned native calls leave actual cost unknown.',
        returned_reset_startup_frames=startup,returned_reset_count=resets,
        journaled_raw_frames_including_startup=gameplay+initial_cost+startup,
        snapshot_raw_frames_including_startup=env.get('raw_frames_total_including_returned_unaudited_work'),
        native_exception_without_returned_result_cost='unknown; no invented native cost',
        completed_counters=worker.get('counters'),snapshot_state=snapshot.get('state'),
        raw_worker_first_failure=worker.get('first_failure'),raw_worker_finalization_error=worker.get('finalization_error'))


def scheduler_module():
    path = b.SOURCE/'runtime/dodge_rl/scheduler_reference.py'
    spec = importlib.util.spec_from_file_location('_supervisor_scheduler_reference', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_outputs(reg, worker, registration_sha):
    """Require complete JSON accounting; never deserialize a checkpoint here."""
    c = b.contracts()
    out = Path(reg['output'])
    b.need(worker.get('status') == 'completed' and worker.get('updates') == 60
           and worker.get('run_id') == reg['run_id'] and worker.get('registration_sha256') == registration_sha,
           'worker did not complete registered global60')
    b.need(all(worker.get(k) is False for k in ('training_eligible','promoted','automatic_selection'))
           and worker.get('evaluated_updates') == [] and worker.get('phase_update') == 384
           and worker.get('cumulative_update') == 432, 'terminal identity/eligibility differs')
    b.need(0 <= worker['elapsed_seconds'] < b.LIMITS['total_seconds'], 'worker elapsed budget differs')
    entry = b.read(out/'entry-restoration.json')
    b.need(entry['study_id'] == reg['study_id'] and entry['pair_id'] == reg['pair_id']
           and entry['replica'] == reg['replica'] and entry['arm'] == reg['arm'] and entry['backend'] == reg['backend']
           and entry['seed_vector'] == reg['vector']['seeds'] and entry['vector_sha256'] == reg['vector']['vector_sha256']
           and entry['parent_fingerprints'] == reg['expected_parent_fingerprints'], 'entry full vector/parent binding differs')
    # The worker already authenticates the reference schema and its full vector.
    expected_ref = c.references.load_bound_reference(receipt_path=reg['reference']['receipt_path'],
        expected_receipt_sha256=reg['reference']['receipt_sha256'],expected_study_id=reg['study_id'],
        expected_replica=reg['replica'],expected_seed_vector=reg['vector']['seeds'],
        expected_vector_sha256=reg['vector']['vector_sha256'],expected_torch_version=reg['runtime_versions']['torch'])
    b.need(entry['seed_evidence']['torch_cpu_rng_state_sha256'] == expected_ref['torch_cpu_global_seed']
           and entry['seed_evidence']['torch_mps_rng_state_sha256'] == expected_ref['action_sampler_torch_mps_seed']
           and entry['seed_evidence']['torch_cpu_initial_seed'] == reg['vector']['seeds']['torch_cpu_global_seed'], 'entry RNG reference differs')
    b.need(entry['new_controller'] == dict(kind='constant',origin=372,horizon=60,first_update=373,
           last_update=432,start_lr=3e-5,end_lr=3e-5), 'controller binding differs')
    b.need(all(entry['post_lr_fingerprints'][k] == reg['expected_parent_fingerprints'][k] for k in ('model','Adam'))
           and entry['adapter_post_reseed_components']['torch_cpu'] == expected_ref['torch_cpu_global_seed']
           and entry['adapter_post_reseed_components']['torch_mps'] == expected_ref['action_sampler_torch_mps_seed'],
           'post-transition model/Adam/RNG binding differs')
    metrics = list(rows(out/'training-metrics.jsonl',strict=True))
    b.need([e['global_update'] for e in metrics] == list(range(1,61)), 'update journal incomplete/duplicated')
    optimizer = raw = 0
    for local, row in enumerate(metrics,1):
        value = row['metrics']; progress = row['progress']
        b.need(type(value['optimizer_steps']) is int and 0 < value['optimizer_steps'] <= 128
               and value['transitions'] == 16384, 'actual optimizer/decision counts differ')
        optimizer += value['optimizer_steps']
        counters = row['counters']
        b.need(type(counters['raw_frames']) is int and raw <= counters['raw_frames'] <= local*16384*4, 'raw metric counters differ')
        raw = counters['raw_frames']
        b.need(counters == dict(updates=local,optimizer_steps=optimizer,environment_decisions=local*16384,raw_frames=raw)
               and row['phase_update'] == 324+local and row['cumulative_update'] == 372+local
               and row['effective_learning_rate'] == 3e-5 and progress.get('complete') is True
               and progress.get('in_update') is False and progress['optimizer_steps'] == value['optimizer_steps'], 'update counters/progress differ')
    b.need(worker['counters'] == metrics[-1]['counters'], 'terminal counters differ')
    report = accounting(out,worker)
    b.need(report['returned_vector_steps'] == 60*256 and report['returned_environment_decisions'] == 983040
           and report['returned_native_gameplay_frames'] == raw and report['initial_startup_frames'] == 64*13
           and report['returned_reset_count'] <= b.LIMITS['resets']
           and report['journaled_raw_frames_including_startup'] <= b.LIMITS['raw_frames'], 'native/raw/startup accounting differs')
    snap = worker['final_snapshot']; env = snap['environment']
    b.need(snap['state'] == 'ready' and snap['completed_optimizer_steps'] == optimizer
           and snap['actual_optimizer_steps_including_failed_update'] == optimizer
           and env['completed_updates'] == 60 and env['pending_update'] is None
           and env['returned_work_not_accepted_by_audit'] == 0
           and env['returned_native_gameplay_frames_unaudited'] == env['gameplay_frames_including_fatal'] == raw
           and env['returned_native_vector_steps'] == report['returned_vector_steps']
           and env['initial_construction_startup_frames'] == report['initial_startup_frames']
           and env['normal_reset_count'] == report['returned_reset_count']
           and env['returned_reset_startup_frames_unaudited'] == env['reset_startup_frames'] == report['returned_reset_startup_frames']
           and env['accepted_raw_frames_total'] == report['snapshot_raw_frames_including_startup'] == report['journaled_raw_frames_including_startup']
           and worker['curriculum_snapshot'] == snap, 'snapshot/accounting binding differs')
    events = iter(rows(out/'training-events.jsonl',strict=True))
    initial = next(events)
    b.need(initial['kind'] == 'initial' and len(initial['info']) == 64, 'initial identity journal missing')
    module = scheduler_module()
    scheduler = module.Scheduler(reg['vector']['vector_sha256']) if reg['curriculum_enabled'] else None
    next_indices = list(reg['initial_episode_indices']); active = {}; seeds = set()
    assignment_count = completion_count = reset_count = 0
    def assign(row):
        nonlocal assignment_count
        slot = row['slot']; seed = row['seed']; episode = next_indices[slot]
        metadata = c.seed_metadata(reg['vector']['seeds']['env_master_seed'],slot,episode,reg['exclusion_union'])
        b.need(seed == dict(slot=slot,episode=episode,actual_seed=metadata['first_actual_seed'],counter=metadata['rejection_counter'],evaluation=False)
               and seed['actual_seed'] not in seeds, 'episode tuple/full vector identity or collision differs')
        expected = scheduler.assign() if scheduler else (None,18000,None)
        b.need((row['generation'],row['horizon'],row['ordinal']) == expected
               and row['vector_hash'] == (reg['vector']['vector_sha256'] if scheduler else None), 'assignment scheduler/vector identity differs')
        seeds.add(seed['actual_seed']); next_indices[slot] += 1; active[slot] = row
        b.need(row == env['assignments'][assignment_count], 'snapshot assignment differs')
        assignment_count += 1
    b.need([e['slot'] for e in initial['assignments']] == list(range(64)), 'initial slots differ')
    for row in initial['assignments']: assign(row)
    deaths = cutoffs = ordinary_caps = 0
    event = next(events,None)
    for local,row in enumerate(metrics,1):
        finished = []; decisions = []; collection_seen = False; local_raw = 0
        while event is not None:
            update = event.get('update',event.get('global_update'))
            if update != local: break
            kind = event['kind']
            if kind == 'returned_step_cost':
                b.need(not collection_seen and len(event['elapsed_raw_frames']) == 64
                       and all(type(v) is int and 0 <= v <= 4 for v in event['elapsed_raw_frames']), 'returned native vector cost differs')
                decisions.append(event['decision'])
                local_raw += sum(event['elapsed_raw_frames'])
            elif kind == 'completion':
                slot = event['slot']; assignment = active[slot]; info = event['native_info']
                b.need(info['seed'] == assignment['seed'] and info['terminated'] != info['truncated']
                       and all(event[k] == assignment[k] for k in ('generation','horizon','ordinal'))
                       and event['success'] == (info['alive_frames'] >= event['horizon']), 'completion/episode identity differs')
                if info['terminated']: deaths += 1
                elif event['horizon'] < 18000:
                    b.need(reg['curriculum_enabled'] and info['gameplay_frames'] == event['horizon'], 'practice cutoff differs')
                    cutoffs += 1
                else:
                    b.need(info['gameplay_frames'] == 18000, 'ordinary cap differs'); ordinary_caps += 1
                finished.append(event)
                b.need(env['completions'][completion_count] == {k:v for k,v in event.items() if k != 'kind'}, 'snapshot completion differs')
                completion_count += 1
            elif kind == 'reset_assignment': assign({k:v for k,v in event.items() if k != 'kind'})
            elif kind == 'collection_complete_before_PPO':
                b.need(not collection_seen, 'duplicate collection boundary'); collection_seen = True
            elif kind == 'returned_reset':
                b.need(env['returned_resets'][reset_count] == {k:v for k,v in event.items() if k != 'kind'}, 'returned reset receipt binding differs')
                reset_count += 1
            else: raise ValueError('unexpected training event kind: '+kind)
            event = next(events,None)
        b.need(decisions == list(range(256)) and collection_seen, 'collection decision order differs')
        previous_raw = metrics[local-2]['counters']['raw_frames'] if local > 1 else 0
        b.need(row['counters']['raw_frames'] == previous_raw+local_raw, 'per-update returned raw cost differs')
        boundary = (scheduler.finish_update(local,[module.Completion(e['decision'],e['slot'],e['generation'],e['horizon'],e['success']) for e in finished])
                    if scheduler else dict(completed_update=local,promoted=False,generation_after_boundary=None))
        b.need(row['scheduler_boundary'] == boundary and env['boundaries'][local-1] == boundary, 'post-PPO scheduler boundary differs')
    b.need(event is None and len(env['assignments']) == assignment_count and len(env['completions']) == completion_count
           and len(env['returned_resets']) == reset_count
           and env['consumed_actual_seed_union'] == sorted(seeds)
           and worker['final_resume_next_episode_indices'] == next_indices, 'terminal episodes/assignments differ')
    expected_scheduler = json.loads(json.dumps(asdict(scheduler))) if scheduler else None
    b.need(env['scheduler'] == expected_scheduler, 'terminal scheduler ledger differs')
    b.need(len(env['in_flight']) == 64 and sorted(e['slot'] for e in env['in_flight']) == list(range(64)), 'in-flight slots differ')
    for row in env['in_flight']:
        b.need(row['assignment_status'] == 'assigned' and row['native_info']['seed'] == active[row['slot']]['seed']
               and not row['native_info']['terminated'] and not row['native_info']['truncated'], 'in-flight episode identity differs')
    b.need(sum(e['native_info']['gameplay_frames'] for e in env['completions'])+sum(e['native_info']['gameplay_frames'] for e in env['in_flight']) == raw,
           'episode raw-frame conservation differs')
    checkpoints = worker['integrity_checkpoints']
    b.need([e['global_update'] for e in checkpoints] == [12,24,36,48,60]
           and worker['formal_comparison_endpoint'] == checkpoints[-1], 'five integrity endpoints differ')
    for record in checkpoints:
        local = record['global_update']; path = out/f'checkpoint-global-{local:03d}-integrity.pt'
        b.need(record == dict(path=str(path),sha256=b.sha(path),global_update=local,phase_update=324+local,
               cumulative_update=372+local,formal_comparison_endpoint=(local==60),training_eligible=False,promoted=False,automatic_selection=False)
               and b.read(str(path)+'.json') == record, 'integrity file/sidecar identity differs')
    resources = b.worker_resources(out,strict=True)
    b.need(resources['samples'] > 0 and resources['peak_rss_bytes'] <= worker['peak_rss_bytes'] <= b.LIMITS['rss_bytes']
           and resources['peak_mps_driver_bytes'] <= worker['peak_mps_driver_bytes'] <= b.LIMITS['mps_bytes'], 'sampled RSS/MPS limits differ')
    report.update(deaths=deaths,practice_cutoffs=cutoffs,ordinary_caps=ordinary_caps,
        integrity_files_checked=5,embedded_checkpoint_audit='not performed; parent must audit identities/counters/LR/full vector',
        status='completed_JSON_and_hash_checks_pending_parent_terminal_audit',automatic_promotion=False)
    return report
