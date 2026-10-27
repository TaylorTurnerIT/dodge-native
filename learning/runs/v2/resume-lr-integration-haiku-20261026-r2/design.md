# Resume LR arm: integration design (r2)

Status: proposed adapter and shared transition module frozen, CPU-tested, and diffed against the frozen runner. Not registered. Not applied to live source. No arm launched, no parent chosen, no lease, state, docs, checkpoint, or game-weight write. The running unchanged best180 control is untouched.

## Files

| Path | Role |
| --- | --- |
| `proposed-adapter/resume_lr_transition.py` | Shared stdlib-only transition module: validators, `without_group_lr`, `fingerprint`, `apply_resume_lr_override`, `transition_record`, `guarded_update`. |
| `proposed-adapter/runner.py` | Proposed arm runner. Copy of the frozen runner with the edits in `arm-adapter.diff`. |
| `arm-adapter.diff` | Unified diff, `a/` and `b/` both `learning/runs/v2/D2-best180-branch-prepare-luna-20261026-r1/runner.py` (frozen path). Applies to a copy; the test does this in a temp directory. |
| `test_resume_lr_transition.py` | 39 CPU tests (`unit-tests.log`). |
| `record_cpu_transition.py`, `cpu-real-parent-transition-record.json` | Real accepted parent, model and Adam on CPU, transition record. |
| `draft-arm-config-lr1e-4.json` | Draft arm learner config: parent config with `ppo.learning_rate` 0.0001. Not registered. |

The frozen runner, `resume_lr_override.py` (r1 prototype), and the r1 review are not changed.

## Transition and identities

- Single declared transition: `PPO learning_rate 0.0003 -> 0.0001`, applied to `optimizer.param_groups[*]["lr"]` only (`DECLARED_TRANSITION`).
- Parent learner config file: `learning/runs/v2/milestone3-D2-freeze-r1/D2-config.json`, sha256 `2d8eb5626d0debdf5416d0b89610d78ddd56011c3238a82fec72efabe1bd7fe3`. This is the `config_path` of the accepted parent registration (sha256 `6f4adf808789655a663800a1e4a0613192d02b0c8287d121455ea748fe043916`). It is pinned as immutable archived provenance.
- Arm learner config file: separate path and sha256 (`reg["config_path"]`, `reg["config_sha256"]`). Draft value: `f858a63c324fc312f794c0423aa56db2daf60793b62990cd51fa400afe3af628`. The arm config may differ from the parent config only at `ppo.learning_rate`. The check is canonical JSON, so `64` vs `64.0` and `true` vs `1` are rejected.
- `config-devhelper-preflight.json` is evidence only and is not read as a learner config.
- Accepted parent: checkpoint sha256 `105e0f7a83e154116bd9f0d5eaaf573a896886468c9038f548f5ce7e6377c7ea` and terminal receipt sha256 `7968a62b6e601fab971e4145dbaebfa1995c8f696e6df442ab70fc0435b74903` (named in `validate_arm_binding`).
- `reg` has no top-level `ppo`. The adapter reads `config["ppo"]`.
- `ppo.py` only validates `PPOConfig.learning_rate` and does not read it during the update. Effective LR is therefore only the optimizer group LR.
- The parent config's own field `parent_checkpoint_sha256` is `ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f`, not the accepted 180 checkpoint. The arm config carries it unchanged. Accepted parent identity comes from the registration and receipt, not that field.

## Validation order (no write before all checks pass)

1. `load_registration` (before restore): schema, pins, `validate_arm_binding` (parent config file sha, arm config file sha, reg identities, parent checkpoint and receipt, `arm_transition == DECLARED_TRANSITION`), `validate_config_transition`, then the existing learner settings check with `ppo == PPO with learning_rate 0.0001`.
2. Worker restore: model, Adam, and RNG restore from the accepted parent, plus the existing exact-equality assertion (unchanged).
3. `apply_resume_lr_override`: re-checks declared transition, `config_lr == 0.0001` as a float, that every group is a float `0.0003`, then writes each group LR and verifies with `assert_effective_lr`.
4. `lr-transition.json`: `transition_record` writes full before and after fingerprints, excluding-LR before and after fingerprints, the exact per-group LR delta, and the file and identity fields. It fails if the full fingerprint did not change or if anything other than LR changed.
5. `load_state_dict` is not called after the hook. Enforced by an AST test.
6. Each PPO update is `guarded_update(optimizer, ARM_LR, ppo_update, ...)`, which asserts effective LR before and after the call. Checkpoint publication (`save_checkpoint`) asserts effective LR first.

If any check in step 1 or 3 fails, the optimizer state is unchanged (tested). The r1 rollback branch is removed: after validation the only writes are dict assignments, so atomicity comes from pre-write validation, not from rollback.

## Tests and scope

- `unit-tests.log`: 39 passed (final run).
- Failed or partial runs kept: `attempt-1-pytest.log` (3 failed before adapter edits: import, ordering, diff); `attempt-2-pytest.log` (2 failed: diff `b/` label and a quote mismatch in the test, both fixed); `attempt-3-pytest.log` (38 passed, before the import test was added); `attempt-4-pytest-key-rename.log` (1 failed: stale test key after renaming the `validate_arm_binding` return keys).
- Positive: real accepted parent loads on CPU through `ckpt.load_checkpoint` (hash-checked), `require_complete_update`, and the parent validator. Model state matches the checkpoint; Adam state matches the checkpoint excluding LR. The hook changes only LR. The CPU RNG state (Python, NumPy, Torch CPU), `model.training`, and grad mode are unchanged.
- Not exercised: the full MPS sampling RNG restore. The frozen loader rejects restoring the MPS RNG backend on CPU (`attempt-1-failure.log` in r1). This test does not bypass that check and does not count as restore coverage. Restore coverage comes from the frozen MPS evidence.
- Toy Adam steps populate moments only. No environment, no gradient, no game-weight optimizer step.
- Source integration without running the worker: undefined-name check with `symtable` (also catches the r1 `without_group_lr` defect, shown by a negative control); stdlib-only top-level imports; module imports cleanly; AST order checks (validation before override, override before update, assertion before publication, `guarded_update` wraps `ppo_update`, no reload after override, `lr-transition.json` written).
- Not executed: `load_registration` on a real arm registration. This needs live pins, runtime, and the MPS environment, and the arm registration is not made here.

## Power note (correction to r1 design)

The ~620-frame figure is an illustrative normal approximation from a fixed-checkpoint, paired-seed bootstrap over the same 64 development seeds (`D2-best180-branch-parent-reconciliation-20261026-r1/ranking-reconciliation.json`). It is not a power calculation and does not include training-replicate variance. It does not show that smaller effects, or effects across training replicates, cannot be resolved. No qualification claim follows.

## Remaining gates (before any arm registration or launch)

1. Current unchanged best180 control completes and is reconciled. The retained-best policy is rechecked then. This design does not choose the arm parent, and the historical 180 parent is not frozen by default.
2. A fresh arm registration is written by a reviewer, not here. It must assign new run id, output path, fresh run seed, lease, and new pins for the runner, `resume_lr_transition.py`, arm config, and parent config. It must also replace the branch-specific constants that are still in the adapter (`RUN_ID`, `expected_lease` authorization, `state_path`, `runtime_root`, native pins). The adapter uses `parent_config_path`, `config_path`, `parent_config_sha256`, `config_sha256`, `arm_transition`, and `schema = d2_resume_lr_arm_registration_v1`.
3. Registration preflight dry run (no lease, no training): `load_registration` on the real registration, pin audit, dependency inventory, and the 1800 s wall / 6 GiB RSS / 6 GiB MPS caps re-validated for the arm.
4. Independent review of `arm-adapter.diff`, `resume_lr_transition.py`, the test suite, the draft arm config, and the transition record.
5. MPS full restore is not repeated here; it stays as the existing frozen evidence for the parent.
6. `lr-transition.json` must be listed in the arm's expected outputs.
