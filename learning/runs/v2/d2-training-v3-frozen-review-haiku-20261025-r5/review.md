# Frozen review: D2 normal 72-update adapter r5

Reviewer: Claude Haiku 5.5 (read-only). Date: 2026-10-25 (UTC 21:05 start).
Scope: `learning/runs/v2/d2-training-v3-adapter-prepare-20261025-r5/` plus parent receipt `d2-training-v3-parent-prepare-20261025-r2/` (registration-r8, pin, preparation-final-receipt-r7).

## Verdict

No blocking findings. Parent may proceed with the corrected normal run, provided it records findings F1 and F2 below (both are provenance/receipt issues, not training-path defects).

## Hash verification (read from disk, sha256)

| File | Digest | Matches |
|---|---|---|
| runner.py | 0176ab99b6762e4d7c9be414461e3406237e0d1cd632d5cde66a0259bd3a0b93 | registration-r8 pin, preparation-final-receipt-r7 |
| execute_once.py | 9bfc62b1c4eaa0fb103d20710623f37aa53caaf1de8be7bbbbd20c94ec6c843e | registration-r8 pin, final receipt |
| README.md | 052e24245dce680fad36389d74923193706a26b0b4b9ff814088f2ce0a82e932 | final receipt |
| test_contract.py | 9241172c597ca605fe6fabbcbb24261f14f328075e4a66c729dcd49ad45f85e7 | final receipt |
| test_torch_restore.py | faf0c55671fb304deb5f5b0d7720ec502826fa1da675c5032395279c0049b9a9 | final receipt |
| test_normal.py | 2e977329e360e147e516f27bad9d3bf5b8cc9fb9de5243e64bfda2066cceb432 | final receipt |
| registration-r8.json | d502c6761064727a610127fc58073e3a4c062fc928ea1e26de5718ad6aee6dcb | external pin registration-r8-pin.json |
| dependency-inventory.json | 2957832457c39751998012f4aeb4440f5d7570250ae9ab072ee10d86dd970ed6 | INVENTORY_SHA; 13513 entries with `sha256` metadata |
| Pinned count | 13560 | not rehashed (parent measured 0.58 s; only the pin file and inventory were spot-checked) |

Native `_native.cpython-312-darwin.so` (022d41…) and the 13.5k runtime pins were not rehashed; parent-reported.

## Source read

Read in full: `runner.py` (568 lines), `execute_once.py` (336 lines), `test_contract.py` (357), `test_normal.py` (120), `test_torch_restore.py` (52), `README.md`, `implementation-result.json`, `registration-r8.json`, `registration-r8-pin.json`, `preparation-final-receipt-r7.json`. `previous_preparation_input_drift.json` checked by hash only. Read `dodge_rl/survival_gate.py` `progress_passed`: D2 threshold `>= 3060` on mean alive frames, matching `validate_outputs`.

Not read: the `dodge_rl` package beyond grep hits (`ppo.py`, `dev_eval.py` body, `checkpoints.py` body, `VecDodgeEnv`); `torch-fixture.log`; `restoration-validation-r7.json`. Validator assumptions about `rollout_step`, `gameplay_frames` = raw frames, and `transitions`/`optimizer_steps` shape rest on the parent's claim that the 48-update run emitted the same payloads. The `test_normal` actual-payload fixture (`critic-diagnostic-D2-20261025-r2/training-episodes.jsonl`, 7 MB) exists and is read by the test.

## Checks passed by reading

- Registration: external digest checked before any read; all limits, lease, seed (810631976, outside excluded ranges), parent lineage, config, policy, native, and pins match constants.
- Worker: pre-restore fingerprint on model/Adam/RNG before environment or gradients; inherited 48 + new 72 = 120; checkpoint file digest and registration digest are separate fields and separate arguments.
- Episode journal: completed-before-reset ordering per `rollout_step`; per-slot replay, skip and missing-reset rejection; final next index = current + 1; raw-frame conservation over completed episodes plus 64 abandoned live episodes.
- Launcher: exclusive marker before any subprocess; exclusive marker outside the failure writer (second launch raises with no receipt write); TERM/KILL on exact owned group only; `os.killpg` never reached after a proven-absent group; post-worker postflight re-verifies registration, runtime, and lease.
- Timing: work 1600 enforced by worker; total 1800 enforced by launcher and by worker finalization; inherited monotonic start validated as finite and not in the future.
- Bytecode: empty absolute `PYTHONPYCACHEPREFIX` and `-B` in the launch command; `check_import_cache` runs pre- and post-worker.
- State writes: lease read is fail-closed on malformed or changed content.

## Findings

**F1 (low, provenance) — stale `implementation-result.json`.**
Path: `learning/runs/v2/d2-training-v3-adapter-prepare-20261025-r5/implementation-result.json` lines 5–11 and 49.
Trigger: anyone reconciling receipts against this file.
Consequence: it records `runner.py` as `c26943b5…` and `validation_script_sha256` as `fc111af8…`. Actual runner is `0176ab99…`; the final receipt records validation script `996356cc…`. The file is not read by the launcher, so no execution effect, but the receipt contradicts the frozen source. Fix: mark it superseded or regenerate it from current bytes.

**F2 (low, receipt consistency) — signal in the publication window can leave `execution-result.json` with `status: "passed"`.**
Path: `execute_once.py` lines 298–300 (primary `save` at 299, return-code computation at 300); the `except r.Cancelled` at 306–320.
Trigger: SIGINT/SIGTERM arrives after line 299 and before the `return_code` logic completes.
Consequence: `handle` raises `Cancelled`; the handler writes `publication-failure.json` (status failed, exit 1), but the primary `execution-result.json` already says `passed` with no `parent_signal`. Exit code and failure marker still block acceptance, so no false success results. But the README claim "interrupted primary receipt remains untouched" is only true for signals before line 299. Fix: write the primary receipt as the final step after the decision, or document the window and require parent to read `publication-failure.json` before accepting.

**F3 (low, scope) — post-worker validation runs in an uncapped launcher process.**
Path: `execute_once.py` lines 140–147 (`import dodge_rl.checkpoints` and two `ckpt.load_checkpoint` calls in the launcher).
Trigger: any large checkpoint decode after the worker exits.
Consequence: this memory is not covered by the 6 GiB RSS/MPS caps. Deadline is checked only after the call returns, so an overrun fails closed (nonzero) but is not interrupted. No silent success path found.

**F4 (limitation, not a defect) — MPS cap is an instantaneous sample.**
Path: `runner.py` lines 318–326. `torch.mps.driver_allocated_memory()` is read every ~0.05 s; RSS uses the kernel high-water mark. A transient MPS peak between samples is unobserved. Accept as stated limitation or add a torch-side high-water hook; no action required for this run.

## Prior-finding dispositions (from parent list)

- 1 self-hash removed: confirmed (no field; external digest only).
- 2 distinct checkpoint/registration digests: confirmed in code and test_normal.
- 3 real payload + multi-reset ordering: confirmed in code; actual fixture exists; rollout-step payload shape not re-verified against runtime source.
- 4 config pin, seed binding, cumulative counters: confirmed (`PPO` constants, `CONFIG_SHA`, `inherited` vs `counters`).
- 5 absolute empty cache prefix and -B: confirmed. 13513-entry inventory pinned; no 5 s hash watchdog present.
- 6 timing policy, T0 in launcher, no hash-cycle timing: confirmed.
- 7 launcher late-publication raise, nonzero exit, failure marker, no resignal after absence: confirmed in code; tests call current `execute`. Window noted in F2.
- N1 completed-run mutation: confirmed (test passes per log `contract-tests-final.log`, 24 tests OK).
- N2 grace at 1601/1602: confirmed as test in `test_normal.py`.
- N3 clock: monotonic; no real-time claim present in code.
- N5 hash cost: parent-reported 0.58 s; not re-measured.
- N7 single-use output intentional: confirmed.
- N8 atomic state writes: parent-side only; not reviewed here (outside this source).

## Limitations

Did not run tests, import code, read the native module, or rehash the 13.5k pins (parent-reported). Did not read the full `dodge_rl` package. Did not read `torch-fixture.log` or `restoration-validation-r7.json`. Historic 214 tests and 48-update performance are not treated as validation of the 72-update run.
