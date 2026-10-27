# r10 wedged-worker direct-reap failure: escalation ordering design (source proposal only)

Scope: read-only design by the Sonnet sub-agent. Nothing frozen was edited. No OS, probe, stress, startup, ML, lease, scheduler, commit, PR or message action. Only files in this directory were created. The model results are a fake-clock/fake-process proof, not OS closure.

## 1. Verdict

Root cause: `Execution.monitor` evaluates one KILL condition, `now >= min(pool.first+5, pool.until-.5)`, for every role in `groups` (`long_d2_executor.py:299-301`). The worker group and the supervisor group are therefore KILLed in the same tick. The supervisor is the only process that can obtain and relay the worker's direct `waitpid` report (`worker_wait`, validated in `pump`, `long_d2_executor.py:362-372`). It is still inside its best-effort reap loop (`long_d2.py:1396-1416`, `reap_by = pool.until - 1.0`) when it is killed, so the report is never produced. The receipt then says `reaping.worker = unproven / supervisor_dead_before_report`, and the fixture predicate (`fixture_guards.py`, `direct('worker')`, "owned direct reap missing") fails honestly.

Smallest supported fix: keep the worker KILL at its original cutpoint, keep supervisor TERM immediate, and gate the supervisor KILL on (a) a validated `worker_wait`, or (b) the supervisor leader already being direct-reaped, or (c) no registered worker, or (d) the existing latest bound `until-.5`. This is an executor-only change confined to `Execution.monitor` plus one new method, `Execution.kill_due`. The diff is `proposed-executor-escalation.diff` (not applied anywhere).

## 2. Confidence against retained r10 events

Retained: `attempts/attempt-03-focused-OS/cases/normal-deadline-wedged/`.

| Fact | Source | Reading |
|---|---|---|
| `T0=516539.26029925`, `first=516539.86029925` (T0+.6 worker cutoff), `until=516549.86029925` | receipt | Pool is `first+10`; `first+5=516544.86029925`; `until-.5=516549.36`; K_w = first+5 |
| `wedged_entry` 516539.6152, gate ACK 516539.6150 | worker/outer events | The worker is in the intended ignore-TERM loop |
| `inner-failure.json`: shared `cleanup_until` = 516549.86029925, `worker_wait=null`, `owned_worker_reaped=false`, no `inner-reap-diagnostic.json` | campaign dir | The supervisor ACKed the same pool and then never wrote its optional diagnostic: it died first |
| Supervisor direct wait raw 9 / rc -9 at 516544.8948 (outer `inner_direct_wait_observed` 516544.8958) | receipt, events | Killed by the executor about 34.5 ms after K_w, within one 20 ms tick plus poll latency |
| `ownership.*.term_sent` and `kill_sent` true for both roles | receipt | Both groups were KILLed; the receipt does not record which tick |
| `monitor_error` `Unexpected private IPC loss`, `received_sequence=1`, `fd=5`, errno 54 | receipt events | Consistent with the worker gate channel (one packet, `worker_ready`, already received) being reset when the worker was KILLed. This is inferred, not proven |
| Both groups positively absent, `cleanup_complete=true` | receipt, observed-command | Absence is real; it is not a direct wait |

Model replay: the real `Execution.monitor/pump/fail` plus the source-extracted inner reap block, on r10 numbers, reproduces the failure exactly. Both groups are KILLed in the same tick (516544.860299), `worker_wait` is None, and `validate_fixture` raises exactly `owned direct reap missing`. The retained worker-gate IPC loss monitor_error also appears. Under the proposed ordering the supervisor relays the report 20 ms after the worker KILL and is KILLed 40 ms after it (`worker_wait.reaped_by == supervisor pid`). `validate_fixture` passes and cleanup completes at first+5.08 s, against `until = first+10`.

Confidence:
- Same-tick KILL is the trigger: about 90%. The code is unambiguous and the timestamps fit. Not directly observed: whether the supervisor was in its poll loop at 516544.86. It had ACKed and `reap_by` was 516548.86, so it should have been.
- Proposed order passes the 14th OS case: about 75%. The nominal margin is about 4.5 s against about 0.1 s of work, but real OS timing is unmeasured.
- Gate shape is minimal and safe: about 85%.

## 3. Proposed ordering (exact)

- Worker (and any non-supervisor) group: TERM immediately; KILL at `K_w = min(first+5, until-.5)`. Unchanged.
- Supervisor group: TERM immediately, so its failure and ACK path runs. KILL at the first tick where `now >= K_w` AND one of:
  1. `worker_wait is not None`. Set only by `pump` after `owned.validate_report(before=pool.until)`. Reason `validated_worker_wait`.
  2. Supervisor leader already direct-reaped by the executor (`child.report` set). Reason `supervisor_reaped`. This preserves the genuine-parent-death behavior, and the group still gets KILLed for descendants.
  3. No registered worker (`'worker' not in groups`). Reason `no_registered_worker`. No valid report can exist.
  4. `now >= until-.5`. Reason `latest_bound`. The unchanged latest KILL bound. This covers an unresponsive supervisor, lost IPC or ACK, a cap-limited window and a late observation.
- `kill_due` reads the current `pool.first/pool.until` on every tick, so earlier ACK tightening moves K_w and the latest bound automatically.
- The gate runs under `monitor_duty('KILL_gate_'+role)`. If it raises, `due` stays True and the KILL goes out (old behavior). The `os._exit(1)` at `pool.until` stays outside every fallible duty and is untouched.
- Each role appends one `dict(kind='escalation', role, reason, monotonic)` to `events`, which the failed receipt already includes. No schema change.

Not changed: success acceptance, guard sampling (max .5 s; .05/.15 intervals), the 6 GiB RSS/MPS limit, the 7200/7140/7170 limits, the pool rule `min(previous, earliest failure+10, T0+7210)`, the publication reserve .25, and the supervisor source. No new signal owner, process, thread or subreaper. No wait is fabricated from absence. The IPC reset classification is left as is, following the prior reconciliation's deferred-change note. The inconclusive early-close probe is not adopted, and transport stays unknown.

## 4. Case analysis (answers to the evaluation list)

- Explicit `until-.5` fallback versus inner `reserve 1.0` / outer `.25`: the supervisor stops reaping at `until-1.0` (its own view) and publishes within `until-.25..until`. Using `until-.5` (the existing latest KILL) as the supervisor fallback leaves .5 s after the supervisor's own reap window for it to exit, and .5 s for executor absence and receipt. The model finishes cleanup 0.46 s before `until` in the unresponsive case. A fallback earlier than `until-1.0` would cut a still-legitimate reap window; one later than `until-.5` would break the old latest-KILL bound. Recommended: `until-.5`, with no new constant.
- Eligible at first+5 only once a validated wait exists, otherwise deferred to `until-.5`: yes, this is the proposal. Tradeoff: a hung supervisor now lives up to 4.5 s longer (still inside `until`); the model's unresponsive cleanup ends at first+9.54 s instead of about first+5.1 s. Killing right after the validated wait drops the supervisor's optional `inner-reap-diagnostic.json`. It was already absent in r10, and the receipt carries `worker_wait`. The alternative, waiting for the supervisor's natural exit up to the latest bound, keeps more diagnostics and a longer tail. It needs no new constant, so it is a defensible variant; it is not the default.
- Late or earlier ACK tightening: the executor pool tightens and the supervisor's pool does not (no second ACK). If `U_exec < U_sup - .5`, the executor may KILL a supervisor that is still legitimately waiting. The report is lost and reaping is truthfully unproven. Modeled: tightening to `first-0.2` after K_w still relays.
- Cap truncation: in the normal protocol `first <= T0+7200` always, because the Outer cutoff duty sets `first=7200` on its first execution. Cap truncation therefore reduces to observation lateness. Modeled: observing at F+6.5 s relays; observing at or after `until-.5` KILLs both in the same tick and stays unproven.
- Worker or descendant signalling errors: unchanged. `signal_once` records `signal_errors`, `monitor_duty` isolates failures, and group absence is probed independently. The supervisor stays bounded by the latest bound.
- Missing worker registration or recovery unknown: no gate (reason `no_registered_worker`). The census recovery path and `worker_reaping_claimed=False` are unchanged.
- Lost IPC or ACK: the supervisor's send fails once with no retry (existing code). Either it exits by itself and is reaped, or it is KILLed at the latest bound. Unproven.
- Genuine parent death: supervisor already reaped (rc 7), so no deferral. Signal timeline identical to frozen; worker_wait None; unproven / `supervisor_dead_before_report`. It is not relabelled for a pass.
- Worker report queued but not pumped: the IPC duty runs every tick, and the supervisor sends by `until-1.0`, so at least .5 s (about 20 ticks) of pumps precede the latest bound. Optional hardening H1, not in the minimal patch: at the latest bound, if the supervisor channel is readable and `now < until-.4`, defer one tick; hard stop at `until-.4`. A pre-KILL blocking pump is rejected because it needs `ipc_lock` and could delay the signal.
- Hazard to keep: `pump` iterates `[super_channel, worker_channel]`. The persistent worker-gate ECONNRESET aborts the pump only after the supervisor channel is processed. The model shows `worker_wait` still arrives while that error recurs (A13). Do not reorder; add the guard test.

## 5. Original 15 scenarios (static reasoning; the OS stage was not rerun)

Only `normal-deadline-wedged` changes behavior.
- Accepted cases (normal-closure, normal-fake-gate, both optional-timing-error cases): `pool.until is None`, so the escalation block is never entered.
- Failure cases where the worker was already reaped and relayed before injection (inner-failure-with-timing-error, outer-failure-with-timing-error, post-gate-persistent-mutation, inner-final-alarm) and where the worker dies on TERM and the supervisor relays within ms (direct-cancel-wait, missing-worker-ACK, surviving-descendant): the validated wait arrives at or before K_w, or the supervisor is already reaped. KILL timing is unchanged or within ticks.
- direct-cancel-startup: the worker may be unregistered, so `no_registered_worker` or `supervisor_reaped` applies and KILL timing is unchanged.
- parent-death: supervisor reaped (rc 7). Identical (A6).
- RSS-resource-cap: no groups. Unchanged.
- The `CASES` list, options, fixture classes and limits are unchanged. The wedged case still has `outer_seconds=1.5`, a maximum wall of 12.0 s and a modeled completion of about 5.7 s, as in r10.

## 6. Regression design

See `plan.json.regression_design` and `model_harness.py`, which is the reference. All 18 model assertions pass (`model-results.json`, `assertions`). The old executor FAILS A1/T1 (same-tick KILL, missing worker wait, fixture text `owned direct reap missing`), and the proposed executor passes. The assertions cover:
- the unresponsive-supervisor fallback;
- earlier-ACK tightening;
- lost IPC;
- genuine parent death identical to the frozen behavior;
- worker dying on TERM, with no KILL at all;
- both late-observation cases;
- no conflation between `direct_reaped` and absence, in every scenario for old and new;
- only `Execution.monitor` and `Execution.kill_due` differing by AST;
- the retained worker-gate IPC loss reproduced without starving the supervisor channel.

T10 (the gate raising defaults to KILL) is specified in `plan.json` but not in this model. The existing `test_r10` and `test_repairs` monitor tests are not touched. They use reaped-supervisor cases, which this gate treats as immediate KILL. They were not run here.

## 7. Limits

- The model proves ordering and classification logic against the real executor, inner and receipt code with fakes only. It does not prove OS behavior: macOS datagram semantics after peer close, zombie timing and scheduler latency remain unmeasured. The model pessimistically drops unreceived datagrams when the supervisor dies.
- It does not claim the 14th OS case, the final RSS case, stress, startup rehearsal or training would pass.
- The retained r10 verdict remains a failed OS stage. A distinct implementation, tests and the parent-ordered validation are needed before any new stage. No auto-follow-on is started.
