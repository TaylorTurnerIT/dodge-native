# Fixed-rollout lambda diagnostic contract

Status: proposal tool only. No capture adapter, active runner change, rollout read, or actual-data result.

## Input

Accept only an immutable, already-collected CPU rollout saved as plain NPZ. Reader uses `allow_pickle=False`; it never accepts pickle, model/checkpoint data, or framework objects. All arrays use `[T,N]`, keep each environment slot's episode order, and include:

- `values`, `next_values`: finite floating-point values before each action and on that action's post-step final observation, before any reset.
- `terminated`, `truncated`: boolean mutually exclusive flags. Termination zeros bootstrap and stops carry. Truncation bootstraps `next_values` and stops carry. Ordinary rollout tail uses `next_values`; carry starts at zero beyond T. A reset never carries across either boundary.
- Either raw `score_delta_raw_fixed`, `alive_raw_frames`, `elapsed_raw_frames`, or scaled `score_reward`, `survival_reward`, `death_reward` components. Raw identity: `score/65536 + alive/100 - 5*terminated`; scale each component once by `0.1`. Require elapsed frames in `[1,4]`, `alive=elapsed-terminated`, and nonnegative score. Scaled components must satisfy `death_reward=-0.5*terminated`.
- Optional `rewards` must match sum of scaled components. It is not a substitute for component arrays.

Only compare lambda `0.95` and `0.99`, with gamma fixed at `0.995` and same rollout values, rewards, and boundaries. Use population moments (`ddof=0`). Decompose each target into score, survival, death, and combined value/bootstrap contribution. Report every pair covariance; variance identity is sum of component variances plus twice all off-diagonal covariances. Advantage is target minus value by construction; its variance is not independent critic error. Self-bootstrapped explained variance is descriptive and undefined for constant targets.

Optional observed return uses only starts whose next boundary within this same slot is termination. Truncated and tail-censored starts are excluded. Time-to-death buckets are descriptive conditional summaries, with no monotonic-variance falsifier.

## Future capture insertion proposal

If separately authorized and registered, capture these fields at existing PPO storage writes in the rollout collection loop, from the already available pre-action value and post-action final-observation value, audited raw step counters, and boundary flags. Source pointer: frozen `learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime/dodge_rl/ppo.py`, `collect_rollout` around lines 333–339. This pointer is a proposal only; do not edit or copy runner/runtime.

## Limits

This compares descriptive targets on one fixed rollout. It does not establish real-rollout parity, causal effect, actor interference, critic quality, guaranteed EV gain, or a training gate. No gamma change, experiment, capture, hardware use, or trial selection is implied.
