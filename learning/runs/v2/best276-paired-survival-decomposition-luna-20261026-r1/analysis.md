# Paired survival decomposition: best 204 vs best 276

## Result

Across the same 64 D2 development seeds, mean alive time rose from 1,921.17 to 2,483.66 frames (+562.48; 38 wins, 26 losses, 0 ties). Median paired change was 202.00 frames. Gross gains were 77,682 frames and gross losses 41,683, net 35,999.

Independent ALIVE-ranked quartile means (old → new):

| Quartile | Old | New | Change |
|---|---:|---:|---:|
| Q1, shortest | 630.44 | 566.75 | -63.69 |
| Q2 | 1,096.62 | 1,454.44 | +357.81 |
| Q3 | 2,044.06 | 2,741.62 | +697.56 |
| Q4, longest | 3,913.56 | 5,171.81 | +1,258.25 |

The mean rose while Q1 fell because Q1 is re-ranked independently at each checkpoint and its seed membership changed. The two shortest-16 groups share 3 seeds. Old Q1's 16 seeds averaged 2,724.75 frames under best 276; new Q1's 16 seeds averaged 2,135.00 under best 204. Q2–Q4 each rose, with Q4 up 1,258.25 frames. These observed group changes account for the higher overall mean; no mechanism is inferred.

## Loss concentration and worst-tail movement

The 26 losing seeds account for 41,683 gross lost frames. The largest 1, 4, and 8 losses account for 14.2%, 38.5%, and 65.3% of that total. Worst 16 retained 3 seeds, with 13 leaving and 13 entering.

Eight largest paired losses (seed, old/new frames, delta, old → new death cause):

| Seed | Old | New | Δ | Old cause → new cause |
|---:|---:|---:|---:|---|
| 3489660983 | 6714 | 794 | -5920 | normal_enemy → kamikaze_enemy |
| 3489660974 | 4152 | 600 | -3552 | normal_enemy → moving_pattern_rect |
| 3489660934 | 3821 | 497 | -3324 | normal_enemy → kamikaze_enemy |
| 3489660978 | 3963 | 695 | -3268 | moving_pattern_rect → kamikaze_enemy |
| 3489660932 | 3748 | 529 | -3219 | kamikaze_explosion → moving_pattern_rect |
| 3489660951 | 3950 | 920 | -3030 | static_pattern_rect → normal_enemy |
| 3489660954 | 4589 | 2004 | -2585 | normal_enemy → moving_pattern_rect |
| 3489660962 | 2907 | 593 | -2314 | static_pattern_rect → kamikaze_explosion |

## Deaths

Best 276: 26 normal enemy, 14 static rectangle, 13 kamikaze enemy, 10 moving rectangle, 1 kamikaze explosion. Each episode ended in death; neither checkpoint reached a cap. Cause-specific alive-time summaries and all observed old-to-new cause transitions are in `analysis.json`. Cause labels and conditional lengths are descriptive; small counts, especially the single new explosion, limit interpretation.

## Evidence boundary

Rows passed seed, termination, death/cap, alive-frame, metadata-mean, and pinned-hash checks. Best 276 checkpoint hash matches the supplied parent terminal receipt. This analysis compares two selected checkpoints on shared dev seeds; it does not establish a causal training effect, replicate-level uncertainty, generalization, or qualification. No checkpoint selection was performed.
