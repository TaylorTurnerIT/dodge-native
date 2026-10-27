# Confirmed324 paired PPO worker preparation

Prepared worker and inert registration draft for exploratory paired learning-rate study `paired-lr-confirmed324-20261026-r1`. This package performs no launch, reservation, model deserialization, RNG read, training, evaluation, or promotion. Worker imports only Python standard-library modules. Runtime-specific work enters through explicit adapters and must be parent authorized.

`worker.py` enforces the confirmed parent identity, exact R5 private-binding source pins, measured-reference state, all six vector fields and canonical vector hash, registered exclusions, and update/counter/PPO controls before any adapter mutation. Missing, pending, malformed, or mismatched references fail before constructor seeding, model construction, environment construction, or claim callback. It delegates actual restore/reseed/claim semantics to a future adapter bound to the accepted R5 transition utilities. R5 measured CPU/MPS references remain `pending_notrun`; no values are supplied here.

`registration-draft.json` is intentionally unlaunchable. It contains explicit placeholders for arm, replica, pair, vector digest, and durable attempt path. `build_registration.py` rejects placeholders and accepts only the inert pending-reference template; it cannot promote status or create launch authority. Parent must replace this with a separately reviewed registration and complete source/runtime/reference pins.

`test_worker.py` drives a fake API through all 60 updates, checks arm LR endpoints and counter alignment, episode indices and exclusions before environment construction, five full candidate save points, and no-promotion completion. It uses no Torch, MPS, game, environment, production checkpoint, or actual random API. Tests do not qualify runtime integration.

Run from repository root:

```sh
PYTHONPYCACHEPREFIX="$PWD/learning/runs/v2/confirmed324-paired-PPO-worker-prepare-luna-20261026-r1/empty-pycache" PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s learning/runs/v2/confirmed324-paired-PPO-worker-prepare-luna-20261026-r1 -v
```

This output directory is the only task-owned write location. Frozen sources and parent records remain untouched.
