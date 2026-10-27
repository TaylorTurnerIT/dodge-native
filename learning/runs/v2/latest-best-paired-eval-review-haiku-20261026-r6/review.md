# R6 frozen review and R2 calibration probe review

Verdict: **BLOCK** the R2 calibration probe as written. R6 frozen artifacts match their anchors. The probe and launcher have concrete blockers that must be fixed and re-frozen before any hardware use. This is a CPU-only, read-only review. It is not hardware acceptance and makes no qualification, D3, B/E, student, or held-out claim.

## Inspected hashes (sha256)

- R6 preparation receipt `d0d9020657412bf2a5b0040fea05c35c5e49df7bd3e48a09aee5c6752ac3193a`: match
- R6 protocol `547d33a4716b7be7e03c663f06a9c784d2497d212e2155e07ac872e4d1612655`: match
- R6 input manifest `4cafb2cf6ccbb6de77d7d3d05ad9c59674a2d621bc8e88235eeb905fdbba3f00`: match
- R6 harness (`paired_eval.py`, `supervisor.py`, `worker.py`, `freeze_artifacts.py`) hashes recomputed; the `harness_sha256` anchor was not recomputed in this pass
- Calibration plan `54f870a0f28ccd7734acca28ce7daab0fdc937b457addd8b9e0bccec6e2b7485`: match
- Calibration source pins `2c73e8e79861a5bbed2f78fbbafce7267e5d2d6e1a3d70cbed8e1596a639e69f`: match (56 file pins, 0 directory pins)
- `launch_once.py` `5f4317ec8821c48074139c6c61e5ab3c50270cbd8e7ec39762bb283d6e268ca4`, `probe.py` `1be007d694a5be6c540852c59845c39f2a48ecfa0dc50e64c47c6fa9330ebb72`, `cpu_preflight.py` `020fdc79a0ed3d66a690cb5055c3a79c87076b87ae4975cdee420466d69f73be`: match frozen values
- R6 `worker.py` `c663543638e6bc5aea684a3dd38e27c079bd633f784590219d148d16fa0d190e`: match
- R6 `paired_eval.py` `51b78e6e74dcbaf3d9b04302d6f9ea1e37ea92779e9d237c48dd03ec77946475`: match
- R6 `supervisor.py` `0aacb8e539585312c053f70518a041a487ca09598865d88e111c5a284b4b25bd`: match
- R6 `freeze_artifacts.py` `ecaf765735b9c30a0d8d4efc11bbabeb067f46224964f90003504bfa86ab5e47`: match
- R2 preparation receipt `32d9ac99fa065acb6657a185944aaa50fdecd8b0209fc1c9571a256934205162`: per freeze output, not recomputed

Not inspected in this pass: the R5 review and R1 failure receipt and parent failure audit (the R2 README and plan were used for R1 facts), the full 56-file pin set beyond the hash summary, and `paired_eval.py` / `supervisor.py` bodies beyond the anchors above. The parent should treat those as open.

## Blockers

1. **Launcher crashes after burning the one-shot marker.** `launch_once.py:119-121` creates `launch-once.marker` with exclusive open. `launch_once.py:126-127` then reads `plan["interpreter"]["resolved_target"]` and `plan["interpreter"]["sha256"]`. `calibration-plan.json` has no `interpreter` key (grep count 0). The launch raises `KeyError` with the marker already consumed, so no probe runs and no `launcher-result.json` is written. The plan's `import_hash_sequence` and README also claim an interpreter pin that is not in the plan. Fix: add an `interpreter` object (`resolved_target`, `sha256`) to the plan, or move the pin into `source-pins.json`. Either changes a frozen hash, so re-freeze and re-review. Also move the marker creation after all pre-spawn checks, including the interpreter check.

2. **No live authoritative-state check before hardware.** The reservation check (`launch_once.py:95-106`, `probe.py` `check_reservation`) only compares static fields, including `no_concurrent_long_mps_training: True`. Nothing reads live training or campaign state. `worker._lease_check` requires `active_long_campaign` to be null, but that function is only in the campaign path and the probe does not call it. The README says the launcher never reads `state.json`, which conflicts with the required gate. Fix: pin the authoritative state path and hash in the plan. Then read it in the launcher before the marker and in the probe immediately before the MPS load, and require no active long campaign, no active training or MPS job, and no cancel request. Record the observed state hash in the receipt.

3. **One-shot marker is per output parent, not per plan.** `launch_once.py:119` uses `args.output.parent / "launch-once.marker"`. A second launch with a different parent directory creates a new marker and passes again. The reservation still reads `authorized_once: True` and nothing marks it consumed. Fix: use a fixed path such as `HERE / "launch-once.marker"`.

4. **Freshness and sample gates pass on empty data.** `probe.py:191` (`max(gaps, default=0.0) <= 1.0`), `probe.py:204` (`max(after_read_ages, default=0.0)`), and `probe.py:206` all default to zero when there are no samples or gaps. The only sample-count gate is `resource_sample_count > 0` (`probe.py` near the `len(forward_calls) == 8` check). The workload is 8 forward calls over 64 synthetic envs, which may finish well under 1 s and produce one or two samples at 0.25 s period. That passes freshness and interarrival gates without measuring anything. Fix: require explicit minimums before `status = passed`. Require a non-empty gap list, at least a fixed number of complete samples derived from the MPS-active window, and an exact guard count. With `GUARD_ACTION_CHUNK = 8` (`worker.py:566`), the probe should expect 64 construction guards plus 9 guards per decision iteration over 8 iterations, which is 136. Assert equality. Do not relax the 1.0 s or 10 s thresholds.

5. **Scope: the probe as written is a smoke test, not a representative freshness or IO qualification.** The workload is one batch of 8 decisions for 64 envs. The original goal was about 30–45 s of representative load. A pass from this plan only shows that the probe code path runs once. Parent needs one of two options: label any pass as `smoke_only, representative_qualification: false`, or write a new plan that repeats the synthetic decision loop until the MPS-active window reaches the target duration within the 90 s budget. The second option is a workload change and needs fresh review.

## Narrow-scope findings (fix before probe, not blockers alone)

6. **TOCTOU between pin check and MPS load.** `probe.py:133` hashes all pins before the sampler starts. `probe.py:149` then waits up to 10 s for the first sample. `probe.py:153` loads the model to MPS. No pin or reservation check runs in that window. Fix: move `verify_pins` and `check_reservation` to directly before line 153.

7. **Launcher RSS monitor can fail a successful run.** `launch_once.py:146` runs `ps -p <pid>` with `check=True`. If the child exits between `process.poll()` and `ps`, the call raises. The monitor then sets `monitor_error`, and the launcher raises before writing its result, after the marker is already consumed. Fix: check `process.poll()` before each `ps` call, and treat a vanished PID as end-of-sampling, not an error.

8. **Timeout kill leaves no probe evidence.** On outer timeout (`launch_once.py` around the `child_timeout` branch), the launcher sends SIGTERM to the process group. The probe's `finally` block (which writes `probe-result.json`) will not run on SIGTERM. This is fail-closed, but cleanup evidence is lost. Note it in the receipt disposition. Keep the 10 s cleanup budget unchanged.

9. **Probe and launcher paths have no tests.** `tests/` contains only `test_paired_eval.py` (30 test functions). Nothing exercises `probe.py`, `launch_once.py`, or `SyntheticEnv` (`probe.py` synthetic `info` dict against `_validate_step`, `_canonical_row`, and death fields). The first real execution is the first test. Parent should replay the focused CPU tests and add a CPU-only dry run of the launcher with a stub reservation and a stub interpreter in a temp directory, with no MPS.

10. **Preflight cost is fine.** `cpu-preflight-validation/cpu-preflight.json` reports `elapsed_seconds: 2.29` and `cpu-preparation-validation.json` reports 1.38 s. The launcher preflight plus probe re-verification fits the 120 s outer bound. No change needed.

## What the R6 freeze itself supports

- Anchors for receipt, protocol, manifest, plan, and pins match. `cpu-preparation-validation.json` reports 0 MPS operations and 0 game episodes, with strict CPU loads for both checkpoints.
- Worker freshness logic (`worker.py:419-449`) fails closed on missing, partial-tail, malformed, future, and stale samples. The helper is correct as written. It is not sufficient alone because of finding 4.
- Probe wiring to R6 `worker.evaluate` with `check_guard` and `episode_sink` matches the signature at `worker.py:452-455`.

## Required before re-review

- Fix blockers 1–5. Re-freeze the plan and pins, because changing `calibration-plan.json` changes its SHA and the reservation anchor.
- Parent replays focused CPU tests independently. This review did not run tests.
- Parent registers a fresh run ID and client request ID, and installs a new exact reservation bound to the new plan SHA.
- Confirm live authoritative state before any MPS work.
- No retry of the failed R1 probe.

No hardware, MPS, game, training, checkpoint, lease, or state write occurred in this review. Writes were limited to this review directory.
