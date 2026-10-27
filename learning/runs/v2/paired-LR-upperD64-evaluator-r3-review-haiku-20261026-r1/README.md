# Paired upper-D64 evaluator r3: source-only review

Scope: `paired-LR-upperD64-evaluator-luna-20261026-r3/` (`paired_eval.py`, `test_paired_eval.py`, `registration-inputs.json`, `README.md`, `artifact-manifest.json`). Read-only. No imports, no execution, no checkpoint load, no native import, no environment, no MPS, no lease or state edits. Frozen artifacts untouched.

## Verdict

No blockers. The r3 source is a sound candidate for the parent's registration step, with the limits below. Real backend behavior is not verified: the 13 CPU tests use fake policy and environment, so they do not exercise `_build_registered_backend` against the frozen runtime.

## Hash checks (sha256, read-only)

- `paired_eval.py` `25021313…6d61`, `test_paired_eval.py` `918ec2e8…8c`, `README.md` `5d72a7a8…adf5f`, `registration-inputs.json` `24b9cce0…56e1`, `cpu-tests.log` `42dd5b9a…6249`, `report.md` `b2b9e954…0fd0e32`, `seed-manifest.json` `e11e9d6a…886c`. All match `artifact-manifest.json`.
- Frozen runtime `D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime/dodge_rl/`: 13 tracked members (`__init__.py`, `_native.cpython-312-darwin.so`, `checkpoints.py`, `critic_diagnostics.py`, `dev_eval.py`, `gradient_alignment.py`, `identity.py`, `models/__init__.py`, `models/teacher.py`, `ppo.py`, `supervision.py`, `survival_gate.py`, `train_teacher.py`) hash to the member map. The native is `022d41dde9bace0b4f4c4c06b9b4ed007bc2c60013cd98734086e587d7bb997e`. Both training registrations carry this identical 13-entry map.
- Training registration pins, metadata receipt, and both endpoint metadata files match the constants in `paired_eval.py` and `registration-inputs.json`.
- Parent proposed registration `paired-LR-upperD64-registration-parent-20261026-r3/registration.json` has SHA `c6a1aab9…1274`. Its 10 top-level keys equal the `validate_registration` field set. `collector_sha256` equals the r3 `paired_eval.py` hash. Its 13 member hashes equal the frozen map.

## Native and runtime contract (checked against source)

- Constructor kwargs in `collect_d2_rows` (L240–243) match the `VecDodgeEnv.__init__` signature in `crates/dodge-rl-env/src/python.rs` and match `dev_eval.development_environment_config`.
- Info keys used (`seed.evaluation`, `seed.actual_seed`, `startup_frames`, `gameplay_frames`, `alive_frames`, `score_raw_fixed`, `score_delta_sum_raw_fixed`, `objective_return`, `terminated`, `truncated`, `bootstrap`, `death_cause`, `fatal_gameplay_frame`, `death_observed_lethal_contacts`) match the `episode()` output in `python.rs`. The step return keys (`observations`, `terminated`, `truncated`, `info`) match `step_batch`.
- Frame accounting in `env.rs` `advance()` (L195–260): a dead frame increments `gameplay_frames` but not `alive_frames`, so `alive+1 == gameplay` for terminated rows. Truncation happens at `gameplay >= raw_frame_cap` with no death, so `alive == gameplay == 18000`. `fatal_gameplay_frame = gameplay_frames`. `bootstrap = !terminated`. Objective is `score_delta_sum/65536 + alive/100 - 5·terminated`. `validate_rows` (L65–105) encodes these exactly.
- Death names match `DeathCause::as_str` in `dodge-core/src/death.rs`. Observation shapes match `observation()` (`[b,1,14]`, `[b,80,16]`, `[b,80]`, `[b,80]`). The teacher forward signature and dtype checks match `OBSERVATION_KEYS` and `logits` usage.
- Seed range: the 64 upper-D seeds `0xD0000040..0xD000007F` lie inside `training_excluded_ranges[1] = [0xD0000000, 0xD000007F]`. This is the same exclusion the registered D-seed path uses (`seed_start = 0xD0000000`), so it is consistent, not a defect. "Prior nonuse not proven" stays a stated limit.
- Checkpoint load goes through `load_checkpoint(expected_sha256=…)`, which hashes raw bytes before `torch.load(weights_only=False)`. Acceptable under the pin.

## Guard and ordering

- Pre-import guard at L435 precedes `import dodge_rl` (L443). Pre-constructor guard at L469 precedes `model_factory()` (L472) and checkpoint load (L474). Per-seed and per-step guards run in the collect loop; a final guard runs before publication (L511).
- Manifest check precedes everything (L491). Preloaded `dodge_rl` is rejected at L421 before import. Injected backends are rejected at L467–468. `evaluate_registered` is absent.
- Publication uses `os.link` to a temp file, which fails on an existing target (L334). This is immutable publication.
- Weight, gradient, RNG, and mode preservation (L229–311) is implemented as checked restore plus `require`. Logic re-read; no bypass found.

## Findings (all low, none blocks)

1. **Unpinned bytecode in frozen runtime.** `runtime/dodge_rl/__pycache__/` and `models/__pycache__/` contain `.pyc` files (`__init__`, `checkpoints`, `dev_eval`, `identity`, `teacher`, `models/__init__`). These are not in the member map. `_build_registered_backend` (L441–449) imports the runtime without `sys.dont_write_bytecode` or `PYTHONDONTWRITEBYTECODE`, unlike the derivation script, which sets it. Consequence: a tampered `.pyc` whose recorded source mtime and size match would run despite the source pin; and the frozen tree may gain new `.pyc` writes. Trigger requires write access to the frozen tree. Fix: set `sys.dont_write_bytecode = True` before the import and reject or ignore `__pycache__` in the runtime tree, or run with `-B` and an empty pycache prefix.
2. **Pin covers listed members only.** `_verify_runtime_pins` (L379–384) iterates the map, not the tree, so an extra unpinned `.py` in the runtime root would not be detected. Current tree has no extra source files. Fix: enumerate the tree and require exact set equality with the map, excluding `__pycache__`.
3. **`dodge_rl` origin check runs after import.** `sys.path.insert(0, root)` (L441–442) runs only when root is absent from `sys.path`. If root is present later in `sys.path` and an earlier entry supplies a `dodge_rl`, that package executes at L443–449 before the origin check at L450–458 rejects it. Fix: always insert root at index 0, or check `importlib.util.find_spec("dodge_rl").origin` before importing.
4. **Pre-guard file reads.** `evaluate_with_registered_backend` reads the caller registration (L493), the metadata file (L496, `read_text()` with no hash check), the parent receipt, and both training registrations before the first `check_guard()` (L497). The metadata content is only checked against the pin later at L428. No import or constructor runs, so this is fail-closed, but it contradicts the L497 comment that the byte-budget gate runs first. Fix: hash the metadata path before parsing, and move the first guard above `validate_registration`.
5. **Mode-capture naming.** `inference_modes` (L236) is captured after `model.eval()` (L235), so `mode_changed` detects in-loop mode changes relative to eval. This is correct but the name and the "original modes restored" message suggest otherwise. Cosmetic.
6. **Non-persistent buffers.** The weight check uses `state_dict()`, which omits non-persistent buffers. A change to them during inference would not be detected. Stated limit only.

## Coverage gaps

- No CPU test exercises `_build_registered_backend` with the real `dodge_rl` import, the real native, or real `load_checkpoint`. This is expected under the CPU-only constraint; it must be covered by a runtime smoke that the parent runs under its own authority.
- The endpoint metadata derivation (`derive_metadata.py`) is r2 code copied via AST into r3-compatible function text. I verified `state_dict_sha256` is byte-identical in r2 and r3. Its output hashes were not recomputed here.
- No "completed training receipt" exists for either endpoint. The parent metadata is the only attestation (stated in README).

## Limits

- Native `022d41…` binary is pinned by hash. Its build provenance from `crates/dodge-rl-env` was not verified, since building is out of scope.
- Environment and checkpoint behavior was not exercised. Everything above is by reading source and hashing bytes.
