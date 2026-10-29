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
