# Confirmed324 runnable RNG reference probe

Preparation only. `worker_cli.py` and `supervisor_cli.py` are executable CLIs for `d2_layerb_rng_reference_probe_registration_v1`. The builder points at these files. Supervisor verifies its separate registration, source, interpreter, runtime version, vector, checkpoint-byte, accepted-receipt, empty-cache, output, cancellation, and exact lease gates before the exclusive marker claim. It reuses only hash-verified process sampling and bounded cleanup primitives from `confirmation-proof-binding-parent-repair-20261026-r4/execute_once.py`; it never calls evaluator preflight or execution.

Worker hashes checkpoint bytes only. It does not deserialize a checkpoint, construct a model/environment, apply constructor/environment seeds, train, evaluate, or launch. Each replica calls CPU `manual_seed`, MPS `manual_seed` last, then fingerprints CPU and MPS generator states. It does not call `torch.mps.initial_seed`. Same replica reference is shared by both paired arms.

Three reference files and aggregate receipt publish with exclusive per-file creation. `COMMITTED.json` is the sole complete-set signal and is created exclusively after all four payload files. Partial files remain diagnostic artifacts and are not complete. Outer receipt records raw worker exit, stop reason, process-group absence, and artifact hashes. Marker and partials are never cleared or retried.

Fake runtime injection requires both an explicitly synthetic registration and `RNG_PROBE_SYNTHETIC_TEST=1`. It does not relax source, lease, marker, input pin, resource cap, or commit checks. Test checkpoint access hashes the pinned bytes only.

## Verification

Command used project Python 3.12.15 with `-B`, `PYTHONDONTWRITEBYTECODE=1`, and a fresh task-owned empty cache:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX="$EMPTY_CACHE" /Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/python/.venv/bin/python -B -m unittest -v test_probe test_campaign
```

Seven fake-only tests passed, including builder pin validation and a complete synthetic supervisor/worker CLI campaign with exclusive commit validation. No actual Torch, NumPy, or MPS import/call occurred. No real RNG reference was captured. Final status remains `pending_notrun`; parent must independently review source and registration, install the exact lease, and own any later one-shot execution and postflight.
