# D2 retained276 LR3e-5 successor auditor review (r2), source-only

Reviewed: `learning/runs/v2/D2-retained276-lr3em5-auditor-luna-20261026-r2/` (audit_candidates.py, wrapper.py, tests, manifests, logs).

## Findings

No findings. No blocking defect found in the static scope below.

## Verified

- Pins: `audit_candidates.py` sha256 `42abf9b5…e62` and `wrapper.py` sha256 `42755974…031` match the brief. `input-manifest.json` sha256 `7c50fc3b…339` matches.
- Registration: `prepare-r2/registration.json` sha256 `8e17e118…308e7` matches REG_SHA. `registration_schema.py` sha256 `f8956515…af95f1af9b` matches the schema pin, and its path matches `registration_schema_module_path` in the registration.
- Observer: `observe.py` sha256 `a52fe93c…da54` matches. Field names the wrapper reads in full mode (`outer_raw_exit`, `worker_raw_exit`, `outer_inclusive_wall_seconds`, `max_aggregate_rss_bytes`, `postflight.pins.failures`, `cache_empty_after`, `outer_process_absent`, `worker_group_absent`, `observer_pid`, `outer_process_group`) are all written by observe.py.
- Launcher result: `execution-result.json` gets `actual_worker_launch_count`, `observed_worker_raw_exit`, `worker_pid`, `owned_pgid` from `execute_once.py` (lines ~325–340), so the wrapper's `owned_processes_absent` lookups do not KeyError.
- Expected outputs: the auditor's `expected_outputs()` list (33 names over six UPDATES) equals `registration.json` `expected_outputs` exactly.
- Full-mode gates: audit requires six published certificates, the exact observer dir and source digest, terminal status `passed`/`completed`, and frozen launcher validation. Wrapper requires registered observer dir, observer raw exits 0, outer wall ≤ limit, RSS and MPS caps, process absence, and empty cache. CLI refuses full mode.
- Diff vs prepare-r1 auditor: only rebinding of paths, run ID, pins, and the added schema origin/digest check. The wrapper diff is the same, plus the R2 schema check.
- CPU logs: `cpu-controls.log` and `cpu-controls-final.log` differ only in the timing line (0.777s vs 0.767s). Both show 13 tests OK.

## Limitations

- 13 tests is not 35 prior regression proof. Prior r1 had 8 (`test_audit_candidates`) + 26 (`test_terminal_wrapper`). The r2 auditor directory has no terminal-wrapper unit file. Terminal gate, process-absence, and bytecode-prefix negatives are covered only by the 3 source-contract tests, by name. Prepare-r2 `test_terminal_wrapper.py` (26 defs) was not run here.
- Not run: CPU tests (parent replays), any audit, any training or campaign read.
- Not inspected: moving run outputs under `D2-retained276-lr3em5-20261026-r2/`, and the observer's live output.
- `owned_processes_absent` uses `os.kill(pid, 0)`. A zombie reads as present, which fails closed. Not a bug, but a late-reaped zombie would block full mode.
- Stale embedded pins in the R1 auditor/wrapper inside prepare-r2 are out of scope and not edited here.

## Scope

Static read of listed files, sha256 checks, and field-name cross-reads against observe.py, execute_once.py, runner.py, registration.json. No file outside this directory was written.
