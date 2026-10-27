# Long D2 results, 2026-10-25

The worker completed **384 D2 updates** and closed below the progression gate. Outer finalization then failed after the observer reported `Owned identity changed: worker` and sent SIGTERM. The single run's outer exit was **1**, with observed wall time **6,776.803289790987 seconds**; it is not an accepted experiment.

| Retained development evaluation | Mean score | Mean alive frames | Checkpoint |
| --- | ---: | ---: | --- |
| Best score and survival | 20.59375 | 2240.0 | 000050 |
| Final | 14.40625 | 1654.546875 | 000058 |

Each point used 64 fixed-seed D2 episodes with deterministic argmax, patterns and powerups enabled; all 64 ended in death, with no caps. There were 24 learned evaluations plus the initial entry control. None passed the unchanged **score ≥50 and alive frames ≥3060** gate. Selecting the best development checkpoint does not establish held-out qualification.

New training collected **25,130,299 raw frames**, **6,291,456 decisions** and **43,808 optimizer steps**. Worker integrity checks passed at all **1,355 boundaries**. Observed worker peaks were RSS **863,633,408 bytes**, MPS driver **2,459,009,024 bytes**, and resource sample gap **0.2188208750449121 seconds**, within their existing limits.

The observer error preceded the supervisor's direct worker reap; the worker exited **2**, retaining `budget_closed_below_gate`. The observer's subsequent SIGTERM interrupted outer finalization, leaving no mandatory execution integrity summary. The mismatching process-census row was not retained, so an exit-transition race remains a hypothesis rather than a proved cause. Later IPC loss is cleanup evidence.

Parent verified all 25 evaluation calculations and checkpoint hashes, **10,294 source bindings**, **120 campaign/receipt artifacts** and **153 monitor-manifest members**. All three owned groups and the observer are absent, with direct-parent wait reports retained. Parent cleared the exact lease; failed checkpoints, metadata and receipts remain unchanged. No retry, resume, D3, student or follow-on experiment is authorized.

Sonnet's read-only diagnosis is reconciled. Evaluation-window mean scores rose from 6.865625 to 17.4609375; the last five averaged 17.9984375. More training remains plausible, but sufficiency is unproved. KL early stopping occurred in 230/384 updates; mean logged pre-clip gradient norms exceeded 0.5 in every update. These observations do not establish that gradient clipping caused slow learning.

The proposed 96-update clipping experiment is not executable as written: its comparison includes unreachable update 112, and its negative-explained-variance stop would reject baseline update 1. Fixed-seed checkpoint variation is policy variation; across-seed uncertainty does not measure run-to-run variation. A flat score/frame ratio does not require changing rewards: longer survival can also satisfy both gates. The proposed observer exit exception also needs separate design and validation. No new work was launched. [Parent diagnosis reconciliation](../learning/runs/v2/postovernight-long-D2-r2-terminal-diagnosis-parent-r1/parent-reconciliation.json) · [Recomputed statistics](../learning/runs/v2/postovernight-long-D2-r2-terminal-diagnosis-parent-r1/recomputed-statistics.json).

Evidence: [parent audit](../learning/runs/v2/postovernight-long-D2-r2-parent-audit-r1/parent-reconciliation.json), [lease clearance](../learning/runs/v2/postovernight-long-D2-r2-parent-audit-r1/lease-clear-receipt.json), [terminal report](../learning/runs/v2/postovernight-long-D2-execution-observer-r2b/monitor/terminal-report.md), [detailed metrics](../learning/runs/v2/postovernight-long-D2-execution-observer-r2b/monitor/terminal-evidence.json), [observer result](../learning/runs/v2/postovernight-long-D2-execution-observer-r2b/execution-result.json).
