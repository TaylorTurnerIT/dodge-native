# Layer B RNG transition helper repair r2

Preparation only. Source and tests live only in this successor directory. No runtime helper binding, restore, checkpoint load, environment construction, lease, marker, or launch occurred.

## Repair

- Replaced nonexistent `torch.mps.initial_seed()` with pinned public `torch.mps.get_rng_state()` and injected fingerprint callback. Fake MPS surface is limited to pinned API names; test checks the pinned source AST.
- Trusted source callback must verify accepted receipt `cb3645899b5cb660d26d44645e00b3f53c5d0c8341b645b3b78af6b651d8b016` and expected checkpoint fingerprints before restore. Fresh live fingerprints do not block restore. Live fingerprints must match the accepted parent immediately after restore and before seeding.
- Seeds apply CPU then MPS. Backend availability uses `torch.backends.mps.is_available()`. CPU initial seed and CPU/MPS RNG-state digests must match preflight expectations.
- `TransitionSession` consumes one in-process attempt before restore; any later failure forbids retry. Pair vectors validate in full before transition. Finite prior master seeds reject.
- Exclusion validator accepts sorted `[low, high]` pairs and `low`/`high` mappings, normalizes to exact sorted union, and rejects bad bounds, overlap, duplicates, bad controls, collisions, and negative counters.
- Optimizer LR override uses update 397 at `3e-5`; linear schedule ends update 456 at `1e-5` over 60 updates. Old provenance remains origin 372, horizon 60, completed 24, saved LR `2.2203389830508474e-5`. This is planned arm design only; it does not authorize or change live LR.

## Verification

`python3 -m unittest -v`: 10 tests passed. Tests use only stdlib and fake APIs. They cover pinned MPS method surface, fresh live restore, trusted-source mismatch before mutation, CPU/MPS state mismatch, unavailable MPS, second invocation and consumed failed attempt, optimizer state/group preservation, sorted union, all three seed vectors' controls, invalid range/control cases, pairing mismatch, prior master rejection, and schedule endpoints.

## Unresolved gates

- `real_state_preflight.status` is `pending_notrun`. Expected real CPU and MPS state digests remain null. A separately verified real-runtime preflight must bind each digest to the full seed vector, vector hash, torch version, and preflight receipt. No actual digest is invented here.
- Injected fingerprint callback definition is unavailable. The required contract excludes only optimizer group `lr` from Adam fingerprint comparison and preserves optimizer moments/steps; this definition is not claimed verified.
- No runner binding, registration, runtime execution, native/environment check, checkpoint load, lease, marker, or launch. Existing exclusions remain a proposal only.
