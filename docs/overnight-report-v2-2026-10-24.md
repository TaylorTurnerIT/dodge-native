# Dodge v2 overnight report — 2026-10-24

M0–M2 are accepted on their recorded source identities. The specified M3 teacher and PPO runtime are implemented and reviewed. D1 passed its development progress gate; D2 failed at its unchanged 1,800-second wall guard. The teacher is **not qualified**. D3, final qualification/replication, and student work remain unstarted.

## Cutoff and final state

The overnight cutoff was **2026-10-24T13:00:00Z**, 08:00 America/Chicago. This thread resumed at **13:51:55 UTC**, after cutoff. The parent then disabled only `scheduled-task:command:mcp:ddabe9aa-111f-44d8-8b93-9dcd3a4e910d:schedule-task:dodge-v2-overnight-20261024-r1`; the scheduler returned `enabled:false` and `nextRunAt:null`, confirmed by a subsequent listing. Closure happened after the deadline; this report does not claim the scheduler was disabled at 13:00.

Before closeout, its final schedule had been changed to Saturday 08:00 local, with next run `2026-10-24T13:00:00.000Z`. That schedule is now disabled. The final receipt and prior ledger snapshot are retained in [`overnight-closeout-r1`](../learning/runs/v2-orchestration/overnight-closeout-r1/). The [orchestration ledger](../learning/runs/v2-orchestration/state.json) has no active long campaign. Both final T3 tasks are terminal; the recorded D2 wrapper/supervisor/worker PIDs are absent. No new experiment or implementation stage ran during closeout.

All failed runs, original checkpoints, source archives, and receipts remain intact. No commit, PR, public deployment, external message, or student implementation was made during the authorized v2 overnight work.

## Changes implemented

| Milestone | Resulting behavior | Acceptance boundary |
| --- | --- | --- |
| M0 | Isolated original-engine profiling and random, neutral, and AABB safe-powerup baseline harness; fixed seeds and episode caps | Audited original-engine measurements, including 1,000 episodes per policy at D2 and D3 |
| M1 | Deterministic `advance_frame_headless`, explicit post-method rendering, and borrowed `PrivilegedView`; camera/draw RNG and legacy cached-pixel behavior preserved | Live logical-state/RNG comparisons, targeted fixtures, legacy tests, formatting, and Clippy on the recorded milestone source |
| M2 | Core-only Rust/PyO3 vector environment; K=4 accumulated score/alive/death reward; fresh u32 episode seeds; typed 14-global/16-entity AABB/slab features; visibility and motion history; owned arrays, explicit episode handling, Rayon chunks, GIL release | Independently audited native parity, Python trajectories/ownership, memory workload, and public API throughput |
| M3 | Full entity teacher, PPO and curriculum runner, development evaluation, immutable checkpoints, frozen source/runtime identities, resource guards, and parent-authorized terminal transitions | Final integration and frozen reviews accepted; learning reached D1 progress only |

The teacher has **321,290 parameters**, width 128, two full self-attention layers, four heads, and 81 tokens at the default 64 enemy-family plus 16 rectangle slots. It uses the required score-centered reward with `0.01` per alive raw frame and one `-5` death penalty. Hidden RNG, scheduling timers, inactive catalogs, and anti-camping counters are excluded from model inputs.

Five runtime defects found during review were repaired before the real experiments: cancellation could orphan workers; interrupted updates could regain candidate eligibility; checkpoint-local accounting could reclaim consumed phase time; nonfinite probe failures could be swallowed; and candidates could remain eligible after their originating run failed or was cancelled. **Same-phase resume remains disabled.** Curriculum transitions require exact successful terminal receipts and a parent-owned lease anchor, including parent-observed supervisor exit 0. A candidate certificate alone cannot authorize advancement.

The [implementation plan](implementation-plan-v2.md), [source corrections](v2-source-audit.md), [environment contract](v2-environment-contract.md), and [M3 component contract](v2-m3-component-contract.md) record the detailed behavior. Earlier survival-only, full-catalog, heuristic-imitation, and player-query-only workflows remain superseded.

## Validation and performance evidence

These counts describe separate source identities and workloads. They must not be added together or treated as fresh validation of another milestone. The old 214-test result is not v2 validation.

- **M1-r2:** 72 workspace tests, including 15 headless fixtures, formatting, and workspace/all-target/all-feature Clippy with warnings denied. The 100×2,000 parity comparison contains 200,000 frames, including 171,650 dead-residence frames. Separate fixtures exercise active mechanics and all 39 catalog entries. External Pemsa runtime validation was not run.
- **M2:** The metadata stage separately ran 86 workspace tests. The binding receipt reports 41 unit plus 35 primitive Rust tests and 68 Python tests, formatting and workspace/all-target/all-feature Clippy; it did not run the whole workspace. The accepted r2 runtime campaign covers **2,000 paired episodes and 10,146,614 raw frames per path**, matching original-engine score/survival/cap totals and all 39 patterns at D2 and D3. Python comparisons cover pixels, auxiliary targets, thread/chunk choices, ragged termination, resets, and array ownership.
- **Memory:** The rendered B8 workload completed 5,000 warmup calls and 100,000 measured calls, retaining 101 RSS samples. First/last median RSS growth was **3,014,656 bytes**, below the fixed 64 MiB threshold. This supports an empirical plateau under that workload, not zero leaks.
- **M3:** Final integration passed **312 Python tests** on 75 pinned inputs. Both frozen r3 Codex control/identity reviews returned no findings. The closeout rechecked all 75 current source hashes without running a new test suite.
- **Independent D2 failure audit:** Passed as an evidence audit, with no findings. It verified 144 execution artifacts, 41 runner artifacts, 75 source pins, 7,915 completed-training-episode reward audits, all seven development evaluations, optimizer progress, resource records, and all 15 retained checkpoints. This audit accepts the failure record; it does not turn D2 into a successful run.

The M1 short matched benchmark measured **265.107× headless** and **7.798× headless/render-K4** relative to full stepping. It used 64 short death-stopped episodes, five rounds, and an earlier identified core source. Those ratios are **not final-core or PPO speedups**. Later metadata timings overlapped noise and establish no causal overhead result.

The accepted M2 B32 public step/reset workload measured:

| Rendering | Threads / chunk | Calls per second |
| --- | --- | ---: |
| Headless | 1 / 1 | 8,281.09 |
| Headless | 4 / 8 | 9,412.90 |
| Rendered | 1 / 1 | 1,548.50 |
| Rendered | 4 / 8 | 3,481.72 |

These single measurements include feature extraction, returned arrays, resets, and limited bookkeeping; construction/warmup are excluded. They do not measure PPO. Full evidence and workload limits are in [environment results](v2-environment-results.md) and the [foundation facts](../learning/runs/v2/overnight-report-facts-r1/foundation.md).

## Measured baselines

Each row below uses 1,000 paired original-engine episodes, patterns/powerups enabled, K=4, and an 18,000-frame cap. Alive frames use the 60 Hz timebase. Capped observations are censored.

| Difficulty | Policy | Mean raw score | Mean alive frames | Caps |
| --- | --- | ---: | ---: | ---: |
| D2 | Random | 0.353 | 255.323 | 0/1,000 |
| D2 | Neutral | 0.340 | 187.861 | 0/1,000 |
| D2 | AABB safe-powerup heuristic | 100.1075 | 6,114.593 | 15/1,000 |
| D3 | Random | 0.338 | 198.354 | 0/1,000 |
| D3 | Neutral | 1.884 | 152.966 | 0/1,000 |
| D3 | AABB safe-powerup heuristic | 88.633 | 4,030.038 | 2/1,000 |

Across baseline configurations, observed maxima were 18 enemy-family records and 16 rectangles. Defaults remain 64/16 with overflow safeguards; these measurements do not prove a universal capacity bound. Full distributions, original-engine identities, profiling, and D1 sanity are in [D2 baseline results](v2-baseline-results.md) and [D3/D1 baseline results](v2-gate-baseline-results.md).

## Bounded learning results

All four runs executed once against frozen inputs. No failed experiment was silently retried or given relaxed limits. Development results below use the fixed **64 D seeds**, separate from the 1,000-episode baseline cohort and unopened final qualification sets.

| Run | Accounted seconds | Complete progress added | Development result | Outcome |
| --- | ---: | --- | --- | --- |
| Device probe | 60.071293 | Matched 16,384 transitions, four epochs, 128 Adam steps per device | CPU inference+update 36.2354 s; MPS 16.4507 s | Passed; MPS accepted after independent audit; probe weights remain diagnostic |
| Fresh D1 pilot | 276.386837 | 16 updates / 2,048 Adam steps | Mean score 0.03125 to 3.921875; alive frames 223.140625 to 990.296875 | Passed the paired improvement rule; below D1 competence floors |
| D1 curriculum | 554.345191 | 32 updates / 4,096 Adam steps | Mean score 12.109375; alive frames 1,917.53125; 7 deaths / 57 caps | Passed D1 progress floors of score 10 and 1,500 alive frames |
| D2 curriculum | 1,800.439150 | 104 complete updates / 13,248 complete Adam steps, plus 69 partial steps | Last complete evaluation: score 8.9140625; alive frames 1,148.78125; 64 deaths / 0 caps | Failed the 1,800-second wall guard; all seven evaluations failed progress |

D1 evaluations had a 2,000-frame cap, restricting the final mean with 57/64 capped episodes. D2 used an 18,000-frame cap and progress floors of score 50 and 3,060 alive frames. Those floors were development progress criteria, not final teacher qualification.

D2 supervisor, worker, and wrapper exits were **1**. Its 1,800.439150 accounted seconds include cooperative stop/checkpoint/cleanup after the 1,800-second guard; the training budget was not extended. Totals including the pilot and D1 are **152 complete updates and 19,461 actual Adam steps**, including the final 69 partial steps. D2 sampled RSS high-water was **952,745,984 bytes**; MPS driver maximum was **2,456,387,584 bytes**. Each was below its separate 6 GiB cooperative guard; they are not an additive memory measurement or hard OS ceiling.

The last complete D2 evaluation occurred at phase update **96**, using `checkpoint-000022-candidate.pt`. It does **not** evaluate the final phase-104-plus-partial weights. The final `checkpoint-000024-interrupted_mid_update.pt` is ineligible. All 15 D2 checkpoints, including earlier candidates, remain diagnostic and cannot authorize a successor after the failed run.

## Retained provenance

| Artifact | SHA256 |
| --- | --- |
| [D1 accepted candidate](../learning/runs/v2/milestone3-D1-curriculum-r1/checkpoint-000009-candidate.pt) | `ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f` |
| [D2 frozen identity](../learning/runs/v2/milestone3-D2-freeze-r1/D2-frozen-identity.json) | `56dcf1ba848c2e2acdca967ce8ed5bca9457551659421a9070c2f7c5ba2bc14f` |
| [D2 execution result](../learning/runs/v2/milestone3-D2-execution-r1/result.json) | `a07005def4bcf0b3bc75dd97731d2b04ead87a344528758f6af2160b37e11c59` |
| [D2 run result](../learning/runs/v2/milestone3-D2-curriculum-r1/run-result.json) | `3b726c8c522e8c44b5d4827abe6b176defc5e4f5653e0e883091eb1e3a9e2250` |
| [Last evaluated D2 candidate](../learning/runs/v2/milestone3-D2-curriculum-r1/checkpoint-000022-candidate.pt) | `2d598e1973ded1748ec18d59ed11abe524b2f2a9d68c8796d105266a31d4e8b6` |
| [Interrupted D2 checkpoint](../learning/runs/v2/milestone3-D2-curriculum-r1/checkpoint-000024-interrupted_mid_update.pt) | `bc0bb18106d52ca2e133fc6123263779660a4324c031b2b4ca5ad3b0741ae194` |
| [Independent D2 failure audit](../learning/runs/v2/milestone3-D2-parent-audit-r1/audit.json) | `08a0d4e409ef7a857fc3aa2be0722e46b7871f38921f169152cd63cf45d35cea` |
| [Stable report facts](../learning/runs/v2/overnight-report-facts-r1/facts.json) | `a23f23f4daa8629b38dc7ef1afb2a75c1016789a79d8d07df2526f02175c3078` |

No old checkpoint metadata was changed. Entry model/Adam/RNG equality supports curriculum continuity; it does not establish uninterrupted gameplay replay.

## Limitations and remaining work

Free OpenCode reviews could not return a verdict because quota was exhausted. Errors and exact-task cancellations are retained; independent Codex fallback reviews were reconciled against frozen source. A missing free-model verdict is not recorded as a pass. Opus supplied substantive read-only design and diagnosis.

Provenance gaps remain explicit: intermediate develop extension binaries were overwritten before independent binary archival; an M2 original-control receipt labels live repaired source while its explicit command selects a separately pinned original; and one initial failing M3 test fixture was hash-recorded without its full source archive. Final installed binary/wheel, corrected test versions, and negative controls were independently verified. These caveats are not repaired by later passing results.

The [Opus D2 diagnosis and parent reconciliation](../learning/runs/v2/milestone3-D2-plateau-diagnosis-r1/parent-reconciliation.json) retain hypotheses of limited D2 experience, pattern distribution shift, and stochastic training versus argmax evaluation. No cause or feature defect was proven. Parent parsing corrected the captured-prefix counts to **97 complete D2 updates, 1,589,248 new decision transitions, 14,189 episode-stream rows, and 7,530 native completed D2 episodes**. Those prefix counts are distinct from the terminal totals above. Captured metrics were finite; observed unknown-motion samples alone do not establish a feature bug.

Future work starts with retained-data episode/phase parsing, early-death and admission-history analysis, and a separately bounded stochastic-versus-argmax comparison if authorized. Further training needs a new reviewed recovery/budget plan; failed D2 artifacts cannot be resumed or advanced under the existing protocol. Do not lengthen D2 or change rewards/gates based on untested hypotheses.

D3 could not fit its full 1,800-second stage plus 600-second reserve before cutoff. Final B qualification and E replication remain unopened. The teacher still must pass the immutable D2 **and** D3 score-and-survival gate against the measured heuristic. Visual palette embeddings, 8px patches, staged distillation/auxiliary losses, and student work remain deferred.
