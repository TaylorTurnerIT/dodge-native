"""Bounded actual worker/model/collector qualification on an already-used training seed.

Four eight-frame probe games exercise both selectors and both repeats with a genuine native environment.
The production collector still requests its fixed 18000 cap; this qualification factory explicitly substitutes 8.
This does not touch the fresh D7 cohort, optimizer, campaign markers, or checkpoint bytes.
"""
from pathlib import Path
import gc
import json
import os
import resource
import signal
import sys
import time

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent / 'control-frequency-screen-luna-20261028-r1'
sys.path.insert(0, str(PACKAGE))
import binding as b
import screen
import worker


def main():
    registration_path = HERE / 'actual-runtime-qualification-r4-registration.json'
    registration = b.read(registration_path)
    b.verify_pins(registration['pins'])
    b.need(registration['constructors'] == 4 and registration['gameplay_frames'] == 32
           and registration['native_steps'] == 20 and registration['probe_raw_frame_cap'] == 8,
           'Qualification bounds differ.')
    b.save(HERE / 'actual-runtime-qualification-r4.claimed', dict(registration_sha256=b.sha(registration_path)))
    started = time.monotonic()
    def timeout(*_):
        raise TimeoutError('Actual startup qualification exceeded registered wall limit.')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(registration['wall_seconds'])
    result = dict(status='failed', optimizer_steps=0, checkpoint_writes=0, dev_seed_games=0,
                  constructors=0, gameplay_frames=0, native_steps=0)
    try:
        reg = b.read(PACKAGE / 'registration-draft.json')
        np, torch, game, checkpoints, teacher = worker.authenticate_runtime(reg)
        fingerprint = worker.load_fingerprint_helper(reg)
        # These are the same frozen helpers the worker imports during production.
        from death_telemetry import death_fields
        from screen import NEURAL_INPUTS
        caller_rng = checkpoints.capture_rng('mps')
        model = None
        try:
            model = worker.load_frozen_policy(reg, torch, checkpoints, teacher, fingerprint)
            initial = fingerprint(model.state_dict())
            completed = []
            for repeat in (4, 1):
                for mode in ('argmax', 'sampled_categorical'):
                    def factory(**options):
                        b.need(options['action_repeat'] == repeat and options['raw_frame_cap'] == 18000,
                               'Production collector request differs.')
                        b.need(options['seeds_by_slot'] == [[registration['training_seed']]], 'Qualification seed differs.')
                        options['raw_frame_cap'] = registration['probe_raw_frame_cap']
                        result['constructors'] += 1
                        b.need(result['constructors'] <= 4, 'Qualification constructor cap.')
                        return game.VecDodgeEnv(**options)
                    def event(row):
                        if row['kind'] == 'step':
                            result['native_steps'] += 1
                            result['gameplay_frames'] += row['elapsed_raw_frames']
                            b.need(result['native_steps'] <= 20 and result['gameplay_frames'] <= 32,
                                   'Qualification returned-work cap.')
                    rows = screen._production_rows(model, factory, NEURAL_INPUTS, death_fields,
                        [registration['training_seed']], reg['evaluation_exclusions'], lambda: None,
                        action_repeat=repeat, action_mode=mode, batch_size=1, event_sink=event)
                    screen.validate_rows(rows, [registration['training_seed']], cap=8)
                    b.need(len(rows) == 1 and rows[0]['truncated'] and rows[0]['gameplay_frames'] == 8,
                           'Eight-frame probe boundary differs.')
                    b.need(fingerprint(model.state_dict()) == initial, 'Probe changed model weights.')
                    completed.append(dict(action_repeat=repeat, action_mode=mode,
                                          policy_decisions=rows[0]['policy_decisions'], gameplay_frames=8))
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            mps = torch.mps.driver_allocated_memory()
            b.need(rss <= registration['rss_bytes'] and mps <= registration['mps_bytes'], 'Probe memory cap.')
            result.update(status='passed_actual_worker_model_native_and_four_collector_conditions', probes=completed,
                          model_fingerprint=initial, peak_rss_bytes=rss, peak_mps_driver_bytes=mps,
                          runtime_manifest_sha256=reg['runtime_manifest_sha256'],
                          source_manifest_sha256=reg['source_manifest_sha256'],
                          limitation='Four eight-frame probe games on one already-used training seed; not a full-game timing or D7 outcome qualification.')
        finally:
            checkpoints.restore_rng(caller_rng, 'mps')
            b.need(fingerprint(checkpoints.capture_rng('mps')) == fingerprint(caller_rng), 'Caller RNG restore differs.')
            del model
            gc.collect()
            torch.mps.empty_cache()
        b.verify_pins(registration['pins'])
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        signal.alarm(0)
        result.update(elapsed_seconds=time.monotonic() - started,
                      registration_sha256=b.sha(registration_path), qualification_source_sha256=b.sha(Path(__file__)))
        b.save(HERE / 'actual-runtime-qualification-r4.json', result)
    print(json.dumps(dict(status=result['status'], probes=len(result['probes']), gameplay_frames=result['gameplay_frames'])))


if __name__ == '__main__':
    main()
