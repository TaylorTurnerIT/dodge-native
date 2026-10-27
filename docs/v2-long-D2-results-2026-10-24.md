# Long D2 experiment, 2026-10-24

The single authorized long-D2 invocation **failed after 1,066.756210666 seconds**. Its worker stopped when the full-input verification interval exceeded the unchanged five-second guard. The recorded maximum was **5.005385208 seconds**. It completed 51 new PPO updates; the latest evaluated checkpoint, at update 48, averaged **score 8.0859375 and 1,093.03125 alive frames**. The D2 progress gate did not pass. No retry or resume was launched.

Parent has reconciled the completed independent failure-evidence audit and read-only Opus timing diagnosis. All **49 evidence-consistency checks passed**, including raw results, frozen inputs, entry controls, rewards, seeds, counters and process absence. This accepts the preserved failure evidence; it does not qualify the teacher or any training parent.

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

Runtime records report 51 complete new updates and 6,528 new Adam steps, with no partial optimizer update. Including inherited D1 state, totals are 99 complete updates and 12,672 Adam steps. Complete rollouts supplied 835,584 decisions and 3,335,599 raw frames. A partial rollout added 13,312 decisions and 53,153 raw frames beyond the last complete update. Total new collection was 848,896 decisions and 3,388,752 raw frames. The independent audit reconciled these denominators, raw reward accounting for **4,306 completed training episodes**, fresh u32 seed derivation, and per-slot resets.

Worker sampled RSS maximum was **1,001,635,840 bytes**; its process high-water receipt was **1,001,701,376 bytes**. MPS driver maximum was **2,459,009,024 bytes**. Each stayed below its separate 6 GiB observed limit. The recorded maximum resource/lease sampling gap was 0.250074125 seconds. The failing measurement was the full-input verification interval, not a memory-cap violation or changed source hash.

The worker's final outcome string is `cancelled`. Its retained traceback identifies the verification guard failure first; executor cleanup then sent SIGTERM to its owned groups. Observer cancellation requests and executor-forwarded cancellation records are empty. Independent audit and parent source reconciliation confirm that the verification guard was the primary cause. The cleanup signal overwrote the terminal outcome label; it was not a user cancellation. Cleanup and outer reap completed 0.347924458 seconds after the first failure, within the shared ten-second pool.

## Guard diagnosis and proposed next step

The frozen controller starts background verification once four seconds have elapsed since the previous successful pass's **start**. It then requires the current pass to finish within five seconds of that previous start. This leaves roughly one second for polling, scheduling, lock wait and the full verification. The independent monitor enforces the same five-second age during an in-flight pass. The recorded violation is consistent with these source rules; the guard correctly rejected the run.

Verification includes 9,870 pin hashes totaling **228,611,008 bytes**, capsule inventory and parent-directory checks, the unchanged historical identity rebuild, and loaded-module origin checks. The pre-run **0.326821541-second** measurement covered idle pin hashing only. It did not measure those additional checks or concurrent training load.

The exact background pass start and component durations were not logged. Opus's inferred 0.955–1.005-second pass duration assumes prompt thread scheduling; scheduling delay could account for part of the elapsed interval. Its foreground median near 0.450 seconds comes from resource-sample spacing, not directly timed verification passes. Concurrent sampling complicates that classification. These estimates do not establish a measured pass distribution, a twofold slowdown, CPU duty or disk throughput. GIL/CPU contention and I/O delay remain hypotheses. No memory-cap violation, external cancellation, changed pinned input or absolute-budget expiration explains the recorded stop; the receipts do not establish a learning defect or rule out every possible latent defect.

The proposed minimal repair is to **start verification earlier, initially at two seconds**, while keeping the strict five-second check, its conservative start-to-end semantics, all 9,870 pins, the 9,675 old-pin union, all 75 legacy source checks, capsule/origin verification, and forced update/evaluation checks. Add per-pass start/end, trigger delay, lock wait, component timing and thread CPU instrumentation. Preserve the primary failure in reporting and record cleanup cancellation separately. Process isolation is a larger fallback only if synthetic stress demonstrates a need. Schedule timestamp changes are optional and would require separate reconciliation of the protected schedule block.

This is a **proposal only**. No controller, learner, limit, frozen identity or checkpoint metadata was changed. The proposed stdlib regressions and stress tests have not run. A future implementation needs frozen adversarial review; any new training experiment needs fresh explicit authorization and registration from an eligible audited D1 parent. No automatic retry or failed-weight resume follows. These 51 updates cannot answer whether the full planned training budget would solve D2.

## Preserved evidence and limits

All eight checkpoints remain, including `checkpoint-000017-failure.pt`. Every new checkpoint remains training-parent and transition ineligible. No historical checkpoint metadata or identity check was changed.

Parent rehashed all 9,870 frozen pins, both observer manifests and all 31 files in the observer's postrun campaign inventory. All three exact owned groups—outer 30643, inner 30650 and worker 30714—were independently absent by process census and `killpg(..., 0)` returning ESRCH. The observer directly reaped only its outer child; absence of the other groups is not a direct-parent worker wait report.

The failed run did not publish its final campaign manifest, direct-parent worker wait report or final outer/inner resource receipts. The separately observed postrun inventory preserves stable file hashes; it does not replace those missing acceptance artifacts or convert the run into a success. A postflight collector's incorrect assumption about a schedule timestamp field is retained alongside its corrected supplement. The earlier r3 intermediate stdout loss remains disclosed historical provenance, not evidence from this run.

Primary evidence:

- [Final observer result](../learning/runs/v2/postovernight-long-D2-execution-observer-r1/execution-result-final.json), with raw timing, evaluations, counters and retained limitations.
- [Failed outer receipt](../learning/runs/v2/postovernight-long-D2-execution-r1/acceptance-receipt.json).
- [Parent terminal reconciliation](../learning/runs/v2-orchestration/postovernight-long-D2-terminal-parent-reconciliation-r1.json).
- [Independent failure audit](../learning/runs/v2/postovernight-long-D2-failure-parent-audit-r1/audit.json), 49 checks passed; checkpoint contents were not independently deserialized.
- [Opus diagnosis](../learning/runs/v2/postovernight-long-D2-guard-diagnosis-opus-r1/diagnosis.md), retained with the parent qualifications above.
- [Final parent audit and diagnosis reconciliation](../learning/runs/v2-orchestration/postovernight-long-D2-final-audit-r1/parent-reconciliation.json).
- [Preserved campaign files](../learning/runs/v2/postovernight-long-D2-campaign-r1/).

Parent verified all 36 Opus input hashes and three receipt-listed outputs, all 11 independent-audit artifacts, and both 9,936-entry audit input snapshots without mismatches before updating the parent ledger and these documents. Pre-closeout parent bytes are preserved separately; the ensuing ledger/document changes are explicit bookkeeping. The first independent receipt-parser error, its exact script and log remain alongside the corrected audit. No training was repeated to repair a collector.

Parent cleared the exact terminal lease after verifying raw exit, hashes and process absence. The owned overnight scheduler was rechecked as disabled with no next run. Both read-only tasks are complete and ingested once. No campaign or review remains active for this experiment. The single-use authorization is consumed; no limit relaxation, training retry, failed-checkpoint resume, D3, B/E qualification or student work follows automatically.
