# Uniform2 recovery: global updates 360 to 600 (r1)

Preparation package for one fresh, exactly-once 240-update recovery. It restores the latest durable checkpoint at global update 360 from the interrupted `uniform2-continuation600-luna-20261028-r2` campaign. The checkpoint, not evaluation score, determines the starting state. The interrupted attempt remains spent: 400 completed PPO updates and 401 completed collections were recorded, while global update 401 completion was not journaled. If recovery completes, total completed updates across both attempts are 640.

The package trains four fresh-environment segments of 60 updates each with the original transformer, reward, PPO settings, action repeat 4, 64 environments, rollout 256, constant LR 3e-5, and uniform training pool. It restores model, Adam, complete RNG, and `next_episode_indices`; it does not reseed learner RNG. Boundaries are global 420, 480, 540, and 600. D6 was already exposed in the interrupted campaign. Recovery evaluates checkpoint360 and each new boundary on the same sampled-action D6 settings; these remain development results, not confirmation.

The independent parent incident audit and restore qualification are pinned. Training seed streams are derived from restored episode indices and rechecked by `audit_streams.py`. Exclusions include D4, D5, and D6. Work cap is 14,400 seconds; cleanup 10 seconds; postflight 120 seconds. RSS and MPS caps are 6 GiB. Retry count is zero. The owned watchdog has direct-child process-group ownership and non-reaping observation. A new lease, output directory, attempt marker, and launch marker belong only to this recovery package.

The worker may record a provisional recovery-only ranking across global360–600. It cannot promote a checkpoint. The final ranking across the original global0–360 prefix and recovery global420–600 is deferred until the parent audits both attempts. Official parent324 stays retained.

## Preparation and review

`binding.py` pins the frozen producer/runtime/evaluator and parent inputs. `build_registration.py` writes an inert draft without importing Torch or loading the checkpoint. `qualify_restore.py` is parent-owned and already produced the pinned read-only qualification. The parent's source/runtime qualification remains a separate gate. `launch.py` requires exact registration, source acceptance, parent gate acceptance, lease, power, and supervisor inputs. Never rerun a spent attempt.

Before any future launch: seal and independently review source; build and finalize registration after parent calibration acceptance; obtain source, restore, runtime, stream, resource, power, exact-once, supervisor, and parent gates; then launch once. After observer completion, run `audit_streams.py` and `audit.py`. Neither worker completion nor local ranking grants promotion.

## Tests and limits

`tests.py` uses CPU fakes to cover ordered updates, segments, evaluation, stream generation, resource limits, supervision, lease handling, tamper rejection, and terminal accounting. It does not exercise real MPS, native runtime behavior, checkpoint loading, or the actual observer. Parent restore/runtime qualification covers the bounded native checks separately.
