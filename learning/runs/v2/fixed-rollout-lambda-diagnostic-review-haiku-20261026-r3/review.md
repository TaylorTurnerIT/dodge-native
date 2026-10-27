# Fixed-rollout lambda diagnostic R3: source-only review

Target: `learning/runs/v2/fixed-rollout-lambda-diagnostic-luna-20261026-r3/` (`diagnostic.py`, `controls_r3.py`, `hash-manifest.json`, `receipt.json`, `CONTRACT.md`, `README.md`, logs).

Scope: read-only source inspection, stdlib `shasum` hashing, and hand algebra/traces. No imports of the analyzer, Torch, NumPy, or runtime; no tests or controls run; no rollout, checkpoint, environment, hardware, or training access; no source, state, or lease changes. Writes only to this directory.

## Hash checks

Match the brief and receipt:

- `diagnostic.py` `de763f42…e3da2`
- `controls_r3.py` `e7cf9315…ca759`
- `hash-manifest.json` `877d06c5…fb38`
- pinned `ppo.py` `b3cef91b…eac5`

Recorded `controls-r3.log` and `controls.log` hashes are listed in `receipt.json`; I did not re-execute controls, so the 24 assertions and PASS line are unverified by this review.

## Findings

1. **High: observed-return recurrence uses the wrong reward index.** `diagnostic.py:153-155`. At each step the code appends `ret` for start `t`, then sets `ret = rewards[t] + GAMMA*ret`. The propagation should use the reward at the start index being computed, `rewards[t]`, before the append, not after it. Hand trace, one slot, `T=3`, death at `t=2`, rewards `a,b,c`:
   - Start 2 (distance 0): `c` — correct.
   - Start 1 (distance 1): code gives `c + γc`; correct is `b + γc`.
   - Start 0 (distance 2): code gives `b + γc + γ²c`; correct is `a + γb + γ²c`.

   Consequence: `observed_discounted_return_mean` and the `1_4`, `5_16`, `17_plus` entries of `time_to_death_bucket_means` are wrong for every start at distance ≥ 1. Counts and the partition are unaffected, so the bucket-coverage check still passes. No control asserts observed-return values. Fix: at non-terminal steps compute `ret = rewards[t] + GAMMA*ret_next` before appending, and add hand-value tests for observed returns and bucket means.

2. **Medium: partial raw variant is silently accepted alongside complete components.** `diagnostic.py:31` (`load_npz` gate) and `diagnostic.py:58-59` (variant gate). `load_npz` passes when `components <= keys`, even if only some raw fields are present, and the extra raw fields land in the allowed `raw` set. `analyze` then takes the component path (`have_raw` is False, `have_comp` is True) and ignores the partial raw arrays. Trigger: an archive with all three components plus only `elapsed_raw_frames`. Consequence: the raw accounting checks (`elapsed` bounds, `alive == elapsed - terminated`, score nonnegativity) are skipped without error, which violates the contract's "exactly one raw/component variant" rule. Controls cover only complete-both and missing-one-raw-field-with-no-components, so this case is untested. Fix: reject any archive that carries a partial raw set or a partial component set.

3. **Low: parity and rejection tests are weaker than they read.**
   - `controls_r3.py` (parity loop, ~lines 21-27) compares only target and advantage mean and variance to production `compute_gae`. Compensating element errors can pass. An elementwise comparison would be stronger.
   - `controls_r3.py:71-73` checks only `target_variance > 0` for the near-constant case. It does not assert that EV is a finite float rather than `None`, so the "no epsilon hiding near-constants" claim is not tested on the EV output.
   - The component-variant path (scaled `score_reward`, `survival_reward`) has no rejection test beyond the death identity; the NPZ rejection cases all use the raw variant.

## Closed from R1 (verified in source)

- Distance-0 bucket present (`"0"` at `diagnostic.py:167`) and bucket counts reported with exclusion counts.
- Dead `target_minus_baseline_norm` field removed; the offset keys are `signed_change_from_lambda_0.95_mean` and `norm_difference_from_lambda_0.95`.
- Exact-equality constant detection (`diagnostic.py:122`), no epsilon.
- Analyzer-vs-production parity for both lambdas and hand terminal/reset/tail and truncation/bootstrap/reset cases are present in `controls_r3.py`.
- Raw-plus-component rejection is preserved (`diagnostic.py:59`, both-present case tested).

## Algebra and parity (checked by hand)

- Carry recurrence matches production `compute_gae` (`ppo.py:163-171`): `cont = ~(term|trunc)` zeroes carry, `boot = ~term` zeroes the bootstrap, tail carry is zero beyond `T`, and `vb = V + B` with `target = ΣC_k + vb` and `adv = target − V`.
- Population covariance over all pairs with `ddof=0` and `Σvar + 2Σcov` reconstruction are correct; the identity error should be near zero by construction.
- Raw `elapsed ∈ [1,4]` and `score ≥ 0` match production audit (`ppo.py:241-243`). The reward identity matches `ppo.py:245-249`.
- Observed-death scan: first-boundary logic (category inherited backward) correctly handles current-step death (distance 0), resets per slot, truncation exclusion, and tail exclusion. Eligible, truncation, and tail counts partition `T·N` exactly. Only the return values in finding 1 are wrong.

## Limits

- Static read and hand algebra only; no controls were executed. The recorded PASS and the 24-assertion count come from the owner's run, not this review.
- Parity is synthetic float32 on one `3×4` case; no actual-rollout parity claim, consistent with `CONTRACT.md`.
- Descriptive only. Nothing here supports a causal, critic-quality, EV-gain, or gate claim. No effect on best300 playback or accepted training.
