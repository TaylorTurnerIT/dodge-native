# Layer B RNG transition helper r2: frozen source review (Haiku 5.5, r1)

Reviewer: Haiku 5.5, source-only review. No imports, no execution (tests not re-run), no torch/MPS, native, checkpoint, game, training, lease, marker, or shared-state actions. Actions taken: file reads, grep, stdlib JSON parsing of frozen artifacts, and SHA-256 hashing. The test log in the successor directory is cited, not reproduced.

## Verdict

- No HIGH blocking findings against the r2 source as a helper.
- All three r1 blockers (B1, B2, B3) are resolved in the source. Verified by reading.
- The r2 contract is usable as a fake-tested source skeleton. It is **not** sufficient for real binding yet. Three MEDIUM items must be fixed or explicitly accepted before any real preflight or runner binding: F1 (optimizer invariant is vacuous), F2 (digest binding not enforced), and F3 (injected callback definitions and real tensor types unverified).
- Real preflight gates remain `pending_notrun`. No real RNG, Adam, model, or MPS state was computed here.

## Reviewed bytes (sha256)

Successor directory `learning/runs/v2/layerB-RNG-helper-repair-luna-20261026-r2/`:

| File | sha256 | Matches receipt |
|---|---|---|
| `transition.py` | `18598ff34f25a31d3dcee961a20064cd470289bb3f0bf1853173095fd6f0ae1c` | yes |
| `test_transition.py` | `c8045189d5c987ce0a63544089eacb2883015223834b28745371b1f4c6c1a4dc` | yes |
| `seed-vectors-successor-metadata.json` | `e112b25a4163ebea38d72429b28613e5bb5a90c71920ce421190a5ba6d6db334` | yes |
| `receipt.json` | `a4c48fbed7defeb36a2d6d789c680437558bf0537f1c638b531f1a48611dde4d` | (self) |
| `report.md` | `12f3866f55421a935b76e5008d2a35cd856d29e00f9b238967db1e5fa75955fd` | yes |
| `test.log` | `6dae9c405e3479f378de521c8fdd2070acf5e05630979603038643263759c64c` | yes |
| `controls.log` | `e0b5710e616c4f7b44d6f67753c471e74927fd874a74d0fd138303ff013af188` | yes |
| `sha256.txt` | `e927c82b21621e9ac8da0ea1aa2d46334acbf4c30f551fb25bf37067ba49a86e` | (not in receipt) |

Other bytes read for cross-checks:

| File | sha256 |
|---|---|
| `layerB-RNG-helper-r2-parent-validation-20261026-r1/receipt.json` | (not hashed; contents match hashes above) |
| `D2-retained324-linear-parent-terminal-audit-20261026-r1/retained-best-candidate-receipt.json` (accepted parent receipt) | `cb3645899b5cb660d26d44645e00b3f53c5d0c8341b645b3b78af6b651d8b016` |
| `expanded-eval-parent-integration-20261026-r1/prospective-training-exclusions.json` | not hashed; read via stdlib JSON |
| `learning/.venv/.../torch/mps/__init__.py` (255 lines, torch 2.14.1) | `642d893d4e235fac8a75d47cb795f0aeb9e9ee85998b9b54beb49bc01f289d7a` (unchanged from r1) |
| `learning/.venv/.../torch/random.py` | `0b2bd65c8fdf324e00ed2c64e7b06ca5d5ff96053001055c86352c0b3668d0be` (unchanged from r1) |
| `learning/.venv/.../torch/backends/mps/__init__.py` | `41ad419584060de3dec625e64b51a247024e87a463d490c6c0e5e7a59f24c6d2` |

## r1 blocker status

**B1 (torch.mps.initial_seed does not exist): resolved.** `transition.py` no longer calls `initial_seed` on MPS. Pinned `torch/mps/__init__.py:35-42` defines `get_rng_state(device="mps")` returning a ByteTensor, and `:57-70` defines `manual_seed`. The MPS read-back is now a digest of `get_rng_state()` against a preflight value (`transition.py:85`). `FakeMPS` exposes only `manual_seed` and `get_rng_state` (`test_transition.py:17-20`), and test line 48-49 checks the pinned module AST. Limit: the pinned file contains no `initial_seed`, and the test asserts that for MPS only.

**B2 (pre-restore check required live state already equal parent): resolved.** `transition.py:73-74` verifies the trusted source (receipt sha and checkpoint fingerprints) before restore. `transition.py:76-78` restores, then checks live fingerprints equal the accepted parent. Fresh live state is allowed. `test_transition.py:50-53` and `:55-58` cover fresh restore and source mismatch. The inverted r1 test is gone.

**B3 (order-sensitive, list-shaped exclusion union): resolved.** `_normalize_range` accepts `[low, high]` and `low/high` mappings (`transition.py:38-44`). The union is sorted and compared to `EXPECTED_EXCLUSION_RANGES` (`:47-50`). I checked the proposal by stdlib: `excluded_seed_ranges` is the same five sorted ranges, and `EXPECTED_EXCLUSION_RANGES` matches it. The sorted-form acceptance test is covered by `test_sorted_proposal_ranges_and_all_three_vectors` (`test_transition.py:82-87`), with the caveat in F5.

r1 medium and low items:

- M1 (silent MPS no-op): addressed by `transition.py:67` (`torch_api.backends.mps.is_available()`). Pinned `mps/__init__.py:67-68` returns silently when `_has_mps` is false, so the availability gate is needed and present.
- M2 (`seeded_once` literal): replaced by `TransitionSession` (`transition.py:14-16`, `:66`, `:75`). Scope limit: see F4.
- M3 (prior-master rejection not enforced): partially addressed. Enforced for `env_master_seed` only (`transition.py:24`). See F6.
- M4 (pairing not enforced at transition time): addressed (`transition.py:69-70`).
- M5 (Adam post-LR recheck): addressed by `final` check (`transition.py:93-94`). The fingerprint definition is still unverified. See F3.
- L1 (identical LR branches): addressed; `controller_lr(arm,397)` (`transition.py:92`).
- L2 (unused `model`, `fingerprint` params): addressed; not in the signature (`:64`).
- L3 (`test_reverse_order_is_detected` never calls `transition()`): partially addressed. See F5.
- L4 (fake Adam state shape): partially addressed. `FakeOpt.state` exists (`test_transition.py:28`), but values are plain lists and ints. See F1.
- L5 (controls checked only on vector 0): **not addressed.** See F5.
- L6 (arm A accepts invalid cumulative_update): addressed (`transition.py:26-28`).

## New findings

### F1 (MEDIUM): optimizer invariant at `transition.py:91` and `:97` is not a deep check

- Where: `transition.py:91` (`old_state=optimizer.state.copy()`) and `:97` (`if optimizer.state!=old_state`).
- Trigger: real `torch.optim.Adam`. `optimizer.state` maps each parameter to a dict of tensors (`exp_avg`, `exp_avg_sq`, `step`).
- Mechanism: `.copy()` is shallow, so the per-parameter dicts and tensor objects are shared. CPython dict comparison uses an identity shortcut (`PyObject_RichCompareBool`). An in-place change to a moment tensor therefore compares equal, and the check cannot fire. If an entry were replaced with a new dict, the comparison would call tensor `==` and raise `RuntimeError` on multi-element tensors (ambiguous truth value), not `ValueError`.
- Test gap: `FakeOpt` uses lists and ints (`test_transition.py:28`), so the test cannot show the failure. `test_optimizer_state_and_group_fields_preserved` (`:79-81`) compares a JSON snapshot, but not with a mutating fake, and it does not exercise the helper's own check.
- Consequence: the return value at `transition.py:98` asserts "optimizer.state moments/steps unchanged". Nothing in the helper verifies it for real tensors. The claim is false assurance. Nothing in `transition()` steps the optimizer, so the practical risk is low. The defect is the claim.
- Fix: snapshot each parameter state by cloning tensors before the LR write and compare with `torch.equal`, or hash the tensor bytes with the same `state_fingerprint` used for RNG. Add a fake with real-like tensor-valued state that mutates in place and expects rejection. Or drop the claim from the contract.

### F2 (MEDIUM): real-preflight digest binding is not enforced by the helper

- Where: `transition.py:72` accepts any 64-character string for each expected digest. `:84-85` compare against them.
- Metadata requirement: `seed-vectors-successor-metadata.json` `real_state_preflight.binding_required` lists `vector_sha256`, `complete_seed_vector`, `torch_version`, and `preflight_receipt_sha256`. The helper checks none of these. Hex format is not checked.
- Trigger: a placeholder, stale, or mis-keyed digest, or one captured under a different torch version, is passed in.
- Consequence: the helper fails closed, but only after the trusted restore and reseed (`:76-81`). Because `_started` is set at `:75`, a wrong digest consumes the one attempt after live state is already mutated. A digest bound to the wrong vector can pass format checks. Expected digests therefore have no binding enforced in code. The brief requires that they bind the actual seed vector, version, and provenance.
- Fix: require a binding object (`vector_sha256`, `torch_version`, `preflight_receipt_sha256`, plus the complete seed vector) and verify it inside the helper before `_started`. Check that digests are lowercase hex, 64 characters. Document that the external driver must produce the preflight receipt from a separate real-runtime run. No real digests are computed here.

### F3 (MEDIUM): injected callbacks and real return types are unverified

- Where: `verify_trusted_source`, `restore_trusted`, `current_fingerprints`, and `state_fingerprint` are all parameters (`transition.py:64`).
- Real return types: pinned `torch.mps.get_rng_state` returns a ByteTensor (`mps/__init__.py:42`). `torch.get_rng_state` on CPU returns a tensor (`random.py:39`). The fakes return `bytes` (`test_transition.py:20`, `:26`). Any real `state_fingerprint` must accept tensors. This is not tested.
- Adam fingerprint: the contract says "Adam exact excluding param_group.lr" (`transition.py:98`). The helper's post-LR check (`:94`) is only correct if the Adam callback excludes `lr`. A `state_dict()`-based fingerprint would include it and fail closed after mutation. The callback is declared unverified in the report and in `fingerprint_contract_status` (`transition.py:98`). I agree the declaration is accurate.
- Trusted source: the helper checks the callback's returned `receipt_sha256` and `checkpoint_fingerprints` (`:74`). It does not check the checkpoint file hash itself. The accepted receipt has a `checkpoint_sha256` field. The real callback must recompute from disk. The helper trusts whatever the callback returns.
- Fix: write down each callback's definition, with a byte-level fingerprint for tensors and an explicit lr exclusion. Test with tensor-valued fakes. Mark the source callback as a trust boundary in the contract.

### F4 (LOW): once-only session is in-process only

- Where: `transition.py:14-15` (docstring says "one attempt per process/run"). `:66` and `:75` enforce it only within the object.
- Trigger: a failed mutable-phase run is relaunched in a new process. `TransitionSession()` is new, so `_started` is False.
- Consequence: the helper does not enforce once-only across processes. That depends on the external lease and marker, which this review did not read. Acceptable only if those gates enforce it.

### F5 (LOW): test coverage claims overstate what is exercised

- `test_sorted_proposal_ranges_and_all_three_vectors` (`test_transition.py:82-87`): the loop over `VECTORS` builds `controls` from the module-level `CONTROLS` (vector 0 only, line 11), so vectors 1 and 2 are never passed to `validate_exclusion_controls`. Vector 2 is never passed to `validate_seeds`. The name overstates the test.
- `test_bad_state_and_reverse_order_detected_after_restore` (`:63-68`): the second case changes the MPS seed value (`seed+1`), not the call order. The test name overstates it. Order is checked separately by the `events` assertion in `test_fresh_live_state_restores_and_seed_order` (`:52`), which is real and correct.
- Check I ran by stdlib, without importing the helper: all three vectors pass the bounds in `validate_seeds`. None of their 64 `first_actual_seed` values fall in the five-range union. `ranges` in each vector's `exclusion_union_ranges` equal the proposal. `reserved_hits` is 0 for each. Vector 0's and vector 1's seeds also pass `validate_pair`, via `test_pair_mismatch...` (`:99-101`).
- Fix: loop over each vector's own `env_control.episode_controls`, call `validate_seeds` on each vector, and rename the tests to match what they check.

### F6 (LOW): rejected prior-master list applies only to `env_master_seed`

- Where: `transition.py:24`, with `REJECTED_MASTERS` at `:8`.
- Metadata: `derivation.prior_master_seeds_rejected` is a list of six values. Five of them are below 2^32 (`810631976`, `3192039780`, `3791628417`, `4200000000`, `4200000001`). They could be entered as `numpy_global_seed` or `constructor_init_seed` without rejection.
- Consequence: low probability, but the contract does not match the r1 M3 fix. Decide whether the list applies to every seed field or only master seeds, and make the code and metadata say so.

### F7 (LOW): exclusion control checks cover only the first episode per slot

- Where: `transition.py:59-61`, `validate_exclusion_controls`.
- Metadata: `env_control.kind` is `splitmix64_slot_stream_first_episode`. The `first_actual_seed` field is one seed per slot. The check covers the first episode only.
- Consequence: if the environment draws more seeds per slot after the first episode, those seeds are not checked here. The helper cannot establish that.
- Fix: confirm in the native or environment review that the first episode is the only seed drawn per slot for this run, or extend the control rows.

### F8 (LOW, design confirmation for parent): LR step at the boundary

- Old provenance (verified, accepted receipt): `optimizer_group_lrs[0]` = `2.2203389830508474e-05`, `candidate_cumulative_counters.updates` = 396, `origin_cumulative_update` = 372, `horizon_updates` = 60. `OLD_CONTROLLER_PROVENANCE` (`transition.py:10`) matches exactly.
- New arms: `controller_lr` gives `3e-5` at update 397 for both arms (`transition.py:28-31`, `:92`).
- Effect: a step of about +35% from the saved LR (3e-5 / 2.2203e-5 ≈ 1.35) at the first new update. The old formula would give `3e-5 - 2e-5*24/59 ≈ 2.1864e-5` at update 397. The brief states the new design, and both arms share the step, so pairing is preserved. The parent should confirm the step is intended. This review does not authorize or change any live LR.

## Checked and consistent

- `EXPECTED_PARENT` (`transition.py:5`) matches the accepted receipt `cb3645899b5cb660d26d44645e00b3f53c5d0c8341b645b3b78af6b651d8b016` (the retained best candidate receipt for phase update 348, under `D2-retained324-linear-parent-terminal-audit-20261026-r1/`). Its `learner_fingerprints` contain `model` `b106e8e1…`, `Adam` `29108e84…`, and `RNG` `831d8fa2…`. Note: the file named `D2-retained348-parent-finalizer-preflight-20261026-r5/receipt.json` has a different sha (`791ff994…`) and is not the accepted receipt. Its selected fingerprints match the same three values.
- The brief's "accepted 348 receipt" is the `retained-best-candidate-receipt.json` above, which is the one whose hash `transition.py` checks.
- The accepted receipt's run seeds (`4200000001` and `5562881586070242562`) are both in `REJECTED_MASTERS`. The three new vectors' `env_master_seed` values are not. Checked by stdlib.
- Seed call order CPU then MPS: correct for the pinned runtime. `random.py:62-72` (`_manual_seed_impl`) seeds MPS as a side effect of `torch.manual_seed`. The helper's explicit MPS call at `transition.py:81` runs last, so the MPS seed is the one kept.
- `torch.initial_seed` exists at top level (`random.py:144`) and is used for the CPU read-back (`transition.py:82`).
- `torch.backends.mps.is_available` exists (`backends/mps/__init__.py:29`), as used at `transition.py:67`.
- Controller arithmetic: the old formula at `u=24` gives `2.2203389830508474e-5`, matching the receipt. The new B arm gives `3e-5` at 397 and `1e-5` at 456. `controller_lr` uses `horizon-1 = 59` denominators, the same as the accepted receipt's `formula` field. "Over 60" means 60 updates with 59 steps, which is consistent with the parent's schedule.
- Metadata: three vectors, each with 64 slots and `reserved_hits` 0. Vector seeds are within the helper's bounds, with no collisions and no rejected masters in `env_master_seed`.

## Limits

- Nothing was executed. The 10-test result in `test.log` is cited from the parent, not re-run. Findings are from reading and stdlib JSON parsing.
- No real torch, MPS, RNG, Adam, or model state was read. No digest was computed. `real_state_preflight.status` is `pending_notrun`.
- The injected callbacks (`verify_trusted_source`, `restore_trusted`, `current_fingerprints`, `state_fingerprint`) are not implemented or reviewed here (F3).
- The training loop is not wired to `controller_lr`. Nothing here proves the driver calls it per update.
- Runner binding, registration, lease, marker, and native environment behavior are outside this review. Cross-process once-only enforcement (F4) and the environment's seed draw pattern (F7) depend on them.
- Torch version: the pinned module hashes above match r1, which reported torch 2.14.1. I did not re-verify the version string from `dist-info` metadata beyond the directory name.

## Required before real binding (not before source acceptance)

1. F1: replace the optimizer `!=` check with a tensor-safe deep check, or drop the invariant claim.
2. F2: require and verify the preflight binding (`vector_sha256`, `complete_seed_vector`, `torch_version`, `preflight_receipt_sha256`) inside the helper before `_started`. Validate digest format.
3. F3: document each callback's byte-level definition, with tensor inputs and an Adam fingerprint that excludes `lr`. Add tensor-valued fakes.
4. Fix or record F5 (test naming and vectors 1 and 2 coverage), F6 (master-list scope), and F7 (episode draw pattern).
5. Parent confirms F8 (LR step) and F4 (cross-process once-only enforced by the lease and marker).
6. Re-run the test suite after fixes, re-hash, and request another review.
