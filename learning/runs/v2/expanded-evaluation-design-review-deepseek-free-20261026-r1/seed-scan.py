#!/usr/bin/env python3
"""Read-only partial seed-exposure spot check for the two proposed ranges.

Stdlib only. Scans accessible training-episodes.jsonl and development-*.jsonl
under learning/runs/v2 for `actual_seed` / `seed` values inside the proposed
ranges. This is a corroborating subset check, not the full ancestry audit
required by the proposal.

No checkpoint binaries, no B/E outcome paths, no environment, no launch.
"""

import glob
import json
import os
import re

V2 = "/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2"
OUT = os.path.join(V2, "expanded-evaluation-design-review-deepseek-free-20261026-r1")

RANGES = {
    "ranking": (3506438144, 3506439167),
    "confirmation": (3523215360, 3523216383),
}

ACTUAL_RE = re.compile(r'"actual_seed"\s*:\s*(\d+)')
SEED_RE = re.compile(r'"seed"\s*:\s*(\d+)')


def main():
    files = sorted(
        glob.glob(os.path.join(V2, "**/training-episodes.jsonl"), recursive=True)
        + glob.glob(os.path.join(V2, "**/development-*.jsonl"), recursive=True)
    )
    hits = []
    total = 0
    per_range = {k: 0 for k in RANGES}
    for path in files:
        try:
            data = open(path, "r", encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for regex, kind in ((ACTUAL_RE, "actual_seed"), (SEED_RE, "seed")):
            for m in regex.finditer(data):
                value = int(m.group(1))
                total += 1
                for name, (lo, hi) in RANGES.items():
                    if lo <= value <= hi:
                        hits.append({"path": path, "value": value, "field": kind, "range": name})
                        per_range[name] += 1
    summary = {
        "schema": "expanded_eval_seed_scan_subset_v1",
        "scope": "accessible training-episodes.jsonl and development-*.jsonl under learning/runs/v2",
        "files_scanned": len(files),
        "seed_tokens_scanned": total,
        "ranges": {k: {"lo": v[0], "hi": v[1], "hits": per_range[k]} for k, v in RANGES.items()},
        "hits": hits,
        "limits": [
            "Subset only: not all artifacts, not checkpoint binaries, not sealed/B/E paths.",
            "No reservation registry/config union audit.",
            "No proof of unrecorded construction/use.",
            "Does not replace the full ancestry audit required by the proposal.",
        ],
    }
    out = os.path.join(OUT, "seed-scan-summary.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
        f.write("\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
