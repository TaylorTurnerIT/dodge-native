# D2-training-v3-20261025-r1 terminal review (read-only)

Reviewer: Claude Haiku 5.5 (native Claude fallback, read-only adversarial pass).
Scope: frozen runner `d2-training-v3-adapter-prepare-20261025-r5/runner.py` and `execute_once.py`; run outputs in `D2-training-v3-20261025-r1/`; observer `D2-training-v3-execution-observer-20261025-r1/`; registration `d2-training-v3-parent-prepare-20261025-r2/registration-r8.json` (SHA-256 `d502c676…6aee6dcb`, matches the pin).

## Verdict

**No blocking findings.** The evidence is internally consistent and the claims in the parent summary reproduce.

## Checks performed

- Launcher exact-once: `launch-marker.json` single-use, `worker-launch.json` pid 3703 = owned pgid, `actual_worker_launch_count` 1, observer `launch_count` 1. No `publication-failure.json`; no `cancel-requested` in the parent directory; observer `events` empty; `first_observed_failure` null.
- Timing: launcher `elapsed_seconds` 1187.342742 ≤ 1800 (`execute_once.py:256`, `:261`, `:264`). Worker `work_elapsed_seconds` 1184.249228 < 1600. Observer `inclusive_process_wall_seconds` 1188.34122675 ≤ 1800. The ≈1.0 s gap between observer and launcher clocks is pre-`started` interpreter startup, not a contradiction.
- Counters: 72 new updates; decisions 72 × 16384 = 1179648; optimizer steps 9120 (per-update range 32–128, none > 128, `runner.py:76`); raw frames 4709765; cumulative updates 48 + 72 = 120; cumulative raw frames 3139552 + 4709765 = 7849317. All reproduce.
- Raw-frame conservation: completed journal frames 4666997 + abandoned live-episode frames 42768 = 4709765 exactly. The abandoned sum was read from the checkpoint with the venv Python (`checks/abandon-output.json`).
- Live abandonment: 64 records, slots 0–63, each once.
- Seed indices: for all 64 slots `next_episode_indices = current_episode_indices + 1` (`checks/verify-output.json`). Worker final resume list equals the journal result. Sum of current indices from reset events = 5628 = number of completed rows, so episode accounting matches.
- Development evaluations: updates 0 and 72, 64 rows each, seeds `0xD0000000 … 0xD000003F` in order, `complete` True. `terminated` XOR `truncated` holds for all rows. Death-cause counts match the summaries. Deaths 64 + caps 0 = 64 for each evaluation.
- Quartile arithmetic (update 72): Q1 bottom-16 mean 533.3125 (sum 8533), Q4 top-16 mean 2325.625 (sum 37210), overall mean 1178.0625 (sum 75396). Implied middle-32 mean 926.656 lies between Q1 and Q4. Update 0: Q1 165.4375, Q4 566.375, mean 295.25.
- Competence: 1178.0625 < 3060, `competence_passed` false. The parent attestation permits D2 training acceptance only, not competence promotion.
- Artifacts: `artifact-manifest.json` lists 16 files; all 16 SHA-256 values match disk. Final checkpoint SHA `2e13b46e…0521a2` equals the manifest entry and the observer `final_candidate.sha256`, and differs from the registration SHA.
- Resources: worker `peak_rss_bytes` 864567296 and sampled `peak_mps_driver_bytes` 2444017664, both below 6 GiB. Observer `max_sampled_aggregate_rss_bytes` 921026560, below 6 GiB.
- Seed: run seed 810631976 (0x3051D0E8) is outside the excluded ranges and does not appear in any D1 run output; it appears only in D2 registration and attempt artifacts.

## Limits (non-blocking)

1. MPS driver peak is sampled at roughly 0.05 s intervals (`runner.py:318–322`), not continuous. The 6 GiB MPS cap is therefore checked against samples, not a true peak. The observer records only aggregate RSS, not MPS.
2. RSS is `ru_maxrss` sampled at the same cadence (`runner.py:319`). The observer aggregate covers the outer launcher plus the worker group. The two figures agree in ordering; neither is a continuous peak.
3. `artifact-manifest.json` (`execute_once.py:262–263`) is written before `execution-result.json` and the manifest itself, so the terminal verdict file is not hashed by the manifest. The observer records its own hashes of these files.
4. `inherited_counters` carries `checkpoint_index: 9` and `phase_updates: 32`. The D2 run does not advance them and `cumulative_counters` (`execute_once.py:165–166`) excludes them. A later continuation that reads these fields could misread the phase or checkpoint index. This is a naming hazard, not a contradiction in this evidence.
5. The post-exit exception path (`execute_once.py:268–270`) calls `stop_owned` on a process that may already be reaped. A recycled PGID is theoretically possible. This path was not reached and is not triggered by this run.
6. Not re-run in this review: the 13560-pin verification, the runtime package imports, `ppo_update` and `dev_eval` internals, the checkpoint loader, and the test suite. The 13560 count is taken from `prelaunch.json` and `registration-r8.json`. No heavy full-runtime hash was computed, per the request.

## Reproduction

- `checks/verify.py` → `checks/verify-output.json`. Hashes are recorded in `receipt.json`.
- `checks/abandon.py` → `checks/abandon-output.json`. Run with the venv Python under `-I -B`.
