"""Compare death-trace rows with saved control-frequency rows, game by game."""
import hashlib
import json
import sys
from pathlib import Path

KEYS = ("seed", "alive_frames", "gameplay_frames", "death_cause", "fatal_gameplay_frame", "score_raw_fixed",
        "terminated", "truncated")


def compare(new_path, saved_path):
    new, saved = json.load(open(new_path)), json.load(open(saved_path))
    mismatches = []
    if len(new["rows"]) != len(saved["rows"]):
        return dict(n=len(new["rows"]), saved_n=len(saved["rows"]), mismatches=["row count"])
    for a, b in zip(new["rows"], saved["rows"]):
        for key in KEYS:
            if key in b and a[key] != b[key]:
                mismatches.append(dict(seed=a["seed"], key=key, new=a[key], saved=b[key]))
        # Trace must agree with the env's own counters.
        t = a["trace"]
        if t["frames"] != a["gameplay_frames"]:
            mismatches.append(dict(seed=a["seed"], key="trace.frames", new=t["frames"], saved=a["gameplay_frames"]))
        if a["terminated"] and t["death"]["frame"] != a["fatal_gameplay_frame"]:
            mismatches.append(dict(seed=a["seed"], key="trace.death.frame", new=t["death"]["frame"],
                                   saved=a["fatal_gameplay_frame"]))
        if a["terminated"] and t["death"]["cause"] != a["death_cause"]:
            mismatches.append(dict(seed=a["seed"], key="trace.death.cause", new=t["death"]["cause"], saved=a["death_cause"]))
    return dict(n=len(new["rows"]), mismatches=mismatches)


def gate(pairs, saved_dir, out=None):
    """Compare every `name` in `pairs` (new file stem -> saved file stem); optionally write the receipt."""
    groups = {}
    for name, (new_path, saved_path) in pairs.items():
        result = compare(new_path, saved_path)
        groups[name] = dict(games=result["n"], mismatches=len(result["mismatches"]),
                            first_mismatches=result["mismatches"][:5],
                            new_sha256=hashlib.sha256(Path(new_path).read_bytes()).hexdigest(),
                            saved_sha256=hashlib.sha256(Path(saved_path).read_bytes()).hexdigest())
    receipt = dict(schema="death_trace_replay_parity_v1", saved_rows=str(saved_dir),
                   compared_fields=list(KEYS) + ["trace.frames", "trace.death.frame", "trace.death.cause"],
                   groups=groups, games=sum(g["games"] for g in groups.values()),
                   mismatches=sum(g["mismatches"] for g in groups.values()))
    receipt["pass"] = receipt["mismatches"] == 0
    if out:
        Path(out).write_text(json.dumps(receipt, indent=1))
    return receipt


if __name__ == "__main__":
    if sys.argv[1] == "--gate":
        new_dir, saved_dir, out = Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
        pairs = {}
        for repeat in (1, 4):
            pairs[f"argmax_r{repeat}"] = (new_dir / f"argmax_r{repeat}.json", saved_dir / f"argmax_r{repeat}-rep0.json")
            for rep in (0, 1, 2):
                name = f"sampled_r{repeat}-rep{rep}"
                pairs[name] = (new_dir / f"{name}.json", saved_dir / f"{name}.json")
        receipt = gate(pairs, saved_dir, out)
        print(json.dumps({k: v for k, v in receipt.items() if k != "groups"}))
        raise SystemExit(0 if receipt["pass"] else 1)
    out = compare(sys.argv[1], sys.argv[2])
    print(json.dumps(dict(n=out["n"], n_mismatches=len(out["mismatches"]), first=out["mismatches"][:10])))
    raise SystemExit(1 if out["mismatches"] else 0)
