# Long-D2 one-shot failure: guard timing diagnosis (Opus, read-only)

Status: **complete diagnosis, plan only.** No code, capsule, config, protocol, ledger, docs, checkpoint metadata or log was edited. Nothing was imported from ML/Torch/native/project code, no checkpoint was deserialized, and no inference, training, retry or model test was run. Analysis used only stdlib `json`/`statistics`/`hashlib` over saved artifacts. The input hashes are in `input-hashes.json`.

Run: `v2-m3-long-D2-20261024-r1`. Frozen pins verified by hash during this read: controller `long_d2.py` a8f1e9a9…2bd1a, executor 6ab9555a…4ab8b52, protocol `postovernight-long-D2-r1-protocol-r4.json` 66cc36ef…6ab501, capsule identity.py 50775b2e…2a4a053 (byte-identical to the current `python/dodge_rl/identity.py`).

Short paths used below:
- `L` = `learning/runs/v2/postovernight-long-D2-prepare-r4/capsule-final/learning/runs/v2/postovernight-long-D2-prepare-r4/long_d2.py`
- `X` = the executor `long_d2_executor.py`, in the same directory as `L`
- `C` = `learning/runs/v2/postovernight-long-D2-campaign-r1/`
- `O` = `learning/runs/v2/postovernight-long-D2-execution-observer-r1/`

## 1. Verified facts

| Fact | Value | Source |
|---|---|---|
| Launches | 1 | `O/start.json` `actual_command_launch_count` |
| Outer raw wait / returncode | 256 / 1 | `O/raw-wait.json` |
| UTC | 19:34:54.697450 (popen) → 19:52:41.455141 (reap) | `O/start.json`, `O/raw-wait.json` |
| Wall | 1066.7562106660334 s | `O/raw-wait.json` |
| Protocol requirement | `guard.worker_full_input_hash_max_seconds: 5.0`, `full_hash_at_update_and_eval_boundaries: true` | protocol r4 `guard` |
| Worker latched failure | `Stop('Full input verification gap exceeded 5s')`, raised from the monitor thread at `L:507` (traceback) | `C/long-worker-result.json` `traceback`, `worker_resources.latched_failure` |
| last_full | 491748.428956583 | `worker_resources.last_full_verification_monotonic` |
| maximum_full_input_gap | 5.005385208001826 | same |
| first failure | 491753.434364083 (= last_full + 5.0054075) | `inner-failure.json` |
| last resource sample | 491753.302113083; max sample gap 0.2500741249532439 | `worker_resources`, `C/worker-resources.jsonl` (6039 rows) |
| RSS / self-peak / MPS | 1001635840 / 1001701376 / 2459009024 (each below its separate cap) | `worker_resources` |
| Phase updates | 51 complete (inherited 48, cumulative 99); new Adam 6528, cumulative 12672, partial 0 | `counters` |
| Partial rollout | 13312 decisions / 53153 frames (update 52, unfinished) | `execution-result-final.json` retained-failure check |
| Failure checkpoint | `checkpoint-000017-failure.pt` sha ec1796cd…; complete_update true, evaluated false, parent-ineligible | `failure_checkpoint` |
| User or lease cancel | none: lease `cancel_requested=false`, observer `forwarded_cancellation=[]` | `inner-failure.json`, `postovernight-long-D2-execution-r1/acceptance-receipt.json` |
| Acceptance | `accepted=false`, `cleanup_complete=true`; reap 0.348 s after first failure; outer, inner and worker groups positively absent | acceptance receipt; `execution-result-final.json` |

The facts that 4 evaluations ran (entry/16/32/48), latest score 8.0859375, alive 1093.03125, 64/64 deaths with no caps, and that entry restoration/control matched exactly (64 rows, 9 fields, model/Adam/RNG) are in `entry-control.json`, `entry-restoration.json` and `execution-result-final.json`. I checked them only at the key level. The reward, seed and counter audit belongs to the parent Codex audit.

Discrepancy to note: the brief says the full pins are "~180 MB". The frozen pre-run receipt `postovernight-long-D2-prepare-r4/hash-volume-receipt.json` says `full_pin_count 9870`, `full_pin_bytes 228611008` (≈218 MiB), `full_pin_hash_seconds 0.3268`, `future_ML_runtime_measured false`. Use 228,611,008 bytes.

## 2. What the source actually does (Q1)

`Guard.full_check` (`L:457-473`):
- Triggers when `at - last_full >= 4` (`L:461`). The background `verify_monitor` polls every 0.05 s (`L:515-522`).
- Pre-check `at - last_full <= 5` (`L:464`). Then `self.verify()`. Then `gap = end - last_full` (`L:469`), recorded into `maximum_full_gap` **before** `require(gap <= 5)` (`L:470-471`). Then `last_full = at`, which is the **start** of the completed pass (`L:472`).
- It holds `verify_lock` only. Resource sampling uses a separate `lock`, so `ps` sampling is not blocked by hashing (`L:446`, `L:475`).

`monitor` (`L:501-511`) polls every 0.05 s and raises when `clock - last_full > 5` (`L:507`). This happens while a pass is still in flight, because `last_full` only advances after a pass succeeds.

The `verify()` actually used by the worker (`L:844-851`) does more than hash pins. After imports it does all of the following:
1. `verify_files(pins)`: 9870 files, `is_file` + 1 MiB chunked SHA-256 (`L:65-73`, `L:115-117`).
2. `assert_readonly_capsule`: for each of 160 manifest files, a stat of the file and of **every parent up to root**, plus two full `rglob('*')` walks (`L:174-186`).
3. `identity.check_frozen` → `build_identity`: re-reads the protocol, qualification JSON and contract, rebuilds `source_inventory` (75 legacy sources) and `foundation_identity`, then re-hashes the identity document (capsule `identity.py:151-188`).
4. `check_module_origins`: two hashes per loaded `dodge_rl.*` module (`L:189-204`).

The 0.327 s pre-run receipt measured only item 1, on an idle machine, with no ML load.

Forced passes: `check(force=True)` → `sample(force=True)` → `full_check(force=True)` (`L:450-455`, `L:494-495`). Every boundary force-check (`L:600-719`, `L:749-758`) runs a full pass **on the main thread**, pausing training, and resets `last_full`.

Answers:
- **`last_full` means the start of the last successful pass.**
- **Is `end - last_start` double counting?** No. `end_now - start_prev` is a sound upper bound on any pinned byte's revisit interval. It is conservative: with a stable iteration order the true per-byte revisit is about `(start_now - start_prev) + max(0, D_now - D_prev)`, so the bound can over-count by up to about `D_prev`. It counts the current pass duration once; nothing is counted twice. Tightening it would require per-pin timestamps (see §5, rejected for now).
- **Does the monitor raise before an in-flight pass can finish?** Yes, by design. It fires at `last_full + 5 + ≤0.05 s poll + scheduling`. Here it fired 5.4 ms past the threshold. The in-flight background pass ended 22 µs earlier (`last_full + 5.005385`), so it would have failed its own `L:471` check anyway. The two latches agree. The worst observed interval (5.0054 s) is **not** materially above 5 s. The guard enforced the limit correctly.
- **The structural constraint:** the 4 s trigger leaves only `5 − 4 = 1.0 s` for poll lag + scheduling + one complete `verify()`. The design had 1 s of headroom against a work item measured at 0.327 s idle (pins only).

## 3. Timing reconstruction from saved records (Q2)

These come only from saved monotonic fields. Nothing below is invented; inferred values are labelled.

| Monotonic | Event | Record |
|---|---|---|
| 491747.486 | update 51 metrics row written | `C/training-metrics.jsonl` last row `monotonic` |
| 491747.954 | `update_complete` 51 (derived: worker deadline 497827.040855666 − remaining 6079.087) | `C/schedule.jsonl` |
| 491748.412 | `update_admitted` 52 (derived from remaining 6078.628) | `C/schedule.jsonl` |
| 491748.413 | forced resource sample (gap 0.098 < 0.15 ⇒ forced) | `C/worker-resources.jsonl` |
| **491748.428957** | **forced full pass start = last_full (main thread, admission boundary)** | `worker_resources` |
| ≥491752.429 (inferred) | background pass may start (`L:461`); actual start **not recorded** | — |
| 491753.302 | last resource sample | `worker-resources.jsonl` |
| 491753.434342 | background pass end (= last_full + max gap) | derived from `maximum_full_input_gap_seconds` |
| 491753.434364 | monitor latch, `first_failure_monotonic` | `inner-failure.json` |
| 491753.5245 | inner (30650) reaped, raw 256 | acceptance `inner_wait` |
| 491753.782 | outer (30643) reaped, raw 256 | `O/raw-wait.json` |

Derived numbers:
- **Failing background pass duration:** `D_bg = 5.005385 − trigger_lag`, with `trigger_lag ∈ [4.000, ~4.05]` unless the verify thread was itself delayed. So `D_bg ≈ 0.955–1.005 s`, or less if the start was delayed by scheduling. In both cases trigger lag + D = 5.0054 s.
- **Foreground (main-thread) forced-pass spacing under the same run,** taken from the 183 forced samples (gap < 0.15 s; monitor and main-loop samples are ≥ 0.15 s by `L:504`/`L:1143`). Intervals under 1.5 s between consecutive forced samples, n=127: min 0.417, **median 0.450**, p90 0.521, max 0.986 s. This is an upper bound on one forced `verify()` plus `ps`/lease/sample overhead and any main-thread work between calls. Examples right before the failure: forced samples at last_full −0.943, −0.475, −0.016 (spacing 0.468, 0.459).
- **Implication:** the failing background pass (≈0.96–1.0 s) was about **2×** the typical foreground pass (≈0.45 s) and about **3×** the idle pins-only receipt (0.327 s). The foreground passes run while training is paused, because the main thread is doing the verify. The background pass ran during the `collect_rollout` of update 52, at 13312/16384 decisions.

Missing records that would be needed to prove attribution:
- no per-pass `start`/`end`/`D` for background passes
- no component split (pins / capsule walk / check_frozen / module origins)
- no `thread_time` vs wall time (CPU vs GIL/IO wait)
- no `verify_lock` wait
- no trigger lag
- no page-cache or IO counters

Only the **maximum** gap survives, and it is the failing one. `schedule.jsonl` has no `monotonic` field: the observer recorded `original_collector_error KeyError('monotonic')`, and the schedule times above are derived from `remaining_worker_seconds`. The outer and inner final resource receipts are missing because publication failed.

How well "4 s cadence with 1 s headroom starves under ML load" is proven: **proven** that headroom was exhausted (source + max gap + latch time). **Strongly supported** that pass duration inflates under concurrent training (the 2× foreground/background contrast within the same run). **Not proven**: the background pass distribution or its tail. The run survived about 200+ background passes and then one exceeded the budget; how often passes come near 1 s is unknown.

## 4. Root-cause ranking

1. **Proven, primary: the guard design leaves only 1.0 s of headroom.** A fixed 4 s trigger against a hard 5 s revisit limit means trigger lag + `verify()` ≤ ~1.0 s. In the failing pass this sum was 5.0054 − 4 ≈ 1.005 s. The guard behaved exactly as written. The limit was not exceeded materially; the budget design was too tight.
2. **Supported, contributing: `verify()` cost is about 0.45 s foreground and up to about 1.0 s in the background under training.** That is well above the 0.327 s idle pins-only measurement that justified the design. The receipt excluded the capsule stat/rglob walks, `check_frozen`/`build_identity` rehashing, module-origin double hashing, and any ML load (`future_ML_runtime_measured: false`).
3. **Hypothesis, unmeasured: contention between the background verify thread and the training main thread.** Candidate mechanisms:
   - CPython 3.12 GIL hand-off: each `stat`, `open`, `read` and `close` across 9870 files plus the walks releases and re-acquires the GIL, and re-acquisition can wait up to `sys.getswitchinterval()` = 5 ms when the main thread is in Python.
   - torch with 4 threads.
   - native environment threads.
   - a `ps` fork/exec every ~0.18 s from `sampled_rss` (`L:401-405`).

   This is consistent with the 2× contrast but cannot be attributed without thread CPU-time instrumentation.
4. **Hypothesis, low likelihood: IO or page-cache pressure** (≈1 GB RSS + 2.4 GB MPS). There is no evidence either way; the files are small and most likely cached.
5. **Ruled out:**
   - resource caps (below)
   - sample gap (0.25 ≤ 0.5)
   - lease or user cancel
   - source or input change (postflight input verification passed: `checks.frozen_inputs_and_strict_lease.passed`)
   - absolute deadline (6078 s remaining)
   - a training numerical fault

Do not read the cause as "5 ms over, so allow 5.1 s". The 5.4 ms overrun is incidental. The real problem is a ~1 s budget for a ~0.45–1.0 s heavy-tailed task.

## 5. Minimal future guard fix (Q3). Plan only; not implemented.

Invariants that must not change:
- revisit limit ≤ 5.0 s strict, with the monitor at `L:507` unchanged in meaning
- all 9870 pins, the 9675 old-pin union, and the legacy 75-source `check_frozen` content
- capsule read-only walk and module-origin checks
- forced full pass at update and eval boundaries
- no hash cache, no mtime shortcut, no sampling or subset hashing, no tolerance

**F1, required: earlier, deadline-driven admission.** Replace the fixed `< 4` trigger with `at - last_full < T_trigger`, where `T_trigger = 5.0 − R` and the reserve `R` covers the worst plausible pass plus poll and scheduling:
- Static choice: `T_trigger = 2.0 s` (R = 3.0 s). This gives about 3× the observed failing pass and about 6.5× the foreground median.
- Optional adaptive tightening: `T_trigger = min(2.0, 5.0 − 0.05 − 2·max(D_bg over last 32 passes))`, with a floor of 0.5 s. If even the floor cannot fit, fail with a distinct `verification_headroom_exhausted` reason. The adaptive part may only start passes **earlier**, never later.

The limit is unchanged; only the admission time moves.

Estimated overhead:
- **Static, measured volume:** 228,611,008 B per pass. At the current ~4.5–5 s period that is about 165–183 GB/h of (mostly page-cache) reads. At a ~2.5–3 s period it is about 275–330 GB/h.
- **CPU duty, partly measured:** pass ≈ 0.45 s foreground / ≤ 1.0 s background. That is about 9–22% of one core now and about 15–40% at a 2 s trigger.
- **Busy case: not measured.** More frequent passes may raise GIL contention and slow training. This must be measured by F2 before any new run is authorized.

**F2, required: per-pass verification instrumentation.** Stream one JSONL row per pass (forced and background) to a new owned file, about 2–3 k rows per 2 h. Each row records:
- `thread`, `forced`, `trigger_lag = at − last_full_prev`
- `lock_wait` (`verify_lock` acquire time)
- `start`, `end`, `duration`
- component durations: pins / capsule / check_frozen / module_origins
- `time.thread_time()` delta (CPU vs wait split)
- `gap`, `files`, `bytes`

This uses the same monotonic clock and no new process. Also add a `monotonic` field to `schedule.jsonl` events. That closes the evidence gaps listed in §3.

**F3, conditional (only if the F2 stress shows background p99.9 duration > 1.5 s at a 2 s trigger): process-isolated verifier.** A dedicated owned child process does the identical hashing and walks with no shared GIL. It reports `(start, end)` per pass over a pipe, and the worker's monitor enforces `now − last_reported_start ≤ 5` itself, with independent liveness. This is a larger scope: a new owned group, lifecycle and ACK ordering. It is not part of the minimal fix.

Rejected:
- raising 5 s, a grace window, or tolerance
- hash or stat caching across passes
- dropping or deduplicating pins or legacy checks
- per-pin timestamp revisit accounting: it is sound but changes measurement semantics, so it is deferred and would need its own review
- lowering the forced-boundary passes
- `sys.setswitchinterval` tuning as the sole fix: it is unproven and would only be considered as a measured follow-up

## 6. Regression matrix for the future fix (stdlib synthetic only; no ML, no rerun)

| ID | Test | Expectation |
|---|---|---|
| R1 | Fake clock: verify duration 0.9, 1.5, 2.9 s with T_trigger 2.0 | pass; max gap ≤ 5 |
| R2 | Fake clock: verify duration 3.1 s at T_trigger 2.0 | latched `Full input verification gap exceeded 5s` (limit unchanged) |
| R3 | Monitor fires before in-flight pass ends when `now − last_full > 5` | latch time ≤ last_full + 5 + poll |
| R4 | Adaptive trigger never later than static; floor breach → distinct failure reason | as stated |
| R5 | Synthetic GIL stress: CPU-bound Python thread + real stdlib hashing of a 228,611,008-byte / 9870-file synthetic tree | record p50/p99/max pass duration and trigger lag; acceptance: p99.9 + trigger ≤ 4.5 s |
| R6 | Pin-set equality: 9870 pins, 9675 old-pin union, 75 legacy sources, capsule 160 files byte-identical to frozen inventory | exact equality |
| R7 | Mutation: change 1 byte in a pin, capsule file, legacy source or module mirror between passes | detected within ≤ 5 s |
| R8 | Forced boundary passes still occur at update/eval boundaries and reset `last_full` | as before |
| R9 | Instrumentation rows: one per pass, monotonic, durations sum ≤ wall | schema check |
| R10 | Outcome precedence (see §7): guard failure followed by executor SIGTERM keeps primary `outcome`/`error` | primary retained, `cancellation_secondary=true` |

## 7. Exit, cancellation and publication behaviour (Q4)

Sequence, reconstructed from source and records:
1. The worker monitor latched (`L:509-510`). The main thread raised it at the next `check_guard` in `collect_rollout`. `worker_failure` (`L:777`) did a memory-first latch and sent the executor ACK.
2. The executor watchdog (`X:212-245`, TERM at `X:240-242`) saw `pool.until` set and sent SIGTERM via `signal_once` to all owned groups. That SIGTERM was the **automatic failure cleanup**, not a user or observer cancel: `forwarded_cancellation=[]` and lease `cancel_requested=false`.
3. The worker's latch recorded the SIGTERM, so `L:937-940` overwrote `outcome`/`error` with `cancelled` / `Cancellation latched`. The primary error survives only in `traceback`, `final_verification_error` and `worker_resources.latched_failure`. The inner supervisor also took SIGTERM before it could send `worker_wait` (`L:1107`), so `worker_wait` is None and the frozen campaign manifest was never published (`L:1126` is never reached).
4. Outer and inner raw exit 256 / returncode 1. All three groups were positively absent 0.348 s after first failure, within the 10 s cleanup window. `accepted=false`.

Classification:
- **Code defect (reporting only): outcome precedence.** A secondary cleanup-induced cancellation overwrites the primary guard failure outcome and error. The rejection is still correct (`expected_exit_code 1`, failed, not eligible). Fix: if `permission['failed']` is already set, keep the first outcome and record `cancellation_requests` / `cancellation_signal` as secondary fields only.
- **Missing proof, not a defect:** the missing `worker_wait`, the missing campaign manifest, and the missing outer/inner final resource receipts. These are expected results of TERM cleanup on the failure path. They prevent full qualification, which is moot because the run failed. They do not weaken the rejection.
- **Holds:** failure rejected, owned groups absent, no publication was mistaken for success, and the post-run observer manifest is an observer artifact, not a success publication.

## 8. Training authority (Q5)

- The one-shot 7200 s authorization is **consumed**. There is no automatic retry and no resume. The failed D2 output is not a parent.
- The run gave about 18 min (51 updates) of new D2 training. It does not show whether 2 h more would solve D2, and it is not an apples-to-apples comparison with old phase 104, because the seed and update index differ.
- A future run requires an explicit new user authorization, a fresh review of the F1/F2 guard change (and F3 if triggered), a new registered protocol/identity/capsule, and an eligible D1 parent (the same D1 `ce9c03c8…` only if re-audited). Old failed weights (`checkpoint-0000{10..17}`) stay TRAINING/TRANSITION-ineligible and diagnostic-only.
- None of the following is in scope: overnight restart, parameter bundle, entropy change, student, or identical retry. The old R2 raw-14 history stays unproven and preserved.

## 9. Limits of this diagnosis

- The background-pass duration distribution is unknown; only its maximum survives.
- GIL contention vs IO vs CPU attribution is a hypothesis.
- The foreground spacing is an upper bound that includes overhead.
- Reading of `docs/implementation-plan-v2.md`, `docs/SPEC_PRIVILEGED_VIT_RL.md` and `state.json` was limited to locating and hashing them plus the `state.json` top-level keys (`active_long_campaign` is null). They are not otherwise used.
- Reward, seed and counter correctness is deferred to the parent Codex audit.
