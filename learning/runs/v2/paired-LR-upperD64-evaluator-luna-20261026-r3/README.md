# Paired upper-D64 evaluator r3

Preparation only. This successor repairs the production runtime binding and endpoint metadata contract from the frozen r2 review. It does not run the evaluator, load a checkpoint, import the native extension, construct an actual environment, start MPS, or touch a lease, marker, campaign state, or shared output.

## Production runtime contract

The only production entry is `evaluate_with_registered_backend(...)`. The old caller-claims `evaluate_registered(...)` API is removed. Registration schema v2 pins the exact frozen runtime root, full `runtime_member_sha256` map, exact registration paths and byte hashes for both training arms, collector source hash, and model source path `dodge_rl/models/teacher.py`.

Before imports or model/environment construction, the backend checks the training registration files against their immutable SHA-256 values, requires both arms to share the same runtime member map, checks every frozen runtime member, and requires the training native SHA-256 `022d41dde9bace0b4f4c4c06b9b4ed007bc2c60013cd98734086e587d7bb997e`. Runtime root is `D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime`, whose package layout is directly `dodge_rl/`. No Cargo/Rust layout or root `python/` layout is assumed. A preloaded `dodge_rl` module is rejected before runtime imports.

## Endpoint metadata

`registration-inputs.json` records the parent-provided, separately pinned constant and linear metadata paths, metadata byte hashes, checkpoint hashes, state-dict hashes, update counts, source full-audit paths and hashes, and metadata-derivation receipt path and hash. Constant remains `e25117bf52f14629a3d2ffada319c49a10c6344763a25506a5f124a76a62199b`. Linear is `cc5c3bee52b3fdad925ad90e793983df41954f16ce11403f9f32c431434e52e2`. Both attest phase update 384 and cumulative update 432.

The supplied parent attestations cite each endpoint's full-audit artifact and the CPU metadata-derivation receipt. They do not carry a separate completed-training-receipt path; this preparation does not invent one. Registration validates the exact parent derivation receipt and endpoint metadata pins. The production path then checks metadata bytes, checkpoint bytes, and loaded model state-dict SHA-256 before collection.

## Parent registration build after review

After reviewing this successor, the parent can build an immutable registration JSON in its own authorized output directory with exactly the schema exercised by `test_paired_eval.py`: schema v2, manifest and episode contract, pinned runtime root and complete member map, both immutable training registration provenance entries, backend identity (`collector_sha256`, model source, and same runtime member map), and both endpoint objects copied from `registration-inputs.json`. Set `collector_sha256` to the final `paired_eval.py` byte hash. Keep constant endpoint identity equal to the fixed constant pin. Supply the matching endpoint metadata file path to `evaluate_with_registered_backend`; its path and bytes must match the selected endpoint object. Parent registration SHA and runtime guard remain caller inputs.

No registration, lease, evaluation, or output artifact was created here.

## CPU tests

Thirteen CPU-only unit tests pass with the fake policy/environment path. They cover strict frames, mutation and RNG guards, endpoint attestations, source/runtime preflight failures, preloaded-module rejection, manifest failure before any guard or constructor, and the removed legacy entry point. They do not import or execute the native extension and do not deserialize checkpoints.

Run command and output are in `cpu-tests.log`.
