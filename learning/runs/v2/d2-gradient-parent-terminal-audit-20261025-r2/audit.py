"""Independent parent audit; reads completed frozen training evidence only."""
import collections
import datetime
import hashlib
import json
import math
import statistics
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
OWN = Path(__file__).resolve().parent
SOURCE = ROOT / "learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5"
REG = SOURCE / "registration-proposed.json"
REG_SHA = "6f4adf808789655a663800a1e4a0613192d02b0c8287d121455ea748fe043916"
sys.path.insert(0, str(SOURCE))
import runner as r
import execute_once as launcher


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


started = time.monotonic()
reg, config = r.load_registration(REG, REG_SHA)
out = Path(reg["output"])
observer = ROOT / "learning/runs/v2/D2-gradient-execution-observer-20261025-r2"
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
assert ob["command"] == r.read(ROOT / "learning/runs/v2/D2-gradient-campaign-parent-authorization-20261025-r2/registration-pin.json")["command"]
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
assert json.loads(json.dumps(checks)) == execution["evidence_checks"]
evaluations = []
for update in (132, 180):
    cert = r.read(out / f"development-{update:06d}.json")
    episodes = rows(out / f"development-{update:06d}.jsonl")
    assert sorted(episodes, key=lambda row: row["seed"]) == cert["evaluation"]["rows"]
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
for name, values in (("all48", metrics), ("first8", metrics[:8]), ("last8", metrics[-8:])):
    windows[name] = {}
    for when, prefix in (("pre_update", "pre"), ("post_update", "post")):
        for key in ("explained_variance", "residual_variance", "residual_mse", "target_variance"):
            windows[name][prefix + "_" + key] = sum(row["metrics"]["critic_diagnostics"][when][key]
                                                   for row in values) / len(values)
fit_improved = sum(row["metrics"]["critic_diagnostics"]["post_update"]["residual_mse"]
                   < row["metrics"]["critic_diagnostics"]["pre_update"]["residual_mse"] for row in metrics)
from dodge_rl import checkpoints as ckpt
candidate = out / "checkpoint-000180-candidate.pt"
state = ckpt.load_checkpoint(candidate, expected_sha256=checks["final_checkpoint_sha256"])
assert state["current_iteration_wall_seconds"] < 1600
parent_state = ckpt.load_checkpoint(Path(reg["parent"]["path"]), expected_sha256=r.PARENT_SHA)
journal = rows(out / "training-episodes.jsonl")
parent_abandoned = [row["info"] for row in journal if row["kind"] == "abandoned_parent_episode"]
assert parent_abandoned == parent_state["abandoned_current_episodes"]
assert state["parent_abandoned_current_episodes"] == parent_state["abandoned_current_episodes"]
initial = next(row for row in journal if row["kind"] == "initial")
assert [row["seed"]["episode"] for row in initial["info"]] == parent_state["next_episode_indices"]
completed_frames = sum(row["info"]["gameplay_frames"] for row in journal if row["kind"] == "completed")
final_abandoned_frames = sum(item["gameplay_frames"] for item in state["abandoned_current_episodes"])
assert completed_frames + final_abandoned_frames == worker["counters"]["raw_frames"]
previous_eval = r.read(Path(reg["parent"]["path"]).parent / "development-000132.json")["evaluation"]["rows"]
entry_eval = r.read(out / "development-000132.json")["evaluation"]["rows"]
assert entry_eval == previous_eval
assert math.isclose(state["cumulative_D2_inclusive_wall_seconds"], r.PARENT_WALL_SECONDS + state["current_iteration_wall_seconds"], abs_tol=1e-9)
assert state["current_iteration_wall_seconds"] < worker["current_iteration_wall_seconds"] < worker["elapsed_seconds"]
assert not [p for p in (Path(reg["runtime_root"]) / "dodge_rl").rglob("*.pyc") if "__pycache__" not in p.parts]
entry_by_seed = {row["seed"]: row for row in entry_eval}
final_rows = r.read(out / "development-000180.json")["evaluation"]["rows"]
paired_deltas = [row["alive_frames"] - entry_by_seed[row["seed"]]["alive_frames"] for row in final_rows]
cause_survival = {}
for row in final_rows:
    cause_survival.setdefault(row["death_cause"], []).append(row["alive_frames"])
cause_survival = {key: {"count": len(vals), "mean_alive_frames": sum(vals)/len(vals)} for key, vals in cause_survival.items()}
artifacts = {str(p): r.sha(p) for p in out.iterdir() if p.is_file()}
for name in ("observation.json", "launch.json", "resources.jsonl", "observe.py"):
    artifacts[str(observer / name)] = r.sha(observer / name)
r.verify_pins(reg["pins"])
r.check_import_cache(reg)
probes = [row["metrics"]["gradient_alignment_diagnostics"] for row in metrics]
assert len(probes) == 48
assert all(p["backend"] == "cpu_shadow" and p["minibatch_count"] == 512 and p["probe_count"] == 1
           and p["measures_live_MPS_gradients"] is False and p["coverage"] == {"actor_used":33,"critic_used":33,"elements":286976,"parameters":33} for p in probes)
gradient = {"probes":len(probes), "backend":"cpu_shadow", "minibatch_samples_per_probe":512,
            "shared_parameters":33,"shared_elements":286976,
            "scope":"Pre-step raw CPU reference gradients on first existing minibatch per update; actor includes entropy, critic includes vf_coef; not live MPS or Adam-preconditioned directions.",
            "causal_harm_claim":False,"windows":{},"groups":{}}
for name, subset in (("all48",probes),("first8",probes[:8]),("last8",probes[-8:])):
    cosine=[p["cosine"] for p in subset]; ratio=[p["norm_ratio_critic_over_actor"] for p in subset]
    gradient["windows"][name]={"cosine_mean":statistics.mean(cosine),"cosine_median":statistics.median(cosine),
        "cosine_min":min(cosine),"cosine_max":max(cosine),"negative_cosines":sum(x<0 for x in cosine),
        "critic_over_actor_norm_ratio_mean":statistics.mean(ratio),"critic_over_actor_norm_ratio_median":statistics.median(ratio),
        "critic_over_actor_norm_ratio_max":max(ratio),
        "live_first_minibatch_clipped":sum(p["live_clip_coefficient"]<1 for p in subset),
        "live_clip_coefficient_mean":statistics.mean(p["live_clip_coefficient"] for p in subset)}
for group in probes[0]["groups"]:
    values=[p["groups"][group] for p in probes]
    gradient["groups"][group]={"cosine_mean":statistics.mean(p["cosine"] for p in values),
        "negative_cosines":sum(p["cosine"]<0 for p in values),
        "critic_over_actor_norm_ratio_mean":statistics.mean(p["norm_ratio_critic_over_actor"] for p in values)}
update_durations=[metrics[j]["elapsed_seconds"]-metrics[j-1]["elapsed_seconds"] for j in range(1,len(metrics))]
update_timing={"complete_update_intervals":len(update_durations),"mean_seconds":statistics.mean(update_durations),
    "max_seconds":max(update_durations),"first_elapsed_including_entry_eval_seconds":metrics[0]["elapsed_seconds"],
    "scope":"Intervals include rollout, optimization, guard and telemetry; exclude entry evaluation and finalization."}
manifest = r.read(out / "artifact-manifest.json")
for relative, digest in manifest.items(): assert r.sha(out/relative)==digest, relative

result = {"schema": "D2_gradient_parent_terminal_audit_v1", "status": "passed",
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
          "consumed_iteration_wall_seconds_at_checkpoint": state["current_iteration_wall_seconds"],
          "parent_abandoned_frames_retained_not_current_training": sum(item["gameplay_frames"] for item in parent_abandoned),
          "completed_training_episodes": sum(row["kind"] == "completed" for row in journal),
          "completed_training_frames": completed_frames, "final_abandoned_training_frames": final_abandoned_frames,
          "entry_evaluation_identical_to_predecessor": True,
          "full_cumulative_D2_inclusive_wall_seconds": r.PARENT_WALL_SECONDS + ob["inclusive_process_wall_seconds"],
          "paired_seed_changes": {"improved": sum(x > 0 for x in paired_deltas), "worsened": sum(x < 0 for x in paired_deltas), "tied": sum(x == 0 for x in paired_deltas), "mean_delta_frames": sum(paired_deltas)/64},
          "death_cause_survival": cause_survival, "gradient_alignment": gradient,"update_timing":update_timing, "critic_windows": windows, "same_batch_fit_mse_improved_updates": fit_improved,
          "critic_limitation": "In-sample self-bootstrapped GAE targets; no held-out accuracy or causal interference conclusion.",
          "artifacts": artifacts, "audit_elapsed_seconds": time.monotonic() - started}
r.save(OWN / "audit.json", result)
print(json.dumps({k: v for k, v in result.items() if k not in ("artifacts", "checks")}, indent=2))
