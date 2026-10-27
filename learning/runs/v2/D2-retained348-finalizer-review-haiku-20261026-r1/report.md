# D2-retained348 finalizer review (Haiku r1)

Scope: source-only review of `D2-retained348-linear-finalizer-prepare-luna-20261026-r1/finalize_parent.py` (SHA-256 `687130a45651c1e7a5d6f0988ac6a065b0b29bb4d0d1fa96b5bc1c82b5b808ab`, matches). Nothing imported, executed, or loaded. Frozen source not edited.

## Verdict: BLOCKER

### B1. NameError in `_validate_and_finalize` (crash after partial output)

- Defined at `finalize_parent.py:335`: `schedule_fields = schedule_field_mapping(...)` inside `_load_selected_state` (starts line 300).
- `_load_selected_state` returns at line 336: `return selected, runner, fingerprints, lr, group_lrs`. `schedule_fields` is not returned.
- Caller at line 404 unpacks only those five values. No other binding of `schedule_fields` exists in the module (grep: only lines 335 and 540).
- Used at line 540, inside the `retained-best-candidate-receipt` dict literal in `_validate_and_finalize`, where it is undefined → `NameError`.

Trigger: any explicit parent invocation that passes the guards and reaches line 540 (i.e., every successful-path run).

Consequence:
- Already written before the crash: `finalizer-assembly.json` (438), `audit.json` (464), `completed-iteration-receipt.json` (494).
- Not written: `retained-best-candidate-receipt.json` (569), `retained-best-decision.json`, `report.md`, state snapshots, output manifest.
- Ledger not replaced; lease not cleared. Good for safety, but the run is left half-accepted in the output directory. Per the README, the parent must not rerun after partial output (the `"x"`-mode writes would also refuse). Recovery requires a new reviewed preparation.
- The 7 CPU controls pass because none exercise `_validate_and_finalize` or `_load_selected_state`. `cpu-tests.log` therefore does not cover this path.

Fix direction (not applied, per instruction): return `schedule_fields` from `_load_selected_state` and unpack it at line 404, or recompute it in `_validate_and_finalize`. Add a test that drives the receipt-construction path with a stub state.

## Non-blocking findings (verified by read, no execution)

- N1 (medium): `finalize_parent.py:690-698` `NamedTemporaryFile` defaults to mode 0600; `os.replace` installs that inode, so the ledger `state.json` mode may change from its original mode. Fix: `os.chmod` to the original `st_mode` before replace.
- N2 (medium): `finalize_parent.py:702-703` compare-then-`os.replace` has a TOCTOU window. A concurrent writer (DeepSeek/eval task) between the final `validate_snapshot_unchanged` and `os.replace` loses its update. No lock is taken. Acceptable only if the orchestrator guarantees no other writer; otherwise add a lock file.
- N3 (low-medium): the script does not pin its own SHA. `source_sha` is only recorded (421). A modified copy is accepted. Add `FINALIZER_SHA256 = "687130…"` and check it at top of `_validate_and_finalize`.
- N4 (low): several receipt fields are literal `True`/counts rather than computed in the same run (e.g., `checkpoint_metadata_unchanged` 511, 476; `owned_groups_absent` 453, 636; `source_pins_unchanged: 13857` 442; `latest_completed_cumulative_updates=432` 656). Supporting checks run earlier, so these are usually backed, but they are assertions, not derived values.
- N5 (low): `report.md` line 577 hardcodes `5.399687436876066%`; `decision` computes its own value. Currently consistent (checked: 3098.125/2939.40625 − 1 ≈ 5.39969%). Derive it from the variables instead.
- N6 (low): `receipt` naming: `parent_checkpoint_sha256` = producing parent (`c10d…`) while `continuation_parent_checkpoint_sha256` = selected (`b952…`). Correct as written, but the bare name is easy to misread. Consider renaming to `producing_parent_checkpoint_sha256`.
- N7 (low): `float` equality checks on hardcoded literals (416-419, 333) are brittle but deterministic for the frozen inputs.
- N8 (low): a crash after line 691 leaves a `.retained348-linear-finalize-*` temp file in the ledger directory, outside OWN.
- N9 (info): `test_finalizer_contract.py:59` hardcodes `/Users/taylor/...` ROOT; non-portable but harmless here.

## Verified (read-only, matching frozen expectations)

- Hashes match: `finalize_parent.py` 687130…, `test_finalizer_contract.py` e8ed4b…, `preparation-manifest.json` 351126… (its file-table values for the other four files match), `README.md` 04a3aa…, `cpu-tests.log` bcaab1…. Pinned-file check of `registration-final-r2.json` 0a6bf9…, `review-reconciliation.json` 4b4e51…, `report.md` (Haiku review) 7bd06e…, `full-audit.json` e1c32e…, `audit-binding.json` a8ad01…, `full-audit-parent-receipt.json` ffe709…, `frozen-manifest.json` ec01c4…, `output-manifest.json` a3eab6…, `reviewed-assembly.json` bd70d9…, all six auditor source SHAs, `observation.json` e234a1…, `observe.py` f271b2…, `instantiation.json` 56d547…, PREP `lr_schedule.py` ef81e8…, `runner.py` e80fba…, incumbent `checkpoint-000324` c10d90…, `retained-best` receipt 76cb15…, selected `checkpoint-000348` b95228…, `development-000348.json` f0da17…, `development-000348.jsonl` d6e914…, sidecar efec8e…, `execution-result.json` 7dad18…, `worker-result.json` 65994b…, `artifact-manifest.json` f2dda4….
- Candidate means: 324=2939.40625, 336=2531.3125, 348=3098.125, 360=2535.140625, 372=2646.5625, 384=2270.59375. Selection = 348 is correct; 384 not selected.
- Selected 348: Q1 867.0625, Q4 6003.875, deaths normal 25 / static 15 / kamikaze 15 / moving 9 / explosion 0 (sum 64). Matches script.
- Cost: 10824.835578584221 + 1131.1351048339857 = 11955.970683418207 (script's expected). Trajectory literal 5678.9823631240915 matches worker `parent_selected_checkpoint_reported_trajectory_wall_seconds`; endpoint 6806.37175508199 matches worker.
- Observer: `launch_count` 1, raw exits 0/0, outer wall 1131.135…, max RSS 2259222528 (< 6 GiB limit), absent flags true.
- Registration: 32 expected outputs, lease `D2_gradient_alignment` / run `D2-retained324-linear-lr-20261026-r1`, 13857 pins, `lr_schedule_sha256` ef81e8…, `config_sha256` 1c24df…

Limits: did not load the checkpoint (binary, forbidden), did not evaluate the ledger contents, did not verify `dodge_rl` runtime or `_native` sha beyond registration fields, did not verify the 13857 pins individually.

## Parent next steps (suggested)
1. Do not copy/run until B1 is fixed in a new reviewed preparation directory.
2. Address N1–N3 in the same repair.
3. Add a control that exercises `_validate_and_finalize` against a stub or a temp copy of the frozen inputs.
