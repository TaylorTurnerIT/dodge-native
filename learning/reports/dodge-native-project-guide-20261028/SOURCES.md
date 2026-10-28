# Source map for Dodge Native guide

Paths below are relative to the repository root. Links use `../../../` from this report directory.

## Project and game

- [README.md](../../../README.md) — project purpose, Rust/Macroquad port, controls, cartridge asset, and attribution. Overview only; game source is authoritative.
- [docs/SPEC_PRIVILEGED_VIT_RL.md](../../../docs/SPEC_PRIVILEGED_VIT_RL.md) — original v2 architecture and intended teacher-to-vision path. Treat as design context; apply corrections in the source audit and environment contract.
- [docs/v2-source-audit.md](../../../docs/v2-source-audit.md) — source-verified contract and correction record. Use with current Rust/Python source.
- [docs/v2-environment-contract.md](../../../docs/v2-environment-contract.md) — observation, reward, action repeat, termination/truncation, seed, and wrapper contracts; identifies items that are design or acceptance requirements rather than completed evidence.
- [crates/dodge-core/src/game.rs](../../../crates/dodge-core/src/game.rs) — movement, score events, difficulty response, enemies, collisions, powerups, patterns, and game loop.
- [crates/dodge-core/src/action.rs](../../../crates/dodge-core/src/action.rs) — nine action names and button masks.
- [crates/dodge-core/src/patterns.rs](../../../crates/dodge-core/src/patterns.rs) — pattern definitions and geometry.
- [crates/dodge-core/src/config.rs](../../../crates/dodge-core/src/config.rs) — game configuration defaults.
- [crates/dodge-rl-env](../../../crates/dodge-rl-env) — native Python environment boundary; source implementation is authoritative over design prose.
- [python/dodge_rl/ppo.py](../../../python/dodge_rl/ppo.py) — current repository PPO configuration, GAE, rollout boundaries, clipping, entropy, KL monitoring, and minibatch updates. Registered runtime copies govern already-running campaigns.
- [python/dodge_rl/models/teacher.py](../../../python/dodge_rl/models/teacher.py) — current structured teacher architecture and input boundary.
- [Pinned campaign PPO source](../../../learning/runs/v2/fullgame-seed-priority-experiment-luna-20261027-r3/runtime/dodge_rl/ppo.py) and [pinned teacher source](../../../learning/runs/v2/fullgame-seed-priority-experiment-luna-20261027-r3/runtime/dodge_rl/models/teacher.py) — authoritative code copies for the currently registered campaign; root source may drift.

## Completed results cited

- [docs/v2-baseline-results.md](../../../docs/v2-baseline-results.md) — audited difficulty-2 native baseline, heuristic/random/neutral comparison, capacity and throughput limits.
- [docs/v2-D2-training-2026-10-25.md](../../../docs/v2-D2-training-2026-10-25.md) — earlier training lineage and gate outcome.
- [docs/v2-action-mode-results-2026-10-24.md](../../../docs/v2-action-mode-results-2026-10-24.md) — sampled versus argmax diagnostic and its limits.
- [docs/v2-death-telemetry-2026-10-25.md](../../../docs/v2-death-telemetry-2026-10-25.md) — first-fatal-contact counts for one fixed development cohort.
- [docs/v2-critic-diagnostic-2026-10-25.md](../../../docs/v2-critic-diagnostic-2026-10-25.md) — short-run behavior and same-batch critic diagnostics.
- [docs/v2-transfer-diagnosis-2026-10-24.md](../../../docs/v2-transfer-diagnosis-2026-10-24.md) — transfer diagnosis context; not evidence of qualified visual student.
- [learning/runs/v2/progressive1000-full-run-evaluator-parent-20261027-r2/result-summary.json](../../../learning/runs/v2/progressive1000-full-run-evaluator-parent-20261027-r2/result-summary.json) — three matched opening-curriculum pairs; confirms mixed outcomes and no replica advancing beyond the first stage. Pair detail belongs with this result and its parent terminal audit.
- [learning/runs/v2/fullgame-priority-D4-last-three-evaluator-sonnet-20261028-r1/six-model-merge.json](../../../learning/runs/v2/fullgame-priority-D4-last-three-evaluator-sonnet-20261028-r1/six-model-merge.json) — six fixed policies, three matched training pairs, 1,024 shared evaluation seeds per policy; full Worst/Q1/Mean/Q4/Best table in the report. D4 is a cohort label, not game difficulty. Its uncertainty is conditional on these policies and does not estimate training-run variation.
- [learning/runs/v2/fullgame-priority-D4-last-three-parent-validation-20261028-r1/lower-quarter-selection.json](../../../learning/runs/v2/fullgame-priority-D4-last-three-parent-validation-20261028-r1/lower-quarter-selection.json) — exploratory selection of the uniform candidate by Q1 after initial difficulty-2 results.
- [Common training contract](../../../learning/runs/v2/fullgame-priority-D4-last-three-parent-validation-20261028-r1/common-training-contract.json) — verifies shared settings across all six producers and identical training-randomness vectors within each matched pair.

## Background and proposals

- [reports/PPO opening survival literature.md](../../../reports/PPO%20opening%20survival%20literature.md) — curriculum and opening-survival proposals, clearly separated from completed Dodge evidence.
- [reports/PPO explained variance diagnosis.md](../../../reports/PPO%20explained%20variance%20diagnosis.md) — critic diagnostics and caveats.
- [reports/PPO innovations for Dodge.md](../../../reports/PPO%20innovations%20for%20Dodge.md) — PPO research proposals and cited background. These are not proof of Dodge-specific causes or gains.
- [Schulman et al., Proximal Policy Optimization Algorithms (2017)](https://arxiv.org/abs/1707.06347) — PPO background.
- [Schulman et al., High-Dimensional Continuous Control Using Generalized Advantage Estimation (2015)](https://arxiv.org/abs/1506.02438) — GAE background.
- [Pardo et al., Time Limits in Reinforcement Learning (2018)](https://proceedings.mlr.press/v80/pardo18a.html) — termination versus external time-limit background.

These papers explain general algorithms and evaluation concerns. They do not establish causes or treatment effects in Dodge.

## Active work: status only

- [Progress snapshot](progress-snapshot.json) — dated count of completed training updates; not a final result or evaluation-performance claim.
- [learning/runs/v2/uniform2-continuation600-luna-20261028-r2/registration-final.json](../../../learning/runs/v2/uniform2-continuation600-luna-20261028-r2/registration-final.json) — frozen plan and source/gate registration for the active continuation. Does not establish final outcomes.
- [learning/runs/v2/uniform2-continuation600-repair-parent-20261028-r2/first-training-update-receipt.json](../../../learning/runs/v2/uniform2-continuation600-repair-parent-20261028-r2/first-training-update-receipt.json) — confirms actual PPO optimizer updates began. This guide intentionally does not inspect active evaluation scores or checkpoint tensors.
- [learning/runs/v2/uniform2-continuation600-parent-20261028-r1/one-frame-decision-followup.json](../../../learning/runs/v2/uniform2-continuation600-parent-20261028-r1/one-frame-decision-followup.json) — queued follow-up proposal; not launched.

## Claim classes and limitations

- Source-verified game mechanics are grounded in Rust source and reconciled contracts.
- Empirical numbers are linked to completed result artifacts and their audits; they describe named cohorts and policies.
- Hypotheses and future experiments are labeled as such. The guide does not infer universal curriculum effects or a proven cause of weak openings.
- The active continuation is incomplete. Its outcome evidence is excluded.
- The guide does not deserialize checkpoints, inspect active checkpoint tensors or outcomes, run experiments, or publish weights/builds. It makes no new empirical claim beyond the cited source set.
