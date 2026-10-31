"""One claimed trajectory; candidate qualification is part of its counted prefix."""
import argparse
import gc
import importlib
import json
import os
import random
import resource
import signal
import sys
import time
import traceback

import common as c
from fingerprints import fingerprint


class PreparedUpdates:
    """One worker session; partial observations never reuse a previous batch."""

    def __init__(self, model, optimizer, adapter, config, ppo, reg, device):
        self.model, self.optimizer, self.adapter = model, optimizer, adapter
        self.config, self.ppo, self.reg, self.device = config, ppo, reg, device
        self.microbatch_size = reg['microbatch']
        self.effective_minibatch_size = reg['effective_minibatch']
        self.progress = {}
        self.attempted_update = None
        self.collection_status = 'not_started'
        self.collected_valid_vectors = self.collected_valid_transitions = None
        self.start_frames = self.start_vectors = None

    def update_once(self, check_guard=None):
        # Reset before *any* check that may fail in a new attempt. A collector
        # that raises has not returned a validated RolloutBatch, even if the
        # adapter already observed some native return costs.
        self.attempted_update = self.adapter.completed_updates + 1
        self.collection_status = 'pre_collection'
        self.collected_valid_vectors = self.collected_valid_transitions = None
        self.start_frames = self.adapter.gameplay_frames
        self.start_vectors = self.adapter.observed_native_steps
        self.progress.clear()
        self.progress.update(in_update=True, complete=False, phase='collection',
                             attempted_update=self.attempted_update)
        c.need(all(g['lr'] == self.config.learning_rate and g['eps'] == self.config.adam_eps
                   for g in self.optimizer.param_groups), 'Adam LR/eps changed')
        self.adapter.begin_update(self.attempted_update)
        self.collection_status = 'collecting'
        try:
            collection = self.ppo.collect_rollout(
                self.model, self.adapter.env, self.reg['rollout'], self.device,
                config=self.config, check_guard=check_guard, boundary_adapter=self.adapter,
                gameplay_frame_budget=self.reg['frame_target'] - self.adapter.gameplay_frames)
        except BaseException:
            self.collection_status = 'interrupted_before_return'
            raise
        self.collected_valid_vectors = int(collection.batch.actions.shape[0])
        self.collected_valid_transitions = int(collection.batch.actions.numel())
        self.collection_status = 'returned_valid_batch'
        self.progress['phase'] = 'optimization'
        metrics = self.ppo.ppo_update(
            self.model, self.optimizer, collection.batch, self.config,
            check_guard=check_guard, progress=self.progress,
            microbatch_size=self.microbatch_size,
            effective_minibatch_size=self.effective_minibatch_size)
        boundary = self.adapter._finish_after_ppo()
        self.collection_status = 'completed_after_ppo'
        self.last_result = collection, metrics, boundary
        return self.last_result


def failure_observations(prepared):
    """Separate returned native costs from a collector's validated batch count.

    An in-flight native call that never returned cannot be counted here. These
    are observations, not proof of every frame executed before a hard kill.
    """
    if prepared is None:
        return dict(attempted_update=None, collection_status='not_started',
            observed_gameplay_frames=None, observed_returned_frames_this_attempt=None,
            observed_returned_vectors_this_attempt=None,
            collected_valid_vectors=None, collected_valid_transitions=None)
    return dict(attempted_update=prepared.attempted_update,
        collection_status=prepared.collection_status,
        observed_gameplay_frames=prepared.adapter.gameplay_frames,
        observed_returned_frames_this_attempt=(None if prepared.start_frames is None else
            prepared.adapter.gameplay_frames - prepared.start_frames),
        observed_returned_vectors_this_attempt=(None if prepared.start_vectors is None else
            prepared.adapter.observed_native_steps - prepared.start_vectors),
        collected_valid_vectors=prepared.collected_valid_vectors,
        collected_valid_transitions=prepared.collected_valid_transitions)


def geometry_failure(error):
    rows=getattr(error,'player_geometry_rows',None)
    if rows is None:return None
    return [dict(row,phase=getattr(error,'phase','unspecified')) for row in rows]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--registration', required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--job', required=True)
    args = parser.parse_args()
    reg = c.load_registration(args.registration, args.sha256)
    job = next(x for x in reg['jobs'] if x['id'] == args.job)
    out = c.HERE / 'outputs' / job['id']
    c.check_lease(reg)
    dispatch = c.read(out / 'dispatch.json')
    c.need(dispatch['worker_expected_job'] == job['id'] and dispatch['parent_pid'] == os.getppid()
           and dispatch['registration_sha256'] == args.sha256, 'Parent launch binding absent')
    c.save(out / 'worker.claimed', dict(pid=os.getpid(), registration_sha256=args.sha256, job=job['id']))
    started = time.monotonic()
    cancelled = False
    torch = None
    telemetry = None
    events = None
    prepared = None
    power_log = None
    peaks = dict(peak_rss_bytes=0, peak_mps_driver_bytes=0)
    last_check = last_power = float('-inf')

    def cancel(*_):
        nonlocal cancelled
        cancelled = True

    signal.signal(signal.SIGTERM, cancel); signal.signal(signal.SIGINT, cancel)

    def guard():
        nonlocal last_check, last_power
        now = time.monotonic()
        c.need(not cancelled and now - started < reg['work_seconds'], 'Cancellation/work deadline')
        if now - last_check >= .25:
            c.check_lease(reg)
            rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            mps = int(torch.mps.driver_allocated_memory()) if torch is not None else 0
            peaks['peak_rss_bytes'] = max(peaks['peak_rss_bytes'], rss)
            peaks['peak_mps_driver_bytes'] = max(peaks['peak_mps_driver_bytes'], mps)
            c.check_worker_resources(reg,rss,mps)
            last_check = now
        if now - last_power >= 5:
            c.record_power(power_log); last_power = now

    try:
        power_log = c.Journal(out / 'power.jsonl')
        guard()
        sys.path.insert(0, reg['runtime_root'])
        torch = importlib.import_module('torch')
        np = importlib.import_module('numpy')
        native = importlib.import_module('dodge_rl')
        ppo = importlib.import_module('dodge_rl.ppo')
        checkpoint_module = importlib.import_module('dodge_rl.checkpoints')
        adapter_module = importlib.import_module('dodge_rl.seeded_training')
        teacher = importlib.import_module('dodge_rl.models.teacher')
        from update_telemetry import Recorder, instrument_update, JsonlSink
        for name, module in list(sys.modules.items()):
            if name == 'dodge_rl' or name.startswith('dodge_rl.'):
                path = str(c.Path(module.__file__).resolve())
                c.need(path in reg['input_pins'] and c.sha(path) == reg['input_pins'][path], 'Unpinned loaded runtime: ' + name)
        c.need(torch.backends.mps.is_available(), 'MPS unavailable')
        torch.set_num_threads(reg['threads']); torch.set_num_interop_threads(1)
        torch.mps.set_per_process_memory_fraction(min(1., reg['allocator_bytes'] / torch.mps.recommended_max_memory()))
        seeds = reg['replicas'][job['replica']]
        torch.manual_seed(seeds['constructor_seed'])
        state = checkpoint_module.load_checkpoint(c.Path(reg['checkpoint_path']), expected_sha256=reg['checkpoint_sha256'])
        checkpoint_module.require_complete_update(state)
        c.need(fingerprint(state['model']) == reg['model_fingerprint'] and fingerprint(state['optimizer']) == reg['adam_fingerprint'], '420 model/Adam differs')
        migration = importlib.import_module('dodge_rl.ray_migration')
        ray_module = importlib.import_module('dodge_rl.models.ray_teacher')
        legacy = teacher.OmniscientEntityTeacher()
        legacy.load_state_dict(state['model'], strict=True)
        model = (ray_module.RayGeometryTeacher(legacy, branch_seed=seeds['branch_seed'])
                 if job['arm'] == 'rays' else legacy)
        # CPU warm-start comparison precedes all learner-device migration.
        g = torch.zeros((1,1,14)); g[:,:,4] = 1
        e = torch.zeros((1,80,16)); t = torch.zeros((1,80), dtype=torch.int64)
        m = torch.zeros((1,80), dtype=torch.bool)
        with torch.no_grad():
            before, after = legacy(g,e,t,m), model(g,e,t,m)
        c.need(all(torch.equal(getattr(before,k),getattr(after,k)) for k in ('logits','values','latent')), 'Warm-start CPU parity differs')
        model.to('mps', dtype=torch.float32)
        optimizer, migration_manifest = migration.migrate_adam(state['optimizer'], legacy, model,
            learning_rate=reg['ppo']['learning_rate'], adam_eps=reg['ppo']['adam_eps'])
        c.need(fingerprint(legacy.state_dict()) == reg['model_fingerprint'], 'Loaded legacy weights differ')
        with torch.no_grad():
            device_data=tuple(x.to('mps') for x in (g,e,t,m))
            before=legacy(*device_data)
            after=model(g,e,t,m) if job['arm']=='rays' else model(*device_data)
            c.need(all(torch.equal(getattr(before,k),getattr(after,k)) for k in ('logits','values','latent')), 'Warm-start MPS parity differs')
        guard()
        c.save(out / 'migration.json', dict(migration_manifest, source_model=reg['model_fingerprint'],
            source_adam=reg['adam_fingerprint'], zero_gate_CPU_parity=True, zero_gate_MPS_parity=True))
        del state; gc.collect()
        random.seed(seeds['python_seed']); np.random.seed(seeds['numpy_seed'])
        torch.manual_seed(seeds['torch_cpu_seed']); torch.mps.manual_seed(seeds['torch_mps_seed'])
        for name, module in list(sys.modules.items()):
            if name == 'dodge_rl' or name.startswith('dodge_rl.'):
                path = str(c.Path(module.__file__).resolve())
                c.need(path in reg['input_pins'] and c.sha(path) == reg['input_pins'][path], 'Unpinned migrated runtime: '+name)
        pool, strata, streams, stream_digest = c.build_streams(reg, job['replica'])
        c.need(stream_digest == seeds['stream_sha256'], 'Paired stream differs')
        env = native.VecDodgeEnv(batch_size=reg['envs'], action_repeat=1, difficulty=2,
            patterns_enabled=True, powerups_enabled=True, raw_frame_cap=18000,
            num_threads=reg['threads'], chunk_size=8, render_pixels=False, auxiliary_targets=False,
            seeds_by_slot=streams, initial_episode_indices=[0] * reg['envs'],
            excluded_seed_ranges=[tuple(x) for x in reg['exclusions']])
        adapter = adapter_module.SeededTrainingAdapter(env, seeds_by_slot=streams,
            components_by_slot=[['uniform'] * len(x) for x in streams], strata_by_seed=strata,
            training_pool_values=pool, exclusions=reg['exclusions'], rollout_steps=reg['rollout'],
            gameplay_frame_target=reg['frame_target'])
        events = c.Journal(out / 'native-events.jsonl'); adapter.event_sink = events.emit
        events.emit(dict(kind='initial_assignments', assignments=adapter.assignment_events))
        config = ppo.PPOConfig(**dict(reg['ppo'], **reg['arms'][job['arm']]))

        prepared = PreparedUpdates(model, optimizer, adapter, config, ppo, reg, 'mps')
        recorder = Recorder(job['id'], 1)
        telemetry = JsonlSink(out / 'updates.jsonl')
        update_times = []
        checkpoints = []
        prefix_passive_checks = []
        setup_seconds = time.monotonic() - started
        for update in range(1, reg['updates'] + 1):
            guard(); begin = time.monotonic()
            captured = []
            original_gae = ppo.compute_gae
            def probe(*a, **kw):
                result = original_gae(*a, **kw)
                captured.append((result, tuple(x.clone() for x in result)))
                return result
            if update <= reg['prefix_updates']:
                ppo.compute_gae = probe
            try:
                returned = instrument_update(prepared, ppo, recorder, telemetry,
                    resource_snapshot=lambda: dict(peaks), check_guard=guard)
                c.need(all(a is b for a, b in zip(returned, prepared.last_result)), 'Telemetry replaced update results')
                if update <= reg['prefix_updates']:
                    c.need(ppo.compute_gae is probe and len(captured) == 1, 'GAE hook/call parity differs')
                    c.need(all(torch.equal(a, b) for a, b in zip(*captured[0])), 'GAE tensors changed')
                    prefix_passive_checks.append(True)
            finally:
                ppo.compute_gae = original_gae
            torch.mps.synchronize(); guard(); events.sync()
            update_times.append(time.monotonic() - begin)
            c.need(adapter.gameplay_frames == update * reg['envs'] * reg['rollout'], 'K1 frame accounting differs')
            if update == reg['prefix_updates']:
                forecast = setup_seconds + 1.2 * max(update_times) * reg['updates'] + reg['IO_reserve_seconds']
                remaining_jobs = len(reg['jobs']) - dispatch['job_index'] - 1
                full_path = (time.monotonic() - dispatch['campaign_started_monotonic']
                    + 1.2 * max(update_times) * (reg['updates'] - update)
                    + reg['IO_reserve_seconds'] + reg['receipt_seconds']
                    + remaining_jobs * (reg['work_seconds'] + reg['receipt_seconds']))
                c.need(full_path < reg['campaign_total_seconds'], 'Full remaining path forecast exceeds global training cap')
                c.need(forecast < reg['work_seconds'], 'Counted prefix forecast exceeds work cap; no resize/retry')
                c.save(out / 'prefix-qualification.json', dict(status='accepted_counted_prefix',
                    updates=update, counted_frames=adapter.gameplay_frames, forecast_seconds=forecast,
                    full_path_forecast_seconds=full_path, valid_partial_vectors=0, actual_K1_frames_per_full_vector=reg['envs'],
                    passive_GAE_and_return_identity_checks=prefix_passive_checks, resources=dict(peaks),
                    limits='Counted single trajectory prefix, not twin-run behavioral parity or full-state resume.'))
            if update in reg['checkpoint_updates']:
                path = out / ('checkpoint-%03d.pt' % update)
                checkpoint = dict(schema='dodge_ray_checkpoint_v1', job=job,
                    registration_sha256=args.sha256, completed_updates=update, gameplay_frames=adapter.gameplay_frames,
                    model=checkpoint_module._cpu_copy(model.state_dict()), optimizer=checkpoint_module._cpu_copy(optimizer.state_dict()),
                    rng=checkpoint_module.capture_rng('mps'), adapter=adapter.snapshot(),
                    full_environment_state_captured=False, automatic_resume_authorized=False,
                    training_eligible=False, checkpoint_role='diagnostic_endpoint_only',
                    promoted=False, model_fingerprint=fingerprint(model.state_dict()), adam_fingerprint=fingerprint(optimizer.state_dict()))
                digest = c.publish(path, lambda f: torch.save(checkpoint, f)); path.chmod(0o444)
                checkpoints.append(dict(update=update, path=str(path), sha256=digest,
                    model_fingerprint=checkpoint['model_fingerprint'], adam_fingerprint=checkpoint['adam_fingerprint']))
                del checkpoint
            print(c.canonical(dict(job=job['id'], update=update, frames=adapter.gameplay_frames,
                                   target=reg['frame_target'], saved_boundary=checkpoints[-1]['update'] if checkpoints else None)).decode(), flush=True)
        telemetry.close(); telemetry = None
        events.close(); events = None
        c.verify_pins(reg); guard()
        with (out / 'updates.jsonl').open() as f:
            rows = [json.loads(line) for line in f]
        counts = c.validate_telemetry(rows, reg, job)
        c.need(counts['frames'] == reg['frame_target'] and adapter.budget_reached, 'Final target absent')
        power_log.close(); power_log = None
        c.save(out / 'result.json', dict(schema='dodge_ray_worker_result_v1', status='complete', job=job,
            registration_sha256=args.sha256, counts=counts, checkpoints=checkpoints,
            prefix_sha256=c.sha(out / 'prefix-qualification.json'), telemetry_sha256=c.sha(out / 'updates.jsonl'),
            native_journal_sha256=c.sha(out / 'native-events.jsonl'), resources=dict(peaks),
            elapsed_seconds=time.monotonic() - started, actual_startup_frames=adapter.initial_startup_frames + adapter.reset_startup_frames,
            consumed_seeds=sorted(adapter.consumed_actual_seeds), stream_sha256=stream_digest,
            passive_power_sha256=c.sha(out / 'power.jsonl'),
            source_checkpoint_unchanged=True, migration_sha256=c.sha(out / 'migration.json'), promoted=False, evaluation_games=0))
        return 0
    except BaseException as error:
        if power_log is not None: power_log.close()
        if telemetry is not None: telemetry.close()
        if events is not None: events.close()
        c.save(out / 'first-failure.json', dict(status='first_failure_preserved_lease_held',
            job=job['id'], error=repr(error), traceback=traceback.format_exc(), resources=dict(peaks),
            **failure_observations(prepared),player_geometry_failure=geometry_failure(error),
            progress={} if prepared is None else prepared.progress, elapsed_seconds=time.monotonic() - started))
        raise


if __name__ == '__main__':
    sys.exit(main())
