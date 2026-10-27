# M2 vectorized environment results

Campaign `v2-m2-validation-20261024-r2` passed all four phases. Independent native/provenance and Python-result audits passed, and the parent accepted M2 for teacher implementation. The acceptance receipt is `learning/runs/v2-orchestration/milestone2-acceptance-r2.json`. No teacher-learning result follows from environment acceptance.

## Identity and execution

- Specification: [SPEC_PRIVILEGED_VIT_RL.md](SPEC_PRIVILEGED_VIT_RL.md).
- Frozen identity: `learning/runs/v2/milestone2-campaign-freeze-r4/frozen-identity.json`, SHA256 `eb72ae7efec29f6def72940715ad6ff09e43d09140f0c348f095bdbbf2727448`.
- Supervisor SHA256: `2a542c52413fd3ef9529688e6f7ea34652ae102c89481d8b593690664adf3303`.
- Installed extension SHA256: `967c7249acd52339d1818dcbe94e63ee734aea914c3497eb59a7e945a6e95583`.
- Results: `learning/runs/v2/milestone2-validation-campaign-r2/` and `learning/runs/v2/milestone2-validation-execution-r2/report.json`.
- Supervisor interval: 2026-10-24 08:48:37.147149–08:57:58.657068 UTC; 561.513 seconds. The outer execution receipt records 561.568 seconds.

One invocation ran the unchanged sequential plan, with a 1,800-second total limit and separate 600-second receipt reserve. No resource limit, assertion, seed exclusion, episode count, or phase workload was relaxed. Parent verified all 34 campaign artifact hashes, 44 outer-owned output hashes, the complete 62-entry source inventory, and absence of all recorded process IDs after completion.

## Native parity

The current native test completed 1,000 paired heuristic episodes at each difficulty. It compares full and headless logical state after every raw frame, excluding the intentionally different framebuffer. Recorded episode results match the original-engine baseline, including raw score, alive and gameplay frames, cap/death reasons, native Death-event multiplicity, final fingerprints, and aggregate pattern counts.

| Difficulty | Episodes | Raw frames per path | Mean score | Mean alive frames | Capped episodes | Patterns covered |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| D2 | 1,000 | 6,115,578 | 100.1075 | 6,114.593 | 15 | 39 |
| D3 | 1,000 | 4,031,036 | 88.633 | 4,030.038 | 2 | 39 |

Together these cover 10,146,614 raw frames per path. The phase took 535.516 seconds under its 900-second limit. Its snapshots, policy work, and parity comparisons are validation overhead and do not measure production training throughput. Logs retain episode summaries rather than every intermediate state; the pinned test source and successful execution support the frame-level assertion claim.

## Python trajectories and ownership

The two thread/chunk configurations, 1/1 and 4/3, passed the full registered trajectory comparison with pixels and auxiliary targets enabled:

| Case | Batch × decisions | Raw cap | Raw frames per path | Deaths | Caps | Explicit resets |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Normal episodes | 9 × 400 | 18,000 | 14,344 | 48 | 0 | 48 |
| Ragged truncation | 5 × 40 | 17 | 680 | 0 | 40 | 40 |

The phase also checks returned-array ownership, mutation isolation, terminal/truncation handling, and reset alignment. It completed in 2.077 seconds under its 120-second limit. The retained result does not serialize every compared array.

## Memory

The rendered, auxiliary-enabled B8 workload used four threads and chunk size two. It completed 5,000 warmup step calls and 100,000 measured step calls, including 3,180,831 measured raw gameplay frames. It retained 101 post-warmup RSS samples: the warmup boundary and every 1,000 measured calls. Across warmup and measurement it recorded 13,155 deaths and explicit resets, with no cap endings.

The first and last 11-sample median RSS values were 50,003,968 and 53,018,624 bytes. Growth was 3,014,656 bytes (2.875 MiB), below the preregistered 67,108,864-byte limit. The reported OLS slope is about 25.12 bytes per step call. The phase completed in 15.397 seconds under its 600-second limit.

This is an empirical allocator plateau under the registered short-episode workload. It does not prove zero leaks. Mature-pattern coverage comes from the separate native replay. Sampled RSS and self-reported peak measurements are cooperative observations, not a hard OS memory ceiling. The maximum observed worker RSS across the campaign was 69,976,064 bytes, below 6 GiB.

## Public API throughput

Each configuration used B32, 200 warmup calls, and 2,000 measured calls. The action matrix, actual seed assignment sequence, work checksums, final neural-array hashes, raw-frame counts, and reset counts must agree across configurations.

| Rendering | Threads / chunk | Public step calls/s |
| --- | --- | ---: |
| Headless | 1 / 1 | 8,281.09 |
| Headless | 4 / 8 | 9,412.90 |
| Rendered | 1 / 1 | 1,548.50 |
| Rendered | 4 / 8 | 3,481.72 |

The phase completed in 4.629 seconds under its 120-second limit; each timed configuration also has a 60-second guard. Timing includes the public step/reset API, feature extraction, returned arrays, and limited audit bookkeeping. Construction and warmup are excluded. These are single measurements under a fixed workload, without uncertainty estimates. They do not measure PPO inference/update throughput or establish a speedup over differently configured historical engine profiles.

## Failed predecessor and remaining work

Campaign r1 remains failed and preserved. Its native phase passed, but the first Python constructor rejected JSON list pairs where the strict binding requires tuple pairs. Memory and throughput never ran. A one-line supervisor adapter repaired the argument representation while preserving the seed ranges. Its 54 pure tests and separate real-extension trajectory preflight passed before the fresh r4 review and r2 campaign. Earlier guard repairs and their negative controls remain retained.

The independent native audit matched all 2,000 episode rows and 78 pattern records, verified the build/archive/wheel lineage, and retained its corrected build supplement v2. The Python audit independently checked all 13,163 memory seed assignments and 13,155 completed-episode objectives, reconstructed warmup and measured raw-frame totals, recomputed the RSS plateau, and matched all four 1,112-row throughput seed schedules and their binary hash.

Audit receipts are `learning/runs/v2/milestone2-validation-parent-native-audit-r2/audit.json` (SHA256 `1fdda45dbc3e5d7d0ae12dfd0ba3cbb1a33f98a650d48878f7a5053402958b0c`) and `learning/runs/v2/milestone2-validation-parent-python-audit-r2/audit.json` (SHA256 `439a4b141cbf482cfdf898d942e94ebd1a3fca0cd75ba39f330bea2a8821b085`). Parent verified the auditors' retained artifact manifests before acceptance. Intermediate-array and cooperative-resource limitations above remain.

Teacher/PPO implementation may now proceed under the registered plan. New neural code still needs integration tests and frozen review before training. No teacher qualification set has been opened. Student work remains deferred until a capable teacher exists.
