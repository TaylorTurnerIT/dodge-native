# Interface addendum

Parent authority mapping follows the selected update-300 receipt. `parent.path` and `parent.sha256` identify its checkpoint; `parent.local_update`, `parent.phase_update`, and `parent.total_update` are 24, 300, and 348. `parent.metadata_path` maps to the selected checkpoint JSON sidecar because the receipt exposes no separate metadata authority. `parent.terminal_receipt_*` identifies the selected receipt; evaluation, audit, selection, full-audit, producing registration, and completed-cost receipt fields point to their verified immutable evidence.

Unresolved runner expectation: final assembled runner and adapter are not present yet. Parent must reconcile emitted `parent.*` key names with the frozen worker/adapter contract. This builder has not qualified a launch.
