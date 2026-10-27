# Independent source-only review

## Scope and disposition

Reviewed frozen `analysis.md`, `evidence.json`, and `horizon_audit.py` against pinned `D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime/dodge_rl/ppo.py`. No runtime imports, checkpoint reads, games, evaluation, training, or shared-state edits. DeepSeek provenance is correctly identified as `opencode/deepseek-v4.1-flash-free`, provider `opencode`, with `paid_fallback: false`.

Useful and novel: this audit consolidates registered reward/horizon arithmetic, masks, critic diagnostic scope, and repeated-seed phase results. Its mask and reward-path source checks look sound. Keep operational 348 acceptance separate; this review does not block it. The causal ranking and selection-null claims below need correction.

## Findings

### High — recommended replay cannot identify critic calibration for trained behavior

**Location:** `analysis.md:195-206`.

**Trigger:** replay uses deterministic argmax on the retained 348 checkpoint, while PPO critic trained under a stochastic behavior policy (entropy about 1.65). It compares argmax-policy return against V learned on behavior-policy states/actions. A single return per seed also has substantial trajectory noise. The proposed arbitrary bias/correlation cutoffs do not resolve policy mismatch or uncertainty.

**Consequence:** failure cannot establish critic-limited credit assignment; passing cannot rule it out. Neither result ranks critic limits against LR effects. Do not use the proposed pass/fail branches to select critic or LR intervention.

**Correction:** collect independent episodes under the actual stochastic policy used for training, preserve behavior log-probability/action and checkpoint-matched V(s), repeat episodes per seed, and report calibration with seed-clustered uncertainty. Better, compare a preregistered critic-target intervention against a matched LR intervention across multiple independent training seeds, with held-out seeds and fixed evaluation policy. Treat calibration as descriptive absent that intervention.

### High — selection bootstrap tests a different statistic

**Location:** `horizon_audit.py:119-137`; claim repeated at `analysis.md:74-78, 189` and `evidence.json:selection_null.linear`.

**Trigger:** code centers each phase independently and bootstraps the maximum of five phase means. Observed statistic is phase-348 mean minus shared phase-324 mean. Baseline is omitted from every draw, and phase covariance induced by same seeds is not retained in the tested contrast. Thus reported `p=0.68885` does not test observed 348-minus-324 against a selection-aware null.

**Consequence:** do not endorse that p-value or its use to discount 348. The separate paired SEs, sustained summary, and phase outcomes remain descriptive evidence, but selection-adjusted inference is unresolved.

**Correction:** for each bootstrap draw, resample the same 64 seed indices jointly across baseline 324 and all five post-baseline phases; calculate each phase-minus-324 paired mean, take the maximum, then compare observed 348-minus-324 against this contrast-max distribution. State whether inference is one- or two-sided and use a finite-sample tail correction.

### High — effect-size conversion does not support “below critic noise” inference

**Location:** `analysis.md:20-22, 106-108, 190`; `horizon_audit.py:202-227`.

**Trigger:** 158.71875 extra alive frames is converted using a pointwise discounted reward heuristic, then compared with global critic residual SD 0.19287. This is not a matched outcome: discounted return is nonlinear in episode length and score/death timing, while residual SD is an in-sample, self-bootstrapped transition-target statistic, not episode-start error or policy-gradient noise. Per-seed paired 348-minus-324 SE is 287.19 frames; it cannot validate the unit conversion.

**Consequence:** the arithmetic may illustrate reward scale, but `4.2% of critic noise`, “metric difference ... far below value error,” and the inference that the effect is hard to learn are unsupported. No critic-vs-LR mechanism ranking follows.

**Correction:** calculate each evaluation trajectory’s exact discounted return from its per-decision rewards and compare it to V(s0) on the same policy/state distribution, with repeated episodes and clustered uncertainty. To test learnability/causality, manipulate critic targets or horizon in a powered replicated training comparison.

### Medium — survival reward is undercounted by action repeat

**Location:** `horizon_audit.py:218`; propagated to `evidence.json:horizon.alive_only_reward_per_decision`. Compare `horizon_audit.py:207` and `analysis.md:99-101`.

**Trigger:** `0.01 * reward_scale` omits `repeat=4`; alive reward is per raw frame. Correct alive-only reward per decision is `0.01 * 4 * 0.1 = 0.004`, not `0.001`. Main dense reward formula at line 207 correctly applies repeat.

**Consequence:** this field is wrong by factor four. Correct it wherever cited; it does not change `learner_reward_per_decision`, which includes repeat, or survival values computed from that field.

### Low — byte-hash discrepancy is mislabeled an unresolved anomaly

**Location:** `analysis.md:43-45, 220`.

**Trigger:** report treats differing 324 checkpoint file hashes as unexplained despite the cited `entry-restoration.json` proving equal model, Adam, and RNG component hashes and matched restoration. Container metadata/serialization can differ while restored training state matches.

**Consequence:** “provenance anomaly” overstates evidence and invites prohibited binary inspection. This does not undermine the supplied matching component-state evidence.

**Correction:** call it a container-byte difference with identical audited model/Adam/RNG restoration; no anomaly established. Preserve both byte hashes as provenance.

## Other limits and corrected claims

- `ppo.py:163-174` uses GAE trace factor `gamma * lambda` and rollout-window bootstrapping. `1/(1-gamma*lambda)` is trace-weight mass, not a hard credit horizon. The value bootstrap can carry effects across many rollouts; low direct terminal trace weight alone does not show long-range signal is unavailable.
- The source arithmetic supports γ per decision, action repeat four, reward scale once, termination/truncation masks, and zero observed truncations in these cohorts. It does not show those design choices caused fixed/linear outcome differences.
- In-sample explained variance and the one CPU-shadow gradient probe are appropriately qualified as limited. Avoid turning their levels into evidence that critic error dominates optimization.
- No numeric recalculation of corrected selection p-value is claimed here; closed-file method review suffices to reject the existing statistic.

## Practical next experiment

Run a preregistered, replicated 2×2 continuation: fixed versus linear LR crossed with baseline versus one specified critic-target intervention (for example, longer λ with all else held fixed). Use multiple independent training seeds per cell, same parent state protocol, common held-out evaluation seeds, and a primary paired outcome averaged over prespecified post-update checkpoints. Report seed-level contrasts and uncertainty; retain complete run receipts. First, if a no-training probe is still desired, log stochastic-policy episodes with repeated trajectories per seed and matched V(s0)/exact discounted G0, labeled calibration only. This separates policy-distribution calibration from causal schedule/critic comparisons.
