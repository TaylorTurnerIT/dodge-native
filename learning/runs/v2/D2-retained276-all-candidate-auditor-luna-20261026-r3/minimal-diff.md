# r3 minimal diff

- Copied frozen r1 auditor and wrapper, then rebound preparation and run paths to the frozen r2 registration (`477217f3c7617ccbe01c651db8932eab01f54ea3924f213e67b413e640cf866c`), runner digest `db0bb3389ee5562bbb9cc1c550cdf64a077c7a1bf84a4f233df861867113a37b`, and the r2 run identity/output.
- Kept the seven-candidate 276→348 gates, exact accepted parent 276 model/Adam/RNG equality, unchanged effective LR 1e-4, baseline and monotonic retained-best semantics, and non-authority flags.
- Full-mode auditor and wrapper now accept only `learning/runs/v2/D2-retained276-continuation-execution-observer-luna-20261026-r2/` and verify its `observe.py` SHA-256 `e3782f1c28c05548e995f3cb8c1a41b2a66f77b69d9455cada0be465f950ad95` before and after audit. Wrapper CLI still refuses full mode; parent calls its explicit `run_audit(provisional=False, ...)` function after terminal evidence exists.
- Added CPU checks for all 72 accepted prior metrics rows against frozen `runner.validate_gradient_alignment`, the accepted prior `full-audit.json` metrics digest, and observer directory/source binding.
- Preserved all predecessor logic and authority limits. No source, registration, checkpoint, native runtime, run output, state, or lease file changed.
