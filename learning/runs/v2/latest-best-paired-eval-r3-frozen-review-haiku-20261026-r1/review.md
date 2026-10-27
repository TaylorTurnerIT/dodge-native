# Latest-versus-best paired eval R3 frozen review (static, read-only)

Scope: `learning/runs/v2/latest-best-paired-eval-prepare-luna-20261026-r3/` (`worker.py`, `supervisor.py`, `paired_eval.py`, `tests/test_paired_eval.py`, `native-fixture-result.json`, `test-runs.log`). Static review only. No tests rerun, no `freeze_artifacts.py`, no games, training, or lease/state edits.

Verified by hash: receipt `a57a89c7…2381945`, harness `f872d572…1c91370c` (recomputed from `input-manifest.json` source set; matches), protocol `6a306407…51126`, manifest `8eb589d5…11ff`. Other pins (checkpoints, audits, dependency inventory) taken from parent; not re-hashed here.

## Findings

1. **High — live freshness check uses a `now` captured before the sample is read.** `supervisor.py:189` sets `now = clock()`. Then `_lease_check` runs, `observed_rss` spawns `ps` (`:197`, up to 0.5 s), and `latest_resource_sample(..., now=now)` reads the log (`:198`). The sampler writes every ~0.25 s plus fsync. Any sample written between `:189` and `:198` has `monotonic > now`, so `age < 0` and `require(0.0 <= age ...)` (`:56`) raises. The loop catches that as `resource_monitor_failure`, cancels, and the run ends `failed_postflight_or_publication`. Impact: a healthy run is killed. Per iteration the hit chance is roughly window/0.25 s; over ~2,360 iterations in 590 s this is near-certain. Fix: take the clock after the read (or pass `now=None`).
   - Tests miss this: the fake child writes `monotonic == now` (`tests/test_paired_eval.py:414`), and the reader test only uses fixed `now` values (`:325–327`).

2. **Medium — sampler failure before the first complete line disables in-flight MPS enforcement.** `supervisor.py:199` maps `sample is None` to `mps = 0` for the whole run. `worker.py:425–426` stores sampler errors in `self.error` only. Nothing in `guard()` (`worker.py:485`) or the evaluation loop checks it. If `_sample` fails before any complete write (e.g. `torch.mps.driver_allocated_memory()` raises), the file stays empty or absent and every poll sees `None`. The run continues without an MPS cap until the 590 s deadline. Postflight (`supervisor.py:249`, "No resource samples retained") and `close()` still fail the final status, so acceptance stays closed. The gap is in-flight only. Fix: make `_sample` publish a ready sample before model load, and have the supervisor treat `None` as failure after the sampler has started.

3. **Low — partial-only log raises, empty log returns `None`.** `supervisor.py:42–43` returns `None` for empty data. A log holding only a partial first line goes to `:49` and raises "no complete sample". That is fail-closed, but the two startup states are handled inconsistently: a first line caught mid-write cancels the run. The test pins the raise at `tests/test_paired_eval.py:328–330`. Fix: return `None` whenever no complete line exists. The file only grows, so a partial-only state after a complete sample cannot occur.

4. **Low — postflight does not use the partial-tail-tolerant reader.** `supervisor.py:249` calls `read_text().splitlines()` and `json.loads` on every line. A tail cut short by `stop_owned_child`'s SIGTERM/SIGKILL (`:81`, `:92`) raises `JSONDecodeError` and becomes `postflight_error`. That is fail-closed, but it contradicts the R3 claim that partial tails are ignored. Fix: parse through the same helper as the live path.

5. **Low — owned-group cleanup skips members when the leader has already exited.** `stop_owned_child` signals only `if process.poll() is None` (`:78`, `:90`), and the cancel branch calls it only when `process.poll() is None` (`:214`). If the leader exits while group members keep running, nothing signals the group. `group_absent_after_reap` becomes `False`, so the status fails closed, but the members can keep RSS and MPS allocations. Fix: call `killpg` whenever `group_exists(pgid)` is true. A PGID is not reused while members remain.

Not reproduced, measure before launch: the 1 s freshness cap (`:56`) is 4 × 0.25 s. The actual sampler period is 0.25 s plus fsync plus GIL wait and has not been measured under the real worker. `ps` with `timeout=0.5` (`:28`) raising `TimeoutExpired` is also fatal, so a loaded host can cancel spuriously.

## Checked and found correct

- Cleanup drops references (`worker.py:370`) and calls no `close()`. `finally` contains only non-raising `dict.clear()`, so it cannot replace the original step error. `test_fake_native_contract_failure_drops_refs_without_masking_step_error` exercises this.
- Persisted episode count increments after `write`+`flush`+`fsync` (`worker.py:358–360`). A failed arm keeps the count of synced rows.
- The live reader pops only a non-newline-terminated tail (`supervisor.py:45–47`). A complete malformed last line fails closed through `json.loads`.
- `time.monotonic()` on macOS is system-wide, so supervisor and worker timestamps are comparable.
- Harness hash recomputes from the manifest source set.

## Native fixture limitations (bounded, as recorded)

- `native-fixture-result.json` (sha256 `64b837fa…f6f884f6b`) comes from a test that overrides `difficulty` to 3 (`tests/test_paired_eval.py:264`, `"difficulty": 3` at `:286`). Campaign D2 config is difficulty 2 (`dev_eval.development_environment_config`). No campaign-difficulty native episode is covered.
- Policy is `FixedLeftPolicy`, not checkpoint inference. One seed, `raw_frame_cap` 128 (32 decisions). Status is `bounded_cap_truncation` with no native death.
- Death-field coverage comes only from the historical canonicalized control row, not a new native terminal.
- MPS was not exercised by the fixture.

## Limitations of the monitor (design, not defects)

- MPS is sampled as current driver bytes every ~0.25 s, not peak. Spikes between samples are not observed, and the final ~0.25 s before exit is unsampled. RSS peak uses `ru_maxrss`, which is exact.

## Verdict

Finding 1 should be fixed before any launch gate. Findings 2–5 are fail-closed or in-flight gaps; fix or record as accepted before parent review. Tests should cover the real negative-age ordering and the empty-sampler path.
