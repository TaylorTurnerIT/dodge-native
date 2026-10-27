# Progressive1000 assembly source review

**Result: one P1 blocking regression.** Reviewed only the active assembly at the supplied pins. No repair or execution performed.

## P1 — Class authentication rejects the unchanged teacher's static methods

- **Location:** [runtime_adapter.py:51](/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/progressive1000-shared-runtime-assembly-sol-20261026-r1/runtime_adapter.py:51), lines 51–56; invoked unconditionally at line 89. The unchanged teacher defines `@staticmethod` members at [teacher.py:105](/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/progressive1000-shared-runtime-assembly-sol-20261026-r1/runtime/dodge_rl/models/teacher.py:105) and line 112.
- **Trigger:** Any later approved run reaches `RuntimeAdapter.__init__` with the correctly loaded, hash-matching `OmniscientEntityTeacher` class.
- **Cause:** The successor changed `getattr(loaded, method)` to `inspect.getattr_static(loaded, method)`. Static lookup returns the `staticmethod` descriptor. Only `property` is unwrapped, so `inspect.isfunction(function)` is false for `_initialize_head` and `_validate_inputs`. The first rejection is `runtime class method differs: OmniscientEntityTeacher._initialize_head`.
- **Consequence:** Both arms fail before bootstrap, checkpoint load, durable R5 attempt claim, or accepted-state restore. The worker has already created its output directory, and entry requires the parent's spent launch marker. This consumes the registered launch without collecting an update. Passing fake CPU controls cannot establish this constructor path.
- **Narrow correction:** Authenticate the descriptor kind, unwrap `staticmethod.__func__`, and retain origin, globals and code checks. Both unchanged static methods need this handling; no trainer, standalone restore probe or broader framework is needed.

## Other source checks

All 104 source-manifest members, 12 runtime members and 145 input pins match. The runtime member set is exact. All 11 declared changed-copy pairs and the regenerated exact-input patch match. Model/checkpoint/identity bytes retain their accepted pins. R5 still claims durably before its single accepted restore, verifies model/Adam/RNG and independent CPU/MPS digests, then applies constant `3e-5` LR.

The reviewed collector preserves the inherited buffers, GAE and PPO bodies except the pre-reset callback. Whole-batch seed prediction precedes reset construction; assignments remain frozen, scheduler advancement follows successful PPO, and final snapshots retain failed-update optimizer progress. The evaluator preserves the frozen row validator; its loop changes are explicit sampled Categorical actions and event hooks. Full1024 normal-start rows, fatal-frame exclusion, exact256-row quarters, conserved outcomes and seven fixed endpoints remain explicit. No active production import of `deferred/` was found; its test-only import creates no production requirement.

## Limits

Source reads, hashes, AST and JSON inspection only. The reported 81 passing author controls were not replayed; test source was inspected. No target import, Torch/NumPy/native/model/environment/MPS execution, checkpoint deserialization, build, repair, delegation, commit or push occurred. B/E expected-result and performance tables were not opened. Release parity, actual MPS restore/runtime qualification, resources, references, seed approval, registration and real preflight remain parent work, with no new prerequisite imposed. Preservation evidence covers the listed pins, not an entire-workspace snapshot. Exact hashes and checks are in `receipt.json`.
