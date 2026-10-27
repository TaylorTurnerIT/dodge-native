# Next PPO experiment ranking (design only)

Scope: frozen evidence only. No web or literature round, no games, no training, no checkpoint or source edits. Retained best is checkpoint 180 (sha256 `105e0f7a83e154116bd9f0d5eaaf573a896886468c9038f548f5ce7e6377c7ea`). Continuation never starts from worse 252. Machine-readable matrix: `plan.json`.

## Evidence used

- Dev survival on the 64 registered seeds: 180 mean alive 1854.47; 252 mean alive 1604.08; paired difference −250.39, bootstrap 95% CI [−691.5, +176.4]. The CI crosses zero. Bootstrap resamples seeds conditional on this pair. It is not training-seed uncertainty.
- Statistical power (approximate): SE about 221 frames, from CI half-width. Minimal detectable paired difference at 80% power about 620 frames, about one third of the 180 mean. One training seed per arm on these 64 seeds cannot resolve smaller effects.
- Update metrics, D2-gradient-alignment-20261025-r2 (48 updates) and D2-continuation-20261025-r2 (72 updates), in 8-update bins:
  - Clip fraction 0.20–0.23 in every bin.
  - Epoch-end approx KL 0.028–0.032 against target 0.03.
  - Early-stop flag true in 25–100% of updates per bin, median about 60%. Mean epochs completed 3.1–3.9 of 4.
  - Entropy 1.72–1.77. NUM_ACTIONS = 9, so ln 9 = 2.197. Entropy fell only 0.01–0.04 over 48–72 updates.
  - Pre-clip grad norm 0.77–0.89 against cap 0.5. Actor grad norm about 0.45, critic about 0.04.
  - Gradient cosine averaged about 0.02 with sign changes.
- Integrity fact: `restore_learner` calls `optimizer.load_state_dict`, which restores the saved lr. A learning-rate config change is therefore silently overridden on resume. Verified with torch 2.14.1 on a 2-parameter linear model: fresh lr 1e-4 became 3e-4 after load. Any lr arm needs an explicit param_group override and an assertion.

## What these numbers do and do not show

- The trust-region measurements are the strongest signal. Clip fraction and early-stop frequency show that per-update policy movement reaches the KL limit in most later updates. This is a measured fact, not a proven cause of the dev curve.
- Gradient cosine (0.0101 mean in the prior summary, about 0.02 in these bins) and the critic/actor norm ratio (about 2%) do not establish harmful interference. The cosine is a raw single-probe CPU shadow.
- Critic EV did not decline in the 252 window: first 8 to last 8 rose 0.435 to 0.460. All 72 critic MSE fits improved. The EV decline argument is not used here.
- The 180-to-252 survival drop is real on these seeds but not established as training-seed signal. Score-matched covariance (−29.7, CI [−100, +36.7]) is descriptive, not causal.

## Ranking

1. **A: learning rate 3e-4 → 1e-4 (trust-region control).** Single config variable, no algorithm change, but a source fix is required. Restore must override the lr, with a unit test that moments equal the parent's. Mechanism: lower per-update movement cuts clip fraction and KL-limited epochs. Falsified if clip and KL fall as intended and dev mean alive does not beat C0 beyond the noise floor. Budget matched to C0: 72 updates, 1,179,648 decisions, about 4.71M raw frames, about 20 min MPS. C0 observed 1.92 GB RSS and 2.45 GB MPS, under the 6 GiB limits.
2. **B: critic reads detached trunk latent (conditional).** One-line source hook in `models/teacher.py:175` plus isolation test. Mechanism is a Dodge-specific stop-gradient test of interference. Justification is weak. Run only after A's result, and only if interference remains a question. A null result is not evidence of no interference.

Control C0 is unchanged best180 continuation. It is a required reference, not a candidate. The existing 72-update continuation is one training-seed sample. A second registered training seed is needed before any arm is read as positive.

Not ranked: entropy coefficient (no collapse measured), GAE λ/γ (no measured critic-bias case), running target normalization (larger change, motivated by unestablished EV decline), max-grad-norm change (small expected effect under Adam), PPG auxiliary or recurrent memory (needs separate design).

## Gates and retained best

- One long MPS campaign at a time, each ≤ 1800 s total, separate 6 GiB RSS and MPS limits, no automatic launch.
- Parent checkpoint and optimizer hashed before and after; never written.
- Dev seeds fixed: 64 registered D seeds, argmax, unchanged order. Excluded training ranges unchanged. No reserved or evaluation seed in training.
- Candidate replaces retained best only if its completed, audited dev mean alive is strictly above 1854.47. Otherwise the parent remains and the candidate is retained as diagnostic only.
- Dev selection repeated on the same 64 seeds is optimistic. Dev curves are selection records, not generalization evidence. No qualification or held-out claim follows.

## Prepare now versus evidence that would change ranking

Prepare now (no MPS): A config and lr-restore fix in a registered snapshot with a unit test; C0 seed-2 registration; protocol seed check; pre-registered decision rule.

Would change ranking: a second C0 seed differing from the first by more than the A-minus-C0 gap (training noise dominates); A's KL and clip not falling (integrity failure, arm invalid); fresh-seed evidence that the 252 drop is checkpoint-specific (lowers urgency of all PPO changes); per-death telemetry pointing to difficulty state or reward value rather than optimizer behavior; dev-eval nondeterminism above the noise floor.
