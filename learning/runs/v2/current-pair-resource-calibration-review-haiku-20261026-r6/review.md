# Frozen review: current-pair resource calibration R6

Target: `learning/runs/v2/current-pair-resource-calibration-prepare-luna-20261026-r6/`
Run: `current-pair-resource-calibration-luna-20261026-r6`
Mode: source-only adversarial review. No code executed, no probe, MPS, reservation, marker, state, or lease touched.

Verdict: **CHANGES REQUIRED before parent reservation.** Two MEDIUM and one LOW finding.

## Verified

- Pins match: plan `a1c49bc5…`, source-pins `23c50cf8…`, freeze manifest `d2d537de…`, CPU preflight receipt `d837ef9e…`.
- CLI is real. `cpu_preflight.py` has argparse `--output` and a `__main__` guard. `launch_once.py` runs it with `-B` and the owned bytecode prefix, and reads `cpu-preflight-validation/cpu-preflight.json`.
- Marker is claimed (`claim_once`, `MARKER.open("x")`) only after CPU preflight, interpreter re-check, reservation re-read, and `check_live_state`.
- Live state check requires `active_long_campaign` null and exact `active_inference_diagnostic` fields. State path is pinned.
- Sample gates in `probe.py` (`validate_representative_measurements`): ≥20 active samples, nonempty gaps ≤1.0 s, after-read ages ≤1.0 s, ≥240 forwards, active 30–45 s, positive active MPS required, startup zero allowed.
- Source-pins `directories` is 0. No timer-driven tree hashing.
- Deadlines: probe 90 s work and 45 s active; launcher child timeout 110 s; cleanup 10 s; outer 120 s.
- `cpu-tests-r6-final3.log`: 16 tests, OK.

## Findings

### R6-F1 MEDIUM: CPU preflight does not assert strict-load properties
- `cpu_preflight.py:49–50` records `training` and `requires_grad_any` without asserting them. `cpu_preflight.py:55` hardcodes `"status": "passed"`.
- `launch_once.py:106` gates only on `status == passed` and `mps_operations == 0`.
- Trigger: a checkpoint load returns `training=True` or a parameter with `requires_grad=True`, and the load does not raise.
- Consequence: the launcher claims the one-shot marker and spawns the probe. The probe's strict check (`probe.py` load loop) rejects the model only after the marker is consumed.
- Fix: assert in `cpu_preflight.run` before writing the receipt, or check `strict_cpu_loads` fields in `launch_once.py` before `claim_once`.

### R6-F2 MEDIUM: 6 GiB MPS driver cap is enforced only at guard boundaries
- `probe.py:256` checks MPS only inside `guard()`. `worker.py:586–592` (`ResourceSampler._sample`) records MPS without enforcing. `launch_once.py` `monitor_rss` reads RSS only.
- Trigger: MPS driver allocation exceeds 6 GiB inside a forward or evaluate segment with no guard call before the 110 s child timeout.
- Consequence: over-cap state persists until the next guard or the timeout. Exposure depends on guard cadence, which I did not verify in `worker.evaluate`.
- Unit test `test_inflight_mps_cap_fails_on_numeric_driver_overage` covers the value check only.

### R6-F3 LOW: surviving owned group on normal exit is not signaled
- `launch_once.py:416–418`: after a normal child exit, a surviving PGID member raises with no signal and no cleanup evidence.
- Trigger: `probe.py` exits 0 while a descendant survives. Probe spawns no children, so the trigger is narrow.
- Consequence: leftover process after launcher returns. The failure record (`process_group_absent: null`, `absence_status: unknown`) is truthful.

## Not verified
- No tests, probe, or MPS run. Source-only.
- `worker.evaluate` guard cadence (sizes R6-F2).
- `worker._default_probe` MPS query semantics.
- Live state and reservation contents (none present).

## Authority
No marker, reservation, state, lease, checkpoint, source, or bytecode written outside this review directory.
