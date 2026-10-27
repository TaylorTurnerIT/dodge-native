# Accepted D2 best276

The 72-update LR1e-4 run completed once and passed parent acceptance, including all seven embedded checkpoints, exact learner ancestry, episode accounting, input pins, raw exits, resources and owned-process absence. Final276 is the best saved candidate and is now the retained training parent.

| Accepted checkpoint | Q1 alive frames | Q4 alive frames | Mean alive frames |
| --- | ---: | ---: | ---: |
| Previous best204 | 630.4375 | 3913.5625 | 1921.171875 |
| Retained best276 | 566.75 | 5171.8125 | 2483.65625 |

Q1/Q4 are the bottom/top 16 means over the same 64 deterministic D2 development seeds. Mean improved 29.3%; Q1 fell 10.1%. Deaths: 26 normal enemies, 14 static rectangles, 13 kamikazes, 10 moving rectangles and 1 explosion. All 64 died; no caps. The 3060-frame progression threshold remains unmet. This development selection does not establish generalization or a causal learning-rate effect.

Paired seed results: 38 improved and 26 worsened. The two independently ranked worst-quarter groups share only three seeds. [Parent-reproduced analysis](../best276-survival-analysis-parent-reconciliation-20261026-r1/reconciliation.json).

Outer wall was 1408.0161675000563 seconds. Observed aggregate current RSS peaked at 1,986,183,168 bytes; worker high-water RSS at 2,090,418,176; MPS driver memory at 2,456,387,584. Both raw exits were 0 and all 13,770 input pins matched. Saved-checkpoint trajectory 4740.377017625088, accepted selected-branch terminal high-water 4760.062404125177, and total completed-campaign resource cost 5537.773026792208 seconds are distinct clocks.

A test helper created five bytecode files after the run's clean postflight. Parent reproduced the exact footprint, archived it, restored the required empty cache, and passed the strict-origin full audit without changing source, weights or checkpoint metadata. No training rerun occurred.

Evidence: [parent audit](audit.json), [continuation authority](parent-terminal-receipt.json), [full audit](full-audit.json), [cache reconciliation](cache-contamination-reconciliation.json). Only separately registered D2 continuation is authorized; no qualification, D3, B/E or student promotion.
