# Review: reusable reporting/preflight utility (r2)

Read-only review of `learning/runs/v2/reusable-reporting-preflight-luna-20261026-r2/`. No tests run, no edits to inspected files. Stdlib reads, hashes, and in-memory probes only (probe objects not written to disk).

## Verdict

No findings change the currently reported numbers. Verified against source JSON: canonical tail means (585.625 / 3502.5625 / 1854.46875 for BEST@180; 532.8125 / 3192.3125 / 1604.078125 for LATEST@252), sorted bottom/top-16 definition, death counts (32/11/0/11/10 and 24/9/3/13/15), row-level causes agreeing with aggregate causes, 64 unique episode indices and seeds, and the embedded `performance` blocks. Accepted-receipt and registration digests match the external pins.

Hardening is needed before regular use (findings 1–4).

## Findings (most severe first)

1. **Authority binding relies on KeyError for missing pins.** `validate_authority` compares `receipt.get(...)` with `registration`-derived `.get(...)` for `checkpoint_sha256`, `registration_sha256`, `runtime_sha256`, `policy_sha256`. If a key is absent on both sides, `None == None` passes the explicit `require`. The function only fails later at the return dict (`KeyError`). Probe: dropping `runtime_sha256` from receipt and registration → `KeyError 'runtime_sha256'`; same for `checkpoint_sha256`. Fail-closed, but not by design, and the CLI would crash with no reason message. Tests do not cover missing keys. Fix: require each pin to be present and a 64-hex string before comparing.

2. **Cohort/cause consistency not enforced.** `summarize_evaluation` counts deaths only from aggregate `death_causes` and ignores row `death_cause`, `terminated`, `episode_index`, and `seed`. Probe: 64 copies of one row → `summarize_performance` accepts it (Q1 = 2940.0). `summarize_evaluation` has the same gap for duplicate `episode_index`/`seed` (code reading). Current fixtures are consistent (checked: row causes match aggregate, indices 0–63 unique, 64 unique seeds), so no current number is wrong. Fix: require `{episode_index} == range(64)`, unique seeds, row-cause counts equal aggregate, and `terminated` consistent with a death cause.

3. **Overclaims in `usage.md` and the inspector.** `usage.md` says the inspector "verifies ... all 64 next indices" and "cumulative plus per-iteration outer-wall accounting". The code only checks length 64, non-negative ints, and inequalities (`wall >= iteration_wall`, `0 < checkpoint_wall <= iteration_wall`). Also `preflight-manifest.json` `parent_authority.checkpoint_sha256` is the receipt's declared value; checkpoint bytes are never hashed, and the manifest does not say so. Fix: narrow the wording, or add an explicit `checkpoint_bytes_verified: false` note in the manifest.

4. **Test gaps (known failures not detected).**
   - No test for `summarize_evaluation` rejection paths: unknown/unavailable deaths, incomplete evaluation, deaths ≠ 64, row count ≠ 64.
   - No test for CLI `inspect`: wrong receipt or registration digest, existing output (exclusive-create), relative paths.
   - `test_actual_report_designations_and_death_counts` only counts `| BEST REFERENCE` and `| LATEST` occurrences. A swapped or misbound value row would still pass. Should pin the rendered row contents.
   - Authority mutation test does not mutate receipt-side `checkpoint_sha256`, `registration_sha256`, `next_episode_indices` length, or wall fields.
   - Row-level cohort checks from finding 2 are untested.

5. **Misnamed weak control.** `test_negative_control_unsorted_slice_is_not_canonical` does not test an unsorted slice. Its `assertNotEqual` against an ad hoc midpoint of `ordered[15]`/`ordered[16]` passes for almost any wrong percentile method. The real percentile control (`test_actual_252_percentile_negative_control`, plus the hardcoded values in `test_actual_252_and_180_rows_and_shuffled_order`) does pin behavior. Rename or tighten the synthetic control.

6. **Labels and cross-checks (low).** `BEST REFERENCE` is printed as a designation with no check. Spec says labels come from explicit inputs, so this is acceptable, but the table reads as validated authority. The source JSON's top-level `checkpoint_sha256` and embedded `performance` and `mean_alive_frames` fields are not cross-checked. They agree for both fixtures (verified), so this is a guard gap, not a current error.

7. **Receipt history pinning incomplete (low).** `receipt.json` `history` lists 4 files; `history/` has 8. Pin all or note the omission.

## Scope note (not a defect)

Current behavior fails closed on censored or unknown causes: any `unknown`/`unavailable` count, or any missing death, makes the sum ≠ 64 and the tool rejects. It does not report censored or truncated episodes. `usage.md` should say that explicitly so no reader assumes general censored-cause reporting.

## Scope confirmed

Consistent with the brief: no training, no Torch, no environments, no checkpoint loads, no gradients. `usage.md` and receipt correctly state that frozen runner hardcoded constants remain and that no launch approval is granted.
