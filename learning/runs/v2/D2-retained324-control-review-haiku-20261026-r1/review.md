# D2 retained324 control prep review (Haiku, static)

Scope: `learning/runs/v2/D2-retained324-continuation-prepare-luna-20261026-r1/` (fixed 3e-5 control, not scheduled treatment). Static read and sha256 only. No imports of prepared code, no tests, no validate.py run, no MPS, training, lease, ledger, or state access, no source edits. Research notes were not read. This review carries no launch-qualification or acceptance authority.

Full hashes and provenance: `receipt.json`. Structured findings: `review.json`.

## Verdict

Static integrity passes. Registration `8a9c29cd...` matches. All 13827 pins exist and their recomputed sha256 matches. The runtime member digest `2cf10e9f...` recomputes. Critical parent, receipt, cost, audit, decision, evaluation, producing-run, config, native, interpreter, policy, and source pins are all present and match. The pin delta against predecessor r5 is 15 removed and 15 added, with no hash rewrites on retained paths. The count stays at 13827.

One finding is recommended before launch. The rest are low.

## Findings

1. **Medium: stale `parent_run_id`.** `runner.py:738` hardcodes `"D2-retained276-lr3em5-20261026-r2"` in every new candidate checkpoint state. No validator reads this field, so no gate fails. Correct lineage is still carried by `parent_checkpoint_sha256` and `parent_registration_sha256`. The fix changes the runner sha and the registration sha, so it requires a re-freeze. It is cheap now and impossible after outputs are produced. Repair before launch, or record that the label is stale and unvalidated.
2. **Low: `execute_once.py:297` `mkdir(exist_ok=True)`.** Launch proceeds into a pre-existing output directory. Add an explicit absence check in preflight.
3. **Low: launch environment not recorded.** Preflight requires `PYTHONPYCACHEPREFIX=<empty-pycache>` and `-B` (`runner.py:124`). A launch without them fails closed before any write, but wastes an attempt. Record the exact command in the runbook.
4. **Low: `forbidden_outputs` not enforced.** `lr-transition.json` is declared but never checked. Nothing currently writes it.

## Notes (not findings)

- `runner.py:208` and `parent_adapter.py:34` pass the constant cost-receipt sha into `validate_cost_anchor`. The file-hash binding still holds through `runner.py:206-207` and `runner.py:363-370`.
- Stale "phase-300" wording in `runner.py:625,629` and `execute_once.py:235` is cosmetic.
- `validate.py` mocks only `check_lease`. Its negative checks exercise only receipt fields, not `validate_parent_terminal_receipt`. The live lease path is not qualified here.
- The worker body changed only by constants and the `parent_run_id` literal. Runtime API names it calls exist in the pinned runtime source. Call-signature correctness rests on the predecessor's live runs, since `validate.py` does not run the worker body.

## Checked and passing

- Import origins are checked (`runner.py:314-329, 634-647`, `execute_once.py:320`).
- The output directory, marker, and cancel path are absent. The import cache is empty.
- The real execute preflight is reached before the first mutation (`validate.py` intercepts the output `mkdir`).
- Same LR 3e-5 is enforced on restore.
- Endpoint 360, local 60, and cumulative 408 are rejected.
- The full audit covers `[300,312,324,336,348,360]`. The decision marks endpoint 360 as not selected. The parent audit status is `accepted_completed_iteration_and_selected_intermediate324`.
