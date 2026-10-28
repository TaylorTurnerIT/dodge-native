"""One bounded native compatibility check of the reviewed continuation's actual RealRuntime.

Constructs one 64-slot training environment without stepping it. Restores the learner, checks evaluation
scratch-state isolation, saves/reloads an inert diagnostic checkpoint, then releases all objects.
No PPO update, evaluation cohort, registered training marker, or resource lease is consumed.
"""
from pathlib import Path
import copy
import gc
import json
import os
import resource
import signal
import sys
import time

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent / 'uniform2-recovery240-luna-20261028-r1'
sys.path.insert(0, str(PACKAGE))
import binding as b
import seeds
import worker


def main():
    reg_path = HERE / 'runtime-qualification-r2-registration.json'
    registration = b.read(reg_path)
    b.check_pins(registration['pins'])
    b.need(registration['environment_constructors'] == 1 and registration['game_steps'] == 0
           and registration['optimizer_steps'] == 0 and registration['evaluation_episodes'] == 0,
           'read-only runtime qualification scope differs')
    b.save(HERE / 'runtime-qualification-r2.claimed', dict(registration_sha256=b.sha(reg_path)))
    started = time.monotonic()
    result = dict(status='failed', game_steps=0, optimizer_steps=0, evaluation_episodes=0,
                  environment_constructors=0, source_manifest_sha256=b.sha(PACKAGE / 'source-manifest.json'))
    def timeout(*_):
        raise TimeoutError('runtime qualification exceeded registered wall limit')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(registration['wall_seconds'])
    rt = segment = None
    try:
        reg = b.read(PACKAGE / 'registration-draft.json')
        b.validate_static(reg, require_registered=False)
        modules = b.frozen()
        rt = worker.RealRuntime(reg, modules, None)
        caller_rng = rt.ckpt.capture_rng('mps')
        try:
            state = rt.load_parent()
            actual = rt.restore_learner(state)
            worker.learner_checks(actual, reg)
            before = rt.learner_snapshot()
            streams, components = seeds.segment_streams(rt.pool_all, reg['streams']['identity'],
                reg['parent']['initial_episode_indices'], frozen=rt.frozen_seed_priority)
            digest = seeds.digests(streams, components)
            b.need(digest == (reg['streams']['first_segment_slot_stream_sha256'],
                             reg['streams']['first_segment_slot_component_sha256']), 'actual stream digest differs')
            segment = rt.begin_segment(reg['parent']['initial_episode_indices'], streams, components,
                                       lambda _: (_ for _ in ()).throw(ValueError('unexpected native training event')))
            result['environment_constructors'] = 1
            counts = segment.live_counts()
            b.need(counts == dict(raw=13*64, constructors=1, steps=0, resets=0), 'zero-step native accounting differs')
            info = segment.env.episode_info()
            b.need(all(row['gameplay_frames'] == 0 and not row['terminated'] and not row['truncated'] for row in info),
                   'normal starts have advanced or ended unexpectedly')
            for slot, row in enumerate(info):
                episode = reg['parent']['initial_episode_indices'][slot]
                b.need(row['seed']['episode'] == episode and row['seed']['actual_seed'] == streams[slot][episode],
                       'native actual seed or episode offset differs')
            b.need(segment.prepared.state == 'ready' and segment.boundary.completed_updates == 0,
                   'prepared session is not at the zero-update boundary')
            observations = segment.env.observations()
            b.need(all(name in observations for name in b.NEURAL_INPUTS), 'neural observation keys absent')
            result['observation_shapes'] = {key: list(value.shape) for key, value in observations.items() if key in b.NEURAL_INPUTS}
            result['native_counts'] = counts
            result['first_actual_seeds'] = [row['seed']['actual_seed'] for row in info]
            b.need(rt.fingerprints() == before['fingerprints'], 'environment setup changed learner state')
            scratch_model = rt.teacher.OmniscientEntityTeacher().to('mps')
            scratch_model.load_state_dict(state['model'], strict=True)
            scratch_model.eval()
            import random
            seed = reg['evaluation']['rng_seed']
            random.seed(seed); rt.np.random.seed(seed % 2**32)
            rt.torch.manual_seed(seed); rt.torch.mps.manual_seed(seed)
            del scratch_model
            restored = rt.learner_restore(before)
            diagnostic = copy.copy(state)
            diagnostic.update(tag='probe_diagnostic', qualification_only=True, promoted=False,
                              automatic_selection=False, training_eligible=False)
            path = HERE / 'runtime-qualification-r2-checkpoint.pt'
            checkpoint_sha = rt.ckpt.save_checkpoint(path, diagnostic)
            os.chmod(path, 0o444)
            reloaded = rt.ckpt.load_checkpoint(path, expected_sha256=checkpoint_sha)
            b.need(rt.fingerprint(reloaded['model']) == before['fingerprints']['model'] and
                   rt.fingerprint(reloaded['optimizer']) == before['fingerprints']['Adam'], 'saved/reloaded contents differ')
            b.need(rt.fingerprints() == before['fingerprints'], 'save/reload changed learner state')
            rss, mps = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, rt.torch.mps.driver_allocated_memory()
            b.need(rss <= registration['rss_bytes'] and mps <= registration['mps_bytes'], 'qualification memory limit exceeded')
            result.update(status='passed_actual_runtime_restore_native_constructor_and_scratch_isolation',
                learner_fingerprints=actual, scratch_restoration=restored,
                runtime_modules_authenticated=True, first_segment_streams_verified=True,
                checkpoint_save_reload_verified=True, diagnostic_checkpoint_sha256=checkpoint_sha,
                peak_rss_bytes=rss, peak_mps_driver_bytes=mps,
                limits='No PPO update, native step/reset, D6 game, long-running throughput or boundary checkpoint-save path exercised.')
            del diagnostic, reloaded, state, observations
        finally:
            if segment is not None:
                segment.close(); segment = None
            rt.ckpt.restore_rng(caller_rng, 'mps')
            b.need(rt.fingerprint(rt.ckpt.capture_rng('mps')) == rt.fingerprint(caller_rng), 'caller RNG changed')
            gc.collect(); rt.torch.mps.empty_cache()
        b.check_pins(registration['pins'])
    except BaseException as error:
        result.update(status='failed', error=repr(error))
        raise
    finally:
        signal.alarm(0)
        result.update(elapsed_seconds=time.monotonic()-started, registration_sha256=b.sha(reg_path),
                      qualification_source_sha256=b.sha(Path(__file__).resolve()))
        b.save(HERE / 'runtime-qualification-r2.json', result)
    print(json.dumps(dict(status=result['status'], elapsed_seconds=result['elapsed_seconds'])))


if __name__ == '__main__':
    main()
