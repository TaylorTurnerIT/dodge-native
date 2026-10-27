# D2 retained300 worker + registration static review (r5)

Scope: frozen `learning/runs/v2/D2-retained300-continuation-freeze-20261026-r5/` worker (`runner.py`), registration compatibility (`registration.json`, `registration_schema.py`, `parent_adapter.py`), against immutable `D2-retained276-lr3em5-prepare-luna-20261026-r2/runner.py` (913 lines). Static reads and hashes only. No imports, decoding, tests, runtime, MPS, training, ledger, lease, or source edits. Launcher reviewed only at interface level.

## Verdict

No blocker found in the worker or registration. No changed-correctness blocker. Notes below are low / inherited.

## Hash verification

| File | SHA-256 | Match |
|---|---|---|
| runner.py (frozen) | 108ba55ad78aa26166acb14f67cc6466da6293ccee3d272e1fe6e775ebf2ac60 | yes |
| execute_once.py | 7215ae6628c364fe74bafba68e66cb1c688000a3b7d648dba9248fc2d812310e | yes |
| parent_adapter.py | a969f2a5e6af35609f0b2cc9fb4a2f4cd1b369743a1d1cb7ba6c345355a6f2f6 | yes |
| registration_schema.py | eae76ec910b232b2cf6accbb6107a35b8cfedb5db162a6328e02bcee3367c088 | yes |
| registration.json | 8a60dc80f1ebe03c43bf18eebf75199e14f207b677570ac2d6d4368ddfcb0f79 | yes |

Registration pins: 13827 entries. Pins for runner, launcher, parent_adapter, registration_schema, config, native (new and old), parent checkpoint and receipt, parent evidence files, cost anchor, policy, gate, dependency inventory, and capsule support files all present with matching digests. Runtime continuity member map present.

## Worker changes vs immutable 276 runner

Verified in source, all correct as described:

- Restore: selected300 checkpoint loaded with exact expected SHA, `validate_parent_checkpoint_for_restore` derives metadata and cost paths from pinned receipt. Model, Adam, RNG restored with `restore_learner`. Fingerprints compared to saved values before any env or gradient work (`entry-restoration.json`, line ~715). Saved optimizer LR is 3e-5 and matches `LEARNING_RATE`; no LR override path remains (old `load_verified_transition` / `guarded_update` removed). `assert_effective_lr` checks 3e-5 before updates.
- Counters: `inherited` = parent cumulative 348 (checked against receipt candidate_cumulative 348 and local 24 = 324 + 24). New cumulative = 348 + 60 = 408 = `EXPECTED_TOTAL`.
- Schedule: `evaluate_at(300)` before training, then 312, 324, 336, 348, 360 inside loop. Six evaluations total; 60 updates.
- Entry evaluation compared to producing run's source evaluation rows (`validate_entry_evaluation`).
- Progress: `progress=progress` passed to `ppo_update`; `progress["completed_updates"]` advanced per update.
- Clocks: new checkpoints use `_PARENT_CLOCKS` derived from selected receipt future baseline 5190.209660791156 and cost receipt after-value 8621.338345875141, plus current elapsed. Matches cost receipt semantics: "Later36 updates after selected300 add resource cost, not selected model/Adam/RNG/counter ancestry."
- Score gate: `progress_passed` result recorded only (`competence_passed` field). No stop/abort on score. No regression vs 276 runner.
- Deadline/cancel: `Guard` uses launcher monotonic start, work cap 1790, finalizing cap 1800, cancel path and lease checks, RSS/MPS caps. Signal handler latches cancel. Cleanup in `finally` writes `worker-result.json`.

Runtime APIs used (`collect_rollout`, `ppo_update`, `evaluate`, `episode_resume_state`, `save_checkpoint`, `load_checkpoint`, `require_complete_update`, `restore_learner`, `capture_rng`, `_cpu_copy`) present in frozen runtime with compatible signatures (static grep only, not executed).

## Registration compatibility

- `limits` equals runner `LIMITS` (9 keys, values match).
- `resource_estimate` values match runner constants (1502.556 observed, 7680 steps, 1727.94 scaled, 1750 planned, 1790 work cap, 1800 outer, 10 cleanup, no relaxation).
- `expected_outputs` (32 entries) matches runner-expected list; `lr-transition.json` absent and forbidden.
- `parent` block has aliases the runner reads: `completed_cost_receipt_path/sha256`, `decision_path/sha256`, `producing_worker_result_path/sha256`, `metadata_path`, `audit_path`, `full_audit_path`, source evaluation paths, registration path.
- Parent values match selected300 receipt: sha `e2c8fb...`, receipt `ccc73f...`, local 24, phase 300, registration `8e17e1...`, run `D2-retained276-lr3em5-20261026-r2`.
- Seed 4200000000 outside excluded ranges (max 3758097383).
- Config ppo block, device, batch, rollout, excluded ranges, budget 1800 match runner constants.
- Output path, run_id, schema match registration_schema. Output dir not yet created.
- Draft `registration-builder-output.json` lacks limits and aliases; correctly not the authority. Final `registration.json` is the authority.

Receipt field names verified against actual JSON: parent retained-best candidate receipt, completed-iteration cost receipt, audit, full audit, decision, source evaluation, metadata sidecar, producing worker-result. All keys used by runner and adapter exist with expected values.

## Findings

1. severity low. path `learning/runs/v2/D2-retained300-continuation-freeze-20261026-r5/runner.py` line ~155. trigger: `planned_seconds` (1750) is only checked as a constant; `Guard` enforces only `work_seconds` 1790 and `total_seconds` 1800. consequence: planned allowance is not a runtime cap. Inherited design choice; hard caps still bound the run. Not changed.

2. severity low. path `runner.py` `validate_runtime_continuity` lines ~314-322. trigger: `old_root` and `new_root` are both the same runtime directory, so the old-vs-new file comparison is self-referential. consequence: the real binding is `member_sha256` vs current bytes, which is correct; the "old vs new" wording is misleading. Not a correctness failure.

3. severity low / by design. path `runner.py` lines ~769-773 and `parent_adapter.py` lines ~84-94. trigger: saved selected300 campaign clock is 7118.78 + 430.15 (adapter-verified), while new checkpoints start from 8621.34 (after-cost including discarded 36-update branch). consequence: campaign clock jumps at continuation start. This matches the cost receipt definition (campaign cost includes discarded branch; trajectory uses selected lineage). Intentional, not a bug.

4. severity low / naming. path `runner.py` line ~720 and new checkpoint field `inherited_counters`. trigger: new `inherited_counters` = 348 (parent cumulative), whereas the r2 receipt's `inherited_counters` = 324. consequence: field meaning shifts between checkpoint generations. Future continuation readers must not assume receipt semantics. Document only.

5. severity low. path `runner.py` line ~784-786. trigger: entry evaluation requires exact row equality with producing run's source evaluation. consequence: any nondeterminism in deterministic evaluation fails the run before training. Inherited from the 276 design; not a regression.

Launcher reviewer F2 ("entry lacks binding") is inaccurate per parent reconciliation: entry evaluation at line ~801 uses the same `evaluate_at` path that enforces the 300 binding. Not re-verified in launcher; interface-level only.

## Limitations

- Static only. No Python import, no checkpoint decode, no tests, no runtime, no MPS, no training. Behaviour of ppo/evaluate/restore is not exercised.
- Did not hash-check each of the 13827 pins (parent validation did that with real `load_registration`).
- Did not inspect `launcher-builder-review-reconciliation.json` or the observer instantiation diff.
- Live lease, MPS restore, and actual worker startup remain untested (as stated by parent).
- Not a launch qualification.
