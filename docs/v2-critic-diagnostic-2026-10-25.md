# Same-batch critic diagnostic, 2026-10-25

The corrected diagnostic completed 48 D2 updates in **796.987 seconds**, with one launcher and one worker, both raw exit 0. Parent verified all 13,566 frozen input pins, artifact hashes, complete metrics/evaluations, per-episode reward and death arithmetic, resource receipts and process absence, then cleared the exact lease. Claude Haiku's independent result review found no blocking integrity issue; parent verified its 25 input hashes and reconciled the interpretation. Luna is designing the next bounded iteration.

## Survival and deaths

Each evaluation uses the same 64 D2 development seeds with deterministic argmax actions. Q1 and Q4 are means of the bottom and top 16 episodes, not percentile cutoffs.

| D2 update | Q1 alive frames | Q4 alive frames | Mean alive frames |
| --- | ---: | ---: | ---: |
| 0 | 165.4375 | 566.375 | 295.25 |
| 24 | 490.3125 | 1648.0625 | 886.609375 |
| 48 | 521.0625 | 2401.1875 | 1101.9375 |

At update 48, first fatal contacts were ordinary enemies **36/64 (56.25%)**, kamikaze enemies **11/64 (17.1875%)**, moving rectangles **9/64 (14.0625%)**, static rectangles **7/64 (10.9375%)**, and kamikaze explosions **1/64 (1.5625%)**. Every episode ended in death; no caps or unknown causes occurred. Attribution identifies the first fatal contact, not the counterfactual cause of a failed maneuver.

Historical best development cohort remains Q1 **648.25**, Q4 **4508.8125**, mean **2240** frames. It was selected among 24 evaluations during a different, much longer run; comparing it directly with this 48-update endpoint confounds training duration and checkpoint selection. Neither cohort is held-out qualification. This diagnostic remains below the prospective D2 survival gate and cannot advance a stage.

Duration-matched inspection found the earlier run's update-48 checkpoint had Q1 **525.125**, Q4 **1481.5**, mean **848.328125** frames on the same evaluation seeds. The fresh diagnostic's update-48 mean is 29.9% higher, with roughly unchanged Q1; training seed streams differ, so this is descriptive rather than a controlled ablation. The earlier best was reached at D2 update **320**. The apparent fall from that best to the fresh diagnostic reflects measuring a newly restarted D1-derived model after 48 D2 updates, rather than continuing the old best. [Comparison evidence](../learning/runs/v2/critic-diagnostic-parent-prepare-20261025-r3/duration-matched-performance-comparison.json).

Paired on identical seeds, update 48 survived longer than update 0 in **58/64** games. From update 24 to 48, **40** improved and **24** worsened; median gain was **54.5 frames**. Later gains were mixed rather than universal.

## What the critic measurements show

Same-batch explained variance improved and residual MSE decreased after optimization on **all 48 updates**. Arithmetic means across updates were pre/post EV **0.609800 / 0.703303** and MSE **0.0273812 / 0.0196050**. At update 48 specifically, EV was **0.559146 / 0.654455**. These are fits to identical frozen, self-bootstrapped GAE targets; they do not measure held-out critic accuracy.

The decline within the later part of this short run has a measurable decomposition. From updates 9–16 to 41–48, mean pre-update EV fell **0.694297 to 0.562027**. Target variance changed **0.067364 to 0.062843**, while residual variance rose **0.020131 to 0.027466**. Both terms changed; target contraction alone does not explain that window. Across updates 1–8 versus 41–48, both target and residual variance decreased. The window matters, and changing rollouts prevent a causal diagnosis of shared-trunk interference or generalization failure.

Behavior improved across all three evaluations while the critic fitted every observed batch. Falling EV alone therefore supplies no stop-training rule. This early-D2 diagnostic cannot explain the historical decline near update 384 or establish that additional training is sufficient or harmful. PPO settings and score-containing reward were unchanged; score is absent from the future progression gate.

Parent also described all **4,189** completed training episodes, excluding 64 abandoned D1 records. Their fatal contacts differ from the deterministic evaluation cohort: 1,606 normal enemies, 1,177 static rectangles, 956 moving rectangles, 415 kamikaze enemies and 35 explosions. These completed episodes span changing stochastic policies and omit unfinished episodes. The journal lacks an authoritative update index, so it cannot support update-aligned causal claims about target variance; future telemetry should include that index.

## Validation and retained failures

The instrumentation passed 63 component tests and 144 integrated tests. Luna's corrected runner passed 16 contract tests and actual Torch model/Adam fixtures, independently rerun by parent. Real accepted-D1 restoration matched model, Adam and Python/NumPy/Torch CPU/MPS RNG; saved/restored optimizer settings and repeated RNG capture also matched.

The first attempt failed before environment creation because the comparator treated `dict` and `OrderedDict` differently. Its command, receipts and checkpoint metadata remain unchanged. Luna's separate r3 repair canonicalizes mappings while retaining keys, scalar types and tensor byte/shape/dtype checks, and persists component evidence before failure. Haiku reviewed it. Parent resolved the additional unpinned-bytecode finding through an exact empty `PYTHONPYCACHEPREFIX` plus `-B`, verified actual restoration under that policy, and confirmed the prefix stayed empty throughout the corrected run.

Final registration SHA256: `6ae91ee55c4437e01daeff0d9cf6adfdcb01a3e62d977c2074c0cf115c4dab6e`. Original master seed `3192039780` was explicitly retained after the pre-environment failure. The corrected run observed sampled peaks of **839,581,696 bytes RSS** and **2,452,406,272 bytes MPS driver allocation**, below separate 6 GiB caps. Sampling does not establish a continuous all-process MPS peak.

Diagnostic checkpoints remain training-ineligible. No D3, student work, B/E qualification, metadata rewrite or automatic promotion occurred. Further iteration must preserve lineage and use a separately frozen, bounded plan under the user's continuation authorization.

The next prospective plan was revised from 80 to **72 new D2 updates**, with entry/final evaluations only. Haiku correctly identified extra-evaluation budget risk. Parent used the same D2 runtime's maximum observed update duration (17.172876 seconds): 72 updates plus 15% slowdown and 150 seconds of evaluation allowance totals **1571.914 seconds**, within 1600 seconds of work and the unchanged 1800-second total cap. This is a conservative estimate, not a completion guarantee. The 48 inherited pilot/D1 updates are prior work, not time charged again; the new final cumulative count will be 120. Only the final D2 update-72 checkpoint can be the prospective training candidate.

Incomplete prospective adapter revisions r1–r4 remain preserved. Parent integrated the normal iteration as a minimal adaptation of the successfully executed critic runner. The current r5 source passed 24 contract tests, actual Torch fixtures and exact accepted-D1 restoration. Full registration preflight verified 13,560 pins in about 0.6 seconds. Haiku's final frozen review found no blocking defects; parent recorded the stale preliminary receipt, late-failure-marker authority and sampled resource limits, and required external RSS observation through finalization.

The 72-update normal run is dispatched to Luna under registration SHA256 `d502c6761064727a610127fc58073e3a4c062fc928ea1e26de5718ad6aee6dcb`; actual launch count and results await observer evidence. The exact lease is installed, with one campaign permitted. New normal checkpoint candidates require parent terminal acceptance, while stage competence remains separate. All historical failed/diagnostic eligibility stays unchanged. The PPO literature report proposes future experiments only; learner settings remain unchanged.

Evidence: [parent terminal audit](../learning/runs/v2/critic-diagnostic-parent-prepare-20261025-r3/parent-terminal-audit-r2.json), [direct measurements](../learning/runs/v2/critic-diagnostic-parent-prepare-20261025-r3/direct-measurement-summary-r2.json), [independent observation](../learning/runs/v2/critic-diagnostic-execution-observer-20261025-r2/observation.json), [Luna implementation](../learning/runs/v2/critic-diagnostic-runner-prepare-20261025-r3/implementation-result.json), [Haiku source review](../learning/runs/v2/critic-diagnostic-runner-review-haiku-20261025-r3/receipt.json), [first failed attempt](../learning/runs/v2/critic-diagnostic-parent-prepare-20261025-r1/parent-terminal-audit-r1.json).
