# Long D2 terminal lifecycle reconciliation: Codex r1

Status: design only, ready for parent reconciliation and a separate implementation delegation. This document completes the missing structured plan after the Opus provider failed with `Claude API rate limit reached. Try again later.` Opus did not complete its task. Its substantial partial design is preserved untouched, SHA256 `931d5912f68668db3e1b547608d8d0c6033cb9d40c176bea6e46defa728f06c4`.

The accepted direction from that partial design is process-lifetime signal ownership, one alarm owner per process, and independent outer acceptance after actual process exit. This reconciliation replaces its double cleanup allowance, 7215-second watchdog, post-disarm IO, all-thread assertion, channel narrowing, circular protocol pins, and repeated identical-probe prescription. It does not approve the partial pseudocode as an implementation.

## 1. Evidence and decision

The first inputs read were the exact parent assessment and the partial Opus design. The two frozen reviews, their findings, actual r2 signal/Guard/publication/CLI source, actual final-unmask and publication probe APIs, retained delayed-unmask summaries and cited signal events were inspected. The original design/plan, protocol/config, API audit, parent reconciliations, learner/evidence audits, ledger, and relevant governing plan/spec sections were also inspected. This is static source/JSON evidence. No candidate module, test suite, ML package, native extension, checkpoint, or probe was executed.

Confirmed defect: r2 `cancellation_signals` restores old dispositions, performs its last callback and pending scan, clears `_ACTIVE_CANCELLATION`, then executes `pthread_sigmask(SIG_SETMASK, mask)` at lines 464–465. Both Guard threads have already stopped. `supervise` then consults the old request counter rather than re-establishing authority. The frozen review proves lease cancellation plus 0.65 seconds, changed input plus 5.1 seconds, and a shortened deadline crossing inside that last operation can preserve complete exit 2/0. Real queued SIGTERM/SIGINT at the same operation produce raw -15/-2 and leave complete artifacts. These are events during teardown, not after a returned call. The next repair removes the production restoration operation rather than putting another check before it.

The retained `old-late-terminal-write-closure` execution exited -14. Its terminal receipt was already failed/wall_guard, manifest unavailable, and owned group reaped and positively absent. The events stop before orderly Guard-close evidence. Repeated context alarms, restoring SIGALRM to SIG_DFL, and post-expiry 1-microsecond arming are plausible hazardous mechanisms. Their involvement in that exact -14 is **unproven**. Do not describe a proven root cause or count that execution as a pass.

Decision: keep the ML and schedule source intact; replace only supervision lifecycle and its external authority. A new stdlib executor owns the experiment clock and independent acceptance. The inner controller produces a provisional candidate. The parent accepts only the outer receipt together with the observed outer raw exit and wall time. Neither a surviving inner complete field nor an outer receipt standing alone establishes acceptance.

## 2. Fixed experiment and deadline contract

All original learner/config bytes remain unchanged: config SHA256 `2ac814d3842228017d09669364a8391344722da56ad19f41ad9030dbb930c2db`, seed `5562873868232098305`, eligible D1 SHA256 `ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f`, full 321290-parameter teacher, width/layers/heads/tokens 128/2/4/81, PPO, environment, reward, resource limits, entry control, counters, and schedule. Entry remains nine fields on 64 rows, means 1.4765625/295.25, before any gradient. Entry/16-update evaluation and update-8 checkpoint cadence remain exact. U/E growth, C=15, F=30, admission, decision budget, restoration, and control comparisons stay unchanged. RSS and MPS each remain 6442450944 bytes; they are not added together.

Choose this concrete split of the existing 60-second supervisory reserve:

| Boundary | Absolute monotonic deadline | Meaning |
| --- | --- | --- |
| T0 | Executor's first clock sample, before its ordinary imports | Shared by every process; never reset at spawn/import |
| Worker | T0+7140 | Existing worker guard and schedule cutoff; outer also rejects a worker still running at this boundary |
| Inner | T0+7170 | Inner candidate publication, joins, final checks, and raw exit must finish before this deadline |
| Outer | T0+7200 | All outer pin/artifact hashes, strict lease reads, receipt write/close, final checks, and actual outer exit must finish before this deadline |
| Failure cleanup | min(first_failure+10, T0+7210) | One shared, failure-only deadline for every participant; never a new allowance per process, phase, signal, retry, or artifact |

Use `<` for admission/final decisions and accept only observed elapsed wall `<=7200`; exact equality is conservatively rejected by the live checks. No normal work uses cleanup time. Worker failure, worker not exited by 7140, inner not exited by 7170, or outer finalization not finished by 7200 permanently changes the result to failure. Earlier failure gets only ten seconds from that failure, not until 7210. Normal successful reaping/absence checks consume normal budget; an already reaped, empty group does not require a termination grace period.

The unchanged worker body contains historical `args.started+BUDGET` finalization bounds. These do not grant extra worker time: the independent executor enforces worker raw exit by 7140, and inner supervision receives the same T0. No learner or worker ML call site changes to accommodate the split. Its existing F=30 reserve already budgets worker finalization inside the worker schedule. A future run that cannot satisfy these bounds fails; it gets no reserve increase or retry.

Feasibility is structural, not a performance claim: 7140+30+30=7200 and 7200+10=7210. No ML work is added. Thirty seconds for each finalizer is a hard allocation, not proof that this machine can hash the future artifact volume within it. Implementation must run stdlib-only frozen-pin/artifact-volume timing controls and fail closed if the reserve cannot be met. No extra ML smoke is authorized. Do not alter config's `supervisor_finalization_reserve_seconds=60`; protocol lifecycle fields subdivide that existing reserve.

## 3. Process and ownership interfaces

New implementation paths, to be created later:

- `learning/runs/v2/postovernight-long-D2-prepare-r3/long_d2.py`
- `learning/runs/v2/postovernight-long-D2-prepare-r3/long_d2_executor.py` (stdlib only)
- New tests, freeze helpers, identity and `capsule-final` in that preparation directory.
- Parent protocol: `learning/runs/v2-orchestration/postovernight-long-D2-r1-protocol-r3.json`.
- Outer receipt: `learning/runs/v2/postovernight-long-D2-execution-r1/acceptance-receipt.json`, outside campaign output.
- Campaign output remains `learning/runs/v2/postovernight-long-D2-campaign-r1`.

The parent launches the exact frozen executor invocation once. The executor captures T0 before ordinary imports, installs its lifetime latch/alarm, validates the frozen external registration and strict lease, then launches the inner supervisor in its own new session. The existing inner supervisor launches exactly one worker in a **different** new session. Killing only the supervisor PGID cannot clean the worker group.

Use one inherited, private `socketpair` for clock/ownership/control messages; no production environment-only T0 override. Hidden `--executor-fd` and `--executor-pid` are the only new controller CLI arguments. The first bounded message schema is `long_d2_owned_start_v1`: `executor_pid`, `t0_monotonic_hex`, `protocol_sha256`, `identity_sha256`, `capsule_manifest_sha256`. Require actual `os.getppid()==executor_pid`, private inherited FD, exact registered paths/hashes, finite T0, `T0<=inner_local_launch<=now`, and registered offsets. Convert `float.hex` with `float.fromhex`; pass the identical float through existing worker `--started`. A direct production `run` without the owned handoff is rejected. Synthetic API seams are subprocess-only and cannot authorize a CLI campaign.

During the existing signal-masked `Popen` assignment, register `worker_pid`, `worker_pgid=pid`, new-session proof and the exact command with the executor before unmasking or permitting ML. Add a hidden worker-start gate in CLI setup **before** calling the unchanged `worker()` body. The worker waits for executor acknowledgment before any project import. The executor maintains an append-only in-memory ownership table for the supervisor and single worker, and acknowledges only an exact owned PID/session/command binding. Both successful and failed runs retain this table in the external receipt.

Registration cannot make POSIX spawn atomic. If supervisor death/timeout occurs between Popen and registration, acceptance is forbidden. The executor uses a bounded process-table census to identify only the exact worker command with this supervisor PID, T0, capsule path and registered output, verifies new-session PGID, and adds that group to failure cleanup. A delayed/unproven census is a cleanup failure, never evidence of absence. Do not kill unrelated or merely old processes. The worker start gate prevents an unregistered process from beginning ML; it does not prove that no bootstrap orphan can ever exist. Kill/reap/census race tests are required. If implementation cannot retain and prove this ownership at its chosen IPC seam, parent must reject the implementation; do not silently weaken the invariant.

An independent stdlib executor watchdog thread monitors deadlines, child exits, IPC closure, cancellation and registered groups while the executor main thread performs bounded validation IO. It uses no disk writer and starts with owned signals masked. Its observation loop is <=0.025 seconds; any observed missed bound causes rejection. It survives inner D and inner exit. Single lifetime ITIMER_REAL on executor main additionally interrupts ordinary blocking IO at T0+7200. This is independent of the inner alarm and of Torch. It is not a real-time OS or kernel-uninterruptibility guarantee; elapsed wall/raw exit remain mandatory parent evidence.

## 4. Function-level lifecycle pseudocode

Pseudocode below is an implementation contract, not executable code or a new campaign entry point. Every named IO/join/probe checks the current absolute deadline before and after, and uses remaining-time subprocess/socket timeouts. No minimum positive timeout may extend an already expired deadline.

### ProcessLatch, one alarm owner

```python
OWNED = {SIGINT, SIGTERM, SIGALRM}

class ProcessLatch:
    # Process singleton. NORMAL can interrupt; DEFER and FAILURE only latch.
    def install(self, normal_deadline):
        require_main_thread_and_no_existing_timer_owner()
        self.phase = NORMAL
        self.requests = 0
        self.first_signal = None
        self.alarm_seen = self.raised = False
        self.deadline = normal_deadline
        for sig in OWNED:
            signal.signal(sig, self.handle)       # Never restore old dispositions.
        remaining = normal_deadline - monotonic()
        if remaining <= 0:
            self.alarm_seen = True
            raise Stop('Expired before alarm installation', 'wall_guard')
        setitimer(ITIMER_REAL, remaining)          # Exactly one nonzero arming.

    def handle(self, sig, frame):
        if sig == SIGALRM:
            self.alarm_seen = True
        else:
            self.requests += 1
            if self.first_signal is None:
                self.first_signal = sig
        if self.phase == NORMAL and not self.raised:
            self.raised = True                    # Before asynchronous raise.
            self.phase = FAILURE
            raise Stop('wall alarm' if sig == SIGALRM else 'cancelled',
                       'wall_guard' if sig == SIGALRM else 'cancelled')
        # No IO, locks, cleanup, restoration or second raise in a handler.

    def observe_pending_once(self):
        # Main has blocked OWNED. Only this main thread consumes these signals.
        pending = sigpending() & OWNED
        for sig in sorted(pending):              # Finite set; no storm-drain loop.
            sigwait({sig})                       # Only already-pending signal.
            self.record_without_raise(sig)
        # A new request after this finite observation is an explicit exit-gap limit.
```

Install one singleton for each production CLI process; in the inner supervisor its deadline is 7170, in executor 7200. Worker CLI ownership setup supplies the existing worker cutoff; the unchanged `cancellation_signals()` call becomes a borrowing adapter over its process latch, with compatible callable deferral and request fields. It never restores handlers or clears the singleton. No nested timer context remains on the production supervisor path. Preflight remains stdlib-only and creates no output. Production CLI uses `os._exit`, never `SystemExit`/atexit/interpreter finalization after the terminal decision.

Python executes Python signal handlers on its main thread between bytecodes. PEP 475 may restart interrupted syscalls if the handler does not raise. Thus DEFER is used only for bounded owned teardown/failure persistence, not as permission for new potentially blocking normal work. All prior dispositions remain replaced for the process lifetime. Pending standard signals coalesce; exact request counts are not promised, but every observed nonzero request forces failure. Do not use unavailable macOS `sigtimedwait`, a new signal restore, or post-expiry microsecond timer rearming.

### Guard and writers

```python
def start_masked_owned_thread(thread):
    oldmask = pthread_sigmask(SIG_BLOCK, OWNED)
    try:
        thread.start()                           # Child inherits blocked OWNED.
    finally:
        pthread_sigmask(SIG_SETMASK, oldmask)     # Latch remains installed here.

# Guard.start: replace only the two owned thread start calls with this helper.
# Retain separate resource and verification locks and latched failures.
# Resource/lease <=0.5s; full verification <=5s including IO duration.

def close_owned_guards(guards, deadline):
    for guard in guards:
        guard.event.set()
    for thread in exact_owned_thread_handles(guards):
        thread.join(timeout=min(0.5, remaining(deadline)))
        require(not thread.is_alive(), 'Owned Guard did not stop')
    require(no_owned_writer_handles_open(), 'Owned writer remains')
```

Keep r2's closed `supervisor-guard.jsonl` disk snapshot: copy memory under the resource lock, close the snapshot, then hash. The continuing publication monitor writes **memory only**. No thread may reopen or append to the disk snapshot. Close all worker log streams after reaping. Require positive absence of exact owned Guard/verifier/writer thread handles before the final decision; do not require `threading.enumerate()==[MainThread]`. Supervisor and executor never import Torch. Native/Torch worker pools are not Guard threads; their lifetime ends with the worker process, whose raw exit and entire group absence must precede hashing. Their runtime behavior remains a future gate.

### One cleanup owner and one shared deadline

The executor is the sole termination/escalation owner in production. Inner normal code waits/reaps its direct worker and proves absence; on failure it sends a failure event and cooperates with the executor, rather than starting a second independent stop allowance. The new r3 `stop_owned` supervision implementation may change; the historical r2 helper stays immutable. All participant cleanup receipts refer to the same executor-owned deadline.

```python
def begin_failure(reason, observed_at=None):
    failure_latch.add(reason)                     # Cannot return to normal.
    if first_failure is None:
        first_failure = min(monotonic(), observed_at or monotonic())
        cleanup_until = min(first_failure + 10.0, T0 + 7210.0)
    return cleanup_until                         # Never reset, including new signals.

# Inner failure detection must send/ack this timestamp before local persistence.
# If it cannot communicate, exit 1; executor starts failure on IPC loss/raw exit.
# Executor rejection includes unacknowledged or inconsistent failure timestamps.

def cleanup_owned_once(table, cleanup_until):
    latch.phase = DEFER                           # Requests recorded; no interruption/retry.
    send_once(SIGTERM, all_exact_owned_live_groups(table))
    kill_at = min(first_failure + 5.0, cleanup_until - 0.5)
    while monotonic() < cleanup_until:
        poll_and_reap_direct_children_without_blocking()
        incorporate_acknowledged_worker_registration_and_exact_census()
        if monotonic() >= kill_at:
            send_once(SIGKILL, remaining_exact_owned_groups(table))
        if all_required_leaders_reaped_and_groups_positively_absent():
            break
        bounded_poll_sleep(cleanup_until, maximum=0.02)
    # Any final ps check has timeout <= min(0.2, remaining); ESRCH or exact ps proof.
    # No wait(timeout=5), new cleanup call, new timer or fresh allowance follows.
    record_absence_or_unproven_failure()
```

Normal reaping/absence is required even without failure. For failures, child cooperative close, group termination, reaping, Guard joins, failure-only persistence and executor rejection publication all share this same ten-second interval. Persistence is best effort, deadline bounded, and never hashes files or emits acceptance. Retain partial/unavailable evidence if a write blocks or time runs out. Repeated signals only latch. No training restart, cleanup retry, or extra post-7210 wait is allowed. Kernel scheduling may delay a kill/reap; record failure/unproven cleanup, never a fictitious successful bound.

### Inner publication and finite decision D

```python
def supervise_owned(args, handoff):
    T0 = validate_private_owned_handoff(handoff)
    latch.install(T0 + 7170)
    # Existing context/pins/lease and worker ML path; single registered worker.
    result = supervise_worker_until_exit_or_failure(worker_deadline=T0 + 7140)
    require_actual_worker_exit_and_positive_group_absence()
    close_worker_log_streams()
    close_disk_guard_snapshot_once()               # Monitor continues in memory.
    authority(force=True)                          # Existing all-pin/origin policy.
    publish_provisional_run_manifest_and_terminal(result)
    authority(force=True)                          # Includes last publication IO.
    latch.phase = DEFER                            # Bounded close; cancellations still count.
    close_owned_guards_and_memory_streams(T0 + 7170)
    require_owned_guards_and_writers_positively_absent()
    authority(force=True)                          # Includes joins/stream closure.
    write_final_provisional_terminal_with_final_guard_receipt()
    authority(force=True)                          # Timer still armed; no post-disarm IO.
    assert_strict_lease_again()
    check_sample_and_full_verify_age_including_last_operation()
    # No context managers or pending ExitStack finally blocks remain after this call.
    return final_D_and_exit(result.expected_exit_code)

def final_D_and_exit(code):
    # All IO, flushes, joins, lease reads, full checks and receipt writes are finished.
    # stdout/stderr flush, if wanted, occurs earlier under the live alarm, never here.
    pthread_sigmask(SIG_BLOCK, OWNED)                # No later unmask.
    setitimer(ITIMER_REAL, 0)                        # Disarm only after normal IO is done.
    latch.observe_pending_once()
    failed = latch.requests or latch.alarm_seen or guard_failure_in_memory
    failed |= monotonic() >= inner_deadline         # D: final finite memory/clock decision.
    if failed:
        code = 1
    os._exit(code)                                 # No normal write/flush/return/context restore.
```

If failure is known before entering the final leaf, transition permanently to failure, notify the executor, close/persist only within the shared cleanup deadline, then enter a failure-only exit leaf. If the final pending scan itself changes code to 1, exit 1 immediately; the provisional candidate can remain on disk but is rejected by raw exit. Do not do downgrade IO after D or invent another D after each write. A separate outer rejection receipt explains why inner candidate files are not accepted. Earlier failures may revoke the inner manifest; missing revocation is explicitly not acceptance.

DEFER during joins cannot drop cancellation: `authority` must inspect the latch before/after every subsequent bounded teardown operation. It must also synchronously check the clock because the one-shot alarm may already have fired while deferred. Once alarm/cancellation is observed there is no further normal verification or write. No arbitrary last unmask is allowed. Direct SIGINT/SIGTERM that is delivered, latched, or pending by the finite scan forces raw exit 1; tests must cover direct real signals, not only lease mutations.

### Outer executor acceptance

```python
def execute_once(frozen_registration):
    # T0 captured at script entry before ordinary imports, never spawn time.
    latch.install(T0 + 7200)
    verify_external_registration_and_exact_strict_lease()
    launch_one_inner_new_session_and_private_handoff()
    start_masked_owned_watchdog()
    monitor_worker_registration_raw_exits_deadlines_and_forwarded_requests()
    raw_inner, inner_reap_at = observe_actual_inner_wait_status()
    require(normal_exit(raw_inner) and exit_code(raw_inner) in (0, 2))
    require(inner_reap_at < T0 + 7170 and worker_reap_at < T0 + 7140)
    require(no_failure_or_cancel_latched_and_no_forwarded_cancel_record())
    require(all_owned_worker_and_supervisor_groups_positively_absent())
    # Read-only stdlib validation, bounded by outer deadline and live watchdog/alarm.
    assert_strict_lease_again()
    verify_all_current_and_retained_original_pins_plus_new_sources()
    verify_readonly_capsule_and_original_module_origin_policy_metadata()
    verify_provisional_manifest_run_terminal_and_all_artifact_bindings(raw_inner)
    assert_strict_lease_again()
    write_close_outer_receipt_atomically()          # Final normal write; still under timer.
    # Receipt cannot include its own hash or the actual time of its own later close.
    # Parent computes that hash after raw outer exit; no self-hash cycle.
    verify_final_lease_latch_guard_ages_and_wall_after_receipt_close()
    stop_and_join_exact_owned_watchdog_within_normal_deadline()
    # Include watchdog close in one final lease/time/latch check, alarm still active.
    assert_strict_lease_again()
    finite_outer_D_then_os_exit_matching_code()     # No IO/restoration after D_outer.
```

Forwarded cancellation is recorded **before** sending it to the supervisor/worker. The outer latch remains installed throughout receipt IO and its teardown. A forwarded request after inner D still rejects even if the inner process exits 0/2. Lease cancellation remains a supported live channel and is reread after hashes and after the outer receipt write, before outer D. An outer receipt written before a late failure is invalid without matching raw outer exit/wall; try to remove/downgrade it within the same failure pool, but never depend on removal for correctness. Parent must retain its actual command start/end/raw exit receipt; if it does not have one, acceptance is unavailable. Receipt publication and validation are normal work inside 7200, not work performed later under cleanup.

Outer accepts only an exact matching outcome: inner/outer code 0 with completed D2 progress gate, or 2 with clean below-gate closure. Worker result code, run result, terminal expected code, gate fields and candidate bindings must agree. Failure/missing/unknown schema, raw -2/-9/-14/-15, other exit code, clock mismatch, late exit, input drift, lease drift/cancel, missing ownership registration, live/unproven group, open writer, extra/symlink/escaped artifact, pending/failed-publication file, altered manifest/run binding, resource/gap failure or unobserved executor termination causes rejection. No normal hash starts while any owned group/writer can still mutate output.

## 5. Authority, cancellation and finite limits

Inner `long-run-result.json` and `finalization-result.json` gain `authoritative=false`, `acceptance_authority="outer-executor-receipt"`, and `internal_decision="complete_pending_outer_acceptance"` or `"failed"`. Existing ML result/outcome fields can retain their schema; `complete` means an internal candidate only and is never sufficient for a consumer. Preserve unchanged `outcome_fields`/`result_code` ML behavior by adding authority metadata in supervisor publication, not altering learner code. Outer receipt supplies `experiment_status` complete/failed, accepted boolean, actual raw statuses/times, bindings, ownership facts, cancellation records, resource/gap receipts and all frozen identities. A 0/2 decision is provisional until outer acceptance; 2 never means gate pass. No receipt grants teacher qualification or training-parent eligibility.

D does not end lease cancellation or redefine a legitimate request away. All bounded owned teardown operations occur before D under lifetime handlers and live outer supervision. The interval between the last finite observation and `_exit` contains only memory arithmetic/branch and `_exit`; it has no intentional IO, flush, unmask or restoration. A test-induced sleep there is outside the production leaf and must still be rejected by the independent outer deadline if it crosses the budget.

There is no atomic global observation of Python handlers, pending kernel signals, lease bytes, all input bytes, wall time and process exit. A third-party **direct** signal arriving at the supervisor after its last pending scan may become pending and be discarded by `_exit`; the executor cannot magically observe it. It is still a legitimate cancellation request; it is an explicit observation limitation, not an excluded channel or a reason to call acceptance cancellation-proof. Parent/executor-forwarded cancellation is recorded independently and rejected; persistent lease/input mutations are rejected by outer checks. The same finite observation limit exists at outer D. Record exact observation bounds and never claim that a signal or a transient cancel-and-revert/input-change-and-revert between samples was observed. Persistent cancellation and sampled-gap breaches remain fail closed.

## 6. Exact protocol r3 patch and noncircular freeze

Do not write the production protocol during this design. Parent registration precedes implementation. Copy r2 unchanged except these existing fields: `version="postovernight_long_D2_protocol_v3"`, `controller="learning/runs/v2/postovernight-long-D2-prepare-r3/long_d2.py"`, `design="learning/runs/v2/postovernight-long-D2-terminal-design-codex-r1/plan.json"`, `design_sha256=<actual completed plan SHA256>`, and `registered_at_utc=<parent registration UTC>`. Add exactly one `terminal_lifecycle` object with the values in plan.json. Existing authorization, run_id, output, budget, guard fields, config, gates, parent, module-origin policy and all ML settings remain unchanged. Existing guard's 7200 all-normal-work limit now includes outer work; its original T0 description is refined by the lifecycle object's shared executor origin.

Protocol stores paths/schema/deadline offsets, **not** final controller/executor/identity/capsule hashes. The completed protocol hash is then embedded in new controller/executor checks and the new identity. Identity `controller_sources` pins every active root helper/executor/test source; original input pins retain the entire r2 793-pin union, prior immutable helpers/reviews/capsule bytes and all original 75 legacy sources. Retain exact historical digest values; add r3 pins rather than substituting/removing old pins. New pin count is expected to grow and must be reported by exact inventory equality, not a weakened minimum-only test. Runtime origin checks still require original `python/dodge_rl` origins plus capsule mirrors. Never patch old 1800/cutoff validators or ignore a mismatch.

Freeze order: completed design/plan hash; parent protocol r3; r3 sources containing protocol hash; identity including protocol and all source hashes but excluding its own document/capsule manifest; readonly capsule including identity and sources but excluding its manifest; external frozen invocation/registration binding all final hashes. Strict lease retains exactly the same 15 fields, with new controller/identity/capsule/protocol values, same config, lineage, budget and authorization. No executor field, T0, task ID, progress, or parent annotation is added to the lease. Lease's identity/capsule bindings transitively bind executor; external invocation directly pins executor as well. Outer receipt pins protocol/config/source inventory/identity/capsule/lease/D1/manifest/run/terminal/artifacts/ownership and actual raw statuses. Parent's command receipt externally hashes the outer receipt. This DAG has no protocol/source/identity/self-hash cycle.

## 7. Required targeted validation before parent freeze

Every test below is future implementation/review work, stdlib-only with owned synthetic state, actual Guard and owned OS fake worker where applicable. Retain all attempts. Run meaningful controls first, stop on the first unexpected failure, repair/review as a new implementation identity, and never translate this into a training retry. No mandatory 20-times repeat. Both `closure` and `pass` mean expected exit 2 and 0 respectively.

| ID | Injection and required result |
| --- | --- |
| POS-0/2 | No mutation/delay using actual full lifecycle, real Guard, real OS fake worker and outer validator: parent accepts 0 and 2 respectively, correct binding, all owned threads/groups absent. Proves implementation does not always reject. |
| R2-NEG | Retained exact r2 evidence is the negative control. Optionally execute each needed exact r2 final-unmask case once, without source edits, in fresh synthetic paths: cancellation 0.65s, input 5.1s, deadline 0.8s/1.0s, real SIGINT/SIGTERM, both outcomes. Contract assertions must fail on r2 with injection fired, not import/API errors. Never replay the unexplained r2 -14 as an identical probe. |
| PRE-D | r3 equivalents at each remaining owned teardown syscall/close/join and before D: cancel+0.65s, input+5.1s, shortened deadline crossing, both outcomes. Require code 1/rejection; no accepted receipt. No test may depend on the removed restoration seam firing in r3. |
| SIG-DIRECT | Real direct SIGINT/SIGTERM before D, inside bounded teardown, between mask and pending scan, and pending before disarm, both outcomes. Require latch/failure, raw 1, no default disposition/uncaught KeyboardInterrupt. Check signals during spawn-mask release too. |
| POST-D | At test-only `_exit` seam, persistent lease/input mutation or delay across inner/outer deadline: reject using outer raw/wall/lease/pins. Executor-forwarded real SIGINT/SIGTERM after inner D: record-before-forward and reject. Direct third-party after-scan variant documents possible unobserved provisional exit; never claim guaranteed observation. |
| ALARM | Spy one nonzero arm per process, no SIG_DFL restore and no post-expiry rearm. Expired installation fails synchronously. Alarm during normal hash interrupts once; alarm/repeated INT/TERM during DEFER/failure do not interrupt or restart cleanup. Pending ALRM after block/disarm fails. Signal storm cannot create an unbounded pending-drain loop. |
| R3-LATE | On new r3 implementation, once per outcome, shortened 0.8s deadline with 1.1s terminal-after delay. Require failed wall result, outer rejection, no unexplained raw -14, retained orderly-close or explicit bounded-close-failure evidence. This exercises the new lifecycle; it does not prove the old -14 cause. |
| R1-REG | Exact earlier hash/manifest/terminal before/after writes, outer-publication-exit equivalent, final verification, stream/Guard closure and deferred cleanup cancellation boundaries, both outcomes where applicable: no acceptance after mutation/deadline/cancel. |
| OUTER-LAST | Delay/mutate during the final outer receipt write/close and watchdog join. Timer remains live; post-write lease/latch/wall checks reject. If failure revocation blocks, parent still rejects raw outer 1/signal/late wall despite an old acceptance-shaped file. No receipt-only consumer permitted. |
| PIN-LEASE | Exact strict 15 fields, duplicate/nonfinite/unknown/missing keys, every D1 anchor/hash, every old pin plus new sources and both identity copies; drift in protocol, executor, old helper or capsule rejects. Byte-compare ML nodes and config; old origin policy and all 75 inputs remain exact. No imports/deserialization required. |
| GUARD | Independent slow 0.7s full hash does not block <=0.5s lease/resource sampling. >0.5 resource/probe and >5 full-check duration/age fail. Separate RSS/peak and MPS at/above limits, invalid observations, latched failure after recovery, final age after IO, and wedged Guard joins all reject. |
| WRITER | At each hash point assert no open owned manifest-bound writer. Disk snapshot stays unchanged while memory monitor advances. A late own terminal rewrite, extra/pending/symlink file, or altered run/manifest/terminal binding rejects. |
| GROUP | Leader exits with live descendant; worker ignores TERM; inner dies while its separately new-session worker survives; worker registration/Popen race; IPC loss; wrong/unproven PGID; EPERM census failure; new signals during cleanup. Exactly one TERM/KILL escalation owner and one shared <=10s deadline. Never infer worker absence from supervisor PGID absence. Positive control proves actual reaping and both groups absent. |
| RAW-WALL | Raw -2/-9/-14/-15, 1, other code, code/receipt mismatch, worker after7140, inner after7170, outer after7200, hashes spanning7200, missing parent raw/wall receipt all reject. Inject blocked normal IO and failure persistence; no normal extension or second ten-second cleanup. |

Required evidence per scenario: immutable tested source/protocol/pins; actual invocation; injection reached; raw process statuses; shared T0 and independent start/end; expected outcome; latch/pending observations; group/thread/writer facts; manifest bindings; external acceptance or rejection. A test ending in API/import errors or never reaching its seam is invalid evidence. Keep method/subprocess/subtest denominators separate. Fresh r3 evidence cannot inherit the historical 83 methods/66 OS scenarios or six Guard tests as current passes.

## 8. Parent handoff and actual limits

Implementation steps are finite and ordered in plan.json: parent reconciles/registers r3, implementation creates only the new preparation identity, static/source checks and targeted stdlib controls, frozen independent review, parent audit, then parent decides when to activate the exact one-run lease. This design does not activate that lease or change scheduler state. Scheduler remains disabled. There is no D3/B/E/student, extra ML smoke, seed replacement, source edit during a campaign, resumption, failed-D2 parent, or automatic retry. Historical checkpoint metadata, including inherited consumed-wall labels, is not rewritten.

`inputs-sha256.json` contains this design's own observed input hashes. Of the partial Opus manifest's 34 inputs, 33 still match; parent-owned mutable `state.json` had already changed to record this fallback. That drift is recorded, not silently overwritten or treated as immutable candidate drift. All exact user-supplied immutable hashes checked here match. Input hashes are rechecked at completion; parent ledger changes, if any, must be reported separately. No all-workspace cleanliness claim is made for this shared uncommitted checkout.

Actual evidence here is static inspection, SHA256 comparisons, JSON parsing and design consistency checks only. Real Torch/native/MPS restoration, entry equality, throughput, memory, runtime signals during native calls, training and gate passage remain untested. No lifecycle design can promise perfect observation of post-scan direct signals, transitory external mutations, uninterruptible kernel operations, or real-time scheduling. Such limits cannot turn a missing raw exit, late wall, unknown ownership, unproven absence or partial receipt into accepted evidence.
