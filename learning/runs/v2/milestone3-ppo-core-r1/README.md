# PPO core component evidence

The component adds `python/dodge_rl/ppo.py` and `python/tests/test_ppo.py`. It implements the M3 component contract, including the parent’s revision-2 raw-accounting and interrupted-update requirements.

The final synthetic CPU suite has 44 passing cases under the target interpreter with bytecode disabled and warnings treated as errors. No game environment was constructed, no MPS probe ran, and no training campaign was executed. Importing the `dodge_rl` package loads its native extension; that is distinct from running native gameplay.

`cpu-tests-r1/` preserves the first run: 40 passes and one loss-oracle precision failure. The loss test originally mixed a float64 GAE oracle with float32 reductions inside a shuffled minibatch. Its corrected fixture isolates the loss with exactly representable alternating advantages; the original tolerance remains unchanged. `cpu-tests-r2/` records 41 passes. The final r3 run adds the registered episode-objective tolerance boundaries and a valid raw-diagnostics update, yielding 44 passes.

## Interfaces

- `PPOConfig.description()` records the exact loss formula and numerical conventions.
- `compute_gae` takes explicit pre-reset next values. Death disables bootstrapping; both death and alive truncation stop the recursive chain.
- `collect_rollout` returns CPU-owned, detached tensors. Every real collected batch includes fixed score deltas, alive frames, elapsed frames, and raw float32 rewards. It initializes integer episode totals from `env.episode_info()` so collection can continue an existing episode across rollout boundaries.
- `RolloutCollection.completed_episodes` contains copied episode metadata with zero-based `rollout_step`. `reset_info` contains events with `rollout_step`, `indices`, and `info`. The caller logs initial seeds separately.
- `ppo_update` moves minibatches to the model device, normalizes advantages per minibatch, clips the policy surrogate, checks finite losses/gradients, and measures current full-buffer KL after each epoch. It does not retain attention graphs in rollout storage.
- Optional updater `progress` records actual completed optimizer steps immediately after `optimizer.step`, before another guard. A raised guard leaves `in_update=true` and `complete=false`; the trainer must preserve and classify that interrupted state.
- Metrics are JSON-compatible. Undefined explained variance is `null`; actor/critic gradient metrics have an availability marker for synthetic models without named heads.

The value loss is `0.5 * mean((new_value - GAE_return)**2)`. Total loss is `policy_loss + vf_coef*value_loss - ent_coef*entropy`. Environment rewards remain unscaled; the learner stores the float32 product of raw rewards and the fixed learner scale.

## Evidence limits

Synthetic doubles establish arithmetic, alignment, storage, gradient, and interruption behavior. They do not establish actual teacher learning, performance, device support, real-environment integration, checkpoint identity, or exact live-environment resume. Those checks belong to parent integration and the separately owned trainer. Parent reconciliation and independent frozen review remain required before real training.

All 66 protected M2 source/binary/input pins remain unchanged. Source snapshots, the complete new-file patch, the source archive, exact command receipts, successful and failed logs, and JSON validation are retained here. `artifact-sha256.json` covers every retained file except itself.
