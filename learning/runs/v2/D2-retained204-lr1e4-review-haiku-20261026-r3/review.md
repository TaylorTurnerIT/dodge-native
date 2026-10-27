# D2 retained-204 lr1e-4 frozen review r3

Target: `learning/runs/v2/D2-retained204-lr1e4-prepare-luna-20261026-r3/`
Registration `68063348dede3050c4a8852c6314f4c95fd3a623e89c9499413f2325f4edad44`; runner `7543ba23a65c03e19b05015894b74a9c68e23e56e49daf1ba3ee3808b368f89d`; launcher `58bc5cb35ab531455d5218dd3a77dde84d441a12d361a99c9c8a0c83b33e4206`; preparation receipt `058a80ba911261af5ba42f8bcbc8639550a7fdcfe0b95e103251d984ba0c9937`.

## Verdict

No deterministic launch or terminal blocker found in the r3 delta. Prior F1/F2 (r1 review) and r2 prototype findings #1/#2 are closed in code. Parent-owned gates remain: exact lease install, unmocked full preflight, single launch, full `validate_outputs` on any real output.

Scope: static review of r3 sources, registration pin check against disk, and CPU-only focused tests. No preflight, worker, launcher, MPS, environment, game, training, checkpoint decode, lease install, or doc write.

## Prior findings status

- r1 F1 (helper import before digest check): closed. Helper path is in the critical set (`runner.py:365-374`). `load_verified_transition` (`runner.py:350-363`) checks canonical path, pin, and bytes, then execs the same hashed bytes. It runs at `runner.py:377`, after `verify_pins`.
- r1 F2 (LR record hashed live shared tensors): closed. `begin_transition_record` hashes the pre-override state (`runner.py:739-740`). `transition_record` compares immutable digests. Saved-copy LR asserted before save (`runner.py:817`) and on every embedded checkpoint in `validate_outputs` (`execute_once.py:192`).
- r1 F3 (archival labels): closed. Labels are external in `archival-labels.json`. Config bytes `f858a63c...` unchanged and pinned.
- r1 F4 (entry mismatch found only after 72 updates): closed. Phase-204 rows checked right after entry evaluation, before the first rollout (`runner.py:824`, per parent note; `validate_entry_evaluation` at `runner.py:677-683`).
- r1 F5 (`completed` status with finalization error): closed. Except paths set `status="failed"` (`runner.py` `except BaseException` and finalization `except`, after `:880`).
- r1 F6 (marker comment): closed. Comment at `execute_once.py:223-225` matches code. Registration read is still shape-only before marker (accepted).
- r1 F7 (non-atomic `execution-result.json`): not changed. Residual, accepted per r3 notes.
- r1 F8 (final digest from loop leftover): closed. Explicit `development-000276.json` read (`execute_once.py` ~171-173).
- r1 F9 (test coverage): partly closed. Two new CPU tests execute production helpers. Source contract still text-only.
- r1 F10 (MPS RNG untested), F11 (estimate 1319.457 s vs 1600 planned / 1790 hard), F12 (import order): unchanged, scope notes.
- r2 prototype #1 (transition module not pinned): closed by pin binding plus `load_verified_transition`.
- r2 prototype #2 (LR evidence): closed (see r1 F2).
- r2 prototype #3 (archival parent label): closed (see r1 F3).
- r3 terminal StopIteration at entry 204: closed. `expected_checkpoint_counters` returns explicit zeros for 204 (`execute_once.py:64-68`); `validate_outputs` uses it at `execute_once.py:175`. Worker counters at checkpoint 216..276 match `metrics` rows, which are emitted before `evaluate_at` (`runner.py:867-869` then `:871`).

## Checks performed

- Hashes: `runner.py`, `execute_once.py`, `resume_lr_transition.py`, `registration.json`, `preparation-receipt.json`, `source-manifest.json`, config, and the three r3 tests match registration pins and receipt values. Pin count 13770.
- Registration output `learning/runs/v2/D2-retained204-lr1e4-20261026-r1` does not exist; no collision.
- Worker result keys used by launcher (`elapsed_seconds`, `work_elapsed_seconds`, `peak_rss_bytes`, `peak_mps_driver_bytes`, `phase_updates`, `final_resume_next_episode_indices`) are all written at `runner.py` finalization (`:876`, `:901`).
- Launcher `r._VERIFIED_TRANSITION` is set by `r.load_registration` at `execute_once.py:283` before `validate_outputs` runs.
- Tests (CPU, no training):
  - `test_entry_counter_binding.py`: passed.
  - `test_entry_evaluation.py`: passed.
  - `test_source_contract.py`: passed (needs `PYTHONPYCACHEPREFIX=<prepare>/empty-pycache-prefix` and no `-I`, since `-I` ignores env; the registration requires it).

## Findings (non-blocking)

1. Low / hardening. `execute_once.py:68` uses bare `next(...)`. An out-of-range update raises `StopIteration`, not a named error. Production only calls it with `EVALUATION_UPDATES`, so no launch impact. Test accepts `StopIteration`.
   Fix: `next((...), None)` then `r.need(row is not None, ...)`. Then tighten `test_entry_counter_binding.py` to expect `ValueError`.
2. Evidence gap. No full synthetic fixture for `validate_outputs` (`execute_once.py:71-205`). New counter lookup and saved-LR assertion are only exercised by the focused helper test. Per brief, not an automatic runtime bug. Parent should decide whether to build a synthetic fixture before launch or accept the gap and run the full gate after.
3. Scope note. `execute_once.py:17` imports `runner` and the worker runs `runner.py` as a script before any pin check. Launcher and runner bytes rely on frozen directory and parent preflight, same as the accepted posture. The helper is now post-verify; this is not an r3 regression.
4. Residual runtime risk. The entry gate (`runner.py:824`) requires 64 MPS rows at phase 204 to equal the predecessor rows exactly. Only an MPS run can confirm this. If evaluation is not bit-reproducible, the lease is consumed by entry evaluation only (fail-fast, not full training). Parent should confirm the predecessor was produced by the same evaluate path on MPS.
5. Carry-over. F7 atomic publication and F12 import order unchanged; F11 estimate unchanged.

## Blockers

None for deterministic launch or terminal path in the r3 delta.
