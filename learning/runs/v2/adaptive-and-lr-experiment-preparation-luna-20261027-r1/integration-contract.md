# Parent assembly contract

Preparation modules are pure Python and do not import Torch, environment or checkpoint code. They are deterministic reference behavior, not runner integration.

## Adaptive arm

- Copy the accepted clean runtime into a new parent-owned successor; never alter frozen source. Keep the existing supervisor, restore/lease/receipt lifecycle, native cutoff operation, telemetry, collector audit and PPO entry point.
- Replace only the fixed assignment rule in the successor adapter with `AdaptiveExposureScheduler`; keep full normal starts and freeze each episode's generation/horizon until death or cutoff. Initialize scheduler from authenticated study-vector digest.
- Aggregate accepted per-step raw gameplay frame deltas by frozen assignment horizon and generation. Feed completed-update totals into `finish_update()` only after `ppo_update()` succeeds. Never count startup frames or unaudited returned work toward the floor. Preserve those separately in receipts.
- Assign only on reset, after successful boundary. All reset slots from an update use the generation active during that update; promotion and quota changes take effect at next boundary. Record scheduler boundary output and per-assignment quota policy in append-only worker events and snapshot/checkpoints.
- Reuse current terminal precedence and native final-observation bootstrap semantics. Refresh runtime identity, adapter source pins, contract allowlist, registration builder, worker/runner pins and manifest hashes. Frozen constant-70/30 contract must remain unchanged.

## LR arm

- In successor runtime adapter, check restored Adam param-group LR against `learning_rate_for_update(1)` before applying any override. Do not reconstruct optimizer or modify Adam moment state.
- Before each local update t, compute expected LR, set and verify every param group, then pass PPO config with `learning_rate=expected`. Worker guard compares against that update's computed value. Receipt records formula/version, t, expected value, pre-set restored/effective value, and post-PPO effective LR.
- Validate update order 1..60, exact endpoints, monotone schedule, complete decision budget, and no unregistered schedule. Update contracts/identity/registration templates/builders and source hashes explicitly. Do not monkeypatch old constant-LR guards or edit old source.

## Review and launch boundary

Use existing robust supervisor only after parent verifies its bindings to the new successor. These modules and tests do not prove parent checkpoint ancestry, MPS/reference restore, native parity, source manifests, registrations, fresh seed cohorts, resource caps, or launch readiness. Parent assembly must review each separately before registration.
