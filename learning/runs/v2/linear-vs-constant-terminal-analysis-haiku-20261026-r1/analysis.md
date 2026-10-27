# Linear vs constant LR: terminal analysis (D2 retained-324, r1)

Scope: closed JSON/JSONL analysis only. No checkpoint binary loads, model imports, environment runs, launches, leases, or shared-state edits. No B/E/D3/student data.

## Arms

| Arm | Run dir | LR |
|---|---|---|
| fixed (control) | `learning/runs/v2/D2-retained324-continuation-20261026-r1/` | constant 3e-5 (not recorded in metrics; inferred, see Limitations) |
| linear | `learning/runs/v2/D2-retained324-linear-lr-20261026-r1/` | 3e-5 to 1e-5 linear over 60 updates, origin cumulative 372, then hold |

Shared start: parent `c10d90ec…` (master 4200000001). Both arms restored model, Adam, RNG to the same hashes (`entry-restoration.json`). Both: 60 updates, 128 optimizer steps/update, 4 epochs, 7680 optimizer steps total, `actual_worker_launch_count` 1, `status` passed, `promoted` false, `training_eligible` false.

Eval: 64 development episodes per checkpoint, same 64 seeds in the same order at every phase, both arms. Phase 324 rows are identical across arms (same starting checkpoint).

## 1. Development certs (all 6 per arm)

| Phase (local upd) | Arm | Mean alive | Q1 / Q4 alive | Mean score | n alive ≥3060 | Recorded competence |
|---|---|---|---|---|---|---|
| 324 (0) | fixed | 2939.4 | 767.5 / 5468.7 | 29.53 | 29 | False |
| 324 (0) | linear | 2939.4 | 767.5 / 5468.7 | 29.53 | 29 | False |
| 336 (12) | fixed | 2708.3 | 719.3 / 5259.9 | 27.33 | 24 | False |
| 336 (12) | linear | 2531.3 | 644.1 / 4673.8 | 23.93 | 20 | False |
| 348 (24) | fixed | 2351.7 | 664.6 / 4491.9 | 22.11 | 18 | False |
| 348 (24) | linear | **3098.1** | 867.1 / 6003.9 | 31.52 | 29 | **True** |
| 360 (36) | fixed | 2372.7 | 655.9 / 4768.6 | 22.79 | 18 | False |
| 360 (36) | linear | 2535.1 | 835.4 / 4831.3 | 24.46 | 20 | False |
| 372 (48) | fixed | 2561.3 | 662.1 / 4762.6 | 24.63 | 23 | False |
| 372 (48) | linear | 2646.6 | 755.8 / 5093.8 | 26.73 | 21 | False |
| 384 (60) | fixed | 2648.4 | 702.4 / 5087.4 | 27.15 | 22 | False |
| 384 (60) | linear | **2270.6** | 637.9 / 4431.8 | 21.79 | 18 | False |

Recorded competence flag equals `mean_alive_frames ≥ 3060` for all 12 certs (threshold per the pinned survival gate; `D2-retained276-lr3em5-prepare-luna-20261026-r2/execute_once.py:274`). It is a gate flag, not formal acceptance.

Full phase table: `phase-metrics.csv`.

## 2. Retained best vs fixed endpoint

- **Retained best (linear 348)**: 3098.1 vs incumbent 324 (2939.4): +158.7. vs fixed 348 (2351.7): +746.5.
- **Fixed endpoint (linear 384)**: 2270.6 vs fixed 384 (2648.4): −377.8.
- Within-arm 348→384 paired change: linear −827.5 (SE 274); fixed +296.7 (SE 303).
- Trajectories are noisy in both arms (eval-to-eval swings of several hundred frames). Linear: 2939 → 2531 → 3098 → 2535 → 2647 → 2271. Fixed: 2939 → 2708 → 2352 → 2373 → 2561 → 2648.

Reading:
- 348 is the maximum of six noisy dev evaluations on the same 64 seeds. That is selection on the dev set. The +746 gain (paired SE 336; nominal 95% CI roughly [75, 1418]) does not account for picking the max, so it is optimistic.
- 384 is the unselected end of the trial. It is below fixed 384 by 378 (SE 298, CI roughly [−973, 217]).
- The evidence does not show a sustained improvement from linear decay. It shows one high dev point mid-trial and a lower endpoint.

## 3. Paired per-seed differences (linear − fixed, alive frames, 64 seeds)

| Phase | Mean diff | SE | Gains / losses / ties | Median diff | Sum of gains / sum of losses | Mean score diff |
|---|---|---|---|---|---|---|
| 336 | −177.0 | 330 | 32 / 32 / 0 | −26 | 61335 / −72664 | −3.40 |
| 348 | **+746.5** | 336 | 40 / 24 / 0 | +663 | 93114 / −45341 | +9.41 |
| 360 | +162.5 | 288 | 35 / 29 / 0 | +178.5 | 64645 / −54246 | +1.67 |
| 372 | +85.3 | 320 | 32 / 32 / 0 | −71 | 67574 / −62118 | +2.10 |
| 384 | **−377.8** | 298 | 30 / 34 / 0 | −130 | 46966 / −71144 | −5.36 |

Per-seed rows: `paired-per-seed.csv`.

## 4. Death-cause shifts (descriptive only)

Counts (fixed → linear):

| Cause | 348 | 384 |
|---|---|---|
| normal_enemy | 29 → 25 | 19 → 28 |
| kamikaze_enemy | 10 → 15 | 19 → 11 |
| kamikaze_explosion | 2 → 0 | 0 → 1 |
| moving_pattern_rect | 4 → 9 | 9 → 9 |
| static_pattern_rect | 19 → 15 | 17 → 15 |

Death cause changed on 47 of 64 seeds at 348 and 39 of 64 at 384. Labels are unstable across checkpoints, so per-category shifts are weak evidence.

Conditional mean alive frames by cause (fixed / linear; n in parentheses where small):

| Cause | 348 | 384 |
|---|---|---|
| normal_enemy | 2027 (29) / 3240 (25) | 2524 (19) / 2385 (28) |
| kamikaze_enemy | 1988 (10) / 2489 (15) | 2043 (19) / 1998 (11) |
| static_pattern_rect | 3407 (19) / 4057 (15) | 3642 (17) / 3106 (15) |
| moving_pattern_rect | 1422 (4) / 2123 (9) | 2313 (9) / 1042 (9) |
| kamikaze_explosion | 713 (2) / — (0) | — (0) / 600 (1) |

These conditional means average over different death sets per arm and are not causal. Do not read them as "linear survives longer against normal enemies."

## 5. Training metrics (60 updates, both arms)

Realized LR:
- Fixed: 3e-5 (inferred; lu1 metrics identical across arms, which requires equal LR at local 1).
- Linear: `lr = 3e-5 − 2e-5·(k−1)/59` at local update k (schedule.py formula). Mean 2e-5. At local 24 (selected 348): **2.2203e-5**. At local 60 (endpoint 384): **1.00e-5**.
- Total LR mass: linear 60 × 2e-5 = 1.2e-3; fixed 60 × 3e-5 = 1.8e-3.

Means over 60 updates (fixed / linear); late = last 10 updates:

| Metric | Fixed | Linear | Note |
|---|---|---|---|
| approx_kl | 0.00601 (late 0.00608) | 0.00432 (late 0.00268) | linear lower |
| clip_fraction | 0.0314 (late 0.0323) | 0.0191 (late 0.0086) | linear lower |
| entropy | 1.659 (late 1.658) | 1.649 (late 1.647) | ~same |
| EV pre-update (in-sample) | 0.383 | 0.415 | linear higher |
| EV post-update (in-sample) | 0.409 | 0.434 | linear higher |
| target variance (pre) | 0.0626 | 0.0636 | ~same |
| residual MSE (post) | 0.0369 | 0.0359 | ~same |
| value loss | 0.01884 | 0.01825 | ~same |
| actor grad norm | 0.545 | 0.568 | ~same |
| critic grad norm | 0.0427 | 0.0424 | ~same |
| gradient alignment cosine | −0.003 | +0.006 | both ≈0, range ±0.27 |

Other:
- Optimizer steps: 128 per update, 7680 total, both arms. Epochs completed: 4 every update.
- Early-stop-KL count: 0 both arms.
- All updates `finite` true both arms.
- Counters match (updates 60; environment_decisions 983040). Raw frames differ by 109 (3929306 linear vs 3929197 fixed).

Descriptive pattern: the linear arm has smaller KL and clip fraction, most visibly in the late updates. That fits a smaller effective step size. Critic EV is slightly higher, and entropy is essentially unchanged. The arms are not matched after update 1 (different LR → different batches and weights), so these differences are not causal. Critic EV uses self-bootstrapped in-sample targets (`fit_scope: in_sample_self_bootstrapped_targets;not_held_out`), so it is not a generalization measure.

Was the lower endpoint associated with smaller LR, critic fit, or entropy shifts? The smaller LR is present, and the critic-fit and entropy shifts are small or unfavorable to the lower endpoint. Nothing here isolates a cause. Endpoint gap is inside noise. Also, LR average (2e-5) and schedule shape are confounded: no constant-2e-5 arm exists.

Per-update table: `training-per-update.csv`.

## 6. Limitations

1. Checkpoint file hashes differ between arms at 324 (`bffa63a8…` fixed vs `d976b257…` linear) even though their 324 dev rows, entry-restoration hashes, and metrics match. Cause not determined. Would need binary inspection, which this brief forbids.
2. Fixed-arm LR is not recorded in `training-metrics.jsonl`. 3e-5 is inferred from brief and lu1 equality.
3. All selection and comparison use the same 64 dev seeds. 348 was selected on them. The endpoint is not held-out. The upper D64 supplemental eval is still in preparation. This is not a scientific independent holdout.
4. Formal acceptance of the linear arm is pending the narrow auditor instantiation repair. `competence_passed` is not acceptance.
5. Death-cause categories are unstable across checkpoints (see §4).
6. n = 1 pair of trainings. One seed family. No variance across training seeds.

## 7. Next operational experiment (proposal only, not authorized)

Precondition: parent acceptance of linear 348 is complete (not the endpoint 384).

Experiment "hold-348-LR":
- Start: accepted linear-348 checkpoint (`b95228e5…`).
- Restore model, Adam, and RNG exactly to that checkpoint's saved state. Verify against its entry-restoration hashes, as in `entry-restoration.json`.
- LR: constant 2.2203e-5 (realized LR at 348). No further decay. No scheduler restart.
- Transition: explicit new controller mode with a receipt naming the parent sha, the prior schedule state (completed 24 of 60, origin 372), the new constant mode, and the LR value. Do not silently reset the completed 24 updates.
- Run 12 updates, evaluate at 360/372/384 on the same 64 dev seeds.
- Compare to linear 348 (3098.1), linear 384 (2270.6), and fixed 384 (2648.4).
- Decision rule to be pre-registered before running. Any claim beyond dev must wait for the upper D64 evaluation.

Why this one: the evidence is weak either way. Late linear updates had low KL and clip, so the decayed LR does not look destabilizing. The 348→384 drop is larger than fixed's, which is consistent with "decayed too far," but noise is also plausible. Holding LR tests that directly.

## Evidence sources

| Artifact | SHA-256 (prefix) |
|---|---|
| fixed `development-000324.json` | `91933896…` |
| fixed `development-000348.json` | `f9ad28da…` |
| fixed `development-000384.json` | `b1b02f1f…` |
| linear `development-000324.json` | `7376a842…` |
| linear `development-000348.json` | `f0da1736…` |
| linear `development-000384.json` | `7fd51bc0…` |
| fixed `training-metrics.jsonl` | `2229013e…` |
| linear `training-metrics.jsonl` | `588cbd13…` |
| fixed `execution-result.json` | `534ea0e9…` |
| linear `execution-result.json` | `7dad18c1…` |
| linear `entry-restoration.json` | `c1f42d43…` |
| linear `checkpoint-000348-candidate.pt.json` | `efec8e2a…` |
| linear `checkpoint-000384-candidate.pt.json` | `67b91f0b…` |
| `D2-retained324-linear-schedule-prepare-luna-20261026-r1/schedule.py` | `35fee3a7…` |

Checkpoint `.pt` binary hashes (from `artifact-manifest.json`): fixed 324 `bffa63a8…`, fixed 348 `d296614a…`, fixed 384 `e25117bf…`; linear 324 `d976b257…`, linear 348 `b95228e5…`, linear 384 `cc5c3bee…`.

Generated tables: `phase-metrics.csv`, `paired-per-seed.csv`, `training-per-update.csv`, built by `build_tables.py` (run with `python3 -I build_tables.py <this_dir>`).
