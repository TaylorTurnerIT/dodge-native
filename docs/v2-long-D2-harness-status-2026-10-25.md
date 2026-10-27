# Long D2 harness status, 2026-10-25

Frozen r14 passed independent review and all validation gates. The one-shot D2 run completed 384 worker updates below gate, but outer finalization failed after an observer identity-check error; [results and audit](v2-long-D2-results-2026-10-25.md). All owned work stopped, parent cleared the lease, and the scheduler remains disabled.

r14 limits CPython thread-switch intervals to 100 microseconds during forced verification, restores the original interval, and preserves callback failures before cleanup interruptions. Model, PPO, rewards, seeds, gates and resource limits remain unchanged.

Current validation passed once:

- **143 tests:** 112 current inherited methods and 31 scheduling, chronology and scanner methods; no historical-target rebinding.
- **15 real-OS lifecycle fixtures**, including wedged-worker direct reaping.
- **Contention gate:** all 12 contended boundaries passed in 0.181997084–0.197388542 seconds; total stage wall was 5.132069042 seconds. Full actual B/R/A endpoint checks passed.
- **Startup:** real imports, origins and unchanged `check_frozen` checks passed, without D1 decoding, gameplay, inference or gradients.

Freeze measured B253/R37/A9998 and 128 capsule members. The parent rehashed 1,477 review inputs and 38 outputs before reserving the exact production lease. Detailed timing, resource readings, raw exits and hashes are in the linked receipts.

Harness validation does not qualify the teacher. OS fixtures use identity/runtime/summary stubs and injected RSS; genuine parent-death worker reaping remains unproven. Contention timing establishes only that synthetic workload. The completed run's retained development results reached 2240.0 mean alive frames and mean score 20.59375 at its best checkpoint, below gate and without accepted outer finalization.

All failed runs and setup attempts remain intact. r12 failed an overbroad test scan and exposed a callback/cleanup chronology bug; r13 produced no candidate after a bad lookup; r14's child wrapper failed before launching tests. A separate parent wrapper ran the first actual r14 suite without changing frozen source. The parent's first freeze-wrapper attempt also failed before launching freeze; both setup failures remain documented.

Evidence:

- [Source and test reconciliation](../learning/runs/v2-orchestration/postovernight-long-D2-r14-parent-reconciliation.json)
- [All validation gates and limitations](../learning/runs/v2/postovernight-long-D2-r14-parent-validation-r1/validation-result.json)
- [Independent review](../learning/runs/v2/postovernight-long-D2-boundary-review-r14/audit.md) and [parent reconciliation](../learning/runs/v2-orchestration/postovernight-long-D2-boundary-review-r14-parent-reconciliation.json)
- [One-shot acceptance](../learning/runs/v2-orchestration/postovernight-long-D2-r14-execution-acceptance.json) and [exact execution plan](../learning/runs/v2-orchestration/postovernight-long-D2-execution-r2-plan.json)
- Retained failures: [r11](../learning/runs/v2-orchestration/postovernight-long-D2-r11-parent-reconciliation.json), [r12](../learning/runs/v2-orchestration/postovernight-long-D2-r12-parent-reconciliation.json), [r13](../learning/runs/v2-orchestration/postovernight-long-D2-r13-parent-reconciliation.json), [r14 setup](../learning/runs/v2/postovernight-long-D2-boundary-prepare-r14/setup-failure.json).

Actual launch/raw/wall, evaluations, counters, resource readings and owned cleanup are retained in the terminal audit. The mandatory outer integrity summary is missing, so no acceptance is granted. No retry, failed-weight resume, D3, student or follow-on experiment is authorized.

Sonnet's terminal diagnosis is [reconciled](../learning/runs/v2/postovernight-long-D2-r2-terminal-diagnosis-parent-r1/parent-reconciliation.json). An exit/zombie census race is plausible; the missing row leaves the changed identity field unknown. Future observer design should retain process state and per-key mismatch evidence before raising. The proposed two-sample exit exception is not approved or implemented. Frozen acceptance allows exit 0 or 2 with all required receipts; this run returned 1 and remains failed.

The first execution observer launched no campaign because it checked the D1 row log against the evaluation-certificate hash. Parent verified the correct certificate and zero launches, retained that observer, and launched the corrected external wrapper once; production source and limits stayed unchanged. [Reconciliation](../learning/runs/v2-orchestration/postovernight-long-D2-execution-r2-prelaunch-parent-reconciliation.json) · [Corrected observer](../learning/runs/v2/postovernight-long-D2-execution-observer-r2b/).
