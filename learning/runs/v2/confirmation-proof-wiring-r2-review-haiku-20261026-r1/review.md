# Confirmation proof wiring R2: frozen source-only review

Scope: `learning/runs/v2/confirmation-proof-fixtures-luna-20261026-r2/` (worker.py, execute_once.py, build_registration.py, selection.py, test_runner.py, test_selection.py, receipt.json, source-hashes.json, tests.log, README.md). Source-only. No imports, no execution, no Torch/MPS/native/checkpoint/ledger/lease/marker access. Current R6 ranking result files not read.

## Verdict

No hard source blocker for the synthetic wiring. Two items to fix before the parent accepts confirmation proof wiring: finding 1 (P2, binding gap) and finding 2 (P3, exec-before-hash). Nothing is registered, launched, or opened, so these are pre-acceptance fixes.

## Hashes of reviewed bytes (sha256)

| file | sha256 | matches source-hashes.json / parent receipt |
|---|---|---|
| worker.py | 99591082986e512b7681b032562f3ab5f3a47228f1bbf807efb500051f968144 | yes |
| execute_once.py | 828f2aaccc30d58990eca578ca6bf1643ce2790d63c2e40300cec0bb25670591 | yes |
| build_registration.py | 623f4ae1d72aeb5cc1b9fe062ceab594000cffae29466da4d1a5220d635cd39a | yes |
| selection.py | d35614e5f3d65836f0b3943622701322297bc201a0d07a2e547f5bd2a2b64e66 | yes |
| test_runner.py | acbdf3234c38d6e0c9eba0f2b953082374d99978f9b3ca5cac1d19f993f3f03a | yes |
| test_selection.py | 836f8a9c222510012968fdfe2140e8a31b4b572722ae312691552dffb8fcc4f1 | yes |
| README.md | 7e8e93137defa30fe27ddfc1a1086b90fc296f2d6037d918937229f924bea3ce | yes |
| receipt.json | f4bca4ec3d28a112ab0fc4e2245e17dcd1e37d6027b81424f32244c5bbea434c | n/a (its own pins match) |
| tests.log | 3f2e6844739a1764f70469d99cc546d7685b2aec3852198b3a41d9e8a25527de | matches receipt tests_log_sha256 |
| source-hashes.json | 2ed60c912804f26eafe8494a19e197e8e3bda8c41f7fae86d0dd05e13bf39a87 | matches receipt source_hashes_sha256 |

R6 comparators (hashed, matched): `expanded-runner-final-parent-20261026-r6/worker.py` = da212582802e9119095b96057d38158d400d046128299ff1b845d420e236b162; `expanded-runner-final-parent-20261026-r6/execute_once.py` = e68567f0225fa2bbc49944c1fc28518250747be1e0dcf274c23586dbac79b09f.

## Verified (source)

- R6 to R2 diff is bounded. worker.py adds only the nested-proof block and `load_selection_validator` (lines 141-182). execute_once.py changes only the `importlib.util` import, the two confirmation call sites (lines 179, 319), and adds `validate_confirmation_worker` (lines 204-216). Inference body, RSS/MPS/heartbeat guards, one-shot marker, and receipt chain are unchanged.
- Order: confirmation preflight validation runs before the one-shot claim. `validate_confirmation_worker` at execute_once.py:179 is inside `preflight`, which runs before `atomic_json(marker, ...)` at line 238. Postflight re-validation at line 319.
- Locked winner and 348: worker.py:152-155 compares record fields to the registration and rejects winner 348. execute_once.py:77 collision check rejects a winner of 348 before claim, because the winner and incumbent output paths collide.
- Winner tie-break matches: selection.py:234 `min(UPDATES, key=(-mean, u))` equals worker.py:251 `sorted(key=(-mean, candidate_update))[0]`.
- Evaluator constants match `expanded-evaluator-publication-repair-parent-20261026-r4/expanded_eval.py`: cap 18000 (line 287), startup_frames 13 (line 296), objective `score_raw/65536 + alive/100 - 5*term` (line 320), score identity (line 319), death-cause rules (lines 303-316), performance keys and quarter means (lines 329-332), ranking seed base 0xD1000000 with 1024 seeds (line 241).
- Cap arithmetic: ranking 110592000 = 6 x 1024 x 18000; confirmation 73728000 = 4096 x 18000 (winner + 348, 2048 each).
- Test log lists the 32 names and `OK`. Parent receipt covers the same 32 tests and the same 7 hashes.

## Findings

### 1. P2, provenance binding gap (confirmation does not bind ranking proof to its own registration)

- Where: selection.py:132-133 (`_validate_result` takes `evaluator_sha`, `runtime_sha`, `manifest_sha`; body never uses them, confirmed by grep: only signature lines reference them). selection.py:245-248 records `evaluator_sha256`, `runtime_member_map_sha256`, `ranking_manifest_sha256` into the record. worker.py:141-171 (`validate_selection`) never compares these recorded values to the confirmation registration.
- Trigger: a ranking registration whose `source.evaluator_sha256`, `runtime.member_sha256`, or ranking manifest differs from the confirmation registration, but which is internally self-consistent (its outer receipt and results were produced against it). Replay passes and the record is accepted.
- Consequence: the confirmation winner can be validated against ranking evidence produced under a different evaluator, runtime member map, or cohort than the confirmation run uses. Checkpoint pins and candidate sets still match, so this is silent.
- Fix: in worker.py `validate_selection`, after replay, assert `record['evaluator_sha256']==reg['source']['evaluator_sha256']`, `record['runtime_member_map_sha256']==canonical digest of reg['runtime']['member_sha256']` (reuse `runtime_digest`), `record['ranking_manifest_sha256']==reg['cohorts']['ranking']['manifest_sha256']`, and `record['ranking_run_id']!=reg['run_id']`. Then either use the `runtime_sha` / `evaluator_sha` params in `_validate_result` or delete them.

### 2. P3, exec-before-hash in validator and worker loaders

- Where: worker.py:173-181 (`load_selection_validator`): `require_hash` at 175, `exec_module` at 178, hash re-check at 179. execute_once.py:204-216 (`validate_confirmation_worker`): hash at 207, `exec_module` at 210, re-check at 211/214.
- Trigger: the pinned file is replaced between the first hash and `exec_module`, or during execution.
- Consequence: attacker-controlled module code runs inside the supervisor or worker process before the post-import check fails. Post-check cannot undo execution. Threat is local write access, so severity is low, but the design claims pinned execution.
- Fix: read bytes once, verify sha256 on those bytes, then `compile` and `exec` from those bytes into the module namespace. Keep the after-import hash check as an extra guard.

### 3. P3, double-read after hash (same class)

- Where: worker.py:150-151 (`require_hash(p,pin)` then `read_json(p)`), worker.py:161-162 (`require_hash(ref['path'])` then `read_json(ref['path'])`). Field checks use the second read.
- Trigger: file changes between hash and read.
- Consequence: fields checked (`winner_update`, `ranking_results`, `candidate_update`, `checkpoint_sha256`) may not be the bytes the hash approved. The validator's own `read_pinned` reads once, so the two reads can disagree.
- Fix: use a single byte read for hash and parse, as `selection.read_pinned` does.

### 4. P3, test coverage gaps

- test_runner.py:16 disables `VERIFY_FROZEN_RUNTIME` and `VERIFY_PROPOSAL_CANDIDATES` in the launcher copy. execute_once.py:165 (frozen runtime/member/version check) and execute_once.py:166-169 (proposal candidate check) are not exercised by any test.
- No test tampers a ranking result file or the ranking summary before the claim (worker.py:161-165 path untested for confirmation).
- No test covers finding 1 (mismatched evaluator or runtime between ranking and confirmation registrations).
- No test tampers ranking artifacts after the worker runs, so postflight re-validation (execute_once.py:318-319) is untested.

### 5. P3, hash coverage gap

- `accept_benchmark.py` (imported by test_runner.py:103 and used to build the accepted benchmark wrapper) is not in source-hashes.json and was not in the parent's 7-file hash check.
- `test_heartbeat.py`, `test_actual_lease_keys.py`, `test_signal_assignment.py`, `test_signal_windows.py`, `test_supervisor_cleanup.py`, `test_worker_lifecycle.py` are present but unpinned and not in the 32-test replay. Their purpose in R2 is unexplained.

### 6. P4, provenance metadata inconsistency

- receipt.json and tests.log header say `Python 3.9.6`. Parent receipt cites `python/.venv/bin/python` and the request says 3.12. The parent `tests.log` has no interpreter header, so the version cannot be confirmed from source. Not executed here.

### 7. P4, path-form asymmetry (fails closed)

- selection.py:217-218 and 223-224 compare `str(Path(...).resolve())` against outer receipt `output_artifacts` paths, which execute_once.py:369-371 writes as unresolved `str(path)`. A symlinked `output_dir` would false-reject. Current `build_registration` resolves `output_dir`, so no live effect.

## Limits

- Source-only. Test results come from parent receipt and logs, not a re-run.
- Synthetic fake-process and synthetic JSON fixtures only. Not real ranking or confirmation outcomes.
- Timing compatibility with the accepted 16.3 s benchmark remains PENDING the parent gate. The projection is linear from the 64-episode, 2-repeat measurement times multiplier 2.0. Not evaluated here.
- Parent paired-bootstrap acceptance not reviewed (separate rule, per request).
- Worker runs with confirmation winner only after replay. Not re-verified against real R6 proof bytes.
