# Source-only review: independent heartbeat sampler, parent r2

Scope: `worker-independent-heartbeat-parent-20261026-r2/` (worker.py, test_heartbeat.py, test_worker_lifecycle.py, receipt.json, tests.log, tests-first-attempt.log, worker.diff).

Verdict: **No blocker in the heartbeat scope.** The independent sampler thread does publish heartbeats without depending on `check_guard`, and it fails closed on the stated conditions. H3 is closed for spans that release the GIL. It stays open for GIL-held native spans, as the receipt already states. Six non-blocking findings below (one Medium, five Low). **No launch clearance.** This review does not cover the supervised signal-window repair, which is still active and outside worker scope.

## Method and limits

- Read-only. Nothing imported, executed, or run. No Torch, MPS, native, checkpoint, game, lease, marker, or shared-state file touched.
- Hashes via `shasum -a 256`. Test results taken from `tests.log` and `tests-first-attempt.log` as text. Not re-run.
- Not in this directory, so not reviewed: `execute_once.py` (outer stale/cap monitor), `expanded_eval.py` (evaluator `check_guard` placement, device selection), `build_registration.py` (whether `limits.startup_grace_seconds` / `guard_poll_seconds` are set), the frozen runtime (whether `psutil` is pinned), torch's MPS API surface.

## Source hashes

| file | sha256 | receipt match |
|---|---|---|
| worker.py | 7fa452dc0f3152d131e8244e97b9b786ca995d9763f99e422bc0c4db06e77b6c | yes |
| test_heartbeat.py | 9d2b95d21f5d15872b0c30982a2313630c25e4de099e2e3964e169c773ec7874 | yes |
| test_worker_lifecycle.py | d1dc82c114770bb891270bf7afbe13b7613481b52be245c73ab01d10b043d159 | yes |
| worker.diff | ce59b69fdaa37e6a81db6c9e822b3a0d0dec1ab161091ad0c8efa2c574f559b3 | yes |
| tests.log | 429cc6a2cd429ca0c4b5f91340df0ca29db1396ceb9687512d55e6d47691192a | yes |
| tests-first-attempt.log | bccab0d012f5f0ce138d9721ebafb49c7773ffef219e9724ffd14055a2a9d0b4 | yes |
| expanded-runner-integrated-parent-20261026-r5/worker.py (predecessor) | 2b5d25d07c671671e6f9a4fb2c976b02af2cb8372ace30ad2d05544bb18a83e4 | matches review.md pin |
| expanded-runner-integrated-parent-20261026-r5/test_runner.py (lifecycle fixture source) | 6b1c1ec9f289587c3520c962dfee65b82cebc7017bb075ecdb351cf1d922ec73 | matches r5 review.md pin |

Test status: `tests.log` shows 8 tests, OK. `tests-first-attempt.log` shows the sequence-race FAIL (`6 != 7`) that the repair targets.

## H3 status (the claim under review)

Implemented as claimed:

- Sampler loop publishes via `worker_guard` every `min(0.2, guard_poll_seconds)` (worker.py:109-121, :119). It does not depend on evaluator `check_guard` calls.
- Heartbeat sequence continues monotonically: the synchronous first sample returns `0→1` (worker.py:187), sampler starts at `initial_sequence=1` (worker.py:188), and the sequence is updated under `self.lock` (worker.py:117-118).
- Thread never imports torch. It reads `sys.modules.get('torch')` only (worker.py:92). It does do `import psutil` on each tick (worker.py:70), which is not torch.
- CPU backend returns `(0,'runtime',False)` without touching torch (worker.py:91).
- Partially imported torch (`__spec__._initializing`) reports `startup` with 0 bytes and is bounded by `startup_grace_seconds` defaulting to 12 s (worker.py:93, :115).
- MPS unavailable, or a read error, is `None` and fails closed (worker.py:95-99, :116, :75).
- Sampler stop is bounded at 2 s and re-raises a sampler error (worker.py:125-128).
- Final publication path: `sampler.check()`, then the final MPS reading must be non-None, `runtime`, initialized, and `<= LIMIT_MPS`, then `sampler.stop()`, then `exclusive_json` (worker.py:233-239).
- Every exit from `run()` after the sampler starts goes through `finally: sampler.stop()` (worker.py:241-242).

Residual, explicitly stated: a GIL-held native call starves the sampler. The outer monitor then sees a stale heartbeat and kills the group. This is fail-closed, not false success.

## Findings

**F1. Medium. worker.py:70-74, :81-88. `ps` fallback can false-stop a healthy run.**
- Trigger: `psutil` not importable in the runtime. Each 0.2 s tick then runs `subprocess.run(['ps',...], timeout=0.2)` from the sampler thread (~5 forks/s of a multi-GB process). Under CPU or memory pressure `ps` exceeds 0.2 s, or raises. `process_rss` returns `None` (worker.py:88). Line 74 raises `worker RSS unavailable`.
- Consequence: sampler `_run` catches it (worker.py:120-121), thread exits, heartbeat stops, outer monitor kills a healthy benchmark. Fail-closed, but it wastes the one-shot budget.
- Not verifiable here: whether `psutil` is pinned in the frozen runtime. If it is, the fallback is dead code and this reduces to Low.
- Fix: pin `psutil` in the runtime pin set, or tolerate a bounded run of transient `None` readings (for example 3 consecutive) before failing, and drop the per-tick subprocess.

**F2. Low, pending evaluator review. worker.py:234-237 and :91-99. Publication gate proves MPS is available, not that MPS was used.**
- `initialized` is `True` whenever torch is present, `is_available()` is true, and `driver_allocated_memory()` returns without error (worker.py:95-97). It does not show that the evaluator's tensors ran on the MPS device. A zero-allocation reading passes.
- Consequence: a run registered with `backend='mps'` whose evaluator silently ran on CPU can publish a benchmark bundle that looks MPS-backed. Severity depends on how the evaluator selects its device, which is not in scope.
- Fix: have the evaluator record the device it used and check it against `reg['runtime']['backend']` before publication. Rename `initialized` to what it measures, or add the device check.

**F3. Low. worker.py:241-242 with :127-128. `finally` can replace the in-flight exception.**
- Trigger: evaluator raises while the sampler also has a recorded error, or while `stop()` times out. `stop()` calls `check()` and raises inside `finally`, which replaces the original exception (chained only as `__context__`).
- Consequence: wrong diagnostic. Both paths still fail closed and no success bundle is written, so no false success.
- Not covered by tests: the lifecycle test (test_worker_lifecycle.py:58-61) only has the evaluator fail, with the sampler healthy.
- Fix: in the `finally`, stop without re-raising when already unwinding, or attach the sampler error with `add_note`.

**F4. Low. worker.py:106, :115, :188. Startup grace clock covers all pre-torch time.**
- `self.started` is set at sampler construction, before evaluator import (worker.py:188). Any work the evaluator does before importing torch (module loads, JSON reads, pin checks) counts against the 12 s grace. A cold torch import on macOS near that bound can false-stop.
- `float(...)` on `startup_grace_seconds` has no bounds check (worker.py:115). An absurd registered value would disable the startup bound. The registration is hash-pinned, so this is parent-controlled.
- Fix: measure cold-import wall time on the target machine and set the grace from that. Bound the registered value.

**F5. Low. worker.py:116, :124, :233-239. Sampler failure is observed only at the next `check` point, and heartbeat goes silent before publication.**
- A sampler error (for example MPS unavailable or RSS over cap) does not interrupt the main thread. The evaluator keeps running until its next `check_guard`, or the outer monitor kills the group after the 2 s stale window. The in-process diagnostic is lost to the outer kill.
- `sampler.stop()` at worker.py:238 ends heartbeats before `exclusive_json` at :239 and before process exit. Heartbeat is silent for the duration of the fsync and teardown. This is only safe if the outer monitor treats a published result or clean exit as terminal and not stale. That behavior is in `execute_once.py`, not reviewed.
- Fix: confirm the outer monitor's terminal-state handling. Optionally write a final `state: stopped_clean` heartbeat before `stop()`.

**F6. Low. Test coverage and hygiene.**
- `test_heartbeat.py:55-58` is named "atomic", but it only re-runs the live test and checks CPU does not import torch. Nothing tests atomicity.
- `test_heartbeat.py:46-54` pops `torch` and restores it only on success, with no `try/finally`. A failure leaves `sys.modules` changed for later tests.
- Test-order dependency: `assertNotIn('torch', sys.modules)` (test_heartbeat.py:57) depends on test ordering across modules.
- Not covered anywhere: final MPS publication gate (worker.py:234-237), `ps` timeout path (F1), `stop()` 2 s timeout (worker.py:126-127), startup→runtime transition, and `startup_grace_seconds` override.
- `test_worker_lifecycle.py:13` loads its fixture from the sibling `expanded-runner-integrated-parent-20261026-r5/`. If that directory moves or is pruned, the test breaks.
- Fix: add tests for the uncovered paths above, wrap the `sys.modules` mutation in `try/finally`, and rename or remove the "atomic" test.

## Resolved since first attempt

- Sequence race (`6 != 7`, `tests-first-attempt.log` line 23): test_heartbeat.py:20-23 now calls `sampler.stop()` before reading the heartbeat file. The `calls[-1]` snapshot is taken after join, so it is consistent. Verified by reading. Fix is sound.
- Exception path now stops the sampler on import, inference, and publication failures (worker.py:193, :241-242). Verified by reading and by `test_inference_exception_stops_sampler_and_preserves_no_success_bundle`.

## Coverage of requested checks

- Real API shape and frozen keys: unchanged in the diff except the `initial_sequence` parameter and the `startup_grace_seconds` / `_initializing` additions (worker.diff hunks 1-3).
- Thread startup and import readiness: F4.
- Races and lifecycle: sequence race fixed; F3, F5.
- Exception handling: `finally` covers all post-start exits; F3 for masking.
- Resource guards and false-success publication: F1, F2.
- Source pin coverage: every guard re-hashes registration, worker, evaluator, launcher each tick (worker.py:59, :63). Verified.

## Limits

- Source-only. Nothing executed. Test results read from logs.
- Outer monitor, evaluator guard placement, registration limits, runtime `psutil` pin, and torch MPS API names not verified.
- GIL-held native spans can starve the sampler; the outer monitor's 2 s stale kill is the only backstop. Stated, not solved.
- No launch authority granted or implied. Supervised signal-window repair still active, outside this scope.
