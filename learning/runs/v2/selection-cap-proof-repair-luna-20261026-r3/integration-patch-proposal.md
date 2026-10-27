# Parent integration proposal

Preparation only. Do not apply this proposal to the current benchmark, registration, or worker sources as part of R3.

The current confirmation registration has `selection_record.path`, `selection_record.sha256`, `selection_record.winner_update`, `selection_record.winner_checkpoint_sha256`, and `selection_record.incumbent_checkpoint_sha256`. Current `worker.py::validate_selection` checks that lock and six ranking result references. It does not call `validate_selection_record`, bind the ranking summary or outer receipt, or recompute winner metrics.

A parent-reviewed confirmation registration revision should add this exact `ranking_proof` object:

- `ranking_registration_path`
- `ranking_registration_sha256`
- `ranking_summary_path`
- `ranking_summary_sha256`
- `outer_receipt_path`
- `outer_receipt_sha256`
- `result_bindings`, mapping string update keys `180`, `204`, `276`, `300`, `324`, and `348` to objects with `path` and `sha256`

The revised worker should validate the existing five-field `selection_record` lock, parse the six `ranking_proof.result_bindings` entries into the producer API's integer-keyed mapping, and call:

`validate_selection_record(selection_record.path, selection_record.sha256, ranking_proof.ranking_registration_path, ranking_proof.ranking_registration_sha256, ranking_proof.ranking_summary_path, ranking_proof.ranking_summary_sha256, ranking_proof.outer_receipt_path, ranking_proof.outer_receipt_sha256, result_bindings)`

The worker should also require the replayed record's three lock values to equal `selection_record.winner_update`, `selection_record.winner_checkpoint_sha256`, and `selection_record.incumbent_checkpoint_sha256`, then retain its existing rejection of update 348 as confirmation winner. Parent review must pin the revised worker and registration contract before use. This proposal creates no confirmation or launch authority.
