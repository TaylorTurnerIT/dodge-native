# Collector failed-reset identity repair

Fix F1: assignments bind full episode seed identity. A returned reset that fails its guard/audit remains explicitly unassigned in the snapshot; no old ordinal or horizon is reused and snapshotting consumes no assignment.

41 synthetic CPU controls passed, including new successful-reset and changed-seed identity checks plus extended original failed-reset coverage. PPO, GAE, KL and scheduler source remain byte-identical. See `r1-to-r2.diff`, `source-manifest.json`, `receipt.json`, and `logs/parent-tests.log`.

Source preparation only; fresh review, native integration/parity, trusted restore, identity/evaluator, seed/resource/registration and launch gates remain pending. No native/MPS/checkpoint/study/training run occurred.
