# Review: D2-retained300 registration builder r6

Scope: static read and sha256 only. No imports, tests, runtime, training, lease, ledger, or source writes. Not a launch qualification.

## Verdict

No builder-internal blocker for the synthetic artifact. The builder's own checks close: paths, pins, counters, retries, expected outputs, resource arithmetic, and exclusive output. Launch remains blocked at the parent level by items below. No launch approval is implied.

## Verified

- Path depth: `prepare_registration.py` ROOT `parents[4]`, `execute_synthetic.py` ROOT `parents[3]`, contract path `parents[4]` all resolve to repo root.
- No undefined names found by manual scan; `ast.parse` passes. pyflakes not available.
- Selected receipt: phase 300, local 24, cumulative 348; registration `8e17e1188253f091b62a8b60397663a530c4a865166f9568978dd009148308e7` (full 64); checkpoint `e2c8fbe44e23da910686954e90cb7841b38b6d7f60f69ca657a4a69b14214710`.
- Evidence map: 19 inputs; zero overlap with base pins, so `pins.update` adds without overwriting.
- Retries 0 on base and output. `expected_lease`, `metadata_path`, `resource_cost_anchor`, `parent.*` repointed to selected receipt.
- Expected outputs: 32 names. Eval set 300, 312, 324, 336, 348, 360. `lr-transition.json` excluded and forbidden.
- Config `1c24df3e...` matches contract; LR `3e-05`.
- Resource arithmetic: `1502.5562572500203 × 1.15 = 1727.9396958375232`; margin to 1750 = 22.06.
- Pins: 13801 − 4 + 23 = 13820.
- Manifest: 12 entries, all match. Synthetic output `6dce6b23...` matches log.
- Output: all checks precede mkdir and `open("x")`. Actual run dir absent. Freeze-r5 `empty-pycache` exists and is empty.

## Findings

- **F1 medium** `prepare_registration.py:141-145` — drops four historical R2 source pins (`execute_once.py`, `lr_transition.py`, `registration_schema.py`, `runner.py`) despite comment "Preserve historical". New in R6. Consequence: archival pin coverage lost; R2 producing run still pinned via evidence map and `parent.registration_sha256`; no runtime path reads the dropped R2 sources. Parent's own freeze-r5 `registration.json` restores them.
- **F2 medium** `prepare_registration.py:136` — output allowed inside frozen final source dir, which already holds two registrations: `registration.json` (`8a60dc80...`, 13827 pins) and `registration-builder-output.json` (`febec589...`, 13820 pins; provenance inferred). Authoritative artifact ambiguous.
- **F3 medium** `prepare_registration.py:127-129, 147, 157-162` — final sources existence-checked and self-pinned, no expected hashes. Integrity relies on parent preflight. Checked: `registration_schema.py` `eae76ec9...` and `parent_adapter.py` `a969f2a5...` match parent-assembly. Not checked: `runner.py`, `execute_once.py`.
- **F10 medium (parent)** freeze-r5 `registration.json` — 13827 pins vs builder 13820; 4 explained by restored historical pins, 3 unexplained. Parent reconciliation open.
- **F4 low (inherited)** `prepare_registration.py:141` — retained base fields not validated by builder: `state_path`, `native`, `runtime_continuity`, `runtime_root`, `runtime_sha256`, `interpreter`, `archival_labels`, `archival_parent_checkpoint_sha256` (`ce9c03...`, archival only). Parent full preflight required.
- **F5 low** `prepare_registration.py:214-215` — hardcoded resource values; `observed_control_optimizer_steps=7680` replaces base 9216 with no derivation in contract or evidence map. Provenance unconfirmed.
- **F6 low** `prepare_registration.py:226` — non-atomic write; failure after `open("x")` leaves truncated file that blocks reruns.
- **F7 low** `prepare_registration.py:241` — `main()` derives root from `--contract`; build checks use module ROOT. Consistent by default only.
- **F8 low** `execute_synthetic.py:46-49` — positive assertions are self-referential; three negative cases; no test for dropped pins, base retries, config drift, counter mismatch.
- **F9 low** `interface-addendum.md:5` — says final runner and adapter not present; freeze-r5 now contains them (mtime 12:11 vs addendum 12:09).

## Parent-level open items (not builder defects)

1. Choose one authoritative registration; remove or quarantine the other from freeze-r5.
2. Decide historical pin policy (restore the four, as parent already did) and make builder match.
3. Explain the 3-pin delta (13827 vs 13820).
4. Verify `runner.py` and `execute_once.py` hashes against parent-assembly, outside this review.
5. Full parent preflight over ~13801 base pins before any launch.

## Limits

Not launch-qualified. Did not read or hash freeze-r5 `runner.py` or `execute_once.py`. Did not re-run seed-collision check. Did not reproduce tests. Provenance of freeze-r5 `registration-builder-output.json` inferred from shape and pin count.
