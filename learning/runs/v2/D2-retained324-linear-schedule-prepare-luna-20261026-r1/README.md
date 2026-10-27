# Retained 324 linear LR successor draft

Draft runner ID: `D2-retained324-linear-lr-20261026-r1`. Source only. No launch, preflight, registration, seed reservation, lease, checkpoint, runtime, or parent ledger mutation occurred.

Restore original model, Adam, RNG, and optimizer LR first. Entry checkpoint LR stays `3e-5`. Verify inherited update count is exactly 372; derive every actual cumulative count only as inherited updates plus runner local updates. Initialize schedule metadata only at that verified origin. Later scheduled resumes require complete `lr_schedule` metadata and fail closed when absent.

Apply schedule after rollout and immediately before PPO update. Stage metadata; commit only after PPO succeeds. Log actual LR for every optimizer parameter group. Updates 373..432 use linear `3e-5` to `1e-5` inclusive; later updates hold `1e-5` with uncapped progress. Preserve other PPO settings, counters, episode indices, diagnostics, and resource guards. Evaluate 324, 336, 348, 360, 372, 384 under unchanged dev action mode/protocol. Keep fixed-control endpoints as paired primary; future independent evaluation stays separate.

## Parent assembly gate

Registration generation remains **BLOCKED ON immutable latest completed-iteration cost receipt**. Selected trajectory baseline remains `5678.9823631240915` seconds. Do not reuse the old `9758` campaign cost. Parent must consume actual latest receipt, then create fresh registration, source/runtime pins, launcher, output contract, and independent auditor. This directory contains no launchable registration and no invented digest.

## Evidence limits

CPU synthetic/source checks only. No runtime qualification, checkpoint load, MPS, rollout, training, campaign preflight, or scientific result.
