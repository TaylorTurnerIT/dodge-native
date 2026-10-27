"""One fixed-cohort inference parity and death-cause diagnostic; no gradients."""
from pathlib import Path
import hashlib
import json
import resource
import statistics
import sys
import time
import traceback

OUT = Path(__file__).resolve().parent
PLAN = json.loads((OUT / "diagnostic-plan.json").read_text())
START = time.monotonic()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def publish(name, value):
    with (OUT / name).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def main():
    for name, digest in PLAN["runtime_pins"].items():
        assert sha(OUT / name) == digest, name
    assert sha(PLAN["checkpoint"]) == PLAN["checkpoint_sha256"]
    assert sha(PLAN["certificate"]) == PLAN["certificate_sha256"]
    sys.path.insert(0, str(OUT / "runtime"))
    import torch
    import dodge_rl
    from dodge_rl.checkpoints import load_checkpoint
    from dodge_rl.dev_eval import evaluate
    from dodge_rl.models.teacher import OmniscientEntityTeacher

    assert str(OUT / "runtime") in dodge_rl.__file__
    torch.set_num_threads(4)
    state = load_checkpoint(Path(PLAN["checkpoint"]), expected_sha256=PLAN["checkpoint_sha256"])
    model = OmniscientEntityTeacher().to("mps")
    model.load_state_dict(state["model"], strict=True)
    model.eval()

    def guard():
        if time.monotonic() - START > PLAN["wall_seconds"]:
            raise RuntimeError("Death diagnostic wall budget exceeded")
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > PLAN["RSS_bytes"]:
            raise RuntimeError("Death diagnostic RSS budget exceeded")
        if torch.mps.driver_allocated_memory() > PLAN["RSS_bytes"]:
            raise RuntimeError("Death diagnostic MPS budget exceeded")

    with (OUT / "diagnostic-episodes.jsonl").open("x") as stream:
        result = evaluate(model, "D2", "mps", check_guard=guard, episode_stream=stream)
    publish("diagnostic-evaluation.json", result)
    expected = json.loads(Path(PLAN["certificate"]).read_text())["evaluations"]["D2"]
    mismatches = []
    for old, new in zip(expected["rows"], result["rows"], strict=True):
        for name in ("episode_index", "seed", "alive_frames", "gameplay_frames", "score_raw_fixed",
                     "score", "objective_return", "terminated", "truncated"):
            if old[name] != new[name]:
                mismatches.append({"episode": old["episode_index"], "field": name,
                                   "old": old[name], "new": new[name]})
    publish("paired-parity.json", {"episodes": len(result["rows"]), "mismatches": mismatches})
    assert not mismatches, "Instrumented binary changed recorded episode outcomes"
    assert sum(result["death_causes"].values()) == result["deaths"]
    summary = {}
    for metric in ("alive_frames", "score"):
        values = sorted(row[metric] for row in result["rows"])
        summary[metric] = {"Q1": statistics.mean(values[:16]), "Q4": statistics.mean(values[-16:]),
                           "mean": statistics.mean(values)}
    causes = {}
    for cause, count in result["death_causes"].items():
        rows = [row for row in result["rows"] if row["death_cause"] == cause]
        causes[cause] = {"count": count, "fraction_of_deaths": count / result["deaths"],
                         "mean_alive_frames": statistics.mean(row["alive_frames"] for row in rows) if rows else None}
    selected = next(row for row in result["rows"] if row["episode_index"] == 58)
    publish("diagnostic-result.json", {"status": "passed_exact64episode_outcome_parity",
                                      "scope": "Fixed-development inference diagnostic; no qualification or checkpoint promotion.",
                                      "training": False, "gradients": False, "episodes": 64,
                                      "deaths": result["deaths"], "caps": result["caps"],
                                      "statistics": summary, "death_causes": causes,
                                      "representative_episode": selected,
                                      "wall_seconds": time.monotonic() - START,
                                      "RSS_peak_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                                      "MPS_driver_bytes": torch.mps.driver_allocated_memory()})
    for name, digest in PLAN["runtime_pins"].items():
        assert sha(OUT / name) == digest, name
    assert sha(PLAN["checkpoint"]) == PLAN["checkpoint_sha256"]
    print(json.dumps({"status": "passed", "statistics": summary, "death_causes": causes,
                      "representative_cause": selected["death_cause"]}), flush=True)


publish("diagnostic-started.json", {"monotonic": START, "actual_launch_count": 1,
                                    "plan_sha256": sha(OUT / "diagnostic-plan.json")})
try:
    main()
except BaseException as error:
    publish("diagnostic-failure.json", {"error": repr(error), "traceback": traceback.format_exc(),
                                        "wall_seconds": time.monotonic() - START})
    raise
