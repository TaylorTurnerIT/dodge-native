# Read-only: per file, min/max/distinct count of top-level-or-row "seed"/"actual_seed" integers. Prints no score fields.
import json, sys, collections
def seeds_in(o, out):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("seed", "actual_seed", "seeds", "episode_seed"):
                for x in (v if isinstance(v, list) else [v]):
                    if isinstance(x, int): out.append(x)
            seeds_in(v, out)
    elif isinstance(o, list):
        for x in o: seeds_in(x, out)
for p in sys.argv[1:]:
    out = []
    try:
        if p.endswith(".jsonl"):
            for line in open(p, encoding="utf-8"):
                if line.strip(): seeds_in(json.loads(line), out)
        else:
            seeds_in(json.load(open(p, encoding="utf-8")), out)
    except Exception as e:
        print(f"{p}\tERROR {type(e).__name__}"); continue
    if out:
        lo, hi = min(out), max(out)
        cls = "dev" if 0xD0000000 <= lo and hi <= 0xD000003F else ("upper_D" if 0xD0000040 <= lo and hi <= 0xD000007F else ("mixed_or_other"))
        print(f"{p}\tn={len(out)}\tdistinct={len(set(out))}\tmin={lo}\tmax={hi}\tclass={cls}")
