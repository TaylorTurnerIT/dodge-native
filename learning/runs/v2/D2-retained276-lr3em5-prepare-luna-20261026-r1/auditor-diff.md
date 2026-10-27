# Independent LR3e-5 audit tooling

- `audit_candidates.py` and `wrapper.py` live in this preparation directory. Auditor pins registration, runner, launcher, parent checkpoint/receipt, cost anchor, runtime, and six candidate boundaries. Wrapper pins auditor and exact observer directory/source.
- Candidate entry requires parent model/RNG equality, exact restored full Adam fingerprint, and Adam equality after excluding only `param_groups[*].lr`. Transition receipt proves 0.0001 to 0.00003 for every group, unchanged non-LR fields, and saved entry optimizer fingerprint.
- Full mode requires six published candidates and successful terminal receipts. Only `wrapper.full_mode(observer_dir=..., name=...)` exposes it. CLI refuses full mode. No audit was invoked.
- CPU tests read accepted original-276 checkpoint and evaluation only. Candidate boundary rows are synthetic fixtures. No game environment or optimizer step ran.
