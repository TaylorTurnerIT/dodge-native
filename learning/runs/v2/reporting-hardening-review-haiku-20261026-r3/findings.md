# Fresh review: reporting-hardening r3 (frozen child)

Scope: read-only inspection of `reporting_preflight.py`, `test_reporting_preflight.py`, `usage.md`, parent receipt/manifest, and the two D2 evaluation fixtures. No tests, runtime, or edits to frozen artifacts.

## Verdict

No metric errors. Independent stdlib recomputation from raw `alive_frames` matches the explicit fixtures:

- BEST180 (`development-000180.json`): Q1 585.625, Q4 3502.5625, mean 1854.46875; deaths 32/11/0/11/10; caps 0.
- LATEST252 (`development-000252.json`): Q1 532.8125, Q4 3192.3125, mean 1604.078125; deaths 24/9/3/13/15; caps 0.

Prior findings status:

- F1 (None==None then KeyError): fixed. `require_sha256` runs on both sides before compare (lines 77–81); both-side None/malformed tests present.
- F2 (row-derived death/cap consistency, seed/index uniqueness): mostly fixed (lines 220–264). Next-index uniqueness still unchecked (see N2).
- F3 (overclaimed verification): fixed. `inspection_limits` and usage.md state declared-field-only checks.
- F4 (mutation controls, report assertions): partly fixed. Report value and role assertions exist; file-side and CLI-side negative controls exist. Report-side provenance is missing (N4).
- F5 (misnamed negative control): fixed. Test renamed to `test_unsorted_input_rows_still_use_sorted_tail_means`; actual 252 percentile control retained.
- F6: caller-supplied role documented; embedded performance and mean fields checked; caps/unknown/unavailable reported; archive inventory complete in parent manifest (19 entries, including `history/imported-r2/receipt.json` omitted from child manifest).

Parent receipt `complete-history-manifest.json` contains all 19 history entries, and its SHA `b445a839…` matches the parent receipt field. Child receipt `8ea31aa5…` and source/test hashes match the brief. 17 tests passed per `test-run.log`.

## Findings

### N1 (low, correctness-adjacent): aggregate death-cause keys outside `ALL_CAUSES` are silently ignored

`summarize_evaluation` builds `reported_causes` only by iterating `ALL_CAUSES` (lines 255–258). Any extra key in `evaluation["death_causes"]` (typo such as `normal_enemies: 5`, or `cap: 3`) is never compared to row data and never rejected. Current fixtures contain only the seven known keys, so no current metric is affected.

Failure scenario: aggregate `death_causes` has a misspelled nonzero key; row counts match the valid keys; the report passes and the misspelled count is dropped without error.

Fix: `require(set(causes) <= set(ALL_CAUSES), ...)`.

### N2 (plausible, needs parent decision): declared `next_episode_indices` duplicates pass

Accepted receipt `d2-gradient-parent-terminal-audit-20261025-r2/parent-terminal-receipt.json` has 64 `next_episode_indices` values with only 29 unique values. `validate_authority` checks length and int ≥ 0 only (lines 111–113). usage.md says it "validates the shape and values" of next indices. Duplicates in a continuation index list would be a value-level anomaly, not a shape issue, and the tool does not report it.

This does not affect the report metrics. Parent should decide whether duplicates are legitimate for the D2 continuation scheme; if not, add a uniqueness check or document the duplicate as accepted.

### N3 (low): vacuous absolute-path checks; relative inputs accepted

`main()` resolves input paths with `resolve(strict=True)` before `is_absolute()` (lines 312–315 and 318–321). After `resolve()`, paths are always absolute, so the "must be absolute" checks never fire for inputs. Relative `--best-reference`/`--latest` paths are accepted silently against cwd. Only the `--output` check is real. The brief asks for explicit paths.

Fix: check `is_absolute()` on the raw argument before resolving.

### N4 (low-medium): report has no input provenance

`report` prints a Markdown table only. It does not record SHA-256 of either evaluation JSON, the tool hash, or stage/phase identity. The `inspect` path writes a hashed manifest; `report` does not. Numbers cannot be tied to input bytes by the tool output alone.

Related: `markdown_report` never asserts `stage == "D2"`. Both fixtures have `stage: "D2"`, and the seed binding (`0xD0000000+index`) limits foreign input, but a non-D2 file with the same seed layout would pass. Label `phase` is also read from the file unvalidated (`phase_update`).

### N5 (low): duplicate-index branch is not exercised by tests

`test_rejects_duplicate_and_foreign_seeds_and_indices` sets one field at a time on row 1. Setting `episode_index=0` leaves `seed` at `0xD0000000+1`, so the seed-binding check (line 228) fails first and the duplicate check (lines 230–231) is never reached. No test has an internally consistent duplicate (index 0 with seed `0xD0000000` on row 1).

Fix: add a paired `episode_index=0, seed=0xD0000000` mutation.

### N6 (low, hygiene): tests write inside the frozen run directory

`summarize_mutation` creates `test-fixtures/` under the run directory and `InspectorCliTests` uses `TemporaryDirectory(dir=Path(__file__).parent)`. Both are cleaned up, and no residue is present now, but tests mutate the frozen directory during execution. `rmdir()` also fails if the directory already contains files.

### N7 (low, fail-closed): non-ValueError exceptions on malformed declared fields

- `_check_embedded_summary` evaluates `metric in embedded` before the `isinstance(embedded, dict)` check (line 190 before line 191). A non-container non-dict value such as an int raises `TypeError`, not `ValueError`. A list value lacking the metric is silently skipped.
- `Path(parent.get("path", ""))` raises `TypeError` when `path` is present with `None` (line 98).
- Uppercase external digests are rejected because the comparison at lines 324–327 uses the raw `args.*_sha256` (not lowercased). Fail-closed, but `require_sha256` implies normalization.

All fail closed. No metric impact.

### N8 (note): exact float equality on embedded means

Embedded `Q1/Q4/mean` and `mean_score` compare with `==`. Current values are exact (alive frames are integers; scores are multiples of 1/32), so this passes. A producer summing in a different order could fail spuriously. No current impact.

## Not found

- No metric, role, or cohort mismatch in the two fixtures.
- No frozen-artifact edits by this review.
- No checkpoint-weight, runtime, or next-index decoded-state verification was attempted; the tool itself documents these as not checked.
