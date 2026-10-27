# Candidate diff summary

- New candidate only: `D2-gradient-capsule-finalize-luna-20261025-r3/`.
- Runtime copied unchanged from `gradient-alignment-prepare-luna-20261025-r3/own/runtime`; expected PPO and `gradient_alignment.py` hashes preserved.
- Four support documents copied unchanged from `critic-diagnostic-parent-prepare-20261025-r1/docs`.
- Runner, launcher, and tests copied from `D2-gradient-capsule-repair-luna-20261025-r2/successor-r2`.
- Test-only fixture correction: workspace root discovered by `docs/SPEC_PRIVILEGED_VIT_RL.md` instead of fixed `parents[4]`.
- Added preparation-only smoke comparator, authority-key audit, and lease-mocked preflight entry point.
- Registration paths and pin keys are absolute; runtime manifest recomputed from resolved runtime members.
- No training, evaluation, environment construction, optimizer step, lease/state/docs edit, commit, or message.
- Validation stopped after preflight reported `ValueError: Original interpreter/Torch/NumPy dependency pins missing`.
