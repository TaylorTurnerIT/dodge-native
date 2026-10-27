# Frozen review: latest-best paired eval R5 (Haiku 5.5)

Reviewer: `claude-haiku-5-5`. Scope: frozen R5 source, pins, receipts, and the failed one-shot resource calibration `current-pair-resource-calibration-luna-20261026-r1`. Read-only except this directory. No MPS, game episodes, training, checkpoint decode, lease or state writes, or test-suite run (the suite loads checkpoints).

## Verdict

NOT READY. Campaign stays ineligible. Calibration r1 stays FAILED and is not counted as a pass. Successor calibration needs a separate registration and the prerequisites below before any hardware probe.

Verified in this review:

- Pins: `verify_inputs()` from frozen R5 `worker.py` passed (23 input files, 2 support files, 23 frozen runtime files, harness `9748b3d6...d871`, protocol `85dd8263...246ad`, manifest `188e6d44...8068`, interpreter target `8dcafa78...216a`, native `022d41dd...b997e`, dependency inventory 13513 pins).
- Receipt anchors: `_receipt_anchor("best204")` and `_receipt_anchor("latest252")` pass with R5 modules only (`python -I -B`, `worker.__file__` and `paired_eval.__file__` both under R5). No checkpoint decoded.
- R5 `ResourceSampler` class body is byte-identical to R4 (sampler sha `4eb86941...`). R5 `supervisor.py` is identical to R4 (`ebf51e8e...`). R5 `paired_eval.py` differs from R4 only in `best180`→`best204` naming.
- Constants: freshness 1.0 s (4 × 0.25 s), startup 10.0 s, RSS and MPS caps 6 GiB each, separate. Schedule, bootstrap seed `764002`, and C4 primary match the protocol.

## Blockers (must close before successor calibration can be valid)

**B1. Probe imports contaminate the R5 module namespace.** `probe.py` imports R4 `worker` and `supervisor` (lines 16–18) before inserting R5 (line 20). That loads R4 `paired_eval` into `sys.modules`. Probe line 21 and the R5 worker's `from paired_eval import` then resolve to R4. `probe.stderr.log` confirms: the traceback at R5 `worker.py` line 152 reads `.../latest-best-paired-eval-prepare-haiku-20261026-r4/paired_eval.py`, line 26. Practical impact is small (same `require`, only naming differs), but the probe did not exercise R5 `paired_eval` as its source pins claim.

**B2. The probe never measured the representative load.** It failed before model-to-MPS (`probe-result.json`: `mps_teacher_inference_calls` 0). Even the intended loop is synthetic zero tensors. It does not run the worker's `evaluate` path: per-step `check_guard`, observation concatenation, `.to("cpu").tolist()`, per-episode fsync sink. It also never tested `torch.mps.driver_allocated_memory()` called from the background sampler thread while MPS inference runs. The 1.0 s gate and the 10.0 s startup bound are therefore still unmeasured, as the protocol itself says.

**B3. The executed worker version is unbound.** `calibration-receipt.json` records `r5_worker_sha256_at_probe_time: null`. R5 `worker.py` mtime is 21:32; probe launch is 21:31. The probe ran a worker version the receipt cannot identify. The current worker's `_receipt_anchor` may or may not be what ran. Successor launches must hash `worker.py`, `supervisor.py`, `paired_eval.py`, `probe.py`, and the launcher before launch, and again inside the process before any MPS call.

**B4. Execution-boundary checks were dropped without declaration.** R4 `worker.py` lines 151–155 required `raw_outer_exit == 0`, `raw_worker_exit == 0`, `all_owned_processes_absent`, `publication_failure_present is False`, `cancellation_lineage == []`, `source_pins_verified > 0`. R5 removed them for both labels. The parent-terminal and retained-best receipts have none of those keys, so R4's check could not pass on them. R5 now gates execution only on `audit.status == "passed"`. `audit.json` does carry `raw_exits` (outer 0, worker 0) and `owned_processes_and_groups_absent: true`, but R5 does not read them. This is a silent relaxation, and it must be restored against the audit fields, not the receipt keys.

**B5. The 1.0 s freshness gate is not enforced inside the worker.** Worker `guard()` and `require_live()` check thread liveness and error only. No after-read age check. The supervisor enforces age (`latest_resource_sample`, every 0.25 s). The worker keeps doing MPS work until the supervisor's next poll. The worker's half of the gate should use the same after-read rule and be measured in calibration.

**B6. Per-action lease read is unmeasured against the 590 s work budget.** `evaluate` calls `check_guard()` for every active env action (worker lines 422–423). Each `guard()` calls `_lease_check`, which parses `state.json`. Cost across roughly 512 episodes × thousands of actions is unknown. Overrun fails closed (`590-second inference work limit exceeded`), and a failed one-shot campaign cannot retry. Batch the lease check per decision batch, or measure its cost in the successor probe.

## Scope and non-blocking defects

- **M1 (medium). Supervisor RSS and MPS readings are not like-for-like.** The live cap uses `ps -o rss=` (current RSS, `supervisor.py` line 33) with a 0.5 s timeout. A `ps` stall raises `TimeoutExpired` and is classed as `resource_monitor_failure`, killing the one-shot campaign. Worker-side `_default_probe` (worker line 485) uses `ru_maxrss`, a high-water mark, but labels it `rss_bytes`. Conservative for the cap, but the two sides measure different quantities. Pick one definition and document it.
- **M2 (medium). Pins include bytecode.** `input-manifest.json` `frozen_runtime_files` includes `__pycache__/*.cpython-312.pyc` entries. Any import without `-B` rewrites them and breaks the pin. Pin sources only, or require caches absent.
- **M3 (low). Dead result fields.** `worker_result["publication_failure"]` and `["cancellation_lineage"]` (worker lines 559–562) are never set. The final `json.dump(..., allow_nan=False)` sits outside `try`; an exception there leaves no `worker-result.json` and reports `failed_worker` (fail closed).
- **M4 (low). Lease run_id template mismatch.** `protocol-proposed.json` `lease_contract.active_inference_diagnostic.run_id` is `latest-best-paired-eval-20261026-r5`. The protocol `run_id` is `latest-best-paired-eval-prepare-luna-20261026-r5`. `_lease_check` requires the exact protocol `run_id`. The parent must install the lease with the protocol's value.
- **M5 (low). Obscure expression.** `verify_module_origins` (worker lines 333–334) uses `dodge_rl.VecDodgeEnv.__module__ and __import__(...)`. Works; readability poor.
- **M6 (low). Name collision.** Supervisor publishes `preparation-receipt.json` inside the campaign output directory (supervisor line 349), the same name as the preparation receipt. Rename.
- **S1 (scope). Action mode only, existing D dev cohort.** 64 seeds `3489660928`–`3489660991`. No generalization or held-out claim. Bootstrap conditions on fixed checkpoints and seeds, not training-replicate variance. A CI crossing zero is inconclusive. Equivalence needs the full CI inside ±100 frames.
- **S2 (scope). Sampler differs from historical.** CPU float64 inverse-CDF is not the historical MPS `Categorical`. Protocol already says so.
- **S3 (scope). Tests not rerun.** `tests/test_paired_eval.py` (hash `cbb01cd6...`) loads checkpoints (`test_both_pinned_v3_checkpoints_load_strictly...`), so this review did not run it. `test-runs-attempt5.log` (hash `736d34e7...`) records 24 OK. Negative-binding claims rest on that log plus the parent's report.
- **S4 (scope). CPU validation not re-run.** `cpu-preparation-validation.json` (hash `c21a9256...`, status `passed`, `mps_operations` 0, `episodes` 0) reports strict CPU loads of both checkpoints. It postdates the worker edit. Not re-run here (checkpoint decode forbidden for this review).
- **S5 (scope). Lease slot now empty.** `state.json` (hash `c9f9fff1...`) has `active_inference_diagnostic` null and `active_long_campaign` null at review time. No campaign lease is installed.

## Successor calibration prerequisites (separately registered, no relaxation)

1. **New registration.** New run id and client request id. Do not retry r1. The reservation is parent-owned.
2. **Import isolation.** The probe loads only R5 modules, or frozen copies with pinned hashes. Assert `__file__` for `worker`, `paired_eval`, `supervisor`, `dodge_rl`, `numpy`, `torch`. Any R4 path aborts before MPS.
3. **Source binding.** Hash worker, supervisor, paired_eval, probe, launcher, interpreter, native `.so`, both checkpoints, audit, and receipts before launch, after launch, and inside the process before any MPS call. Any mismatch means no MPS.
4. **CPU gate with no MPS and no game.** Run `verify_inputs()`, `_receipt_anchor` for both labels, and strict CPU load of both checkpoints. Add explicit audit checks: `raw_exits` outer and worker 0, `owned_processes_and_groups_absent` true, `pins_checked_before_and_after` present, and `observer_wrapper_error_disposition` accounted. Restore R4's removed boundary intent against audit fields.
5. **Worker freshness.** Add the same after-read age check (≤ 1.0 s) to worker `guard()`. Startup 10.0 s unchanged.
6. **Representative MPS calibration, one shot, parent-authorized.** Run the worker's real `evaluate` loop with a fake or synthetic env (test helpers only, no game episodes), 64 active envs, sampler running, real per-action guard including lease read. Record first-sample delay, max interarrival gap, after-read age, RSS and MPS peaks against 6 GiB each, guard cost per step, and whether background MPS queries succeed. Thresholds unchanged.
7. **Lease-read cost.** Batch the lease check per decision batch, or show its measured overhead fits the 590 s budget.
8. **Parent review of the successor calibration receipt.** Only then may a separate campaign lease be installed. Campaign remains blocked until this step.

## Files inspected

See `receipt.json` for exact hashes.
