# Review: resume LR transition integration (r2)

Scope: read-only review of `learning/runs/v2/resume-lr-integration-haiku-20261026-r2/` (receipt SHA `cc369bc84942d796f8516187ea623dadaf2e87c9f8cda37efc3cd1f6e660415a`). CPU only. No runs, registrations, or edits outside this review directory.

## Readiness scope

CPU-tested integration template and diff. Not registered, not launched. The arm is not chosen here. The template still carries old parent/run constants, which is known scope. The MPS sampling RNG restore is not exercised by the CPU tests. The 620-frame figure is illustrative only and carries no training-replicate power claim. No causal improvement claim follows from one new seed branch.

## Verdict

No blocking defect in the LR-only transition closure. Three findings. Findings 1 and 2 should be fixed before branch-specific registration drafting. Finding 3 is a labeling item.

## Findings

### 1. Sibling module imported before any pin check (medium)

- `arm-adapter.diff:7-9`: the runner imports `resume_lr_transition` at module top level.
- `arm-adapter.diff:58-60`: the `critical` pin set includes `runner_path`, `config_path`, `parent_config_path`, and others, but not the transition module.
- `execute_once.py:250` (frozen r5 capsule): the launcher runs `[interpreter, "-B", runner_path, ...]`. `-B` keeps the runner directory on `sys.path`, so the import resolves to whatever `resume_lr_transition.py` sits beside the runner.
- Impact: module code runs at process start, before `load_registration` verifies any pin. A swapped or drifted transition module executes unverified.
- Fix: add the module path to the registration, to `critical`, and to the pin binding. Ideally verify its sha before the import, or move the import under a verified loader.

### 2. Override evidence is weaker than written (low)

- `resume_lr_transition.py:181`: `before_excluding` is computed inside `transition_record`, after `apply_resume_lr_override` has already run. Both "before" and "after" views share the same live moment tensors, so the excluding-LR equality check compares the same tensors twice. It cannot detect a moment change in the override window. The override only writes `group["lr"]`, so the claim is likely true, but the record does not prove it.
- `resume_lr_transition.py:190`: `non_lr_fields_changed` is hard-coded to `[]`, not computed.
- `proposed-adapter/runner.py:611-618`: `parent_optimizer_state` is a `state_dict()` view sharing tensors with the live optimizer.
- Fix: digest the excluding-LR view (bytes) before the override call and store it. Compute `non_lr_fields_changed` from the comparison.
- `proposed-adapter/runner.py:662-663` vs. `:674-676`: `state["optimizer"]` is a CPU copy captured inside the dict literal. The publication assertion `assert_effective_lr(optimizer, ARM_LR)` checks the live optimizer, not the captured copy that is saved. Equal in practice because nothing mutates LR between them, but the assertion does not cover the bytes saved. Fix: also assert `state["optimizer"]["param_groups"]` lr values equal `ARM_LR`.

### 3. Archival `parent_checkpoint_sha256` is unlabeled in the config (low)

- `draft-arm-config-lr1e-4.json` and the parent `milestone3-D2-freeze-r1/D2-config.json` both carry `parent_checkpoint_sha256` = `ce9c03c8...`. Normalized diff of the two files: only `ppo.learning_rate` (0.0003 to 0.0001) differs. The one-variable config diff holds.
- The actual parent authority is `105e0f7a...` (external pin). A reader of the arm config alone gets the wrong parent checkpoint. Grep of the proposed runner found no read of the config field; authority is `PARENT_SHA`.
- Only label is the runner comment at `arm-adapter.diff:18`. Fix: record the field as archival in the arm registration (for example `archival_config_fields_not_authority`). Do not change config bytes.

## Verified closed

- Restore equality (`proposed-adapter/runner.py:607`) precedes the override (`:612`), which precedes environment construction.
- Parent Adam is built at `PPO` lr 0.0003 (`:596`), then `load_state_dict` restores it. `apply_resume_lr_override` requires per-group 0.0003 before writing 0.0001.
- `validate_arm_binding` and `validate_config_transition` run in `load_registration` before any optimizer exists (`arm-adapter.diff` hunk at 289-306).
- `guarded_update` asserts before and after every PPO update call (`arm-adapter.diff:114-120`).
- Only one `save_checkpoint` call site (`proposed-adapter/runner.py:675`); it has the publication assertion.
- `ppo.py` contains no `learning_rate` write. The only reference is the dataclass default and a validator. The update cannot reset LR.
- The launcher uses `-B`, not `-I`, so the sibling import is not suppressed by isolated mode.
- `arm-adapter.diff` applies cleanly to the frozen parent runner (`learning/runs/v2/D2-best180-branch-prepare-luna-20261026-r1/runner.py`, sha `8807b520...`). Patched output matches `proposed-adapter/runner.py` sha `70e04ca9...` exactly.
- `unit-tests.log` ends with `39 passed`, with 39 PASSED lines.
- `design.md:44-45` (RNG caveat) and `:50-52` (power note) are labeled accurately.

## Inspected inputs and outputs

See `review.json` and `receipt.json` in this directory for full SHA-256 lists.
