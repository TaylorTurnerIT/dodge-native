# Frozen source-only review: ranking selection producer r2

Verdict: **Not acceptable as-is.** Confirmed High: `_row_alive` rejects every valid cap-truncated episode, so `produce_selection` fails closed on any ranking run with at least one cap episode. No wrong-winner path found from that bug. Second finding: the selection record does not carry or replay the outer receipt or summary binding. Boundary: this producer does not close R4 H-1 by itself; `worker.py` still does not call `validate_selection_record`.

**No launch or confirmation clearance.** No accepted-348 change.

## Scope and method

- Source-only, read-only. Nothing imported, executed, or tested. `tests.log` read as text; the 7 synthetic tests were not re-run.
- Did not read any actual ranking result, summary, outer receipt, registration output, or confirmation artifact. Ranking/confirmation outputs under `learning/runs/v2/` were not opened.
- Written by the sub-agent under `learning/runs/v2/selection-r2-frozen-review-haiku-20261026-r1/` only. No benchmark source, supervisor, heartbeat, or shared file touched.
- Caveman voice for chat; this file uses normal prose per `/Users/taylor/AGENTS.md`.

## Reviewed bytes (sha256, computed at review time)

| file | sha256 | status |
|---|---|---|
| `ranking-selection-producer-luna-20261026-r2/selection.py` | 850916152765538f35b4808ec8ab2132fad973ab0127c9fe1d28f76ffeff9d00 | matches parent pin |
| `ranking-selection-producer-luna-20261026-r2/test_selection.py` | 7e6bcebca47e884fc4eb25596408769eebcf110bca8340d15de86a0c788be4b0 | matches parent pin |
| `ranking-selection-producer-luna-20261026-r2/README.md` | ccd22c30708387d5e4b40dd1e4f856508bda5b2dad8174561438a3ef7478621a | matches parent pin |
| `ranking-selection-producer-luna-20261026-r2/integration-patch-proposal.md` | 13ccc49a7527d3f1f1f97769037351903216b5fca071bb65b6c70f3f4af1bf6c | matches parent pin |
| `ranking-selection-producer-luna-20261026-r2/tests.log` | 21df4995c6bb7e6b5e0af742188013587a8f27708b24fa429678543a11e2c55a | matches parent pin |
| `ranking-selection-producer-luna-20261026-r2/manifest.json` | 062d8c3a354dc119c12fa9ebf779e5fa9710ffb051fa0d9e9cb8b62e8cb650cf | not pinned by itself |
| `expanded-evaluator-publication-repair-parent-20261026-r4/expanded_eval.py` | a3439c33152b082471cd9f9a36ef4bb03783b9544ae7c1e3fe1878e607b128aa | matches contract pin |
| `expanded-runner-integrated-parent-20261026-r5/worker.py` | 2b5d25d07c671671e6f9a4fb2c976b02af2cb8372ace30ad2d05544bb18a83e4 | matches contract pin |
| `expanded-runner-integrated-parent-20261026-r5/execute_once.py` | b1020bd112dd79ae2c8486424907001292be64e8e81224aad68b38dd044a775c | matches contract pin |
| `expanded-runner-integrated-parent-20261026-r5/build_registration.py` | 280650effba15ca1763707bbf054d081f6d4fb662da83f6a70a299243b07e8eb | matches contract pin |
| `expanded-runner-integrated-parent-20261026-r5/receipt.json` | 3d7a36380e25fc9d8340a75df584df1d6d8c0528722ce8b09b83a0d44e5268b2 | matches contract pin |
| `expanded-runner-integrated-parent-20261026-r5/tests.log` | 2f9cde0e5780357d7a0b6877f647b692b6876cdb8471cc92ede943b6d6eecc46 | matches contract pin |
| `expanded-evaluation-registration-proposal-parent-20261026-r5/proposal.json` | 187e0464ba966b29124b29cf606c831d7097adeea99ccfc0e336598ad3fc9765 | matches contract pin |

All 7 contract pins in `manifest.json` match. Parent-verified findings and 5 hashes were taken as given where not re-derived here.

## Field contract (evaluator to producer)

Evaluator emits per-candidate results via `_summarize` (`expanded_eval.py:327-340`) and validates rows via `_validate_rows` (`expanded_eval.py:287-325`).

Truncated (cap) row, evaluator-enforced (`expanded_eval.py:315-316`): `gameplay_frames == alive_frames == 18000`, `death_cause is None`, `fatal_gameplay_frame is None`, `death_observed_lethal_contacts is None`.

Terminated row, evaluator-enforced (`expanded_eval.py:301-314`): `alive_frames + 1 == gameplay_frames <= 18000`, `death_cause in DEATH_CAUSES`, `fatal_gameplay_frame == gameplay_frames` (except `unavailable`), `death_observed_lethal_contacts` a dict with exact keys `DEATH_CAUSES[:-1]` and nonnegative ints.

Shared: `startup_frames == 13` (`:296`), `score_delta_sum_raw_fixed == score_raw_fixed` (`:297`), `alive <= gameplay <= cap` (`:300`), `score == score_raw_fixed / 65536`, objective identity `score + alive/100 - 5*terminated` (`:320-323`).

Producer `_metrics` (`selection.py:88-93`) and `_summarize` (`expanded_eval.py:329-333`) use the same quartile formula (q = len//4 = 256) and the same mean/worst/best. Winner tie-break `(-mean, update)` (`selection.py:219`) matches worker sort key (`worker.py:203`). Recomputed mean is used; reported `summary.winner_update` is cross-checked (`selection.py:220-221`). Worker-side bundle winner uses reported mean (`worker.py:203`); producer does not trust it.

## Findings

**H-1 (High). Truncated cap rows are rejected.**
- Location: `selection.py:69` (`_row_alive`); branch at `:74-75` does not fix it.
- Code: `row.get("gameplay_frames") != alive + 1` is applied unconditionally. Evaluator emits `gameplay_frames == alive_frames == 18000` for truncated rows (`expanded_eval.py:315-316`).
- Trigger: any ranking candidate with one or more truncated episodes at the 18000-frame cap. `_row_alive` raises `ValueError("alive/gameplay frame accounting invalid")` (`selection.py:70`); `_validate_result` (`:124`) propagates it; `produce_selection` (`:166-216`) aborts before writing a record.
- Consequence: fail-closed availability block. No wrong selection is emitted. Every ranking run that reaches cap in any episode cannot produce a selection file. Recovery requires a code fix; the result files are not damaged.
- Test gap: `make_result` (`test_selection.py:18-25`) builds only terminated rows (`terminated: True`, `truncated: False`), so the truncated branch is never exercised. The "7 tests passed" log does not cover this case.
- Fix:
  - In `_row_alive`, branch on `terminated`:
    - truncated: require `gameplay_frames == alive == CAP`, `death_cause is None`.
    - terminated: require `gameplay_frames == alive + 1`, `alive <= CAP - 1`, `death_cause in DEATH_CAUSES`.
  - Add tests: (a) truncated cap row with `alive=gameplay=18000` accepted; (b) truncated row with `gameplay=18001` rejected; (c) terminated row with `gameplay==alive` rejected; (d) a ranking set with one cap row end-to-end through `produce_selection` returns a record.
- Severity: High (agrees with parent). Blocks valid output; no unsafe output.

**M-1 (Medium). Selection record does not bind the outer receipt or summary; validator cannot replay postflight.**
- Location: record payload `selection.py:222-234`; producer checks `:159-203` against outer receipt; validator `validate_selection_record` `:246-285` takes only registration path/hash and six result bindings.
- Facts: the producer checks the summary path/hash and the outer receipt (`:169-203`), but the record stores neither the summary path/hash nor the outer receipt path/hash. The validator never reads the outer receipt, so it cannot check `raw_exit_code == 0`, `stop_reason is None`, `process_group_absent`, `stage == ranking`, `candidate_update == 348`, or artifact bindings.
- Trigger: a hand-written or future-generated `selection.json` plus pinned registration and six result files, where the ranking run's outer postflight failed after the worker wrote all six candidate files but before or without a valid summary. The validator accepts it (`:246-285` checks only registration, results, winner, refs, checkpoint pins). The producer would have refused it.
- Consequence: confirmation-side trust depends on the producer having run correctly at the time of writing. Provenance is not self-contained in the record. Current worker does not call the validator (see boundary below), so exposure today is limited to the producer being the sole writer of the record.
- Fix: add `ranking_summary_path`, `ranking_summary_sha256`, `outer_receipt_path`, `outer_receipt_sha256` to the record. Change `validate_selection_record` to take externally pinned outer-receipt and summary bindings, and re-run the same identity/postflight/artifact checks used by `produce_selection`.
- Severity: Medium (provenance gap; not a current wrong-winner path while the producer is sole writer).

**B-1 (Boundary, not a producer defect). R4 H-1 remains open at the confirmation worker.**
- Location: `worker.py:116-131` (`validate_selection`) checks five lock fields, record hash, ref hashes, and six-update coverage. It does not call `validate_selection_record`, does not recompute argmax, and does not check `ranking_results` against independently pinned result bindings.
- Trigger: a selection record whose winner is not argmax of its six refs, with matching checkpoint pins and six valid refs. Worker accepts it.
- Consequence: R4 H-1 (`review.md` of `benchmark-acceptance-r4-frozen-review-haiku-20261026-r1`) remains open until the parent-reviewed revision in `integration-patch-proposal.md` lines 25-26 wires the validator into the worker with six externally pinned result bindings. This producer alone does not close it.
- Required: parent-reviewed contract revision to the worker call site. Not in scope for this review.

**T-1 (Medium, test fidelity). Fixtures do not match evaluator row shape.**
- Location: `test_selection.py:19-25` and `:30-33`.
- Facts: fixture rows set `startup_frames: 0` (evaluator requires 13, `expanded_eval.py:296`); terminated `normal_enemy` rows set `fatal_gameplay_frame: None` and `death_observed_lethal_contacts: None`, which the evaluator rejects (`expanded_eval.py:303-313`). `README.md` and `manifest.json` describe the fixtures as "matching evaluator result shape" / "matching R5 evaluator result fields"; this is overstated.
- Consequence: fixtures cannot catch H-1 (no truncated rows) and would reject real evaluator output on the telemetry fields if the producer ever validated them.
- Fix: build fixtures from evaluator-shaped rows (startup 13, fatal == gameplay, contacts dict) and add truncated cases.
- Severity: Medium.

**L-1 (Low, defense in depth). Producer checks a subset of evaluator row rules.**
- Missing vs `_validate_rows`: `startup_frames == 13` (`expanded_eval.py:296`); `score_delta_sum_raw_fixed == score_raw_fixed` (`:297`); `alive <= gameplay <= cap` bound (`:300`); death/cap telemetry rules (`:301-318`); strict int type on `gameplay_frames` (`selection.py:69` uses `!=`, so a float `18001.0` equals `18001`).
- Trigger: evaluator bug or tampered result file whose hash is still pinned (hash pins prevent tampering; this is for evaluator regressions).
- Consequence: producer accepts rows the evaluator would reject. Winner is by `alive_frames`, so selection impact is limited.
- Fix: mirror the evaluator checks in `_row_alive`, or import the shared rule set from `expanded_eval.py` (import disallowed in the current producer, so copy rules with a test per rule).
- Severity: Low.

**L-2 (Low). Non-atomic write of selection record.**
- Location: `selection.py:239-242` (`output.open("x")`, `json.dump`, `flush`).
- Trigger: crash or kill between open and final flush.
- Consequence: partial `selection.json` remains. Re-run fails with `FileExistsError` (fail closed) and needs manual cleanup. No false acceptance.
- Fix: write to temp path in the same directory, `fsync`, then `os.link` or `os.rename` to exclusive target.
- Severity: Low.

## Checked and not a defect

- Output path match: `build_registration.py:61` resolves `output_dir`; `execute_once.py:70` requires `Path(output).resolve().parent == Path(reg['output_dir']).resolve()`; `receipt` uses `Path(reg['output_dir']).glob('*')` (`execute_once.py:335-341`). Artifact path strings therefore match `str(Path(x).resolve())` used in `produce_selection` (`selection.py:202`, `:208`).
- Summary-embedded results: worker embeds full result dicts (`worker.py:203`); producer requires exact equality with raw result (`selection.py:215-216`). OK.
- Outer receipt scope: `output_artifacts` lists every file in `output_dir` at receipt time (`execute_once.py:335-341`). Producer checks summary and six candidate paths and hashes are present. Does not require exactly seven artifacts; `output_dir` is empty at preflight (`execute_once.py:152`) so no extras expected.
- Worker-side candidate file naming matches producer assumption: `call_plan` ranking files `-candidate-{k}` (`worker.py:47`) and planned in `execute_once.py:75`.
- 348 winner: record sets `confirmation_status: no_confirmation` and `invocable_confirmation_record: False` (`selection.py:233-236`); validator enforces (`:281-282`); worker rejects 348 as confirmation winner (`worker.py:119`).
- `validate_selection_record` ties `ranking_results` to parent-supplied bindings (`selection.py:275`) and checkpoint pins to registration (`:277-278`). Good.
- No evaluator import, no native/Torch, no run output read.

## Required before accepting this producer

1. Fix H-1 (`_row_alive` branch on terminated/truncated) with truncated and negative tests.
2. Fix M-1 (record and validator carry and replay outer receipt and summary bindings) or record an explicit parent decision that postflight provenance is producer-only.
3. Fix T-1 fixtures to evaluator shape, add truncated cases.
4. Parent-reviewed revision wiring `validate_selection_record` into the confirmation worker (B-1) before any confirmation use. Does not block ranking-stage production.

Low items optional.

## Limits

- Static review only. No tests run. `tests.log` taken as text.
- Did not read any actual ranking, confirmation, or candidate output.
- Did not verify runtime behavior of `expanded_eval.py` (e.g. the cap branch), only its source.
- Parent-verified 5 hashes and 7 synthetic tests accepted as stated; this review re-hashed all 13 listed pins above.
- Did not review supervisor/heartbeat repairs (parallel, out of scope).
- Did not review throughput gate M-5 (separate parent gate).
