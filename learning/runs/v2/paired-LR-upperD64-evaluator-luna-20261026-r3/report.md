# r3 implementation report

## Result

Implemented the r2 B-A through B-D repairs inside the authorized r3 output directory. r2 sources and all campaign/runtime state remain untouched.

## Changes

- Runtime pins now bind the exact frozen `own/runtime` package tree and its complete member map, checked against both byte-pinned training registrations. Native import must resolve to the same `022d41…` module used by both arms.
- Model source pin uses `dodge_rl/models/teacher.py`. Root Cargo/Rust layout is no longer part of runtime loading.
- Endpoint schema accepts the parent's immutable CPU attestations and separately pins metadata files, checkpoint bytes, state-dict hashes, update values, full-audit references, and derivation receipt.
- Production path checks the manifest before registration and backend setup. `evaluate_registered` is removed; only `evaluate_with_registered_backend` publishes production output.
- Existing 64-seed D2 loop, CPU-only restriction, no-grad inference, guards, frame/score/death telemetry checks, model/RNG/gradient mutation checks, and exclusive output publication remain.

## Verification

`cpu-tests.log`: 13 tests passed, using fake environments and policy only. No actual environment, native import, checkpoint deserialization, MPS, lease, marker, or evaluation was used.

Parent must independently review this source, create the final immutable registration in its own authorized directory using `registration-inputs.json`, and provide its runtime guard before any later evaluation decision.
