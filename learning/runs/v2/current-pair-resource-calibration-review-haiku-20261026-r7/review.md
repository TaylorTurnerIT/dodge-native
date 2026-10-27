# R7 source-only review (Haiku)

Mode: static source read. No imports, tests, checkpoint loads, MPS, probe, marker, environment, or launch were run. Logs cited are not re-run. Runtime acceptance is not established here.

## Findings

1. **low, contract accuracy: `probe.py`.** The comment "No MPS call precedes this gate" is inaccurate. `ResourceSampler.start()` runs `_default_probe`, which calls `torch.mps.driver_allocated_memory()`, before the rehash-before-MPS gate. Consequence: the stated evidence claim is false. Runtime effect is unverified.
2. **low, correctness: `launch_once.py` `monitor_rss`.** A nonzero `ps` return for the worker PID raises before the `process.poll()` recheck. A clean child exit racing with `ps` then becomes `RSS monitor failed closed`, and a passing probe is recorded as failed. Race window is small.
3. **low, evidence: `probe.py`.** Failures before the `try` block do not write `probe-result.json`. Launcher still records `failed_child`, but probe-owned failure reason is lost.
4. **low, defense in depth: `launch_once.py` `run_cpu_preflight`.** Gate checks only `status` and `mps_operations`, not `training` or `requires_grad_any`. Probe's own CPU loop still rejects these before MPS, so no MPS exposure.
5. **info, intent: 6 GiB cap.** Launcher caps launcher plus worker current RSS combined. Probe caps worker `ru_maxrss` separately. `calibration-plan.json` says `rss_and_mps_caps_separate: true`. Confirm whether a combined cap is intended.

## Verified statically

- Frozen hashes match: plan, freeze manifest, preparation receipt, review-source manifest. Source pins matched in freeze log.
- Reader integration: `probe.py` `require_mps_within_cap` matches `worker.read_latest_resource_sample` return keys (`sample`, `age_seconds`, `complete_records`). Stale or malformed samples fail.
- Guard formula: 136 per pass holds by trace (64 construction + 8 decisions × 9).
- Launcher args: accepts only `--plan --pins --reservation --output`. Plan and pins sha flags go to the child probe only. Output path fixed to `probe-output`.
- Startup MPS zero is accepted. Active-window all-zero fails.
- `cpu_preflight.py` has `main()` and a `__main__` guard. Both `ROOT` derivations resolve to repo root.
- `cpu-tests-r7-final.log` shows 17 tests OK (log only).

## Limitations

- Static review only. `torch.mps` behavior, `ps` race timing, and RSS/MPS measurement semantics are unverified.
- Test log cited, not re-run.
- Did not review R6 reconciliation or parent audit in depth given time budget.
