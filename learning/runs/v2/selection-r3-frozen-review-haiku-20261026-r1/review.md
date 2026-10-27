# Frozen source-only review: ranking selection cap-proof repair r3

Verdict: **No blocker in the pure adapter source.** The producer and validator now mirror the R4 evaluator row, result, and summary contract, and the R2 High (cap rows rejected) and Medium (record lacks summary/outer binding) are closed. **Blocker for the integration as written:** the proposal adds a new top-level `ranking_proof` key, which the evaluator and preflight reject. The proposal must nest it under `provenance`. Confirmation wiring (B-1) remains open. No launch or confirmation clearance. No accepted-348 change.

## Scope and method

- Source-only, read-only. Nothing imported, executed, or tested. Python was not run. `patch --dry-run` and a patch reconstruction were run only in a temp directory on copies of R2 source.
- Read the seven R3 artifacts, the R4 evaluator, the R5 registration/execute/worker/build/test sources, the R5 proposal's ranking seed manifest, the R2 review, and the parent R3 validation receipt.
- Did not read any ranking summary, candidate result, outer receipt, registration output, confirmation output, checkpoint, lease, marker, or benchmark output.
- Wrote only under `learning/runs/v2/selection-r3-frozen-review-haiku-20261026-r1/`.
- Caveman applies to chat. This file is persisted, so it uses normal prose per `/Users/taylor/AGENTS.md`.

## Reviewed bytes (sha256, computed at review time)

| file | sha256 | status |
|---|---|---|
| `selection-cap-proof-repair-luna-20261026-r3/selection.py` | d35614e5f3d65836f0b3943622701322297bc201a0d07a2e547f5bd2a2b64e66 | matches R3 receipt and parent pin |
| `selection-cap-proof-repair-luna-20261026-r3/test_selection.py` | 836f8a9c222510012968fdfe2140e8a31b4b572722ae312691552dffb8fcc4f1 | matches R3 receipt |
| `selection-cap-proof-repair-luna-20261026-r3/receipt.json` | 9dbe9b8d5dd77fdd1b3549fc9e1efc4d70888d6b2b7782a4f60429c092ccda9e | not self-pinned |
| `selection-cap-proof-repair-luna-20261026-r3/diff.patch` | b4d8f4369c0f541c78c800e71947ca563215c4fd6a6223595c18915b1b702ccb | matches R3 receipt |
| `selection-cap-proof-repair-luna-20261026-r3/README.md` | 191236065d3bce7a457e99d73dc3cdc89b675bc62816485e42bdac0c6bcdc526 | matches R3 receipt |
| `selection-cap-proof-repair-luna-20261026-r3/integration-patch-proposal.md` | 6167438de6c93a4b6bef936b261c7b601ae22a4f5f97cfd0ea1c43baad806a94 | matches R3 receipt |
| `selection-cap-proof-repair-luna-20261026-r3/tests.log` | 8d025e7ab9d7e059dd29f7cff2319e366bd9131ef52539cff7a05abbadc6cc71 | matches R3 receipt |
| `expanded-evaluator-publication-repair-parent-20261026-r4/expanded_eval.py` | a3439c33152b082471cd9f9a36ef4bb03783b9544ae7c1e3fe1878e607b128aa | matches contract pin |
| `selection-r3-parent-validation-20261026-r1/receipt.json` | 6581ae81deee5cb578755489c90e4deff7c23039ae4b0aefaacfbc5e1ea1dcc1 | not pinned by R3 |
| `expanded-runner-integrated-parent-20261026-r5/execute_once.py` | b1020bd112dd79ae2c8486424907001292be64e8e81224aad68b38dd044a775c | matches R2 review pin |
| `expanded-runner-integrated-parent-20261026-r5/worker.py` | 2b5d25d07c671671e6f9a4fb2c976b02af2cb8372ace30ad2d05544bb18a83e4 | matches R2 review pin |
| `expanded-runner-integrated-parent-20261026-r5/build_registration.py` | 280650effba15ca1763707bbf054d081f6d4fb662da83f6a70a299243b07e8eb | matches R2 review pin |
| `expanded-runner-integrated-parent-20261026-r5/test_runner.py` | 6b1c1ec9f289587c3520c962dfee65b82cebc7017bb075ecdb351cf1d922ec73 | not pinned by R2 |
| `expanded-evaluation-registration-proposal-parent-20261026-r5/ranking-seed-manifest.json` | e4aafa70226a5191f926f07961025e829466373bcfab30303af5f3a862f9f3ed | matches `proposal.json` cohort pin; seeds are 1024 consecutive values from 0xD1000000 |
| `selection-r2-frozen-review-haiku-20261026-r1/review.md` | e83b4e9163171ce2c9b7b635de51850ce280a19a54c0307aa4e053cbbab51483 | prior findings source |

Patch check: `diff.patch` dry-runs cleanly against R2 `selection.py` and `test_selection.py`. Applying it to an R2 copy reproduces `selection.py` with sha d35614e5…. The reconstructed `test_selection.py` hash was not checked.

## Row, result, and summary contract (read against R4 evaluator)

- Row checks in `selection.py:65-112` match `expanded_eval.py:287-325` (`_validate_rows`) for integer fields, `startup_frames == 13`, score accumulation, boundary flags, `alive <= gameplay <= 18000`, terminated fatal-frame conservation, death cause and contacts, truncated shape, score identity, and objective identity. I compared these by reading; the match is line-for-line in intent.
- Result fields checked by `_validate_result` (`selection.py:132-162`) are all produced by the evaluator: `schema`, `complete`, `registration_sha256`, `candidate_update`, `checkpoint_sha256`, `cohort_name`, `cohort_sha256`, `episodes`, `caps`, `death_causes`, `performance`, `elapsed_seconds`, `rows`, `model_state_dict_sha256`, `backend` (`expanded_eval.py:327-340`, `547-552`).
- Summary checks match worker output: `schema`, `selection_only`, `winner_update`, and `candidate_results` (`worker.py:203`). `RANKING_SCHEMA` matches.
- Outer receipt keys checked (`selection.py:188-196`) match `execute_once.py:341`: `schema`, `run_id`, `registration_sha256`, `stage`, `candidate_update`, `cohort`, `raw_exit_code`, `stop_reason`, `process_group_absent`, `output_artifacts`, `worker_sha256`, `evaluator_sha256`.
- Registration keys match `build_registration.py` and the proposal: `mode`, `run_id`, `source.evaluator_sha256`, `source.worker_sha256`, `runtime.member_sha256` (13), `runtime.backend`, `candidates[str(u)].phase_update` and `checkpoint_sha256`, `cohorts.ranking.manifest_path`, `manifest_sha256`, `count`.
- Ranking manifest: `count == 1024` and `seeds == list(SEEDS)` verified by reading the file.
- Ranking candidate-update convention: the producer hard-requires outer `candidate_update == 348` (`selection.py:193`). `execute_once.py:68` accepts any int for ranking. `test_runner.py:70` launches ranking with `update=348`. No real ranking launch command was reviewed.

## Carry-forward status

- **R2 H-1 (cap rows rejected): closed.** `selection.py:85-104` and `:101-104` accept truncated rows with `alive == gameplay == 18000`, `death_cause None`, and telemetry None. Matches `expanded_eval.py:315-318`.
- **R2 M-1 (record lacks summary/outer binding): closed.** Record stores `ranking_summary_path/sha256` and `outer_receipt_path/sha256` (`selection.py:241-246`). `validate_selection_record` replays the full `_derive_proof` chain with externally pinned inputs (`selection.py:288-297`).
- **R2 T-1 (fixtures not evaluator-shaped): closed for shape.** Fixtures now use `startup_frames 13`, `fatal_gameplay_frame == gameplay`, contacts dict, and truncated rows (`test_selection.py:14-42`). Coverage is still thin; see A-1.
- **R2 L-1 (missing shared rules): closed.** All shared and branch rules from `_validate_rows` are mirrored, including strict int typing.
- **R2 L-2 (non-atomic write): closed with a caveat.** Temp file, fsync, `os.link` exclusive create, unlink, and dir fsync (`selection.py:266-284`). See A-2.
- **R2 B-1 (worker unwired): still open.** `worker.py:116-132` is unchanged. It checks the five-field lock and six refs, but does not call the validator, does not recompute argmax, and does not check result refs against external pins. R3 says this explicitly (`README.md:9`, receipt `limits`).

## Integration proposal contract (separate from adapter source)

**P-1 (High, integration blocker, fail-closed). Top-level `ranking_proof` is rejected.**
- Location: `integration-patch-proposal.md:7-8` ("add this exact `ranking_proof` object" as a registration object).
- Evidence: the R4 evaluator allows top-level registration keys only from `required | {"provenance", "benchmark_measurement", "observer"}` (`expanded_eval.py:130`). The R5 preflight enforces the same set (`execute_once.py:64-66`). A new root key raises a preflight error ("registration top-level field set differs").
- Trigger: parent adds `ranking_proof` at the registration root, as the proposal reads.
- Consequence: confirmation registration fails preflight. No confirmation starts. No unsafe acceptance.
- Fix: rewrite the proposal to nest under `provenance.ranking_proof`, which the parent already plans. Update `build_registration.py:82`, where `provenance` is a fixed-key dict, to include it. Note that the evaluator checks only the root key set, not `provenance` contents as far as I read. The worker or validator must therefore shape-check the nested object: exact keys, 64-hex pins, and integer-keyed `result_bindings` after JSON string-key conversion.

## Adapter findings

**A-1 (Medium, test coverage). Several contract branches are unexercised by the 8 tests.**
- Untested: `unavailable` death cause (`selection.py:91-93`); `unknown` cause exemption (`:99`); contact count `< 1` for a named cause (`:98-99`); `startup_frames != 13` (`:31-32`); `score_delta_sum` mismatch (`:33-34`); score and objective identity (`:105-111`); caps-count mismatch (`:152-153`); death-cause count mismatch (`:158-159`); duplicate or missing candidate in summary (`:208-212`); summary-embedded result mismatch (`:230-231`); missing `output_artifacts` (`:213-215`); float-typed integer fields (`:21-23`).
- Two test names overstate what they check. `test_summary_drift_and_wrong_winner_rejected` (`test_selection.py:160-165`) changes only the winner, so the summary-content branch at `selection.py:230-231` is never hit. `test_invalid_cap_frames_and_flags_rejected` (`:138-143`) checks only the frame bound.
- Trigger: a regression in any branch above passes all 8 tests.
- Consequence: real evaluator output with `unavailable` or `unknown` death causes, or with a summary/result mismatch, is unverified.
- Fix: a parametrized mutation table covering each branch with the expected message.

**A-2 (Low, error path). Dir fsync failure after link leaves a record and raises.**
- Location: `selection.py:274-281`. After `os.link` succeeds, `os.open`/`os.fsync` on the directory can raise. The `finally` does not unlink in this case, which is correct, but the caller sees an exception while `selection.json` exists.
- Trigger: dir fsync error (rare, I/O failure).
- Consequence: retry raises `FileExistsError` (fail closed). Operator may misread the state.
- Fix: document, or check the output exists before re-raising. Low priority.

**A-3 (Low, evidence). Interpreter version is inconsistent across records.**
- `receipt.json` says `"python": "3.9.6"`. The brief says the parent validated under project Python 3.12. The parent receipt (`selection-r3-parent-validation-20261026-r1/receipt.json`) and `tests.log` record no interpreter version.
- Consequence: the parent claim of 3.12 is not evidenced by the file. Code uses only stdlib APIs present in both.
- Fix: record the interpreter version in the parent validation receipt.

**Not a defect, dependency note. Ranking candidate-update must be 348.**
- The producer fails closed unless outer `candidate_update == 348` (`selection.py:193`). The only ranking launch convention in reviewed source is `test_runner.py:70`. Confirm the real launch command uses 348.

## Checked and not a defect

- `_derive_proof` reads each pinned file once and hashes the same bytes it parses. No TOCTOU between hash and parse.
- `validate_selection_record` writes nothing. It is read-only.
- Winner tie-break `(-mean, update)` matches the worker sort key (`worker.py:203`) after the recomputed mean equals the reported mean.
- Collision test (`test_selection.py:193-205`) confirms existing bytes are preserved on `FileExistsError`.
- `os.link` exclusive create refuses an existing output, so no overwrite.

## Required before parent acceptance

1. Correct `integration-patch-proposal.md` to nest `ranking_proof` under `provenance` (P-1). Note the builder and worker changes this needs.
2. Confirm the real ranking launch uses `--candidate-update 348`.
3. Add mutation coverage for A-1 branches. This is not a blocker for the synthetic ranking-stage producer.
4. B-1 worker wiring stays a separate parent-reviewed revision before any confirmation use.

## Limits

- Static reading only. No tests run, no code executed, no patch-reconstructed test file hash checked.
- No actual ranking, confirmation, candidate, summary, outer receipt, or checkpoint output read.
- `execute_once.py`, `worker.py`, `build_registration.py`, and `test_runner.py` were read for key names and branches, not audited.
- The producer's dependence on exact path string equality with the outer receipt's `output_artifacts` was not re-verified beyond the R2 review's check.
- Supervisor, heartbeat, and throughput gates were out of scope.
