# Critic diagnostic runner r3 — fresh readonly review

Reviewer: Haiku 5.5 (review sub-agent). Scope: frozen r3 source, registration-r3 and pin, restoration evidence, rehearsal evidence. No target, source, registration, ledger, checkpoint, native, model, or test execution. Only this directory was written.

## Verdict

Non-blocking. One medium-low finding (unpinned bytecode in the frozen runtime) and three low notes. None of them blocks the parent's automatic launch, but the parent should decide on the bytecode item before launch because it touches frozen identity.

## Verified

- External registration digest: `registration-r3.json` SHA256 = `612fd759a9c135ec939646e19686f3ab27d94c4ae8a3843d20046b390aa2188e`, matches the brief.
- `registration-r3-pin.json` SHA256 = `5c7c2e99a4e821846f460fdb0334cc8ad6be66ac929d2bc51a5e5d45b6cecb96`; it records the registration digest above, `run_seed` 3192039780, `pins_checked` 13563, and `actual_worker_launches` 0.
- Registration fields match `runner.py` constants: `limits` equal `LIMITS`; `config_sha256` = `CONFIG_SHA`; parent sha256 = `PARENT_SHA` at the accepted D1 path; native sha256 = `NEW_NATIVE_SHA`, old = `OLD_NATIVE_SHA`; `runtime_versions` python 3.12.15, torch 2.14.1, numpy 2.5.4; `expected_lease` run_id `critic-diagnostic-D2-20261025-r2` matches `run_id` and output name; output directory is under `learning/runs/v2`; `diagnostic_only` true, `training_eligible` false. Pin count 13563 matches the parent claim. No `__pycache__` or `.pyc` path appears in the pin set.
- Source/read hashes: `runner.py` 48bde41f4cc71b2ffa973b9cc61da5ea1cee175ca36b4344d520d5765d0699f1; `execute_once.py` 6d935fd6081e84bca1b4b22f16573494dd520f7109c65eb46b4e3a5df917f903; `test_contract.py` d8d98676b428d91d53ad11fd857f6737e8d320ffaf48da83ff25e2224768218d; `test_torch_restore.py` faf0c55671fb304deb5f5b0d7720ec502826fa1da675c5032395279c0049b9a9; `startup_rehearsal.py` a60d484843531cbae1e1f0cf35bed14bfb5ef543fb749acf57c417cd5571c711; `implementation-result.json` 7a8f02bd311707d098c8e11b82eac750fc3140beea8ffefedb60fdd9df5a6562; `startup-rehearsal-result.json` 0d7a8e2d360a6fce4cce41224457bfc79f2c67d89765a20d4fc50941ab80bb16.
- Launcher (`execute_once.py`) read in full: one-use `launch-marker.json` written before subprocess; worker launched with `start_new_session=True`; raw-zero outer and worker exits required; postflight `load_registration` re-run after worker exit and before acceptance; `owned_group_absent` guard prevents re-signaling a reaped group in the normal path; `publication_phase` handler raises `Cancelled` so late signals yield a nonzero exit and a separate `publication-failure.json`.
- Runner (`runner.py`) read in full: 48 update journal and 3x64 development cohort checks (`validate_outputs`), inclusive `<=1680` worker elapsed check, `fingerprint` typed tree with type-tagged mappings/lists/tuples/arrays/scalars (dict vs OrderedDict tags are canonicalized as `mapping`; keys, scalar types, bytes, dtype and shape are retained), `mismatch_paths` for diagnostics, entry restoration saved before the equality gate, and before/after training-state equality around evaluation.
- Rehearsal: `startup-rehearsal-result.json` shows model, Adam and RNG restored SHA equal to expected, `environment_created` false, `gradients_or_updates` false. Recorded peak RSS and MPS are sampled values, not continuous peaks; the parent already acknowledged this.

## Prior findings disposition

- r1 P1 (late publication cancellation swallowed): fixed. The active handler and separate `publication-failure.json` with nonzero exit remain present in r3 `execute_once.py` (lines 148–158, 244–259).
- r1 P2 (postflight re-signal of reused group): fixed. `owned_group_absent` guard at lines 206 and 189 is present.
- Dict vs OrderedDict tag failure: fixed by canonical mapping framing. Content checks were not weakened: keys, scalar types, tensor bytes, dtype, shape and list vs tuple remain in the digest.
- Haiku restoration audit (missing components, no comparator tests): components are persisted before the gate; `test_torch_restore.py` and `test_contract.py` exist. I did not run or fully read the test files in this pass; I verified only their hashes.
- Haiku Adam advisory (`load_state_dict` adopts checkpoint options): parent verify_restoration was reported to check those options. I did not read `verify_restoration.py` in full in this pass.

## Findings

### 1. Unpinned bytecode inside the frozen runtime (medium-low, non-blocking)

- File/line: `execute_once.py:138-139` (`load_registration` exclusion), `runner.py:138-139` (`actual` set excludes `__pycache__` and `.pyc`).
- Trigger: `runtime/dodge_rl/__pycache__/*.cpython-312.pyc` and `runtime/dodge_rl/models/__pycache__/*.pyc` (five files) exist under `learning/runs/v2/critic-diagnostic-parent-prepare-20261025-r1/runtime/`. None is in the 13563-entry pin set. The worker runs with `-B` and `PYTHONDONTWRITEBYTECODE=1`, which stops writing but not reading. I checked the five pyc headers: flags 0, source mtime and size match the pinned sources, so CPython's timestamp check would accept them and load their code without any hash check.
- Consequence: the frozen runtime identity covers pinned source bytes, but the executed bytecode is not pinned. If a pyc differs from its source (stale build, or tampering that preserves mtime and size), the worker runs code the registration does not identify. I did not decode the pyc bodies, so I have not shown that they differ.
- Recommendation: before launch, either remove the `__pycache__` directories inside the runtime and re-pin, or pass an empty `sys.pycache_prefix`, or pin the `.pyc` files. Any of these changes the registration digest, so it needs a re-register. The parent should decide whether the extra cycle is worth it.

### 2. Budget comparisons are strict, not inclusive (low, conservative)

- `runner.py:281,292` and `execute_once.py:162,179,194,199,202,239` use `<` for the 1680 s work and 1800 s total budgets. The brief says inclusive. Strict is the stricter direction (fails at exactly the boundary), so it cannot admit an overrun. Note the mismatch; `validate_outputs` (line 64) uses inclusive `<=` for the worker value, so the two checks disagree at the boundary only.

### 3. Late signal after `execution-result.json` = passed (low)

- `execute_once.py:219-260`. If a signal arrives after `save(execution-result.json)` with `status: passed`, the handler raises `Cancelled`, `publication-failure.json` is written and exit is 1. The primary receipt still says `"status": "passed"`. Acceptance depends on exit 1 and the failure receipt, not on the primary receipt. The code comment ("primary receipt remains untouched") is wrong for this window. Parent acceptance must check the exit code and absence of `publication-failure.json`, not the status string.

### 4. Peak RSS and MPS are last-sample values (low, evidence limit)

- `runner.py:285-290,445-446`. `peak_rss_bytes` and `peak_mps_driver_bytes` are the last sampled values, with no sample at finalization. `ru_maxrss` is monotonic, so an RSS spike after the last sample is missed; MPS is current allocation, not peak. This is the limit the parent already acknowledged. The actual campaign's Guard is the only enforcement; rehearsal numbers are not continuous peaks.

## Evidence limits

- I did not execute tests, startup rehearsal, the launcher, the worker, or MPS. Test and rehearsal results were read as retained artifacts and are not independent qualification.
- I did not read `test_contract.py`, `test_torch_restore.py`, `verify_restoration.py`, `restoration-validation-result.json`, or `haiku-audit-reconciliation.json` line by line. Their hashes are listed only where recorded above; the rest are not claimed.
- Torch/NumPy site-packages are identified by version string only (registration `runtime_versions`), not by hash. Interpreter binary is pinned by SHA via the pin set. This is an identity boundary the parent accepted; I did not verify the site-packages contents.
- `runner_dir` is on `sys.path` (script directory) ahead of stdlib and site-packages; currently it contains no stdlib-named modules. Not a finding in the current directory state.
- No runtime qualification is claimed. Historical best development cohort (for context, not evidence of r3): Q1 = 648.25, Q4 = 4508.8125, mean = 2240 frames.

## Gate

No blocking finding. Parent may launch the corrected diagnostic per its own rules. Finding 1 should be resolved or consciously accepted first.
