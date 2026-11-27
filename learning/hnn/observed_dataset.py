"""Strip a native dataset stream to visible geometry for estimator training."""
import json
import sys

for line in sys.stdin:
    row = json.loads(line)
    if "end" in row:
        print(json.dumps(row, separators=(",", ":")))
        continue
    output = {
        "s": row["s"], "f": row["f"], "p": row["p"][:2],
        "e": [[e[0], e[1], e[4], e[5]] for e in row["e"] if e[5] < 2],
        "r": [r[:4] for r in row.get("r", [])],
    }
    print(json.dumps(output, separators=(",", ":")))
