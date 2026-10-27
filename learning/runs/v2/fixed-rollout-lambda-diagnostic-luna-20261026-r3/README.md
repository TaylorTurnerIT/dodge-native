# Fixed-rollout lambda diagnostic R3

CPU-only descriptive analyzer for an already-collected immutable rollout. No capture, actual rollout, checkpoint, environment, optimizer, or training access. `controls.py` preserves R1 synthetic checks; `controls_r3.py` adds direct production moment parity, hand boundary cases, NPZ reader-to-analyzer validation, exact-constant EV, and observed-return coverage checks.

Both controls ran with `python/.venv/bin/python -B`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH` unset, an owned empty `PYTHONPYCACHEPREFIX`, and CPU thread limits of 2. See `CONTRACT.md` for the input and evidence limits.
