# Ranking selection producer: R5 contract

This isolated preparation consumes current `expanded_D2_evaluation_registration_v1` ranking registrations, `expanded_D2_ranking_selection_v1` bundles, `expanded_eval_outer_receipt_v1` receipts, and six evaluator result JSON files. It does not require evaluator or benchmark output changes.

Every result's existing `registration_sha256` must match the externally pinned registration file. Registration supplies `run_id`, `source.evaluator_sha256`, `runtime.member_sha256`, `candidates`, and `cohorts.ranking`. Runtime identity is SHA-256 over sorted compact JSON for the 13-member map. The ranking manifest is loaded from registered `manifest_path`, checked against `manifest_sha256`, count 1024, and exact ordered seeds `0xD1000000..0xD10003FF`.

The adapter verifies outer receipt run/stage/cohort/anchor, registration and source pins, successful exit and postflight, and SHA-256 artifact bindings for summary plus six per-candidate outputs. It validates result identity, complete 1024 ordered rows, finite fields, cap and death counts, recomputed performance summaries, and bundle-to-result equality. Winner uses row-derived mean alive frames, with earlier update winning ties.

Output has current confirmation worker fields (`winner_update`, `winner_checkpoint_sha256`, `incumbent_checkpoint_sha256`, `ranking_results`) plus registration and metric provenance. Parent computes output SHA and embeds the existing five-field selection lock in confirmation registration. A 348 winner is marked `no_confirmation` and non-invocable.

Tests use stdlib synthetic JSON matching evaluator result shape. No evaluator import, Torch, native code, MPS, checkpoint, game, training, lease, marker, actual ranking outcome, or confirmation artifact used. Tests do not validate live registration or actual ranking results. Throughput equivalence remains the separate M-5 parent gate. No authority to launch, confirm, or alter accepted update 348.
