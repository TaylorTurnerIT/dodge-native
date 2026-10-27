"""Independent parent audit; reads completed frozen training evidence only."""
import collections
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
OWN = Path(__file__).resolve().parent
SOURCE = ROOT / "learning/runs/v2/d2-training-v3-adapter-prepare-20261025-r5"
REG = ROOT / "learning/runs/v2/d2-training-v3-parent-prepare-20261025-r2/registration-r8.json"
REG_SHA = "d502c6761064727a610127fc58073e3a4c062fc928ea1e26de5718ad6aee6dcb"
sys.path.insert(0, str(SOURCE))
import runner as r
import execute_once as launcher


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


started = time.monotonic()
reg, config = r.load_registration(REG, REG_SHA)
out = Path(reg["output"])
observer = ROOT / "learning/runs/v2/D2-training-v3-execution-observer-20261025-r1"
ob = r.read(observer / "observation.json")
execution = r.read(out / "execution-result.json")
worker = r.read(out / "worker-result.json")
launch = r.read(out / "worker-launch.json")
assert execution["status"] == "passed" and worker["status"] == "completed"
assert ob["launch_count"] == execution["actual_worker_launch_count"] == 1
assert ob["outer_raw_exit"] == execution["observed_worker_raw_exit"] == 0
assert execution["directly_reaped"] and ob["directly_reaped"]
assert execution["first_observed_failure"] is None and worker["first_failure"] is None
assert ob.get("first_event") is None and not ob["events"] and not ob["cleanup_signals"]
assert execution["cleanup"] is None
assert not (out / "publication-failure.json").exists() and not Path(reg["cancel_path"]).exists()
assert ob["command"] == r.read(REG.with_name("registration-r8-pin.json"))["command"]
assert ob["registration_sha256"] == execution["registration_sha256"] == REG_SHA
assert ob["inclusive_process_wall_seconds"] <= 1800 and ob["observer_inclusive_wall_seconds"] <= 1800
assert worker["work_elapsed_seconds"] < 1600 and worker["elapsed_seconds"] < 1600
assert worker["peak_rss_bytes"] <= 6442450944 and worker["peak_mps_driver_bytes"] <= 6442450944
samples = rows(observer / "resources.jsonl")
assert samples and all(s["aggregate_rss_bytes"] <= 6442450944 for s in samples)
max_rss = max(s["aggregate_rss_bytes"] for s in samples)
assert max_rss == ob["max_aggregate_rss_bytes"]
assert samples[-1]["elapsed_since_command_start"] >= ob["inclusive_process_wall_seconds"] - 2
assert all(b["monotonic"] >= a["monotonic"] for a, b in zip(samples, samples[1:]))
process_text = subprocess.check_output(["/bin/ps", "-axo", "pid=,pgid="], text=True)
processes = [tuple(map(int, line.split())) for line in process_text.splitlines()]
assert not any(pid in (ob["outer_pid"], launch["worker_pid"]) or group == launch["owned_pgid"]
               for pid, group in processes)
assert launcher.group_exists(launch["owned_pgid"]) is False
checks = launcher.validate_outputs(reg, worker, REG_SHA)
assert checks == execution["evidence_checks"]
evaluations = []
for update in (0, 72):
    cert = r.read(out / f"development-{update:06d}.json")
    episodes = rows(out / f"development-{update:06d}.jsonl")
    assert episodes == cert["evaluation"]["rows"]
    values = sorted(row["alive_frames"] for row in episodes)
    evaluations.append({"update": update, "episodes": len(episodes),
                        "q1_bottom16_mean": sum(values[:16]) / 16,
                        "q4_top16_mean": sum(values[-16:]) / 16,
                        "mean_alive_frames": sum(values) / 64,
                        "deaths": sum(row["terminated"] for row in episodes),
                        "caps": sum(row["truncated"] for row in episodes),
                        "death_causes": dict(collections.Counter(row["death_cause"] for row in episodes)),
                        "checkpoint_sha256": cert["checkpoint_sha256"]})
metrics = rows(out / "training-metrics.jsonl")
windows = {}
for name, values in (("all72", metrics), ("first8", metrics[:8]), ("last8", metrics[-8:])):
    windows[name] = {}
    for when, prefix in (("pre_update", "pre"), ("post_update", "post")):
        for key in ("explained_variance", "residual_variance", "residual_mse", "target_variance"):
            windows[name][prefix + "_" + key] = sum(row["metrics"]["critic_diagnostics"][when][key]
                                                   for row in values) / len(values)
fit_improved = sum(row["metrics"]["critic_diagnostics"]["post_update"]["residual_mse"]
                   < row["metrics"]["critic_diagnostics"]["pre_update"]["residual_mse"] for row in metrics)
from dodge_rl import checkpoints as ckpt
candidate = out / "checkpoint-000072-candidate.pt"
state = ckpt.load_checkpoint(candidate, expected_sha256=checks["final_checkpoint_sha256"])
assert state["consumed_iteration_wall_seconds"] < 1600
artifacts = {str(p): r.sha(p) for p in out.iterdir() if p.is_file()}
for name in ("observation.json", "launch.json", "resources.jsonl", "terminal-audit.json", "observe.py"):
    artifacts[str(observer / name)] = r.sha(observer / name)
r.verify_pins(reg["pins"])
r.check_import_cache(reg)
result = {"schema": "D2_training_v3_parent_terminal_audit_v1", "status": "passed",
          "recorded_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
          "registration_path": str(REG), "registration_sha256": REG_SHA,
          "pins_checked": len(reg["pins"]), "checks": checks, "evaluations": evaluations,
          "raw_outer_exit": ob["outer_raw_exit"], "raw_worker_exit": execution["observed_worker_raw_exit"],
          "inclusive_wall_seconds": ob["inclusive_process_wall_seconds"],
          "worker_work_elapsed_seconds": worker["work_elapsed_seconds"],
          "max_sampled_aggregate_rss_bytes": max_rss,
          "worker_peak_rss_bytes": worker["peak_rss_bytes"],
          "worker_peak_sampled_mps_driver_bytes": worker["peak_mps_driver_bytes"],
          "resource_samples": len(samples), "max_sample_gap_seconds": max(b["monotonic"]-a["monotonic"] for a,b in zip(samples,samples[1:])),
          "resource_limitation": "Aggregate RSS and MPS driver values are sampled, not continuous peaks; worker RSS additionally uses process high-water.",
          "cancellation_lineage": [], "publication_failure_present": False,
          "outer_worker_group_absent_independently_observed": True,
          "cache_prefix_empty": True, "checkpoint_metadata_unchanged": True,
          "consumed_iteration_wall_seconds_at_checkpoint": state["consumed_iteration_wall_seconds"],
          "critic_windows": windows, "same_batch_fit_mse_improved_updates": fit_improved,
          "critic_limitation": "In-sample self-bootstrapped GAE targets; no held-out accuracy or causal interference conclusion.",
          "artifacts": artifacts, "audit_elapsed_seconds": time.monotonic() - started}
r.save(OWN / "audit.json", result)
print(json.dumps({k: v for k, v in result.items() if k not in ("artifacts", "checks")}, indent=2))
