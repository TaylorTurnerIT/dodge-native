# RNG transition components integration r6: source review (r1)

Scope: read-only source review of `learning/runs/v2/RNG-transition-components-integration-luna-20261026-r6/` (`transition.py`, `fingerprints.py`, `rng_reference.py`, `test_transition.py`, `receipt.json`). Only CPU stdlib toy tests were run: `PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest -v` (Python 3.9.6), 5 passed. No torch, MPS, checkpoint deserialization, environment construction, real RNG reads, or ranking-campaign files were touched.

## Verdict

No blockers for the toy/preparation scope. Finding 1 must be closed in the production driver before any real transition run.

## Verified

- Source hashes match pins: `fingerprints.py` `6ef9cf3f…d61`, `rng_reference.py` `d302828e…3d`. `transition.py` and `test_transition.py` match receipt values.
- `EXPECTED_PARENT`, `ACCEPTED_PARENT_RECEIPT_SHA256`, and checkpoint SHA match the receipt's `accepted_parent_pins` and the `rng_reference.py` constants.
- Gate ordering is correct: source, parent-receipt, checkpoint, and RNG-reference validation (`transition.py:75-122`) all precede `session._started = True` (`:124`) and `restore_trusted()` (`:125`). The pending-reference test confirms rejection before mutation.
- Seed order python, numpy, torch CPU, MPS matches the contract (`:131-134`). CPU and MPS state digests are checked before the LR override (`:140-145`).
- Post-seed model/Adam comparison (`:146-149`) and LR-only exclusion logic (`:151-167`) match the contract.
- The after-reseed mutation test (`test_transition.py:157-173`) does exercise the detection path.

## Findings

1. **MAJOR**: `transition.py:14-16, 75-76, 124`. "No retry" is enforced only per `TransitionSession` object. Trigger: the caller catches a post-consumption error (for example `:141-149`) and calls `transition(session=TransitionSession(), ...)` on the same model and optimizer. Consequence: a second restore and reseed runs, which is the retry the contract forbids, and measured results could come from a retried attempt. Tests only reuse the same object (`test_transition.py:172-173`, `:208-209`). The driver needs a process- or run-scoped guard or a durable attempt marker.

2. **MEDIUM**: `test_transition.py:141-154`. The test name says "content hash stays", but `:153-154` compares the post-LR content fingerprint with a recomputation of the same post-LR state. It never compares pre-LR content. The branch at `transition.py:162-165` ("model changed after LR override" and "optimizer contents changed beyond LR") has no test. Deleting it leaves all 5 tests passing.

3. **MEDIUM**: `test_transition.py:88-105`. Expected CPU and MPS digests and the reference receipt are produced by `fingerprints.fingerprint` itself. The live-vs-reference comparison at `transition.py:142-145` is therefore only self-consistent. No test checks a real pinned measured digest, and the tensor path in `fingerprints.py:18-22` (`.detach().cpu().numpy()`) is not exercised. The predecessor demand for real pinned reference digests versus self-derived ones is still unmet.

4. **MEDIUM**: `transition.py:168-179`. The success return omits the six-seed vector and its SHA. Seed identity is reduced to the `pair_id` string. `constructor_init_seed` and `env_master_seed` are validated (`:20`) but never applied or recorded as evidence in this file.

5. **LOW-MEDIUM**: `rng_reference.py:82, 84`. Receipt fields are compared with `==`. Python's `True == 1` and `11.0 == 11` pass, so `replica` and `complete_seed_vector` need only be numerically equal, not type-exact as the caller arguments are at `:47-54`. The receipt SHA is pinned, so exploiting this requires a pinned receipt that already has the wrong types.

6. **LOW-MEDIUM**: `test_transition.py:188-198`. Only the vector-hash mismatch is tested. The study, replica, torch version, backend, checkpoint, parent-receipt, schema, and status-other-than-pending branches (`rng_reference.py:68-83`) have no tests.

7. **LOW**: `transition.py:104-108, 125`. The checkpoint is hashed at `checkpoint_path`, but `restore_trusted()` takes no path, so the restore source is not bound to the hashed file. The post-restore fingerprint check (`:126-129`) is the real content guard. The driver must bind the restore source.

8. **LOW**: `transition.py:158-167`. The LR value is never read back. The check only proves the Adam fingerprint changed. It fails closed, but `all(g["lr"] == controller_lr(arm, 397) for g in groups)` is cheap. A parent whose live LR already equals the start LR would also fail spuriously.

9. **LOW**: `transition.py:174`. The success status string "concrete state_dict fingerprints verified" is hardcoded. Only toy objects were exercised, so the string reads as a runtime verification it is not. Reword it or drop it.

10. **INFO**: `transition.py:46-61`. `validate_exclusion_controls` is not called by `transition()` and has no test. This is acceptable if it belongs to a future environment gate, but the receipt's `remaining_gates` does not list it.

11. **INFO**: `transition.py:10`. `OLD_CONTROLLER_PROVENANCE.saved_lr` `2.2203389830508474e-5` equals the new-formula value at u=24 (`3e-5-2e-5*23/59`). Nothing in code uses it, and the old controller source is not in this directory, so it cannot be checked here.

## Evidence limits

- Toy fixtures only. There is no torch import, so `torch.mps` seeding semantics and `get_rng_state` format are unverified.
- `stdlibderive.py`, cited at `rng_reference.py:28`, is not in this worktree. The canonical vector byte rule is unverified.
- The production `capture_rngpayload` callback and the trusted restore source were not reviewed. Both are listed as remaining gates.
- The real measured RNG reference is `pending_notrun`. It was not read.
- This is not runtime qualification.
