# Expanded evaluator r2 — source-only review

Scope: `expanded-evaluator-implementation-parent-20261026-r2/{expanded_eval.py,INTERFACE.md,tests/test_expanded_eval.py,manifest.json}`, compared with predecessor `expanded-evaluator-implementation-luna-20261026-r1/expanded_eval.py` (SHA `0b19e2c9…f21`). Read-only. No imports, no test runs, no native/checkpoint loads, no game or MPS calls.

Verdict: **not launch-clean.** One reachable blocker (list-vs-tuple at the native boundary). The stagger fix itself is correct.

## Findings

### 1. BLOCKER — excluded seed ranges passed as lists to native constructor

- Source: `expanded_eval.py:518-520` builds `excluded_ranges = json.loads(...)["training_excluded_ranges"]`, which yields list-of-lists. `_production_rows` forwards it at `:410` as `excluded_seed_ranges=excluded_ranges`.
- Native contract: `crates/dodge-rl-env/src/python.rs:290` takes `excluded_seed_ranges: Option<Vec<(u32, u32)>>`.
- PyO3 behavior: the vendored pyo3 is 0.27.2 (`Cargo.lock`; frozen `_native.cpython-312-darwin.so` contains `pyo3-0.27.2` strings). Its tuple extraction does `obj.cast::<PyTuple>()` (`pyo3-0.27.2/src/types/tuple.rs:906`), so a Python `list` pair is rejected.
- Trigger: `evaluate_registered` → `_production_rows` → first `env_factory(...)` call, for any cohort (benchmark, ranking, confirmation). Passes all static checks, then raises `TypeError` at the first construction.
- Consequence: deterministic failure before any row is produced; no output is published (fail-closed, no corruption). The 348 benchmark replay and every ranking/confirmation run fail. Inside the `try/finally` the RNG states are restored first.
- Why tests missed it: `FakeEnv` / `env_factory` lambdas take `**kwargs` and never type-check `excluded_seed_ranges` (test lines 100-104, 127-132). The predecessor has the same bug (`luna` lines 406, 513-515).
- Frozen runtime already does the conversion: `own/runtime/dodge_rl/dev_eval.py:32`, `identity.py:199`, `runner.py:591` all use `tuple(...)`. Golden rows were produced that way.
- Fix: `excluded_ranges = [tuple(pair) for pair in json.loads(...)["training_excluded_ranges"]]` at `:518`. Add a test that asserts `all(type(p) is tuple for p in kwargs["excluded_seed_ranges"])` in the fake env factory.

### 2. Hardening (not blocking)

- `expanded_eval.py:506-534`: `model.eval()`/`original_modes` are set before the `try`. If the RNG or mode `_require` in `finally` fails, it masks any earlier inference exception. Move the mode snapshot inside the `try`, or chain/log the original error.
- `expanded_eval.py:264-266`: `output_dir` existence is not checked. A missing dir fails only at `_write_exclusive` (`:549`), after the full compute.
- `expanded_eval.py:543`: `cohort_sha` re-reads the manifest after evaluation. Use the already-validated `chosen["manifest_sha256"]` instead, to avoid a TOCTOU gap.
- `expanded_eval.py:130, 270-273`: optional top-level `provenance`, `benchmark_measurement`, `observer` and extra limit keys are accepted but never validated or read. INTERFACE.md and the contract say to coordinate before freezing. Confirm no launch decision depends on them.
- `expanded_eval.py:479-494`: `import dodge_rl` runs `__init__` (which loads `_native`) before the origin re-check. The static SHA check at `:151-154` precedes it, so this is same-user TOCTOU only.
- `checkpoints.py:119` (called at `expanded_eval.py:502`): `torch.load(..., weights_only=False)` executes pickle. The bytes are SHA-pinned to accepted artifacts, so the trust boundary is the pin. Consider `weights_only=True` if the checkpoint format allows it.

## Checked and consistent

- Stagger fix: `active = sorted(envs)` with stable local keys, `actions[position]` mapped to active order, `completed[i]` keyed by local index and emitted in manifest order, `del envs[i], obs[i]` on terminal. No reset/filler. Matches `dev_eval.evaluate` ordering (`sorted(environments)`).
- Native API: constructor kwarg names and types match `python.rs:274-290`. `step` info keys (`bootstrap`, `score_delta_sum_raw_fixed`, `death_cause`, `fatal_gameplay_frame`, `death_observed_lethal_contacts`) match `episode()` at `python.rs:86-130`. Death causes: 6 native + `unavailable` matches `DeathCause::ALL` (`dodge-core/src/death.rs:26`).
- Accounting: `alive+1==gameplay` on terminal and `gameplay==alive==cap` on truncation match `env.rs:217-300`. `bootstrap = !terminated` matches `env.rs:283`.
- Pins, all re-hashed:
  - proposal r5 `187e0464…`; protocol `9e0d8202…`; seed proof `fe4b0cc6…` (`status passed`, 10 payloads, 110911 unique, collisions zero for ranking/confirmation).
  - benchmark manifest `a57410e1…`; ranking manifest `e4aafa70…`; confirmation manifest `d2594d71…` (count 1024/2048, first seeds `0xD1000000`/`0xD2000000`).
  - golden 348 rows `d6e91434…` (64 rows, seeds `0xD0000000..3F`). Recomputed performance: worst 375, Q1 867.0625, mean 3098.125, Q4 6003.875, best 8180, matching `_verify_incumbent_golden_rows:361`.
  - incumbent receipt `cb364589…` status in `RECEIPT_STATUSES`; checkpoint `b95228e5…`.
  - Six candidate checkpoint and receipt SHAs match proposal r5. All six receipt statuses are in `RECEIPT_STATUSES`.
  - 13 runtime members plus native `022d41dd…` match `RUNTIME_MEMBERS`.
- Operator precedence at `:232` (`A == B if C else D == E`) parses as intended.
- Confirmation gating (`:246-263`): winner ≠ 348, winner checkpoint pinned, comparator 348 only.
- RNG and mode restore (`:514-535`) and exclusive publication via `os.link` with pre/post hash checks (`:365-380, 549-550`) are sound.
- Result keys match `interface-contract.json` `result_required`. Performance order matches.
- Tests: 12 test methods, consistent with parent's claim. Staggered test does reproduce the r1 failure shape (`batch_size=5`, staggered deaths, seeds across chunks).

## Not verified / limits

- The native `.so` was not checked against repo source beyond the pyo3 version and kwarg-name strings. Binary-to-source identity is not established.
- Worker, launcher, and runner R2 are not reviewed (runner R1 is BLOCKED per brief).
- No test execution. Findings 1 and the checks above rest on reading source and pinned bytes.
