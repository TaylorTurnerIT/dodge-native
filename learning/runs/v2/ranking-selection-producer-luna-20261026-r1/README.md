# Ranking selection producer preparation

Inert stdlib adapter and synthetic tests. Parent-owned output only.

`selection.py` accepts externally pinned bundle, registration, outer receipt, six per-candidate JSON files, and evaluator/runtime/cohort/manifest SHA-256 values. It validates the exact six updates (180, 204, 276, 300, 324, 348), 1024 manifest-ordered seeds (`0xD1000000..0xD10003FF`), row accounting, finite metrics, cap 18000, candidate pins, run registration hash, provenance pins, reported summaries, and recomputed mean-alive argmax. Ties choose earlier update. Selection record is created exclusively.

Expected raw candidate result adds `registration_sha256`, `evaluator_sha256`, `runtime_sha256`, and `manifest_sha256`; current worker output lacks these fields. Producer must add and bind them before adapter can accept real results. Registration/runtime throughput matching remains a parent gate described in `integration-patch-proposal.md`.

Validator takes independent pinned result path/hash bindings. It does not trust refs in selection JSON. A 348 winner gets `confirmation_status: no_confirmation` and `invocable_confirmation_record: false`. No confirmation artifact is generated. No actual ranking results, checkpoint files, leases, markers, runtime, or training were read or used.

Run synthetic tests with:

```sh
python3 -m unittest -v
```

These tests prove only adapter behavior on synthetic JSON. They do not establish runtime compatibility, parent registration compatibility, throughput equivalence, ranking outcomes, or launch/confirmation authority.
