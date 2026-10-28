# Full-game seed-priority r3 origin-binding review

**Result: no blocking source findings plus limits.** The narrow r3 change fixes the observed package-origin mismatch without changing runtime bytes or checkpoint/identity pins. The prior attempt remains spent; this review grants no retry or launch authority.

## Origin path review

- `driver_binding.py:15-20` derives `PROJECT_ROOT` from the frozen package's `__file__`, then derives `CHECKPOINTS_RELATIVE` and `IDENTITY_RELATIVE` under that package. `RuntimeAdapter.bootstrap` passes `contracts.ROOT` to `build_callbacks` at `runtime_adapter.py:156-157`.
- `_read_pinned` resolves each path under that root, requires the file remain below root, and checks its original SHA-256 (`driver_binding.py:27-34`). The checkpoint and identity SHA pins are unchanged. `RUNNER_RELATIVE` and its SHA remain unchanged.
- `build_callbacks` checks the loaded checkpoint module's `__file__` against the package-owned checkpoint file (`driver_binding.py:88-98`), then retains exact source code signatures, source-file origins, identity `require` origin/code, and module/default checks (`:69-77, 99-115`). The private callback namespace remains built only from authenticated code objects (`:117-174`). Runner origin and code-object checks remain in place.
- The r2-to-r3 source-manifest delta is limited to `driver_binding.py` and new `tests/test_owned_origin_binding.py`. Runtime manifest is unchanged.
- The new regression imports the actual r3 package checkpoint and identity modules, calls `runner_namespace` and `build_callbacks` with a CPU `TinyNet` and Adam, verifies the recorded owned paths, and rejects a module whose `__file__` points at the predecessor runtime. It only constructs callbacks; it does not invoke restore or RNG capture.

## Verification

- Source manifest SHA before and after review: `a29e25b285d2d4651a2d74699929a27578860cfdd9a8d7980ca47c72824d41e2`; all 51 member hashes match.
- Runtime manifest SHA before and after review: `e032a5ab1d609512461e287d372375f1bf28800fb2b13d9c5cf98e20768de986`; all 14 member hashes match.
- Twelve scoped CPU/fake or stdlib tests passed: owned-origin regression (1), gate wiring (3), terminal checkpoint shape (1), pool schedule (4), seeded adapter (1), and seeded pipeline/accounting (2).

## Limits

This establishes source-level repair plus synthetic CPU callback-construction coverage. It does not qualify accepted learner restoration, RNG capture, MPS, native explicit-seed behavior, or gameplay. The preserved first attempt audit says the failure preceded environment construction/PPO and reports `retry_authorized=false`; do not reuse or clear its marker. Any later start needs a fresh parent registration and explicit authorization.
