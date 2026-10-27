# Review: D2-retained324-linear-auditor-prepare-luna-20261026-r3 vs r2

Scope: static read and SHA-256 of r3 vs r2 only. No imports, tests, subprocesses, checkpoint loads, or writes outside this output directory.

## Verdict

No blockers. The r3 change is narrow, the observer instantiation check is correctly rebound, and the frozen artifacts match their pins.

## Verified

- Hashes match the frozen claims: `audit_candidates.py` 4cc856c9…, `wrapper.py` 871bed65… (identical to r2), `binding_builder.py` 30dab9bd… (identical to r2), `frozen-manifest.json` ec01c46d…. All 13 entries in `frozen-manifest.json` `files` match the bytes on disk. `output-manifest.json` lists the same files plus `frozen-manifest.json` (14 entries), all matching. Neither manifest has a self-entry.
- The r2→r3 change set is limited to `audit_candidates.py` (`validate_observer_instantiation` plus its single callsite) and `test_source_contract.py`. Nothing else in the candidate, model, numeric, or schedule logic changed.
- Observer instantiation record `D2-retained324-linear-execution-observer-parent-20261026-r1/instantiation.json` (SHA 56d547b6…): has no `run_id` key, `registration_path` equals `str(REG_PATH.resolve())` (ROOT is derived from `__file__`, and the worktree `realpath` equals the literal path), `registration_sha256` = 0a6bf982…, `observer_sha256` = f271b264…, schema exact, `actual_launches` 0, `one_shot_marker_absent` true.
- `OBSERVER_SOURCE_SHA256` (f271b264…) equals the SHA of the linear `observe.py`, and `observe.py` declares `REG_SHA = '0a6bf982…'`, so the observer-side registration binding is consistent.
- Strictness: no loosening beyond the intended change. Literal `run_id` is now optional, but if present it must equal the registration `run_id`, which is itself checked against `RUN_ID`. `registration_path`, `registration_sha256`, and the global `OBSERVER_SHA == pin` check are new or stricter. Schema, `actual_launches`, and `one_shot_marker_absent` are unchanged.
- The callsite (line ~691) passes `reg` from `runner.load_registration(REG_PATH, REG_SHA)` (line ~296), and `REG_SHA` is byte-pinned at line ~250.
- `test_source_contract.py` mutation test: 8 negatives (`registration_path`, `registration_sha256`, `observer_sha256`, `schema`, `actual_launches`, `one_shot_marker_absent`, present-wrong `run_id`, present-`None` `run_id`). Each mutation breaks a predicate in the function, so each should raise `AuditError`. The test restores `OBSERVER_SHA` in `finally`.
- Test count: 8 + 17 = 25, matching `cpu-tests.log` ("Ran 25 tests … OK") and the manifest's "25 passed". I did not rerun them.
- r2 `audit-binding.json` is r2-specific (r2 source digests and paths). r3 has no `audit-binding.json`, and `test_source_contract` asserts it must not exist. The parent must regenerate the binding for r3 via `binding_builder.py`. This is expected, not a defect.

## Findings (non-blocking)

1. LOW, `test_source_contract.py` (new test), coverage gap. No negative case for the global `OBSERVER_SHA == OBSERVER_SOURCE_SHA256` check (audit_candidates.py:536) or for a wrong `registration` argument `run_id` (line 533). Trigger: caller passes a registration whose `run_id` differs, or `OBSERVER_SHA` binding differs from the pin. Consequence: none today, because callsite-level checks (lines 683, 688, 792) still gate these paths. Recommend adding two subtests in a later round, not now.
2. LOW, same test, no positive case with a present, correct literal `run_id`. Code reads correctly (`record.get("run_id") == registration_run_id`), so only test coverage is missing.
3. INFO, audit_candidates.py:537 uses string equality `str(REG_PATH.resolve())` against an absolute path baked into an immutable record. It is correct for this worktree (realpath verified). Moving the worktree breaks it. Acceptable: the r2 callsite already had the same path-resolution dependency.

## Limits

- Static review only. I did not execute the test suite or the audit. Test pass status is taken from `cpu-tests.log` and is unverified here.
- Did not review training methodology, schedule math, or candidate predicates beyond confirming they are unchanged.
- No subdelegation.
