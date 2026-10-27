# Review: frozen post-restore LR hook (resume-lr-ablation-prepare-luna-20261026-r1)

Scope: read-only review of the preparation hook, tests, design, and integration patch. CPU only. No environments, training, optimizer steps, MPS, or writes outside this directory. Live `state.json` changed during the review (current sha256 `0a35ccc2…943cd`, differs from the sha256 recorded in the parent policy inputs `ee58c19f…abfaa`); this review does not depend on that file's contents beyond the authority fields noted below.

## Verdict

The hook itself holds on the points in scope: validation precedes mutation, rollback is structurally unreachable for valid finite positive inputs, and only `optimizer.param_groups[*].lr` is written. The findings are in the integration patch, the test claims, and the design text. None is a current-use defect in the hook. Findings 1 and 2 must be fixed before the patch is used in a real arm.

## Findings

### 1. Pre-update LR assertion is missing from the integration patch (moderate)

`integration.patch`, hunk "after each PPO update, before metrics/checkpoint publication". The only per-update LR check runs after `optimizer.step()`. The design (`design.md`, "Reassert effective LR at restore and before each update") and the brief require a check before the first update.

- Failure: an `Adam.load_state_dict` between `apply_resume_lr_override` and the first update resets group LR to `0.0003`. The first update then steps at `0.0003`. The post-update check detects the drift only after that step has already used the wrong LR and trained the parent-LR update.
- Fix: add `assert_effective_lr(optimizer, expected_lr=reg["ppo"]["learning_rate"])` immediately before each update call, not only after it.

### 2. `without_group_lr` is undefined (moderate)

`integration.patch` calls `without_group_lr(optimizer.state_dict())` twice. The frozen runner `learning/runs/v2/D2-best180-branch-prepare-luna-20261026-r1/runner.py` defines `fingerprint` at line 375 and has no `without_group_lr`. The helper exists only in the test file (`optimizer_without_lr`). The patch fails with `NameError` at the transition point. It fails closed, but the patch is not runnable as written.

- Fix: define the helper in the adapter, or import it from one shared module. Do not duplicate it with a different scope.

### 3. Registration check runs after the LR mutation (low)

`integration.patch` calls `apply_resume_lr_override(...)` before `need(reg["arm_transition"] == {...})`. A mismatched registration therefore mutates the optimizer LR and only then raises. The hook's own validation is pre-mutation. The integration validation should be too.

- Fix: move the `reg["arm_transition"]` check above the `apply_resume_lr_override` call.

### 4. Explicit parent-to-arm identity transition is not implemented in code (moderate, future use)

The patch checks only the `arm_transition` dict and the optimizer fingerprints. The following are not enforced anywhere in code:

- The arm config differs from the parent config only at `ppo.learning_rate` (`0.0003` to `0.0001`) plus arm identity. The frozen runner still pins `CONFIG_SHA = 2d8eb5626d0debdf5416d0b89610d78ddd56011c3238a82fec72efabe1bd7fe3` (line 28) and checks `reg["config_sha256"] == CONFIG_SHA` (line 138). A config-only change cannot pass today, as the integration constraints already say, but no validator exists yet to replace that check.
- `lr-transition.json` records parent checkpoint and receipt SHA, but not the parent config SHA and not the arm config SHA. The brief requires the parent config identity to stay immutable and separate from the new arm config.

- Fix: add a declared validator that allows exactly the LR field and arm id/config digest, and requires parent config SHA to be recorded as archived provenance. Make this a required gate before any arm registration.

### 5. Integration patch is a sketch, not an applicable diff (low)

The hunk headers are prose comments (`@@ after exact parent …`) with no line numbers. The paths `frozen-training-adapter/runner.py` and `future-registered-arm/runner.py` are placeholders, not the real `learning/runs/v2/D2-best180-branch-prepare-luna-20261026-r1/runner.py`. `git apply --check` cannot run against the real file. The anchor itself is correct: the equality assertion is at runner.py line 596, and `optimizer` is built at line 584, before any environment construction.

- Fix: label the file as a sketch, or regenerate it as a real unified diff against the frozen runner with correct hunk headers.

### 6. Test names and claims overstate the RNG coverage (low to moderate)

`test_real_accepted_best180_restore_on_cpu_then_override_only_lr` calls `model.load_state_dict` and `optimizer.load_state_dict` directly. It does not call `ckpt.restore_learner`, which is the production path. It exercises no RNG restore. Its check `torch.equal(torch.get_rng_state(), restored_rng)` is trivially true, since the hook never touches RNG. The attempt-1 failure (`attempt-1-failure.log`) shows that the production restore rejects CPU restoration of the MPS sampling backend, as designed.

- Scope the claim to: exact model and Adam tensors loaded on CPU, and the hook leaves CPU RNG unchanged. Do not describe it as restore coverage. Restore coverage is the separate MPS evidence the design cites.

### 7. Rollback branch is untested and effectively dead (low)

`apply_resume_lr_override` rolls back LR inside `except BaseException`. For finite positive `config_lr` equal to `1e-4`, `assert_effective_lr` cannot fail after the loop, so the rollback never runs. No test covers it. This is harmless, but it is not evidence of atomic rollback. Atomicity rests on the pre-mutation checks, which the tests cover.

- Also: `math.isfinite` on a non-numeric `config_lr` raises `TypeError`, not `ValueError`. The rejection still happens before mutation.

### 8. Fingerprint outputs are incomplete against the design (low)

`design.md` says to retain and report both full optimizer fingerprints and the exact LR delta. The patch records only `parent_optimizer_fingerprint_excluding_lr` and `effective_optimizer_fingerprint_excluding_lr`, plus `parent_lr` and `effective_lr`. It does not record full before and after fingerprints. The test's full-state comparison excludes LR only, which is the correct scope.

### 9. Design overstates the power limit (medium, documentation)

`design.md` states that one seed per arm "cannot resolve effects below roughly 620 frames" as a fact. Per the brief, the parent ranking reconciliation qualifies this as an illustrative fixed-cohort approximation, not a training-replicate power proof. I did not open the reconciliation file, so I cannot quote its exact wording. Rewrite the sentence to match that qualification and drop the absolute claim.

## Checked and holding

- Atomic rejection: `config_lr != ARM_LR` and any non-`0.0003` group LR both raise before the first write. `test_parent_group_mismatch_rejected_before_any_group_mutation` and the `2e-4` rejection assertion cover the non-mutation claim.
- Mutation scope: the hook writes only `group["lr"]`. The test removes only `lr` from `param_groups` before fingerprinting, so model, moments, step counters, and other group fields are compared as exact.
- Overwrite detection: `test_load_state_dict_after_override_resets_lr_and_is_detected` shows `load_state_dict` restores `0.0003` and `assert_effective_lr` detects it. Finding 1 is about where that check runs, not whether it works.
- Hashes: the receipt and source hashes in the brief match the files on disk (see `receipt.json`).
- Parent identity: the patch preserves `PARENT_SHA` and `PARENT_RECEIPT_SHA` checks (runner.py lines 22 and 24). The policy names update 180 as incumbent. The review does not select a parent.
- Not inspected: the post-update drift check placement inside the update loop, `save`, `emit`, and the ranking reconciliation file. No MPS, training, or environment runs were executed for this review. Test results are the parent's independent four-pass CPU run and were not re-run here, per the read-only brief.

No automatic arm or parent selection is implied by these findings. The control may change the incumbent only after its terminal audit.
