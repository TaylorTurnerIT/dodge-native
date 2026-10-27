# D2 252-vs-180 regression: read-only diagnosis

Scope: frozen artifacts only. No Torch load, checkpoint load, environment steps, gradients, training, or edits outside this directory. Numbers come from `analysis.json`, produced by `analyze.py` (stdlib, `python3 -I`). Input and script hashes are in `receipt.json`.

Status: checkpoint 252 is provisional, `training_eligible: false`, parent terminal audit pending. Accepted reference remains 180 (`D2-gradient-alignment-20261025-r2`). Nothing here changes eligibility.

## Verified facts

**Development endpoints (64 fixed seeds, deterministic argmax, no caps)**

| Checkpoint | Mean alive | Q1 (bottom 16) | Q4 (top 16) | Mean score | Deaths: normal / kamikaze / explosion / moving / static |
|---|---|---|---|---|---|
| 132 | 1518.75 | 565.81 | 2786.25 | 12.45 | 34 / 12 / 2 / 5 / 11 |
| 180 | 1854.47 | 585.63 | 3502.56 | 16.11 | 32 / 11 / 0 / 11 / 10 |
| 252 | 1604.08 | 532.81 | 3192.31 | 13.59 | 24 / 9 / 3 / 13 / 15 |

- Canonical Q1/Q4 recompute from sorted alive frames matches the correction. Every 180 value matches the parent.
- The 180 development record is identical to the parent's (`jsonl` equal; `json` differs only by the checkpoint and phase fields).
- **Postflight summary is wrong and is kept as-is.** It reports Q1/Q4 of 768.75/2590.75 at 180 and 617.25/2415.25 at 252. Neither file order, seed order, nor any contiguous 16-value window reproduces these. They fall near the sorted 25th/75th-percentile boundary values (720–785 and 2571–2650 at 180). The likely cause is a different quantile definition. Not confirmed.

**Paired same-seed changes**

| Comparison | Mean diff (alive frames) | Median | Improved / worsened / tied | Paired bootstrap 95% (fixed seed 20261026, 10k draws) |
|---|---|---|---|---|
| 180 → 252 | −250.4 | −136 | 28 / 36 / 0 | [−691, +176] |
| 132 → 180 | +335.7 | — | 33 / 31 | [−34, +722] |
| 132 → 252 | +85.3 | — | 33 / 31 | [−252, +422] |
| Parent 180 → child 180 (control) | 0.0 | 0 | 0 / 0 / 64 | exact match |

- The 180 → 252 drop is consistent with the data but not separable from seed-level noise. Its CI includes zero.
- 252 is not worse than 132 on these seeds. The three-point trajectory is non-monotone. Only two checkpoints exist per run, so this cannot describe the training curve.
- Tail churn: 15 of 180's bottom-16 seeds left the bottom-16 by 252, and 15 new seeds entered it. Of 180's top-16, 12 left.
- Death causes (descriptive, per paired seed, not hazard rates): static-rectangle deaths rose 10 → 15, and their mean alive frames at death are high (~2275). Kamikaze-enemy mean alive fell from 1695 to 995. Explosion deaths appear at 252 (0 → 3). Seeds that moved to static-rect deaths gained a median of +996 frames. Seeds that moved to kamikaze deaths lost a median of −1380.
- Score tracks alive frames closely (Pearson 0.985 at 180, 0.978 at 252). Score adds no separate signal on these seeds.

**Training windows (72 updates 181–252 vs prior 48 updates 133–180)**

Window comparison uses the first 8 vs last 8 updates within each run. Values are first8 → last8.

| Metric | Child 181–252 | Parent 133–180 | Reading |
|---|---|---|---|
| Max-epoch approx KL (mean) | 0.0308 | 0.0300 | Similar |
| Fraction of updates with max-epoch KL > 0.03 | 0.68 | 0.54 | Higher in child |
| Early-stop KL flag true | 49/72 | 26/48 | Higher in child. Flag does not match `epochs_completed < 4` (child: 23 flagged with 4 epochs), so definition unverified |
| Clip fraction (mean) | 0.218 | 0.228 | Similar |
| Entropy | 1.758 → 1.754 | 1.774 → 1.739 | Parent decline did not continue in child |
| EV, pre-update (same batch, self-bootstrapped) | 0.435 → 0.460 | 0.492 → 0.433 | No EV decline in child window |
| EV, post-update | mean 0.516 | mean 0.541 | Critic moves within-batch but is not held out |
| Value loss | 0.0162 → 0.0177 | 0.0164 → 0.0177 | Rises in both |
| Target variance (pre) | 0.064 → 0.072 | 0.072 → 0.069 | Child target scale rising |
| Trunk grad norm | 0.641 → 0.703 | 0.608 → 0.656 | Rising in both |
| Pre-clip grad norm (live) | 1.12 → 1.29 | 1.01 → 1.08 | Child rising |

Gradient probe (CPU shadow, one probe per update, first 512-sample minibatch, pre-step, 33 parameters, 286,976 elements). This is not live MPS and not Adam-preconditioned:

- Child cosine: mean 0.0101, median 0.0098, 43% negative, minimum −0.691 at update 67. Parent: mean 0.0133, median −0.0065, 56% negative, minimum −0.154.
- Child embedding-group cosine: −0.010 (first 8) → −0.171 (last 8). Layer-0: 0.035 → −0.088. These late-window drifts come from single probes per update and are noisy.
- Critic/actor weighted-norm ratio: mean 0.0189 (child), 0.0213 (parent). Critic gradient is small in raw norm.
- Live clip coefficient matches `min(1, 0.5 / pre-clip norm)` to 8e-7. Global clipping rescales the combined gradient. It does not change its direction.

## Competing explanations, ranked by evidence

1. **Checkpoint-level noise on a fixed 64-seed development set.** Most consistent with the data. The 180 → 252 CI includes 0, 132 → 252 is indistinguishable from zero, and 132 → 180 is near zero too. 180 may sit on a favorable draw. *Predicts:* on fresh seeds, the 252 − 180 gap shrinks and its CI crosses zero. *Against:* on fresh seeds, the gap persists with a CI below zero.
2. **Evaluation-mode artifact (argmax vs sampled policy).** Untested. Endpoints use deterministic argmax, while training uses sampling. Entropy at 1.74–1.78 means sampled behavior may differ from argmax. *Predicts:* sampled-action ordering differs from argmax ordering. *Against:* both modes give the same 180 > 252 ordering.
3. **Policy churn / over-update.** Weak to moderate. KL-stop frequency rose from 54% to 68%, but mean max-epoch KL and clip fraction are similar, and entropy stays flat. *Predicts:* KL and entropy keep moving with survival drops across checkpoints. Only two checkpoints exist per run, so it cannot be tested with current artifacts.
4. **Shared-trunk gradient interference (embedding and layer-0).** Weak. Mean cosine is near zero, the extreme negative (−0.69) is a single probe, and the late negative drift is noisy at one probe per update. *Predicts:* repeated live-minibatch cosine stays negative. Not supported by the CPU shadow alone.
5. **Critic underfit or value-target drift.** Weak to moderate, and not testable on these artifacts. EV did not fall in the child window, so the EV decline in the parent window does not carry into the 252 regression. Value loss and target variance both rose. *Predicts:* held-out critic error rises with target scale. Same-batch EV cannot test this.
6. **Reward-score vs alive dynamics.** No independent evidence. Score tracks alive closely on these seeds. Reward shape is not separable from survival here.
7. **Failure-mode shift.** Descriptive only. Early kamikaze deaths decreased while static-rectangle deaths at long survival increased. This does not identify a cause.

Not supported: "EV decline caused the regression." The child window shows EV rising. The parent window's EV decline is a separate observation.

## Smallest discriminating experiments

Both experiments need parent registration before execution. Neither changes the algorithm. Neither replaces 180 or 252 or rolls back the parent.

**X1 (eval-only, no training, run first).** Re-evaluate frozen checkpoints 132, 180, and 252 on a fresh, pre-registered held-out seed set. Use at least 256 seeds, disjoint from the 64 development seeds. Run both argmax and sampled action modes. Use matched environment config, no caps, and the same step budget.
- Gate: report paired bootstrap CIs for 252 − 180 and 180 − 132 per action mode.
- Rejects noise if the 252 − 180 CI excludes zero in both modes.
- Rejects the argmax artifact if the ordering agrees across modes.
- Budget: evaluation only. No gradients, no training.

**X2 (training replication, run only if X1 leaves 252 below 180).** Re-run the 180 → 252 continuation twice more from the identical 180 state, changing only the run seed. Keep everything else matched: entry-restoration hashes, registration, update budget (72), and eval points (180/252). Evaluate both new 252 checkpoints on the X1 fresh seeds.
- Gate: if both new 252 checkpoints fall near the original 252 level, the drop is a repeatable outcome of continuing from 180. If both reach 180's level, the original 252 is a draw.
- Budget: about 20 minutes wall each (observed 1169 s for the first). Run serially on the single MPS device.
- Does not isolate a mechanism. It only tests whether the regression is repeatable.

Not proposed: algorithm changes, gradient surgery, detaching the critic, or more training before X1.

## Process speedups

- **Freeze inputs before any run.** Use `receipt.json`'s hash manifest as the frozen input set. Analytics then read only frozen artifacts and never touch in-flight runs.
- **Run analytics in parallel with the single MPS run.** Analysis is stdlib on CPU and does not contend with MPS, but keep only one MPS job at a time.
- **Start X1 checks before training ends.** X1 needs only frozen checkpoints and a pre-registered seed list, so its precheck (seed-list hashing, disjointness from development seeds) can run now.
- **Review scope.** Reviews need frozen inputs (manifests, registration, hashes), not Luna's in-progress code diffs.
- **Gate early.** Register X1's gate and seed list before running it, so its result is not chosen after the fact.

## Limits

- One training lineage. The 252 result is a single trajectory point.
- The 64 development seeds are reused for every checkpoint. The bootstrap quantifies this fixed set only. It is not a CI over training seeds.
- Gradient cosine is one CPU shadow probe per update over 33 parameters. It is not live MPS and not Adam-preconditioned, and it does not measure causal harm.
- Death causes are censored endpoints. They are not hazard rates or causal mechanisms.
- Early-stop flag definition unverified. Quantile definition behind the postflight Q1/Q4 values unverified.
- Training-episode records were checked only for kind counts (64 abandoned parent records retained, 3498 completed, 3153 reset). Per-update training reward was not analyzed.
