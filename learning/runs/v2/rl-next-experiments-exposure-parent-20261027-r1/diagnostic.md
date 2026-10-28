# Exposure audit: 70/30 episodes became 50/50 frames

**The 70% short-stage assignment consumed 50.3% of raw gameplay frames and cut age 1,000–2,000 exposure about in half.** Total native gameplay frames matched across arms: 11,787,590 control vs 11,788,805 curriculum. Measured shift does not prove cause of Q4.

| Arm/replica | 1,000-stage assignment | Frame share in 1,000-stage runs | Frames age 0–1k | Frames age 1k–2k | Natural deaths / artificial cutoffs | Mastery windows passed/checked |
|---|---:|---:|---:|---:|---:|---:|
| Control 1 | 0% | 0% | 1,732,113 | 1,104,196 | 1,877 / 0 | — |
| Curriculum 1 | 69.9% | 50.0% | 2,819,507 | 548,318 | 1,632 / 1,477 | 0/21 |
| Control 2 | 0% | 0% | 1,737,856 | 1,087,499 | 1,898 / 0 | — |
| Curriculum 2 | 70.1% | 50.0% | 2,816,847 | 560,564 | 1,584 / 1,504 | 0/21 |
| Control 3 | 0% | 0% | 1,706,034 | 1,093,575 | 1,830 / 0 | — |
| Curriculum 3 | 69.9% | 50.8% | 2,854,846 | 559,649 | 1,599 / 1,515 | 0/21 |

Pooled control vs curriculum: **0–1k 5.176m vs 8.491m frames (+64%); 1k–2k 3.285m vs 1.669m (−49%); 2k–4k 2.737m vs 1.379m (−50%)**. Neither arm reached 9k. All 4,496 artificial cutoffs came from 1,000-horizon assignments and bootstrapped; curriculum had 4,815 natural deaths and no 18,000-horizon truncations.

PPO metrics show no update starvation: all 360 updates completed four epochs; zero early stops. Mean approx-KL: 0.00600 control / 0.00585 curriculum; clip fraction: 0.0320 / 0.0305; entropy: 1.67 / 1.69. Explained variance varied by replica. These metrics do not explain endpoint outcomes.

Existing terminal evaluation: curriculum-minus-control mean −9.23, Q1 +13.78, Q4 −180.31 frames; descriptive across three pairs. Logs measure raw frames, not exact decisions. Best next isolation: full episodes, capped training-only opening-seed priority vs uniform, matched budget and age-bin coverage.

## Artifacts

[Exposure JSON](exposure.json) and [CSV](exposure.csv); [script](analyze_exposure.py) and [hashed input receipt](data-receipt.json).
