# Current-pair resource calibration R3 frozen review

Verdict: **BLOCK**. Do not write the parent reservation and do not authorize the probe. This is a read-only source review. No probe, MPS, game, training, checkpoint, lease, state, or source write occurred. The review did not run the CPU tests, so it adds no test evidence beyond the logged 8-test result. It is not hardware acceptance and makes no qualification, D3, B/E, student, or held-out claim.

## Inspected hashes (sha256)

- `calibration-plan.json` `b65924df4979a05526205d7765e6611b90f49c7e14c07f8bbf341dbe549fde54`: match
- `source-pins.json` `ceb8f5ec33a953c39711363fbaaf29dce976da956ca8f4745673c5b7dfc8c5c2`: match. 60 file pins, 0 directory pins, 0 mismatches on disk. The "56" in earlier text is stale.
- `launch_once.py` `c710bd5acabba52bed76bce61f0ad617a2d5024876f06fc6409ba87497db2ca0`: match
- `probe.py` `131354592814fc2c9d16a12d2d044a3d8e139ed81534e35d19bd1d3b83d09b22`: match
- `cpu_preflight.py` `020fdc79a0ed3d66a690cb5055c3a79c87076b87ae4975cdee420466d69f73be`: match
- `test_calibration_cpu.py` `af877f5e5e651f65a25e1eb09d5cb466667e8f8b0b06a86e9be3238291a8db8b`: match
- `cpu-preflight-validation/cpu-preflight.json` `4737c9f1c484b1834f62d179cf594fec757b39ee9017df12a282f1efa2e0dc50`: match
- `cpu-tests.log` `9ebbbe68c888cb93053da678a2a17ecf907219d054661042d5d330280dd34e6d`: match
- R6 preparation receipt `d0d9020657412bf2a5b0040fea05c35c5e49df7bd3e48a09aee5c6752ac3193a`, protocol `547d33a4716b7be7e03c663f06a9c784d2497d212e2155e07ac872e4d1612655`, input manifest `4cafb2cf6ccbb6de77d7d3d05ad9c59674a2d621bc8e88235eeb905fdbba3f00`: match
- R6 `worker.py` `c663543638e6bc5aea684a3dd38e27c079bd633f784590219d148d16fa0d190e`, `paired_eval.py` `51b78e6e74dcbaf3d9b04302d6f9ea1e37ea92779e9d237c48dd03ec77946475`, `supervisor.py` `0aacb8e539585312c053f70518a041a487ca09598865d88e111c5a284b4b25bd`, `freeze_artifacts.py` `ecaf765735b9c30a0d8d4efc11bbabeb067f46224964f90003504bfa86ab5e47`: match
- Live `learning/runs/v2-orchestration/state.json` `32a11f1430886d4f61796832f9930496cb278387bfe3ac85dde5b3f78c334d26` (provenance only, read-only): `active_long_campaign` null, `active_inference_diagnostic` null
- `parent-reservation.json` and `launch-once.marker`: both absent

## Blockers

**B-1. The probe spawns the base interpreter, not the pinned venv.** `launch_once.py:146-147` pins both `resolved_target` and `lexical_path`. Line 157 spawns `str(target)`, the uv base `cpython-3.12.15-macos-aarch64-none/bin/python3.12`, not `python/.venv/bin/python`. Read-only check under `-I -B`: the base binary reports `sys.prefix` = the uv base, and `find_spec` returns None for both `numpy` and `torch`. `probe.py:152-153` imports numpy and torch outside the `try` block, so the child exits 1 with no `probe-result.json`. The marker is claimed first (`launch_once.py:154`), so the one-shot is consumed with no measurement. `test_calibration_cpu.py:32` uses `sys.executable` with a harmless child that imports nothing, so no current test can catch this.
Fix: spawn the lexical venv path. Venv `pyvenv.cfg` applies with site enabled, and `-I` does not disable site. Before the marker, run a CPU-only `lexical -I -B -c` check that asserts `sys.prefix` is the venv directory and that numpy and torch origins are under `python/.venv`. Add a test for the spawn argv. Re-freeze plan and pins, then re-review.

**B-2. Bytecode is written into the frozen R6 directory, and the receipt claim is false.** `cpu_preflight.py:22-28`, the launcher's in-process preflight, and `test_calibration_cpu.py:166` load R6 `worker.py` (and through it `paired_eval.py` and the frozen runtime `dodge_rl`) with no bytecode guard. `latest-best-paired-eval-prepare-luna-20261026-r6/__pycache__/worker.cpython-312.pyc` and `paired_eval.cpython-312.pyc` are dated 2026-10-25 22:16:57. R6 was frozen at 22:02, and the timestamp falls inside the R3 preparation window. The R3 preparation receipt still says `writes_outside_new_r3_directory: false`. Pins do not cover `__pycache__`, so every pin check passes while the frozen directory has changed. This review did not delete or modify that cache. Ownership is for the parent to decide.
Fix: set `sys.dont_write_bytecode = True` before any import in `launch_once.py`, `cpu_preflight.py`, `probe.py`, and the test file. Parent commands must use `-B` and `PYTHONDONTWRITEBYTECODE=1`. Correct the receipt claim.

**B-3. The MPS gate can pass with nothing measured.** `probe.py:239` uses `max(..., default=0)`. Line 241 enforces the 6 GiB cap, and 0 passes it. `worker.read_latest_resource_sample` (around `worker.py:441`) accepts any non-negative int for `mps_driver_bytes`. `probe.py:266` counts successful MPS queries, but nothing requires it. A sampler that returns 0 on every sample passes the MPS cap while measuring nothing. This is the same class as R6 B-4.
Fix: for `status = passed`, require `mps_sampler_query_success_count == resource_sample_count` and `mps_driver_highwater_bytes > 0`.

## Narrow limits (fix in the same re-freeze; not blockers alone)

- **N-1. Active window contradicts the plan.** `probe.py:233` stops only when forwards are at least 240 and elapsed is at least 30 s. Nothing stops at 45 s. `calibration-plan.json:167` (`active_window_seconds_max: 45`) and `:169` ("stop by 45 seconds target") disagree with the code. Plan `:149` (`"mps_forward_calls": 8`) is stale next to the minimum of 240. Enforce 45 s in code, or change the plan text.
- **N-2. RSS monitor race can fail a successful child.** `launch_once.py:172-182`: the `poll()` check precedes `ps`. A child that becomes a zombie during `ps` can return rc 0 with empty or zero RSS. Line 182 raises, `monitor_error` is set (`:193`), and the launcher raises at `:234` after the probe succeeded, with no `launcher-result.json`. Fix: after `ps`, return if `process.poll()` is not None before validating the value.
- **N-3. Evidence fields are constants.** `launch_once.py:250` hard-codes `pins_checked_before_and_after: 2`. `probe.py:291` hard-codes `pins_checked_before_import_and_mps: 3` in `finally`, even when the run failed before any pin check. `launch_once.py:224` hard-codes `term_sent: True`. The observer disposition strings are constants. Replace them with counters measured at each call.
- **N-4. The live gate is narrower than the production check.** `worker.py:543-564` `_lease_check` also requires `kind`, `review_status`, `campaign_launch_authorized`, `no_concurrent_long_mps_training`, and review hashes. The R3 check (`launch_once.py:45-59`, `probe.py:70-84`) requires five fields. It fails closed on the current state. Either match a calibration-specific schema deliberately, or record why the narrower check is sufficient.
- **N-5. Plan anchors are not enforced in code.** The reviewed plan SHA `b65924…`, `cpu_preflight_evidence_sha256` `4737c9…`, and the preparation receipt SHA `b7724a3f…` are not checked by any code. The reservation's `plan_sha256` is the only binding. The parent must verify `b65924…` before writing the reservation.
- **N-6. `--output` is still caller-chosen.** `launch_once.py:131` creates whatever path is passed. The marker is fixed (`:18`, `:62`), so the one-shot holds. Pin the evidence directory, or require it to sit under the R3 directory.
- **N-7. Test gaps.** `test_calibration_cpu.py:65` and `:85` stub `spec_from_file_location`, so the real CPU preflight never runs on the CLI path. `:32` (`sys.executable`) masks B-1. `:117` sets `launcher.MARKER` globally with no restore.
- **N-8. Timeout "identity" is recorded but not compared.** `start_new_session` makes PGID equal PID, so no foreign group is signalled. The behaviour is acceptable. The evidence label overstates what is checked.

## Checked OK (against concrete code)

- Marker is fixed (`launch_once.py:18`, `:62`) and claimed only after reservation, interpreter, live-state, and CPU-preflight checks (`:146-154`).
- Live state is checked before the marker (`:152`), before MPS load (`probe.py:190-194`), and at every guard (`:204`).
- Pins are checked before import and before MPS (`probe.py:144`, `:166`, `:190`).
- Measurement gates reject empty and short data: nonempty gaps and ages, at least 20 samples, freshness and gap at most 1.0 s, forwards at least 240, active time 30–90 s (`probe.py:85-95`).
- Guard count matches `worker.evaluate`: `check_guard` at `worker.py:482`, `:491`, `:508`, `:526` gives 9 per decision iteration over 64 envs. One pass is 64 + 72 = 136, which the CPU test asserts.
- RSS units are correct: `worker.py:571-572` converts `ru_maxrss` from bytes on darwin.
- Timeout branch writes evidence and group-absence proof (`launch_once.py` around `:200-233`).
- R6 `worker.evaluate` signature and the R6 frozen files match their anchors.

## Required before re-review

- Fix B-1, B-2, and B-3, and the narrow items N-1 through N-7.
- Re-freeze the plan and pins. Replay the CPU tests with `-B` and `PYTHONDONTWRITEBYTECODE=1`.
- Re-review the re-frozen source. Then the parent may write a new reservation bound to the new plan SHA, if training permits.
- Do not retry the failed R1 probe. Do not write a reservation from this review.
