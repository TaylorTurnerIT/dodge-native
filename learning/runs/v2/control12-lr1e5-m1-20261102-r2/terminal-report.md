DODGE-071 completed its single M1 SSH invocation from 02:14:38 to 05:51:14 America/Chicago on 2026-11-02. It completed 72 additional updates, 4,718,592 training gameplay frames and 9,216 Adam steps. The frozen loop stopped for `persistently_uncompetitive_play` and retained control12 at continuation update 0.

All results below use 512 same-machine development games per check. Mean and Q1 are survival frames; Q1 averages the worst quarter. The run completed 1,024 baseline games and 3,072 continuation development games.

| Checkpoint | Mean | Q1 | Early deaths |
| --- | ---: | ---: | ---: |
| 420 fallback | 4366.35 | 1849.95 | 10 |
| control12 / retained update 0 | 4533.36 | 1836.45 | 7 |
| Additional update 12 | 4150.08 | 1357.05 | 16 |
| Additional update 24 | 3972.35 | 1302.46 | 22 |
| Additional update 36 | 4096.28 | 1382.95 | 19 |
| Additional update 48 | 3949.79 | 1180.67 | 24 |
| Additional update 60 | 4042.12 | 1324.55 | 15 |
| Additional update 72 | 3830.92 | 1139.26 | 22 |

The frozen rule required the initial 72 additional updates. Checks at 12,24,36,48,60 continued that initial horizon; none selected a new best. At update 72, the last three checks each had Q1 below 80% of the control12 baseline. Update 72 also failed the Q1 guard and early-death allowance (22 > 18). No guarded 2% Mean gain occurred. The prospective persistently_uncompetitive_play rule stopped the live loop.

The first two actual counted updates passed training qualification: 131,072 frames and 256 Adam steps, preserved model/Adam/source RNG with LR changed from 3e-5 to 1e-5, and both passive GAE/return identity checks passed. Their measured update times were 131.44 s and 129.32 s; full-path time through qualification was 1,235.05 s. Peak RSS was 2,438,037,504 bytes and peak MPS allocation was 2,382,102,528 bytes, each below its separate 6 GiB limit. No wall-clock gate stopped the run.

Saved descriptive paired bootstrap intervals: control12 minus 420 Mean +167.01 frames (95% interval -92.10 to +419.71), Q1 -13.50 (-302.81 to +261.42). Update 72 minus control12 Mean -702.44 (-972.48 to -417.52), Q1 -697.19 (-951.33 to -437.04). These describe repeated development selection on the same seeds; they do not establish performance across training replicas or fresh confirmation games.

Retained checkpoint on M1: `/Users/taylor/Projects/dodge-native/learning/runs/v2/control12-lr1e5-m1-20261102-r2/output/worker/control/checkpoints/checkpoint-000000.pt`; SHA-256 `ce19968026102f4550334ff0b3cb3305cd39b451e5e83ee93471b291615c9ed1`. Its zero additional update/frame/Adam counts describe the retained starting checkpoint, not the completed run. All seven checkpoints remain intact and read-only. Original control12 `/Users/taylor/Projects/dodge-native/learning/runs/v2/m1-stage-tailscale-20261102-r1/inputs/checkpoints/control12.pt` (`04171886ad1d200f58579952519e972610f9518ddd32af54d25b817204d072b8`) and 420 fallback `/Users/taylor/Projects/dodge-native/learning/runs/v2/m1-stage-tailscale-20261102-r1/inputs/checkpoints/checkpoint420.pt` (`7e0de8640f1337261412d91cde6bc692772ff212fbd360f5aad415dc6bc7ed4b`) were hash-verified without loading weights.

Source commit `0ba4d9191ba47250685a6d5c0c590274a12cf705`; config `/Users/taylor/Projects/dodge-native/learning/runs/v2/control12-lr1e5-m1-20261102-r2/config.json`, SHA-256 `2f9adc5af999020da9278d094cc5fc4abece2fae87642197d8d114e0618f5b5d`. All 19 algorithm files, the host caller and route guard matched their frozen hashes. [Full structured result](result-summary.json) records exact sources, checkpoints, counts and paths.

Host coordinator, owner, supervisor, worker, acceptance helper and caffeinate have saved direct-reap and group-absence receipts. A fresh read-only process snapshot confirmed those groups absent and host caller 5867 absent. The existing foreground handle 50912 returned exit 0; the exec provider performed its process reap. Terminal acceptance ran once automatically. Its durable accepted audit binds the exact lease release, and the live ledger has no active long-campaign lease.

[Accepted audit](remote-receipts/parent-terminal-audit.json), [exact lease release](remote-receipts/lease-release.json), [host completion](remote-receipts/host-driver-complete.json), and [terminal readback](terminal-readback.json) preserve the evidence. The corresponding originals are under `/Users/taylor/Projects/dodge-native/learning/runs/v2/control12-lr1e5-m1-20261102-r2/output/`. No new evaluation, model/checkpoint load, retry, promotion or change to frozen070 occurred. Weights, native journals and the live ledger remain off Git.

Return this completed execution result to the accountable M4 parent with callback ID `control12-lr1e5-m1-20261102-r2-terminal-call-home-v1`. This task sent no department or cross-thread message.
