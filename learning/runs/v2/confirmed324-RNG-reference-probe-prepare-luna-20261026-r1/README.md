# confirmed324 RNG reference probe preparation

Preparation only. No MPS/device call, production checkpoint read or deserialization, model/env construction, training, evaluation, launch, marker, lease, ledger, or root README change occurred.

`probe.py` is an inert worker library. A future parent-owned exact-once worker must import pinned Torch 2.14.1 and NumPy 2.5.4 only after registration checks; verify SHA-256 of checkpoint bytes without deserializing; verify the exact vector file/hash and source pins; then call `capture_references`. Each reference seeds CPU first and explicit MPS last, reads `torch.get_rng_state()` and `torch.mps.get_rng_state()`, and fingerprints through the pinned `fingerprints.py` bytes. It must never call `torch.mps.initial_seed`, construct a model or environment, or apply constructor/env seeds. The measurement represents initial generator state only, not checkpoint restore proof.

The future parent supervisor must use the exact hash-pinned `execute_once.py` source bytes in `build_registration.py` for its reviewed process sampling and bounded TERM/KILL/reap primitives. It must implement this probe's separate schema and preflight; it must not call that file's evaluation `preflight`, `execute_once`, modes, or evaluation worker. Before marker O_EXCL claim, validate registration/source/runtime/interpreter/vector/checkpoint/original receipt pins, owned empty cache, empty output, cancellation absence, parent ledger's exact `active_inference_diagnostic` lease, and no conflicting leases. No ledger writes or child lease clearing. At 0.2 second intervals, check cancellation, registration/source/lease/marker pins, process-group RSS and heartbeat MPS bytes. Accept nonnegative MPS bytes including zero; reject over-cap. Bound startup at 12 seconds, work at 45 seconds, outer wall at 55 seconds, cleanup at 10 seconds, caps at 6 GiB RSS and MPS, stale heartbeat at 2 seconds. The heartbeat must run independently through imports. Always retain raw exit, process-group absence, outer receipt, and partial failure artifacts. Never clear marker or retry.

Publish the three reference files plus aggregate receipt atomically only after all captures and post-capture checks pass. Existing marker/output collision, partial three-reference set, schema drift, or any failed check is terminal. The same replica reference is shared by both paired arms. Parent owns final registration, independent source/registration review, lease installation, one-shot execution, and postflight acceptance.

## Checks

Fake Torch/MPS API tests and toy byte fingerprints only; no actual Torch, NumPy, MPS, environment, or checkpoint imported. Runtime command:

```sh
PYTHONDONTWRITEBYTECODE=1 projectpython/.venv/bin/python -B -m unittest -v test_probe
```

Use `PYTHONDONTWRITEBYTECODE=1` and the registered empty owned cache for future runtime. No test is launch authority.
