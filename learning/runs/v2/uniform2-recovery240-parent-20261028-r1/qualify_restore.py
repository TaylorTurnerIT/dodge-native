"""Exactly one checkpoint360 read-only MPS restore qualification; no game environment or optimizer update."""
from pathlib import Path
import gc
import importlib
import json
import os
import resource
import signal
import sys
import time

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
sys.path.insert(0, str(V2 / 'fullgame-priority-D4-last-three-evaluator-sonnet-20261028-r1'))
import binding as b


def main():
    reg = b.read(HERE / 'restore-qualification-registration.json')
    output = Path(reg['output'])
    b.need(not output.exists(), 'restore qualification output already exists')
    b.save(HERE / 'restore-qualification.claimed', dict(registration_sha256=b.sha(HERE / 'restore-qualification-registration.json')))
    started = time.monotonic()
    result = dict(status='failed', environment_constructors=0, game_steps=0, optimizer_steps=0,
                  evaluation_episodes=0, checkpoint_sha256=reg['checkpoint_sha256'])
    def timeout(*_):
        raise TimeoutError('restore qualification exceeded registered 60-second limit')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(reg['wall_seconds'])
    try:
        b.need(b.sha(reg['checkpoint_path']) == reg['checkpoint_sha256'], 'checkpoint hash drift')
        b.need(b.sha(reg['runtime_manifest_path']) == reg['runtime_manifest_sha256'], 'runtime manifest drift')
        runtime = Path(reg['runtime_root'])
        manifest = b.read(reg['runtime_manifest_path'])
        b.check_pins({str(runtime / name): digest for name, digest in manifest['files'].items()})
        sys.path.insert(0, str(runtime))
        sys.path.insert(0, str(runtime.parent))
        import torch
        import numpy as np
        from fingerprints import fingerprint
        from dodge_rl import checkpoints as ckpt
        from dodge_rl.models.teacher import OmniscientEntityTeacher
        b.need(str(torch.__version__) == reg['runtime_versions']['torch'], 'torch version differs')
        b.need(torch.backends.mps.is_available(), 'MPS unavailable')
        torch.set_num_threads(4)
        caller_rng = ckpt.capture_rng('mps')
        try:
            state = ckpt.load_checkpoint(Path(reg['checkpoint_path']), expected_sha256=reg['checkpoint_sha256'],
                                         expected_identity=reg['expected_identity'])
            ckpt.require_complete_update(state)
            b.need(state['schema'] == reg['expected_checkpoint_schema'] and
                   [state['global_update'],state['phase_update'],state['cumulative_update']] == reg['expected_checkpoint_counters'],
                   'selected checkpoint counters/schema differ')
            expected = dict(model=fingerprint(state['model']), Adam=fingerprint(state['optimizer']), RNG=fingerprint(state['rng']))
            model = OmniscientEntityTeacher().to(device='mps', dtype=torch.float32)
            optimizer = torch.optim.Adam(model.parameters(), lr=3e-5, eps=reg['ppo']['adam_eps'])
            ckpt.restore_learner(state, model, optimizer, 'mps')
            b.need(expected == reg['expected_fingerprints'], 'checkpoint fingerprints differ from pinned sidecar')
            actual = dict(model=fingerprint(model.state_dict()), Adam=fingerprint(optimizer.state_dict()),
                          RNG=fingerprint(ckpt.capture_rng('mps')))
            b.need(actual == expected, 'restored model/Adam/RNG differs from selected checkpoint')
            b.need(all(group['lr'] == 3e-5 for group in optimizer.param_groups), 'restored LR changed')
            b.need(len(state['next_episode_indices']) == 64, '64 resume offsets required')
            b.need(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss <= reg['rss_bytes'] and
                   torch.mps.driver_allocated_memory() <= reg['mps_bytes'], 'restore qualification memory exceeded')
            origins = {}
            for name, module in tuple(sys.modules.items()):
                if name == 'dodge_rl' or name.startswith('dodge_rl.'):
                    path = Path(module.__file__).resolve()
                    b.need(path.is_relative_to(runtime), 'loaded module outside pinned runtime')
                    relative = str(path.relative_to(runtime))
                    b.need(b.sha(path) == manifest['files'][relative], 'loaded module content differs')
                    origins[name] = str(path)
            result.update(status='passed_exact_selected_model_Adam_RNG_restore_readonly',
                fingerprints=expected, readback_fingerprints=actual, next_episode_indices=state['next_episode_indices'],
                abandoned_current_episodes=state['abandoned_current_episodes'], counters=state['counters'],
                identity_sha256=state['identity_sha256'], architecture=model.architecture_description(),
                global_update=state['global_update'], phase_update=state['phase_update'], cumulative_update=state['cumulative_update'], origins=origins,
                restored_learning_rate=3e-5, peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                peak_mps_driver_bytes=torch.mps.driver_allocated_memory(),
                pycache_empty=not any(Path(os.environ['PYTHONPYCACHEPREFIX']).iterdir()))
            del model, optimizer, state
            gc.collect(); torch.mps.empty_cache()
        finally:
            ckpt.restore_rng(caller_rng, 'mps')
            b.need(fingerprint(ckpt.capture_rng('mps')) == fingerprint(caller_rng), 'qualification caller RNG restore differs')
        b.need(b.sha(reg['checkpoint_path']) == reg['checkpoint_sha256'], 'checkpoint changed during qualification')
    except BaseException as error:
        result.update(status='failed', error=repr(error))
        raise
    finally:
        signal.alarm(0)
        result.update(elapsed_seconds=time.monotonic()-started,
                      registration_sha256=b.sha(HERE / 'restore-qualification-registration.json'),
                      qualification_source_sha256=b.sha(Path(__file__).resolve()))
        b.save(output, result)
    print(json.dumps(dict(status=result['status'], fingerprints=result['fingerprints'])))


if __name__ == '__main__':
    main()
