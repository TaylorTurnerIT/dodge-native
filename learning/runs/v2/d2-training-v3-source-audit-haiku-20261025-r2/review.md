# D2 training-v3 source audit r2 (readonly, Haiku review)

Scope: frozen `learning/runs/v2/d2-training-v3-adapter-prepare-20261025-r2/` (`adapter.py`, `worker.py`, `launcher.py`, `helper.py`, tests, `implementation-result.json`), parent `parent-plan-r2.json`, `parent-r2-source-findings.json`. Read-only. No imports, execution, tests, model, or training. `partialr3` and old source/state/runtime/metadata not inspected for modification. Project files read only by `grep`/`sed` (`critic-diagnostic-parent-prepare-20261025-r1/runtime/dodge_rl/{identity,checkpoints,ppo}.py`). Source hashes match `implementation-result.json` for all eight frozen files.

Verdict: **not approvable for registration.** Known blockers are all still present in frozen source. Additional concrete defects below. Launch count: 0.

Scope note: this review does not approve the newly-written source. The fresh round after Luna's fixes is still required.

## Known findings: disposition

| ID | Status | Evidence (frozen r2) |
|---|---|---|
| REG-SELF-HASH | Confirmed, open | `worker.py:27` reads `reg["registration_sha256"]`; key absent from `registration-template.json` and `registration-spec.json` (grep). KeyError at worker start. |
| FINAL-HASH-CONFUSION | Confirmed, open | `launcher.py:192-193` passes checkpoint file SHA as `expected_sha`; `launcher.py:68-69` compares `state["registration_sha256"]` to it. `worker.py` stores the registration digest there, so the check always fails. |
| EPISODE-CONTRACT | Confirmed, open, detail extended | `adapter.py:327` expects initial next indices `[0]*64`; actual native value not verified here. Reset records: `worker.py:141` emits `{"kind","phase_update","info"}` with no `indices`; `adapter.py:342` reads `record["indices"]` → KeyError on first reset. Only `test_adapter.py:99` has `indices` (fixture does not match worker shape). `launcher.py:82-84` compares checkpoint next indices to live `current`, not current+1. Completed-before-reset ordering (`worker.py:139`) still unfixed. |
| CHECKPOINT-CONFIG | Confirmed, open | `adapter.py:239-252` emits no `config_sha256`, no inherited/cumulative counters; `launcher.py:74` requires `config_sha256`; counters are D2-local (`worker.py:94`). |
| CACHE-AND-DEPS | Confirmed for empty prefix; manifest part unverifiable | `launcher.py:131` sets `PYTHONPYCACHEPREFIX=""`, which Python treats as unset. `adapter.py:204-207` checks `os.environ` only, not `sys.pycache_prefix`. Dependency-inventory allowlist not in scope. |
| FROZEN-TIME-ANCHOR | Confirmed, open, extended (N3) | Frozen anchors consumed before launch: `adapter.py:79-83`, `launcher.py:106-108`, `launcher.py:33-36`. |
| LATE-SIGNAL-REGRESSION | Confirmed, open | `launcher.py:209-218` last budget check before publish; `launcher.py:272-273` returns exit 0 for a latched signal arriving after that. |

## Additional findings

**N1 (P1, proven by code reading). Second invocation after success marks a completed run as publication failure.**
- Path: `launcher.py:238-251` (except branch), `launcher.py:113` (fresh-output check).
- Trigger: run completes and writes `launcher-result.json` (status `completed_worker_pending_parent_terminal_acceptance`). Any retry or duplicate `launch(reg, sha)` then fails at `:113` ("not fresh"), enters the except branch, sees completed status with no `publication-failure.json`, and writes `publication-failure.json` with `status: failed`.
- Consequence: evidence contradicts itself on a successful run; parent could act on a false failure.
- Fix: write `publication-failure.json` only when the failure happened after this invocation published `launcher-result.json`; never on pre-run errors.

**N2 (P1, proven by arithmetic and code). Worker is hard-killed at 1600 s, before its own finalization window.**
- Path: `launcher.py:144` kills at `elapsed >= work_seconds` (1600) measured from `started` (`launcher.py:121`). Worker finalization budget is 1800 (`helper.py:162`, `worker.py:166,174`). Worker result save at `worker.py:186` and final guard at `worker.py:166` therefore fall in a window the launcher already killed.
- Parent planning total is 1571.9 s (`parent-plan-r2.json` budget basis), leaving about 28 s to 1600 for final eval, checkpoint save, and `worker-result.json`.
- Trigger: training and final eval finish at ~1590 s; SIGTERM at 1600 during save → no `worker-result.json` → `launcher.py:175` fails a run that trained to completion.
- Fix: either kill at 1800 minus worker finalize reserve, or move final save inside the work bound with explicit margin. Also reconcile the "200 s finalization reserve" text with what the worker can actually use.

**N3 (P2). Budget clock: negative elapsed passes every check; sleep behavior unverified.**
- Proven: `time.monotonic()` here is `mach_absolute_time()` (system Python 3.9.6 `time.get_clock_info`; Python 3.12 pin should match). All budget checks use this clock: `launcher.py:33-36,106-108,140-147,168`, `helper.py:162-163`. No check rejects `clock() < started_monotonic`, so a negative elapsed value satisfies every `< total_seconds` test (e.g., anchor from before a reboot).
- Hypothesis (not measured): `mach_absolute_time` may not advance during system sleep, so a sleep during a run would under-count elapsed time and let the 1800 s wall bound be exceeded. Verify by sleep test before relying on it.
- Fix: reject negative elapsed; use a wall-clock anchor (or sleep-inclusive clock) for the absolute bound; add an explicit boot/clock identity to the registration.

**N4 (P2, proven). Stale progress counter in checkpoint.**
- `worker.py:96` initializes `progress["completed_updates"] = 0`; no code path increments it (`ppo.py:416,576` update only `state`/`in_update`/`complete`). Final checkpoint therefore records `completed_updates: 0` with `counters.updates: 72`.
- `launcher.py:77-80` checks `complete` and `in_update` but not `completed_updates`, so the mismatch passes silently. Any future resume reading that field replays or skips updates.
- Fix: increment on each completed update in the worker and validate it in `validate_final_checkpoint`.

**N5 (P2, proven structure, cost unmeasured). Post-training full revalidation counts against the deadline.**
- `launcher.py:172` and `launcher.py:194` re-run `validate_registration`, which re-hashes every pinned file; `worker.py:22` does the same at worker start, inside the 1600 budget. Checks at `launcher.py:174,196` then run against the 1800 total.
- Once the known dependency inventory (~13k files) is added to pins, repeated multi-GB hashing can push a finished run past 1800 at `launcher.py:196`.
- Fix: hash once before launch and record; post-run check only cheap identity (size/inode/mtime) or measure first.

**N6 (P2, proven pins do not cover bytecode; exploit path hypothesis). Frozen source dir contains bytecode.**
- `learning/runs/v2/d2-training-v3-adapter-prepare-20261025-r2/__pycache__/` holds seven `cpython-312` `.pyc` files (`adapter`, `helper`, `launcher`, tests). They are not in `source_sha256` or the pin manifest.
- Worker runs with `-B` (`launcher.py:128`), which suppresses writes, not reads. `adapter`/`helper` import from script dir (`sys.path[0]`), so a `.pyc` whose recorded mtime and size match the source would execute instead of pinned `.py`. Launcher itself has no `-B` enforcement.
- Fix: remove bytecode before registration; enforce `sys.dont_write_bytecode`/`-B` in launcher; pin or exclude `__pycache__` explicitly.

**N7 (P2, design/ops). Pre-run failures consume the run ID.**
- `launcher.py:112` creates the output dir before the one-use marker; any error after that (e.g., wrong `expected_sha256` at `launcher.py:100`) makes `launch()` write `launcher-result.json` with `status: failed` (`launcher.py:252-261`). The run ID and output dir are then unusable ("not fresh" at `:113`).
- If intentional (one-use), state it; otherwise validate before mkdir.

**N8 (P3, hypothesis). Monitor fragility and launcher death.**
- `launcher.py:143` reads and parses `state.json` every 0.1 s with no tolerance; a non-atomic parent write causes `JSONDecodeError` → `monitor_error` (`:154`) → kills a healthy run. Depends on parent writer atomicity (not in scope).
- Worker runs in its own session (`launcher.py:135`). If the launcher is SIGKILLed, only cooperative `guard.check()` and lease checks stop the worker; there is no in-worker alarm for a hung native call.

## Not verified / out of scope

- Native initial next-episode indices (EPISODE-CONTRACT) and dependency inventory (CACHE-AND-DEPS): not inspected.
- `validate_summary` and `checkpoints.save_checkpoint` semantics beyond the grep above.
- Test results: not rerun (readonly). `implementation-result.json` claims 11 passing tests under venv; not revalidated here.
- `partialr3`, old source/state/runtime/metadata: not inspected for modification.
- The r2 README mentions an overwritten r3 rehearsal receipt; not audited here.

## Required before the fresh round

Resolve all seven known blockers plus N1–N2 (both P1), N4–N6 (P2), and decide N7. Re-freeze source and registration; the next audit must review the new source, not this one.
