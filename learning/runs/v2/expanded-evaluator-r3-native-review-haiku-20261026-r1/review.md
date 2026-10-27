# Expanded evaluator R3 native-boundary repair — source-only review

Reviewer: Haiku 5.5 review sub-agent. Read-only on the reviewed directory. No imports, no test runs, no native/MPS/checkpoint loads, no games, no leases, markers, or shared edits.

Scope: `learning/runs/v2/expanded-evaluator-native-boundary-repair-luna-20261026-r3/{expanded_eval.py,tests/test_expanded_eval.py,receipt.json,diff.patch,test.log}`, the parent validation receipt, `expanded-eval-parent-integration-20261026-r1/interface-contract.json`, the R2 review, and read-only checks of `crates/dodge-rl-env/src/python.rs` and the frozen runtime `dodge_rl/__init__.py`.

## Reviewed bytes (SHA-256)

- `expanded_eval.py` `d8dadbfec213a93f11b79ceeeb02a6dea7584878b5efc1c05d4628954ac371e7`
- `tests/test_expanded_eval.py` `a80c26eb2de5b5629fa989813293fad3646d8e15bda5005dca8d3fed4b277e41`
- `receipt.json` `f764f1e772d178176fcdc6f84375c9c2252b831debf698026e6407094cf57553`
- `diff.patch` `2f7bc34f094aa3bf92450311e4796f5270229e602b0b16105e04b1e147b9d015`
- `test.log` `513753e45c0d72fb5304dab556d796ad177f028c7db055f7a8c49d0bd5b022b8`
- `interface-contract.json` `9d0facf0a480f80e3dccd535e463a39524cf29689734619d9b2179889b6e1e99`
- R2 `review.md` `0ede8afdecddaadd5dfe06d83e2699567283b2859c499fa8ae9989ee5c6a2f3d`
- Parent validation `receipt.json`: read, hash not recorded.

Verdict: **not launch-clean. One blocking defect.** The R2 list-vs-tuple blocker is fixed correctly. The R3 edit introduced a new `NameError` on the success path.

## Findings

### 1. BLOCKER — `chosen` is undefined in `evaluate_registered`

- Location: `expanded_eval.py:548`, `cohort_name, chosen["manifest_sha256"])`.
- Cause: `chosen = cohorts[cohort_name]` is a local of `_validate_static` (`:209`). `evaluate_registered` (`:456-556`) never assigns `chosen`, and there is no module-level `chosen`. A grep of the file shows only the `_validate_static` uses (`:209-259`) and `:548`.
- Trigger: any call to `evaluate_registered` that passes validation, completes `_production_rows`, and passes the post-inference checks. This affects benchmark, ranking, and confirmation alike.
- Consequence: `NameError` at `:548`, after the full inference run and after the RNG/mode restore in `finally`. `check_guard()` at `:553` and `_write_exclusive` at `:554` are not reached. Nothing is published, so the failure is fail-closed. But every successful evaluation fails after consuming its full compute budget, including the 348 benchmark replay. The R3 claim "use already validated chosen manifest SHA" is the right intent, but the name is out of scope.
- Why tests missed it: the 13 tests never drive a successful `evaluate_registered` through `:548`. The only `evaluate_registered` tests (`:219-240`) fail before the guard. `test.log` shows 13 passes, but that does not cover this path.
- Fix: in `evaluate_registered`, use `reg["cohorts"][cohort_name]["manifest_sha256"]`, or have `_validate_static` return the chosen record. Then add a test that runs the success path with a fake env, or run a static undefined-name check (for example `pyflakes`) over the file. That check does not execute the module.

### 2. Native boundary wiring — verified correct (no finding)

- `expanded_eval.py:523` calls `_native_excluded_seed_ranges`, which returns `[tuple(pair) ...]` (`:452-453`). That value goes to `_production_rows` (`:524-525`), then to `env_factory(... excluded_seed_ranges=excluded_ranges)` (`:411`).
- Native constructor: `crates/dodge-rl-env/src/python.rs:290` takes `excluded_seed_ranges: Option<Vec<(u32, u32)>>`, so tuples are required.
- `dodge_rl/__init__.py:3` re-exports `VecDodgeEnv` directly from `._native`, so `dodge_rl.VecDodgeEnv` is the PyO3 class and not a Python wrapper.
- The frozen runtime uses the same tuple conversion (`dev_eval.py:32`, `identity.py:199`).
- Limit: `tuple(pair)` does not check pair length or element type. The protocol bytes are pinned (`PROTOCOL_SHA256`, `:163`), so this is acceptable.

### 3. Test gap for the native boundary (non-blocking)

- `tests/test_expanded_eval.py:80-91` tests a closure defined inside the test (`strict_native_boundary`), not the production call. It proves the helper output is tuples. It does not prove `_production_rows` forwards tuples to the env.
- The fake env factories take `**kwargs` and never type-check `excluded_seed_ranges` (`:113-117`, `:140-145`).
- Fix: have the fake factory assert `all(type(p) is tuple for p in kwargs["excluded_seed_ranges"])`.

### 4. Interface-contract provenance mismatch (non-blocking)

- `receipt.json` lists `allowed_optional_parent_sections` (`provenance`, `benchmark_measurement`, `observer`) and `allowed_optional_limits` as coming from `interface-contract.json`. The contract at the hash above has no such fields. It only says extra keys need coordination before freezing.
- The code accepts those optional root sections (`:129-130`) and extra limit keys (`:270-275`) without validating or reading them. This is the optional-root-key ownership issue from R2, still open. Resolve it before freezing, or remove the acceptance.

### 5. Carried-over R2 hardening, still open (non-blocking)

- `finally` masking: `model.eval()` at `:512` precedes the `try` at `:522`. If inference raises and the RNG or mode check in `finally` also fails (`:538-540`), the `ValidationError` replaces the original exception.
- `_validate_static` now checks `output_dir.is_dir()` before evaluation (`:266`). Fixed.
- `cohort_sha` reread after evaluation: fixed by the R3 change, but its scope is broken (finding 1).
- Import-before-origin-check (`:479-494`) and `torch.load` pickle trust (`checkpoints.py:119`): trust rests on SHA pins and same-user boundary, as R2 said.

## Checked and consistent

- Stable IDs: `_production_rows` keys `envs`/`obs`/`completed` by local index, uses `sorted(envs)` with `actions[position]`, and emits `episode_index: offset + i` in manifest order (`:403-449`). The staggered test covers this with `batch_size=5`.
- Publication and guard boundary: `_validate_static` runs before the first `check_guard()` (`:464`). Guards fire before construction, per step, and before the post-inference checks. `_write_exclusive` (`:554`) follows the final guard (`:553`). Output uses `os.link` with a pre/post hash check (`:365-381`, `:555`).
- Registration validation: static pins for proposal, protocol, seed proof, candidates, incumbent receipt and checkpoint, golden rows, benchmark reference, cohort manifests, runtime members, native, and review records are all checked in `_validate_static` before `evaluate_registered` calls `check_guard()`.
- Pins: `diff.patch` touches only three hunks (`:263-270`, `:520`, `:545-548`). The pin constants are unchanged from R2, including native `022d41dd…`, incumbent checkpoint `b95228e5…`, incumbent receipt `cb364589…`, and golden rows `d6e91434…`. I did not re-hash the pinned files myself. R2 did.
- Metrics: `_summarize` returns `worst`, `q1_bottom_quarter_mean`, `mean`, `q4_top_quarter_mean`, and `best` over alive frames, in the required order, plus `death_causes` for all seven causes.
- Confirmation gating (`:246-263`) and the seed-vector checks (`:92-113`) are unchanged.

## Limits

- Source-only review. No execution. The blocker in finding 1 is established by reading the source; a static name check would confirm it mechanically.
- Native `.so` identity, actual PyO3 acceptance of the tuple list, runtime qualification, backend determinism, and resource budgets are not established. The fake tests cannot show them.
- Runner R2, worker, and launcher are not reviewed. Runner R2 is still separate pending work and must not be treated as launch-clean as a system.
- The 13 tests are the parent's claim. I read them and the test log. I did not run them.
