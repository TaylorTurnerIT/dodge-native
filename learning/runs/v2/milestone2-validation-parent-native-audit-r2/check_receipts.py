"""Independent read-only native/provenance audit. No project imports or execution."""
from collections import Counter
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import tarfile
import traceback

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
CAMPAIGN=ROOT/"learning/runs/v2/milestone2-validation-campaign-r2"
EXECUTION=ROOT/"learning/runs/v2/milestone2-validation-execution-r2"
CAPSULE=ROOT/"learning/.cache/v2-m2-campaign-review-r4"
FREEZE=ROOT/"learning/runs/v2/milestone2-campaign-freeze-r4"
IDENTITY_SHA="eb72ae7efec29f6def72940715ad6ff09e43d09140f0c348f095bdbbf2727448"
CAPSULE_SHA="4ccfad09f2dc3a5c6a9625a269598a3bea4dc823e4fef6128760965ae192f1dd"
POLICY="nearest_lethal_aabb_safe_powerup"
BASELINES={2:("learning/runs/v2/milestone0-campaign-r2/native-results/baselines/episodes.jsonl","40b5a8a1614a304bfd041dcd6eedfd7e68262f60fbca5cf6acfc1ece9a2694b3"),3:("learning/runs/v2/gate-baselines-r1/native-results/d3/episodes.jsonl","cd0222856a3e56d3eb2b7ae89228314af5d35feefb1e28784aadfab3ad4f9801")}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def utc(value):return datetime.fromisoformat(value.replace("Z","+00:00"))
def require(ok,message):
    if not ok: raise AssertionError(message)
def save(path,value):
    with path.open("x") as stream:json.dump(value,stream,indent=2,sort_keys=True,allow_nan=False);stream.write("\n")
def audit():
    report={"schema":"independent_successful_M2_r2_native_and_provenance_audit_v1","created_at_utc":datetime.now(timezone.utc).isoformat(),"checker_sha256":sha(Path(__file__)),"frozen_identity_sha256":IDENTITY_SHA,"scope":"Read-only standard-library hash/archive/source/record audit; no project imports, native or extension execution.","checks":[],"failures":[],"findings":[],"total_M2_acceptance":False,"limitations":["This audit covers native phase and provenance; parent must reconcile the separate Python evidence audit before complete M2 acceptance.","The pinned native test compares every raw frame except physical_screen, but logs serialize final episode state hashes rather than every intermediate state.","Sampled RSS is cooperative and does not establish an unsampled OS memory ceiling.","One-invocation assertions are verified against retained outer receipts; no process replay or live PID probe occurs.","Native use of B seeds is engine regression, not teacher qualification or training."]}
    identity=read(FREEZE/"frozen-identity.json")
    original_path=ROOT/"learning/runs/v2/milestone2-integration-r2/build-receipt.json"
    original_build=read(original_path)
    paths={p for base in (CAMPAIGN,EXECUTION,CAPSULE,FREEZE) for p in base.rglob("*") if p.is_file()}
    paths.update(ROOT/name for name,_ in BASELINES.values())
    paths.add(original_path);paths.add(Path(original_build["source_manifest"]))
    paths.update(ROOT/c["log"] for c in original_build["commands"])
    paths.update(Path(name) for name in identity["binary_and_receipt_sha256"])
    paths.add(Path(identity["runtime"]["extension_path"]))
    before={str(p):sha(p) for p in paths}
    stage="start"
    try:
        stage="complete_artifact_hash_coverage"
        artifacts=read(CAMPAIGN/"artifact-sha256.json")
        require(len(artifacts)==34,"Not 34 campaign artifacts")
        require(set(artifacts)=={str(p.relative_to(CAMPAIGN)) for p in CAMPAIGN.rglob("*") if p.is_file() and p!=CAMPAIGN/"artifact-sha256.json"},"Campaign artifact coverage differs")
        for name,value in artifacts.items():require(sha(CAMPAIGN/name)==value,"Campaign hash differs: "+name)
        owned=read(EXECUTION/"owned-output-sha256.json")["files"]
        require(set(owned)=={str(p.relative_to(ROOT)) for base in (CAMPAIGN,EXECUTION) for p in base.rglob("*") if p.is_file() and p!=EXECUTION/"owned-output-sha256.json"},"Owned-output coverage differs")
        for name,value in owned.items():
            path=ROOT/name
            require(sha(path)==value["sha256"] and path.stat().st_size==value["bytes"],"Owned-output pin differs: "+name)
        report["checks"].append({"check":stage,"passed":True,"campaign_artifacts":len(artifacts),"owned_output_pins":len(owned)})
        stage="capsule_archive_and_build_lineage"
        require(sha(FREEZE/"frozen-identity.json")==sha(CAMPAIGN/"identity.json")==IDENTITY_SHA,"Identity mismatch")
        require(sha(CAPSULE/"manifest.json")==CAPSULE_SHA,"Capsule manifest mismatch")
        capsule=read(CAPSULE/"manifest.json");require(len(capsule["files"])==178,"Capsule file count differs")
        require(set(capsule["files"])=={str(p.relative_to(CAPSULE)) for p in CAPSULE.rglob("*") if p.is_file() and p!=CAPSULE/"manifest.json"},"Capsule coverage differs")
        for name,value in capsule["files"].items():require(sha(CAPSULE/name)==value,"Capsule hash differs: "+name)
        pins=identity["source_sha256"];require(len(pins)==62,"Source pin count differs")
        for name,value in pins.items():require(sha(CAPSULE/name)==value,"Capsule source pin differs: "+name)
        receipt=read(Path(identity["build_receipt"]))
        require(sha(FREEZE/"source.tar.gz")==receipt["source_archive_sha256"],"Source archive hash differs")
        require(sha(ROOT/receipt["current_source_manifest"])==receipt["current_source_manifest_sha256"],"Source manifest hash differs")
        require(read(ROOT/receipt["current_source_manifest"])==pins,"Source manifest and identity differ")
        with tarfile.open(FREEZE/"source.tar.gz","r:gz") as archive:
            members=archive.getmembers()
            require(len(members)==62 and {m.name for m in members}==set(pins),"Archive coverage differs")
            for member in members:
                require(member.isfile(),"Archive non-file")
                require(hashlib.sha256(archive.extractfile(member).read()).hexdigest()==pins[member.name],"Archived source differs: "+member.name)
        for name,value in identity["binary_and_receipt_sha256"].items():require(sha(Path(name))==value,"Binary/receipt/interpreter pin differs: "+name)
        require(sha(Path(identity["runtime"]["extension_path"]))==identity["runtime"]["extension_sha256"],"Extension pin differs")
        require(sha(original_path)==receipt["original_complete_build_receipt_sha256"],"Original build receipt changed")
        require(sha(Path(original_build["source_manifest"]))==original_build["source_manifest_sha256"],"Prebuild source manifest differs")
        built_pins=read(Path(original_build["source_manifest"]))
        require(set(built_pins)==set(pins),"Original build inventory differs")
        changed=[name for name in pins if pins[name]!=built_pins[name]]
        require(changed==["learning/scripts/v2_validate_environment.py"],"Compiled source differs from original build")
        require(original_build["source_unchanged_through_checks"] and original_build["status"]=="passed","Original build not passed")
        require(original_build["native_test_binary"]==identity["native_test_binary"] and original_build["native_test_binary_sha256"]==sha(Path(identity["native_test_binary"])),"Original native binary lineage differs")
        require(original_build["installed_extension_sha256"]==original_build["archived_extension_sha256"]==identity["runtime"]["extension_sha256"],"Original extension lineage differs")
        for command in original_build["commands"]:
            require(command["exit_code"]==0 and sha(ROOT/command["log"])==command["log_sha256"],"Original build/check log differs")
        chain=receipt;chain_links=0
        while "previous_reconciled_build_receipt" in chain:
            previous=Path(chain["previous_reconciled_build_receipt"])
            require(sha(previous)==chain["previous_reconciled_build_receipt_sha256"],"Reconciled receipt chain differs")
            require(sha(Path(chain["previous_frozen_identity"]))==chain["previous_frozen_identity_sha256"],"Previous identity differs")
            chain=read(previous);chain_links+=1
        source=(CAPSULE/"crates/dodge-rl-env/src/qualification_replay_tests.rs").read_text()
        for fragment in ['expected.physical_screen = actual.physical_screen.clone();','&expected, actual,','per-raw-frame full/headless state mismatch','for _ in 0..4','let deadline = Duration::from_secs(900);','full_hash, expected.full_state_hash']:
            require(fragment in source,"Missing native parity source anchor: "+fragment)
        report["checks"].append({"check":stage,"passed":True,"capsule_files":178,"source_archive_members":62,"source_pins":62,"unchanged_original_build_inputs":61,"original_build_command_logs":len(original_build["commands"]),"reconciled_receipt_chain_links":chain_links,"binary_receipt_interpreter_pins":len(identity["binary_and_receipt_sha256"]),"extension_sha256":identity["runtime"]["extension_sha256"],"native_binary_sha256":original_build["native_test_binary_sha256"]})
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
            normalized = json.loads(json.dumps(value))
            require(all(retained["difficulties"][key][name] == expected for name, expected in normalized.items() if name not in {"death_event_sum", "maximum_terminal_frame_death_events"}), "Existing per-difficulty audit differs")
        report["native_evidence"] = {"status": "passed_retained_frozen_r2_native_evidence", "episodes": len(native_rows), "raw_frames_per_path": total["raw_frames_per_path"], "native_test_wall_seconds": total["wall_seconds"], "difficulties": summaries, "teacher_qualification_opening_consumed": False}
        report["checks"].append({"check": stage, "passed": True, "matched_native_rows": len(native_rows), "matched_pattern_count_records": len(native_patterns), "summary_difficulties": 2})

        stage="native_time_RSS_and_one_invocation_receipts"
        overall=read(CAMPAIGN/"campaign-result.json");outer=read(EXECUTION/"outer-result.json");execution_report=read(EXECUTION/"report.json");invocation=read(EXECUTION/"invocation.json");preflight=read(EXECUTION/"preflight.json");plan=read(CAMPAIGN/"registered-plan.json")
        require(overall["status"]=="passed" and outer["exit_code"]==0 and execution_report["status"]=="campaign_passed_pending_independent_parent_audit","Successful outcomes disagree")
        require(outer["campaign_invocations"]==execution_report["boundaries"]["campaign_invocations"]==1,"Invocation count differs")
        require(overall["automatic_retries"]==execution_report["boundaries"]["automatic_retries"]==0 and not overall["resource_limits_relaxed"],"Retry/limits differ")
        require(overall["identity_sha256"]==outer["identity_sha256"]==preflight["identity_sha256"]==IDENTITY_SHA,"Identity anchors differ")
        require(outer["runner_sha256"]==pins["learning/scripts/v2_validate_environment.py"]==preflight["runner_sha256"],"Executed runner source differs")
        require(outer["interpreter_sha256"]==identity["binary_and_receipt_sha256"][identity["runtime"]["python_executable"]],"Executed interpreter differs")
        require(outer["argv"]==invocation["argv"] and outer["cwd"]==str(ROOT),"Outer command differs")
        require(sha(CAMPAIGN/"registered-plan.json")==identity["plan_sha256"]==overall["registered_plan_sha256"]==preflight["campaign_plan_sha256"],"Campaign plan differs")
        require(utc(outer["start_utc"])+timedelta(seconds=2400)<=utc(plan["cutoff_utc"]),"Full budget/reserve would not fit cutoff")
        require(plan["campaign_wall_seconds"]==1800 and plan["receipt_reserve_seconds"]==600 and plan["observed_worker_peak_rss_limit_bytes"]==6*1024**3,"Budget/RSS plan differs")
        require(overall["elapsed_seconds"]<1800 and utc(overall["finished_at_utc"])<utc(plan["cutoff_utc"]),"Campaign deadline failed")
        require(abs((utc(overall["finished_at_utc"])-utc(overall["started_at_utc"])).total_seconds()-overall["elapsed_seconds"])<0.01,"Campaign wall/monotonic discrepancy")
        require(outer["elapsed_seconds"]>=overall["elapsed_seconds"] and outer["elapsed_seconds"]-overall["elapsed_seconds"]<1,"Outer/campaign duration discrepancy")
        phase=overall["phases"][0];require(phase["name"]=="native_parity" and phase["status"]=="passed" and phase["exit_code"]==0,"Native phase not passed")
        require(read(CAMPAIGN/"native_parity-receipt.json")==phase,"Native receipt differs")
        require(phase["command"]==[identity["native_test_binary"],identity["native_test_name"],"--ignored","--exact","--nocapture","--test-threads=1"],"Native test invocation differs")
        require(phase["elapsed_seconds"]<phase["wall_limit_seconds"]==900,"Native phase wall limit failed")
        require(sha(CAMPAIGN/"native_parity.stdout.log")==phase["stdout_sha256"],"Native log hash differs")
        samples=[json.loads(line) for line in (CAMPAIGN/"native_parity.rss.jsonl").read_text().splitlines() if line]
        require(len(samples)==phase["rss_samples"]==1045,"RSS sample count differs")
        require(all(row["pid"]==phase["owned_pid"] and 0<row["rss_bytes"]<=overall["rss_limit_bytes"] and 0<=row["wall_seconds"]<phase["elapsed_seconds"] for row in samples),"RSS sample ownership/time/ceiling failed")
        require(all(a["wall_seconds"]<b["wall_seconds"] and utc(a["at_utc"])<utc(b["at_utc"]) for a,b in zip(samples,samples[1:])),"RSS not chronological")
        require(max(row["rss_bytes"] for row in samples)==phase["observed_peak_worker_rss_bytes"]==6799360,"RSS peak differs")
        require(total["wall_seconds"]<phase["elapsed_seconds"],"Native internal test exceeds observed phase duration")
        require(execution_report["native"]["episodes"]==2000 and execution_report["native"]["raw_frames_per_path"]==total["raw_frames_per_path"],"Execution report native summary differs")
        for difficulty,value in summaries.items():
            require(all(execution_report["native"]["difficulties"][difficulty][key]==value[key] for key in execution_report["native"]["difficulties"][difficulty]),"Execution report native difficulty differs")
        for key in ["source_edits_performed","state_or_scheduler_writes_performed","resource_limits_relaxed","root_lease_cleared","M3_implementation_or_training_performed"]:require(execution_report["boundaries"][key] is False,"Unauthorized operation reported")
        report["campaign_evidence"]={"overall_status":"passed_pending_parent_reconciliation","elapsed_seconds":overall["elapsed_seconds"],"outer_elapsed_seconds":outer["elapsed_seconds"],"native_elapsed_seconds":phase["elapsed_seconds"],"native_RSS_samples":len(samples),"native_sampled_peak_RSS_bytes":phase["observed_peak_worker_rss_bytes"],"campaign_invocations":1,"automatic_retries":0,"budget_seconds":1800,"receipt_reserve_seconds":600,"current_live_process_existence_checked":False}
        report["checks"].append({"check":stage,"passed":True})
    except Exception as error:
        report["failures"].append({"check":stage,"error":repr(error),"traceback":traceback.format_exc()})
    changed=[name for name,value in before.items() if sha(Path(name))!=value]
    report["checks"].append({"check":"input_preservation","passed":not changed,"files":len(before),"changed":changed})
    if changed:report["failures"].append({"check":"input_preservation","changed":changed})
    save(HERE/"input-pins.json",before)
    report["status"]="passed_native_phase_and_build_provenance_audit" if not report["failures"] else "audit_failed"
    save(HERE/"audit.json",report)
    print(json.dumps({"status":report["status"],"audit_sha256":sha(HERE/"audit.json"),"failures":report["failures"],"preserved_inputs":len(before)}))
    return not report["failures"]
if __name__=="__main__":raise SystemExit(0 if audit() else 1)
