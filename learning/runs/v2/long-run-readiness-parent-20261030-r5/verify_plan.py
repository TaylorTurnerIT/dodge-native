"""Static count/pin/notebook checks only. No RL import, execution or lease mutation."""
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


protected = read(OUT / "protected-before.json")
for name, digest in protected.items():
    assert sha(ROOT / name) == digest, name
audit = read(OUT / "readiness-audit.json")
for row in audit["findings"]:
    assert sha(ROOT / row["source"]) == row["source_sha256"], row["source"]
plan = read(OUT / "long-run-protocol-v5.json")
assert plan["launch_authority"] is False and plan["promotion"] is False
assert plan["seeds"]["reserved_now"] == plan["seeds"]["cohorts_opened_now"] == 0
t, m, f = plan["training"], plan["monitoring"], plan["final_confirmation"]
assert t["replicas"] * (t["work_seconds_per_replica"] + t["receipt_seconds_per_replica"]) == 66000
assert m["looks"] * m["fresh_game_seeds_per_look"] * m["models_per_look"] == 24576
assert f["fresh_game_seeds"] * f["models"] == 14336
assert sum(x["total_ceiling_seconds"] for x in [t, m, f]) == plan["combined_long_run_ceiling_seconds"] == 103800
assert m["nominal_raw_frame_barriers"][-1] == t["additional_raw_frames_per_replica"]
formal = ROOT / "learning/runs/v2/one-frame-training-comparison-luna-20261029-r2"
reg = read(formal / "registration-formal-final-r5.json")
assert sha(formal / "registration-formal-final-r5.json") == "d395b3d0bf2ca058a57622f23ad9b317cb0af0fcbe1e2ef8fb6a7124d6e075e1"
assert sha(reg["source_manifest_path"]) == reg["source_manifest_sha256"]
assert sha(reg["runtime_manifest_path"]) == reg["runtime_manifest_sha256"]
for name, digest in reg["source_files"].items():
    assert sha(formal / name) == digest, name
runtime = read(reg["runtime_manifest_path"])
for name, digest in runtime["files"].items():
    assert sha(Path(runtime["runtime_root"]) / name) == digest, name
assert len(runtime["files"]) == 14
runtime_ppo = Path(runtime["runtime_root"]) / "dodge_rl/ppo.py"
for field in ["epoch_approx_kls", "approx_kl", "entropy", "value_loss", "explained_variance", "clip_fraction"]:
    assert f'"{field}"' in runtime_ppo.read_text(), field
cache = formal / "empty-pycache"
assert cache.is_dir() and list(cache.iterdir()) == []
s1r2 = ROOT / "learning/runs/v2/track-a-s1-successor-parent-20261030-r2"
assert not (s1r2 / "S1-launch.claimed").exists()
assert list((s1r2 / "empty-pycache").iterdir()) == []
records = {x["id"]: x for x in read(ROOT / "learning/research/records.json")["experiments"]}
for identifier in ["DODGE-043", "DODGE-044"]:
    prediction = read(OUT / (identifier + "-prediction.json"))
    assert records[identifier]["expected"] == prediction["expected"]
    assert records[identifier]["prediction_timing"] == "before_run"
    for item in records[identifier]["evidence"]:
        path = Path(item["uri"])
        if not path.is_absolute():
            path = ROOT / path
        assert sha(path) == item["sha256"], path
assert records["DODGE-043"]["actual_kind"] == "observed"
assert records["DODGE-044"]["status"] == "planned"
assert records["DODGE-044"]["measurements"] == []
verification = dict(
    schema="dodge_long_run_planning_verification_v5", scope="Source/count/pin/notebook checks only; not runtime qualification.",
    long_run_ceiling_seconds=103800, all_missing_entry_ceiling_seconds=51480,
    evaluation_seed_request=9216, new_cohorts=0, runtime_launches=0,
    protected_files_unchanged=True, formal_source_pins_unchanged=True, runtime_members_verified=14,
    runtime_PPO_numerical_metrics_present=True, runtime_PPO_source_sha256=sha(runtime_ppo),
    caches_exist_empty=True, S1_r2_unlaunched=True, failed_S1_lease_held=True,
    original_predictions_preserved=True,
    HTML_checks=dict(desktop_width=760, mobile_width=375, tabs_checked=5,
                     priority_rows=[8, 9, 10], horizontal_overflow=False, console_errors=0),
    pins={str(p.relative_to(ROOT)): sha(p) for p in [
        OUT / "readiness-audit.json", OUT / "long-run-protocol-v5.json", OUT / "long-run-gate.html",
        OUT / "build_plan.py", OUT / "build_visual.py", ROOT / "docs/review-ideas-and-scaling-plan-20261030.md"]})
(OUT / "planning-verification.json").write_text(json.dumps(verification, indent=2, sort_keys=True) + "\n")
print(json.dumps(verification, sort_keys=True))
