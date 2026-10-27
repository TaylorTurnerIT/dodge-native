# R3 cap and proof-chain repair

This owned-output successor repairs the R2 ranking selection producer. It uses stdlib JSON and filesystem APIs only. The candidate row checks mirror the pinned R5 evaluator contract, including `startup_frames == 13`, score accumulation identity, terminal telemetry, and cap rows with `alive_frames == gameplay_frames == 18000`.

`_derive_proof` is shared by `produce_selection` and `validate_selection_record`. Both paths reread and validate the externally pinned registration, manifest, summary, outer receipt, and six result files; they recompute row metrics and the winner. Records bind `ranking_summary_path`, `ranking_summary_sha256`, `outer_receipt_path`, and `outer_receipt_sha256`. Output creation writes and fsyncs a same-directory temporary file, then uses exclusive hard-link creation. A collision preserves existing bytes.

Run synthetic checks with `python3 -m unittest -v test_selection.py`. Fixtures use current evaluator row fields and exact 1024-seed order. They cover capped rows and metrics, terminal/cap shape failures, stale hashes, artifact and outer postflight failures, summary drift, winner ties, 348 winner handling, count errors, and output collision.

This R3 source does not close confirmation-worker wiring. Current `worker.py::validate_selection` still checks the five-field lock and six result references without calling this replay validator. A parent-reviewed worker and registration revision remains required before confirmation use. No launch or confirmation authority follows from R3.

No actual ranking result or confirmation outcome was read or created. No benchmark/evaluator/worker/README/ledger/runtime/checkpoint/lease/marker/launch source was changed. No Torch, MPS, native game, training, or checkpoint code was imported or run.
