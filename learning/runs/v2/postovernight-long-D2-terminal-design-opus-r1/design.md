# Long-D2 terminal publication and cancellation ownership — Opus design r1

Status: **design only**. No source, helper, capsule, protocol, config, ledger, docs or checkpoint metadata was edited. No ML/Torch/native import, deserialization, inference, gameplay, gradient or training occurred. No child agents. All writes are inside this directory (`design.md`, `plan.json`, `inputs-sha256.json`).

Candidate inspected: `postovernight-long-D2-prepare-r2/long_d2.py` SHA `0fe9970187e5c4c2576ff2929a475025cd5731a538325ffac78f172304af1d01` (re-hashed, matches). Protocol r2 `f662a4ab…1cff09`, config `2ac814d3…30c2db`, identity `969d8259…781ed0`, capsule-final manifest `b1ccbeef…ef25a1` all re-hashed and matched. Full input list and hashes: `inputs-sha256.json`.

Reading depth, stated honestly: the r2 controller's signal, alarm, Guard, `stop_owned`, `publish_terminal`, `revoke_terminal`, `_supervise`, `supervise` and `main` were read line by line. So were the r2 supervisor review, the probe seams in `publication_probes.py`/`probe_old_boundaries.py`, and the `old-late-terminal-write-closure` receipts. The ledger, the plan/spec docs, the r1 materials and the parent reconciliations were hashed and treated as the governing context the parent summarized. They were not re-audited.

---

## 1. Root cause, ranked by evidence

### RC-1 (confirmed by SUP-001-R2/SUP-002-R2 and source; high confidence): the design keeps a "restore previous process state" teardown *after* its last in-process authority check

`cancellation_signals()` (`long_d2.py:407-465`) saves the SIGINT/SIGTERM dispositions, which are `SIG_DFL` and the default `KeyboardInterrupt` handler in the CLI. Its `finally` restores them, drains `sigpending()`, runs `after_handler_restore`, rescans, sets `_ACTIVE_CANCELLATION=None`, and **then** issues `pthread_sigmask(SIG_SETMASK, mask)`. That last syscall is a real operation of the supervisor:

* It is the moment the process becomes deliverable to the restored `SIG_DFL` and `default_int_handler` (SUP-002-R2: raw −15/−2 with complete artifacts).
* It is after the last lease/input/deadline check (SUP-001-R2: lease cancel, input mutation or deadline crossing during that window returns complete 2/0).

`supervise()` then checks only `cancel.cancellation_requests`, which the restored handlers can no longer increment.

### Why the second repair only moved the blind interval

r1's finding was "checks stop before publication/alarm restoration". r2 answered by adding a check after handler restoration. The structure stayed the same: *check → restore process state → return*. Any check placed before a restoration step leaves that step unchecked. Adding a check after it adds a new last step, and the same problem appears one step later. Whatever the r3 repair is, the restoration step must not exist. Moving the check again would not fix it. Three things are therefore rejected outright: recursion that keeps adding checks, "move the check after the last check", and restoring "previous" dispositions in production.

### RC-2 (source-proven latent defect class; contributes to RC-3): per-context SIGALRM save/arm/restore with asynchronous raises

`absolute_alarm` (`:640-663`) is entered sequentially about seven times. Each entry saves `old=signal.signal(SIGALRM, expired)`, re-arms `ITIMER_REAL`, and on exit disarms and restores `old`, which is `SIG_DFL` in the CLI. Its handler raises `Stop` asynchronously at any bytecode. When a context is entered **after** the deadline, it arms `max(1e-6, deadline-now)`. That is a 1 µs timer, which guarantees an asynchronous raise at an arbitrary point, including inside `contextlib` `__exit__` machinery or another generator's `finally`. A raise in those places can skip or defer (to cyclic GC) the generator `finally` that holds the restoration. A deferred `finally` later restores a stale `old=SIG_DFL` and disarms or re-arms the timer out of order.

### RC-3 (unresolved r2 `old-late-terminal-write-closure` raw −14; plausible, NOT proven)

Facts from the retained receipts:

* The probe ran with `BUDGET=.8` and a 1.1 s sleep after the first terminal write.
* The failed `wall_guard` terminal was written with `wall_seconds_lower_bound=0.8069`. That is the publication alarm firing at the deadline during the sleep, followed by `revoke_terminal`.
* The owned group was reaped and positively absent. `events.json` ends at `trigger`, with **no `guard_closed` event**. There is no traceback and no observation.

So the process died after the failure revocation and before Guard close finished. That is the post-publication region, entered *after the deadline*, which begins `with alarm_factory(deadline)`. That entry arms a 1 µs timer, and the probe's `alarm` wrapper adds a second generator layer around `real_alarm`. A raw −14 requires SIGALRM to be **delivered while the disposition is `SIG_DFL`**. Two mechanisms fit, ranked:

1. **Most plausible:** a deferred or skipped `absolute_alarm` generator `finally` (RC-2) restored `SIG_DFL` while a timer armed by a later or overlapping context was live. One trigger is the 1 µs post-deadline arming interleaving with the asynchronous `Stop` from `authority()` passing through two `@contextmanager` layers.
2. **Less plausible:** a process-directed `ITIMER_REAL` SIGALRM targeted at a non-main thread whose mask did not block it. Guard threads inherit an unblocked mask in r2. If delivery on that thread completes after the main thread restored `SIG_DFL` (the disposition is evaluated at delivery), the default action kills the process. This is weakened because both Guard threads should self-terminate within ~0.05 s of the deadline.

Neither is proven. No retry was performed, and the design must not depend on which one is true. The r3 design removes **both** preconditions:

* the disposition never returns to `SIG_DFL` in the supervisor;
* the timer is armed exactly once and never after the deadline;
* the handler raises at most once;
* every non-main thread is created with INT/TERM/ALRM blocked.

Test T-ALRM-3 reproduces the r2 configuration under r3 and asserts no raw −14.

### Not a root cause

No learner, schedule, counter, environment or control defect is implicated. Those blocks stay byte-identical.

---

## 2. Authority boundaries (precise)

A finite program cannot promise anything about requests that arrive after it decides. This design therefore defines **two authorities** and **one decision point**.

### 2.1 In-process decision point D

`D` is the instant `final_decision()` reads its last observation: `sigpending`, latch counters, `guard.failure`, the lease read, and `monotonic()`. After D the supervisor executes **only** one of:

* `os._exit(code)` (CLI), or `return code` (Python API);
* if and only if the decision is 1: failure-only downgrade writes (`revoke_terminal`), then exit 1.

There is **no handler restoration, no unmask, no thread join, no flush, no atexit, no interpreter finalization, no hash, no normal write** after D. INT/TERM/ALRM are blocked in the main thread from before D through exit. Every other thread is positively absent before D. Signals that become pending in `[D, exit]` are discarded by the kernel at `_exit`. They are never delivered to any disposition, so raw −2/−14/−15 from these signals is impossible.

**In-process guarantee (exact):**

* Every SIGINT/SIGTERM delivered or pending at any time from handler install (first statement of `run`) through D reaches the single latch and yields exit 1 with revoked artifacts.
* Every lease cancel, lease field change, pinned-input change, Guard failure or deadline crossing that is *observable by the final reads at D* yields exit 1.
* The in-process guarantee claims nothing for the bytecodes between the last read and `_exit`. That window holds no IO and no unbounded operation.

### 2.2 Outer executor acceptance (sole acceptance authority)

The in-process `finalization-result.json` becomes a **provisional internal decision**. It is not acceptance. Its shape: `internal_decision ∈ {complete_pending_outer_acceptance, failed}`, `authoritative=false`, `acceptance_authority="outer-executor-receipt"`.

This is not a relabel of the old false complete. Three things change authority:

* (a) no consumer, ledger rule or gate may read it as acceptance;
* (b) the executor independently re-establishes every property after the observed exit;
* (c) every event the r2 review placed in teardown now precedes D and fails in-process.

The executor is a separate stdlib process. It is the parent of the supervisor and runs it in a new session, so terminal Ctrl-C reaches the executor, not the supervisor. It is the only channel of record for cancellation: it forwards a SIGTERM and records the send time, or the user sets `cancel_requested` in the lease. It writes its acceptance receipt **outside** the campaign output and never modifies campaign files.

It accepts **only if all** of the following hold, evaluated after `waitpid` returns:

1. Raw wait status is a normal exit (`os.WIFEXITED`) with code ∈ {0, 2}. Any signal death (−2/−9/−14/−15), code 1 or any other code → reject.
2. The executor sent no cancellation signal before observing the exit.
3. Lease re-read after reap is strict 15-field equal to the protocol's expected lease and `cancel_requested is False`. Lease identity is unchanged, so any cancel at any time up to this read → reject. The read is conservative because executor ordering is "after exit".
4. `reap_monotonic − spawn_monotonic ≤ 7200`. `spawn ≤ T0`, so this bound is never looser than the supervisor's 7200 from T0.
5. The internal receipt is `complete_pending_outer_acceptance`, its `expected_exit_code` equals the raw code, and its `artifact_manifest_sha256` equals the re-hash of the on-disk manifest.
6. Every file in the campaign output is listed in the manifest, except `finalization-result.json` and the manifest itself, and its re-hash matches. There are no extra files and no `.pending`/`.failed-publication` files.
7. Pure preflight (`long_d2.py preflight`, stdlib, existing) re-run after reap passes all active pins. That covers the 793 pins, the capsule mirror, the 75 legacy module-origin bytes and the original identity. The run's own controller SHA must equal the protocol value.
8. The owned worker group recorded in the internal receipt is positively absent (`killpg(pgid,0)` → ESRCH, plus a `ps` fallback), and the supervisor's own session has no survivors.

Executor failure path: on reaching `spawn + 7200 + 10 (failure cleanup) + 5` it SIGTERMs the supervisor session, waits 5 s, then SIGKILLs. It records a reject and never accepts. The executor never retries and never resumes.

### 2.3 State table

| Event time | In-process result | Executor result |
| --- | --- | --- |
| Before handler install (imports) | raw signal death, no output | reject (raw) |
| Install → worker spawn → publication → teardown → D | 1, revoked, manifest absent | reject (code 1) |
| Inside `[D, _exit]` (bytecodes only) | 0/2 provisional | reject via rules 2/3/4/7 (cancel, lease, wall, inputs). Third-party direct signals to the supervisor PID in this window are discarded and are outside the cancellation channel of record. |
| After exit, before executor checks | n/a | reject if the lease is cancelled, inputs/artifacts changed, or the group is alive |
| After the executor receipt is written | n/a | outside this experiment. Later changes are new evidence for the parent, not a revocation. |

---

## 3. Minimal repair, per function (r3 controller in a new `prepare-r3` directory)

Unchanged byte-for-byte:

* `Learner`, `Schedule`, `run_schedule`, `environment_kwargs`, `counter_report`, `compare_control`, `tree_fingerprint`, `assert_equal_tree`, `stop_owned`, `assert_lease`, `check_module_origins`;
* `worker()` body;
* `validate_long_config`, `expected_lease`, pins/identity/module-origin policy;
* old 1800/cutoff validators;
* every budget constant: `BUDGET=7200`, `WORKER_SECONDS=7140`, `CLEANUP_SECONDS=10`, `LIMIT=6GiB`.

### 3.1 `ProcessLatch` (replaces `cancellation_signals` and `absolute_alarm`)

```python
OWNED = (signal.SIGINT, signal.SIGTERM, signal.SIGALRM)
class ProcessLatch:                      # module singleton LATCH; never restored
    NORMAL, FAILURE, FINAL = 'normal', 'failure', 'final'
    def __init__(self): self.phase=None; self.requests=0; self.requested_signal=None
                        self.alarm_fired=False; self.raised=False; self.deadline=None
    def install(self, deadline):          # first statement of `run`, before any thread/output
        require(threading.active_count()==1, 'Latch must precede threads')
        require(self.phase is None, 'Latch installed once')
        self.deadline=deadline; self.phase=self.NORMAL
        for s in OWNED: signal.signal(s, self._handle)   # no getsignal/save: nothing to restore
        remaining=deadline-time.monotonic()
        if remaining <= 0:                # never arm a 1 µs timer; fail synchronously
            self.alarm_fired=True; self.phase=self.FAILURE
            raise Stop('Deadline reached before latch install','wall_guard')
        signal.setitimer(signal.ITIMER_REAL, remaining)   # armed exactly once
    def _handle(self, number, frame):
        if number==signal.SIGALRM: self.alarm_fired=True
        else:
            self.requests+=1
            if self.requested_signal is None: self.requested_signal=number
        if self.phase==self.NORMAL and not self.raised:
            self.raised=True; self.phase=self.FAILURE    # state change precedes the raise
            raise (Stop('Supervisor absolute 7200s alarm','wall_guard') if number==signal.SIGALRM
                   else KeyboardInterrupt(f'Cancellation signal {signal.Signals(number).name}'))
        # FAILURE: latch only, never raise (failure persistence is not torn).
        # FINAL: unreachable, OWNED are blocked in main and other threads are absent.
    def enter_failure(self): 
        if self.phase==self.NORMAL: self.phase=self.FAILURE
    def failed(self): return self.requests>0 or self.alarm_fired or time.monotonic()>=self.deadline
    def scan_pending_blocked(self):       # call only with OWNED blocked in main thread
        pend=signal.sigpending() & set(OWNED)
        while pend:                       # sigwait on an already-pending set returns at once
            n=signal.sigwait(pend)        # consumes exactly one pending instance
            if n==signal.SIGALRM: self.alarm_fired=True
            else:
                self.requests+=1
                if self.requested_signal is None: self.requested_signal=n
            pend=signal.sigpending() & set(OWNED)
```

Python/OS semantics this depends on:

* Python handlers run only in the main thread, between bytecodes. PEP 475 retries EINTR syscalls unless a handler raises, so a raise in NORMAL interrupts `sleep`/`read`/`waitpid` in main.
* `sigpending` on macOS returns process ∪ calling-thread pending. With every other thread absent or blocked, a pending OWNED signal is visible to main.
* `sigwait` is used only on a non-empty pending set, so it never blocks. `sigtimedwait` is unavailable on macOS and is not used.
* Blocked standard signals coalesce: two SIGTERMs while blocked count once. The latch counts *delivered or consumed* instances, and any count > 0 is failure, so coalescing cannot hide a request.
* `ITIMER_REAL` is process-directed. With non-main threads blocking SIGALRM it is delivered to main.
* Handlers survive for the process lifetime. `exec` in the worker resets caught dispositions to default, and the worker clears its mask as today.

### 3.2 `start_masked_thread(thread)` (new helper; used by `Guard.start`)

```python
def start_masked_thread(t):
    prev=signal.pthread_sigmask(signal.SIG_BLOCK, set(OWNED))
    try: t.start()                        # child thread inherits OWNED blocked
    finally: signal.pthread_sigmask(signal.SIG_SETMASK, prev)
```

`Guard.start` changes only its two `thread.start()` calls to `start_masked_thread(thread)`. The Guard keeps both locks, its ≤0.5 s resource/lease sampling and its ≤5 s full verification, and its stream is memory-only. `Guard.close` is unchanged, except that it must also return a positive-absence fact: `closed_threads_absent = all(not t.is_alive())`. No mutable manifest-bound writer exists. The disk snapshot is still opened `'x'`, written and closed before any hash, as in r2.

### 3.3 Remove per-context alarms in `_supervise` and `publish_terminal`

Replace every `with alarm_factory(deadline):` and `with absolute_alarm(deadline):` with **nothing**. The single process timer from `LATCH.install` interrupts NORMAL-phase IO at the deadline. Keep the synchronous `require(time.monotonic()<deadline, …)` checks.

`alarm_factory` stays as a test seam. It defaults to a no-op `nullcontext` and is never used in the CLI. Test fixtures that shorten the deadline do so through `LATCH.install(deadline)` and `BUDGET`, which is how probes already patch `BUDGET`.

### 3.4 Failure path discipline in `_supervise`

```python
except BaseException as error:
    LATCH.enter_failure()                 # first statement of every failure handler
    result.update(outcome_fields(failure_outcome(error)), ...)
finally:
    LATCH.enter_failure() if result-is-failed else None
    cleanup_owned_once(process, result)   # see 3.5
```

`publish_terminal` loses its `with cancellation_signals()` and uses `LATCH` directly:

```python
def check(stage):
    stages.append(...)
    require(time.monotonic()<deadline, ..., 'wall_guard')
    authority(force=stage in ('before_terminal_authority','terminal_receipt_publication'))
    if LATCH.requests or LATCH.alarm_fired: raise Stop('Cancellation/alarm latched during publication', ...)
```

The receipt it writes is provisional: `internal_decision='complete_pending_outer_acceptance'`, `authoritative=False`, `acceptance_authority='outer-executor-receipt'`, plus the existing fields. `revoke_terminal` writes `internal_decision='failed'` and is otherwise unchanged. It stays idempotent and failure-only, and it may exceed the deadline. It never hashes and never creates a complete record.

### 3.5 `cleanup_owned_once(process, result)` (wrapper; `stop_owned` itself unchanged)

```python
def cleanup_owned_once(process, result):
    if process is None or result.get('owned_process_stop',{}).get('stable') is True: return
    start=time.monotonic()
    try: r=stop_owned(process)            # byte-identical r1; its own 9.5s bound
    except BaseException as e:            # e.g. one NORMAL-phase raise landed inside it
        LATCH.enter_failure()             # no further raises can occur
        r=stop_owned(process)             # retry ONCE in FAILURE phase; 2nd failure is final
        r['first_attempt_error']=repr(e)
    r['stable']=(process.poll() is not None and r.get('reaped') is True and r.get('group_empty') is True
                 and not r.get('errors') and not r.get('error'))
    result['owned_process_stop']=r; result['cleanup_seconds']=time.monotonic()-start
    if not r['stable'] or result['cleanup_seconds']>CLEANUP_SECONDS:
        result.update(outcome_fields('publication_failure'),cleanup_failure=True)
```

The group is single-use: one `Popen(start_new_session=True)`, never respawned. The cleanup is bounded and failure-only. The retry exists only because a NORMAL-phase asynchronous raise may abort the first attempt mid-loop. That can happen at most once (`LATCH.raised`), so the total is ≤ 2 × 9.5 s, and the cleanup budget check still marks >10 s as `publication_failure`. This is not a run retry.

### 3.6 Post-publication sequence (replaces the r2 code from `closed=False` to the end of `_supervise`, and `after_handler_restore`)

```python
# NORMAL or FAILURE phase, single process timer still armed, OWNED unblocked in main.
try:
    authority(force=True)                 # lease + forced resource sample + forced full verify (<=5s)
    guard.close(); guard.stream=None      # joins (<=0.5s each); require threads not alive
    stream.close()
    receipt=read_json(terminal); receipt.update(supervisor_resources_final=..., ...)
    replace_json(terminal, receipt)       # LAST normal write
    authority(force=True)                 # full verify after last write
except BaseException as e:
    LATCH.enter_failure(); revoke_terminal(...); code=1
finally:
    failure-only guard close as today (sets guard.stream=None, closes stream)
return final_decision(code, args, result, started, stable, lease_check)
```

### 3.7 `final_decision` (new; contains D)

```python
def final_decision(code, args, result, started, stable, lease_check):
    signal.pthread_sigmask(signal.SIG_BLOCK, set(OWNED))   # never unblocked again
    LATCH.phase = LATCH.FINAL if code != 1 else LATCH.FAILURE
    signal.setitimer(signal.ITIMER_REAL, 0)    # disarm; a fired-but-pending ALRM is scanned below
    decided = code; reason = None
    try:
        sys.stdout.flush(); sys.stderr.flush() # bounded, before D (tty/pipe only)
        require(threading.enumerate()==[threading.main_thread()], 'Non-main thread alive at decision')
        lease_check()                          # one small read of the strict lease
        LATCH.scan_pending_blocked()
        if guard_failure_latched or LATCH.requests or LATCH.alarm_fired: decided = 1
        if time.monotonic() >= LATCH.deadline: decided = 1      # <-- D: last observation
    except BaseException as e:
        decided = 1; reason = e
    if decided == 1 and code != 1:             # downgrade only; never upgrade
        LATCH.phase = LATCH.FAILURE
        revoke_terminal(args.output, result, started, stable, reason or Stop('Final decision', ...))
    return decided
```

* `supervise(args)` becomes `LATCH.install(started+BUDGET)` (when not already installed; for the API test seam, the fixture installs), then `_supervise`, then the return of `final_decision`.
* `main` `run`: `code = supervise(args); os._exit(code)`. There is no `SystemExit`, no atexit and no finalization. The `preflight` and `worker` paths are unchanged.
* The Python API returns `decided` with OWNED still blocked in the calling thread. API tests run in a subprocess so that state never leaks.

Why this is not "another check moved later":

* After D there is no state restoration whose failure could be unobserved. The only code left is `os._exit`, or downgrade-only writes followed by exit 1.
* Blocked signals cannot reach any disposition before `_exit`.
* No handler is restored, so `SIG_DFL` never returns.

What remains unchecked is a finite bytecode window. The executor closes it, and section 2 states it as the boundary.

Lease commit point: D is **not** a lease commit that ends cancellation. The lease remains cancellable until the executor's post-reap read (rule 3), and any `cancel_requested=true` observed there rejects. So the live-cancellation contract (≤0.5 s detection during run; cancel → failure, never acceptance) is strengthened, not weakened: in-process detection covers through D, and executor rejection covers through acceptance.

### 3.8 Unbounded-IO discipline

After the single timer is disarmed in `final_decision`, the only IO is `flush`, one lease read, and, on failure only, `revoke_terminal`. A hung filesystem there cannot produce a false accept, because the executor's wall rule (rule 4 / kill path) rejects it. Normal IO before `final_decision` stays under the live process timer. The deadline includes all normal writes, hashes, Guard joins and teardown; `final_decision` re-checks `monotonic() < deadline` at D.

---

## 4. Test matrix

All OS tests run the actual r3 `supervise` with the actual Guard and an actual owned stdlib OS worker, in a fresh subprocess with a synthetic lease/root. That is the existing `publication_probes.scenario` style.

Each test asserts the **pre-acceptance failure**: in-process code 1 with a revoked internal receipt, or a provisional receipt that the executor model then **rejects**. It must also assert that the failure was an `AssertionError`/Stop outcome category, not an import, API or fixture error. That is checked by asserting `trigger_fired`, `ML_imports==[]`, and the outcome field.

Every injected test has a paired **false-pass control**: the same seam with no mutation and no delay must yield in-process 2 (closure) or 0 (pass) **and** executor ACCEPT. Without that pairing, an always-reject implementation would pass the matrix.

**Kill tests:** the parent runs the new seam tests against the frozen r2 controller (seam = its final `SIG_SETMASK`) and must observe AssertionError failures for T-FU-*, T-SIG-* and T-ALRM-3. The tests are black-box on the receipt/exit contract, so they apply to both controllers unchanged.

Seams (Python-only fixtures, not CLI-exposed):

* `S_pre_D`: wrap `final_decision` before `lease_check`.
* `S_D_exit`: wrap the `os._exit` callable (API: the `return`).
* `S_teardown`: Guard close, stream close, last terminal write.
* `S_alarm_entry`: `LATCH.install`.

| ID | Seam / injection | Modes | Expected |
| --- | --- | --- | --- |
| T-FU-1 | S_teardown: own-lease cancel + 0.65 s delay (exact r2 SUP-001 case, moved to its r3 equivalent) | closure, pass | 1, revoked, manifest absent |
| T-FU-2 | S_teardown: pinned-input change + 5.1 s delay | closure, pass | 1 (full verify after last write) |
| T-FU-3 | S_teardown with BUDGET 0.8, 1.0 s delay (deadline crossing) | closure, pass | 1, wall_guard, no raw −14 |
| T-FU-4 | S_pre_D: lease cancel / input change / deadline crossing, each | closure, pass | 1 |
| T-FU-5 | S_D_exit: lease cancel; input change; 1.0 s delay past a 0.8 s budget | closure, pass | in-process 2/0 provisional; executor REJECT by rules 3/7/4 |
| T-SIG-1 | real `os.kill(self, SIGTERM)` at S_teardown | closure, pass | 1, cancelled, `requests≥1`, exit not −15 |
| T-SIG-2 | real SIGINT at S_teardown | closure, pass | 1, no KeyboardInterrupt traceback, not −2 |
| T-SIG-3 | real SIGTERM / SIGINT at S_pre_D (blocked → pending → `scan_pending_blocked`) | closure, pass | 1 |
| T-SIG-4 | real SIGTERM / SIGINT at S_D_exit (the exact r2 SUP-002 position, after the last scan) | closure, pass | raw exit = provisional code (not −15/−2; signal discarded). Executor with forwarded-signal record → REJECT; direct third-party variant → ACCEPT only if lease and inputs unchanged, documented as the stated boundary. |
| T-SIG-5 | two SIGTERMs while blocked (coalescing) and SIGINT+SIGTERM during worker run | closure | 1, requests≥1, worker group reaped and absent |
| T-ALRM-1 | timer fires during NORMAL publication hash | closure, pass | 1, wall_guard, handler raised once (`LATCH.raised`) |
| T-ALRM-2 | timer fires during failure persistence (FAILURE phase) | closure | no raise, revoke completes, 1 |
| T-ALRM-3 | exact r2 `old-late-terminal-write` configuration: BUDGET 0.8, 1.1 s at terminal-after | closure, pass | 1, wall_guard, Guard closed event present, observation written, **no raw −14**. Run 20× (not a retry: a repeat sample, all retained). |
| T-ALRM-4 | `install` with deadline already passed | — | Stop wall_guard, no `setitimer` call (spy), 1 |
| T-ALRM-5 | SIGALRM pending at `final_decision` (fired after block, before disarm) | closure | `scan_pending_blocked` latches → 1 |
| T-ALRM-6 | static/AST: no `signal.signal` call outside `ProcessLatch.install`; no `getsignal`; exactly one `setitimer(` with nonzero arg; no `SIG_SETMASK` to an unblocking mask after `final_decision` | — | pass |
| T-R1-1..n | all r1 SUP-001/002 boundaries: authority/input before publication, late cancel/input during publication, SIGTERM at publication exit | closure, pass | 1 |
| T-R2-old | all 17 r2 old-boundary probes, re-run against r3 (blocked worker included) | as r2 | 1 and assertions complete |
| T-SAMP-1 | resource/lease sample gap >0.5 s injected (slow probe) at each phase incl. teardown | closure | 1 resource_stop |
| T-SAMP-2 | full-verify gap >5 s (slow verify) incl. after last write | closure | 1 |
| T-SAMP-3 | full hash 0.7 s while resource sampling continues (r2 independent Guard tests, kept) | — | sampling gaps ≤0.5 |
| T-IO-1 | blocked IO in NORMAL phase (fifo read) past deadline | closure | single timer interrupts → 1 within cleanup bound |
| T-IO-2 | blocked worker ignoring SIGTERM | closure | SIGKILL, reaped, group absent, 1 |
| T-IO-3 | lease read hangs inside `final_decision` (fifo lease, synthetic) | — | executor kill path → REJECT (raw −9/−15 recorded) |
| T-THR-1 | Guard thread wedged (verify blocked) at close | closure | `close` require fails → 1; `final_decision` non-main-thread check also fails |
| T-THR-2 | `threading.enumerate()` positive absence at D recorded in receipt | pass | `[MainThread]` |
| T-THR-3 | every Guard thread's mask contains OWNED (read via `pthread_sigmask(SIG_BLOCK, set())` inside thread) | — | pass |
| T-WR-1 | no open writer on any manifest-bound path at each hash point (r2 check, kept) | closure, pass | pass |
| T-WR-2 | after `final_decision` the only writes are failure-only (fs spy) | all | pass |
| T-OWN-1 | late own terminal write (spy rewrites terminal after manifest) | closure | executor REJECT (rule 5) and in-process 1 if before D |
| T-EXE-1 | executor: raw −15 / −2 / −14 / −9 / exit 1 / exit 3 | — | REJECT each |
| T-EXE-2 | executor: exit 2 but internal receipt says expected 0 (mismatch) | — | REJECT |
| T-EXE-3 | executor: extra unlisted file / `.pending` file in output | — | REJECT |
| T-EXE-4 | executor: wall 7200+ε (synthetic clock) | — | REJECT |
| T-EXE-5 | executor: lease `cancel_requested=true` after exit | — | REJECT |
| T-EXE-6 | executor false-pass control, no mutation | closure, pass | ACCEPT 2/0 |
| T-EXE-7 | executor never writes into campaign output (fs spy); acceptance receipt path outside it | — | pass |
| T-IDN-1 | pure preflight, 793 pins, 75 legacy module-origin bytes, original module origins, unchanged learner AST blocks | — | pass |

Count: 14 seam rows × 2 modes ≈ 28 injected OS scenarios, 28 paired controls, plus static, executor and inherited suites. Every failing assertion must have `trigger_fired=True`.

---

## 5. Artifacts, pins, lease, executor invariants

* New directory `learning/runs/v2/postovernight-long-D2-prepare-r3/` with `long_d2.py` (r3), `long_d2_executor.py` (stdlib only), tests, probes, a new capsule freeze and identity doc. r1/r2 directories and all failed attempts are retained untouched.
* Pins unchanged in value: teacher 321290 params, 128/2/4/81, PPO/env/reward, master seed `5562873868232098305`, D1 parent `ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f`, entry control 9 fields / 64 rows with means 1.4765625 / 295.25 before any gradient, 16-update cadence, periodic at 8, reserves, gate pass 50 / score 3060 / alive, exit codes 0 pass / 2 clean closure / 1 failure, 7200/7140/10, RSS/MPS 6 GiB each. No resume, no failed-D2 parents.
* The strict 15-field lease is unchanged in schema. Its `controller_sha256` points at r3. The executor checks the lease with the existing `assert_lease` semantics.
* Executor invariants: E1 sole acceptor; E2 never retries or resumes; E3 writes only its own receipt dir; E4 records spawn, signal-send and reap monotonic times and the raw wait status; E5 accepts only under §2.2 rules 1–8; E6 hard-kill path is failure-only.

### Parent protocol revision (r3) — minimal new or changed fields (not written here)

* `controller_path`, `controller_sha256` → r3 values; `capsule_manifest_sha256`, `identity_sha256` → r3 freeze.
* `executor_path`, `executor_sha256` (new).
* `acceptance_authority: "outer-executor-receipt"` (new); `acceptance_receipt_path` outside the campaign output (new).
* `in_process_terminal_receipt_semantics: "provisional_internal_decision"` (new).
* `executor_wall_rule: "reap_minus_spawn_le_7200"`, `executor_kill_after_seconds: 7215` (new; failure-only).
* `cancellation_channel_of_record: ["lease.cancel_requested", "executor_forwarded_signal"]` (new).
* `supersedes: protocol-r2` while retaining r1/r2 files; `registered_at`.

Config, budgets, gates, campaign plan parameters: **unchanged**.

## 6. Explicit non-claims

* The −14 cause is a ranked hypothesis, not proven. T-ALRM-3 is the discriminating test.
* No claim about the parent's acceptance of past r2 runs. No ML defect is claimed.
* The `[D, _exit]` window is stated, not eliminated. Its closure is executor-side.
* Real MPS restore, entry comparison, throughput, PPO and qualification remain untested runtime gates.
