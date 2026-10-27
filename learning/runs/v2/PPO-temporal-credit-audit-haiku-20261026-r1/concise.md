# PPO temporal credit audit (static, r1)

**Result: no source bug reproduced.** No findings in temporal credit, reset, or GAE semantics of the frozen D2 r5 runtime. Nothing was run.

## Source checks (all pass)
- `next_values` uses the post-action observation, read before `reset_done` (`ppo.py:333-338`). The native step does not auto-reset (`env.rs:385-446`).
- Terminated steps zero the bootstrap and cut the trace. Truncated steps bootstrap from V(final obs) and cut the trace (`ppo.py:166-169`). The truncated branch is not exercised by retained data: 0 of 2563 completed episodes truncated.
- The GAE carry does not cross resets (`ppo.py:167`). It starts at zero at rollout end, with the boundary bootstrapped from `next_values[T-1]`.
- Reward scale 0.1 is applied once. The raw reward identity is checked exactly (`ppo.py:440`).
- The model has only LayerNorm, so train and eval modes match for `old_log_probs`.

## Horizons (60 raw frames/s taken from the task statement; 4 frames per decision)
| quantity | half-life | e-fold | effective horizon |
|---|---|---|---|
| gamma 0.995 | 138 dec (9.2 s, 553 frames) | 200 dec (13.3 s) | 200 dec (13.3 s) |
| gamma·lambda 0.94525 (GAE trace) | 12.3 dec (0.82 s, 49 frames) | 17.8 dec (1.18 s) | 18.3 dec (1.22 s) |

The GAE trace decays in about 18 decisions. The value target decays in about 200. The median completed episode is 389 decisions (25.9 s). For most states, credit from distant death reaches the advantage through critic bootstrap V. A short trace alone does not show missing long-term credit, because V may carry it correctly. This remains uncertain.

## Hypotheses (proposals, not tested)
- **H1:** Hazard-avoidance advantage depends mainly on critic accuracy far from death. Falsifier: bin advantage variance and critic residual by decisions-to-death. If the residual does not rise with decisions-to-death, H1 is weakened. Single change: lambda 0.95 → 0.99 (trace e-fold 66 dec, 4.4 s).
- **H2:** gamma 0.995 (13.3 s horizon) exceeds typical survival scale. Value targets then carry large future mass. Falsifier: decompose Var(returns) into score, survival, and death terms. Single change: gamma 0.995 → 0.99 (6.7 s horizon). This changes the objective.

Neither hypothesis can be tested from retained files, which hold no per-step advantage or return variance.

## Distinct from a GAE bug
- **Fresh-env resume shift:** restore recreates the env at episode index 0 for all 64 slots (`train_teacher.py:187`). 64 partial episodes are abandoned (median 245 dec). This shifts state distribution at the restore boundary only. It is not a GAE defect.
- **Deterministic argmax evaluation and checkpoint selection:** dev evaluation uses argmax (`dev_eval.py:137`), while training samples. The best-276 score (2483.66) and the endpoint-348 discard are evaluation and selection effects.

## Limitations
- Static only. No torch, no checkpoint decode, no training.
- The 60 FPS timebase is from the task statement and was not re-verified.
- The existing EV note cites `ppo.py` SHA 533055b0. The current r5 runtime is b3cef91b. Not reconciled.
- This does not show a critic failure or a benign EV shift.

Files: `diagnosis.json`, `receipt.json`.
