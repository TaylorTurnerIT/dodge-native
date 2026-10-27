# Current pair resource calibration R4 preparation

CPU-only preparation for a fresh, distinct R4 proposal. No state or lease was written. No launch marker, probe, MPS operation, actual episode, game environment, training, or checkpoint write occurred.

R6's historical evaluator and checkpoints remain pinned: `best204` and `latest252` (historical 204/252 pair). The current accepted best is phase update 276. R4 measures resource reuse for the frozen R6 evaluator; it does not compare current 276 or run a 512-episode comparison.

R3 review blockers and parent guard-count reproduction are copied as retained evidence. R4 fixes interpreter selection, bytecode policy, MPS sample validity, repeated-pass guard math, active time bound, RSS race, identity-checked signaling, live authority fields, and bounded workload limits. R6's two historical `__pycache__` files and R3's false outside-write claim are recorded in `calibration-plan.json`; files remain untouched.

Run CPU controls with:

```sh
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 python/.venv/bin/python -B learning/runs/v2/current-pair-resource-calibration-prepare-luna-20261026-r4/test_calibration_cpu.py
```

Run the CPU-only strict checkpoint preflight with:

```sh
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX="$PWD/learning/runs/v2/current-pair-resource-calibration-prepare-luna-20261026-r4/bytecode-cache-empty" python/.venv/bin/python -B learning/runs/v2/current-pair-resource-calibration-prepare-luna-20261026-r4/cpu_preflight.py --output learning/runs/v2/current-pair-resource-calibration-prepare-luna-20261026-r4/cpu-preflight-validation
```

Preparation artifacts are not launch authority. Pending gates: independent review of the frozen R4 set, parent-side verification and registration of the exact plan hash, and parent-owned one-shot probe authorization.
