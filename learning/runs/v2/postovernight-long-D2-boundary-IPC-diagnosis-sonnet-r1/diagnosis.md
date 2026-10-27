# r9 post-gate-persistent-mutation: IPC and cleanup-starvation diagnosis (Sonnet, read-only)

Scope: diagnosis only. Nothing outside this directory was written. No OS case, no ML import, no lease/scheduler/commit. Pins verified before proof: controller `288fdec9…`, executor `fd603a1c…`, lifecycle `aab36d67…`, protocol-r6 `96c170a5…` (see `input-hashes.json`). Broad source audit is Codex's; this covers only the transport and monitor questions.

## 1. What the retained evidence shows (facts)

Timeline (monotonic, case `post-gate-persistent-mutation`):
- 562.772 inner spawns worker (pid 23357). 562.884 worker timer event. Worker sends `worker_ready` on fd 3 (the passed gate endpoint).
- Executor `pump` receives `worker_ready` and calls `worker_channel.send(start_ack)` with `remaining(deadline, .2)`. That send raised `TimeoutError('timed out')`; outer `first_local_failure` = 563.0854, which is 0.2 s after the send began (~562.885).
- 562.9106 worker raw exit rc1 (reaped by supervisor 23342). 562.9109 inner `first_global_failure`. The worker stderr: `Truncated owned IPC packet … raw_length 0, flags 0, ancillary_records 0, expected_sender 23339, fd 3, received_sequence 0`. That is: the first recvmsg on the gate returned an empty datagram, no error, no truncation flag.
- The inner then timed out waiting for `failure_ack` (`errno null` = socket timeout), read a missing `long-worker-result.json`, and could not report.
- Outer cleanup_errors: one `Unexpected private IPC loss … errno 54 … fd 3` (executor-side supervisor channel, after the supervisor died) followed by seven `OSError(39, Destination address required)`. 39 is the start_ack resend to the worker channel after its peer was gone (pump retries `start_ack` every pass because `gate_acked` is never set).
- The injection event fired at 572.68 with `latch_phase=FAILURE`, after the unrelated startup failure. See section 5.

## 2. Initial transport failure (task item 1)

Supported by reproduction: **a zero-length recvmsg on the worker and a 200 ms start_ack send timeout both occur when a second process still holds a reference to the shared gate endpoint while the worker does its ready/ack exchange.** Not proven: that this is what happened in r9.

One preregistered probe invocation (`ipc_probe.py`, sha `19b33802…`, venv python 3.12.15, `-B`, fresh `PYTHONPYCACHEPREFIX`, raw exit 0, ~1 s). Results (`probe-stdout.json`, `probe-out/D1.jsonl`, `probe-out/D2.jsonl`):

| case | result |
|---|---|
| A plain socketpair | ready/ack both delivered |
| B dup then close duplicate (original kept) | delivered |
| C SCM_RIGHTS same process, sender copy closed while in flight | delivered |
| D1 cross-process: executor → supervisor (SCM_RIGHTS) → worker (pass_fds); supervisor closes its gate copy *before* the worker's exchange | delivered; ack_recv `start_ack` 9 bytes |
| D2 same as D1 but supervisor keeps its gate copy open through the exchange | worker `ack_recv`: ok, `raw_length 0, flags 0, anc 0` in 0.01 ms; executor `start_ack_send`: `TimeoutError`, errno None, 201 ms |

D2 reproduces both r9 symptoms exactly (flags 0, no ancillary, immediate empty datagram; executor send timeout of the 0.2 s send window). So:
- The empty datagram is **not** evidence of peer close by itself. The earlier startup-reap probe (`…startup-reap-diagnosis-sonnet-r1/dgram_close_probe.out.json`) showed peer close gives one `ConnectionResetError` (errno 54) then timeouts, never a 0-byte read. Keep that distinction.
- Plain socketpair, in-process dup/close, and same-process SCM_RIGHTS transfer are exonerated for the specific cases run (single run each).
- The discriminating factor in D1/D2 is a still-open copy of the endpoint in the supervisor process during the exchange. Kernel mechanism is unproven. I did not isolate why a retained cross-process copy yields an empty read and a blocked peer send.

Why r9 may match D2 (plausible, unproven): in production `gate.close()` in the supervisor (`long_d2.py:1262-1285`) runs only after the executor's `registered` ack, and the ack is sent after `owned.verify_session` in `pump` (`long_d2_executor.py:300-307`). The worker does its own startup (~110 ms here) and sends `worker_ready`. If the ack is later than `worker_ready`, the supervisor still holds the endpoint at exchange time, which is the D2 condition. I did not measure `verify_session` latency or the supervisor close time in r9; the retained events do not record the supervisor close. The six earlier cases passing is consistent with an intermittent race but is not proof.

SCM_RIGHTS / pass_fds / close order as the production path: matched in D1/D2 (rights received, `pass_fds=(gate,)`, `start_new_session=True`, sender copy closed right after send). Outer IPC lock: not a cause of the send timeout; `pump` is serialized by `ipc_lock`, and the timeout is the socket's own 0.2 s window.

## 3. Cleanup starvation (task item 2)

Source cause (certain from source): `monitor` (`long_d2_executor.py:234-277`) runs `pump()` first inside one broad `try`. Any exception from `pump` jumps to `except`, which only (a) records a failure if none yet, or (b) `os._exit(1)` if `now >= pool.until`. Everything after `pump` is skipped: cancel forwarding, guard failure, worker/inner/outer cutoffs, `child.poll`, TERM/KILL, `group_absent`, `cleanup_complete`, and the normal `os._exit` at `pool.until`. After the supervisor and worker died, `pump` raised on every 20 ms pass (errno 54 once, then EDESTADDRREQ via the unconditional start_ack retry), so all duties stayed starved until the cap-time `os._exit`. This is why the outer receipt says `cleanup_complete false, TERM/KILL false, ownership absence false` while independent probes later found both groups absent (the processes died on their own; absence was never established by the executor).

Model: `starvation_model.py` (sha `068c2f95…`, stdlib only, <1 s, structure only, not production code). Same persistent pump error, same 0.5 s deadline: current structure → 22 pump errors, 0 TERM, 0 KILL, 0 absence checks, deadline exit only via the except branch; isolated structure → duties run every pass (22 each). This reproduces the control-flow gap, not the live r9 trace. No live trace is claimed.

Initial transport failure and the cleanup reporting gap are independent defects: the first is the worker's empty read plus start_ack timeout; the second is that fallible IPC starves resource/cancel/deadline/reap/absence work. Fixing only one leaves the other.

Note: the first failure in the evidence is the worker's raw exit (observed 562.910627), caught by inner at 562.910867; the executor's own TimeoutError at 563.0854 is later. Earliest-failure retention (`FailurePool.fail` keeps `min`) already handled that correctly.

## 4. Proposed minimal structure (source proposal only; no patch made)

Monitor, same file, same pool/allowance semantics:
1. Per-pass order: (a) cancel/latch handling, (b) guard failure, (c) cutoffs/sample age, (d) `child.poll` + `raw_inner_failure`, (e) when `pool.until` set: TERM, KILL at existing `kill_at`, `owned.absent`, `cleanup_complete`, deadline `os._exit`, (f) last: `pump`.
2. Each of (a)–(f) in its own `try`. A caught error calls `self.fail(error)` only if no failure exists, otherwise appends to a bounded `cleanup_errors` list (dedup by `repr`, cap e.g. 8) and continues. Never `continue`/skip the later blocks. The deadline `os._exit` check must also run in a `finally`-equivalent outside any try that can raise.
3. Mark a channel lost on the first `ConnectionResetError`/`EDESTADDRREQ` (set `peer_closed`, or per-channel `send_failed`). Do not retry `start_ack` after the first send exception: set `worker['gate_acked']='failed'` once (never retried, mirroring the worker_wait rule). That removes the unbounded send retry loop.
4. No new allowance, ACK retry or time added; all within `min(previous, earliest_failure+10, T0+7210)`. Earliest failure stays the min.

Transport, conditional on the discriminator below (not a rewrite):
- Candidate: the supervisor closes its gate copy immediately after `Popen` returns (the child has already inherited it), instead of after the `registered` ack. This removes the D2 window by construction. It is a candidate only; the `registered` ack still guards worker identity (pgid/session verification).
- Keep the executor-side gate send timeout; treat a zero-length datagram as a distinct diagnostic `empty_datagram`, not peer close.

## 5. Fixture guard requirement (item 4)

`post-gate-persistent-mutation` (`outer:receipt-before`, `mutation=input`) was intended to fire in the normal post-gate path. It fired at 572.68 with `latch_phase=FAILURE` after an unrelated startup failure (first_global 562.9109 precedes the injection by ~9.8 s). `fixture_guards.py:62-63` only asserts that *an* injection event with that phase exists; `os_checks.py:50,67` only asserts `fired`. Exit 1 matched expected 1, so the guard accepted a wrong-path failure. Do not count r9's `injection_reached=true` as a correct injection.

Required guard (source proposal): for each phase-injection case record pre-injection milestones in events (e.g. `start_ack_sent` / `gate_acked`) and require, at injection: `latch_phase` equals the scenario's expected phase (not `FAILURE`), no `first_global_failure.timestamp` earlier than the injection, and the post-injection failure must be attributable to the mutation. A case that reaches the phase only after an independent failure is `fixture_precondition_failed`, not pass and not a counted injection.

## 6. Discriminators and gates (no automatic relaxation)

Next discriminator (one preregistered probe, not an OS retry): extend D1 so the executor delays the `registered` ack by 400 ms (worker `worker_ready` arrives before the supervisor's `gate.close()`), plus D3 closing the gate right after `Popen`. If D1-delayed reproduces the empty read and D3 does not, the race is confirmed and the early-close fix is justified. If D1-delayed passes, the production cause stays unproven and the monitor restructuring still stands on its own evidence.

Regression gates (all keep existing integrity, success consumer, ownership, earliest-failure+10, 7200 / 7140 / 7170, 0.5 s resource and separate 6 GiB caps):
1. Unit: monitor with a `pump` that raises forever must still perform TERM, KILL, absence and deadline exit within `pool.until` (the model in `starvation_model.py` is the template; use the real `monitor` via the existing factory hooks).
2. Unit: start_ack send exception → exactly one send attempt, `gate_acked` failed, no resend.
3. OS fixture: late `registered` ack (delay > worker startup) must either pass with the early-close change or fail deterministically as an empty-datagram diagnostic, never as an unclassified cleanup gap.
4. Fixture guard in section 5, with a negative unit test that feeds r9's injection event (`latch_phase=FAILURE`, earlier first_global) and expects rejection.

## 7. Evidence limits

- One probe invocation; each case ran once. No repetition, so D1-vs-D2 is a single paired observation, not a rate.
- The first launch attempt of the probe failed before execution (`timeout` binary does not exist; raw exit 127; `probe-wrapper-failure-exit.txt`). The script never ran then; it was launched once, unwrapped, as `probe-exit.txt`. Disclosed so the "one invocation" count is auditable: one script execution, two shell launches.
- Probe passing for A/B/C/D1 does not exclude unmeasured races or attest production. Kernel mechanism for D2 is not isolated.
- r9 supervisor close time and `verify_session` latency are not in the retained events; the r9-matches-D2 link is plausibility only.
- Starvation model is control-flow structure, not a live trace.
- No safety or acceptance bypass was found or claimed. Nothing here is consumer proof.
- Not read in full, because of the 600 s budget: `implementation-plan-v2.md`, `SPEC_PRIVILEGED_VIT_RL.md`, `state.json`, prior Sonnet reconciliations, and `owned.verify_session`. Only the r9 source above, the failing case files, `parent-result-r9.json` (head) and the earlier `dgram_close_probe` output were read. Parent should check the proposal against accepted boundary policy before use.
