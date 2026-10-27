# Long D2 verifier redesign after the failed guard-repair stress (Opus, r1)

Scope: read-only design. Nothing here was implemented or executed beyond stdlib reads of
source and receipts. No ML/native import, checkpoint decoding, inference, training, stress
re-execution, lease or scheduler action took place. The r2 training authorization
(`postovernight-long-D2-r2-plan.json`, SHA `a08dfea9…6fce83`) is still unconsumed. No
experiment should start until the parent reconciles this design and a frozen review passes.

## 1. Facts (from source and receipts)

F1. The stress (`attempts/stress-01`) ran the frozen worker `verify` closure over the
current pins: 10091 files / 289887435 B in `full_pins`, 10111 controller sha calls /
292446815 B in total. There were two passes:

| pass | thread | wall s | thread CPU s | full_pins wall / CPU s | full gap s |
| --- | --- | --- | --- | --- | --- |
| 0 forced | MainThread | 0.4315 | 0.4279 | 0.3753 / 0.3730 | 0.4315 |
| 1 background | long-D2-inputs | 3.4319 | 0.4458 | 3.3824 / 0.3964 | 5.4592 |

F2. Pass 0 ran inside `g.start()`, before `stress.py` started the burn thread. So it is an
uncontended measurement. It is not evidence that a main-thread pass survives contention.

F3. Pass 1 started 2.0273 s after pass 0 started: the 2 s trigger plus a 0.0273 s trigger
delay. CPU use stayed about the same (0.446 s vs 0.428 s) while wall time grew about 8×. The
pins are page-cache-hot (pass 0 ran at about 770 MB/s). In this synthetic workload the extra
~3 s is time the thread spent runnable but not running. It matches `hashlib`/`read` releasing
the GIL and then waiting for the default 5 ms switch interval to get it back from a Python
thread that holds it continuously.

F4. The gap requirement in `Guard.full_check` is `end_current - start_previous <= 5`, with
a 2 s trigger. That leaves at most `3 - trigger_delay` seconds for one pass. The measured
uncontended pass (0.43 s) fits easily. The contended background pass (3.43 s) does not.

F5. The protected learner already calls the controller-owned `Guard` at fine granularity:
- `ppo.collect_rollout` calls `check_guard` 3–5 times per rollout step.
- `ppo.ppo_update` calls it 4 times per minibatch and twice per KL minibatch.
- `dev_eval.evaluate` calls it once per environment step and per batch.
- `Learner.update_once`, `checkpoint`, `evaluate_checkpoint` and `run_schedule` call
  `guard.check(force=True)` at every update, evaluation and checkpoint boundary.

`Guard.check()` with `force=False` currently does only the latched-failure and deadline
checks. `Guard` is controller code, not protected learner bytes.

F6. The independent monitor thread (`long-D2-guard`, 50 ms wait) samples the lease and
resources at ≥0.15 s age with a 0.5 s cap, and latches `now - last_full > 5`. Its sample gaps
stayed small in both settings: 0.221 s in the stress and 0.250 s in the production r1 run
(6039 samples). It does not hash.

F7. Production r1 for comparison:
- 51 updates; consecutive metric rows 19.27–28.70 s apart (mean 20.64).
- Peak RSS 1.00 GB, MPS 2.46 GB, against a cap of 6442450944.
- Checkpoints are about 8.07 MB.
- `long-worker-result.json` records `cancelled` / `Cancellation latched` while the guard
  failure is recorded elsewhere. This is the precedence defect the r2 plan targets.

F8. The inner supervisor (`supervise_owned`) builds a `Guard` with a pins/capsule/origins
`verify` and its own background thread. Its main thread only sleeps, waits and polls the
channel. It has no ML load. Its `authority()` calls `guard.check()`.

F9. P2 (`DEFERRED-CANCEL-PRIMARY`): `primary_error` returns `guard.failure` only when
`guard.failure_at <= ACTIVE.first_at`. Otherwise it returns its `error` argument unchanged.
When a direct cancellation was recorded at t=1 under `DEFER`, the main thread later raises
the guard error (t=2), and that error is the argument, the function returns the later guard
error. Retained probe: required `cancelled`, actual `safety_stop`. A second defect:
`ProcessLatch.first_at` is one field shared by SIGALRM and the cancellation signals, so no
per-kind first timestamp exists.

F10. The plan and protocol forbid ML imports during preparation. The protocol's guard
section names `background_full_input_trigger_seconds: 2.0`.

## 2. Hypotheses (not proven)

H1. The production r1 failure (gap 5.005 s at about 1066 s, with no per-pass timing) had
the same cause as the stress: the background verifier was starved of the GIL by
Python-level work on the ML main thread. This is supported only by analogy. Production
holds the GIL less steadily than the synthetic burn because torch/MPS/Rayon release it,
so the real tail is unknown.

H2. A pass that runs on the ML main thread, between learner callbacks, takes about the
uncontended 0.4–0.5 s because no other Python thread is CPU-bound. The monitor thread is
light and mostly sleeping. MPS/Rayon/torch worker threads do not hold the GIL. This is
unmeasured under real ML load: page-cache eviction under unified-memory pressure and
residual Python threads are possible.

H3. Most stretches between protected-learner callbacks are milliseconds long. The largest
expected uncooperative stretches are:
- worker startup imports (`torch`, `numpy`, `dodge_rl`, MPS availability);
- `check_frozen`, `validate_transition`, `Learner.initialize`;
- `make_state`/`save_checkpoint` of about 8 MB (bounded by forced checks on both sides);
- `capture_rng`, `tree_fingerprint`, `deepcopy` in `evaluate_checkpoint`.

None of these durations is measured.

## 3. Options

### A. Cooperative main-thread verification at existing callbacks (CHOSEN)

When `Guard.check()` runs on the worker's main thread and `now - last_full >= 2` (the same
trigger), it runs the same `full_check` synchronously. The worker's background hashing
thread is removed. Nothing else changes:
- the `full_check` body: gap requires before and after, row schema, components and pins;
- forced checks;
- the independent ≤0.5 s resource/lease sampler and the ≤5 s staleness latch, which keep
  running throughout, including while a pass is in flight.

A long uncooperative call is not hidden. If any stretch makes
`now - last_successful_start > 5`, the monitor latches the failure with its true
`failure_at`. The main thread raises it at the next callback.

Cooperation budget: `2 + L + D <= 5`, where L is the longest stretch between callbacks after
the trigger is due and D is the pass duration. With D = 0.43 s, L ≤ about 2.57 s.

Worker startup imports occur inside the protected worker body between `guard.start()` and
the first forced check, so no callback can be added there. Instead, during that window
only, a single `sys.meta_path[0]` finder whose `find_spec` always returns `None`, after
calling `guard.check()`, yields cooperative points on every submodule import. It is removed
right after the first post-import forced check. It cannot change resolution (it never
returns a spec), but it is a new mechanism and is flagged for review.

Costs and tradeoffs:
- The ML thread stops about D/2.4 ≈ 15–20% of wall time to verify, so fewer updates fit in
  7200 s. Hyperparameters, Schedule and `run_schedule` bytes are unchanged. Schedule already
  learns walls from measured update and evaluation durations.
- A native call that wedges past about 2.6 s now fails honestly instead of being covered by a
  background thread. That is the intended behavior, and it can consume the single-use run.
- Safety does not depend on any GIL-scheduling assumption: a pass no longer competes with
  the thread it was competing with.

### B. Dedicated verifier process (NOT chosen now)

A separate GIL would remove CPU contention between the verifier and the ML thread. A
faithful version needs all of the following:

1. Legacy `check_frozen` builds runtime/architecture/PPO metadata by importing torch, numpy,
   `dodge_rl.models.teacher` and PPO config, and by checking MPS availability. The child
   must either:
   - (a) do those same imports: a second torch/MPS process with extra RSS and possible
     Metal init, which needs an RSS row per role under the existing cap; or
   - (b) receive the metadata from the worker. That is not independent and would amount to
     a cached fixture, which is forbidden.
2. Origin checks need the worker's live `sys.modules` table. The worker must snapshot it on
   its main thread each pass and send it over typed, immutable IPC (sequence number, t0
   hex, identity SHA, per-module path). The child hashes those files and compares them to
   the identity. A stale or missing snapshot is a failure.
3. Lifecycle: the child is spawned with the same registered interpreter (`sys.executable`
   realpath and SHA bound in the identity; the system-Python vs uv-Python monotonic epochs
   differed during preparation, so mixing interpreters invalidates every timestamp). It
   gets an inherited socketpair and the t0 handoff check (`t0 <= LAUNCH <= now`), and must
   be ready before ML imports (startup verification) and after them (origin binding).
   Each pass is a request/response. A forced barrier waits for an explicit pass-complete
   response whose start and end use the shared monotonic clock. The worker monitor checks
   liveness at ≤0.5 s.
4. Parent disappearance: macOS has no `PR_SET_PDEATHSIG`, so the child needs
   `getppid` polling or kqueue `NOTE_EXIT`.
5. Teardown: direct-child `waitpid` within the shared earliest-failure+10 pool, with no
   new budget. Teardown comes after the final IO observation, so the monitor is never
   closed before final IO. The child's timing rows must be persisted (or explicitly
   recorded as lost) under the worker's write permission.
6. Ownership: process-group and ACK roles must extend to a fourth process.

Even so, the IO and page-cache behavior of a 290 MB re-hash every 2–3 s next to MPS
training is unmeasured. Process isolation gives no performance guarantee without a new
bounded stress. This is a much wider surface, it was explicitly excluded by the r2 plan
without new evidence, and the evidence available does not need it. Kept as the fallback if
A's production telemetry shows callback stretches that cannot be fixed.

### C. Other simpler options (rejected)

- A smaller `sys.setswitchinterval`: global interpreter tuning with no bound. It would
  still lose to long GIL holds on the ML thread.
- A background thread "only when main is late" (hybrid): this is the adaptive trigger, and
  it brings contention back exactly when it matters.
- A lower trigger, a hash cache, mtime checks or fewer pins: forbidden.

Option A is already the simplest option that removes the measured mechanism.

## 4. Primary-outcome ordering design (P2)

Each process gets an append-only event ledger `life.EVENTS` with entries
`(at, seq, kind, role, detail, outcome)`. Events are recorded at their source:

| event kind | recorded by | timestamp | outcome |
| --- | --- | --- | --- |
| `direct_signal` | `ProcessLatch.record`, per signal number, with the latch phase at receipt (NORMAL/DEFER/FAILURE) | receipt time | `cancelled` |
| `alarm` | `ProcessLatch.record` for SIGALRM | receipt time | `wall_guard` |
| `deadline` | deadline observation | observation time | `wall_guard` |
| `guard_failure` | the monitor latch, a cooperative/forced verify, or a sample | `failure_at` | the Stop's outcome |
| `main_exception` | the `Stop` constructor (not catch time) | creation time | `failure_outcome(error)` |
| `peer_first` | executor ACK | `first_monotonic_hex` | carries the first event's kind, role and outcome |

`ProcessLatch` keeps per-kind first timestamps (`first_cancel_at`, `first_alarm_at`) and also
keeps `first_at`. Selection: primary = min over `(at, seq)`. A signal does not lose to a
later error because it was deferred: DEFER delays raising, not ordering. The ordering of a
signal relative to failures:
- A signal with `at` > `POOL.first` (the earliest known failure, local or from any ACKed
  role) is labelled `cleanup_phase_signal`. It is secondary, and no claim is made about who
  sent it.
- A signal recorded before every failure is the primary `cancelled`. It is described as a
  "direct signal N, sender unrecorded", never as "user cancelled".

Across processes, the worker, inner and outer each keep a local primary and adopt the
global first from the ACK. The outer verdict uses the global min. Failure and ACK messages
gain `first_kind`, `first_role` and `first_outcome`. All roles must have the same
registered interpreter or the result is an identity failure.

`record_primary_failure` then becomes: compute the selection once at failure latch time.
Later errors append to `secondary_failures` and never rewrite the primary.

## 5. Limits and required future validation

- The stdlib stress can only show that A removes the synthetic convoy and that its
  cooperation arithmetic holds. It cannot measure the production stretches between
  callbacks. Telemetry records the longest stretches and their caller frames. The r2
  run is the first production measurement, and it can fail honestly on a stretch longer
  than about 2.6 s.
- An optional ML-import timing probe (imports only; no checkpoint, inference or training)
  would reduce that risk. It requires new user authorization, because preparation forbids
  ML imports.
- No claims about p99.9 or population tails. Only a bounded sample with actual counts and
  maxima is reported.
- Status: the design is complete for parent reconciliation. It is not implemented,
  validated or reviewed.
