# Boundary r3 failure-path diagnosis (Sonnet, read-only)

Frozen r3 source, protocol and capsule were read only; their hashes match the task statement (see `input-hashes.json`). Nothing under `postovernight-long-D2-boundary-prepare-r3/` or any state, protocol or doc file was edited. No OS case, ML/native import, checkpoint, lease or scheduler action was performed. Scope is P2 (failure reporting). P1 (acceptance) is not weakened by anything below: every failure still exits 1 and `accept_observed` rejects it.

## Result

Two reproducible source bugs and one source-level design gap remain in r3. All affect only failed runs: lost or late failed receipt, masked first-failure reason, lost worker result. None can turn a failed run into an accepted one.

### F1. Monitor cleanup is starved by a `str` failure reason (confirmed)

`Execution.monitor` calls `self.fail('Inner raw failure')`, and four cutoff/age strings, at `long_d2_executor.py:238-243`. `Execution.fail` hands the `str` to `c.observed_failure`, which does `primary.first_failure_descriptor = descriptor` (`long_d2.py:~855`). A `str` has no such attribute, so `AttributeError` is raised. The monitor's blanket `except` swallows it, and the group-signaling, `group_absent` and `cleanup_complete` block (`:244-253`) sits after the call, so it is skipped on each of the 20 ms iterations for as long as the child report shows a raw exit outside (0,2).

`cleanup_complete` is set only there. The main failure handler waits on it (`:459-464`) until the shared 10 s cap, swallows the final `Stop` (`:485`), and exits 1 without calling `failure_publication`.

`discriminator_monitor.py` runs the real `Execution.monitor`, `Execution.fail` and `FailurePool` with a stub guard and a preset child report:

| inner raw | pool failed first | cleanup_complete in 1.0 s | swallowed exceptions |
| --- | --- | --- | --- |
| 0 | yes | true | 0 |
| 2 | yes | true | 0 |
| 1 | yes | false | 42 `AttributeError` |
| 1 | no | false | 43 `AttributeError`; `pool.reason` becomes the AttributeError text |
| 7 | yes | false | 42 `AttributeError` |

Correlation with the retained OS run (timing and missing files only, not a live trace): the five starved cases ended 10.0006 to 10.0025 s after the first failure and have no outer failed receipt. The three failure cases that did produce receipts (`parent-death` 2.07 s, `missing-worker-ACK` 2.05 s, `surviving-descendant` 5.46 s) ran with `outer_seconds=2`; after the outer lifetime deadline passes, `observed_failure` selects the `Stop('Absolute wall deadline')` candidate, which accepts the attribute. `outer-failure-with-timing-error` and `post-gate-persistent-mutation` have inner raw 0. So the fixtures hid the bug; a production inner failure at, say, 600 s into a 7200 s lifetime would not be hidden.

### F2. r3 descriptor default is not applied at the worker call sites (confirmed)

`FailurePool.fail(reason)` now uses the descriptor time, but two sites still pass an explicit fresh `now`:

- `worker_failure` (`long_d2.py:938`): `life.POOL.fail(error, min(candidates))`, where `candidates[0]` is `time.monotonic()` taken after `primary_error` already stamped the descriptor.
- `notify_failure(error)` with `at=None` (`lifecycle.py:228`, called at `long_d2.py:1374`) when `error` already carries a descriptor.

`discriminator_timestamp.py` (real functions): `worker_failure(RuntimeError)`, `worker_failure(Stop)` and `notify_failure(error_with_descriptor)` all raise `Stop('Failure descriptor timestamp differs')`. `notify_failure(error, descriptor.timestamp)` (inner path, `:1316`), `pool.fail(error)` and the pool's rejection of a genuinely conflicting explicit `at` behave correctly. So Execution.fail (outer) and inner supervise_owned are fine; the worker path is not.

Source-derived chain: the raise happens inside `worker()`'s `except BaseException`, after `permission['failed']=True; acknowledged_until=None`. Every later worker write is then forbidden, `long-worker-result.json` is never written, and `main()` ACKs a different reason ('Failure descriptor timestamp differs') at a later catch time. This is the r2 attempt08 signature. Neither test_10b (pool only) nor the OS fixture (`fake_worker` never enters `c.worker`) reaches it.

### F3. Failed receipt gated on cleanup completion (source only)

The loop leaves only when `cleanup_complete` is true or `remaining(pool.until)` raises, and the raise has no publication. So the receipt field `cleanup_complete` is always true when it exists, and any stall yields no receipt instead of one saying false. Fix by stopping the wait at `pool.until - 0.5` (the existing `kill_at` convention), inside the unchanged 10 s cap.

### F4. Test gaps (confirmed)

- `os_checks.case`: `absent` comes only from a written receipt or the `ownership` event emitted when one is written, so five receipt-less cases yielded `{}` and `all({}.values())` passed.
- `direct-cancel-startup`: the hook fires on the first inner `subprocess.Popen`. That is the guard's `ps` sample, 2.5 ms after the inner timer arm, with `live_owned_threads=[]`. The worker was never spawned (no `worker.stdout/stderr.log`, no `worker-events.jsonl`).
- `normal-deadline-wedged`: the worker died in `worker_gate` ~4 ms after arming and never reached its wedged loop.

### O1. Open, no cause claimed

`Truncated owned IPC packet` in `worker_gate` (`lifecycle.py:192`) covers an empty datagram, `MSG_TRUNC` and `MSG_CTRUNC`. The retained evidence has no raw length, flags or errno. A local probe showed that a closed DGRAM peer produces a one-shot `ConnectionResetError` on this macOS, not an empty read, so the empty-read explanation is unsupported. Add raw length/flags/errno to the exception message (test-only observation first) before theorizing.

## The six zero-witness cases

| case | inner | worker | positive proof that survives | classification |
| --- | --- | --- | --- | --- |
| inner-failure-with-timing-error | yes (pid 84524) | yes, pid/pgid 84533 | supervisor `waitpid` status 512 rc 2 at 510108.0072; `group_empty` probe | F1 reporting loss |
| inner-final-alarm | yes (85463) | yes, 85472 | `waitpid` status 512 rc 2 at 510124.3918; `group_empty` probe | F1 reporting loss |
| direct-cancel-startup | yes | no (absence by missing files) | none needed for worker | expected no-worker; receipt loss is F1; label wrong (F4) |
| direct-cancel-wait | yes | yes, pid not retained | worker stderr traceback (process exit inferred) | F1; worker death not positively witnessed |
| normal-deadline-wedged | yes | yes, pid not retained | worker stderr traceback | F1 plus ineffective fixture, O1 |
| RSS-resource-cap | no | no | receipt: `ownership {}`, `inner_wait null`, no campaign dir; receipt 7 ms after first failure | expected early no-child; correct |

For none of the five inner-existing cases is supervisor-group absence positively witnessed; only executor raw exit 1 and the harness's lack of a kill. Do not state survivors or all-absent for them.

## Mandatory publication and stale receipts (items 3 and 4)

`failure_publication` writes the mandatory receipt before optional timing, each in its own `try` (`long_d2.py:909-920`; test_12). That ordering holds. In the actual case flow it is unreachable for five cases because of F1/F3, not because of optional telemetry. The RSS case shows it working end to end (receipt present, `outer-verification.jsonl` present afterward).

`discriminator_acceptance.py` against frozen `accept_observed`: a stale accepted receipt with raw 1, a failed receipt with raw 0 or 1, an empty receipt with raw 1, and an accepted receipt with raw 2 but no parent digests all return `False`. P1 needs no change. One unconfirmed observation: a pre-existing receipt path trips the single-use check at `:351`, and the failed receipt then replaces it via `replace_json`; the stale bytes are lost as forensic evidence. Parent policy decision, not a defect against the stated acceptance rules.

## Minimal proposed fix

See `proposed-fix.diff` (applied only to `patched-candidate/`, a copy inside this directory):

1. `long_d2_executor.py`: construct `c.Stop(msg, outcome)` at the six string sites (`cancelled`, `wall_guard` x3, `resource_stop`, `publication_failure`) and add `if not isinstance(error, BaseException): error = c.Stop(str(error), 'safety_stop')` at the top of `Execution.fail`.
2. `long_d2.py` `worker_failure`: drop the local `candidates` block and call `life.POOL.fail(error)`; `primary_error` already folded guard, latch, deadline and catch times into the descriptor.
3. `lifecycle.py` `notify_failure`: when `at is None` and the error has a descriptor, use `descriptor['timestamp']` as `at`.
4. (F3, not in the diff) bound the cleanup wait at `pool.until - 0.5` and publish with the true `cleanup_complete`.

Rerunning both discriminators against the patched copy: monitor cleanup completes with 0 swallowed exceptions for raw 1 and 7 and keeps the reason `Inner raw failure`; the three worker/notify sites no longer raise; explicit-conflict rejection is retained. The 10 s cap formula, minimum-of-observations logic and explicit cutoff `at` values (t0+7140, t0+7170, t0+7200) are unchanged. No timestamp is fabricated or reset.

## Regressions worth adding (after the frozen review)

1. Monitor starvation: real `Execution.monitor` with child rc 1, 7 and -15 and each string site; assert `cleanup_complete` within 0.5 s, zero swallowed exceptions, reason preserved. (`discriminator_monitor.py` is the body.)
2. `worker_failure(RuntimeError)` and `worker_failure(Stop)` with a socketpair ACK peer: no raise, `pool.first_global['timestamp']` equals the descriptor, `permission['acknowledged_until']==pool.until`. Same for `notify_failure(error_with_descriptor)`. (`discriminator_timestamp.py`.)
3. OS: inner nonzero raw exit with a long outer lifetime (not `outer_seconds=2`); require a failed receipt in well under 10 s with both groups witnessed absent. Make the harness fail when `receipt_available` is false for a case that registered a child, and assert `ownership=={}` and no campaign dir for pre-child cases instead of relying on `all({})`.
4. Anchor `spawn-before-registration` on the worker `Popen` (argv contains `worker`), and require a worker marker in `normal-deadline-wedged` before the case counts.
5. F3: stall cleanup (a group that never reports absent) and require a failed receipt with `cleanup_complete=false` before `until`.

## Evidence limits

No live trace of the monitor in the OS run exists; F1 is tied to those runs by timing, missing files and the three-case exclusion argument above. No PID or PGID is retained for `direct-cancel-wait` or `normal-deadline-wedged` workers. The patched copy was exercised only by the discriminators, not by OS cases or the 21 unit methods.
