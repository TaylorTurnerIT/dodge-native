# D2 continuation276–348: completed, retained best unchanged

The registered continuation completed all 72 updates exactly once. Parent accepted the iteration after the strict seven-candidate audit, 13,787 unchanged input pins, model/Adam/RNG restoration, counters and episode accounting, resource checks, raw exits0, and process/group absence. None of the six new candidates improved the retained development mean. The exact earlier best276 checkpoint and its existing continuation receipt remain authoritative; endpoint348 is preserved and is not the next training parent.

| Audited development checkpoint | Q1 frames | Q4 frames | Mean frames |
| --- | ---: | ---: | ---: |
| Retained276 / reproduced entry | 566.75 | 5171.8125 | 2483.65625 |
| 288 | 836.625 | 4047.0625 | 2300.953125 |
| 300 | 732.9375 | 4113.5625 | 2137.390625 |
| 312 | 681.8125 | 5117.3125 | 2468.34375 |
| 324 | 845.25 | 4588.375 | 2437.15625 |
| 336 | 719.8125 | 4424.0625 | 2237.46875 |
| Endpoint348 | 861.25 | 4004.875 | 2273.171875 |

Each evaluation uses the same 64 deterministic D2 development seeds. Q1/Q4 are bottom/top16 means ranked by alive frames. All64 games died, with no caps. Endpoint348 deaths: 32 normal enemies, 16 kamikazes, nine static rectangles, five moving rectangles and two explosions. Retained276 deaths remain 26 normal enemies, 14 static rectangles, 13 kamikazes, ten moving rectangles and one explosion. These are development results, not generalization or competence; the 3060-frame threshold remains unmet.

The run added 9,216 optimizer steps, 1,179,648 environment decisions and 4,714,511 raw frames. Endpoint learner ancestry totals396 updates, 49,568 optimizer steps, 6,488,064 decisions and 25,917,040 raw frames. LR stayed1e-4. The raw reward still includes score delta; score is excluded from the gate. Runtime was1581.0090618329123 outer seconds. Observed aggregate RSS peaked at2,079,440,896 bytes, worker RSS at2,028,093,440 bytes and MPS driver allocation at2,464,776,192 bytes, below the separate6GiB caps.

Retained276's future branch high-water stays4760.062404125177 seconds. Its saved checkpoint point clock stays4740.377017625088 seconds. Cumulative completed-campaign resource cost rises to7118.78208862512 seconds, including this discarded branch's full outer time. Future preparation must bind this new resource-cost anchor separately from the unchanged retained276 model receipt. Parent audit CPU time is separate.

The T3 execution turn and two preparation turns later reported provider high-demand failures. The OS training run nevertheless completed successfully and retained complete receipts; parent audited the existing run without relaunching it. The planner's proposal-only files and calibrationR5 draft remain preserved. A late resumed Haiku review found a missing CPU-preflight CLI entrypoint in calibrationR4, still present in R5; a separate R6 successor repairs it. No calibration probe launched. Haiku analyzes completed PPO metrics before the next training experiment.

Evidence: [parent audit](audit.json), [completed-iteration receipt](completed-iteration-receipt.json), [strict full audit](full-audit.json), [unchanged retained-best decision](retained-best-decision.json), [task results](task-result-ingestion.json). The completed-iteration receipt grants no continuation authority to348. Checkpoint metadata and historical receipts are unchanged.
