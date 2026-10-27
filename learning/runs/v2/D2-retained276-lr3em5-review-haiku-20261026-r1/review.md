# D2 retained276 LR 3e-5 source review (SOURCEONLY, static)

Target: `learning/runs/v2/D2-retained276-lr3em5-prepare-luna-20261026-r1/`
Reviewer: claude-haiku-5-5 (sub-agent, no children, no runs, no writes outside this directory)

## Verdict: No findings

No concrete correctness, path, or resource defect found that blocks the next parent-gated step. Pinned hashes (registration, runner, launcher, LR helper, cost anchor) match the values in the task.

## Checked

- Config diff vs parent `f858a63c...`: only `ppo.learning_rate` changes (1e-4 → 3e-5). Seed `3791628420` is outside excluded ranges.
- Runner schedule: 60 updates, 276→336, evaluations 276, 288, 300, 312, 324, 336. Cumulative target 384.
- Stale expectations (7 evals, 72 local updates, 396 cumulative) appear only where they describe the parent or the resource anchor, not the arm.
- Resource anchor fields match `completed-iteration-receipt.json` (348 completed, endpoint `2a21ca...`, cost 5537.77 → 7118.78, branch high-water 4760.06).
- LR transition: Adam/model/RNG restored and fingerprinted before write. Only `param_groups[*].lr` is written. Model, RNG, and mode are checked unchanged. Fingerprint excluding LR is checked unchanged. Helper is loaded by hash-pinned exec with origin check.
- `guarded_update` asserts effective LR before and after each PPO call. Saved checkpoints assert LR 3e-5.
- Entry candidate 276 is saved after the override, so its LR expectation (3e-5) is consistent.
- Resource estimate arithmetic: 1581.0090618329123 × 60/72 × 1.15 = 1515.1336842565406 (fits 1650 planned, 1790 work, 1800 outer). Linear scaling is conservative since the arm has one fewer evaluation.

## Non-blocking observations

- `D2-retained276-lr3em5-config.json` carries `parent_checkpoint_sha256: ce9c03c8...`, inherited from the validated r2 config. It differs from the accepted parent `0b5cf72b...`. The reviewed runner pins the parent by constant and does not read this field, but I did not trace the whole tree. Low severity.

## Not verified here

- Entry-restoration Adam `restored_sha256` vs transition receipt fingerprint: not traced into the prior run's outputs.
- Lease assertion and unmocked parent preflight: parent-owned gates.
- Test and CPU scripts were not executed (static review only).
