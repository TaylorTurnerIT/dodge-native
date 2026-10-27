# D2 boundary r6 `direct-cancel-startup` diagnosis (Sonnet 5.5, read-only, proposal only)

Scope: why the ninth focused-OS case failed `fixture_guards.validate_fixture` ("owned direct reap missing" for role `worker`), what the production code should do about it, and how fixture expectations should differ between accepted closure, failed cancellation and deliberate parent death.

Nothing outside this directory was written. r6 source, capsule, state, protocol and docs were only read. No OS case, subprocess, ML/native import, checkpoint, lease or scheduler action was run. The only executed code is `dgram_close_probe.py` (in-process stdlib `socketpair`, no subprocess, single run, raw output kept).

Verified before review: all 8 entries of `parent-frozen-pins.json` match disk (controller `791038b5…`, executor `3a14d4c2…`, lifecycle `aab36d67…`); `protocol-r5-proposal.json` and `learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r5.json` both hash to `2296154b…8379`. `state.json` was read as mutable context (hash recorded in `input-hashes.json`).

## 1. What happened (evidence only)

| Evidence | Fact |
| --- | --- |
| `inner-events.jsonl` | `owned_spawn` worker pid 6944 at 512464.708939, SIGINT injected at 512464.709079 (`latch_phase NORMAL`, handlers are `ProcessLatch.handle`). |
| `campaign/inner-failure.json` | `Stop('Cancellation latched')`, first failure 512464.753178, `worker_wait: null`, `owned_worker_reaped: false`, `cleanup_complete: false`, `failure_ack_unavailable` absent, so the executor ACKed. |
| `campaign/worker.stderr.log` | Worker 6944 died at `worker_gate` `long_d2.py:1211`: `Stop: Worker ownership/session differs`. No `worker.stdout.log` bytes. |
| Receipt `ownership.worker` | `pid=pgid=6944`, `new_session_verified: true`, `parent_at_registration: 6935`, `term_sent: true`, `kill_sent: false`, `group_absent: true`. |
| Receipt `cleanup_errors` | `Unexpected private IPC loss … recvmsg … errno 54 … received_sequence 0 … fd 5`. |
| Receipt `inner_wait` | pid 6935, raw 256, rc 1, `reaped_by` 6932 (executor), observed 512464.809747. `worker_wait: null`. Census: `matches 1`, `worker_reaping_claimed: false`. |
| File mtimes (wall) | `inner-failure.json` .4407, `inner-verification.jsonl` .4411, `worker.stderr.log` .5078, receipt .5494. Worker traceback is written ≈67 ms after the inner's mandatory publication. |

### Source-derived chain (every step cites code, not conjecture)

1. `supervise_owned` blocks `life.OWNED` (`long_d2.py:1272`), `Popen`s the worker with `start_new_session=True`, then `child=owned.Child(process)`, sends `register_worker`, receives `registered`, `gate.close()`. The `finally` (`:1285`) restores the mask. The pending SIGINT is delivered there; `ProcessLatch.handle` (`lifecycle.py:105`) records it and, in phase NORMAL, raises `Stop('Cancellation latched','cancelled')` at that unmask. First failure = handler time 512464.753178, about 44 ms after Popen (registration round trip, census).
2. `except BaseException` (`:1326`): `observed_failure` → `notify_failure` (failure sent, failure_ack received) → result → `mandatory_failure(inner-failure.json)` → event set / stream close / `gate.close` → guard joins → `optional_timing` → `CHANNEL.sock.close()` → `return 1` → `final_exit`. Nowhere is `child.poll()` called again, so the supervisor never waits for the worker it spawned and exits as soon as publication and joins are done (observed reaped by the executor at 512464.8097).
3. The worker inherited the blocked mask (Popen does not reset it), so executor `signal_once(TERM)` stays pending. Python start-up plus imports took longer than the supervisor's whole failure path. When the worker reached `worker_gate` its first `require` checked `args.supervisor_pid==os.getppid()`. Two of its three clauses are proven true by the executor's own `verify_session` (pid==pgid==sid==6944). The failing clause is therefore the parent test: 6935 was already gone, so `ppid` was 1.
4. Independent support: the executor's `Unexpected private IPC loss` has `received_sequence: 0`. The supervisor channel had already delivered `register_worker` and `failure` by then (sequence ≥ 2), so fd 5 is the worker channel and the worker closed it without ever sending `worker_ready`. That matches a death at the first statement of `worker_gate` before `channel.send(worker_ready)`. The worker never completed the handshake.
5. The worker's direct parent was therefore dead before it ended, so no `waitpid` for 6944 could exist in any process. Group absence (`killpg(6944,0)`→ESRCH) was proven by the executor, but absence is not reaping.

Limit of this inference: the wall-clock/monotonic mapping is only millisecond-accurate, and I did not trace the worker live. The `ppid` explanation rests on the `require` expression plus executor-verified pid/pgid/sid plus the sequence-0 reset; it is the only reading consistent with all three. It is not a live-observed fact.

## 2. Verdict

This is a production defect in the failure path, not a fixture-only defect, and the fixture guard is correct to flag it.

- `supervise_owned`'s failure branch can preserve and reap its own child inside the existing shared cap but never tries. It records `owned_worker_reaped = child.report is not None` (always false here) and exits.
- Safety and acceptance are unaffected. The run fails, raw exit is 1, `accept_observed` rejects it, groups are proven absent, and no harness kill occurred. Worker orphaning is also bounded by the worker's own `ppid` gate and the executor's TERM/KILL. The loss is evidence strength and cleanup-ordering honesty: a spawned, registered worker is left with no direct-parent reap report and an inner that left before the child.
- The fixture wording is right for this class: a failure where the supervisor is alive and the worker was spawned should end with a worker direct-reap report. It is wrong only for a supervisor that is dead by design (§4).

## 3. Minimal supported design

Principle: the supervisor, the only possible direct parent of the worker, stays alive until it has either reaped its worker or run out the shared cleanup window, and then reports exactly what it observed. No new process, thread, hook, signal sender, allowance or reset.

### 3.1 Production change (long_d2.py `supervise_owned` only, plus two executor touches)

A. Own-child recovery (assignment boundary). `process` is assigned by `Popen` and `child=owned.Child(process)` is the very next statement, inside the blocked region. Handler delivery cannot interleave there. The fix is defensive: in the failure branch use `child = child or owned.Child(process)` when `process is not None`. `Child.__init__` cannot fail, so this adds no new failure path.

B. Bounded supervisor reap wait, placed after the mandatory publication and the non-blocking closes, before the guard joins (guard `event` already set, so joins return fast):

1. Run only if all hold: a child exists and is unreaped, the failure ACK was obtained (`failure_ack_unavailable` absent, `until` is the shared executor deadline), and phase is FAILURE.
2. Poll `child.poll()` every ≤20 ms until `reap_by = until - INNER_REAP_RESERVE` (proposed 1.0 s). Do not signal the worker or its group. `lifecycle.py` docstring says the executor is the only group-signal owner; the executor already sends TERM at once and KILL at `min(first+5, until-.5)`.
3. If `child.report` is set and no `worker_wait` message was sent earlier, send `dict(kind='worker_wait', report=child.report, t0_monotonic_hex=started.hex())` on `life.CHANNEL` with `until`, once. The existing `pump` branch already validates pid, `reaped_by==sender`, `direct_child_reaped`, raw status/returncode coherence and `t0 <= observed <= now`. No outer validator is weakened.
4. Keep a local `worker_wait_sent` flag, set to True before the existing success-path send at `:1292`. It prevents a duplicate send in the surviving-descendant flow, where the report is sent and `require(owned.absent(...))` then raises.
5. If the wait expires or `failure_ack_unavailable`, exit as today with the child unreaped. That result is stated honestly and never upgraded.
6. Why the ACK condition matters: if the executor does not know about the failure, it only learns from raw inner exit, so a long inner wait would push the executor's own first-failure time and `until` beyond the supervisor's `until`. That would break "earliest failure + 10".

C. `inner-failure.json` stays the first, immutable publication. Optionally add `worker_reap_phase: 'pending_after_publication'` to it when a live unreaped child exists. The later outcome travels only by IPC into the outer receipt. A second write of `inner-failure.json` is not proposed (extra IO inside the cap, no added authority).

D. Executor `publish_failed`: after the cleanup loop and before building `result`, add a finite drain identical in shape to the success path's `for _ in range(4): pump()`. Reason: `monitor` can see `child.report` (inner exit) between a pump and the `worker_wait` datagram that was queued before the exit; the receipt would then be built without it. `dgram_close_probe.out.json` shows that on this macOS a queued datagram is delivered before the one-shot `ConnectionResetError` (cases 1 and 2: `msg0`/`msg1` then errno 54), so the drain returns the message first.

E. Executor `pump` reset handling in failure: when `pool.until is not None`, treat `ConnectionResetError` as `peer_closed` plus an `events` row (`peer_closed_after_failure`, channel name, diagnostic) instead of `Stop`. Today failed receipts carry `Unexpected private IPC loss` as a cleanup error whenever the worker or supervisor closes a channel after failure. This is cosmetic and low risk, and a reset never counts as reaping or absence.

F. Failed receipt gains a derived `reaping` object computed only from validated evidence: `supervisor.status` is `direct_reaped` iff `self.child.report`; `worker.status` is `direct_reaped` iff `self.worker_wait` passed `pump` validation, `not_registered` if no worker group, else `unproven` with `basis`: `group_absent_only` or `supervisor_dead_before_report` when `inner_wait` exists without a worker report. No code path may write `direct_reaped` otherwise. `cleanup_complete` keeps its present definition (processes gone), and reaping evidence stays a separate fact.

### 3.2 Strongest feasible guarantee (earliest failure + 10, no OS subreaper)

- Supervisor alive and acknowledged failure: the worker is directly reaped by its true parent, proven by raw status, exact pids and deadline, whenever it can exit before `until - 1.0`. With TERM at once and KILL at `first+5`, that holds for every worker not in uninterruptible kernel state. When the cap truncates the window (failure inside the last ~10 s of the outer lifetime, `until = cap`), KILL can land after `reap_by`, so reaping may be reported unproven. This is a stated limit.
- Supervisor dead or killed: the executor can prove session, signalling and positive group absence. It can never prove a `waitpid` for a grandchild (macOS has no child subreaper). The receipt says "unproven, supervisor dead" and never fabricates a direct reap.
- Executor dead: out of scope for this receipt (no receipt exists).

### 3.3 Things this must not change

`accept_observed` (still demands both direct-parent waits, exact pids, raw status, deadlines), single `FailurePool`, `notify_failure` ACK rules, mandatory failed receipt before optional IO/guard joins/stream closes, the final `.25 s` reserve, no reset/extra allowance, no new threads/processes/import hooks, no source performance claim. In `Execution.publish_failed` the new drain sits after the cleanup loop and inside the existing `until - .25` bound.

## 4. How test expectations should differ

Expectation class must be declared by the fixture options (what the case injects), not inferred from the receipt, otherwise a missing report would justify itself.

| Class | Case selector | Supervisor | Worker | Common mandatory |
| --- | --- | --- | --- | --- |
| Accepted closure | `expected in (0,2)` | `inner_wait` direct reap, pid/raw/deadline as today | `worker_wait` direct reap, `reaped_by == supervisor pid` | Unchanged, no relaxation. Both roles in `absence`. |
| Failed, supervisor alive | default for `expected == 1` unless class below | `inner_wait` direct reap by executor | If a worker `owned_spawn` witness exists: `worker_wait` required: pid equals spawn pid, `direct_child_reaped`, `reaped_by == ownership.supervisor.pid`, `waitstatus_to_exitcode(raw)==returncode`, `observed >= spawn monotonic`. Return code not asserted (a TERMed worker may legitimately be 1, or 2 if it finished). | Mandatory failed receipt present, `accepted false`, spawn witness for every role in `ownership`, positive group absence for each, injection reached. |
| Failed, supervisor killed by design | `mutation in ('crash','SIGKILL')` on `phase` starting `inner:` (today `parent-death`) | `inner_wait` direct reap, returncode equals the injected code (7 for crash) so the fixture proves the supervisor really died | `worker_wait is None`, `reaping.worker.status == 'unproven'` with supervisor-dead basis, `ownership.worker.group_absent True`, independent harness `killpg` probe True | Same mandatory block. A present `worker_wait` here fails the test (cannot be real; would be fabricated or misattributed). |
| Failed, no child | `resource_cap` | none | none | Unchanged pre-child assertions. |

Negative controls for `validate_fixture` and `os_checks`: missing worker report in the supervisor-alive class fails; present worker report in the killed class fails; `absence == {}` fails; no receipt fails; none of these may be satisfied by `all({})`, by inferring absence from a missing file, or by treating group absence as a reap. Success acceptance tests do not change.

## 5. Static view of the six unrun cases (no runtime claim)

| Case | r6 as frozen | After design |
| --- | --- | --- |
| `direct-cancel-wait` (inner SIGTERM at first worker `poll`) | Same code path as startup: inner raises at the first poll with a live, registered worker, exits without reaping. Expected to hit the same guard failure. | Supervisor-alive class; worker reaped by the supervisor after the executor TERM. |
| `missing-worker-ACK` (worker closes channel, sleeps 2 s; inner cutoff at 0.7 s) | Inner fails on the raw-exit cutoff with a live worker; same defect. | Worker has handlers installed (gate passed), TERM interrupts the sleep, supervisor reaps. |
| `parent-death` (inner `os._exit(7)` with TERM-ignoring worker) | Guard demands `worker_wait`, which can never exist. Expected guard failure by design. | Killed class: `worker_wait None`, KILL at `first+5`, absence positive. |
| `surviving-descendant` | Worker exit is reaped and `worker_wait` sent at `:1292` before `require(owned.absent)` raises; group survives until executor KILL. Likely already passes the guard. | Unchanged. Must not resend `worker_wait` (hence the flag). |
| `normal-deadline-wedged` | Inner fails at 0.6 s with a TERM- and ALRM-ignoring worker and leaves. Same defect. | Supervisor waits until executor KILL at `first+5` (about 5.7 s total, inside the fixture's 12 s bound), then reaps. |
| `RSS-resource-cap` | No child; expected to be unaffected. | Unchanged. |

These are predictions from reading code. None has been run. The first unexpected result in the next focused stage stays a stop condition.

## 6. Residual risks and open points

- `INNER_REAP_RESERVE` needs parent sign-off; 1.0 s is a proposal sized to the guard joins (up to 2×0.5 s each, normally milliseconds because the guard event is set first). Parent decides whether a longer reserve is preferable.
- `cap` truncation (failure inside the last 10 s of the outer lifetime) can make KILL arrive after `reap_by`. The receipt then reports unproven. This is intentional and should be documented.
- `group_absent` after supervisor death may mean init reaped the orphan, but that is not asserted: the macOS zombie behavior of `killpg(…,0)` was not tested (it needs a subprocess, which was out of scope). The design deliberately does not rely on it.
- The wall/monotonic mapping in §1 is approximate. Treat the timeline claim as supporting evidence only.
- `dgram_close_probe` ran on system Python 3.9.6, not the project venv interpreter. It tests the kernel socket semantic, not `Channel`.
- Another reviewer's direct-reap consumer finding is outside this diagnosis; nothing here touches `accept_observed`.
