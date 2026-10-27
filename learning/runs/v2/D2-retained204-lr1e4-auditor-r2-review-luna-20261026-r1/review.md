# R2 auditor review

## Decision

**Changes required before treating the auditor as provenance-complete.** The reviewed source and tests are frozen at the requested hashes. Published candidate metadata shows a contiguous prefix through update 252; updates 264, and 276 and terminal artifacts were not published at review time. Full-mode execution and frozen `validate_outputs` therefore remain unverified. This is an expected run gate, not an audit failure.

## Finding

**Blocker — active interpreter and runtime submodule origins are not fully bound.** `bind_environment()` checks `-B`, bytecode prefix, and absence of three top-level cache names. `load_frozen()` loads the pinned runner bytes and calls its real `load_registration()`. But the auditor never checks `Path(sys.executable).resolve()` against `reg["interpreter"]`, and `import_runtime()` checks only that `dodge_rl.__file__` is somewhere under `runtime_root`. It does not check the exact origins of `dodge_rl.checkpoints`, `dodge_rl.survival_gate`, or `dodge_rl.identity`, nor reject their preloaded `sys.modules` entries. The frozen worker does check its interpreter path and exact package `__init__.py`; the auditor does not inherit those worker checks.

A parent wrapper can import the audit function into an existing process, so these missing checks are reachable even if the standalone test command used the registered venv. A mismatched interpreter or cached runtime submodule could supply checkpoint decoding, identity, or survival-gate code outside the registered runtime while the current origin assertion still passes.

**Minimal fix:** after `load_registration()`, assert resolved `sys.executable` equals resolved `reg["interpreter"]`. Before runtime imports, reject cached `dodge_rl` and all `dodge_rl.*` entries (or validate each cached module); after import, assert exact resolved origins for the package and every used submodule. Add negative controls for a wrong interpreter and a preloaded out-of-runtime submodule.

## Checks supported by inspected artifacts

- `audit_candidates.py`, `test_audit_candidates.py`, `source-manifest.json`, and `receipt.json` match all four supplied SHA-256 pins.
- Frozen registration identifies run seed `3791628418`, run `D2-retained204-lr1e4-20261026-r1`, exact runner/launcher/helper paths, and 13,770 pins. The target source manifest pins the supplied registration digest.
- R2 uses the real `runner.load_registration()` preflight, verifies the transition helper is bound, and makes frozen launcher's `r` reference the exact audited runner. Its positive test covers that binding and the saved-LR helper call.
- LR audit recomputes full and LR-excluded optimizer fingerprints from the CPU parent and entry optimizer. Tests include forged fingerprint/identity and Adam-moment mutation controls.
- Candidate checks separate the strict mean-alive proposal threshold from competence (3060 frames), preserve false selection/continuation/terminal authority, compare full evaluation rows to JSONL, and check scores, reward formula, death/cap totals, and cause aggregates.
- Journal parsing uses one captured buffer; final checks compare consumed prefixes and rehash tracked files, registration pins, and bytecode prefix.
- Frozen tests log 35 passing tests. Their positive candidate gate covers 216 plus entry 204; test log does not establish all-seven candidate coverage or full-mode completion. The frozen full-mode attempt refused before candidate audit with `Full mode requires all seven published certificates`.
- Read-only directory inspection found candidate artifacts for 204, 216, 228, 240, and 252. Their published certificates each contain 64 rows and false competence. No checkpoint was decoded and no training, environment, optimizer, lease, or source state was changed by this review.

## Nonblocking notes

- Full-mode call order is statically coherent: it requires all seven published certificates, audits each, requires successful worker/execution status, binds the exact launcher to the audited runner, calls frozen `validate_outputs`, checks observer raw exits, then performs final stability and pin checks. This path still needs the authorized parent-side terminal run after all seven certificates publish.
- The frozen receipt is provisional through 252, proposes 252 only as a provisional mean-improvement candidate, and explicitly grants no selection, continuation, best-replacement, or terminal-acceptance authority.
- Raw exits, resource postflight, wall accounting, source postflight, final publication absence, and lease release remain parent-gated checks as recorded by the auditor.
