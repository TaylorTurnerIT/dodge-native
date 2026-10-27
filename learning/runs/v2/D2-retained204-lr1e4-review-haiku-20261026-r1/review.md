# D2-retained204-lr1e4 frozen review (r1)

Target: `learning/runs/v2/D2-retained204-lr1e4-prepare-luna-20261026-r1/` (frozen, read-only review).
Verdict: **not ready for lease install.** Two pre-lease fixes required (F1, F2). No finding invalidates the accepted best204 parent chain or the frozen r1 authority chain.

Scope: static source review, hash and JSON cross-checks, one stdlib probe of the transition helper, one CPU-only torch probe of Adam `state_dict()` sharing, and one read-only run of `test_source_contract.py`. Not run: preflight, worker, launcher, MPS, environment, games, training, checkpoint decode, lease install. Source-contract pass is not runtime acceptance.

## Blockers (fix and re-review before lease)

### F1. Resume helper is not bound by origin or critical set before import
- `runner.py:340` verifies pins; `runner.py:342-344` critical set omits `lr_transition_helper_path`; `runner.py:378` imports `resume_lr_transition`; `runner.py:388-390` checks the helper pin only after import.
- Correction to the prior review: the helper is in `pins` (`registration.json`, pinned `c44d1682...`) and `verify_pins` (`:340`) runs before the import (`:378`). It is not executed unverified. The real gaps are: module origin is never asserted (import resolves via `sys.path`, not the registered path), the helper is not in the critical set, the helper digest check runs after import, and hash-then-import reads the file twice (TOCTOU).
- Fix: add the helper path to the critical set at `:342-343`. Before `:378`, assert the pinned digest and load the helper from the registered path (`importlib.util.spec_from_file_location`) or assert `resume_lr_transition.__file__` resolves to the registered path after import. Keep the `:388-390` check or move it up.

### F2. Transition record does not measure the claim it asserts
- `runner.py:694` takes `optimizer_before = optimizer.state_dict()`. Probe confirmed torch Adam `state_dict()` shares `exp_avg` tensors with live state and copies only the `param_groups` dicts. So the excluding-LR digest is computed over shared objects after mutation (`resume_lr_transition.py:181-182`, called from `runner.py:700-703`).
- Probe: simulated moment mutation inside the override window passed `transition_record` with `non_lr_fields_changed: []` and equal excluding-LR digests.
- `resume_lr_transition.py:190` hard-codes `"non_lr_fields_changed": []`.
- Saved state is not LR-checked: `runner.py:756-757` copies optimizer state; `runner.py:771` saves it; `execute_once.py:172-198` never reads `state["optimizer"]` param-group LR.
- Negative controls cover counter, phase, raw frames, resume index, and selection receipt only (`cpu_restore_and_controls.py:38-48`). None cover moments or LR.
- Impact: the one-variable claim in `lr-transition.json` is true by construction (the only write is `resume_lr_transition.py:166`, and `guarded_update` asserts LR around each update), but the record does not prove it. Evidence weakness, not an observed defect.
- Fix: before override (`runner.py:693-696`), deep-copy the optimizer state and store its measured excluding-LR digest. Compute `non_lr_fields_changed` by diffing the copy against the post-override state. Assert saved `state["optimizer"]` group LR equals `0.0001` before `runner.py:771`, and re-check on the final checkpoint in `execute_once.py` near `:172`. Add CPU negative controls: mutate `exp_avg` in the override window (must raise); set a group LR to `0.0002` (`assert_effective_lr` must raise); tamper saved optimizer LR (launcher check must fail).

## Pre-lease hardening (recommended)

### F4. Entry reproduction is checked only after all 72 updates
- `runner.py:789` evaluates entry; training starts at `:791`. The comparison exists only at `execute_once.py:165-169`, after the single-use run.
- Impact: a non-reproducing entry wastes the lease and up to 1790 s of work before rejection.
- Fix: in the worker, compare `development-000204` rows to the predecessor rows (`reg["parent"]["source_evaluation_path"]`, hash already checked at `runner.py:270-271`) immediately after `:789`; raise before `:791`.

### F5. Worker status stays "completed" on finalization failure
- `runner.py:825` sets `status="completed"`. The `except` at `:836-839` does not reset it. `valid_worker_result` still rejects via `"error" not in value` (`runner.py:599`), so acceptance is safe; the receipt is misleading.
- Fix: add `status="failed"` to the `except` update.

### F6. Launch marker comment misstates order
- `execute_once.py:224-225` says byte checks precede the marker. Actual: marker at `:232-233`, `load_registration` at `:254`. Registration is read unverified at `:226` (shape-checked only).
- Fix: correct the comment, or move the marker after `:254` and before `:263`.

### F7. Primary receipt interruption contradicts comment
- `execute_once.py:332` writes `execution-result.json` with an exclusive open. The publication handler (`:246-249`) can raise mid-write, leaving a partial file. Comment at `:340` says the primary receipt "remains untouched".
- Fix: correct the comment, or write to a temp file and `os.replace` it.

### F8. Final checkpoint digest uses leaked loop variable
- `execute_once.py:172` uses `certificate` from the last iteration of the loop at `:136-137`. Correct today (276 is last). Fix: read `development-000276.json` explicitly.

## Scope notes (no fix required for r1 preparation)

### F3. Archival fields flow into identity
- `D2-retained204-lr1e4-config.json:25` `parent_checkpoint_sha256` = `ce9c03c8…` is the stale D1 checkpoint (`registration.json:362`, `milestone3-D1-curriculum-r1/checkpoint-000009-candidate.pt`), inherited from `milestone3-D2-freeze-r1/D2-config.json:25`.
- `D2-retained204-lr1e4-config.json:32` `phase_settings.run_seed` = `5562881586070242562` (parent D2 seed). The env uses `reg["run_seed"]` (`runner.py:726`).
- `runner.py:717` embeds the whole config into identity, so every new checkpoint carries these stale values. Authority fields are correct (`runner.py:718-721`: parent `f1300…`, run seed from registration).
- Fix: no config byte change (`f858…` pinned, `runner.py:31`). Label both fields as archival and non-authoritative in the registration and findings.

### F9. Tests are contract-string checks
- `test_source_contract.py:16-24` checks text and index order only. No helper or worker execution. No unit test for `resume_lr_transition` in this directory. CPU controls do not cover moments or LR (F2).

### F10. MPS RNG restore not exercised here
- `runner.py:682` → `checkpoints.py:138-142` → `restore_rng` MPS branch (`checkpoints.py:40-42`). Equality is checked at `runner.py:683-693` before environment construction (`:723`). Fail-closed; observed only in a real run.

### F11. Resource estimate is a linear scale, not a bound
- Scaled estimate 1319.46 s (`1177.43 × 9216/8224`) against preregistered 1600 s and hard 1790 s. Evaluation and environment time may not scale with optimizer steps. Guard enforces the caps regardless.

### F12. Launcher imports runner before checks
- `execute_once.py:17` `import runner as r` runs before `load_registration` (`:254`). `runner.py:1-60` has no side effects, so harmless now. Keep module top level side-effect-free.

### F13. Sibling r2 directory exists and is not covered
- `learning/runs/v2/D2-retained204-lr1e4-prepare-luna-20261026-r2/` exists, mtime 21:31–21:33, with `attempts/` and `cpu-restore-and-controls.json` being written. Not reviewed here. Launch must bind to r1 hashes or to a separately reviewed r2.

## Verified closed (static, receipt cross-check)

- Parent authority hashes match files: checkpoint `f1300e4e…` (`runner.py:22`), candidate receipt `7fd26ae3…` (`:25`), selection `f21b0298…`, audit `b93cfd24…`, whole receipt `059f927d…`.
- Parent receipt validator is strict: schema, status, counters, phase, identity, native/policy, wall fields, and whole-run acceptance (`runner.py:211-285`, schema check `:214-215`).
- Parent audit embeds 7 candidates `[180,192,204,216,228,240,252]`, 7 audited, pins 13767, candidate 204 checkpoint and certificate match (`runner.py:272-284`; audit.json).
- Restore validator is stricter than predecessor. Predecessor (`D2-best180-branch-prepare-luna-20261026-r1/runner.py:153-171`) checked only run id and counts, no receipt binding. Current `runner.py:172-208` binds counters, resume indices, identity, config, runtime, native, policy.
- Checkpoint load pinned by file digest (`runner.py:676`, `:682`).
- Restore order: restore `:682` < equality `:683-693` < override `:699` < environment `:723`. Source-contract test passed.
- Override validates parent LR `0.0003` before the only write (`resume_lr_transition.py:157-167`, write at `:166`, assert `:167`).
- Config transition exact: `validate_config_transition` on archived D2 config and arm config returns only `ppo.learning_rate` (`0.0003 → 0.0001`); only top-level `ppo` differs.
- Counters: total updates 324 (`execute_once.py:199-201`); raw-frame conservation (`:210-212`); parent abandoned records preserved (`:124-131`); episode journal (`:132`).
- Seed: `3791628418` outside excluded ranges (`runner.py:136-137`); ranges match config (`config:10-23`, `runner.py:38`); no other run JSON references it.
- Output validator: all 7 development certificates, cohort seeds, checkpoint sidecars (`execute_once.py:136-164`); entry equals predecessor rows (`:165-169`); final checkpoint identity and counters (`:170-201`).
- Startup and final cancellation: `execute_once.py:240-252`, `:256`, `:273-274`, `:299-311`, `:312-360`; worker `runner.py:552-580`, `:835-853`.
- Lease: worker every 0.15 s (`runner.py:566-567`), launcher every 0.1 s (`execute_once.py:275`), postflight reload (`:292`).
- Resource caps: `runner.py:46-48`, `:124-134`, `:576`; sampling 0.05 s.
- Score removed from gate: `progress_passed("D2")` uses mean alive frames (`survival_gate.py:29-30`); launcher check `execute_once.py:213-214` matches. Score reported only.
- Accounting separate: trajectory 3352.0462366251204 and campaign 4129.756859292152 (`runner.py:26-27`, `:761-765`, `:824-833`; `execute_once.py:70-77`).
- Cleanup: `stop_owned` with 5 s TERM and 5 s KILL (`execute_once.py:28-60`); group-absent check `:283`; failure path `:301-305`.
- Source manifest: all 16 listed files match on disk (checked).

## Inputs inspected (SHA-256)

See `receipt.json` for the full list with hashes.
