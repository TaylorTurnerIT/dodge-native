# Checkpoint 420 deaths: fyou, patterns and death-frame scenarios

Date: 2026-10-29. Branch `t3/death-telemetry-fyou-patterns`. Notebook record: DODGE-014. Inference only: no training, selection or promotion.

## Answer in brief

Evidence: 8,192 fresh complete games (checkpoint 420, 2,048 new seeds, four action settings) plus 2,048 games from the DODGE-012 D8 cohort that reproduce the saved rows exactly. Phases are by `alive_frames`.

1. **fyou is almost absent from deaths.** At 1-frame argmax, 2.3% of 0-1k deaths (3 of 129) had any fyou trigger before death; at 4-frame argmax, 0.4% (1 of 284). Across all phases, 2.9% (1-frame) and 1.1% (4-frame) of games ever triggered fyou at all, and sampled 4-frame games never did (0 of 2,048). The policy leaves the central box in the first few dozen frames and does not camp. The fyou-spawned share of enemy kills is 0.6% (7 of 1,227, 1-frame argmax) and 0.3% (4 of 1,398, 4-frame argmax). **fyou does not explain the 40-60% normal-enemy share.** Normal-enemy killers are ordinary spawns, mostly 101-300 frames old.
   - When fyou does trigger, the next 300 frames are riskier: 27 deaths against 6.9 expected at the same phase's never-triggered rate (3.9x, 95% interval 2.6-5.7, pooled over all four settings; sampled 4-frame has no triggers). That is observational and rests on 27 deaths, and it touches under 3% of games.
2. **Patterns are the main hazard, and a few specific ones dominate.** A pattern is active in 42-49% of frames but in 91-96% of 1-frame argmax deaths (88-94% at 4-frame argmax): 14-27x the death rate of pattern-free frames at 1-frame control, 10-20x at 4-frame control.
   - 0-1k killers (share of that window's deaths): 1-frame argmax: id 28 (22%), 32 moving (18%), 18 (16%), 9 moving (7%), 2 (5%). 4-frame argmax: 28 (20%), 18 (18%), 8 moving (12%), 32 moving (6%), 2 (6%).
   - From 1k on, pattern 3 and its transposed sibling 4 lead (1-frame argmax 1k-2k: 3 = 24%, 4 = 13%); 3 killed in 70% of its encounters at 1-frame control and 74% at 4-frame control. Pattern 4 kills in 40% (1-frame) and 57% (4-frame), so the mirrored variant is much safer.
   - After 3k, score-gated static patterns take over (13, 14, 25, 26, 29, 36-39, 19, 20, 21). At 1-frame argmax, 13/14/25/26 were survived in 1 of 355 encounters; at 4-frame argmax in 0 of 155. They are mostly enemy kills made while the pattern is active (rectangle contact is 15-47% of their deaths).
   - Deaths come 61-600 frames after a pattern starts (84-94% of pattern deaths in the argmax settings), not at its start (1-14% within 60 frames).
3. **Other common features.** Few enemies are on screen (mean 4.1-4.6 others; 0% have 15+), the player is almost never in the fyou box (0-2%), 37-62% die within 20 px of an edge and 2-6% in a corner, and the killer enemy is usually 101-300 frames old (50-61% in the argmax settings). These have no base rate in the data (see caveats).
4. **1-frame versus 4-frame.** Hazard per phase is 7-16 percentage points lower at 1 frame (P(die in 0-1k) 6.3% vs 13.9%). The cause mix differs mainly in 0-1k, where normal enemies are 40% vs 54% of deaths. fyou and pattern conclusions are the same in both settings.

## What was built

- `crates/dodge-core/src/trace.rs`: `RunTrace`, an ephemeral observation-only recorder in the style of `death.rs`. It is off by default, absent from snapshots, `Eq` is constant, and it touches no RNG, reward, collision, spawn, or feature code. It records every `update_fyou` firing and the enemy birth ordinals it spawned, every pattern encounter (id, type, start, end), and at the first lethal contact: killer personality, fyou provenance and age, other enemies on screen, fyou-spawned enemies on screen, player position and velocity, consecutive center-dwell frames, the game's own fyou timer and enable flag, the active pattern with frames since it started, and the last pattern end. Frames are gameplay frames (startup excluded), so the death frame equals `fatal_gameplay_frame`.
- `EnvConfig.trace` / Python `VecDodgeEnv(..., trace=True)`: `info["trace"]` on ended episodes only. `action_repeat=1` is now accepted, matching the one-frame successor runtime used for DODGE-012 (the only dodge-core/env difference from that build).
- Tests: Rust trace tests (trace on/off gives identical `FullState` including RNG every frame across 4 seeds x 4 policies, fyou timing and independent birth-count check, killer attribution, killer age, pattern spans, reset/restore) and an env-level on/off test for repeat 1 and 4. Python tests for the extension (on/off identical observations, rewards and info; trace matches env counters) and for the aggregation helpers.

## Replay-parity gate (passed before any trace was interpreted)

The same checkpoint (sha256 `7e0de864...ed4b`, weights fingerprint unchanged before and after), MPS float32, the saved loop and group seeds, and the new build reproduced all 8 saved groups: argmax 1-frame and 4-frame, and sampled 1-frame and 4-frame for all three saved controller seeds, 256 seeds each, 2,048 games. `seed`, `alive_frames`, `gameplay_frames`, `death_cause`, `fatal_gameplay_frame`, `score_raw_fixed`, `terminated` and `truncated` match in all 2,048 games (0 mismatches); trace frame, death frame and death cause also agree with the env's own counters. Receipt: `parity-gate.json` (with hashes of both sides).

## Data and method

- Fresh cohort: 2,048 consecutive seeds 3657433088-3657435135 (0xDA000000-0xDA0007FF), run for argmax and sampled at 1-frame and 4-frame decisions. Not training, not any recorded evaluation exclusion range, not D8 or D9, not in the 189,743-seed conservative history list, and no cohort reservation, state-ledger entry or exclusion range I could read in the other thread's worktree overlaps it. This is a diagnostic cohort: it was not used to select anything, and the other thread should record it as consumed. Sampled fresh groups use one new controller seed (202610291401) per setting. Sampled D8 groups pool the three saved controller seeds (768 games over 256 seed clusters).
- All 8,192 fresh games ended in death; none reached the 18,000-frame cap. P(die) in `5k+` is therefore 100% by construction; read the per-frame rates there.
- Intervals: 95% percentile bootstrap, 2,000 draws, resampling seeds (all games of a seed stay together; 1-frame and 4-frame share the same draws, so contrasts are paired). Every statistic is a ratio of sums over games.
- Phase of death by `alive_frames`: 0-1k, 1k-2k, 2k-3k, 3k-5k, 5k+. Hazard = P(die in the phase | alive at its start). Rates use frames lived in the phase. A pattern encounter belongs to the phase in which it started; "deaths during" an encounter counts any cause while that pattern was active; "rect deaths" count only rectangle contact. "Observed / expected" divides an id's deaths by those expected if each of its encounters died at its start phase's overall rate (removes the late-game confound; it does not remove score gating or the policy's position in the pattern).
- Compute: MPS, torch 2.14.1, 2 threads per process, up to 5 concurrent processes; peak RSS 421-564 MB, peak MPS 184 MB (caps were 6 GiB each); run under `caffeinate -ims` on AC power. No other Dodge training or evaluation process was running.

**Phase hazard.** Games alive at the phase start, P(die in the phase), and deaths per 10k frames lived. No game reached the 18,000-frame cap, so every game ends in a death and P(die) in `5k+` is 100% by construction; use the per-frame rate there.

| phase | 1-frame alive | 1-frame P(die) | 1-frame / 10k frames | 4-frame alive | 4-frame P(die) | 4-frame / 10k frames |
|---|---|---|---|---|---|---|
| 0-1k | 2,048 | 6.3% [5.2, 7.4] | 0.64 [0.53, 0.76] | 2,048 | 13.9% [12.5, 15.5] | 1.46 [1.30, 1.63] |
| 1k-2k | 1,919 | 10.6% [9.2, 12.0] | 1.10 [0.95, 1.25] | 1,764 | 17.9% [16.1, 19.7] | 1.90 [1.69, 2.11] |
| 2k-3k | 1,715 | 14.5% [12.8, 16.2] | 1.54 [1.35, 1.73] | 1,449 | 25.5% [23.3, 27.6] | 2.88 [2.60, 3.17] |
| 3k-5k | 1,467 | 44.3% [41.8, 46.9] | 2.83 [2.63, 3.05] | 1,080 | 60.0% [57.2, 62.8] | 4.35 [4.05, 4.66] |
| 5k+ | 817 | 100.0% [100.0, 100.0] | 6.24 [5.88, 6.66] | 432 | 100.0% [100.0, 100.0] | 9.22 [8.51, 10.01] |

**Cause share of deaths, 1-frame decisions.**

| phase | deaths | normal | kami body | kami blast | static rect | moving rect |
|---|---|---|---|---|---|---|
| 0-1k | 129 | 40% [31, 48] | 16% [9, 22] | 5% [2, 10] | 8% [3, 13] | 32% [24, 40] |
| 1k-2k | 204 | 54% [47, 61] | 15% [10, 20] | 2% [0, 5] | 16% [11, 21] | 12% [8, 17] |
| 2k-3k | 248 | 41% [35, 47] | 11% [8, 15] | 4% [2, 7] | 38% [31, 44] | 6% [3, 9] |
| 3k-5k | 650 | 44% [41, 48] | 15% [12, 18] | 2% [1, 3] | 34% [30, 37] | 5% [4, 7] |
| 5k+ | 817 | 43% [40, 47] | 12% [10, 14] | 1% [1, 2] | 41% [38, 44] | 2% [1, 3] |

**Cause share of deaths, 4-frame decisions.**

| phase | deaths | normal | kami body | kami blast | static rect | moving rect |
|---|---|---|---|---|---|---|
| 0-1k | 284 | 54% [48, 59] | 11% [8, 15] | 4% [1, 6] | 8% [5, 11] | 24% [19, 29] |
| 1k-2k | 315 | 55% [49, 60] | 19% [14, 23] | 1% [0, 2] | 13% [9, 17] | 13% [9, 17] |
| 2k-3k | 369 | 53% [48, 58] | 17% [13, 20] | 1% [0, 2] | 25% [21, 30] | 5% [3, 7] |
| 3k-5k | 648 | 52% [49, 56] | 14% [11, 17] | 1% [0, 2] | 28% [24, 31] | 5% [3, 7] |
| 5k+ | 432 | 48% [43, 53] | 15% [12, 19] | 1% [0, 2] | 34% [30, 39] | 2% [0, 3] |

**fyou before death.** Share of each phase's deaths preceded by any fyou trigger (n triggered / deaths), and killer enemy spawned by fyou (n / enemy-kill deaths).

| phase | 1-frame any trigger | 1-frame fyou killer | 4-frame any trigger | 4-frame fyou killer |
|---|---|---|---|---|
| 0-1k | 2.3% [0.0, 5.3] (3/129) | 3/78 | 0.4% [0.0, 1.2] (1/284) | 1/194 |
| 1k-2k | 2.0% [0.5, 4.0] (4/204) | 1/147 | 1.0% [0.0, 2.1] (3/315) | 1/234 |
| 2k-3k | 3.2% [1.2, 5.5] (8/248) | 1/140 | 1.6% [0.5, 3.1] (6/369) | 2/258 |
| 3k-5k | 2.2% [1.1, 3.3] (14/650) | 2/397 | 0.9% [0.3, 1.8] (6/648) | 0/435 |
| 5k+ | 3.8% [2.5, 5.2] (31/817) | 0/465 | 1.6% [0.5, 2.9] (7/432) | 0/277 |

**Pattern base rate.** Share of frames with a pattern active, share of deaths with a pattern active, and death rate per 10k frames lived with a pattern active versus inactive.

| decisions | phase | frames pattern active | deaths with pattern active | deaths / 10k active | deaths / 10k inactive |
|---|---|---|---|---|---|
| 1-frame | 0-1k | 44% [43, 44] | 91% [87, 96] | 1.35 [1.11, 1.60] | 0.10 [0.04, 0.16] |
| 1-frame | 1k-2k | 46% [46, 47] | 92% [88, 96] | 2.20 [1.89, 2.51] | 0.16 [0.09, 0.24] |
| 1-frame | 2k-3k | 43% [42, 43] | 95% [92, 97] | 3.42 [2.99, 3.87] | 0.14 [0.07, 0.22] |
| 1-frame | 3k-5k | 49% [48, 50] | 96% [95, 98] | 5.56 [5.14, 5.99] | 0.20 [0.13, 0.29] |
| 1-frame | 5k+ | 48% [47, 49] | 94% [92, 96] | 12.25 [11.45, 13.18] | 0.73 [0.55, 0.93] |
| 4-frame | 0-1k | 43% [42, 43] | 94% [91, 96] | 3.20 [2.84, 3.62] | 0.16 [0.09, 0.23] |
| 4-frame | 1k-2k | 46% [45, 47] | 92% [89, 95] | 3.79 [3.37, 4.25] | 0.28 [0.18, 0.39] |
| 4-frame | 2k-3k | 42% [41, 43] | 88% [85, 92] | 6.02 [5.40, 6.68] | 0.58 [0.41, 0.76] |
| 4-frame | 3k-5k | 49% [49, 50] | 93% [91, 95] | 8.23 [7.61, 8.82] | 0.57 [0.42, 0.74] |
| 4-frame | 5k+ | 48% [47, 50] | 91% [89, 94] | 17.43 [15.95, 19.18] | 1.57 [1.11, 2.03] |

**Patterns that kill in each phase, 1-frame decisions.** Top five pattern ids by deaths with that pattern active; share of the phase's deaths.

| phase | 1st | 2nd | 3rd | 4th | 5th |
|---|---|---|---|---|---|
| 0-1k | 28 (sta): 28 (22%) | 32 (mov): 23 (18%) | 18 (sta): 20 (16%) | 9 (mov): 9 (7%) | 2 (sta): 6 (5%) |
| 1k-2k | 3 (sta): 49 (24%) | 4 (sta): 27 (13%) | 28 (sta): 24 (12%) | 18 (sta): 14 (7%) | 8 (mov): 11 (5%) |
| 2k-3k | 3 (sta): 47 (19%) | 28 (sta): 24 (10%) | 21 (sta): 22 (9%) | 4 (sta): 21 (8%) | 36 (sta): 18 (7%) |
| 3k-5k | 3 (sta): 82 (13%) | 21 (sta): 55 (8%) | 4 (sta): 51 (8%) | 38 (sta): 46 (7%) | 36 (sta): 42 (6%) |
| 5k+ | 29 (sta): 93 (11%) | 13 (sta): 72 (9%) | 14 (sta): 69 (8%) | 20 (sta): 69 (8%) | 25 (sta): 58 (7%) |

**Patterns that kill in each phase, 4-frame decisions.** Top five pattern ids by deaths with that pattern active; share of the phase's deaths.

| phase | 1st | 2nd | 3rd | 4th | 5th |
|---|---|---|---|---|---|
| 0-1k | 28 (sta): 57 (20%) | 18 (sta): 50 (18%) | 8 (mov): 35 (12%) | 32 (mov): 18 (6%) | 2 (sta): 17 (6%) |
| 1k-2k | 28 (sta): 48 (15%) | 3 (sta): 39 (12%) | 18 (sta): 36 (11%) | 4 (sta): 32 (10%) | 8 (mov): 16 (5%) |
| 2k-3k | 3 (sta): 45 (12%) | 4 (sta): 39 (11%) | 28 (sta): 38 (10%) | 18 (sta): 31 (8%) | 21 (sta): 31 (8%) |
| 3k-5k | 3 (sta): 65 (10%) | 21 (sta): 65 (10%) | 28 (sta): 52 (8%) | 39 (sta): 39 (6%) | 4 (sta): 37 (6%) |
| 5k+ | 29 (sta): 51 (12%) | 25 (sta): 32 (7%) | 20 (sta): 30 (7%) | 22 (sta): 30 (7%) | 19 (sta): 26 (6%) |

**fyou followed by deaths (phase-standardized).** Deaths in the 300 frames after the last trigger, against deaths expected at each phase's never-triggered rate over the same frames.

| setting | deaths in 1-300 frames after a trigger | expected | frames | observed / expected |
|---|---|---|---|---|
| 1-frame argmax | 9 | 2.7 | 16,996 | 3.4 [1.4, 6.3] |
| 4-frame argmax | 8 | 1.4 | 5,600 | 5.9 [2.3, 11.6] |
| 1-frame sampled | 10 | 1.3 | 7,574 | 7.7 [3.4, 14.9] |
| 4-frame sampled | 0 | 0 | 0 | no triggers |
| pooled | 27 | 6.9 | 30,170 | 3.9 [2.6, 5.7] |

**Hazard split by whether fyou had triggered before the phase started.** Too few games had triggered (28-34 of about 1,900 alive at the start of 1k-2k, 2k-3k and 3k-5k at 1-frame control; 7-12 at 4-frame control), so every difference has an interval spanning zero (for example 1-frame, 3k-5k: 35% [19, 52] with a prior trigger vs 45% [42, 47] without). These are in `tables-fresh.md`.

## Per-pattern results (argmax)

"Death / encounter" counts any death while the pattern was active; "rect" counts only rectangle contact. The table is sorted by id; the complete table with intervals and all four settings is in `tables-fresh.md` and the JSON. Highlights, 1-frame argmax / 4-frame argmax:

| id (type, family) | encounters | death / encounter | rect / encounter | observed / expected |
|---|---|---|---|---|
| 28 (static) | 831 / 758 | 15% / 28% | 1% / 3% | 0.97 / 1.19 |
| 18 (static) | 835 / 703 | 8% / 22% | 1% / 4% | 0.54 / 0.97 |
| 32 (moving, 30-33) | 229 / 216 | 22% / 19% | 16% / 9% | 1.32 / 0.82 |
| 8 (moving, 5-8) | 223 / 202 | 11% / 34% | 6% / 27% | 0.69 / 1.51 |
| 3 (static, 3+4) | 264 / 211 | 70% / 74% | 34% / 29% | 3.15 / 2.32 |
| 4 (static, 3+4) | 267 / 205 | 40% / 57% | 9% / 14% | 1.76 / 1.80 |
| 29 (static) | 137 / 69 | 77% / 96% | 66% / 77% | 1.58 / 1.67 |
| 36-39 (static, one family) | 69-105 / 54-81 | 77-88% / 84-93% | 29-72% / 27-69% | 2.3-2.7 / 1.9-2.2 |
| 13, 14, 25, 26 (static) | 82-97 / 27-57 | 99-100% / 100% | 18-47% / 15-42% | 2.0-2.4 / 1.6-1.9 |

Counts are small after 3k for the rarest ids; see the full table. Early (0-1k) moving-rectangle deaths are 32% [24, 40] of 1-frame and 24% [19, 29] of 4-frame argmax deaths, consistent with the existing 27% figure, and are spread over the moving families (5-8, 9-12, 30-33) rather than one id. Static rectangles become the largest rectangle cause after 2k (34-41% of deaths past 3k at 1-frame, 28-34% at 4-frame).

## Predictions registered before the fresh run (DODGE-014)

1. At least 40% of 4-frame 0-1k deaths follow a fyou trigger: **false** (0.4% [0.0, 1.2]).
2. At least a fifth of normal-enemy deaths preceded by a trigger are killed by a fyou-spawned enemy, so fyou explains a measurable part of the normal-enemy share: **half true**. Among normal-enemy deaths with a prior trigger, 17 of 52 (33%) were fyou-spawned killers, but there were only 52 such deaths among 4,201 normal-enemy deaths, so fyou explains about 0.4% of them.
3. The five most lethal ids account for at least half of pattern kills: **false**. Top five ids hold 41% (1-frame) and 44% (4-frame) of rectangle kills and 32% / 40% of all deaths during an encounter. Per-encounter rates do differ by more than 5x between ids (rect/encounter 66% for id 29 vs 1% for id 28).
4. Games with a prior trigger die more often within a phase: **not supported**; the phase-start split has too few triggered games. The recency analysis does show a higher death rate in the 300 frames after a trigger (3.9x, observational).

## Caveats

- The policy is one checkpoint; the fresh cohort is one seed block. Nothing here says patterns or fyou would stay the cause for other checkpoints, and nothing is causal: a pattern being active, a trigger, or an edge position are observed states at death.
- Base rates exist for fyou recency and pattern state (exposure-based tables above). They do not exist for player location, number of enemies on screen, and killer age: those are descriptive death-frame distributions with no comparison to typical frames, so do not read "mostly edge" as risk.
- Rates per encounter mix death causes and depend on score gating (ids 13-14, 25-26, 29 and 36-39 appear only after the score passes their gate), so cross-id comparisons favor "observed / expected", which standardizes only by the phase in which the encounter started.
- 100% death per encounter for ids 13, 14, 25, 26 means no encounter was survived in this cohort; it does not say rectangles alone cause it (15-47% are rectangle contacts).
- "fyou-spawned" is exact enemy-row provenance (birth ordinals), not inferred; all 8,192 fresh and 2,048 parity-cohort games had complete attribution. Killer ages are exact frame differences. Enemy lifetime is finite in the game, which bounds killer age.
- Counts for fyou are tiny (60 triggered games at 1-frame argmax, 23 at 4-frame, 31 at 1-frame sampled, 0 at 4-frame sampled). Treat the post-trigger multiple as a lead.
- Fresh sampled groups are one controller repetition. The D8 sampled groups (768 games per setting, 3 saved repetitions) are in `tables-d8-parity-cohort.md`; they agree qualitatively.
- The existing test `test_teacher_runner.py::test_real_identity_is_read_only_and_preserves_torch_rng` fails by design after this change: it pins the frozen native source hashes (`enemy_rows.rs` is the first file it names), and this branch intentionally changes native source. Frozen identities and the other thread's pins were not edited.
- `pattern_table.json` comes from `cargo run -p dodge-core --example pattern_table`.

## Files

- `REPORT.md` (this file); `tables-fresh.md` / `tables-fresh.json`: all aggregate tables for the fresh cohort; `tables-d8-parity-cohort.md` / `.json`: the same for the DODGE-012 cohort.
- `per-game-fresh.json`, `per-game-d8-parity-cohort.json`: per-game records for every setting (seed, alive frames, cause, fyou trigger frames, pattern spans, full death context).
- `parity-gate.json`, `pattern_table.json`.
- Scripts: `learning/scripts/death_trace_eval.py` (evaluator), `death_trace_parity.py`, `death_trace_analysis.py`, `death_trace_report.py`. Raw group files are in the ignored `learning/runs/death-trace-ckpt420-r1/` (checkpoint copy, logs).
- Reproduce: build with `maturin develop --release` in `python/` (venv from `requirements-local-mac.txt`), then run `death_trace_eval.py --checkpoint ... --mode argmax --repeat 1 --seed-start 3657433088 --count 2048 --out ...` under `caffeinate -ims`, and the analysis and report scripts on the group files.
