# Layer B RNG transition helper: frozen source review (r1)

Reviewer: Haiku 5.5, source-only review. No imports, execution, torch/MPS, native, checkpoint, game, training, lease, marker, or shared-state actions. Only file reads, grep, and stdlib JSON parsing of the frozen artifacts.

Verdict: **not ready to bind.** Three blockers. Parent must fix them before any registration or runner binding.

## Reviewed bytes (sha256)

| File | sha256 |
|---|---|
| `layerB-RNG-transition-helper-luna-20261026-r1/transition.py` | `bc4fde169e5923c0b254942d5f6a60f2eaa3d582fc2711a211f2ec33bc482b8f` |
| `layerB-RNG-transition-helper-luna-20261026-r1/test_transition.py` | `8f61ad17f48b9982f7f30a2a5ca3d52eadd40e8927bc6b7367bf19fc0ccb146c` |
| `layerB-RNG-transition-helper-luna-20261026-r1/seed-vectors-successor-metadata.json` | `92cab6ca41058ffd1510ee83d272973d78c4a1d82bb102a9c93390cbe108e102` |
| `layerB-RNG-transition-helper-luna-20261026-r1/receipt.json` | `fe07853c33740b4c6f0e8c49111b55880ef0809d7d4112ba55161e41091a057d` |
| `layerB-RNG-transition-helper-luna-20261026-r1/report.md` | `e0b17db384985c5abdb2e7b375b1df4c246dd7d837d190a9d6ad1d6b7b3e1606` |
| `layerB-RNG-transition-helper-luna-20261026-r1/controls.log` | `93136c8ae71bc3d7f4b01c2f53b266005acaea6a388597c02a223f9060dce395` |
| `expanded-eval-parent-integration-20261026-r1/prospective-training-exclusions.json` | `d2fab545d55630dbc713f4b48a44138cb04fd753d15d29737c3b4ea32d126c58` |
| `learning/.venv/lib/python3.12/site-packages/torch/mps/__init__.py` (torch 2.14.1, 255 lines) | `642d893d4e235fac8a75d47cb795f0aeb9e9ee85998b9b54beb49bc01f289d7a` |
| `learning/.venv/lib/python3.12/site-packages/torch/random.py` | `0b2bd65c8fdf324e00ed2c64e7b06ca5d5ff96053001055c86352c0b3668d0be` |

Receipt hashes for `transition.py`, `test_transition.py`, `seed-vectors-successor-metadata.json`, `controls.log`, and `report.md` match the frozen receipt. Total reviewed bytes across the six helper files: 69,470.

## Blockers

### B1 (HIGH): `torch.mps.initial_seed()` does not exist on the pinned runtime

- Where: `transition.py:75` (`torch_api.mps.initial_seed()`). Fake: `test_transition.py:22`.
- Evidence: `torch/mps/__init__.py` defines `device_count`, `synchronize`, `get_rng_state`, `set_rng_state`, `manual_seed`, `seed`, and more. A grep for `initial_seed` and `__getattr__` in that file returns nothing. The only `initial_seed` in `torch/` at this pin is the top-level `torch.initial_seed` (`torch/random.py:144`, CPU default generator).
- Trigger: any real run on torch 2.14.1 reaches line 75 after both seed calls succeed.
- Consequence: `AttributeError` mid-transition after reseed and before the LR is set. Every real run fails. The six tests pass only because `FakeMPS.initial_seed` (line 22) invents the method the real module lacks.
- Fix: drop the MPS `initial_seed` read-back. Use a real surface, e.g. compare `torch.mps.get_rng_state()` against a state captured from a reference seed, or make the MPS evidence a driver-side probe. Build fakes only from attributes present in the pinned module. Add a test that fails on any fake attribute not in the pinned surface.

### B2 (HIGH): pre-restore check requires live state to already equal the accepted parent

- Where: `transition.py:60-63`. Test that codifies it: `test_transition.py:75-80` (asserts `restored == []` after a mismatch).
- Trigger: a fresh process, or any process whose model/Adam/RNG differ from accepted 348 before restore (the normal case the restore exists for). `current_fingerprints()` returns non-parent values, so `ValueError("parent ... do not match accepted 348")` raises before `restore_trusted()` runs.
- Consequence: the helper only succeeds when restore is a no-op. The brief's "trusted restore then verify" cannot happen. Report line 14 ("check ... only after ... Recheck after trusted restore") carries the same inverted wording.
- Fix: verify the trusted source (receipt sha256 and expected fingerprints of the checkpoint artifact) before restore. Keep the live post-restore check at line 64-66. Rewrite `test_transition.py:75-80` to assert restore runs when live state differs.

### B3 (integration blocker, fails closed): exclusion-union check is order-sensitive and wrong-shaped for the installed artifact

- Where: `transition.py:22-26` (`EXPECTED_EXCLUSION_RANGES` in order B, D128, E, D1_new, D2_new) and `transition.py:127-128` (tuple equality on the ordered sequence).
- Evidence: `prospective-training-exclusions.json` lists the same five ranges sorted by start: B, D128, D1_new, D2_new, E. Its entries are `[low, high]` lists with no names. The helper expects dict rows with `low`/`high` keys.
- Trigger: the parent installs the proposal file as the future union and passes its rows to `validate_exclusion_controls`.
- Consequence: `ValueError("future environment requires exact five-range exclusion union")` on an identical union. Fails closed, but blocks registration. The set of ranges is the same; only order and shape differ.
- Fix: normalize both sides to `sorted((low, high))` tuples and compare sets, plus check `low <= high` and no overlap. Add an adapter from the proposal's list form. Add a test that feeds the sorted proposal form and expects acceptance.

## Non-blocking defects (MEDIUM)

### M1: MPS seed call can silently no-op

- `torch/mps/__init__.py` `manual_seed` returns without error when `torch._C._has_mps` is false. `transition()` only checks the string `backend == "mps"` (`transition.py:53`).
- Trigger: a non-MPS torch build or an unavailable device.
- Fix: require `torch.backends.mps.is_available()` in the injected API or the driver, and read back real state.

### M2: `seeded_once` is a hardcoded literal with no guard

- `transition.py:94` returns `"seeded_once": True` unconditionally. Nothing stops a second `transition()` call in the same run from reseeding mid-run.
- Trigger: a driver that calls `transition()` twice for one run.
- Fix: track a per-run flag in the injected state, or move seeding behind a once-only object.

### M3: prior-master rejection is not enforced by the helper

- `seed-vectors-successor-metadata.json` `derivation.prior_master_seeds_rejected` lists `810631976, 3192039780, 3791628417, 4200000000, 4200000001, 5562881586070242562`. `validate_seeds` (`transition.py:33-45`) checks only type and bounds.
- Trigger: `transition(seeds=...)` with `env_master_seed = 5562881586070242562`, or any other listed value.
- Fix: reject any seed that appears in the rejected-master list, or move the check into the injected driver with a test.

### M4: pairing is not enforced at transition time

- `validate_pair` (`transition.py:116-123`) is never called by `transition()`. `transition()` takes one `seeds` dict and one `arm`, so the driver can give arms different vectors.
- Fix: the driver must call `validate_pair` on the full pair, or `transition()` must accept the pair.

### M5: model/Adam invariance is not rechecked after the LR write, and the Adam fingerprint definition is not in the reviewed files

- `transition.py:81-84` checks invariance after reseeding. Lines 85-91 then change `group["lr"]`, and nothing rechecks afterward.
- If the Adam fingerprint includes group `lr`, the final state no longer matches `EXPECTED_PARENT["Adam"]` and nothing detects it. If it excludes `lr`, the claim holds but is unverified in this bundle.
- Fix: state in the contract which Adam fields the fingerprint covers. Add a post-LR recheck or a test that pins the fingerprint definition.

## Low-severity items (LOW)

- L1 `transition.py:86`: `lr = 3e-5 if arm == "A_constant_3e-5" else 3e-5` has identical branches. Use `controller_lr(arm, 397)` so the B start is derived, not hardcoded.
- L2 `transition.py:48-51`: parameters `model` and `fingerprint` are unused. Remove them, or document them as deliberately inert.
- L3 `test_transition.py:64-73` (`test_reverse_order_is_detected`) never calls `transition()`. The `raise` sits in the test body, so the test would pass if the helper's ordering code were deleted. Ordering coverage actually comes from `test_order_readback_and_model_adam_invariance` (its `mps_seed == 987` assertion would fail on a reversed order). Replace this test with one that drives `transition()` with a reversed-order fake.
- L4 `test_transition.py:39-41`: fake Adam state lives inside `param_groups`. Real `torch.optim.Adam` keeps moments in `optimizer.state` keyed by parameter. The test is a fidelity gap, not a defect in the helper.
- L5 `test_transition.py:102-122`: `validate_exclusion_controls` is exercised only on `vectors[0]`. Vectors 1 and 2 are not checked. No test covers the collision branch (`transition.py:136-137`) or a negative `rejection_counter`.
- L6 `controller_lr` (`transition.py:105-107`): arm A returns `3e-5` for any input, including invalid `cumulative_update`. Validate the input for both arms.

## Verified correct (by reading)

- `EXPECTED_PARENT` (model `b106e8e1...`, Adam `29108e84...`, RNG `831d8fa2...`) matches the frozen receipt.
- Seed call order CPU then MPS is correct for this pin. `torch/random.py:62-72` (`_manual_seed_impl`) calls `torch.mps.manual_seed` after the CPU seed, so the helper's explicit `torch.mps.manual_seed` call last matches.
- `torch.initial_seed` (top-level, `random.py:144`) exists, so the CPU read-back at line 74 works.
- `controller_lr`: update 397 gives `3e-5` and update 456 gives `1e-5` (`test_transition.py:108-109` passes by reading).
- `OLD_CONTROLLER_PROVENANCE.saved_lr` = `3e-5 - 2e-5*23/59` = `2.2203389830508474e-05`. Consistent with origin 372, completed 24, using the same formula. Note for parent: the schedule steps from `2.22e-5` at update 396 to `3e-5` at update 397. This is intended by the brief, but the parent should confirm it is accepted.
- Successor metadata: 3 vectors, each with 64 rows and `reserved_hits` 0, `zero_actual_seeds` 0. No row falls inside the five-range union (checked by stdlib read). `prospective-training-exclusions.json` contains the same five ranges as the metadata, as a set.
- `episode_indices` has 64 entries but only 32 distinct values (range 273-322), with repeats. This matches the parent's per-slot construction (`stdlibderive.py:182-193`), so it is not a defect. The helper's wording "64 parent episode indices" should say "64 per-slot indices".
- The row field `first_actual_seed` is one seed per slot (64 distinct values per vector), so the check covers all 64 slots despite the name.

## Limits (integration, not defects in the reviewed files)

- No runtime fingerprint implementation exists. `current_fingerprints` and `restore_trusted` are injected and unverified.
- No real torch or MPS state read-back exists. The controls list in the metadata (`controls_pending_runtime`) is still pending.
- No environment construction; the union is not installed, and collision reconciliation with the native runtime is pending.
- The training loop is not wired to `controller_lr`. Nothing in the reviewed code proves the loop calls it per update.
- Master-seed collision checks are limited to the parent's finite history (see M3 and the parent's F7 note).
- Parent registration, lease, and acceptance procedures are outside this review and remain authoritative.
- Nothing was executed. The "6 tests passed" claim in the receipt was not re-run here. My findings for B1 and B2 rest on the reading of the source and the pinned module, not on a test run.

## Required before binding (parent)

1. Fix B1: remove `mps.initial_seed`; fakes must match the pinned surface.
2. Fix B2: verify the trusted source before restore; rewrite the test that asserts the inverted behavior.
3. Fix B3: order-insensitive, shape-aware union check; add a test with the sorted proposal form.
4. Address M1-M5 or record them as accepted limits.
5. Re-run the six tests after fixes and re-hash. Only then request another review.
