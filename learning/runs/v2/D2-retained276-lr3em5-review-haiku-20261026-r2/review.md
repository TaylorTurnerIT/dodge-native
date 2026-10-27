# D2 retained276 LR3e-5 — Haiku review R2

Frozen source-only, static review. No imports, checkpoint loads, MPS, env, training, launch, marker, state, or lease actions. Tests were not run.

## Verdict

No blocking defect in the R1 fix. The hardcoded old-schema guard is gone; `execute_once.execute` now uses `registration_schema.validate_identity`, shared with the runner. One medium finding (F1) and five low or informational items.

## Findings

**F1 (medium, CONFIRMED) — stale auditor pin.** `wrapper.py:33` pins `AUD_SHA = 884cf86a…`. The on-disk `audit_candidates.py` hashes to `604133a1…`, and `freeze-hashes.json:55` agrees with disk. `load_auditor` (`wrapper.py:103-106`) fails closed, so `run_audit` and `full_mode` cannot run. No bypass. The launch path in `execute_once.py` does not appear to call this, which the parent should confirm. Repin only as part of the six-candidate auditor rebind.

**F2 (low, CONFIRMED) — marker before digest check.** `execute_once.py:291-292` writes the one-use marker before `load_registration` checks `registration_sha` (`runner.py:362`). A wrong sha with a valid-shape registration burns the marker and launches nothing. This matches the R1 consumption symptom. It is the documented design; flagged for the parent to decide.

**F3 (low, CONFIRMED) — dead `ROOT`.** `test_execute_registration_boundary.py:11` uses `parents[4]`; the repo root is `parents[3]`. Unused.

**F4 (low, PLAUSIBLE) — import before pin check.** `registration_schema` is imported at module load (`execute_once.py:18`, `runner.py:21`). Its pin is verified later in `load_registration`. Same trust model as the launcher and runner source; no new bypass.

**F5 (low, PLAUSIBLE) — coverage gap.** The boundary regression exercises only `execute()`. The runner's `validate_registration` also calls `validate_identity` but has no rejection test.

**F6 (info, PLAUSIBLE) — auditor drift.** R2 `audit_candidates.py` drops the `PYTHONPATH`-unset check; `test_audit_candidates.py` drops the Entry Adam mutation test. Auditor is inactive per brief; rebind should decide.

## Checked, no finding

- Hashes match the brief: schema `f8956515`, launcher `fd7298a8`, runner `013ef0b5`, test `acec2d1c`, registration `8e17e118`.
- No launch-code path accepts `d2_retained276_continuation_registration_v1`. Only the negative test fixture uses it.
- Schema v2 and RUN_ID `D2-retained276-lr3em5-20261026-r2` match `registration.json`.
- `registration.json` is not in its own pins; pins for runner, launcher, schema, LR helper, and config match disk. Non-circular.
- Cost anchor `711b2949…` and receipt fields (348 phase, 72 local, counters) match `runner.py:412-416`. Parent terminal receipt `d64d0f80…` matches.

## Uncertainties

- Tests not executed (would import forbidden modules). All verdicts static.
- Launch-path membership of the wrapper audit is inferred from grep, not run.
- No runtime, RSS, MPS, or resource evidence examined.
- Auditor rebind is out of scope; F1 and F6 feed it.

Machine-readable form: `review.json`. Hashes: `receipt.json`.
