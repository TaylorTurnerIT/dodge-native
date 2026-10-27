# Frozen source review: retained 276 auditor r3

**No findings.**

Reviewed auditor `audit_candidates.py` (`98a58d8300eebd4630eb5d8ba66cf4880b49fc0526253d3bb8fe4b9d485ab707`) and strict wrapper `wrapper.py` (`fbc3e71532b4db918042c962efa61172848a40626ec065c78838d4d858d8f854`). Their hashes match the frozen source manifest and preparation receipt.

The full-mode path binds the registered observer directory and source digest. The wrapper refuses full mode on its CLI; only the parent-owned explicit function call can request it. The auditor checks the seven registered candidates, exact accepted parent entry state, effective LR, candidate and evaluation bindings, counters, resume state, journal prefixes, raw-frame conservation, and monotonic retained-best calculation. Wrapper plus pinned launcher cover interpreter and import origins, pins, terminal exits, registered time and resource limits, postflight state, and process absence.

Existing CPU logs report 55 auditor tests and 25 wrapper tests passing. They are test evidence only. This review did not run an actual audit, load checkpoints, or read live-run outputs, state, or lease. Parent retains full postflight and acceptance.
