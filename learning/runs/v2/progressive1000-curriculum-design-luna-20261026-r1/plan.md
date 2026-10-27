# Progressive survival curriculum design

**Proposal:** train matched control and curriculum arms from the same accepted step-324 checkpoint, with unchanged reward, model, and PPO settings. Curriculum episodes start normally and stop at 1,000 raw gameplay frames, then 2,000, and onward by 1,000-frame stages. Keep the existing 256-decision rollout. Current weakness hypothesis is unproven. All thresholds and mix fractions in `experiment.json` are proposed, not user-approved.

At stage horizon H, assign 70% episodes to H and 30% across earlier horizons. Require at least 10 updates and 200 target-horizon episodes; then require two consecutive 100-episode target-horizon windows at 90% milestone success. A death on the H-reaching transition counts as failure. Failure resets the consecutive-window count. If a stage does not pass by update 60, end the pilot at that stage. Earlier-horizon episodes give extra practice but cannot advance mastery. See `experiment.json` for exact schedules, metrics, and resource rules.

| Arm | Parent | LR | Training | Evaluation |
|---|---|---:|---|---|
| Matched control | accepted step 324 | constant `3e-5` | 3 replicas × 60 updates | new disjoint full-run cohort |
| Progressive curriculum | same accepted step 324 | constant `3e-5` | same paired seed vectors and decision budget | same cohort and fields |

Budget equality means equal rollout decisions and optimizer steps. Episode cutoffs can change raw frames, reset count, startup cost, and wall time. Log each separately and enforce parent-approved caps. If no existing control matches every source, config, seed, budget, exclusion, and evaluation field, prepare isolated control runs.

## Runtime feasibility

Frozen PPO computes values from the actual step observation before `reset_done`; GAE bootstraps truncated-but-alive states and stops recurrence at termination or truncation (`own/runtime/dodge_rl/ppo.py:143-170, 334-360`). Native `reset_done` only accepts terminated or truncated slots (`crates/dodge-rl-env/src/env.rs:473-488`). Current Python binding exposes reset, but no active-slot practice-cutoff operation (`crates/dodge-rl-env/src/python.rs:335-350`). So cutoff cannot be implemented safely by changing only Python flags. Add a scoped native operation that marks the selected slot as practice-truncated after its final continuing observation, then allow its normal reset; preserve observation, reward, episode counters, seed episode index, and final-observation accounting. Death on the same transition wins. Add isolated tests for real-death masks, cutoff bootstrap, no GAE leakage, action-repeat boundary behavior, and slot isolation before any training.

Do not create later-stage starts by changing a frame counter. This first design needs no later-start optimization. If added later, require full normal-prefix replay or a complete validated snapshot: engine RNG and objects, wrapper velocity/history, action-repeat state, seed/episode counters, and replay/construction cost charged to its arm.

Evaluation disables practice cutoff and starts every episode normally, running to death or the regular 18,000-frame cap. Training mastery is an online scheduler signal, not independent evaluation. Reserve and audit a new disjoint evaluation cohort before environment construction; both arms use the same cohort and exclusion union. Do not open B/E cohorts. Parent must resolve seed ancestry, cohort size, resource ceilings, and whether any existing control is truly identical before registration.

## Architecture, objective, and source impact

Use the accepted entity transformer checkpoint unchanged: frozen two-layer, width-128, 81-token full-attention model. Keep reward `score + alive_frames/100 - 5 on true death`, learner reward scale `0.1`, `gamma=0.995`, `gae_lambda=0.95`, entropy `0.01`, minibatch `512`, and four epochs. Keep reward shaping and model capacity unchanged. The design changes only episode horizon assignment and the required practice-cutoff boundary handling.

Any runtime/native change needs a new isolated successor source pin and registration. Do not edit the frozen runtime, checkpoint, ledger, lease, marker, README, or LR-study preparation. Parent owns source/ancestry audit, seed reservation, resource calibration, registration, independent review, and acceptance. No training or qualification is authorized by this design.

## Source anchors and reproducibility

`source-sha256.txt` records exact read-only source hashes from the frozen runtime and current native API. Hash command: `shasum -a 256 <listed path>` from repository root. SHA-256 covers bytes as present during this design pass. Line anchors above aid review; the hashes identify the exact inputs. No production code changed. No environment, game, or realMPS import or construction occurred. No checkpoint was deserialized. No training, evaluation, or launch occurred. No tests were run.
