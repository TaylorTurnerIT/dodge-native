# Paired upper-D64 endpoint evaluator r2

Preparation only. No actual game, native environment, checkpoint deserialization, MPS inference, training, lease, marker, or trial output was used. CPU tests used fake environments and a fake policy only. The frozen r1 directory remains unchanged.

The evaluator collects 64 independent one-slot environments in ascending manifest order. It uses D2, K=4, difficulty=2, patterns and powerups enabled, raw cap 18,000, one thread, no rendering or auxiliary targets, no resets, batched deterministic argmax only for live slots, and `torch.no_grad()`. Parent guard runs before each environment construction, each step, and after collection. The exact frozen three-range `excluded_seed_ranges` field is passed, including the upper-D range. Model training mode, weights/buffers, and Python, NumPy, and Torch CPU RNG state are restored or checked. The explicit production API is `evaluate_with_registered_backend(...)`; its imports, model construction, checkpoint loader, and native environment constructor remain lazy.

## Registration required by production API

Registration must include the r1 schema/episode contract plus:

- `linear_endpoint`: run id, checkpoint SHA-256, `endpoint_phase_update: 384`, `cumulative_update: 432`; parent supplies actual linear endpoint and receipt.
- `backend_identity.collector_sha256`: SHA-256 of this exact `paired_eval.py`.
- `backend_identity.model_source`: `python/dodge_rl/models/teacher.py`.
- `backend_identity.runtime_source_sha256`: SHA-256 map for `Cargo.toml`, `Cargo.lock`, both Rust crate manifests and every Rust source in `dodge-core` and `dodge-rl-env`, Python package/model/evaluator/identity/checkpoint sources, `docs/v2-m3-run-protocol.json`, plus the compiled `python/dodge_rl/_native*.so` file. Source root and imported Python/native module origins must match.
- Each endpoint has nonnull 64-hex checkpoint SHA, nonempty exact run ID, model `state_dict` SHA-256, and `metadata_sha256` for exact endpoint metadata JSON. Metadata must match run id, phase update 384, cumulative update 432, and checkpoint hash. Checkpoint file bytes match before loader; loaded model state-dict bytes match its independent SHA pin.
- Per-arm summary records constant and linear checkpoint SHA, run ID, registration SHA, and linear endpoint identity. Output uses same-directory temporary bytes plus exclusive hard-link publication; existing destinations fail and stay unchanged. Output includes collector SHA, registration SHA, and observed model state-dict SHA.
- RNG, all module modes, parameters/buffers, and parameter gradients are snapshotted around inference. Inference runs in eval and `torch.no_grad()`. Any mutation fails closed and restores original RNG, mode, weights, or gradients.
- Native production collection rejects `unavailable` death cause. Explicit `validate_rows(..., allow_unavailable=True)` remains only for offline legacy-row diagnostics; native collector defaults to rejecting it.
- For a reviewed injected backend, `injected_backend_reviewed: true` and exact env/model/checkpoint-loader identities. Partial callback injection is rejected.

All pins and endpoint metadata are checked before model construction, deserialization, or environment creation. Parent guard must include execution-budget checks before calling the API and remain active throughout. No fallback checkpoint, seed, runtime, or collector exists.

The constant endpoint remains pinned to update 384 / cumulative 432 / SHA-256 `e25117bf52f14629a3d2ffada319c49a10c6344763a25506a5f124a76a62199b`. Linear endpoint is unresolved until parent binds its exact metadata and receipt. Seed manifest remains `e11e9d6accb79fcafd1b0e6049c322356edf16601007d2af62da6b59539c886c`: ascending `D0000040..D000007F`, unselected training-excluded development namespace, prior nonuse not proven, not sealed or proven independent.

Raw validation requires startup 13; exact XOR of termination/truncation; fatal conservation `gameplay_frames = alive_frames + 1`; exact cap truncation `alive_frames = gameplay_frames = 18000`; fixed score identity; optional objective-return identity; and native-compatible unavailable death telemetry. Cause-unavailable death rows retain null fatal frame and contacts. Terminated native telemetry requires fatal frame equal gameplay frame; truncations carry null death telemetry.

Comparison remains diagnostic: one paired training seed `4200000001`; average LR differs (`2e-5` linear vs `3e-5` constant); fixed update-384 endpoint only, no best-checkpoint selection. Retained dev64 decision remains separate and parent controlled. No real-game timings or resource qualification claimed.

## CPU tests

```sh
cd /Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/paired-LR-upperD64-evaluator-luna-20261026-r2
mkdir -p empty-cache
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 XDG_CACHE_HOME="$PWD/empty-cache" /Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/python/.venv/bin/python -B -m unittest -v
```
