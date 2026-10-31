"""Actual CUDA0/420/PPO session; imported only by the authorized remote worker."""
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


class LiveSession:
    fixture_only = False

    def __init__(self, reg, job, out, guard):
        from native_build import verify_certificate, verify_loaded
        certificate = verify_certificate(reg)  # Before importing the extension.
        sys.path.insert(0, reg['runtime_root'])
        import torch
        import numpy as np
        import dodge_rl as native
        import dodge_rl._native as extension
        from importlib.machinery import ExtensionFileLoader
        from dodge_rl import ppo, checkpoints as ckpt, seeded_training as adapter_module
        from dodge_rl.models.teacher import OmniscientEntityTeacher
        from dodge_rl.models.ray_teacher import RayGeometryTeacher
        from dodge_rl.ray_migration import migrate_adam
        verify_loaded(certificate)
        from numpy._core import _multiarray_umath
        for name,path in dict(python=sys.executable,torch_python=torch.__file__,torch_native=torch._C.__file__,
                             numpy_python=np.__file__,numpy_native=_multiarray_umath.__file__).items():
            c.need(dict(path=str(c.Path(path).resolve()),sha256=c.sha(path))==certificate['package_origins'][name],
                   'Package binary origin changed since build admission: '+name)
        c.need(native.VecDodgeEnv.__module__ == 'dodge_rl._native', 'Native constructor type origin differs')
        c.need(native.VecDodgeEnv is extension.VecDodgeEnv and type(native.VecDodgeEnv) is type
               and isinstance(extension.__loader__,ExtensionFileLoader)
               and str(c.Path(extension.__file__).resolve())==certificate['native_binary'],
               'Imported native extension loader/type identity differs')
        from receipts import write_stage
        write_stage(out/'runtime-import.json',reg,'runtime_import','complete',job=job['id'],
            native_games=0,training_frames=0,trained_weights_saved=False,constructor_calls=0,
            binary_sha256=c.sha(extension.__file__),module_origin=extension.__file__,
            constructor_type_module=native.VecDodgeEnv.__module__,
            Python=sys.version,NumPy=np.__version__,device_index=0)
        self.torch, self.ppo, self.ckpt, self.reg, self.job, self.out = torch, ppo, ckpt, reg, job, out
        self.device = torch.device('cuda', 0)
        c.need(torch.cuda.is_available(), 'CUDA0 unavailable')
        c.need(torch.cuda.get_device_name(self.device).startswith('NVIDIA A100'), 'Registered A100 unavailable')
        torch.set_num_threads(reg['threads']); torch.set_num_interop_threads(1)
        torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
        torch.set_float32_matmul_precision('highest')
        torch.cuda.set_per_process_memory_fraction(min(1., reg['allocator_bytes'] /
            torch.cuda.get_device_properties(self.device).total_memory), self.device)
        seeds = reg['replicas'][job['replica']]
        torch.random.default_generator.manual_seed(seeds['constructor_seed'])
        state = ckpt.load_checkpoint(c.Path(reg['checkpoint_path']), expected_sha256=reg['checkpoint_sha256'])
        ckpt.require_complete_update(state)
        c.need(fingerprint(state['model']) == reg['model_fingerprint'] and
               fingerprint(state['optimizer']) == reg['adam_fingerprint'], '420 model/Adam differs')
        legacy = OmniscientEntityTeacher(); legacy.load_state_dict(state['model'], strict=True)
        self.model = RayGeometryTeacher(legacy, branch_seed=seeds['branch_seed']) if job['arm']=='rays' else legacy
        g = torch.zeros(1,1,14); g[:,:,4] = 1
        arrays = (g, torch.zeros(1,80,16), torch.zeros(1,80,dtype=torch.int64), torch.zeros(1,80,dtype=torch.bool))
        with torch.no_grad():
            CPU_reference, CPU_candidate = legacy(*arrays), self.model(*arrays)
        c.need(all(torch.equal(getattr(CPU_reference,k),getattr(CPU_candidate,k)) for k in ('logits','values','latent')),
               'CPU warm-start zero-gate parity differs')
        self.model.to(self.device, dtype=torch.float32)
        self.optimizer, mapping = migrate_adam(state['optimizer'], legacy, self.model,
            learning_rate=reg['ppo']['learning_rate'], adam_eps=reg['ppo']['adam_eps'])
        with torch.no_grad():
            same_device = legacy(*(x.to(self.device) for x in arrays))
            candidate = self.model(*arrays) if job['arm']=='rays' else self.model(*(x.to(self.device) for x in arrays))
        c.need(all(torch.equal(getattr(same_device,k),getattr(candidate,k)) for k in ('logits','values','latent')),
               'CUDA0 warm-start zero-gate parity differs')
        differences = {}
        for key in ('logits','values','latent'):
            left, right = getattr(CPU_reference,key), getattr(same_device,key).cpu()
            differences[key] = float((left-right).abs().max())
            c.need(torch.allclose(left,right,atol=2e-5,rtol=2e-5), 'CPU/CUDA numerical parity differs: '+key)
        for parameter in legacy.parameters():
            c.need(all(self.optimizer.state[parameter][key].device == self.device for key in ('exp_avg','exp_avg_sq')),
                   'Migrated Adam moment device differs')
        verify_loaded(certificate); guard()
        c.save(out/'migration.json', dict(mapping, device='cuda',device_index=0,
            CPU_zero_gate_exact=True,CUDA_zero_gate_exact=True,CPU_CUDA_differences=differences,
            CPU_CUDA_atol=2e-5,CPU_CUDA_rtol=2e-5, trained_weights_saved=False,
            source_model=reg['model_fingerprint'],source_adam=reg['adam_fingerprint']))
        del state; gc.collect()
        random.seed(seeds['python_seed']); np.random.seed(seeds['numpy_seed'])
        torch.random.default_generator.manual_seed(seeds['torch_cpu_seed'])
        # Preserve the old numeric replica root, while declaring the new backend.
        with torch.cuda.device(self.device): torch.cuda.manual_seed(seeds['torch_mps_seed'])
        pool, strata, streams, self.stream_digest = c.build_streams(reg,job['replica'])
        c.need(self.stream_digest == seeds['stream_sha256'], 'Paired training stream differs')
        guard(); verify_loaded(certificate)
        env = native.VecDodgeEnv(batch_size=reg['envs'],action_repeat=1,difficulty=2,
            patterns_enabled=True,powerups_enabled=True,raw_frame_cap=18000,
            num_threads=reg['threads'],chunk_size=8,render_pixels=False,auxiliary_targets=False,
            seeds_by_slot=streams,initial_episode_indices=[0]*reg['envs'],
            excluded_seed_ranges=[tuple(x) for x in reg['exclusions']])
        c.need(type(env) is native.VecDodgeEnv, 'Native environment type differs')
        self.adapter = adapter_module.SeededTrainingAdapter(env,seeds_by_slot=streams,
            components_by_slot=[['uniform']*len(x) for x in streams],strata_by_seed=strata,
            training_pool_values=pool,exclusions=reg['exclusions'],rollout_steps=reg['rollout'],
            gameplay_frame_target=reg['frame_target'])
        self.events = c.Journal(out/'native-events.jsonl'); self.adapter.event_sink = self.events.emit
        self.events.emit(dict(kind='initial_assignments',assignments=self.adapter.assignment_events))
        self.config = ppo.PPOConfig(**dict(reg['ppo'],**reg['arms'][job['arm']]))
        self.prepared = PreparedUpdates(self.model,self.optimizer,self.adapter,self.config,ppo,reg,self.device)
        from update_telemetry import Recorder, JsonlSink
        self.recorder = Recorder(job['id'],1); self.telemetry = JsonlSink(out/'updates.jsonl')
        self.peaks = dict(peak_rss_bytes=0,peak_cuda_reserved_bytes=0,peak_cuda_allocated_bytes=0)

    def resources(self):
        from dodge_rl.device_runtime import peak_rss_bytes
        values = dict(peak_rss_bytes=peak_rss_bytes(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
            peak_cuda_reserved_bytes=int(self.torch.cuda.max_memory_reserved(self.device)),
            peak_cuda_allocated_bytes=int(self.torch.cuda.max_memory_allocated(self.device)))
        for key,value in values.items(): self.peaks[key] = max(self.peaks[key],value)
        c.need(self.peaks['peak_rss_bytes'] < self.reg['rss_bytes'] and
               self.peaks['peak_cuda_reserved_bytes'] < self.reg['cuda_driver_bytes'], 'Worker RSS/Torch reserved cap')
        return dict(self.peaks)

    def step(self, update, guard):
        from update_telemetry import instrument_update
        captured = []; original = self.ppo.compute_gae
        def probe(*args,**kwargs):
            result = original(*args,**kwargs); captured.append((result,tuple(x.clone() for x in result))); return result
        if update <= self.reg['prefix_updates']: self.ppo.compute_gae = probe
        try:
            returned = instrument_update(self.prepared,self.ppo,self.recorder,self.telemetry,
                resource_snapshot=self.resources,check_guard=guard)
            c.need(all(a is b for a,b in zip(returned,self.prepared.last_result)), 'Telemetry replaced PPO returns')
            if update <= self.reg['prefix_updates']:
                c.need(len(captured)==1 and all(self.torch.equal(a,b) for a,b in zip(*captured[0])), 'Passive GAE identity differs')
        finally: self.ppo.compute_gae = original
        self.torch.cuda.synchronize(self.device); self.events.sync()
        return dict(passive_GAE_return_identity=True,**self.counts())

    def counts(self):
        return dict(training_frames=self.adapter.gameplay_frames, completed_updates=self.adapter.completed_updates,
                    native_games=self.reg['envs']+self.adapter.reset_count,
                    actual_startup_frames=self.adapter.initial_startup_frames+self.adapter.reset_startup_frames,
                    observed_native_vectors=self.adapter.observed_native_steps,budget_reached=self.adapter.budget_reached)

    def checkpoint(self,path,update):
        state = dict(schema='dodge_colab_training_checkpoint_v1',job=self.job,
            registration_sha256=self.reg['registration_sha256'],**self.counts(),
            model=self.ckpt._cpu_copy(self.model.state_dict()),optimizer=self.ckpt._cpu_copy(self.optimizer.state_dict()),
            rng=self.ckpt.capture_rng(self.device),adapter=self.adapter.snapshot(),
            full_environment_state_captured=False,automatic_resume_authorized=False,
            training_eligible=False,promoted=False,model_fingerprint=fingerprint(self.model.state_dict()),
            adam_fingerprint=fingerprint(self.optimizer.state_dict()))
        digest = c.publish(path,lambda f:self.torch.save(state,f))
        return dict(update=update,filename=path.name,sha256=digest,
                    model_fingerprint=state['model_fingerprint'],adam_fingerprint=state['adam_fingerprint'])

    def failure(self,error):
        return dict(**failure_observations(self.prepared),player_geometry_failure=geometry_failure(error),progress=self.prepared.progress)

    def close(self):
        self.telemetry.close(); self.events.close()

