# best180 vs latest252: paired inference-only plan (design, r1)

Status: planned, not implemented, not run. Inference only. No gradients, optimizer, checkpoint writes, B/E opens, or training-eligibility change. Machine-readable version: `plan.json`.

## Question
Is the 180 → 252 argmax drop (mean alive −250, paired CI [−691, +176] from the prior study) finite-seed noise (T1), or does it depend on argmax vs sampled action selection (T2)?

## Pair and parents
- best180: `checkpoint-000180-candidate.pt`, sha `3173d293…2cca8`. Accepted reference. Stays accepted.
- latest252: `checkpoint-000252-candidate.pt`, sha `cbdc65d0…254b`. Provisional, `training_eligible: false`.
- No training parent chosen. No rollback.
- Canonical values to reproduce: 180 Q1/Q4/mean = 585.625 / 3502.5625 / 1854.46875; 252 = 532.8125 / 3192.3125 / 1604.078125.
- Correction accepted: Q1/Q4 are sorted bottom/top-16 means, not inclusive percentiles or seed-ordered slices. The postflight summary's quartiles use a different definition and stay unused.

## Cohort
- Reuse the 64 existing dev seeds, 3489660928–3489660991. No new seeds.
- Caveat: dev seeds were already observed for 180/252 selection. Diagnostic only. No held-out claim, no B/E.
- Future-training constraint (declared, not applied): any later training-selection decision that reads this diagnostic must exclude these 64 seeds or mark them diagnostic-only.
- Fresh-cohort alternative not chosen for r1. It needs a new declared seed range and a reservation decision from parent.

## Design (512 episodes)
- Per checkpoint: 64 argmax episodes + 64×3 sampled episodes (controller seeds 64001, 64002, 64003).
- Argmax controls: saved dev JSONL per-seed fields must match field-for-field. Mismatch stops the run; no retry.
- Game: D2, difficulty 2, action_repeat 4, patterns and powerups on, no pixels, 64 independent B1 envs, no reset.
- Raw-frame cap 18000 per episode. Capped episodes are censored and reported; primary table requires zero caps.
- Action RNG: argmax draws nothing. Sampled uses `Categorical(logits).sample()` on MPS, float32. Reset torch and MPS seeds once per checkpoint × replicate, after load. Draw order matches r3.

## Budget
- Wall cap 600 s, cleanup reserve 10 s. Host RSS 6 GiB (6442450944 B) and MPS driver 6 GiB, separate caps. Torch threads 4.
- Measured: campaign-r1 ran 768 episodes in 47.7 s. Dev argmax 180 took 10.1 s, 252 took 5.8 s.
- Expected about 40–90 s. Worst-case raw frames 512×18000 = 9,216,000.

## Outputs and schema
- Dir: `learning/runs/v2/postovernight-best180-latest252-paired-action-mode-r1` (proposed).
- Per checkpoint × mode: 64 per-seed alive frames; mean; Q1 (sorted bottom-16 mean); Q4 (sorted top-16 mean); mean score; deaths by cause; cap count. Sampled values are the mean of 3 replicates per seed.
- Contrasts (paired by seed):
  - C1 = 252 − 180, argmax.
  - C2 = sampled − argmax, 180.
  - C3 = sampled − argmax, 252.
  - C4 = C3 − C2 (interaction).
  - C5 = 252 − 180, sampled.
- Also report per-checkpoint replicate noise floor (SD across 3 replicates per seed).

## Statistics and decisions
- Bootstrap: 10,000 percentile draws over the 64 seed clusters, seed 764002, same indices for all metrics. Conditional on the fixed checkpoint pair and environment-seed sampling. Not training-replicate uncertainty.
- Practical margins: 100 alive frames, 1 score point.
- Rules: a contrast is "real" if its CI excludes 0 and |mean| ≥ 100. CI inside (−100, 100) means practically similar. Otherwise inconclusive.
- Report all contrasts regardless of outcome.

## What would weaken each theory
- T1 (env-seed noise explains the drop) is weakened if C1's CI excludes 0 with |mean| ≥ 100, or if the argmax gap exceeds the sampled replicate noise floor.
- T2 (action-mode sensitivity drives the gap) is weakened if C4's CI includes 0, or if C5 matches C1 in sign and size under both modes.
- If C1 and C4 both include 0, the data does not separate T1 from T2. Report inconclusive, not a win for either.

## Expected limits
- 64 seeds means wide CIs. A null is likely and is not equivalence unless the CI sits inside the margin.
- One checkpoint per arm. No training-replicate variance.
- Dev seeds reused. No qualification or held-out claim.

## Parent decisions
- Reuse dev seeds vs declared fresh range. Current choice: reuse.
- Keep controller seeds 64001–64003 for comparability with r3.
- Keep 18000-frame cap. Censoring is reported, not hidden.

## Provenance
- Inputs and hashes in `receipt.json`. Prior regression study: `learning/runs/v2/D2-252-regression-analysis-haiku-20261026-r1/`.
- No harness implementation, run, source/ledger/lease edits, Torch load, environment steps, or child work.
