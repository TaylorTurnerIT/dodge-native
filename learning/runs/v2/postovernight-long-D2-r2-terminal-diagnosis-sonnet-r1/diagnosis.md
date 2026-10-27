# D2 r2 terminal diagnosis (read-only, proposal only)

Started 2026-10-25T07:14:53Z (epoch 1792912493). Sonnet 5.5 sub-agent. No source/state edits, probes, ML imports, evaluation or training. The failed run stays failed: outer raw exit 1, mandatory `integrity-summary.json` absent, frozen `accept_observed` false. Nothing here accepts it or invents the missing summary or census row.

## 1. Observer-triggered shutdown vs worker completion

### Proved by retained evidence

| Fact | Source |
|---|---|
| Worker finished its work: `outcome=budget_closed_below_gate`, 384 phase updates, final checkpoint evaluated, `worker_wall_seconds_lower_bound=6776.166064` so result written at or after monotonic 532106.705582 (T0 525330.539518 + bound). Last worker resource sample 532106.574788, last full integrity pass 532106.589792, 1355/1355 boundaries passed, no latched failure. | `long-worker-result.json` bounded fields |
| Last observer census with an intact worker row: 532106.419676 (13,197 rows retained; none shows an owned-identity mismatch, because a mismatch raised before `emit`). | `process-observations.jsonl` |
| Observer raised `RuntimeError('Owned identity changed: worker')` at 532106.958840. The raising line is `execute_once.py:88`: one `need(all(row[k]==g[k] for k in ('argv','pgid','start_time')))` over three keys, with a message that names only the role. `emit()` of the census row comes after that `need`, so the mismatching row was never written. | `observer-errors.jsonl`, `execute_once.py:84-90` (`emit` at line 90) |
| Supervisor direct `waitpid` of worker: 532106.978796, `raw_wait_status=512`, returncode 2 = `expected_exit_code 2`. That is 19.96 ms **after** the observer error. | `inner-failure.json` `worker_wait` |
| Observer SIGTERM to outer: 532107.009341 (record precedes forward). Outer cancel latched 532107.009817; supervisor local cancel 532107.028985; then `Unexpected private IPC loss` (errno 54), inner reaped 532107.205710, outer reaped 532107.323542, raw 256. First global failure = cancel; no integrity summary written. | `signals.jsonl`, `execution-result.json`, `raw-wait.json` |
| First emitted census after the error (532107.085798) shows outer and supervisor only; worker row gone. | tail of `process-observations.jsonl` |

Chain: worker completes and exits 2 (expected) → one observer 0.5 s sample lands in the exit window → identity compare raises on the worker row → observer's own error handler SIGTERMs the outer (`execute_once.py:204-207`, by design) → outer/supervisor cancel latched in the middle of terminal bookkeeping → IPC lost → receipt failed, summary never written. The shutdown was observer-caused, not worker-caused. The worker result and 25 certificates are intact and parent-verified, but frozen acceptance still requires the summary and exit 0 path, so acceptance stays false.

### Exit/zombie transition hypothesis (strongly supported, one link unproven)

Argument:
1. **The matched row was the worker, not a PID-reuse stranger.** The row existed (`row is not None`) in a snapshot taken before 532106.958840. The supervisor reaped pid 10203 only at 532106.978796. A POSIX pid cannot be reallocated before its parent reaps it, so every ps row for 10203 in that window is the worker (live, exiting or zombie). Independent corroboration: the pid counter was near 3.7k-4.0k in the final seconds (child pids 3757→4023), far from 10203. This is a deduction from retained times, not a retained row.
2. **Host `ps ... args` renders exited/in-transition entries as a parenthesised name.** The retained census contains 11,716 `(ps)` and 1,641 `(python3.12)` rows (children of owned leaders, `pid != pgid`). A leader never showed this form in 13,197 rows because leaders stayed alive 6,776 s.
3. **Supervisor reaps on a 20 ms poll** (`long_d2.py:1363`, `time.sleep(life.remaining(started+WORKER_SECONDS,.02))` in the `child.poll()` loop), so an exit-to-reap window is tens of ms. The observed error-to-reap gap is 19.96 ms. A 0.5 s sampler with a ~20-30 ms window lands once with probability a few percent per run, matching a single event in 6,776 s.

Unproven: which of `argv`/`pgid`/`start_time` differed, and that `ps` showed `Z`. `ps` rows have no `stat` column (`execute_once.py:50`), and the mismatching row was not retained. Best guess is `argv`→`(python3.12)`; keep it a hypothesis. Alternatives not excluded by evidence: a transient `ps` read of argv/lstart during teardown while still not a zombie (same class: process exiting); a true pgid/start change is implausible for an unreaped child but not directly excluded.

### Smallest future observer correction (not implemented here)

Keep identity strictness; change only what is recorded and one narrow, bounded exit-transition case in `observe()` of a **new** observer (frozen executor, acceptance rules and old metadata untouched):

1. Add `stat=` to the census (`ps -axo pid=,ppid=,pgid=,lstart=,stat=,rss=,args=`) and parse it.
2. Compare keys separately. **Before any raise**, persist the full observed row, registered identity, per-key diff and ps timestamp to a new append file (`identity-mismatch.jsonl`, fsync). The mismatching-row loss that made this run undiagnosable cannot recur.
3. Treat a mismatch as `owned_exit_transition` (log, no SIGTERM) only if **all** hold: same pid, ppid, pgid and start_time as registered; `stat` begins with `Z`; argv is a single token `(<name>)`. Anything else (different start_time/pgid/ppid, non-`Z` state with changed argv, multi-token argv) stays fatal exactly as now. PID-reuse protection is unchanged because pid+ppid+pgid+start_time must still equal the registration.
4. Failure deadline preserved: a transition may persist at most 2 consecutive samples (1.0 s) and must resolve to row-absent, else fatal. The existing `pool_until`, 7200 s wall and 7210 s latest-failure caps and `signal_owned` revalidation are untouched. A role whose parent's direct-wait report is present (outer via `child.poll`) must still produce its report.

### Bounded discriminating validation (stdlib only, nothing launched, ≤30 s)

- Pure-function table tests of the comparator, same code the observer calls: (a) zombie row, all four fields equal, `Z`, `(python3.12)` → transition, logged; (b) same pid but start_time differs → fatal; (c) same pid, `Z`, but ppid differs → fatal; (d) argv changed, state `S` → fatal; (e) multi-token or non-parenthesised argv with `Z` → fatal; (f) `Z` persisting 3 samples → fatal; (g) mismatch row is on disk before the exception is raised.
- One OS check on this host: spawn `python3.12 -c pass` with `start_new_session=True`, do not `wait()`, poll `ps` at 5 ms until the row shows `Z`; record exact `stat`, `lstart`, `pgid`, `args`; then `waitpid` and confirm row absent. This directly confirms or refutes the `(name)` rendering and that lstart/pgid survive. If it refutes (argv/lstart unchanged in `Z`), the hypothesis is wrong and only the logging fix (item 2) ships.

## 2. What the 384-update curve adds

All numbers from retained certificates/`D2-development.jsonl` (64 fixed seeds, same seeds every checkpoint, keyed by `episode_index`) and `training-metrics.jsonl`. 16 updates per evaluation; ckpt 50 = update 320.

### Evidence

| Window (evals) | mean score | mean alive frames |
|---|---|---|
| entry control (update 0, ckpt 10) | 1.48 | 295 |
| ckpt 12-20 (updates 16-80) | 6.9 | 937 |
| ckpt 22-32 | 10.6 | 1302 |
| ckpt 34-44 | 13.3 | 1560 |
| ckpt 46-56 | 17.5 | 1939 |
| ckpt 50-58 (last 5) | 18.0 | 1990 |

- Best ckpt 50 (320 updates): 20.594 / 2240.0; final ckpt 58 (384): 14.406 / 1654.5. Gate score≥50 AND alive≥3060: best is 41% of score gate, 73% of alive gate; need ×2.43 score and ×1.37 alive.
- Eval noise: per-checkpoint SE of the 64-episode mean is 0.3-2.3 score. Paired ckpt50−ckpt58 = +6.19 ± 2.62 SE (score), +585 ± 233 (alive); ckpt50−ckpt52 = +3.3 ± 3.0, ckpt50−ckpt54 = +1.1 ± 3.0. Ckpt 50 is the max of 24 noisy learned evaluations (winner's curse); smoothed level near the end is ≈18, so the 20.6 should not be read as the policy's true level, and the 14.4 final is partly noise.
- OLS over ckpts 20-58: +3.0 score and +274 alive frames per 100 updates, residual sd 1.7 score; fitted values at update 384 ≈ 18.2 / 2001. The last two 6-eval windows are flat (17.46 vs 17.35), so a deceleration is possible but not distinguishable from noise.
- Score per alive frame (pooled): 0.0050 at entry, 0.0094 at ckpt 30, 0.0092 at ckpt 50, 0.0087 at ckpt 58. The gate implies 50/3060 = 0.0163. Density has been flat since ~update 100; improvement since then is mostly survival. Even 3060 alive frames at current density gives ≈28, so the score gate needs both longer survival and higher scoring per frame.
- Tail exists: at ckpt 50, 18/64 episodes reach ≥3060 alive frames and 5/64 reach score ≥50 (max alive 7462). At ckpt 58: 11/64 and 1/64.
- Optimizer (all 384 updates): `approx_kl` 0.015 (first 20) → 0.031 (last 20) vs `target_kl` 0.03; KL early stop first fires at update index 68, 230/384 updates early-stopped, mean epochs 3.57/4, ≈10.9% of nominal optimizer steps lost; clip fraction 0.22 late; entropy 1.88 → 1.75 and flat ≈1.73-1.75 after ~update 100 (no collapse); explained variance 0.60 → 0.32, monotone decline; value loss 0.012 → 0.019; reported `grad_norm` > `max_grad_norm` 0.5 in 384/384 updates (min 0.55, median 0.78; metric is the pre-clip value returned by `clip_grad_norm_`, working-copy `learning/python/dodge_learning/ppo.py:431`; capsule copy not diffed).
- Stochastic training completed-episode means (biased to short episodes): alive 791 → 1474, score 5.0 → 12.2 across six 64-update blocks. Deterministic argmax eval (up to 18-20) sits above it, so the "stochastic improves while deterministic stalls" picture from the 97-update plateau diagnosis does not hold at 384 updates.

### Hypotheses (not established)
- H1 more training at the same settings keeps improving. Supported: monotone-ish trend, no collapse. Weakened: flat last window, flat score density, linear extrapolation needs ~770 updates for alive but ~1440 for score (≈4× this run, ≈11-13 h at ~17.6 s/update); extrapolation is not evidence.
- H2 optimization is throttled: grad clip binds every update, KL cap binds on 60% of updates, critic fit worsens as episodes lengthen (EV down, no return normalization). Correlational only; nothing here isolates a cause.
- H3 the dev score is limited by scoring-rate (pickups/kills) rather than survival. Only the density series above supports it; no mechanism check was made.

### One recommended cheapest discriminator (proposal, unauthorized)

**Single-factor 96-update arm: `ppo.max_grad_norm` 0.5 → 1.0, everything else identical to the frozen r2 D2 config.** Choice: grad clipping binds in 100% of updates and affects every step, unlike the KL cap (≈11% of steps) and it needs no new architecture, reward or timing code. It isolates "optimization throttling" (H2) at about 96 × 17.6 s ≈ 28 min instead of the ≥11 h that testing H1 directly would take.

- Preconditions (all absent today): new parent authorization; start from the **eligible D1 parent** under the existing contract, not failed-run weights, no resume, no edits to old metadata/identity; the corrected, validated observer from section 1; fresh output dir.
- Frozen comparison: same run seed/schedule/D2 eval seeds (3489660928-…991), eval every 16 updates (updates 16..96, 6 evals + entry). Baseline = retained r2 evaluations at updates 80/96/112 (ckpt 20/22/24): mean score 9.72, mean alive 1251 (per-eval SE 1.2-1.4 score, ~110 alive).
- Trigger: treatment mean of evals at updates 80/96 (+ 112 only if budget allows) ≥ baseline +4.0 score AND +400 alive → throttling implicated; propose a follow-up separately. ≤ +1.5 score → H2-via-clip falsified; do not tune clip further. In between → inconclusive; no repeat without a new baseline replicate. Run-to-run variance of the baseline is unreplicated, so the threshold is deliberately large.
- Stop: hard 96 updates; abort on any non-finite metric, entropy < 1.0, explained variance < 0, or integrity failure (no retry); if the D2 gate passes stop and report, no qualification claim.
- Not chosen now: `target_kl` change (confounded with clip: both limit step size), reward/return normalization, LR, architecture, longer continuation, baseline replicate (answers only noise).

## Incomplete evidence / inspection notes
- Missing census row (primary gap), no `stat` column: cause of the mismatch unproven.
- I did not read the authoritative plan/spec or full ledger; only `parent-reconciliation.json`, observer source, frozen `processes.py` and targeted `long_d2.py` lines, terminal monitor evidence, campaign metrics/certificates and the 97-update plateau reconciliation.
- Inspection slips: initial `cd` into the observer dir (no writes); one over-large print of a `training-episodes.jsonl` abandoned-rows record (display only).
- Mutable `state.json` is snapshotted by hash in `receipt.json`, not treated as source drift.
