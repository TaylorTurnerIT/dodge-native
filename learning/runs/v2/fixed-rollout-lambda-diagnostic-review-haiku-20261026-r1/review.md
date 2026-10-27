# Fixed-rollout lambda diagnostic: source-only review

Scope: static read of frozen `fixed-rollout-lambda-diagnostic-luna-20261026-r1` (`diagnostic.py`, `controls.py`, `CONTRACT.md`, `README.md`), pinned production `D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime/dodge_rl/ppo.py`, and `PPO-temporal-credit-parent-reconciliation-20261026-r1/reconciliation.json`. No imports, no Torch, no runs, no checkpoint or rollout reads, no writes outside this directory.

## Hash checks

All match the brief and receipt: `diagnostic.py`, `controls.py`, `CONTRACT.md`, `README.md`, pinned `ppo.py` (`b3cef91b…eac5`), and `controls.log` (`b510df43…c282`).

Not verified: the synthetic array and analyzer JSON hashes in `receipt.json` and `controls.log`. Those need a run, which this review does not do.

## Static check of the analyzer math

I traced `analyze()` against production `compute_gae` (ppo.py:143-174) by hand.

- Carry-based reward components `C_k` plus value/bootstrap carry `B` give `adv = ΣC_k + B` in exact arithmetic. That equals the production GAE advantage.
- `target = ΣC_k + vb` where `vb = values + B`. `vb` is the value/bootstrap component.
- Termination zeroes bootstrap and stops carry. Truncation bootstraps and stops carry. Carry starts at zero beyond T. Both match production.
- Raw identity `score/65536 + alive/100 - 5*terminated`, scaled by 0.1, matches the production audit (ppo.py:246-252, `atol=1e-5`).
- Population covariance over all pairs, and the reconstruction `Σvar + 2Σcov`, are correct for `ddof=0`.

Caveat: this is my algebra, not a runtime check. It has not been confirmed by executing code.

## Findings

Ranked most severe first. None blocks the descriptive claims in `CONTRACT.md`.

1. **Coverage gap (test), medium.** `controls.py:41-55`. The controls compare production `compute_gae` output to a hand recurrence (lines 53-54). They never compare `diagnostic.analyze()` target, advantage, or component moments to production `targets` and `adv`. The printed `production_GAE=CPU-parity` refers only to production versus the hand recurrence. Trigger: any change to the analyzer's carry or bootstrap logic that still passes the existing controls. Consequence: "analyzer production parity" is untested, not proven. The static algebra above says it should hold.

2. **Dead output field, low.** `diagnostic.py:131`. `"target_minus_baseline_norm": None` is set and never overwritten. The real lambda-offset keys are `signed_change_from_lambda_0.95_mean` and `norm_difference_from_lambda_0.95` (lines 138-139). Trigger: every `analyze()` call. Consequence: JSON always contains a null field whose name suggests a missing offset or norm.

3. **Death-distance-0 bucket gap, low.** `diagnostic.py:146-148, 154-157, 164-166`. Starts include the terminal step itself (`range(start, T)` includes `start`), so every termination adds a distance-0 observation. Distance-0 counts toward `eligible_state_count` and `observed_discounted_return_mean`. No bucket covers it: buckets are `1_4`, `5_16`, `17_plus`. Trigger: any `terminated[t,n]=True`. Consequence: bucket means do not partition the eligible set, and bucket counts are not reported, so the reader cannot reconcile them. Starts also overlap within an episode (every state is a start), so the cohort is not independent samples. That is consistent with "descriptive", but the cohort description should say so.

4. **Silent field ignore, low.** `diagnostic.py:31-33, 58-61` with `load_npz` at lines 31-33. `load_npz` accepts raw fields and component fields in one archive. `analyze` uses the raw path and silently ignores partial component arrays, for example a full raw set plus only `score_reward`. Trigger: an archive with the full raw set plus any subset of component arrays. Consequence: extra arrays are read and discarded without error. Only matters if a future caller assumes the components were used.

5. **Exact-zero EV guard, low.** `diagnostic.py:122`. `ev = None if target_var == 0`. A constant target can produce a tiny nonzero float variance from rounding, which makes EV unstable instead of `None`. Trigger: constant or near-constant targets. Consequence: the "undefined for constant target" claim in the contract may not hold for float-rounded constants. The controls test only exact zeros (`constant` case).

6. **Hardcoded exclusion flag, low.** `diagnostic.py:152`. `"excluded_tail_censored_and_truncated": True` is a constant, not a count. The contract asks for tail-censored starts to be excluded explicitly. The flag states the rule, but no count of excluded starts is reported.

7. **Asserts in controls, low (static limitation).** `controls.py:43-74`. The checks are bare `assert`s, which are stripped under `python -O`. The PASS print at line 77 runs after them and is unconditional. The receipt command uses `python -B`, not `-O`, so this does not affect the recorded run.

8. **Efficiency, low (note).** `diagnostic.py:144-149`. The observed-return loop is O(T²·N) Python with a `next()` scan per start. Fine for the synthetic cases. Could be slow for a long real rollout. Not a correctness issue.

## Confirmed matches to the contract

- Inputs: `allow_pickle=False`, mutually exclusive boundary flags, exactly one reward-input variant, `elapsed` in `[1,4]`, `alive = elapsed - terminated`, nonnegative score, finite arrays, optional `rewards` identity.
- Target decomposition into score, survival, death, and value/bootstrap components, all pair covariances, population variance (`ddof=0`).
- Reported target and advantage mean and variance, lambda offset and norm, self-bootstrapped EV with `None` for zero variance, `allow_nan=False` JSON.
- Observed returns: only same-slot starts whose first boundary is termination. Truncated and tail-censored starts excluded.
- Production audit (ppo.py:234-256) enforces the same raw identity and boundary rules that `analyze()` assumes.

## Limitations

- Static read only. No runtime qualification. The synthetic receipt values are unverified.
- Controls use one 3×4 synthetic rollout. They do not cover multi-episode or long-horizon behavior, or real rollout data.
- Descriptive only. Nothing here supports a causal, actor-interference, critic-quality, or EV-gain claim.
- The parent reconciliation's corrections (4/60 s decisions, nonzero saved resume indices, GAE target equal to advantage plus value) are consistent with this code. The review did not re-verify the reconciliation's counts.
