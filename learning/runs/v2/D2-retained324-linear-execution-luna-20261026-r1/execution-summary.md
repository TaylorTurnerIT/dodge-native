# D2 retained324 linear execution summary

The single registered observer launch completed. This records execution and postflight only; parent acceptance remains authoritative. The candidate is not promoted or training eligible.

- Observer: `observe.py`, SHA-256 `f271b2641b995fc34a90cebe420657953cb16ce9038886edc2fd74c184ccacad`; registration SHA-256 `0a6bf98221689ffcf62a28289dae7bb98eb89bc8d3c02b93127f4a04df75cb4e`.
- Launch count: observer `1`, worker `1`. Observer PID `73959`; outer PID `73969`; worker PID/PGID `73972`.
- Observer command: `env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained324-continuation-prepare-luna-20261026-r2/empty-pycache /Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/python/.venv/bin/python -B /Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained324-linear-execution-observer-parent-20261026-r1/observe.py`
- Worker command and immutable registration are recorded in `../D2-retained324-linear-execution-observer-parent-20261026-r1/observation.json` and `../D2-retained324-linear-lr-20261026-r1/worker-launch.json`.
- Raw exits: observer `0` (attached command session `61926`), outer `0`, worker `0`. Outer wall `1131.1351048339857 s`; work `1127.3893919578986 s`; worker direct-wait elapsed `1129.8281631659484 s`.
- Training: 60/60 updates, phase `324 -> 384`, cumulative updates `372 -> 432`; evaluation checkpoints at `324, 336, 348, 360, 372, 384`. Final checkpoint SHA-256 `cc5c3bee52b3fdad925ad90e793983df41954f16ce11403f9f32c431434e52e2`.
- Resource peaks: aggregate RSS `2259222528` bytes; worker RSS `2150055936` bytes; MPS driver `2456387584` bytes. Each stayed below `6442450944` bytes. Limits: 1750 s planned, 1790 s work, 1800 s total, 10 s cleanup.
- Postflight: all `13857` registered pins passed; lease identity exact; inference leases absent; cache empty; no stdout/stderr; worker directly reaped; worker PID/group and outer PID/group absent; observer PID `73959`, outer PID `73969`, worker PID `73972` absent on final process inspection. Observer reported `success_authoritative: true`, `first_event: null`, and no cleanup signals.
- Worker result status `completed`; `first_failure: null`; promotion `false`; `training_eligible: false`; competence gate `false`. Candidate remains provisional pending parent review and acceptance. Parent owns lease clearing and checkpoint acceptance.
- The user reported an earlier provider high-demand failure. This monitor attached to the already-running observer; it did not relaunch any process. The campaign completed successfully under the existing single observer launch.

Evidence: `../D2-retained324-linear-execution-observer-parent-20261026-r1/observation.json`, `../D2-retained324-linear-execution-observer-parent-20261026-r1/prelaunch.json`, `../D2-retained324-linear-lr-20261026-r1/execution-result.json`, and `../D2-retained324-linear-lr-20261026-r1/worker-result.json`.
- Provisional development evidence reported by the parent: checkpoint `348` Q1 `867.0625`, Q4 `6003.875`, mean `3098.125`; checkpoint `360` mean `2535.140625`. Original retained `324` mean `2939.40625` remains incumbent until parent acceptance.
