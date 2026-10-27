# Paired upper-D64 evaluator r2 preparation

Status: **source and synthetic CPU validation complete; no evaluation launched.** r1 remains byte-for-byte unchanged. Root `README.md` remains protected at SHA-256 `be478416b33c772a7ff9c28f2c974f767c205f7df77bcf7346ab36133d384652`.

## Implemented

- Concrete 64-environment D2 collector: ordered manifest seeds, one independent B1 environment per seed, exact frozen constructor flags and excluded ranges, shrinking live-only batched argmax, K=4, no gradients, no resets, per-step parent guard, and exact native startup, fixed-score, objective, fatal-frame, and cap checks.
- Production backend builder checks collector and runtime source pins, imported code origins, actual checkpoint file bytes, endpoint metadata bytes, and loaded model state-dict SHA before collection. Model/runtime imports and native environment construction remain explicit and lazy.
- Completed rows require startup 13, terminated XOR truncated, death `alive_frames + 1 == gameplay_frames`, cap truncation at exactly 18,000 alive/gameplay frames, score accumulation identity, and objective-return identity. Native collection rejects unavailable death telemetry.
- Endpoint pins reject null or malformed SHA, empty run IDs, wrong updates, and linear endpoint identity equal to constant. Paired summary records both arms' checkpoint SHA, run ID, and registration SHA.
- Exclusive atomic result publication refuses existing destinations. Guard interruption leaves no success file.
- Inference checks and restores RNG, module modes, weights/buffers, and parameter gradients. Any mutation fails closed. CPU fakes cover ragged completions, active-batch shape/action mapping, seed order, cap/death conservation, and mutation restoration.

## Validation

`cpu-tests.log`: 11 unittest cases passed using the project lexical venv, CPU, one BLAS/OpenMP thread, unset `PYTHONPATH`, `-B`, and r2's empty cache. Tests constructed only fake environments and a CPU fake policy.

Frozen native contract was read from `python/dodge_rl/dev_eval.py`, `crates/dodge-rl-env/src/env.rs`, and `crates/dodge-rl-env/src/python.rs`. No source outside r2 was written. No real native environment was constructed, no checkpoint binary was read, hashed, or deserialized, and no MPS, game, lease, state, marker, trial output, or training process was used.

## Parent-owned inputs still required

Before any later evaluation, parent must supply reviewed registration bytes and active budget guard; exact 384/432 endpoint metadata and checkpoint SHA for each arm; model state-dict SHA for each endpoint; full runtime source map including compiled extension; and accepted execution decision. Linear endpoint remains unset until parent binds the selected receipt. No timing, resource qualification, held-out independence, or evaluation result is claimed.

Seed pool remains the exact manifest pin `e11e9d6accb79fcafd1b0e6049c322356edf16601007d2af62da6b59539c886c`, ascending D0000040..D000007F. Label remains unselected, training-excluded development namespace; prior nonuse not proven; not sealed or proven independent. Comparison remains diagnostic: one paired training seed 4200000001, average LR 2e-5 linear vs 3e-5 constant, fixed update-384 endpoint only. Retained dev64 decision remains separate and parent-controlled.
