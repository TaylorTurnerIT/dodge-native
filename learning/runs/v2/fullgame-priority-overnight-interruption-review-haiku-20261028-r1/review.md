# Review: overnight interruption audit and lease release (run 3, replica-2 opening_priority)

Reviewed: `learning/runs/v2/fullgame-priority-overnight-interruption-audit-sonnet-20261028-r1/` (`interruption_audit.py`, `audit.json`, `lease-release.json`, `incident-summary.json`). Read-only. Full hashes and checks in `review.json`.

**Verdict: no blocking findings.**

## Verified

- Hashes match: `interruption_audit.py` e2bc1184…, `audit.json` 032e681c…, `lease-release.json` 14982746…, `incident-summary.json` 3cf1fcab….
- Lease owner `98c859dbdd6007277e0d18b3ebf49f31` is identical in registration, audit, and release.
- Audit written with O_EXCL + fsync before the lease clear. Release hash-binds the audit.
- All 13657 envelope pins re-hashed now: 0 mismatches. Pin-key digest 604f78dd… recomputed.
- Evidence snapshot (20 files, 3 dirs) unchanged since audit.
- Observer (76509) and worker (76517) groups gone; no run processes.
- Missing receipts confirmed absent. No terminal update 60. Prior completed-run audits unchanged.
- Timing: pmset sleep spans 354+345+1018 s = 1717 s. Wall 1825.8 s minus 1717 s ≈ 109 s, matching observer monotonic 109.94 s. This supports "active clock excluded sleep". Correlation only, not terminating-signal proof.

## Findings (none blocking)

| ID | Sev | Where | Issue |
|---|---|---|---|
| F1 | low | `incident-summary.json` `what_happened` | States the wrapper "hit its 30 min default timeout" as fact. Audit says only "consistent with". Reword. |
| F2 | low | `interruption_audit.py:201` (also 213, 242, 262, 264, 265) | Several `audit.json` labels are hardcoded, not computed. `parent324_unchanged` is supported only indirectly (lines 133–134). `original_summary_preserved` and `unstarted_paths_untouched` are not checked. Values are true on read-back. |
| F3 | low | `state.json` via `interruption_audit.py:317` | `mkstemp` leaves `state.json` at `0600`; siblings are `0644`. Pre-release mode and hash are not recorded, so "unrelated state preserved" rests on the in-process check only. Do not blind-restore. |
| F4 | low | `interruption_audit.py:273–291` | `release()` does not re-hash the evidence snapshot before clearing the lease. No effect here (snapshot verified unchanged). |
| F5 | info | `audit.json` | Sleep-to-active-clock arithmetic and post-wake progress alert (01:27:19, awake elapsed 226.59 s, about 116 s awake after the 01:25:23 wake with no progress rows) are not stated. Shows no output resumed after wake; cannot separate killed-at-wake from died-in-sleep. |
| F6 | info | git | HEAD moved to `a036df4` (01:40:04 CDT) during review. Its `state.json` and audit files match the reviewed hashes. |

## Limits

- Terminating signal, raw exit codes, direct reap, and whether sleep alone or the wrapper kill ended the processes remain unknown.
- Source binding is proven for files at review time. Runtime behaviour is not proven.
- Missing observer postflight status is not labelled proven.
- Nothing here inspects training metrics, performance, or D4 outcomes.
