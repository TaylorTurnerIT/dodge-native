# Existing D2 retained-300 run: terminal monitor summary

Monitor attached read-only to observer PID 26658, launcher PID 26659, and worker PID 26662. The observer published its terminal receipt; all three named processes are absent. No campaign command was launched by this monitor.

## Authoritative terminal evidence

- Observer: `success_authoritative: true`; `launch_count: 1`; outer raw exit `0`; worker raw exit `0`.
- Actual worker launch count: `1`; worker status `completed`; `60` updates; evaluation updates `[300, 312, 324, 336, 348, 360]`; first failure `null`.
- Outer inclusive wall: `1137.027081334032s` of `1800s`; worker elapsed: `1133.6250237498898s` of `1790s` work budget.
- Peak aggregate RSS: `2084847616` bytes of `6442450944`; peak worker RSS: `2025586688` bytes; peak MPS driver allocation: `2456387584` bytes of `6442450944`.
- Registration SHA-256: `8a60dc80f1ebe03c43bf18eebf75199e14f207b677570ac2d6d4368ddfcb0f79`; observer preflight and postflight each checked `13827/13827` pins with no failures.
- Cleanup signals: none. Observer, outer process, worker process, and worker process group are absent. Postflight says cache empty and publication failure absent.
- Per-run counters: 60 updates, 7680 optimizer steps, 3929195 raw frames. Cumulative counters: 408 updates, 51104 optimizer steps, 26703298 raw frames.
- `competence_passed: false`; `promoted: false`; `training_eligible: false`. Candidate checkpoints remain provisional pending parent acceptance.

## Candidate survival table (PROVISIONAL)

All six candidate checkpoint files and sidecars were present at terminal observation. “Death cause” means none recorded for these retained files; this is not a parent acceptance decision.

| Update | Checkpoint SHA-256 | Eval alive-frames mean | Eval score mean | Survival / death cause |
|---:|---|---:|---:|---|
| 300 | `4c3bd2fe3be07c4d50a79626e3a6c1fcf50093ffc0b94fd82158fb50544c6feb` | 2704.390625 | 25.890625 | Present; no death cause recorded; provisional |
| 312 | `6cfd9ffc4bb78b5c18bceb03dedfb075383c770505caa36635c09d9e6de8df2b` | 2607.09375 | 25.9453125 | Present; no death cause recorded; provisional |
| 324 | `c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc` | 2939.40625 | 29.53125 | Present; no death cause recorded; provisional |
| 336 | `1299e5a0458ee5e7fd82c20bfa1789cb8ac7d4534ab803b219ef4a6ad27a61b9` | 2336.5 | 21.640625 | Present; no death cause recorded; provisional |
| 348 | `405a378fd4d44b7c5933f5058609d875741ef95e07486b4f9f32fcc9450e9276` | 2918.265625 | 29.6328125 | Present; no death cause recorded; provisional |
| 360 | `14fe430b9e2c8c299620db3c9d081f0a80b3c25883ea6ccdfdfd8cffc6e69fd0` | 2524.8125 | 24.0859375 | Present; no death cause recorded; provisional |

## Receipt paths

- Observer terminal receipt: `learning/runs/v2/D2-retained300-execution-observer-parent-20261026-r1/observation.json`
- Worker result: `learning/runs/v2/D2-retained300-continuation-20261026-r1/worker-result.json`
- Execution result: `learning/runs/v2/D2-retained300-continuation-20261026-r1/execution-result.json`
- Monitor snapshot: `learning/runs/v2/D2-retained300-existing-run-monitor-luna-20261026-r1/terminal-report.json`
