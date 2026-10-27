"""Paired study loop using the exact R5 transition and concrete runtime adapter."""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import random
import resource
import sys
import time

from attempt_claim import AttemptClaim
from fingerprints import fingerprint
import driver_binding as binding
import contracts as c
from runtime_adapter import RuntimeAdapter
import transition


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def emit(stream, value):
    stream.write(json.dumps(value, sort_keys=True, allow_nan=False)+'\n')
    stream.flush()


def cache_check(reg):
    policy = reg['import_policy']
    c.need(set(policy) == {'pycache_prefix','dont_write_bytecode'} and policy['dont_write_bytecode'] is True, 'import policy differs')
    path = Path(policy['pycache_prefix'])
    c.need(path.is_absolute() and path.is_dir() and not any(path.iterdir()), 'registered cache must exist empty')
    c.need(sys.dont_write_bytecode and sys.pycache_prefix == str(path) and os.environ.get('PYTHONPYCACHEPREFIX') == str(path), 'process cache policy differs')


class Guard:
    def __init__(self, reg, adapter, started, resources):
        self.reg, self.adapter, self.started, self.resources = reg, adapter, started, resources
        self.peak_rss = self.peak_mps = 0

    def check(self, finalizing=False):
        elapsed = time.monotonic()-self.started
        c.need(elapsed <= self.reg['limits']['total_seconds' if finalizing else 'work_seconds'], 'registered wall limit exceeded')
        rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        mps = int(self.adapter.torch.mps.driver_allocated_memory())
        self.peak_rss, self.peak_mps = max(self.peak_rss,rss), max(self.peak_mps,mps)
        c.need(rss <= self.reg['limits']['rss_bytes'] and mps <= self.reg['limits']['mps_bytes'], 'registered memory limit exceeded')
        c.need(c.read(self.reg['state_path']).get('active_long_campaign') == self.reg['expected_lease'], 'parent lease changed')
        emit(self.resources, dict(elapsed_seconds=elapsed,rss_bytes=rss,mps_driver_bytes=mps))


def run_transition(reg, adapter):
    """No callbacks supplied by CLI callers; accepted R5 owns the only restore."""
    c.need(type(adapter) is RuntimeAdapter, 'concrete runtime adapter required')
    if Path(reg['attempt_claim_path']).exists():
        raise FileExistsError('fixed transition attempt already spent')
    adapter.bootstrap()
    seeds = reg['vector']['seeds']
    record = dict(run_id=reg['run_id'],study_id=c.STUDY,replica=reg['replica'],arm=reg['arm'],
                  vector_sha256=reg['vector']['vector_sha256'],parent_checkpoint_sha256=c.references.ACCEPTED_CHECKPOINT_SHA256)
    result = transition.transition(session=transition.TransitionSession(),
        attempt_claim=AttemptClaim(reg['attempt_claim_path'],record),backend=reg['backend'],seeds=seeds,
        pair=dict(pair_id=reg['pair_id'],A=dict(seeds),B=dict(seeds)),
        verify_trusted_source=adapter.source,restore_trusted=adapter.callbacks['restore_trusted'],
        model=adapter.model,optimizer=adapter.optimizer,rng_capture=adapter.callbacks['rng_capture'],
        pinned_rng_reference=reg['reference'],python_api=random,numpy_api=adapter.np.random,torch_api=adapter.torch,
        pair_id=reg['pair_id'],arm=reg['arm'],study_id=c.STUDY,replica=reg['replica'],
        torch_version=reg['runtime_versions']['torch'],run_id=reg['run_id'])
    # Validate actual R5 return; it deliberately has no generic status field.
    c.need(result['parent_fingerprints'] == transition.EXPECTED_PARENT
           and result['fingerprint_contract_status'] == 'concrete state_dict fingerprints verified'
           and result['seed_vector'] == seeds and result['vector_sha256'] == reg['vector']['vector_sha256']
           and result['new_controller']['first_update'] == 373 and result['new_controller']['last_update'] == 432,
           'R5 transition evidence differs')
    raw = adapter.callbacks['rng_capture']()
    c.need(type(raw) is dict and set(raw) == binding.RAW_RNG_KEYS
           and raw['numpy_generator'] is None and raw['sampling_backend'] == 'torch_global_mps',
           'post-reseed raw RNG binding differs')
    c.need(fingerprint(raw['torch_cpu']) == result['seed_evidence']['torch_cpu_rng_state_sha256']
           and fingerprint(raw['torch_mps']) == result['seed_evidence']['torch_mps_rng_state_sha256'],
           'post-reseed capture differs from measured CPU/MPS reference')
    c.need(fingerprint(raw['python']) == fingerprint(random.Random(seeds['python_random_seed']).getstate())
           and fingerprint(raw['numpy_global']) == fingerprint(adapter.np.random.RandomState(seeds['numpy_global_seed']).get_state()),
           'post-reseed Python/NumPy readback differs from scratch seeded states')
    c.need(fingerprint(adapter.model.state_dict()) == result['post_lr_fingerprints']['model']
           and fingerprint(adapter.optimizer.state_dict()) == result['post_lr_fingerprints']['Adam'],
           'post-transition learner binding differs')
    result['adapter_post_reseed_raw_rng_sha256'] = fingerprint(raw)
    result['adapter_post_reseed_components'] = {key:fingerprint(value) for key,value in raw.items()}
    result['adapter_bootstrap'] = dict(constructor_seed_applied_before_transition_claim=True,
        constructor_seed=seeds['constructor_init_seed'],model_and_Adam_constructed_before_transition_claim=True,
        accepted_state_restored_by_R5_only=True,bootstrap_is_not_accepted_state_restore=True)
    return result


def study_loop(reg, adapter, out, guard, registration_sha, started, result=None):
    """Preserve raw metrics, progress, episode events and complete candidates."""
    adapter.make_env()
    counters = dict(updates=0,optimizer_steps=0,environment_decisions=0,raw_frames=0)
    progress = dict(complete=True,in_update=False,completed_updates=0)
    saved = []
    result = {} if result is None else result
    result.update(counters=counters,update_progress=progress,candidates=saved)
    actor = critic = False
    with (out/'training-episodes.jsonl').open('x') as episodes, (out/'training-metrics.jsonl').open('x') as metrics:
        for abandoned in adapter.parent['abandoned_current_episodes']:
            emit(episodes,dict(kind='abandoned_parent_episode',reason='fresh_environment_at_saved_next_episode_index',parent_checkpoint_sha256=c.references.ACCEPTED_CHECKPOINT_SHA256,info=abandoned))
        emit(episodes,dict(kind='initial',info=adapter.env.episode_info(),batch_info=adapter.env.batch_info()))
        for local in range(1,61):
            guard.check()
            lr = transition.controller_lr(reg['arm'],372+local)
            for group in adapter.optimizer.param_groups:
                group['lr'] = lr
            c.need(all(group['lr'] == lr for group in adapter.optimizer.param_groups), 'effective LR differs')
            def journal_collection_events(completed, resets):
                # Synchronous, worker-owned durable prefix. Never replay a failed
                # write or journal again after adapter.update returns.
                for event in adapter.runner['ordered_episode_events'](completed,resets,324+local):
                    emit(episodes,event)
                    os.fsync(episodes.fileno())
            value, collection = adapter.update(guard.check,progress,journal_collection_events)
            c.need(progress.get('complete') is True and progress.get('in_update') is False, 'incomplete update cannot advance counters')
            progress['completed_updates'] = local
            counters['updates'] = local
            result['updates'] = local
            counters['optimizer_steps'] += value['optimizer_steps']
            counters['environment_decisions'] += collection.batch.actions.numel()
            counters['raw_frames'] += int(collection.batch.elapsed_raw_frames.sum().item())
            actor |= value['actor_grad_norm'] > 0
            critic |= value['critic_grad_norm'] > 0
            cumulative = adapter.runner['continuation_cumulative_counters'](adapter.context['parent']['candidate_cumulative_counters'],counters)
            c.need(cumulative['updates'] == 372+local, 'cumulative update differs')
            emit(metrics,dict(phase_update=324+local,local_update=local,cumulative_update=372+local,effective_learning_rate=lr,
                              metrics=value,counters=dict(counters),cumulative_counters=cumulative,update_progress=dict(progress),elapsed_seconds=time.monotonic()-started))
            if local in c.SCHEDULE['candidate_local_updates']:
                candidate = adapter.candidate(out,local,counters,progress,registration_sha,started)
                save(out/(candidate['checkpoint']+'.json'),candidate)
                saved.append(candidate)
            guard.check()
    c.need(actor and critic, 'nonzero actor/critic gradient evidence missing')
    return dict(status='completed',updates=60,counters=counters,update_progress=dict(progress),cumulative_counters=cumulative,
                final_resume_next_episode_indices=adapter.env.batch_info()['next_episode_indices'],candidates=saved,
                training_eligible=False,promoted=False,automatic_selection=False,evaluated_updates=[],
                claim_limit='three exploratory pairs; no confirmatory claim')


def execute(reg, context, registration_sha, started):
    # No injected adapter parameter. CLI can only construct this exact class.
    cache_check(reg)
    out = Path(reg['output'])
    out.mkdir()  # Refuse an existing destination; no retry/repair/replace.
    result = dict(status='failed',updates=0,training_eligible=False,promoted=False,automatic_selection=False)
    adapter = guard = resources = None
    try:
        adapter = RuntimeAdapter(reg,context)
        resources = (out/'resources.jsonl').open('x')
        guard = Guard(reg,adapter,started,resources)
        guard.check()
        evidence = run_transition(reg,adapter)
        save(out/'entry-restoration.json',evidence)
        result = study_loop(reg,adapter,out,guard,registration_sha,started,result)
    except BaseException as error:
        result.update(status='failed',first_failure=repr(error))
    finally:
        try:
            if adapter is not None:
                adapter.close()
            if guard is not None:
                guard.check(finalizing=True)
                result.update(peak_rss_bytes=guard.peak_rss,peak_mps_driver_bytes=guard.peak_mps)
            cache_check(reg)
        except BaseException as error:
            result.update(status='failed',finalization_error=repr(error))
        if resources is not None:
            resources.close()
        result.update(run_id=reg['run_id'],registration_sha256=registration_sha,elapsed_seconds=time.monotonic()-started)
        save(out/'worker-result.json',result)
    return 0 if result['status'] == 'completed' else 1
