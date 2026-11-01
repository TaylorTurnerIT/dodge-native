DODGE-068: accepted local survival evaluation

Rays had lower mean and worst-quarter survival estimates in both replicas. All four paired95% intervals span zero. This panel does not establish a ray benefit or harm. Checkpoint420 had higher mean survival than all four trained endpoints.

All640 declared games completed:128 clean games per fixed model on shared consumed development seeds3657433088..3657433215. Controller:sampled per-game paired CPU RNG,K1,no shield,18000-frame cap.

| Fixed model | Mean survival (s) | Worst-quarter mean (s) | Early deaths ≤600frames |
|---|---:|---:|---:|
| r1-control | 66.66 | 22.50 | 3/128 |
| r1-rays | 63.72 | 18.39 | 7/128 |
| r2-rays | 65.28 | 18.71 | 4/128 |
| r2-control | 67.61 | 21.60 | 1/128 |
| 420 | 77.12 | 30.92 | 3/128 |

| Rays minus control | Mean difference,95% interval (s) | Worst-quarter difference,95% interval (s) |
|---|---:|---:|
| r1-rays-minus-r1-control | -2.94 [-11.88,+5.88] | -4.11 [-12.63,+3.27] |
| r2-rays-minus-r2-control | -2.34 [-11.34,+6.77] | -2.90 [-10.25,+3.15] |

Actual exposure:2,614,798 gameplay frames plus8,320 startup frames. No game reached the cap. Acceptance completed in505.700s within7200s work+180s receipts. Peak worker RSS600.8MiB and MPS driver176.5MiB stayed below separate6GiB caps.

Exact independent review passed. Counted native qualification covered the first64 games for every model and projected2142.892s with20% margin+240s IO reserve. Parent recomputed complete coverage, native frame identities and10,000 paired-seed bootstrap draws. Worker/supervisor exited0 and were directly reaped. The owned sleep helper and owner are also reaped; all owned groups are absent. Accepted audit preceded exact lease release. Follow-up monitoring is disabled.

Limits:exploratory consumed development seeds,one sampled controller stream per seed,clean execution only,128 seeds and two training replicas. Intervals describe game-seed uncertainty conditional on these fixed models; they do not estimate training-replica uncertainty or establish general superiority. Noise robustness and fresh heldout performance remain unknown. No training, selection or promotion occurred.

Evidence:
- Registration:registration-r1.json, SHA256 7ef31c0e090cdceebdcab834dd479ecf515d81984e78e6ed584550759664eb06
- Exact independent review:review.json, SHA256 a391ba34bd3ea6c61cfad80a004d15339f2731251f85b657a2675740218fb7f5
- Native qualification:output/worker/prefix-qualification.json
- Survival and paired uncertainty:output/worker/analysis.json, SHA256 0b6330316bdc36fcfd1d8f54abdb08c5d98e9dc300cef515d723275a3e87ec29
- Accepted parent audit:output/parent-terminal-audit.json, SHA256 1fcd5ef6110c6853dc9c5c9d6a1d857d1c62ee1db9fac9ca47c96bb5f531f18a
- Exact release:output/lease-release.json, SHA256 a3f754654867122975a7573f2905c39379d80b55beae6a900b71b42fe1213ed3
- Direct owner reap and final group absence:output/owner-exit.json
