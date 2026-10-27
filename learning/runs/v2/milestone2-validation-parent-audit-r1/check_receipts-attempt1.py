"""Independent, standard-library-only audit of retained failed M2 campaign r1.

This script never imports audited project code or executes the game/binding.
"""
from collections import Counter
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import tarfile
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CAMPAIGN = ROOT / "learning/runs/v2/milestone2-validation-campaign-r1"
EXECUTION = ROOT / "learning/runs/v2/milestone2-validation-execution-r1"
CAPSULE = ROOT / "learning/.cache/v2-m2-campaign-review-r3"
FREEZE = ROOT / "learning/runs/v2/milestone2-campaign-freeze-r3"
IDENTITY_SHA = "9139a19d0b9862fb0cdc2befd3d7fd20601f3efea5934885e83a493f4f170c19"
POLICY = "nearest_lethal_aabb_safe_powerup"
BASELINES = {
    2: ("learning/runs/v2/milestone0-campaign-r2/native-results/baselines/episodes.jsonl", "40b5a8a1614a304bfd041dcd6eedfd7e68262f60fbca5cf6acfc1ece9a2694b3"),
    3: ("learning/runs/v2/gate-baselines-r1/native-results/d3/episodes.jsonl", "cd0222856a3e56d3eb2b7ae89228314af5d35feefb1e28784aadfab3ad4f9801"),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def utc(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def save_new(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def audit():
    report = {
        "schema": "independent_failed_m2_campaign_receipt_audit_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "checker_sha256": sha(Path(__file__)),
        "frozen_identity_sha256": IDENTITY_SHA,
        "scope": "Read-only hash/archive/source and independently parsed retained execution evidence; no project import or execution.",
        "checks": [], "failures": [], "findings": [],
        "total_M2_qualification": False,
        "limitations": [
            "Passing native retained evidence belongs to frozen r1 identity; it is not transferred qualification for a changed supervisor or future campaign.",
            "Retained passing test output plus pinned native test source support raw-frame parity; the log does not serialize all ten million intermediate states.",
            "Sampled RSS is a cooperative resource observation, not an unsampled hard OS memory ceiling.",
            "Recorded wait/exit/reaping receipts are checked; current live process existence is left to the parent.",
            "No trajectory comparison, memory stress, throughput measurement, teacher learning or teacher qualification passed in this failed campaign.",
        ],
    }
    original_files = {p for base in (CAMPAIGN, EXECUTION, CAPSULE, FREEZE) for p in base.rglob("*") if p.is_file()}
    original_files.update(ROOT / item[0] for item in BASELINES.values())
    before = {str(p): sha(p) for p in original_files}
    stage = "start"
    try:
        stage = "exact_campaign_artifact_coverage"
        artifacts = read(CAMPAIGN / "artifact-sha256.json")
        require(set(artifacts) == {str(p.relative_to(CAMPAIGN)) for p in CAMPAIGN.rglob("*") if p.is_file() and p != CAMPAIGN / "artifact-sha256.json"}, "Campaign artifact manifest coverage differs")
        for name, expected in artifacts.items():
            require(sha(CAMPAIGN / name) == expected, "Campaign artifact hash differs: " + name)
        execution_output = read(EXECUTION / "campaign-output-sha256.json")
        for name, expected in execution_output.items():
            require(sha(ROOT / name) == expected, "Execution output hash differs: " + name)
        require(set(execution_output) == {str(p.relative_to(ROOT)) for p in CAMPAIGN.rglob("*") if p.is_file()}, "Outer campaign-output manifest coverage differs")
        execution_files = {}
        for line in (EXECUTION / "execution-artifact-sha256.txt").read_text().splitlines():
            expected, name = line.split(None, 1)
            require(name not in execution_files, "Duplicate execution artifact")
            execution_files[name] = expected
            require(sha(ROOT / name) == expected, "Execution artifact hash differs: " + name)
        require(set(execution_files) == {str(p.relative_to(ROOT)) for p in EXECUTION.iterdir() if p.is_file() and p.name != "execution-artifact-sha256.txt"}, "Execution manifest coverage differs")
        json_count = 0
        for base in (CAMPAIGN, EXECUTION):
            for p in base.glob("*.json"):
                read(p)
                json_count += 1
        report["checks"].append({"check": stage, "passed": True, "campaign_artifacts": len(artifacts), "outer_campaign_files": len(execution_output), "execution_artifacts": len(execution_files), "JSON_files_parsed": json_count})

        stage = "frozen_archive_capsule_and_binary_pins"
        require(sha(FREEZE / "frozen-identity.json") == IDENTITY_SHA, "Frozen identity hash changed")
        require(sha(CAMPAIGN / "identity.json") == IDENTITY_SHA, "Executed identity differs")
        identity = read(FREEZE / "frozen-identity.json")
        require(sha(CAPSULE / "manifest.json") == "c8ad9cffd171c964e89c0f599dd4c3fe67e88393f89571c1e39c768141c3d8fa", "Capsule manifest changed")
        capsule = read(CAPSULE / "manifest.json")
        for name, expected in capsule["files"].items():
            require(sha(CAPSULE / name) == expected, "Capsule file hash differs: " + name)
        for name, expected in identity["source_sha256"].items():
            require(sha(CAPSULE / name) == expected, "Frozen capsule source pin differs: " + name)
        receipt = read(Path(identity["build_receipt"]))
        require(sha(FREEZE / "source.tar.gz") == receipt["source_archive_sha256"], "Archive hash changed")
        require(sha(ROOT / receipt["current_source_manifest"]) == receipt["current_source_manifest_sha256"], "Source manifest changed")
        require(read(ROOT / receipt["current_source_manifest"]) == identity["source_sha256"], "Source manifest and identity disagree")
        with tarfile.open(FREEZE / "source.tar.gz", "r:gz") as archive:
            members = archive.getmembers()
            require(len(members) == len(identity["source_sha256"]), "Archive member count differs")
            require({member.name for member in members} == set(identity["source_sha256"]), "Archive coverage differs")
            for member in members:
                require(member.isfile(), "Archive has non-file member")
                require(hashlib.sha256(archive.extractfile(member).read()).hexdigest() == identity["source_sha256"][member.name], "Archived source pin differs: " + member.name)
        for name, expected in identity["binary_and_receipt_sha256"].items():
            require(sha(Path(name)) == expected, "Binary/build receipt hash differs: " + name)
        require(sha(Path(identity["runtime"]["extension_path"])) == identity["runtime"]["extension_sha256"], "Extension hash differs")
        require(sha(Path(receipt["original_complete_build_receipt"])) == receipt["original_complete_build_receipt_sha256"], "Original complete build receipt changed")
        report["checks"].append({"check": stage, "passed": True, "capsule_files": len(capsule["files"]), "source_archive_members": len(members), "source_pins": len(identity["source_sha256"]), "binary_receipt_pins": len(identity["binary_and_receipt_sha256"]), "installed_extension_sha256": identity["runtime"]["extension_sha256"], "live_supervisor_compared": False})

        stage = "independent_original_baseline_native_record_comparison"
        original = {}
        original_patterns = {}
        for difficulty, (name, expected_hash) in BASELINES.items():
            path = ROOT / name
            require(sha(path) == expected_hash, "Original baseline changed")
            with path.open() as stream:
                all_rows = [json.loads(line) for line in stream if line.strip()]
            rows = sorted((row for row in all_rows if row["policy"] == POLICY), key=lambda row: row["episode_index"])
            require(len(rows) == 1000, "Not exactly 1000 heuristic-only original rows")
            original[difficulty] = rows
            pattern = Counter()
            for index, row in enumerate(rows):
                config = row["native_config"]
                require(row["episode_index"] == index and row["seed"] == 0xB0000000 + index, "Original seed/order mismatch")
                require(config == {"difficulty": difficulty, "patterns_enabled": True, "powerups_enabled": True, "theme_background_shadow": [12, 1], "initial_highscores_raw_fixed": [0] * 12}, "Original native config mismatch")
                require(row["episode_status"] == "complete" and row["failure"] == "" and not row["run_deadline_truncation"] and row["startup_native_frames_excluded"] == 13, "Incomplete original row")
                require(row["gameplay_native_frames"] <= 18000 and row["score_delta_sum_raw_fixed"] == row["scores"]["final_score_raw_fixed"], "Original cap/score accounting mismatch")
                for item in row["counts"]["pattern_frames"]:
                    pattern[item["id"]] += item["frames"]
            require(set(pattern) == set(range(1, 40)), "Original coverage not all39 patterns")
            original_patterns[difficulty] = dict(pattern)
        native_rows = {}
        native_patterns = {}
        native_summaries = {}
        native_totals = []
        log = (CAMPAIGN / "native_parity.stdout.log").read_text()
        for line in log.splitlines():
            for prefix, category in (("V2_FULL_PARITY_EPISODE ", "episode"), ("V2_FULL_PARITY_PATTERN ", "pattern"), ("V2_FULL_PARITY_DIFFICULTY ", "difficulty"), ("V2_FULL_PARITY_TOTAL ", "total")):
                if prefix not in line:
                    continue
                row = json.loads(line.split(prefix, 1)[1])
                if category == "episode":
                    key = (row["difficulty"], row["episode_index"])
                    require(key not in native_rows, "Duplicate native episode")
                    native_rows[key] = row
                elif category == "pattern":
                    key = (row["difficulty"], row["id"])
                    require(key not in native_patterns, "Duplicate native pattern")
                    native_patterns[key] = row["frames"]
                elif category == "difficulty":
                    require(row["difficulty"] not in native_summaries, "Duplicate native difficulty summary")
                    native_summaries[row["difficulty"]] = row
                else:
                    native_totals.append(row)
        require(len(native_rows) == 2000 and set(native_summaries) == {2, 3} and len(native_totals) == 1, "Native log incomplete")
        require("test result: ok. 1 passed; 0 failed;" in log, "Native test did not pass")
        summaries = {}
        for difficulty, rows in original.items():
            for index, reference in enumerate(rows):
                expected = {"difficulty": difficulty, "episode_index": index, "seed": reference["seed"], "score_raw_fixed": reference["scores"]["final_score_raw_fixed"], "raw_frames": reference["gameplay_native_frames"], "alive_frames": reference["raw_survival_frames"], "terminated": reference["death"], "truncated": reference["cap_truncation"], "death_events": reference["frame_event_counts_enemy_spawn_collision_death_pattern_active_terminal"][2], "full_state_hash": reference["final_state_hash"]}
                expected["objective_return"] = expected["score_raw_fixed"] / 65536 + expected["alive_frames"] / 100 - 5 * expected["terminated"]
                require(native_rows[(difficulty, index)] == expected, f"Native D{difficulty} row{index} differs from original")
            observed_pattern = {key[1]: value for key, value in native_patterns.items() if key[0] == difficulty}
            require(observed_pattern == original_patterns[difficulty], "Native pattern counts differ")
            summary = {"difficulty": difficulty, "episodes": 1000, "raw_frames_per_path": sum(row["gameplay_native_frames"] for row in rows), "alive_frames": sum(row["raw_survival_frames"] for row in rows), "score_sum_raw_fixed": sum(row["scores"]["final_score_raw_fixed"] for row in rows), "caps": sum(row["cap_truncation"] for row in rows), "pattern_ids": len(original_patterns[difficulty])}
            require(native_summaries[difficulty] == summary, "Native aggregate differs from original rows")
            summaries[f"D{difficulty}"] = dict(summary, score_mean=summary["score_sum_raw_fixed"] / 65536 / 1000, alive_frames_mean=summary["alive_frames"] / 1000, pattern_frames=original_patterns[difficulty], death_event_sum=sum(row["frame_event_counts_enemy_spawn_collision_death_pattern_active_terminal"][2] for row in rows), maximum_terminal_frame_death_events=max(row["frame_event_counts_enemy_spawn_collision_death_pattern_active_terminal"][2] for row in rows))
        total = native_totals[0]
        require(total["episodes"] == 2000 and total["raw_frames_per_path"] == sum(row["raw_frames_per_path"] for row in summaries.values()), "Native total mismatch")
        retained = read(CAMPAIGN / "native-parity-audit.json")
        require(retained["raw_frames_per_path"] == total["raw_frames_per_path"] and retained["native_total"] == total and retained["episodes"] == 2000 and retained["status"] == "passed", "Existing native audit summary differs")
        for key, value in summaries.items():
            require(all(retained["difficulties"][key][name] == expected for name, expected in value.items() if name not in {"death_event_sum", "maximum_terminal_frame_death_events"}), "Existing per-difficulty audit differs")
        report["native_evidence"] = {"status": "passed_retained_frozen_r1_evidence", "episodes": len(native_rows), "raw_frames_per_path": total["raw_frames_per_path"], "native_test_wall_seconds": total["wall_seconds"], "difficulties": summaries, "teacher_qualification_opening_consumed": False}
        report["checks"].append({"check": stage, "passed": True, "matched_native_rows": len(native_rows), "matched_pattern_count_records": len(native_patterns), "summary_difficulties": 2})

        stage = "phase_time_RSS_failure_and_process_receipts"
        overall = read(CAMPAIGN / "campaign-result.json")
        execution = read(EXECUTION / "result.json")
        launch = read(EXECUTION / "launch.json")
        end = read(EXECUTION / "termination.json")
        plan = read(CAMPAIGN / "registered-plan.json")
        require(overall["status"] == execution["status"] == "failed" and execution["exit_code"] == end["exit_code"] == 1, "Failed outcome not preserved")
        require(execution["campaign_invocations"] == 1 and execution["automatic_retries"] == overall["automatic_retries"] == 0 and not overall["resource_limits_relaxed"], "Retry/limit ledger differs")
        require(launch["identity_sha256"] == overall["identity_sha256"] == execution["identity_sha256"] == IDENTITY_SHA, "Execution identity anchors differ")
        require(launch["runner_sha256"] == identity["source_sha256"]["learning/scripts/v2_validate_environment.py"] == execution["runner_sha256"], "Executed source identity differs from frozen archive")
        require(launch["interpreter_sha256"] == identity["binary_and_receipt_sha256"][identity["runtime"]["python_executable"]] == execution["interpreter_sha256"], "Interpreter pin differs")
        require(sha(CAMPAIGN / "registered-plan.json") == identity["plan_sha256"] == launch["plan_sha256"] == overall["registered_plan_sha256"], "Plan pins differ")
        require(utc(launch["start_utc"]) + timedelta(seconds=2400) <= utc(plan["cutoff_utc"]), "No full campaign plus reserve before cutoff")
        require(overall["elapsed_seconds"] < 1800 and plan["campaign_wall_seconds"] == 1800 and plan["receipt_reserve_seconds"] == 600 and plan["observed_worker_peak_rss_limit_bytes"] == 6 * 1024**3, "Resource limits differ")
        require(abs((utc(overall["finished_at_utc"]) - utc(overall["started_at_utc"])).total_seconds() - overall["elapsed_seconds"]) < 0.01, "Campaign elapsed/wall receipts disagree")
        require([row["name"] for row in overall["phases"]] == ["native_parity", "trajectory"], "Unexpected follow-on phase ran after failure")
        phase_reports = {}
        for phase in overall["phases"]:
            name = phase["name"]
            require(read(CAMPAIGN / (name + "-receipt.json")) == phase, "Phase and overall receipts differ")
            require(sha(CAMPAIGN / (name + ".stdout.log")) == phase["stdout_sha256"], "Phase stdout hash differs")
            samples = [json.loads(line) for line in (CAMPAIGN / (name + ".rss.jsonl")).read_text().splitlines() if line]
            require(len(samples) == phase["rss_samples"] and samples, "Missing or miscounted RSS samples")
            require(all(row["pid"] == phase["owned_pid"] and 0 < row["rss_bytes"] <= overall["rss_limit_bytes"] and 0 <= row["wall_seconds"] < phase["elapsed_seconds"] for row in samples), "RSS sample ownership/ceiling/time differs")
            require(all(left["wall_seconds"] < right["wall_seconds"] and utc(left["at_utc"]) < utc(right["at_utc"]) for left, right in zip(samples, samples[1:])), "RSS samples not chronological")
            require(max(row["rss_bytes"] for row in samples) == phase["observed_peak_worker_rss_bytes"], "RSS peak differs")
            require(phase["elapsed_seconds"] < phase["wall_limit_seconds"], "Phase exceeded declared wall guard")
            phase_reports[name] = {"status": phase["status"], "exit_code": phase["exit_code"], "elapsed_seconds": phase["elapsed_seconds"], "RSS_samples": len(samples), "sampled_peak_RSS_bytes": phase["observed_peak_worker_rss_bytes"]}
        failure = read(CAMPAIGN / "trajectory-failure.json")
        require(failure["error"] == 'TypeError("argument \'excluded_seed_ranges\': \'list\' object cannot be cast as \'tuple\'")', "Unexpected trajectory failure")
        require('left = Env(**base_config' in failure["traceback"] and 'line 339' in failure["traceback"] and failure["identity_sha256"] == IDENTITY_SHA, "Failure is not the first constructor")
        frozen_source = (CAPSULE / "learning/scripts/v2_validate_environment.py").read_text()
        binding_source = (CAPSULE / "crates/dodge-rl-env/src/python.rs").read_text()
        require('"excluded_seed_ranges": plan["effective_reserved_ranges"]' in frozen_source and 'excluded_seed_ranges: Option<Vec<(u32, u32)>>' in binding_source, "Static source does not support list/tuple diagnosis")
        require(all(type(pair) is list for pair in plan["effective_reserved_ranges"]), "Plan range pair schema changed")
        require(execution["phases"]["trajectory"]["completed_trajectory_comparisons"] == 0 and execution["phases"]["memory"]["status"] == execution["phases"]["throughput"]["status"] == "not_run", "Partial/absent phases misreported")
        require(not any((CAMPAIGN / name).exists() for name in ("trajectory-result.json", "memory-command.json", "throughput-command.json", "memory-result.json", "throughput-result.json")), "Unexpected later phase evidence exists")
        stop = overall["owned_process_stop"]
        require(stop["reaped"] and stop["exit_code"] == 1 and not stop["errors"] and not stop["kill_sent"] and not stop["term_sent"], "Owned worker cleanup receipt differs")
        require(execution["ownership"]["runner_pid"] == end["runner_pid"] and execution["ownership"]["runner_stop_receipt"] == stop and execution["ownership"]["worker_pids"] == [p["owned_pid"] for p in overall["phases"]], "Recorded ownership differs")
        require(not execution["lease_cleared"] and not execution["ledger_writes"] and not execution["scheduler_writes"] and not execution["source_or_frozen_artifact_edits"], "Execution child reports unauthorized writes")
        report["campaign_evidence"] = {"status": "failed_stop_on_first_failure", "elapsed_seconds": overall["elapsed_seconds"], "phase_receipts": phase_reports, "failure": failure["error"], "failure_point": "first trajectory environment constructor; before stepping", "trajectory_comparisons_completed": 0, "memory_measured_step_calls": 0, "throughput_completed_configurations": 0, "trajectory_ru_maxrss_bytes": failure["observed_peak_self_rss_bytes"], "recorded_owned_worker_reaped": True, "current_live_process_existence_checked": False}
        report["checks"].append({"check": stage, "passed": True})
    except Exception as error:
        report["failures"].append({"check": stage, "error": repr(error), "traceback": traceback.format_exc()})
    changed = [name for name, expected in before.items() if sha(Path(name)) != expected]
    report["checks"].append({"check": "input_preservation", "passed": not changed, "files": len(before), "changed": changed})
    if changed:
        report["failures"].append({"check": "input_preservation", "changed": changed})
    report["status"] = "passed_audit_of_failed_campaign;M2_remains_unqualified" if not report["failures"] else "audit_failed"
    save_new(HERE / "audit.json", report)
    save_new(HERE / "input-pins.json", before)
    print(json.dumps({"status": report["status"], "checks": len(report["checks"]), "failures": report["failures"], "audit_sha256": sha(HERE / "audit.json")}))
    return int(bool(report["failures"]))


if __name__ == "__main__":
    raise SystemExit(audit())
