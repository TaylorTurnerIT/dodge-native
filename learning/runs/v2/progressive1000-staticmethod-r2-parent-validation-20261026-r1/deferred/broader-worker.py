"""Concrete single-run worker. Only worker_cli's external parent gates may enter."""
from __future__ import annotations
import copy
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import random
import resource
import signal
import sys
import time

from attempt_claim import AttemptClaim
from fingerprints import fingerprint
import driver_binding as binding
import contracts as c
from runtime_adapter import RuntimeAdapter
import transition


def emit(stream,value):
    stream.write(json.dumps(value,sort_keys=True,allow_nan=False)+'\n')
    stream.flush()
    os.fsync(stream.fileno())


def save(path,value):
    with Path(path).open('x') as stream:
        json.dump(value,stream,sort_keys=True,indent=2,allow_nan=False)
        stream.write('\n');stream.flush();os.fsync(stream.fileno())
    directory=os.open(Path(path).parent,os.O_RDONLY)
    try: os.fsync(directory)
    finally: os.close(directory)


class Guard:
    def __init__(self,reg,adapter,started,resources):
        self.reg,self.adapter,self.started,self.resources=reg,adapter,started,resources
        self.peak_rss=self.peak_mps=0
        self.last_sample=float('-inf')

    def check(self,finalizing=False):
        elapsed=time.monotonic()-self.started
        c.need(elapsed<=self.reg['limits']['total_seconds' if finalizing else 'work_seconds'], 'registered wall limit exceeded')
        rss=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*(1 if sys.platform=='darwin' else 1024)
        mps=int(self.adapter.torch.mps.driver_allocated_memory()) if self.reg['backend']=='mps' else 0
        self.peak_rss,self.peak_mps=max(self.peak_rss,rss),max(self.peak_mps,mps)
        c.need(rss<=self.reg['limits']['rss_bytes'] and mps<=self.reg['limits']['mps_bytes'], 'registered memory limit exceeded')
        c.need(c.read(self.reg['state_path']).get('active_long_campaign')==self.reg['expected_lease'],'parent lease changed')
        boundary=self.adapter.boundary
        if boundary is not None:
            raw=boundary.initial_startup_frames+boundary.observed_native_frames+boundary.returned_reset_startup_frames
            c.need(raw<=self.reg['limits']['raw_frames'],'registered total raw-frame limit exceeded')
            resets=sum(len(r['indices']) for r in boundary.returned_resets)
            c.need(resets<=self.reg['limits']['resets'],'registered reset limit exceeded')
        if elapsed-self.last_sample>=.5 or finalizing:
            emit(self.resources,dict(elapsed_seconds=elapsed,rss_bytes=rss,mps_driver_bytes=mps))
            self.last_sample=elapsed


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


def study_loop(reg,adapter,out,guard,registration_sha,started,result):
    adapter.make_env()
    counters=dict(updates=0,optimizer_steps=0,environment_decisions=0,raw_frames=0)
    result.update(counters=counters,integrity_checkpoints=[],evaluated_updates=[],
                  training_eligible=False,promoted=False,automatic_selection=False)
    with (out/'training-events.jsonl').open('x') as events, (out/'training-metrics.jsonl').open('x') as metrics:
        # The sink journals returned native work and completed/reset identities
        # before later bootstrap/guard/PPO/diagnostic failures can occur.
        adapter.boundary.event_sink=lambda event:emit(events,event)
        emit(events,dict(kind='initial',info=adapter.env.episode_info(),batch_info=adapter.env.batch_info(),
                         assignments=copy.deepcopy(adapter.boundary.assignment_events),
                         parent_abandoned_episodes=adapter.parent['abandoned_current_episodes']))
        for local in range(1,61):
            guard.check()
            c.need(all(g['lr']==3e-5 for g in adapter.optimizer.param_groups),'constant LR changed after restore')
            progress={}
            result['active_update']=local
            def before_ppo(completed,resets):
                emit(events,dict(kind='collection_complete_before_PPO',global_update=local,
                    completed=completed,resets=resets,snapshot=adapter.snapshot()))
            value,collection,boundary=adapter.update(guard.check,progress,before_ppo)
            c.need(progress.get('complete') is True and progress.get('in_update') is False,'incomplete update cannot advance counters')
            counters['updates']=local
            counters['optimizer_steps']+=value['optimizer_steps']
            counters['environment_decisions']+=collection.batch.actions.numel()
            counters['raw_frames']+=int(collection.batch.elapsed_raw_frames.sum().item())
            result.update(updates=local,update_progress=copy.deepcopy(progress))
            emit(metrics,dict(global_update=local,phase_update=324+local,cumulative_update=372+local,
                effective_learning_rate=3e-5,metrics=value,counters=dict(counters),
                progress=progress,scheduler_boundary=boundary,elapsed_seconds=time.monotonic()-started))
            if local in c.SCHEDULE['integrity_local_updates']:
                checkpoint=adapter.integrity_checkpoint(out,local,counters,registration_sha)
                save(out/(Path(checkpoint['path']).name+'.json'),checkpoint)
                result['integrity_checkpoints'].append(checkpoint)
            guard.check()
        c.need(counters['updates']==60 and counters['environment_decisions']==983040,'fixed global60 transition budget differs')
        result.update(status='completed',formal_comparison_endpoint=result['integrity_checkpoints'][-1],
            final_resume_next_episode_indices=adapter.env.batch_info()['next_episode_indices'],
            curriculum_snapshot=adapter.snapshot(),cumulative_update=432,phase_update=384,
            interpretation='descriptive pilot only; parent comparison required; no automatic promotion')
    return result


@contextmanager
def cancellation_signals():
    old={}; stopping=[False]
    def cancel(number,frame):
        if not stopping[0]:
            stopping[0]=True
            raise InterruptedError('signal '+str(number))
    try:
        for number in (signal.SIGTERM,signal.SIGINT):
            old[number]=signal.getsignal(number);signal.signal(number,cancel)
        yield
    finally:
        for number,handler in old.items():signal.signal(number,handler)


def execute(reg,context,registration_sha,started):
    c.cache_check(reg)
    out=Path(reg['output']);out.mkdir()
    result=dict(status='failed',updates=0,training_eligible=False,promoted=False,automatic_selection=False)
    adapter=guard=resources=None
    with cancellation_signals():
        try:
            adapter=RuntimeAdapter(reg,context)
            resources=(out/'resources.jsonl').open('x')
            guard=Guard(reg,adapter,started,resources);guard.check()
            save(out/'entry-restoration.json',run_transition(reg,adapter))
            study_loop(reg,adapter,out,guard,registration_sha,started,result)
        except BaseException as error:
            result.update(status='failed',error=repr(error),comparison_complete=False,no_retry=True)
        finally:
            if adapter is not None:
                try:
                    result['final_snapshot']=adapter.snapshot()
                except BaseException as error:
                    result['snapshot_error']=repr(error)
                try:
                    adapter.close()
                except BaseException as error:
                    result.update(status='failed',cleanup_error=repr(error))
            if guard is not None:
                try:
                    guard.check(finalizing=True)
                except BaseException as error:
                    result.update(status='failed',final_guard_error=repr(error))
                result.update(peak_rss_bytes=guard.peak_rss,peak_mps_driver_bytes=guard.peak_mps)
            if resources is not None:resources.close()
            result.update(run_id=reg['run_id'],registration_sha256=registration_sha,
                          elapsed_seconds=time.monotonic()-started,cleanup_qualification='parent_supervisor_required')
            save(out/'worker-result.json',result)
    return 0 if result['status']=='completed' else 1
