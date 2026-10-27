# D2 boundary contention: diagnosis and one proposed next step

Scope: read-only design for the frozen, source-intact r11 candidate. This is a proposal. It runs nothing, changes nothing, and makes no production, causal-confidence, training-performance or acceptance claim. The unused 7,200-second D2 authorization stays held. The overnight scheduler stays disabled.

## 0. Pin and input verification (done before source analysis)

All eight `parent-frozen-pins.json` bindings for `learning/runs/v2/postovernight-long-D2-boundary-prepare-r11/` matched byte for byte: `boundary_integrity.py`, `capsule-final/capsule-manifest.json`, `classification.json`, `lifecycle.py`, `long-identity.json`, `long_d2.py`, `long_d2_executor.py`, `registration.json`. Protocol r8 (`fe11c081...`) and the boundary policy (`95977b36...`) also matched their registered SHA256. The receipt lists every input hash. No setup error occurred.

## 1. Observations (evidence, read from files)

Source (r11, line numbers from `long_d2.py` and `boundary_integrity.py`):

- `Guard.full_check(force=True)` (`long_d2.py:497-531`) calls `self.verify()` synchronously on the calling thread (`:511`). Production and stress both reach it from the main thread via `Guard.check(force=True)` -> `sample(force=True)` -> `full_check(True)` (`:490-495`, `:574`).
- The verify callback in the stress and profile is `integrity.verify` (`boundary_integrity.py:104-129`). Its byte work is `c.verify_files(pins)` (`long_d2.py:124-126`), which per file does `Path.is_file()` (a `stat`) and then `sha(path)` (`long_d2.py:68-82`): one `open`, a `read(1 MiB)` loop, one `hashlib.update` per block, then close. It also runs `assert_readonly_capsule` (one `os.scandir` walk with `DirEntry.stat`) and `project_members` (`rglob` + `is_file`).
- Every one of those is a GIL-releasing C call (file `open`/`read`/`close`, `stat`, `scandir`, and `hashlib.update` for blocks over 2,047 bytes).
- `Guard.start` runs a separate monitor thread that wakes every 0.05 s and calls `sample()` when the last sample is at least 0.15 s old. That sample spawns `ps` through `subprocess.run` (`long_d2.py:440-444`), so the monitor is a second thread that also needs the GIL.
- Runtime is CPython 3.12.15 (`long-identity.json` runtime policy). No `setswitchinterval` call exists anywhere in the r11 sources.
- The stress contender (`stress.py:28-31`) is a pure-Python loop: 12,000 integer-LCG iterations, then an `Event.is_set()` check, repeating. It never makes a blocking or GIL-releasing call. Its only exit from the GIL is the interpreter's forced drop request.
- The stress is a registered robustness requirement, not a model of the real workload: `parent-validation-plan.json` stage `changed-source-contention` (120 s cap) and its `stress_justification` ("unchanged CPU contender / 12 forced boundaries / actual B bytes / 120s cap"). The stress is stdlib-only, `MPS_driver_observed` is false, and the contender is not an MPS workload. Neither `docs/implementation-plan-v2.md` nor `docs/SPEC_PRIVILEGED_VIT_RL.md` describes a busy Python thread beside the boundary; the spec's only GIL text is Rayon/GIL release in the Rust env. In real training the boundary runs on the main thread while the training step is paused. No file I read shows a busy pure-Python thread there.

Failed r11 stress (`attempts/attempt-04.../stress/stress-result.json`, read directly):

| pass | wall s | thread CPU s | files | bytes |
|---|---|---|---|---|
| 0 (uncontended) | 0.031 | 0.031 | 273 | 47,527,648 |
| 1-9 (contended, complete) | 9.692, 13.655, 15.978, 4.280, 12.405, 14.589, 16.135, 14.704, 15.851 | 0.082-0.159 | 273 | 47,527,648 |
| 10 (interrupted) | 0.132 | 0.003 | 1 | 58,912 |

Status `failed`, error `Stop('Lifetime wall alarm')` at 120.017 s. Max sample gap 0.2633 s. Every pass read identical bytes through identical hash calls.

Profile r1 (`boundary-profile-r1/output/result.json`, `function-stats.json`): uncontended 0.029707 s wall / 0.029701 s CPU; contended 8.577670 s wall / 0.084720 s CPU; max sample gap 0.2028 s; RSS 37,781,504 bytes. Function-level calls in the profile: `_io.open` 371, `BufferedReader.read` 585, `HASH.update` 310, `DirEntry.stat` 171, `posix.stat` 426, `_IOBase.__exit__` 275, `posix.scandir` 70. Sum of those main-thread GIL-releasing calls is about 2,400. `sampled_rss` ran 48 times (0.744 s cumulative). Profile caveats from the parent stand: cProfile overhead, overlapping cumulative entries (`threading.wait` 9.476 s cumulative exceeds the 8.578 s boundary and must not be summed), and no unique attribution.

Earlier independent evidence (Opus verifier design, r3 stress): 3.43 s wall / 0.446 s CPU for one background pass with a busy Python thread, described there as GIL waiting for the synthetic workload, with production recurrence only a hypothesis. This is consistent but is an earlier opinion, not new evidence.

Ruled out by evidence:
- cProfile overhead as cause: the stress ran without a profiler and shows the same 4-16 s regime.
- Byte volume: uncontended and contended passes read the same 47,527,648 bytes in the same 273 hash calls.
- `project_members` dominance: the profile has it at 0.527 s cumulative out of 8.578 s.
- CPU saturation of the verifier: its own thread CPU is 0.08-0.16 s of 4-16 s wall (about 1-2 %).
- Resource sampler starvation to the limit: max gap 0.2633 s against the hard 0.5 s limit. This is margin, not proof of safety.

## 2. Hypotheses (not established)

H1 (most source-supported): CPython GIL handoff. With a pure-Python thread that never blocks, each time the verifier thread releases the GIL for a syscall (open/read/stat/close/update/scandir) it must wait for the switch interval (default 5 ms, `sys.getswitchinterval()`) before it can force a drop request and get the GIL back. About 2,400 GIL releases times roughly 3.5-7 ms predicts about 8-16 s per pass. That matches the profile (8.6 s) and the stress (9.7-16.1 s, plus the 4.28 s outlier). Uncontended, no waiter exists, so each release costs microseconds (0.03 s total). The extra thread CPU (0.03 s -> 0.08-0.16 s) fits handoff and wakeup cost. This is an order-of-magnitude fit from call counts, not a measurement of any single handoff.

H2: storage or page-cache latency. Weak: identical bytes read uncontended in 0.03 s imply warm cache, and a Python thread does not change storage service time. Not excluded for cold-cache runs.

H3: macOS scheduler/QoS effects on the contender, the verifier or the monitor thread. Not excluded. The verifier and contender can run on different cores, which argues against plain core starvation, but this is not measured. On macOS the wait inside a GIL handoff is a timed condition-variable wait, so scheduler wakeup latency is part of H1 rather than separate from it.

H4: variance from the second GIL waiter (the 0.05 s monitor thread and its `ps` subprocess). Not excluded. It plausibly explains the 4.28 s versus 16.1 s spread but is unmeasured.

Not claimed: that production training suffers this. No evidence shows a busy pure-Python thread beside the real boundary.

## 3. Candidate interventions considered

| Option | Decision | Reason |
|---|---|---|
| A. Scoped `sys.setswitchinterval` around only the Guard boundary verification | Recommended (after probe) | Targets H1 directly. Changes no byte, check, cadence, limit or contender. Process-global effects are bounded and explained below. |
| B. Batch byte work (bigger reads, whole-file read, fewer syscalls) | Not primary | Per-file overhead (`stat`, `open`, `close`, `read`, `update`) dominates. Coalescing 1 MiB blocks removes at most about 340 of about 2,400 releases, roughly 14 %. Predicts about 11-14 s per pass under H1, still failing a 12-pass 120 s budget. Whole-file reads also change memory behavior. |
| C. Hash in a child process or helper thread | Rejected | Adds a verifier process/thread and a trust boundary. Contradicts the "no background verifier thread/process" contract. |
| D. Skip or cache stats/content, or reduce passes | Rejected | Violates "no cross-pass content/stat cache, no cadence skips." |
| E. Change contender, raise cap, remove boundaries | Rejected | Excluded by the task. |
| F. Do nothing, accept risk | Not a design | The stress is a registered gate. |

## 4. Recommendation: one next step, a discriminating probe, then one scoped repair if confirmed

### 4.1 Next step: switch-interval discriminating probe (does not touch r11 source)

New parent-registered fixed-work script in a new directory (for example `learning/runs/v2/postovernight-long-D2-switchinterval-probe-r1/`). It imports the frozen r11 context exactly as `profile_once.py` does (no ML imports, `capsule_context(verify_inputs=False)`), builds the actual `c.Guard(...)` with `integrity.verify` unmodified, and starts the byte-identical contender. Only the probe wrapper calls `sys.setswitchinterval`; no r11 file is edited. cProfile stays off, so timings are not profiler-inflated.

Fixed order, one invocation, no retry: B0 uncontended boundary; start contender; then forced boundaries in order A1 (default interval 0.005 s), B1 (0.0001 s), A2 (default), B2 (0.0001 s). Restore the original interval in a `finally` after each pass and verify it. Record per pass: wall, thread CPU, `sys.getswitchinterval()` before/during/after, max sample gap and RSS. Cap 60 s with the profile run's 70 s emergency guardian. The A passes bound the wall at roughly 2 x 16 s.

Predicted outcome under H1 (a prediction, not a result): A1/A2 land in the 4-16 s regime; B1/B2 finish in 0.03-0.5 s, at least 10x faster than the adjacent A pass, with thread CPU under 0.2 s and a smaller max sample gap.

Falsifying outcome for H1 as the dominant mechanism: either B1/B2 are not at least 10x faster than the adjacent A pass, or any B pass exceeds 1.0 s. Then the stated mechanism does not explain the slowdown, no source change is proposed, and a storage/scheduler discriminator (cold-cache, single-thread-affinity-free comparison, no `ps` monitor) must be designed instead. If A1/A2 both finish under 4 s the probe is inconclusive: contention was not reproduced, so record it and stop. Do not substitute the probe result for the stress gate.

### 4.2 Contingent repair (only if the probe confirms): scoped boundary switch interval in r12

Exact location: `long_d2.py`, new helper `boundary_switch_interval()` beside the other `@contextmanager` helpers (near `long_d2.py:452`), and `Guard.full_check` (`long_d2.py:497-531`) changed to run `observation = self.verify()` (`:511`) inside it. Nothing else changes in source.

```python
BOUNDARY_SWITCH_INTERVAL = 0.0001

@contextmanager
def boundary_switch_interval():
    previous = sys.getswitchinterval()
    try:
        try:
            sys.setswitchinterval(BOUNDARY_SWITCH_INTERVAL)
            yield previous
        finally:
            sys.setswitchinterval(previous)
    finally:
        if sys.getswitchinterval() != previous:
            sys.setswitchinterval(previous)
```

Scope: only the Guard's forced boundary callback, while `verify_lock` is held. That callback is `integrity.verify` in stress/profile and, in production, whatever the production callback runs (including its legacy `check_frozen`/origin/runtime/cache checks), so all of it is covered. Outer preflight/postflight endpoint passes and the final-hash/timing writers are not wrapped; no contender is registered there. The single value 0.0001 is fixed before any run; no tuning loop is proposed. The probe uses the same value, so a pass of the probe validates the exact value.

Process-global effects and risks:
- The interval is interpreter-wide, so every Python thread in the process sees it while a boundary runs. That is the stress contender and the monitor thread. The contender yields to a waiter more often and loses some throughput during boundaries. The monitor thread should wake and sample with smaller gaps. This is a prediction to measure.
- Context-switch overhead may raise verifier thread CPU. Measure it: thread CPU per boundary should stay about 0.2 s or lower.
- Native threads (torch/MPS compute) do not depend on the GIL for compute. Boundaries run with training paused. No claim is made about MPS behavior; the stress does not observe MPS.
- Signal and cancel responsiveness: `ProcessLatch.handle` raises `Stop` on the main thread (`lifecycle.py:113-118`). The main thread's regain-GIL wait is what shrinks, so cancel latency should improve, not worsen (hypothesis). Resource/lease timing (.05/.15/max .5) is unchanged.
- Restoration on every failure path: the inner `finally` restores on success, `Stop`, any `BaseException`, `KeyboardInterrupt` and a signal-raised `Stop`. A signal-raised `Stop` could land inside the inner `finally` before it restores; the outer `finally` re-checks and restores. Exits that bypass both, `os._exit` in `final_exit`, destroy the process, and child processes do not inherit the setting. A leaked small interval would change performance only, never a check outcome. Nested same-thread `full_check` is LIFO-safe: the inner restores to the outer's reduced value, the outer restores to the original. `verify_lock` forbids concurrent changes from other threads.
- Residual: the actual wakeup granularity at 100 us on macOS is not known. The probe measures it.

Optional evidence fields (only if the r12 review confirms every consumer tolerates them): per-row `switch_interval_before`, `switch_interval_during`, `switch_interval_after`. Current consumers read only `sequence` and `verdict` per row (`boundary_integrity.py:165`) and never compare rows strictly.

### 4.3 Protected contracts for the repair

Expected byte-identical in r12: `boundary_integrity.py` (`d4aafd46...`), `lifecycle.py` (`aab36d67...`), `classification.json` (`17612541...`), `long_d2_executor.py` (`b63d5356...`). Expected to change: `long_d2.py` plus whatever derives from its hash (`capsule-final/capsule-manifest.json`, `long-identity.json`, `registration.json`). That derived list is an expectation to confirm at freeze, not a measurement.

Unchanged by construction: full actual B/R/A endpoint checks; all forced active B checks; genuine legacy `check_frozen`/origin/runtime/cache checks; no content/stat cache; no cadence skip; no background verifier; no new integrity deadline; identity and the single-scandir capsule pass; 7200/7140/7170 s; shared cleanup `min(previous, earliest_failure+10, T0+7210)`; .05/.15/max .5 timing; separate 6 GiB RSS/MPS limits; acceptance on raw/exit-wall/direct-parent wait/positive absence/mandatory integrity summary; failure chronology, one-shot ACK, IPC, r11 escalation repair; model/PPO/reward/env/seeds/gates/D1 lineage; restore-before-environment and the 64-row nine-field entry control; the stress contender, 12 forced boundaries, actual B bytes and the unchanged 120 s cap. No failed-weight resume, D3, student, CPU fallback or automatic launch/retry.

### 4.4 Bounded validation order (each stage stops on its first failure)

1. Rehash the eight r11 pins, protocol r8, config, D1 checkpoint hash. Keep the failed r11 stress, r11 review and profile r1 evidence unchanged.
2. Run the switch-interval probe (section 4.1), at most 60 s. Gate: confirmed, falsified or inconclusive as defined above. Only "confirmed" continues.
3. Freeze a new r12 candidate with only the two source edits above. Static diff check: no changes to protected files, and `long_d2.py` differs only in the helper and the `full_check` call site.
4. Stdlib unit tests for restoration on success, `Stop`, other `BaseException`, signal-injected `Stop` inside the `finally`, nested calls, and a second thread calling `getswitchinterval` during a boundary; plus the existing 112 methods.
5. Independent review of the frozen r12 source.
6. Existing 15 real-OS lifecycle fixtures, once.
7. Changed-source contention stress, once, unchanged contender/12 boundaries/120 s cap. Pass criteria are the existing ones; the interval restore receipt is additional evidence.
8. Startup-only stage per the existing plan. The 7,200-second authorization stays held until the parent's gates pass.

Stop conditions at any stage: any failed or missing check, any boundary that is not `passed`, interval not restored, a B pass slower than 1.0 s in the probe, max sample gap at or above 0.5 s, cap breach, any attempt to change the contender/cap/checks, or any need to widen scope.

## 5. What this does not claim

No measurement was run. H1 is the best source-supported mechanism but is not proven. Passing the probe or the stress would not demonstrate production performance, real MPS behavior, continuous immutability, memory attestation or OS isolation. Genuine parent-death worker reaping stays unproven. The failed r11 stress remains failed evidence, and no unchanged-source retry is proposed.
