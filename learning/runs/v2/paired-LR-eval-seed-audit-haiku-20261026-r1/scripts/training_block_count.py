# Read-only: count seed-keyed integers (any nesting) per training-episode file that fall in D-upper, D-dev, B, or E blocks. No score fields read.
import json, sys
BLOCKS = {"D_dev": (0xD0000000, 0xD000003F), "D_upper": (0xD0000040, 0xD000007F),
          "B_block": (0xB0000000, 0xB00003E7), "E_block": (0xE0000000, 0xE00003E7)}
def seeds_in(o, out):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("seed", "actual_seed", "seeds", "episode_seed") or k.endswith("seed"):
                stack = [v]
                while stack:
                    x = stack.pop()
                    if isinstance(x, list): stack.extend(x)
                    elif isinstance(x, int) and not isinstance(x, bool): out.append(x)
            seeds_in(v, out)
    elif isinstance(o, list):
        for x in o: seeds_in(x, out)
for p in sys.argv[1:]:
    counts = {k: 0 for k in BLOCKS}; n = 0; seeds = []
    for line in open(p, encoding="utf-8"):
        if not line.strip(): continue
        n += 1; seeds_in(json.loads(line), seeds)
    for s in seeds:
        for k, (lo, hi) in BLOCKS.items():
            if lo <= s <= hi: counts[k] += 1
    print(p, "rows", n, "seed_ints", len(seeds), "distinct", len(set(seeds)), counts)
