"""Exactly one disposable update per registered profiling cell; no weights saved."""
import argparse
from collections import defaultdict
import hashlib
import importlib
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cell', required=True, type=int)
    args = parser.parse_args()
    reg = read(HERE / 'S1-registration.json')
    cell = reg['cells'][args.cell]
    output = HERE / 'S1-output' / ('cell-%02d.json' % args.cell)
    claim = output.with_suffix('.claimed')
    with claim.open('x') as stream:
        json.dump(dict(pid=os.getpid(), cell=args.cell, registration_sha256=sha(HERE / 'S1-registration.json')), stream)
    for path, digest in reg['input_pins'].items():
        if sha(path) != digest:
            raise ValueError('Pinned input differs: ' + path)
    if read(reg['state_path']).get('active_long_campaign') != reg['expected_lease']:
        raise ValueError('Exact profiling lease missing')
    started = time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('cell wall limit')))
    signal.alarm(reg['cell_wall_seconds'])
    torch = None
    peaks = dict(rss_bytes=0, mps_driver_bytes=0)
    counters = defaultdict(float)
    status = 'failed'
    result = dict(cell=cell, cell_index=args.cell, disposable_updates_only=True,
                  saved_weights=False, source_checkpoint_sha256=reg['checkpoint_sha256'])
    try:
        sys.path.insert(0, reg['runtime_root'])
        torch = importlib.import_module('torch')
        native = importlib.import_module('dodge_rl')
        ppo = importlib.import_module('dodge_rl.ppo')
        adapter_module = importlib.import_module('dodge_rl.seeded_training')
        teacher = importlib.import_module('dodge_rl.models.teacher')
        for name, module in tuple(sys.modules.items()):
            if name == 'dodge_rl' or name.startswith('dodge_rl.'):
                path = str(Path(module.__file__).resolve())
                if path not in reg['input_pins'] or sha(path) != reg['input_pins'][path]:
                    raise ValueError('Unpinned loaded module: ' + name)
        torch.set_num_threads(cell['threads'])
        torch.set_num_interop_threads(1)
        torch.manual_seed(reg['controller_seed'])
        torch.mps.manual_seed(reg['controller_seed'])
        torch.mps.set_per_process_memory_fraction(min(1.0, reg['allocation_limit_bytes'] / torch.mps.recommended_max_memory()))

        def guard():
            rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            mps = int(torch.mps.driver_allocated_memory())
            peaks['rss_bytes'] = max(peaks['rss_bytes'], rss)
            peaks['mps_driver_bytes'] = max(peaks['mps_driver_bytes'], mps)
            if rss >= reg['resource_limit_bytes'] or mps >= reg['resource_limit_bytes']:
                raise RuntimeError('Separate6GiB resource guard reached')
            if time.monotonic() - started > reg['cell_wall_seconds']:
                raise TimeoutError('Cell work limit')

        def sync(device):
            if str(device).startswith('mps'):
                torch.mps.synchronize()

        guard()
        checkpoint = torch.load(reg['checkpoint_path'], map_location='cpu', weights_only=False)
        inference = teacher.OmniscientEntityTeacher().to(cell['inference_device'])
        inference.load_state_dict(checkpoint['model'], strict=True)
        learner = (inference if cell['inference_device'] == 'mps' else
                   teacher.OmniscientEntityTeacher().to('mps'))
        if learner is not inference:
            learner.load_state_dict(checkpoint['model'], strict=True)
        optimizer = torch.optim.Adam(learner.parameters(), lr=3e-5, eps=1e-5)
        optimizer.load_state_dict(checkpoint['optimizer'])
        if any(group['lr'] != 3e-5 for group in optimizer.param_groups):
            raise ValueError('Checkpoint optimizer recipe differs')
        del checkpoint
        pool_doc = read(reg['pool_path'])
        pool = sorted(row['seed'] for row in pool_doc['seeds'])
        strata = {row['seed']: row['stratum'] for row in pool_doc['seeds']}
        # Only previously consumed training seeds. No new cohort or training seed.
        streams = [[pool[(slot + episode * cell['envs']) % len(pool)]
                    for episode in range(cell['rollout_steps'] + 1)] for slot in range(cell['envs'])]
        raw_env = native.VecDodgeEnv(batch_size=cell['envs'], action_repeat=4, difficulty=2,
            patterns_enabled=True, powerups_enabled=True, raw_frame_cap=18000,
            num_threads=cell['threads'], chunk_size=8, render_pixels=False, auxiliary_targets=False,
            seeds_by_slot=streams, initial_episode_indices=[0] * cell['envs'],
            excluded_seed_ranges=[tuple(pair) for pair in reg['excluded_seed_ranges']])
        adapter = adapter_module.SeededTrainingAdapter(raw_env, seeds_by_slot=streams,
            components_by_slot=[['uniform'] * len(row) for row in streams], strata_by_seed=strata,
            training_pool_values=pool, exclusions=reg['excluded_seed_ranges'], rollout_steps=cell['rollout_steps'])

        class TimedEnv:
            def __getattr__(self, name):
                return getattr(raw_env, name)

            def step(self, actions):
                begin = time.perf_counter()
                value = raw_env.step(actions)
                counters['native_step_plus_observation_export'] += time.perf_counter() - begin
                return value

            def reset_done(self, indices):
                begin = time.perf_counter()
                value = raw_env.reset_done(indices)
                counters['native_reset_plus_observation_export'] += time.perf_counter() - begin
                return value

        original_observation = ppo._observation_tensors
        original_output = ppo._model_output
        original_gae = ppo.compute_gae
        phase = 'collection'

        def observation(*a, **kw):
            begin = time.perf_counter()
            value = original_observation(*a, **kw)
            counters[phase + '_observation_validation_and_copy'] += time.perf_counter() - begin
            return value

        def model_output(model, tensors, device):
            sync(device)
            begin = time.perf_counter()
            transferred = {name: tensor.to(device) for name, tensor in tensors.items()}
            sync(device)
            counters[phase + '_host_device_transfer'] += time.perf_counter() - begin
            begin = time.perf_counter()
            value = original_output(model, transferred, device)
            sync(device)
            counters[phase + '_model_forward_and_output_validation'] += time.perf_counter() - begin
            return value

        def gae(*a, **kw):
            begin = time.perf_counter()
            value = original_gae(*a, **kw)
            counters['gae'] += time.perf_counter() - begin
            return value

        ppo._observation_tensors, ppo._model_output, ppo.compute_gae = observation, model_output, gae
        config = ppo.PPOConfig(learning_rate=3e-5)
        guard()
        adapter.begin_update(1)
        sync(cell['inference_device'])
        begin = time.perf_counter()
        collection = ppo.collect_rollout(inference, TimedEnv(), cell['rollout_steps'],
            cell['inference_device'], config=config, check_guard=guard, boundary_adapter=adapter)
        sync(cell['inference_device'])
        counters['collection_total'] = time.perf_counter() - begin
        phase = 'ppo'
        sync('mps')
        begin = time.perf_counter()
        metrics = ppo.ppo_update(learner, optimizer, collection.batch, config,
                                 check_guard=guard, microbatch_size=512, effective_minibatch_size=512)
        sync('mps')
        counters['ppo_total_including_gae'] = time.perf_counter() - begin
        counters['ppo_validation_epochs_and_metrics_excluding_gae'] = counters['ppo_total_including_gae'] - counters['gae']
        adapter._finish_after_ppo()
        guard()
        raw_frames = int(collection.batch.elapsed_raw_frames.sum().item())
        total = counters['collection_total'] + counters['ppo_total_including_gae']
        accounted = sum(counters.get(key, 0) for key in ['native_step_plus_observation_export',
            'native_reset_plus_observation_export', 'collection_observation_validation_and_copy',
            'collection_host_device_transfer', 'collection_model_forward_and_output_validation'])
        counters['collection_other_python_sampling_auditing_storage'] = counters['collection_total'] - accounted
        if counters['collection_other_python_sampling_auditing_storage'] < 0:
            raise ValueError('Timing partition overlaps')
        result.update(status='complete', timings_seconds=dict(counters), resources=peaks,
            gameplay_frames=raw_frames, policy_decisions=cell['envs'] * cell['rollout_steps'],
            update_seconds=total, raw_frames_per_second=raw_frames / total,
            collection_raw_frames_per_second=raw_frames / counters['collection_total'],
            metrics=metrics, consumed_seeds=sorted(adapter.consumed_actual_seeds),
            startup_frames=adapter.initial_startup_frames + adapter.reset_startup_frames,
            actual_saved_boundary=None, completed_updates_discarded=1)
        if sha(reg['checkpoint_path']) != reg['checkpoint_sha256']:
            raise ValueError('Source checkpoint changed')
        status = 'complete'
    except BaseException as exc:
        result.update(status='failed', failure=repr(exc), traceback=traceback.format_exc(),
                      partial_timings_seconds=dict(counters), resources=peaks)
    finally:
        signal.alarm(0)
        result['elapsed_seconds_including_setup'] = time.monotonic() - started
        with output.open('x') as stream:
            json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write('\n')
    return 0 if status == 'complete' else 1


if __name__ == '__main__':
    sys.exit(main())
