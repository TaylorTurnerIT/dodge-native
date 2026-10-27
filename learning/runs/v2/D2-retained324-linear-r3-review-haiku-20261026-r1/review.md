# D2 retained324 linear r3 source review (Haiku, r1)

Scope: source-only read review of `learning/runs/v2/D2-retained324-linear-runner-luna-20261026-r3/`. No imports, tests, subprocesses, checkpoints, MPS, training, or edits to reviewed files. Hash and diff checks only.

## Verified

- Hashes match the brief: `runner.py` SHA-256 `1d56471f…80630`; `lr_schedule.py` SHA-256 `ef81e875…079`. `source-manifest.json` owned-output hashes match for `control.log`, `cpu-tests.log`, `frozen-manifest.json`, `runner.py`, `lr_schedule.py`, `registration-contract.md`, `runner.diff`, `test_runner_schedule.py`. No `__pycache__` or `.pyc` in r3.
- Helper delta vs r2: only `verify_frozen_manifest` filename, `schedule.py` → `lr_schedule.py` (r2 would have raised at runtime).
- Schedule math (`lr_schedule.py:43-50`): `u = cum − 372`, `u∈[1,59]` → `3e-5 − 2e-5·(u−1)/59`, `u≥60` → `1e-5`. Horizon is 60 updates, endpoints hit exactly.
- LR timing: stage at `runner.py:936` after rollout (`:926`), before PPO (`:940`). Update k uses `LR(u=k)`. Saved LR at cum `372+k` = `LR(k)`. Entry (cum 372) = `3e-5`. Cum 384 (local 12) and 432 (local 60) match `lr(12)` and `1e-5`.
- Commit order (`runner.py:946-962`): finite (`:943`), progress (`:946-950`), gradient (`:953`), EV (`:954-956`), effective LR (`:957`), schedule commit (`:958`), counters (`:965`). Commit uses pre-increment counters, consistent.
- Identity defined at `:843` before use in checkpoint state `:888`. Fixed.
- Metric row (`:970-973`) records cumulative, `lr_schedule`, and `optimizer_group_lrs` after commit; values equal the LR applied.
- Progress contract vs pinned `ppo.py` (`b3cef91b…eac5`, `ppo_update` at `:403-600`): `ppo_update` resets `state/in_update/optimizer_steps` at start and writes `state="complete", in_update=False, complete=True, optimizer_steps=<this update>` on success. `runner.py:946-949` expectations match exactly. `progress` is per-update, so the copy-then-commit pattern is correct.
- Gradient alignment vs pinned `gradient_alignment.py`: group names `layers.0`, `layers.1`, `embeddings_and_input_projections`, `final_norm` exist for `NUM_LAYERS=2` (`teacher.py:21`). Cosine/ratio identities match `runner.py:576-577`. Live clip identity matches `ppo.py:523` formula.
- Runtime API names used by the runner exist in the pinned runtime, except native `VecDodgeEnv.observations/episode_info/batch_info`, which were not verified (native `.so`).
- `validate_episode_journal` is used by the launcher (`execute_once.py`), not dead code.

## Known (confirmed present, not re-analysed)

- K1 Old adapter alias imports vs new `*_SHA256`.
- K2 `validate_parent` signature. The runner's 9-arg call (`runner.py:320-324`) matches the r1 adapter (`D2-retained324-continuation-prepare-luna-20261026-r1/parent_adapter.py:16-17`). Must be re-checked against the r4 adapter.
- K3 Launcher hardcoded LR: `execute_once.py:85` `assert_saved_optimizer_lr(state, 0.00003)` fails for every scheduled checkpoint (cum 384 and 432). Launcher `r.COMPLETED_CAMPAIGN_COST_BASELINE_SECONDS` is undefined in r3 (`runner.py` has `LATEST_*`/`PARENT_PRODUCING_*`).
- K4 `FINAL_SOURCE_DIR` contradicts external-builder rule: `runner.py:51`, `:281-285`, `:447-454` vs `registration-contract.md:3,12`.
- K5 Registration key mismatch: `runner.py:284` requires `registration_schema_path`; `:447-449` derives its own path.
- K6 Own helper pin `ef81…079` matches `runner.py:26`. Aligned.
- K7 `FROZEN_LAUNCHER_PATH` (`runner.py:52`) points to r2 continuation-prepare; launcher digest `7215ae…` matches `runner.py:50`.

## Independent findings

Severity order.

1. **medium** `runner.py:960` `checks_passed=True` literal. The commit gate is a tautology; safety depends only on statement order at `:946-958`. Trigger: any refactor that moves or drops a check. Consequence: schedule commits after failed PPO/diagnostic checks. Fix: compute the boolean from the checks, or drop the parameter. The source-order test (`test_runner_schedule.py:153-157`) does not catch a logic regression.

2. **medium** Launcher does not validate per-update schedule metadata. `execute_once.py` `validate_outputs` (~`:150-185`) never reads `lr_schedule`, `cumulative_updates`, or `optimizer_group_lrs` from `training-metrics.jsonl`. Contract line 22 requires metric binding. Trigger: runner emits wrong per-update LR or a non-advancing counter. Consequence: launcher accepts it. Fix: per row, assert `cumulative_updates == 372 + local`, `lr_schedule.completed_schedule_updates == local`, `optimizer_group_lrs == [LR(local)] * groups` (exact float equality).

3. **medium** Companion schema RUN_ID mismatch (corroborates K5). `runner.py:254-255` requires `registration_schema.RUN_ID == "D2-retained324-linear-lr-20261026-r1"`. The r1 companion (`…continuation-prepare-luna-20261026-r1/registration_schema.py:3-4`) has `RUN_ID = "D2-retained324-continuation-20261026-r1"` and `SCHEMA = "d2_retained324_same_lr_registration_v1"`. Any companion not rebuilt for the linear run fails at `validate_registration`. The test stub (`test_runner_schedule.py:25`) sets the linear ID and hides this. Note: r4 was not inspected.

4. **low-medium** Failed-update record is thin. `runner.py:995-998` records `update_progress` from committed `progress` (previous update), not the in-flight `progress_candidate`. It also omits the staged LR already written to the optimizer at `:936-938`, staged schedule, and cumulative counters. Trigger: PPO raises mid-update. Consequence: post-mortem cannot tell whether LR was already moved to `LR(k)` or how many optimizer steps ran. Fix: add `progress_candidate` copy, `staged_lr`, and `optimizer_group_lrs` to the failure result. Do not commit.

5. **low** Import-time bytecode. `runner.py:22-23` and `:43` import/exec `parent_adapter`, `registration_schema`, and `lr_schedule` before `check_import_cache` (`:505`). Without `-B` or `PYTHONPYCACHEPREFIX`, `__pycache__` lands in the r3 source dir, violating the "no pyc" control. Fix: check `sys.dont_write_bytecode` or the prefix at module top before the imports.

6. **low** Test overclaim (not runtime defect). `test_runner_schedule.py`:
   - `:105-125` "failed PPO never commits" never calls `worker`; it raises a local exception and asserts `committed` is unchanged. Tautological.
   - `:67-103` "actual runner full sixty" calls helpers only. It skips rollout, PPO, checkpoints, metrics, launcher. Uses a 2-group optimizer (`:46`) while the runner builds one Adam group (`runner.py:816`).
   - Stubs: `parent_adapter.CHECKPOINT_SHA="a"*64` (`:21`), `RECEIPT_SHA="b"*64` (`:22`), no `STATUS`, `COST_RECEIPT_SHA`, `validate_parent`, `validate_identity`.
   - Four passing unit tests are schedule helper evidence only. They are not integration evidence.

7. **info** `gradient_alignment.py` (measure_cpu_shadow metadata) labels `minibatch_count = len(actions)`, which is the sample count 512, not a number of minibatches. Runner check (`runner.py:559`) is consistent with that. Label only.

## Not verified

- Native `VecDodgeEnv.observations/episode_info/batch_info`.
- `checkpoints.restore_learner` LR restore behaviour (assumed `load_state_dict`).
- Whether PPO shadow `_model_output` argument names match `measure_cpu_shadow` (`gradient_alignment.py` uses explicit tuple of 4 names).
- r4 companions (mutable, excluded by brief).
- No tests or runtime executed (per brief).
