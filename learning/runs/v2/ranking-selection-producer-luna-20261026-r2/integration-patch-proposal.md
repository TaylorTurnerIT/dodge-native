# Parent integration contract

This is a preparation proposal. Do not edit accepted worker, evaluator, supervisor, shared runtime, or registration source here.

## Producer inputs

Call `produce_selection` with:

- externally pinned ranking registration path and SHA-256;
- ranking bundle path and SHA-256;
- successful ranking outer receipt path and SHA-256;
- six update keyed result path/SHA-256 pairs (180, 204, 276, 300, 324, 348);
- exclusive output path for the selection JSON.

The adapter reads actual R5 shapes. Registration schema/mode are `expanded_D2_evaluation_registration_v1` / `ranking`. Candidate checkpoint pins come from `candidates[str(update)].checkpoint_sha256`; candidate entries also retain actual `phase_update`, `checkpoint_path`, `source_receipt_path`, and `source_receipt_sha256` fields. Evaluator SHA comes from `source.evaluator_sha256`. Runtime identity is SHA-256 of sorted compact JSON encoding of `runtime.member_sha256` (13-member map). Ranking cohort identity comes from `cohorts.ranking.manifest_path`, `manifest_sha256`, and `count`.

R5 evaluator result has no `run_id`, evaluator SHA, or runtime SHA. Adapter requires each result's existing `registration_sha256` to equal externally pinned ranking registration hash. It derives run ID, evaluator pin, runtime map digest, and cohort manifest pin from that exact registration. It checks outer receipt run ID, registration SHA, stage, anchor update 348, cohort, worker/evaluator source pins, successful exit/postflight, and output artifact path/hash bindings for summary and each candidate file. Outer output artifacts must bind all seven files.

R5 summary `candidate_results` embeds the six complete evaluator results. Adapter requires each embedded result to equal its externally pinned raw result JSON. It recomputes row metrics and winner; never trusts summary `winner_update`.

## Confirmation handoff

Producer writes payload with fields current worker expects: `winner_update`, `winner_checkpoint_sha256`, `incumbent_checkpoint_sha256`, `ranking_results`. It adds `schema`, ranking registration path/hash/run ID, evaluator SHA, runtime member-map digest, manifest path/hash, recomputed mean, metric label, status, and evidence limit.

Parent computes the selection file SHA and stores the five current lock fields in confirmation registration: `path`, `sha256`, `winner_update`, `winner_checkpoint_sha256`, and `incumbent_checkpoint_sha256`. Values come from the produced selection file and pinned registration candidates. Existing worker compares winner/checkpoint fields and validates record path/hash. A future replacement validator receives externally pinned ranking registration path/hash and six parent-owned result path/hash bindings, then calls `validate_selection_record`. It must not rely on record-provided paths without those independent pins. Confirmation registration must carry this provenance binding through a parent-reviewed contract revision before invoking that validator.

If 348 wins, producer writes a non-invocable selection record with `confirmation_status: no_confirmation` and `invocable_confirmation_record: false`. Parent must leave confirmation unopened. Any other winner remains subject to separate parent confirmation authorization. Ranking alone never changes parent-accepted 348.

## Remaining gates and limits

The adapter does not alter benchmark outputs. It consumes current result fields and registration-bound identities. Throughput compatibility between benchmark and ranking source/runtime remains a separate parent gate from review finding M-5. Adapter verifies ranking outer worker/evaluator against ranking registration; it does not claim benchmark/ranking throughput equivalence. No confirmation or launch authority is created.
