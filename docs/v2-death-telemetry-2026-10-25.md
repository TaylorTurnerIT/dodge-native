# Death telemetry, 2026-10-25

Native diagnostics now record the first alive-to-dead collision, its gameplay frame, and any later lethal contacts processed by the legacy loop in that same frame. Later contacts are observations, not additional episode deaths. Metadata stays outside neural inputs, snapshots, RNG and reward accounting. Reset clears it; a restored dead snapshot has an unknown cause.

One isolated-build diagnostic replayed checkpoint 000050 on the same 64 fixed D2 development seeds. Every episode matched its retained score, lifetime, termination and objective return exactly. Survival Q1 **648.25**, Q4 **4,508.8125**, mean **2,240.0** frames. Score Q1 **3.5**, Q4 **46.59375**, mean **20.59375**. These are development diagnostics, not qualification.

| First lethal contact | Deaths | Share | Mean alive frames in this category |
| --- | ---: | ---: | ---: |
| Normal enemy | 29 | 45.3125% | 2,473.31 |
| Kamikaze body | 3 | 4.6875% | 2,818.00 |
| Kamikaze explosion | 1 | 1.5625% | 4,280.00 |
| Fully expanded static rectangle | 21 | 32.8125% | 2,181.67 |
| Moving rectangle | 10 | 15.625% | 1,308.50 |

All 64 episodes died; no caps or unknown causes. The representative playback episode, index 58, survived 2,209 frames and scored 18 before hitting a static rectangle. Cause shares describe this fixed cohort and checkpoint; they do not estimate all future games.

Validation: the child ran workspace Rust tests, format and Clippy, including 82 core and 46 wrapper tests. Parent corrected Python row/counter validation, froze sources, obtained an independent static review with no findings, and passed **81 Python tests against the new isolated binary**. The existing training-identity test rejects the changed native source; its checks remain unchanged. No training ran and no historical checkpoint was promoted.

The accepted installed extension remains intact. The new wheel and extracted runtime are isolated, with hashes and build inputs retained. Setup failures remain recorded: the learning venv lacked pytest, one build selected CFFI, and another packaged the wrong module name. The established Python-project build recipe produced the validated wheel. Future training requires a fresh registration binding this binary and the survival-only gate.

Evidence: [parent reconciliation](../learning/runs/v2/death-telemetry-parent-validation-20261025-r1/parent-reconciliation.json), [cause counts and statistics](../learning/runs/v2/death-telemetry-parent-validation-20261025-r1/diagnostic-result.json), [paired outcome checks](../learning/runs/v2/death-telemetry-parent-validation-20261025-r1/paired-parity.json), [new binary](../learning/runs/v2/death-telemetry-parent-validation-20261025-r1/isolated-binary.json), [child implementation receipt](../learning/runs/v2/death-telemetry-20261025-r1/implementation-result.json).
