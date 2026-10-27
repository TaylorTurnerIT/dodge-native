# Fixed-rollout lambda diagnostic R4

CPU-only descriptive analyzer for an already-collected immutable rollout. No capture, actual rollout, checkpoint, environment, optimizer, or training access. `controls.py` preserves earlier synthetic checks; `controls_r4.py` adds elementwise production parity, observed-return bucket values, strict variant rejection, hand boundary cases, NPZ reader-to-analyzer validation, and exact-constant and near-constant EV checks.

Controls run with `python/.venv/bin/python -B`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH` unset, an R4-owned `PYTHONPYCACHEPREFIX`, and CPU thread limits of 2. See `CONTRACT.md` for input and evidence limits.
