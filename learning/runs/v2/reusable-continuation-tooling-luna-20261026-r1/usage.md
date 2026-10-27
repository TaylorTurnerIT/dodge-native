# Reusable D2 continuation preparation prototype

`continuation_tool.py` is a read-only authority inspector plus shared performance summarizer. It does not edit the frozen `runner.py`, create a registration, prepare a lease, or launch execution. The inspected registration must already be externally pinned. Source review remains one-time work; future use still needs an accepted parent receipt and a fresh, externally pinned registration.

## Inspect and prepare

Run from the repository root, with absolute paths and digests supplied by the parent authority source:

```sh
python3 -B learning/runs/v2/reusable-continuation-tooling-luna-20261026-r1/continuation_tool.py \
  --receipt "$PWD/learning/runs/v2/d2-gradient-parent-terminal-audit-20261025-r2/parent-terminal-receipt.json" \
  --receipt-sha256 7968a62b6e601fab971e4145dbaebfa1995c8f696e6df442ab70fc0435b74903 \
  --registration "$PWD/learning/runs/v2/D2-continuation180-parent-freeze-20261025-r4/registration-proposed.json" \
  --registration-sha256 0059ce1a3f2dae18a34b085b57b251c115ac53e7bc82835a6eff2164ac70e949 \
  --output "$PWD/learning/runs/v2/reusable-continuation-tooling-luna-20261026-r1/prepared-manifest.json"
```

Output uses exclusive creation. It binds receipt, registration, and controller-source SHA-256 values, and records the receipt's D2 identity, checkpoint, parent registration, cumulative counters, full outer wall, next episode indices, runtime, and policy. Capture stdout and stderr into closed logs; record argv, cwd, environment, exit status, and timing in the preparation receipt. The printed manifest digest must be registered externally before any downstream use. A local digest alone is not authority.

The prototype supports accepted same-phase D2 continuation authority only. It rejects failed, ineligible, promoted, cancelled, incomplete, wrong-phase, substituted-path, or mismatched-digest receipts. It does not infer acceptance from the latest campaign: the 2026-10-25-r2 phase-252 run remains pending parent audit and cannot be supplied as an accepted parent.

## Metrics

Call `summarize_performance(rows, metric="alive_frames")` or pass `metric="score"`. For 64 rows, it sorts metric values, averages the lowest 16 for Q1, the highest 16 for Q4, and all 64 for mean. Input row order has no effect. This is not a percentile interpolation and does not use seed order.

Historical phase-252 and phase-180 summary files remain unchanged. Recomputed canonical alive-frame values are respectively `532.8125 / 3192.3125 / 1604.078125` and `585.625 / 3502.5625 / 1854.46875` for Q1/Q4/mean. The former incorrect `617.25 / 2415.25` summary is not rewritten.

## Readiness boundary

This prototype removes repeated hand-checking of accepted-parent authority fields and provides one tested metric implementation. It does **not** remove per-run edits from the current hardcoded frozen adapter: `runner.py` and `execute_once.py` still contain parent counters, paths, lease identity, and run constants. Do not claim controller reuse or launch from this prototype. Frozen Haiku review and parent acceptance are required before adapting the controller to consume a data-only registration. Keep all existing receipt, source, runtime, lease, native, seed, cache, cancellation, resource, publication, and outer-wall guards intact.
