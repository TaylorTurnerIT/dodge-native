#!/usr/bin/env python3
"""Offline audit of six existing PPO worker-result snapshots. Stdlib only."""
import csv
import hashlib
import json
import os
import statistics
from collections import Counter, defaultdict

ROOT = "learning/runs/v2"
PACKAGE = os.path.join(ROOT, "progressive1000-opening-maintenance-integrated-parent-20261027-r1")
MANIFEST = os.path.join(PACKAGE, "six-endpoint-completion.json")
OUT = os.path.join(ROOT, "rl-next-experiments-exposure-parent-20261027-r1")
BINS = [(0, 1000), (1000, 2000), (2000, 3000), (3000, 4000),
        (4000, 5000), (5000, 6000), (6000, 7000), (7000, 8000),
        (8000, 9000), (9000, 10000), (10000, 11000), (11000, 12000),
        (12000, 13000), (13000, 14000), (14000, 15000), (15000, 16000),
        (16000, 17000), (17000, 18000)]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def mean(xs):
    return statistics.fmean(xs) if xs else None


def metric_summary(metrics):
    fields = ("approx_kl", "clip_fraction", "epochs_completed", "entropy",
              "explained_variance", "value_loss", "policy_loss")
    out = {f: {"mean": mean([m[f] for m in metrics if isinstance(m.get(f), (int, float))]),
               "first10_mean": mean([m[f] for m in metrics[:10] if isinstance(m.get(f), (int, float))]),
               "last10_mean": mean([m[f] for m in metrics[-10:] if isinstance(m.get(f), (int, float))]),
               "min": min([m[f] for m in metrics if isinstance(m.get(f), (int, float))], default=None),
               "max": max([m[f] for m in metrics if isinstance(m.get(f), (int, float))], default=None)} for f in fields}
    out["early_stop_updates"] = sum(bool(m.get("early_stop_kl")) for m in metrics)
    out["updates_with_less_than_4_epochs"] = sum(m.get("epochs_completed") != 4 for m in metrics)
    out["update_count"] = len(metrics)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    manifest = json.load(open(MANIFEST))
    assert manifest["formal_training_runs"] == 6
    rows = []
    run_results = []
    source_files = [{"path": MANIFEST, "sha256": sha256(MANIFEST), "bytes": os.path.getsize(MANIFEST)}]
    eval_path = os.path.join(ROOT, "progressive1000-full-run-evaluator-parent-20261027-r2", "result-summary.json")
    eval_summary = json.load(open(eval_path))
    source_files.append({"path": eval_path, "sha256": sha256(eval_path), "bytes": os.path.getsize(eval_path)})
    for endpoint in manifest["endpoints"]:
        audit_path = endpoint["audit"]
        run_dir = os.path.dirname(audit_path)
        result_path = os.path.join(run_dir, "worker-output", "worker-result.json")
        source_files.append({"path": result_path, "sha256": sha256(result_path), "bytes": os.path.getsize(result_path)})
        result = json.load(open(result_path))
        env = result["final_snapshot"]["environment"]
        arm = "curriculum" if "curriculum" in endpoint["run_id"] else "control"
        replica = int(endpoint["run_id"].split("replica-")[1].split("-")[0])
        exposure = defaultdict(int)
        for item in env["interval_exposure"]:
            key = (item["horizon"], item["low"], item["high"])
            exposure[key] += item["executed_gameplay_frames"]
        bins_sum = sum(exposure.values())
        native_gameplay = env["gameplay_frames_including_fatal"]
        update_horizon = defaultdict(int)
        for item in env["update_exposure"]:
            update_horizon[item["horizon"]] += item["raw_frames"]
        interval_horizon = defaultdict(int)
        for (horizon, low, high), frames in exposure.items():
            interval_horizon[horizon] += frames
        assignment_counts = Counter(item["horizon"] for item in env["assignments"])
        completions = env["completions"]
        outcome_counts = Counter()
        death_causes = Counter()
        for item in completions:
            info = item["native_info"]
            status = "artificial_cutoff" if info.get("truncated") else "natural_death" if info.get("terminated") else "other"
            outcome_counts[(item["horizon"], status)] += 1
            if info.get("terminated"):
                death_causes[info.get("death_cause", "unknown")] += 1
        assert bins_sum == native_gameplay, (endpoint["run_id"], bins_sum, native_gameplay)
        assert sum(update_horizon.values()) == native_gameplay, (endpoint["run_id"], sum(update_horizon.values()), native_gameplay)
        assert dict(interval_horizon) == dict(update_horizon), (endpoint["run_id"], dict(interval_horizon), dict(update_horizon))
        assert sum(assignment_counts.values()) == len(env["assignments"])
        metrics = result["final_snapshot"]["metrics"]
        mastery_windows = [w for b in env["boundaries"] for w in b.get("window_results", [])]
        metric_result = metric_summary(metrics)
        total_assignments = sum(assignment_counts.values())
        total_frames = native_gameplay
        run = {
            "run_id": endpoint["run_id"], "arm": arm, "replica": replica,
            "assignment_counts": {str(k): assignment_counts[k] for k in sorted(assignment_counts)},
            "assignment_fraction": {str(k): assignment_counts[k] / total_assignments for k in sorted(assignment_counts)},
            "gameplay_frames_by_assigned_horizon": {str(k): update_horizon[k] for k in sorted(update_horizon)},
            "gameplay_frame_fraction_by_assigned_horizon": {str(k): update_horizon[k] / total_frames for k in sorted(update_horizon)},
            "age_bins_by_assigned_horizon": {},
            "age_bin_total_frames": {},
            "native_gameplay_frames": native_gameplay,
            "accepted_raw_frames_total_including_startup": env["accepted_raw_frames_total"],
            "startup_frame_difference": env["accepted_raw_frames_total"] - native_gameplay,
            "completion_count": len(completions),
            "outcomes_by_horizon_and_kind": {f"{horizon}:{status}": count for (horizon, status), count in sorted(outcome_counts.items())},
            "natural_deaths": sum(count for (h, s), count in outcome_counts.items() if s == "natural_death"),
            "artificial_cutoffs": sum(count for (h, s), count in outcome_counts.items() if s == "artificial_cutoff"),
            "death_causes": dict(death_causes),
            "mastery_windows": {"count": len(mastery_windows), "passed": sum(bool(x) for x in mastery_windows), "failed": sum(not bool(x) for x in mastery_windows), "promotion_boundaries": sum(bool(b.get("promoted")) for b in env["boundaries"])},
            "metrics": metric_result,
            "conservation": {"age_bin_sum_equals_native_gameplay_frames": bins_sum == native_gameplay,
                             "update_horizon_sum_equals_native_gameplay_frames": sum(update_horizon.values()) == native_gameplay,
                             "interval_horizon_equals_update_horizon": dict(interval_horizon) == dict(update_horizon)}
        }
        for horizon in sorted(set(k[0] for k in exposure)):
            run["age_bins_by_assigned_horizon"][str(horizon)] = {}
            for low, high in BINS:
                frames = exposure.get((horizon, low, high), 0)
                run["age_bins_by_assigned_horizon"][str(horizon)][f"{low}-{high}"] = frames
                rows.append({"run_id": endpoint["run_id"], "arm": arm, "replica": replica,
                             "assigned_horizon": horizon, "age_low": low, "age_high": high,
                             "native_gameplay_frames": frames})
        for low, high in BINS:
            run["age_bin_total_frames"][f"{low}-{high}"] = sum(v for (h, l, hi), v in exposure.items() if l == low and hi == high)
        run_results.append(run)
    with open(os.path.join(OUT, "exposure.csv"), "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["run_id", "arm", "replica", "assigned_horizon", "age_low", "age_high", "native_gameplay_frames"])
        writer.writeheader(); writer.writerows(rows)
    arms = {}
    for arm in ("control", "curriculum"):
        selected = [r for r in run_results if r["arm"] == arm]
        frames = sum(r["native_gameplay_frames"] for r in selected)
        bin_sum = {f"{low}-{high}": sum(r["age_bin_total_frames"][f"{low}-{high}"] for r in selected) for low, high in BINS}
        horizon_sum = defaultdict(int)
        for r in selected:
            for horizon, value in r["gameplay_frames_by_assigned_horizon"].items():
                horizon_sum[horizon] += value
        assignments = defaultdict(int)
        for r in selected:
            for horizon, value in r["assignment_counts"].items():
                assignments[horizon] += value
        arms[arm] = {"replicas": len(selected), "native_gameplay_frames": frames,
                     "age_bin_total_frames": bin_sum,
                     "gameplay_frames_by_assigned_horizon": dict(horizon_sum),
                     "gameplay_frame_fraction_by_assigned_horizon": {h: v / frames for h, v in horizon_sum.items()},
                     "assignment_counts": dict(assignments),
                     "assignment_fraction": {h: v / sum(assignments.values()) for h, v in assignments.items()},
                     "natural_deaths": sum(r["natural_deaths"] for r in selected),
                     "artificial_cutoffs": sum(r["artificial_cutoffs"] for r in selected),
                     "mastery_windows": {"count": sum(r["mastery_windows"]["count"] for r in selected),
                                         "passed": sum(r["mastery_windows"]["passed"] for r in selected),
                                         "failed": sum(r["mastery_windows"]["failed"] for r in selected)}}
    aggregate = {"source_manifest": MANIFEST, "bin_unit": "native gameplay frames", "age_bins": BINS,
                 "decision_counts_inferred": False, "arm_aggregates": arms,
                 "existing_terminal_evaluation_summary": {"status": eval_summary["status"],
                     "control_mean": eval_summary["descriptive_arm_aggregates"]["control"]["mean_of_three_policy_summaries"]["Mean"],
                     "control_Q1": eval_summary["descriptive_arm_aggregates"]["control"]["mean_of_three_policy_summaries"]["Q1"],
                     "curriculum_mean": eval_summary["descriptive_arm_aggregates"]["curriculum"]["mean_of_three_policy_summaries"]["Mean"],
                     "curriculum_Q1": eval_summary["descriptive_arm_aggregates"]["curriculum"]["mean_of_three_policy_summaries"]["Q1"],
                     "mean_delta": eval_summary["curriculum_minus_control_across_three_descriptive"]["Mean"]["mean"],
                     "Q1_delta": eval_summary["curriculum_minus_control_across_three_descriptive"]["Q1"]["mean"],
                     "Q4_delta": eval_summary["curriculum_minus_control_across_three_descriptive"]["Q4"]["mean"]},
                 "runs": run_results}
    with open(os.path.join(OUT, "exposure.json"), "w") as f:
        json.dump(aggregate, f, indent=2, sort_keys=True); f.write("\n")
    receipt = {"analysis": "stdlib-only offline worker-result analysis", "training_or_game_execution": False,
               "checkpoint_loads": False, "inputs": source_files,
               "outputs": ["analyze_exposure.py", "exposure.json", "exposure.csv", "data-receipt.json", "diagnostic.md"]}
    with open(os.path.join(OUT, "data-receipt.json"), "w") as f:
        json.dump(receipt, f, indent=2, sort_keys=True); f.write("\n")
    print(json.dumps({"runs": [{"run_id": r["run_id"], "assignment_counts": r["assignment_counts"],
        "gameplay_frames_by_assigned_horizon": r["gameplay_frames_by_assigned_horizon"],
        "age_bin_total_frames": r["age_bin_total_frames"], "outcomes": r["outcomes_by_horizon_and_kind"],
        "mastery_windows": r["mastery_windows"], "metrics": r["metrics"]} for r in run_results]}, indent=2))

if __name__ == "__main__":
    main()
