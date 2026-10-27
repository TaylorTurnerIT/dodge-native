# Expanded evaluator R4 publication repair — source-only review

Reviewer: Haiku 5.5 review sub-agent. Read-only on the reviewed directory. No imports, no test runs, no native/MPS/checkpoint loads, no games, no training, no leases, markers, or shared edits. Runtime member files were hashed and grepped only.

Scope: `learning/runs/v2/expanded-evaluator-publication-repair-parent-20261026-r4/{expanded_eval.py,tests/test_expanded_eval.py,tests/test_success_path.py,receipt.json,diff.patch,test.log}`, the R3 predecessor, R2 and R3 reviews, `expanded-eval-parent-integration-20261026-r1/interface-contract.json`, and the frozen runtime member bytes.

## Verdict

**The R3 blocker is fixed.** No new blocker found by reading source. Evaluator-level source is acceptable for the next step. This is not launch clearance: runner, worker, and launcher are not reviewed here, native identity and runtime qualification are not established, and the open nonblocking items below remain.

## Reviewed bytes (SHA-256)

- `expanded_eval.py` `a3439c33152b082471cd9f9a36ef4bb03783b9544ae7c1e3fe1878e607b128aa` (matches parent receipt and task)
- `tests/test_expanded_eval.py` `a80c26eb2de5b5629fa989813293fad3646d8e15bda5005dca8d3fed4b277e41` (matches receipt)
- `tests/test_success_path.py` `520055a64a9927ebe5ef71af478bc49ebda4224453b6cac30f7313a5a502e04d` (matches receipt)
- `diff.patch` `23bb471b980350e9b89f7982bb34eae506aa6b8b9a0bf9a27b2ec79dc282810c` (matches receipt)
- `test.log` `b9e6988f129ea895af89fe1049d25f153eaad2d9be3ad975452c8abc4f160dd4` (matches receipt)
- `receipt.json` `b96b04188fa3c09b2bc58bdf6c160089d073dff39fa1ad1899a69247c5901208` (not self-recorded)
- Predecessor R3 `expanded_eval.py` `d8dadbfec213a93f11b79ceeeb02a6dea7584878b5efc1c05d4628954ac371e7` (matches receipt `predecessor_source_sha256`)
- `interface-contract.json` `9d0facf0a480f80e3dccd535e463a39524cf29689734619d9b2179889b6e1e99`
- R3 `review.md` `19ec7a8546a8afb01b4daf363e4665674162d63e1333e73b1a46606ce93bbce5`

## Source change

Full diff R3→R4 of `expanded_eval.py` is one line:

- `:548` `cohort_name, chosen["manifest_sha256"])` → `cohort_name, reg["cohorts"][cohort_name]["manifest_sha256"])`

Checks:

- `reg` is bound once, at `:462`, from `_validate_static`, and not reassigned in `evaluate_registered`. The name resolves.
- `cohort_name` was validated against `COHORT_KEYS` and `reg["cohorts"]` keys in `_validate_static` (`:121`, `:207`).
- The value equals the validated `chosen["manifest_sha256"]` (`:209-214`), so the intent of R3 is kept. `chosen` is not used anywhere in `evaluate_registered` (grep confirms only `_validate_static` uses, `:209-259`).
- Other names in `evaluate_registered` and `_production_rows` are bound. Manual read of every identifier found no other out-of-scope reference. A mechanical undefined-name check (for example pyflakes) would confirm this. I did not run it, since the brief forbids execution.

## Success-path test coverage

`tests/test_success_path.py` runs real `evaluate_registered` with real CPU Torch/NumPy, a fake `dodge_rl` package and submodules in `sys.modules`, a `Teacher` fixture, and a `FakeEnv` strict on tuple pairs. It asserts:

- `strict_env` raises unless `excluded_seed_ranges == [(1, 2), (5, 8)]` with tuple pairs. This covers production wiring of `_native_excluded_seed_ranges` → `_production_rows` → constructor. It closes the R3 finding 3 gap for the production path. The other test fakes in `test_expanded_eval.py` still take `**kwargs` without type checks.
- All 8 seeds construct, so `tracker["boundaries"]` has length 8.
- `_summarize`, `_validate_rows`, `_write_exclusive`, and the post-hash readback run. `json.loads(out.read_text()) == result`.
- `result["cohort_sha256"] == "b"*64`, which is the fixture's `reg["cohorts"]["ranking"]["manifest_sha256"]`. This asserts the exact changed expression, not just absence of NameError.
- `test_predecessor_fails_after_inference_without_publishing` loads R3 `expanded_eval.py` through the same fixture, expects `NameError` matching `chosen`, and asserts `out` does not exist. It reproduces the R3 failure.

Test log: 15 tests, `OK`, 13 in `test_expanded_eval.py` plus 2 in `test_success_path.py`. I read the log. I did not run the tests, so the pass is parent-reported.

## Limits of the success-path evidence

These are fixture-scoped. They are not runtime qualification.

- `_validate_static` is patched to return a fixture tuple. Real pins, real candidate receipts, real cohort manifests, confirmation gating, and the real return-shape contract are not exercised by any test.
- `_trusted_module_cache` is patched. The real preloaded-module origin check runs in no test.
- The benchmark success branch (`_verify_incumbent_golden_rows`, `:542-543`) and the confirmation branch are not exercised on the success path. The 348 golden-row test covers verification in isolation only.
- `inspect.getfile` is patched for `Teacher`. The real `OmniscientEntityTeacher` origin check is not exercised.
- Native `.so`, PyO3 acceptance of the tuple list, MPS, real games, and real checkpoint deserialization are not exercised.

## Runtime member check (read-only)

I hashed the 13 runtime members and the native binary under the frozen runtime root. All 13 bytes match `RUNTIME_MEMBERS` and `NATIVE_SHA256` in `expanded_eval.py:33-48`. I grepped the imports reachable from `dodge_rl/__init__.py`, `models/__init__.py`, `dev_eval.py`, `identity.py`, `checkpoints.py`, and `models/teacher.py`. Lazy imports resolve to `.ppo`, `.models.teacher`, `.dev_eval`, `.supervision`, `.identity`, and `._native`, all in the member map. So `_trusted_module_cache` should not reject a legitimately imported runtime module on the sequential second candidate. This is still source-level, not an execution check.

## Nonblocking items still open

1. **`finally` masking (carried from R2).** `model.eval()` and the `original_modes` snapshot (`:511-512`) run before the `try` at `:522`. If inference raises and the RNG or mode `_require` at `:538-540` also fails, the `ValidationError` replaces the original exception. Low consequence (fail-closed), but it hides the root cause. Fix: move the mode snapshot and `model.eval()` inside the `try`, or chain the original error.
2. **Optional registration metadata is accepted but not validated.** `:129-130` allows `provenance`, `benchmark_measurement`, `observer`, and `:270-275` allows extra limit keys. The evaluator never reads them, so they cannot change evaluation output. `interface-contract.json` does not enumerate them, and it says to coordinate before freezing. Worker and launcher must validate launch-relevant metadata independently. The receipt already says this.
3. **`patch.dict(sys.modules, modules)` hygiene** (`tests/test_success_path.py:85`). On exit it restores the original `sys.modules`, which can evict modules first imported during inference. Low risk for these tests. It is a test-isolation hazard, not a product defect.
4. **Predecessor regression depends on a sibling directory** (`tests/test_success_path.py:113`). The test loads `expanded-evaluator-native-boundary-repair-luna-20261026-r3/expanded_eval.py`. If that directory is removed or moved, the test errors. Acceptable while the R3 directory is kept as evidence.
5. **Test-only coverage gaps** listed above. These are expected for the fixture approach and are already named in `receipt.json` `test_limits`.

## Prior findings status

- R2 blocker (list vs tuple at native boundary): fixed in R3, and production wiring is now covered by `strict_env` in the success test.
- R3 blocker (`chosen` NameError at success publication): fixed in R4 by the one-line change. Covered by the success test. The predecessor test reproduces the failure.
- R3 finding 3 (fake env does not type-check tuples): closed for the production path by `strict_env`. Still open for the other fakes, which is minor.
- R3 finding 4 (interface contract vs optional keys): still open, nonblocking, see item 2.
- R2 hardening: `output_dir` existence is checked (`:266`), `cohort_sha` uses validated record (`:548`), `finally` masking still open (item 1), import-before-origin check (`:479-494`) still open as same-user TOCTOU, `torch.load` pickle trust (`checkpoints.py:119`) still open and bounded by SHA pins.

## Not established by this review

- Native `.so` source identity and PyO3 acceptance of tuples, beyond the SHA pin.
- Real `_validate_static` on real launch registration.
- MPS backend, real games, real checkpoints, resource budgets, determinism.
- Runner, worker, and launcher. Runner R2 is still separate pending work and is not launch-clean as a system.
- Test results beyond the parent's `test.log`. I did not execute the tests.
