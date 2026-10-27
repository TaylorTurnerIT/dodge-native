# Frozen review r2: latest-best paired eval (native Haiku, readonly)

Target: `learning/runs/v2/latest-best-paired-eval-prepare-luna-20261026-r2/`
- preparation receipt `40657b9443e5aee179ca46fbdf807b4e4642edbbcbb9999af980456370b41660` (matches)
- protocol `5b6910133b33cd5e8350581e42230864fa9902bf18b0617f9af233a65b2ee954` (matches)
- input manifest `ca1cfbe01b6cfdb06e65aa17b5c974ec8e59167e7bbf33d2480324b2a3e1f227` (matches)
- harness `8d5a56509f5b44171f4cfa222064a9ad3eaf61a9408787018b9da1623b3db10a` (recomputed from `harness_source_files`, matches)

Scope: read-only. No games, env construction, training, optimizer, gradients, `freeze_artifacts.py`, source/ledger/lease/checkpoint edits. Hashes of every inspected input are in `receipt.json`.

Lines below refer to the frozen target files unless marked otherwise.

## Verdict

No blocking defect reproduced. F1, F2, and F3 are closed in code. Launch is gated on one unresolved item (R1). R2 is a budget risk that the parent should measure or narrow before the one-shot run.

## Closure of prior findings (Sonnet r1)

**F1 (live-step `death_fields`): closed in code.**
- `worker.py:344` runs `_validate_step` on every step. `worker.py:345-354` builds a row, calls `death_fields`, and writes it only when `terminated or truncated`. `_canonical_row` (`worker.py:280-289`) is reached only from that branch.
- `test_paired_eval.py:50-60` now makes calls 1-2 live (`truncated=False`, `death_cause: None`). `test_paired_eval.py:136-164` runs them through `evaluate` to the cap. This reproduces the r1 failure and passes.
- Gap: no committed test has `terminated=True` on any step. `FakeEnv.step` never terminates (`test_paired_eval.py:59`). The live-to-death path is therefore untested in committed tests. The parent already plans an independent test; it is required before launch.
- Terminal branch consistency: frozen `dev_eval.death_fields` (`dev_eval.py:41-61`) is the same helper the worker calls. Both committed control files (`development-000180.jsonl`, `development-000252.jsonl`) have 64/64 terminated rows whose `death_cause` values are in the Rust `DeathCause::as_str` set and whose `fatal_gameplay_frame` equals `gameplay_frames`. The terminal branch is therefore consistent with real Rust output.

**F2 (dependency bytes): closed as truthfully scoped.**
- `worker.py:64-89` pins all 13,513 inventory entries by size and SHA-256 and checks that the installed Torch/NumPy package membership (13,512 files, bytecode excluded) matches the pins exactly. `worker.py:90-94` binds the manifest to the inventory hash and scope. The parent's dependency-preflight log shows the same 13,512 count and inventory hash.
- Residual scope, not material to current use: transitive pure-Python packages that Torch imports (for example sympy, jinja2, networkx, fsspec) and dist-info metadata are not pinned. Stdlib, OS frameworks, and driver binaries are not pinned. The inventory scope string (`worker.py:71`) states the Torch/NumPy-and-interpreter scope. The README should not describe the closure as complete for Torch's full import graph.

**F3 (lifecycle tests): closed for the stated scope.**
- `test_paired_eval.py:230-303` drives the real `run_once` with a fake `popen`, fake lease guard, and mocked `verify_inputs`. Covered: success (`:277-283`), worker exit 7 as `failed_worker` (`:284-287`), 590-second work-deadline cancel with retained `-15` and cleanup present (`:289-295`), lease-guard cancel (`fail_lease_at=2`, `:296-299`), and publication failure (`fail_lease_at=4`, `:300-303`).
- Low gap: `test_paired_eval.py:271` passes `protocol_path=Path("protocol-proposed.json")`, a cwd-relative path. The suite passes only when run from the prepare directory. Harmless for the parent's run, but run it from that directory and state so.

## Findings

### R1 (medium, settle before launch): control device parity not established

- `worker.py:454-456` runs every arm, including both argmax controls, on `mps`.
- Frozen `dev_eval.evaluate` defaults to `device="cpu"` (`dev_eval.py:110`, `:116`).
- I could not confirm from the artifacts I inspected which device produced `D2-gradient-alignment-20261025-r2/development-000180.jsonl` and `D2-continuation-20261025-r2/development-000252.jsonl`.
- Impact: if those rows came from CPU, MPS argmax can flip a near-tie action on some step. The whole-row control comparison (`worker.py:364-365`, `paired_eval.py:55-60`) would then abort before any sampled arm. The one-shot launch is spent with no retry.
- Settle: read the invocation or log that generated the two dev files. If they were MPS, close R1. If CPU, the parent must choose and re-review a device before launch.

### R2 (medium, measure or narrow before launch): per-env-step lease re-read against the 590 s work cap

- `worker.py:339-341` calls `check_guard()` before every env step. `guard()` (`worker.py:468-470`) calls `_lease_check`, which runs `load_json(state.json)`.
- Measured here without games: `state.json` is 302,111 bytes. One read plus `json.loads` takes about 0.63 ms.
- Estimate: decision steps are about 29.7k for the best180 argmax arm and 25.7k for the latest252 argmax arm. Sampled arms are unmeasured. If the sampled arms are similar in length, about 221k steps total, so about 140 s of the 590 s hard work cap goes to re-reading state.
- Impact: this is not a failure by itself. Combined with per-step PyO3 env calls, per-logit CPU copies, and the no-retry policy, the 590 s cap is unmeasured for the full campaign.
- Settle: one dry timing of the harness without games, or call the guard once per batch iteration, which already has a guard at `worker.py:322-323`. Any change alters the harness hash and requires re-review.

### R3 (low): resource-monitor partial-line race can cancel a healthy run

- `supervisor.py:38-42` `latest_resource_sample` parses the last line of `resources.jsonl`. `supervisor.py:183` calls it inside the 0.25 s loop.
- The worker writes with `stream.write(json + "\n")` and then `flush` and `fsync` (`worker.py:406-409`). A read that lands mid-write yields a trailing partial line. `json.loads` raises, and `supervisor.py:190-194` converts that into `resource_monitor_failure`, which cancels the owned child.
- Likelihood is low because lines are small. Consequence is fail-closed but spends the one-shot. A minimal fix is to ignore an unterminated final line.

## Checked, no material defect

- **Argmax controls.** Both run first (`paired_eval.py:63-71`, `worker.py:472-483`). The compare sorts by seed and checks the full canonical key set. Both committed control files have exactly the 12 `CANONICAL_ROW_KEYS`, 64 rows, seed set equal to `SEEDS`, and `episode_index == SEEDS.index(seed)`. The comparison will not fail on schema or ordering alone.
- **Per-step validation** (`worker.py:270-278`) matches frozen `dev_eval.evaluate` lines 145-149: `terminated and truncated` exclusion, `bootstrap == not terminated`, score identity, and objective identity at abs tolerance 1e-9.
- **Sampler.** `UniformStream` is keyed by version, replicate, and game seed only (`paired_eval.py:86-101`). One draw per env step. Common across checkpoints. `inverse_cdf` uses normalized float64 with strict `<` at CDF edges. The unit test covers exact boundaries and underflow.
- **Statistics.** Bootstrap uses 10000 draws, seed 764002, 64 seed clusters, and one index matrix reused across contrasts. C4 is the primary contrast (`paired_eval.py:225-254`). Decision rules match the contract. `allow_nan=False` on serialization.
- **Checkpoint and receipt binding.** `worker.py:132-242` checks SHA pins, the terminal receipt, the v3 identity hash, and the D2 config. `load_state_dict(strict=True)` and no-grad are asserted. The two-test file covers both pinned checkpoints.
- **Module origins** (`worker.py:245-267`), assessed under a clean launch. With `env -i`, `PYTHONPATH` set to the frozen runtime, and `python/.venv/bin/python -B`, `numpy` and `torch` import from `python/.venv/lib/python3.12/site-packages`. `sys.path` contains no user-site entry. The frozen runtime precedes a repo `python/` entry on `sys.path`. The byte pins in `verify_inputs` bind those files. Versions are recorded and not compared to registered strings. The origin check derives site-packages from NumPy rather than the registered path. Under the supervisor's clean environment this has no material current-use impact.
- **Lease contract.** `_lease_check` (`worker.py:369-388`) matches `protocol.lease_contract.active_inference_diagnostic` on kind, authorization, run_id, protocol, harness, and manifest hashes. Required review fields are checked for 64-hex format only. The parent must bind `review_receipt_sha256` and `parent_reconciliation_sha256` to real documents. That is a parent duty, not a harness defect.
- **Live state.** `learning/runs/v2-orchestration/state.json` has `active_inference_diagnostic: null` and `active_long_campaign: null`. Nothing has been launched.

## Readiness scope

- Closed in code: F1, F2, F3 (within the stated scope).
- Open before launch: R1 (device parity of the control files), and the parent's own live-to-death test.
- Recommended, not blocking: R2 timing or narrowing; R3 partial-line handling.
- Not reviewed: scientific plan, statistics beyond the code paths above, and Rust behavior beyond the Python-visible fields in `python.rs`.
