# Hash-only RNG-reference registration review

**No blocking findings** in the new registration, six-key vectors, or reused source pins. New registration SHA-256 is `6c0fe9e4adb06c97622111ab74129fb65bfbdad6e05edbb3f227ce66cac33008`; it matches the requested hash and preparation receipt.

The new schema and top-level field set match the already accepted registration. Differences are limited to the new study/run ID; its vectors and vector path/hash; owned run paths, cache path, and expected lease identity. Limits match exactly: 45-second work, 55-second outer bound, 10-second cleanup, 6 GiB RSS and MPS caps. Runtime fields match except the new owned empty-cache path. Parent checkpoint, parent receipt, and confirmation acceptance hashes match their pinned file bytes.

New vector bytes equal the seed artifact byte-for-byte; both hash to `9c98e3c0f5e85ffad70da73fda94e4b27f390f755f30640e97c6dc658dc3cb92`. The reused `probe.validate_vectors(vectors, study_id)` accepts all three vectors under `fullgame-seed-priority-luna-20261027-r1`. Independent stdlib derivation reproduced all 18 stream values from their recorded attempts; bounds, per-stream uniqueness across replicas, environment-master reserved ranges, and prior-master exclusions pass.

Probe, worker, supervisor, and fingerprint source hashes match the new registration and the previously accepted registration exactly. Cleanup primitive hash matches the supervisor pin. The probe accepts a dynamic study ID when callers pass it; supervisor and worker pass the registration's ID. No old study ID is hard-coded into those entry points.

The lexical interpreter path and file hash match registration. The owned cache and output directories are empty; one-shot marker and cancel file are absent. Expected lease is not yet present in orchestration state, so live preflight is pending parent lease installation. This review did not call runtime preflight or touch the lease/marker.

## Limits

This is a registration/source/vector hash review, not live runtime qualification. Reused source's accepted terminal audit reports sampled resource checks, no hard watchdog around filesystem/hash/fsync/receipt finalization, and dependency-version checks without package-byte pins. Probe scope remains raw CPU/MPS RNG-state capture only. No Torch import, model construction/deserialization, native/game execution, training, or evaluation occurred. No source or predecessor files changed.
