# Long D2 experiment, 2026-10-24

The single authorized long-D2 invocation **failed after 1,066.756210666 seconds**. Its worker stopped when the full-input verification interval exceeded the unchanged five-second guard. The recorded maximum was **5.005385208 seconds**. It completed 51 new PPO updates; the latest evaluated checkpoint, at update 48, averaged **score 8.0859375 and 1,093.03125 alive frames**. The D2 progress gate did not pass. No retry or resume was launched.

Parent has verified the primary receipts, frozen input hashes and process absence. Independent failure-evidence audit and read-only Opus timing diagnosis are in progress; their final conclusions will be added here. This report does not qualify the teacher or any training parent.

## Registered experiment and actual execution

The [execution plan](../learning/runs/v2-orchestration/postovernight-long-D2-execution-r1-plan.json) authorized one invocation from the successful D1 terminal checkpoint, SHA256 `ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f`. It preserved the full transformer teacher, PPO, reward, difficulty/pattern settings and development gate. Fresh training environments used master seed `5562873868232098305`. Failed checkpoints from the earlier D2 run were not used for training.

The frozen r4 controller and outer executor passed independent source and bounded stdlib review before launch. The normal maximum was 7,200 seconds, including finalization, with worker/inner/outer cutoffs at 7,140/7,170/7,200 seconds. Failure handling shared one ten-second pool. The actual command started at **19:34:54.697450 UTC** and its direct observer reaped it at **19:52:41.455141 UTC**. Raw outer exit was **1**, wait status **256**. Exactly one invocation occurred.

This run therefore supplied about 18 minutes of new training, rather than two hours. It did not reach the earlier D2 run's 104 complete updates and cannot establish whether a longer training budget would solve the learning gap.

## Runtime controls and development scores

The actual worker recorded exact model, Adam and Python/NumPy/CPU/MPS RNG restoration before creating environments or taking gradients. Its entry evaluation matched all nine fields of all 64 historical D2 control rows, with unchanged model/Adam/RNG state. These are pinned runtime receipts and exact row comparisons; no postrun independent checkpoint deserialization has been performed.

All evaluations used the fixed 64 development seeds, deterministic argmax, difficulty 2 with patterns and powerups, and an 18,000-frame episode cap.

| New phase updates | Mean score | Mean alive frames | Deaths / caps | Progress gate |
| --- | ---: | ---: | --- | --- |
| 0 | 1.4765625 | 295.25 | 64 / 0 | Failed |
| 16 | 6.6796875 | 773.234375 | 64 / 0 | Failed |
| 32 | 5.0078125 | 615.234375 | 64 / 0 | Failed |
| 48 | 8.0859375 | 1,093.03125 | 64 / 0 | Failed |

The unchanged development gate requires mean score at least 50 **and** mean alive frames at least 3,060. It is a curriculum progress gate, not final qualification against the measured heuristic at difficulties 2 and 3. The last failure checkpoint at update 51 was not evaluated.

## Counters, resources and failure

Runtime records report 51 complete new updates and 6,528 new Adam steps, with no partial optimizer update. Including inherited D1 state, totals are 99 complete updates and 12,672 Adam steps. A partial rollout added 13,312 decisions and 53,153 raw frames beyond the last complete update. Total new collection was 848,896 decisions and 3,388,752 raw frames. The independent audit is checking these denominators and raw reward/seed accounting.

Worker sampled RSS maximum was **1,001,635,840 bytes**; its process high-water receipt was **1,001,701,376 bytes**. MPS driver maximum was **2,459,009,024 bytes**. Each stayed below its separate 6 GiB observed limit. The recorded maximum resource/lease sampling gap was 0.250074125 seconds. The failing measurement was the full-input verification interval, not a memory-cap violation or changed source hash.

The worker's final outcome string is `cancelled`. Its retained traceback identifies the verification guard failure first; executor cleanup then sent SIGTERM to its owned groups. Observer cancellation requests and executor-forwarded cancellation records are empty. Parent is treating the verification guard as the primary cause, with independent causal audit pending, rather than attributing the stop to a user cancellation.

## Preserved evidence and limits

All eight checkpoints remain, including `checkpoint-000017-failure.pt`. Every new checkpoint remains training-parent and transition ineligible. No historical checkpoint metadata or identity check was changed.

Parent rehashed all 9,870 frozen pins, both observer manifests and all 31 files in the observer's postrun campaign inventory. All three exact owned groups—outer 30643, inner 30650 and worker 30714—were independently absent by process census and `killpg(..., 0)` returning ESRCH. The observer directly reaped only its outer child; absence of the other groups is not a direct-parent worker wait report.

The failed run did not publish its final campaign manifest, direct-parent worker wait report or final outer/inner resource receipts. The separately observed postrun inventory preserves stable file hashes; it does not replace those missing acceptance artifacts or convert the run into a success. A postflight collector's incorrect assumption about a schedule timestamp field is retained alongside its corrected supplement. The earlier r3 intermediate stdout loss remains disclosed historical provenance, not evidence from this run.

Primary evidence:

- [Final observer result](../learning/runs/v2/postovernight-long-D2-execution-observer-r1/execution-result-final.json), with raw timing, evaluations, counters and retained limitations.
- [Failed outer receipt](../learning/runs/v2/postovernight-long-D2-execution-r1/acceptance-receipt.json).
- [Parent terminal reconciliation](../learning/runs/v2-orchestration/postovernight-long-D2-terminal-parent-reconciliation-r1.json).
- [Preserved campaign files](../learning/runs/v2/postovernight-long-D2-campaign-r1/).

Parent cleared the exact terminal lease after verifying raw exit, hashes and process absence. The overnight scheduler remains disabled. Only read-only failure audit and diagnosis are running. No limit relaxation, training retry, failed-checkpoint resume, D3, B/E qualification or student work follows automatically.
