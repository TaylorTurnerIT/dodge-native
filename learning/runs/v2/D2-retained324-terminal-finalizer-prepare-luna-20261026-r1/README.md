# D2 retained324 parent finalizer preparation

`finalize_parent.py` imports without side effects. Only explicit parent invocation (`python finalize_parent.py`) performs terminal publication. That later invocation writes only this directory and the registered orchestration state ledger. It does not write the run, auditor, observer, frozen preparation, checkpoint, or incumbent receipt.

Before publication it checks the exact lease and cancellation state, every registration pin, all six full audits, terminal observer and execution evidence, resource bounds, live process and process-group absence, and incumbent hashes. It repeats lease and cancellation checks immediately before atomic ledger replacement and compares original ledger bytes at each publication boundary. Partial output files use exclusive creation; any mismatch stops without clearing the lease.

No candidate replaces the original incumbent. Current-run phase324 is reserialized and has a different checkpoint hash. Retain the exact original checkpoint `c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc` and original receipt `76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08`. Original immutable certificate gives Q1 767.5, Q4 5468.6875, mean 2939.40625.

The completed-iteration receipt records endpoint384 and all discarded updates for resource cost only. Retained decision references the original checkpoint and receipt. Trajectory baseline remains 5678.9823631240915 seconds; completed resource cost adds the observer's outer-inclusive 1066.4701513750479 seconds to 9758.365427209174 seconds. No qualification, D3, B, E, or student claim; score gate remains absent.

`test_finalizer_controls.py` contains CPU-only AST and synthetic guard checks. It does not call finalization or write the state ledger.
