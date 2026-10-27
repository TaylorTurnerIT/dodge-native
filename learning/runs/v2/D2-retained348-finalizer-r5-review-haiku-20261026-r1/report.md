# D2-retained348 finalizer r5 review (Haiku 5.5, `claude-haiku-5-5`)

Scope: source-only review of `learning/runs/v2/D2-retained348-linear-finalizer-prepare-parent-20261026-r5/finalize_parent.py`, SHA-256 `d82ee2bbc62ac98e185c795774b046d4cfc470d0d9bce777bb102652eb0aef04` (matches `preparation-manifest.json`). Prior review: `D2-retained348-finalizer-r4-review-haiku-20261026-r1/report.md`.

Method: read `finalize_parent.py` in full; `diff` r4 vs r5; read-only `shasum`, `jq`, `grep`, `ls` over frozen evidence. No Python imported or run, no `.pt` loaded, no tests run, no lease or ledger write, no shared edits. Only this directory was written.

## Verdict: CLEAN. No blockers.

## Exact R4 → R5 delta (`diff`, verified)

1. `_load_selected_state` (`:312-314`): adds `identity_hash(selected["identity"]) == selected["identity_sha256"]` and `selected["run_seed"] == reg["run_seed"]`. Runs before the first write. `identity_hash(value) -> str` exists at `own/runtime/dodge_rl/identity.py:37`. This closes R4 N2.
2. LR check (`:335-337`): literal `2.2203389830508478e-05` replaced by exact equality with `runner.lr_schedule.learning_rate_for_cumulative_update(cumulative["updates"])`, plus all group LRs equal. `runner.lr_schedule` is loaded from the sha-pinned `PREP/lr_schedule.py` (`runner.py:34-44`). `learning_rate_for_cumulative_update` is defined at `PREP/lr_schedule.py:43`. `validate_saved_schedule_lr` (`runner.py:179`) already asserts the same value, so the new line is redundant but consistent.
3. Pre-write block (`:432-469`), before `_write("finalizer-assembly.json")` at `:489`:
   - `json.dumps` of the 13 selected receipt keys (`:437`).
   - Six certificate reads with hash pin, `selected_performance`, and aggregate match against `full-audit.json` (`:439-447`).
   - Incumbent certificate hash and `performance` fields (`:448-451`).
   - `candidate_comparison` and six report rows (`:452-469`). Both were previously computed after `audit.json` (R4 B1).
4. Schedule: `"specification": schedule_spec` replaces a second parse (`:582`). Equality `schedule_spec == read_json_from_bytes(schedule_bytes)` is still checked (`:430-431`).

R4 B1 is closed. Every parse or read that can raise on the frozen inputs now runs before the first write. Verified by reading `:437-469` against the post-write code at `:489-734`.

## Post-write accesses checked on disk (frozen inputs)

Read-only `jq`/`grep`/`shasum`, no imports:

- r5 files match `preparation-manifest.json`: `README.md` `41cdab91…`, `cpu-tests.log` `4acd7dbb…`, `test_finalizer_contract.py` `92341b72…`, `test_publication.py` `46e79f6a…`, `test_real_evidence.py` `bb1aba28…`. Parent preflight receipt `791ff994…` matches the manifest.
- `RUN/worker-result.json` has `counters`, `cumulative_counters`, `current_iteration_observed_outer_seconds`, `elapsed_seconds`, `cumulative_selected_checkpoint_trajectory_wall_seconds`, `status`, `first_failure`. All keys used post-write exist.
- `PREP/registration-final-r2.json` has `parent.registration_sha256`, `parent.latest_resource_cost_anchor`, `lr_schedule` (with `origin_cumulative_update` 372, `horizon_updates` 60, `spec_sha256` `7ceed85c…`), `run_seed` 4200000001, `runtime_root`, `native`, `pins`, `config_sha256`, `runtime_sha256`, `policy_sha256`.
- Ledger `learning/runs/v2-orchestration/state.json`: `postcritic_training_work` and `training_parent_selection_policy` are objects. `active_long_campaign` equals `reg.expected_lease` exactly. `active_inference_diagnostic`, `active_inference_campaign`, `active_inference_lease`, `cancel_requested` are null. Cancel file absent. No `NaN`/`Infinity` token in the ledger, so `json.dump(..., allow_nan=False)` at `:660`, `:715`, `:733` is safe.
- `full-audit.json` `.audit.candidates[*]` has `caps`, `certificate_sha256`, `checkpoint_sha256`, `competence_passed`, `component_fingerprints`, `deaths`, `mean_alive_frames`, `mean_score`, `performance`, `rows_sha256`, `sidecar_sha256`. All six candidates have `deaths` 64 and `caps` 0 in the file. Means: 324 `2939.40625`, 336 `2531.3125`, 348 `3098.125`, 360 `2535.140625`, 372 `2646.5625`, 384 `2270.59375`.
- No `NaN`/`Infinity` token in `RUN/*.json` or `PREP/*.json`.
- `PREP/lr_schedule.py` top level has one binding per constant (`:12-25`) and no rebinding. Its sha `ef81e875…` matches reg `lr_schedule_sha256` and `runner.py`'s pin. The auditor copy `1ac2a62d…` matches `AUDITOR_SOURCE_SHA`.
- No `runner.py`, `lr_schedule.py`, or `dodge_rl/checkpoints.py` shadowing in the runtime root (only `dodge_rl/` exists there).
- Parent output directory `D2-retained324-linear-parent-terminal-audit-20261026-r1/` contains only `review-reconciliation.json` (`4b4e51ed…`). The finalizer copy is not yet placed, which is the expected pre-invocation state (`validate_review_reconciliation` requires exactly these two files).

## Nonblocking

- NB1 (low, generic). Pre-write precheck `json.dumps` (`:437`) omits `sort_keys=True`, which `_write` uses. A dict with mixed key types passes the precheck and then fails `_write`, after `finalizer-assembly.json` (and possibly `audit.json`) exists. Not reachable on the frozen evidence. The torch `.pt` dict keys were not inspected. Fix: serialize with the same options as `_write` before the first write.
- NB2 (low, generic). Payloads not in the precheck list (`performance`, `group_lrs`, `fingerprints`, `sidecar_data`, `schedule_spec`, `candidate_comparison`) are JSON-checked only after the first write. Non-JSON types would fail after partial output. Reachable only if torch-loaded values are not JSON types. `group_lrs` are Python floats from `apply_next_update_lr` (`_finite_number`); fingerprints are digests; no `NaN` in JSON evidence. Fix: serialize every payload to bytes before the first `_write`.
- NB3 (carry from r4 N1, latent). `read_json_from_bytes` (`:741-770`) is unchanged. A top-level rebinding of a constant, `AugAssign`, `AnnAssign`, or a duplicate `SCHEDULE_SPEC` is not poisoned. Not reachable on the pinned helper: sha is checked before parse (`:427-428`), the auditor copy is checked at `:207-210`, and the top-level bindings are unique.
- NB4 (generic, late failure). Ledger `guard()` (`:655`), precommit process absence (`:656`), and the replace window between `:726` and `:727` run after `audit.json`, `completed-iteration-receipt.json`, `retained-best-candidate-receipt.json`, `retained-best-decision.json`, and `report.md` are written. A failure there leaves partial output with the lease still active. The `NamedTemporaryFile(delete=False)` at `:714` is not removed on exception. Not a frozen-input blocker. The brief promised no broader atomic publication guarantee.
- NB5 (test only). `test_finalizer_contract.py:59` hard-codes `/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79` as `ROOT`. Carry from r4 N4.
- NB6 (info). `sys.dont_write_bytecode = True` remains a global side effect on import. Import is otherwise inert.

## Not verified (limits)

- `.pt` contents not read. Checkpoint-internal values are verified only through the parent CPU preflight receipt (`791ff994…`), which was not rerun here.
- `identity_hash` signature checked by reading only, not executed.
- Test suite not rerun. `cpu-tests.log` (`4acd7dbb…`) is taken as reported.
- Cost sum `11955.970683418207` and trajectory values were not recomputed here; the constants at `:419-421` are carried from the parent.

## Recommended next step

No blocker. The parent may proceed under its own gate: copy the exact finalizer bytes, verify SHA `d82ee2bb…`, and invoke once. Optional before invoke: NB1 and NB2 hardening (serialize-before-first-write) would be a small change, but they are not needed for the frozen inputs. If the parent edits the source, re-run this review on the new SHA.
