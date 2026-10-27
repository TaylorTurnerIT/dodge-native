# r9 IPC close-order discriminator (Sonnet, r2): verdict `inconclusive`

One wrapper invocation (raw exit 0, 1.44 s, within 60 s, all owned groups proven absent). Script sha `1a0ba4e9…`, wrapper sha `baf0cfcb…` (frozen in `plan.json` before the run; the wrapper refuses to run on a mismatch). Interpreter was the project venv alias with `-B`, a fresh empty `PYTHONPYCACHEPREFIX`, and `PYTHONDONTWRITEBYTECODE=1` for wrapper and children. Required context was read. The 8 frozen pins and the parent IPC assessment sha `a9c5e0fc…` all match (`input-hashes.json`).

## Result

| | case 1 legacy close, delayed registration | case 2 (intended: close right after Popen) |
|---|---|---|
| worker `worker_ready` observed by executor | yes, positive | yes |
| registered ACK held until | t_ready + 0.4 s, then registered sent BEFORE start_ack | same |
| executor `start_ack` send (.2 s timeout) | ok, 48 B, dt 22 µs | ok, 48 B |
| worker start_ack recv | `start_ack`, 48 B, flags 0, no ancillary | same |
| zero-byte flags0 | no | no |
| ACK send timeout | no | no |
| supervisor gate close | after barrier release; pre-close fd 3 open, post-close EBADF (errno 9) | **same, see defect below** |

Rows come from `probe-stdout.json` and `probe-out/*.jsonl`.

## Defect in my probe (disclosed; no rerun per rules)

In `supervisor()` I tested `case == 'case2_early_close'`, but the real case name is `case2_early_close_after_popen`. The early-close branch never ran. Case 2 therefore ran the same retained-until-barrier schedule as case 1: gate closed after `ack_attempt_done`, not right after Popen. The `gate_closed_right_after_popen` event is absent from `case2_*.jsonl`, which confirms it. **Case 2 is an invalid treatment, so the "does immediate close remove the symptoms" half is untested.** The result is two identical runs of the case 1 schedule, both clean.

A first wrapper launch aborted at the `plan.json` load because my `sed` failed and no plan existed. The probe script never executed (no `probe-out`). Evidence is in `prelaunch-aborted/`. The only edit before the real run was `rec()` using `setdefault('pid', …)` for owned-PID bookkeeping. This is bookkeeping, not transport.

## What this supports

- Under production message order (registered ACK before start_ack) with a deliberate 400 ms registration delay and the supervisor gate copy retained until after the ACK attempt, the paired symptoms did **not** reproduce in either run. Delayed supervisor close is therefore **not sufficient** to explain the zero-byte flags0 and ACK timeout under this schedule.
- The earlier D2 reproduction differs in ways not isolated here. The variables include the registered ACK being sent before `worker_ready` was observed, no 400 ms hold, and the supervisor gate retained until worker exit. One run each, so this is not a rate.
- Cause of the r9 symptoms stays **unproven**. I make no claim about kernel mechanism, rates, or whether old r9 had this schedule.
- Recommendation for parent: do not adopt the early-duplicate-close transport change on this evidence. It is not supported here, and it is not refuted either, since the treatment was not applied. Any further discriminator needs a new authorization. The monitor/cleanup fixes (independent safety duties, `gate_ack_attempted` separate from `gate_acked`, latch-before-retirement, late-evidence pool tightening, fixture phase guards) stand on their own source evidence and are untouched.

## Limits

Synthetic probe with an artificial barrier in case 1 (not a production delay). Single run. No production edit, OS rerun, ML import, lease, scheduler, commit, PR, or deploy. Source ownership released; no auto follow-on.
