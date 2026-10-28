#!/usr/bin/env python3
"""Read-only, stdlib seed history extension and control-only candidate pool."""
import csv
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

V2 = Path("learning/runs/v2")
OUT = V2 / "rl-followup-seed-reservation-parent-20261027-r1"
CLOSURE = V2 / "progressive1000-seed-history-closure-sol-20261026-r2"
COHORT_REVIEW = V2 / "progressive1000-cohort-provenance-decision-review-sol-20261026-r1"
COHORT_ACCEPT = V2 / "progressive1000-cohort-parent-acceptance-20261026-r1"
FORMAL = V2 / "progressive1000-opening-maintenance-integrated-parent-20261027-r1"
EVAL = V2 / "progressive1000-full-run-evaluator-parent-20261027-r2"
REGISTRY = Path("learning/runs/v2-orchestration/state.json")

RESERVED = {
    "B": (0xB0000000, 0xB00003E7),
    "D128": (0xD0000000, 0xD000007F),
    "D100": (0xD1000000, 0xD10003FF),
    "D200": (0xD2000000, 0xD20007FF),
    "D300": (0xD3000000, 0xD30003FF),
    "E": (0xE0000000, 0xE00003E7),
}
NEW = {"D400_dev": (0xD4000000, 0xD40003FF), "D500_confirm": (0xD5000000, 0xD50007FF)}
SOURCES = {}


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def read(path, kind):
    path = str(path)
    SOURCES[path] = {"sha256": sha(path), "bytes": os.path.getsize(path), "role": kind}
    with open(path) as f:
        return json.load(f)


def inside(value, span):
    return span[0] <= value <= span[1]


def source_descriptor(path, digest=None):
    if digest is not None:
        return {"path": str(path), "sha256": digest}
    p = str(path)
    if p not in SOURCES:
        SOURCES[p] = {"sha256": sha(p), "bytes": os.path.getsize(p), "role": "input"}
    return {"path": p, "sha256": SOURCES[p]["sha256"]}


def add_run_seed_history(run_id, category, source_paths, seeds, completions=None, note=""):
    values = sorted(set(seeds))
    return {"run_id": run_id, "category": category, "sources": [source_descriptor(p) for p in source_paths],
            "unique_constructed_actual_seed_count": len(values), "actual_seeds_sorted": values,
            "completed_episode_records": completions, "note": note}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    merged = read(CLOSURE / "merged-conservative-seeds.json", "named-scope historical conservative set")
    closure_receipt = read(CLOSURE / "receipt.json", "history closure limits/status")
    closure_map = read(CLOSURE / "coverage-closure-map.json", "history claim scope")
    cohort = read(V2 / "progressive1000-seed-cohort-prepare-sol-20261026-r1" / "cohort.json", "original D300 proposal")
    acceptance = read(COHORT_ACCEPT / "acceptance.json", "parent accepted cohort decision")
    review_receipt = read(COHORT_REVIEW / "receipt.json", "parent-relevant provenance review limits")
    state = read(REGISTRY, "post-closure registry ledger")
    curriculum_state = state["progressive1000_curriculum_work"]
    assert curriculum_state["actual_training_launches"] == 9
    assert curriculum_state["formal_training_endpoints_complete"] is True
    assert curriculum_state["full_comparison_complete"] is True

    post_runs = []
    post_seed_values = defaultdict(set)

    # Failed first attempt and later bounded retry: event logs pin each initial/reset assignment.
    failed_runs = [
        ("failed_attempt_1_41_updates", V2 / "progressive1000-matched-run-parent-assembly-20261026-r1" / "progressive1000-confirmed324-20261026-r1-replica-1-control_constant_3e-5", 41),
        ("failed_attempt_2_44_updates", V2 / "progressive1000-control-retry-proposal-parent-20261027-r1", 44),
    ]
    for label, run_dir, updates in failed_runs:
        event_path = run_dir / "worker-output" / "training-events.jsonl"
        registration = run_dir / ("registration-final.json" if label.endswith("1_41_updates") else "registration-final-candidate.json")
        audit = run_dir / "parent-terminal-audit.json"
        read(registration, "failed attempt registration and vector/exclusion pin")
        read(audit, "failed attempt terminal audit")
        values = set()
        completion_count = 0
        for line in open(event_path):
            event = json.loads(line)
            if event.get("kind") in ("initial", "reset_assignment"):
                for a in event.get("assignments", [event] if event.get("seed") else []):
                    seed = a.get("seed", {}).get("actual_seed")
                    if seed is not None: values.add(seed)
            if event.get("kind") == "completion":
                seed = event.get("native_info", {}).get("seed", {}).get("actual_seed")
                if seed is not None: values.add(seed)
                completion_count += 1
        post_seed_values[label].update(values)
        post_runs.append(add_run_seed_history(label, "failed_training_attempt", [str(event_path), str(registration), str(audit)], values,
                                              completion_count, f"{updates} completed updates; episode assignments from event log"))

    # The 24-update timing probe started a native environment and reset episodes.
    probe_dir = V2 / "progressive1000-throughput-probe24-parent-20261027-r1"
    probe_reg = read(probe_dir / "registration-final.json", "24-update probe registration")
    probe_result_path = probe_dir / "worker-output" / "worker-result.json"
    probe = read(probe_result_path, "24-update probe worker result")
    probe_audit = read(probe_dir / "parent-terminal-audit.json", "24-update probe terminal audit")
    probe_env = probe["final_snapshot"]["environment"]
    probe_values = {a["seed"]["actual_seed"] for a in probe_env["assignments"]}
    probe_values.update(c["native_info"]["seed"]["actual_seed"] for c in probe_env["completions"])
    post_seed_values["timing_probe24"].update(probe_values)
    post_runs.append(add_run_seed_history("timing_probe24", "bounded_training_probe",
        [str(probe_result_path), str(probe_dir / "registration-final.json"), str(probe_dir / "parent-terminal-audit.json")], probe_values,
        len(probe_env["completions"]), "Only completed 24-update probe; duplicate seeds also appear in matched replica-1 control stream"))

    # Six accepted terminal training endpoints; preserve all assigned seeds, while the pool uses completed control episodes only.
    manifest_path = FORMAL / "six-endpoint-completion.json"
    manifest = read(manifest_path, "six formal endpoint index")
    assert len(manifest["endpoints"]) == 6 and manifest["formal_training_runs"] == 6
    pool_observations = defaultdict(list)
    control_source_rows = []
    for endpoint in manifest["endpoints"]:
        run_id = endpoint["run_id"]
        result_path = Path(os.path.dirname(endpoint["audit"])) / "worker-output" / "worker-result.json"
        result = read(result_path, "formal endpoint assignments/completions")
        reg_path = Path(os.path.dirname(endpoint["audit"])) / "registration-final.json"
        reg = read(reg_path, "formal endpoint seed vector and exclusion union")
        assert sha(reg_path) == endpoint["registration_sha256"]
        env = result["final_snapshot"]["environment"]
        assigned = {a["seed"]["actual_seed"] for a in env["assignments"]}
        completed = {c["native_info"]["seed"]["actual_seed"] for c in env["completions"]}
        values = assigned | completed
        label = "formal_" + run_id
        post_seed_values[label].update(values)
        post_runs.append(add_run_seed_history(label, "formal_training_endpoint", [str(result_path), str(reg_path)], values,
                                              len(env["completions"]), "All initial/reset assignments and accepted terminal completions included"))
        if "control" in run_id:
            for idx, completion in enumerate(env["completions"]):
                info = completion["native_info"]
                seed = info["seed"]["actual_seed"]
                obs = {"run_id": run_id, "completed_episode_index": idx,
                       "alive_frames": info["alive_frames"], "source_path": str(result_path),
                       "source_sha256": SOURCES[str(result_path)]["sha256"],
                       "registration_path": str(reg_path), "registration_sha256": SOURCES[str(reg_path)]["sha256"],
                       "seed_vector_sha256": reg.get("seed_vector_sha256"),
                       "observation_kind": "accepted_worker_result_final_snapshot.environment.completions.native_info"}
                pool_observations[seed].append(obs)
                control_source_rows.append({"run_id": run_id, "completion_index": idx, "actual_seed": seed,
                                            "alive_frames": info["alive_frames"], "result_path": str(result_path),
                                            "registration_path": str(reg_path)})
    assert len(control_source_rows) == 5605

    # D300 is now consumed as the fixed full-run evaluation; these constructor events repeat for each of seven policies.
    eval_events = EVAL / "worker-output" / "evaluation-events.jsonl"
    eval_seeds = set()
    eval_events_count = 0
    for line in open(eval_events):
        event = json.loads(line)
        if event.get("kind") == "evaluation_constructor":
            eval_seeds.add(event["seed"]); eval_events_count += 1
    eval_result = read(EVAL / "worker-output" / "worker-result.json", "terminal full-run eval run summary")
    eval_audit = read(EVAL / "parent-terminal-audit.json", "terminal full-run eval audit")
    eval_reg = read(EVAL / "registration-final.json", "D300 evaluation registration")
    eval_summary = read(EVAL / "result-summary.json", "existing accepted endpoint evaluation summary")
    post_seed_values["full_evaluation_D300"].update(eval_seeds)
    post_runs.append(add_run_seed_history("full_evaluation_D300", "seven-policy evaluation constructors",
        [str(eval_events), str(EVAL / "registration-final.json"), str(EVAL / "worker-output" / "worker-result.json"), str(EVAL / "parent-terminal-audit.json")],
        eval_seeds, eval_events_count, "1024 unique shared seeds constructed for 7 policies; D300 is the registered reserved evaluation cohort"))
    assert len(eval_seeds) == 1024 and eval_events_count == 7168
    assert len(eval_reg["seeds"]) == 1024 and set(eval_reg["seeds"]) == eval_seeds
    assert all(inside(s, RESERVED["D300"]) for s in eval_seeds)

    # CPU/MPS RNG reference measured generator states only; inspect registration/outputs to exclude game constructors.
    restore_probe_path = V2 / "confirmed324-restore-probe-prepare-sol-20261026-r1" / "receipt.json"
    restore_probe_receipt = read(restore_probe_path, "restore qualification preparation receipt; not registered or runtime-qualified")
    runnable_ref_path = V2 / "confirmed324-runnable-reference-probe-luna-20261026-r2" / "receipt.json"
    runnable_ref_receipt = read(runnable_ref_path, "runnable-reference preparation receipt; pending and not run")
    assert restore_probe_receipt["status"] == "prepared_not_registered_not_runtime_qualified"
    assert runnable_ref_receipt["status"] == "pending_notrun"
    rng_dir = V2 / "progressive1000-rng-reference-parent-20261026-r1"
    rng_reg = read(rng_dir / "registration-final.json", "CPU/MPS RNG reference registration and stated no-environment purpose")
    rng_audit = read(rng_dir / "parent-terminal-audit.json", "CPU/MPS RNG reference terminal audit")
    ref_outputs = []
    for n in (1, 2, 3):
        p = rng_dir / "outputs" / f"replica-{n}.json"
        obj = read(p, "measured CPU/MPS RNG state receipt")
        ref_outputs.append({"path": str(p), "sha256": SOURCES[str(p)]["sha256"], "backend": obj["backend"], "status": obj["status"],
                            "complete_seed_vector": obj["complete_seed_vector"], "contains_game_seed_or_episode_records": False})
    assert "no_model_environment_training" in rng_reg["expected_lease"]["purpose"]

    history = set(merged["sorted_unique_seed_values"])
    extended_actual = set().union(*post_seed_values.values())
    range_hits = {name: sorted(s for s in extended_actual if inside(s, span)) for name, span in {**RESERVED, **NEW}.items()}
    pool_records = []
    exclusion_hits = Counter()
    for seed, observations in pool_observations.items():
        if seed in history: exclusion_hits["closure_merged_history_set"] += 1
        reserved = [name for name, span in RESERVED.items() if inside(seed, span)]
        new_hits = [name for name, span in NEW.items() if inside(seed, span)]
        exclusion_hits["historical_reserved_range"] += bool(reserved)
        exclusion_hits["new_cohort_range"] += bool(new_hits)
        vals = sorted(o["alive_frames"] for o in observations)
        median = vals[len(vals)//2] if len(vals) % 2 else (vals[len(vals)//2-1] + vals[len(vals)//2]) / 2
        below = sum(v < 1000 for v in vals)
        above = sum(v >= 1000 for v in vals)
        cls = "hard_alive_lt_1000" if median < 1000 else "alive_ge_1000"
        pool_records.append({"actual_seed": seed, "class_by_median_alive_frames": cls,
                             "median_alive_frames": median, "min_alive_frames": min(vals), "max_alive_frames": max(vals),
                             "replica_observation_count": len(observations), "observations_disagree_at_1000": bool(below and above),
                             "reserved_range_hits": reserved, "new_cohort_hits": new_hits,
                             "observations": sorted(observations, key=lambda x: (x["run_id"], x["completed_episode_index"]))})
    pool_records.sort(key=lambda x: x["actual_seed"])
    eligible = [r for r in pool_records if not r["reserved_range_hits"] and not r["new_cohort_hits"]]
    by_class = defaultdict(list)
    for row in eligible: by_class[row["class_by_median_alive_frames"]].append(row)
    assert len(by_class["hard_alive_lt_1000"]) >= 256 and len(by_class["alive_ge_1000"]) >= 256
    selected = []
    for cls in ("hard_alive_lt_1000", "alive_ge_1000"):
        ranked = sorted(by_class[cls], key=lambda r: hashlib.sha256(f"rl-followup-seed-pool512-v1:{r['actual_seed']}:20261027".encode()).hexdigest())
        selected.extend({"actual_seed": r["actual_seed"], "class_by_median_alive_frames": cls,
                         "median_alive_frames": r["median_alive_frames"],
                         "selection_key_sha256": hashlib.sha256(f"rl-followup-seed-pool512-v1:{r['actual_seed']}:20261027".encode()).hexdigest()}
                        for r in ranked[:256])
    selected.sort(key=lambda r: r["actual_seed"])
    assert len(selected) == 512 and len({r["actual_seed"] for r in selected}) == 512
    assert not any(inside(r["actual_seed"], span) for r in selected for span in RESERVED.values())
    assert not any(inside(r["actual_seed"], span) for r in selected for span in NEW.values())

    d4 = list(range(* (NEW["D400_dev"][0:1] + (NEW["D400_dev"][1] + 1,))))
    d5 = list(range(NEW["D500_confirm"][0], NEW["D500_confirm"][1] + 1))
    assert not (set(d4) & history) and not (set(d4) & extended_actual)
    assert not (set(d5) & history) and not (set(d5) & extended_actual)
    assert not (set(d4) & set(d5))

    source_pin_path = OUT / "source-pins.json"
    with open(source_pin_path, "w") as f:
        json.dump({"inputs": SOURCES}, f, indent=2, sort_keys=True); f.write("\n")
    seed_vector_hashes = {"D400_dev_sha256_u32be": hashlib.sha256(b"".join(x.to_bytes(4, "big") for x in d4)).hexdigest(),
                          "D500_confirm_sha256_u32be": hashlib.sha256(b"".join(x.to_bytes(4, "big") for x in d5)).hexdigest()}
    reconciliation = {
        "scope": "Freshness evidence only for parent-accepted recorded accepted324 entity-teacher lineage, its related recorded failed/diagnostic runs, and recorded checkpoint selection/evaluation history. No global workspace nonuse claim.",
        "closure": {"receipt_status": closure_receipt["status"], "known_scope_conservative_seed_count": merged["count"],
                    "known_scope_conservative_sha256": merged["canonical_sha256"], "parent_acceptance_status": acceptance["status"],
                    "parent_supported_claim": acceptance["supported_freshness_claim"], "parent_launch_authority": acceptance["launch_authority"],
                    "unresolved_file_roles": closure_receipt["remaining_unresolved_file_roles"],
                    "qualification_content_isolation_passed": closure_receipt["qualification_content_isolation_passed"],
                    "interpretation": "Earlier parent explicitly accepted D300 freshness for this learner family despite bounded unresolved nonteacher roles and the recorded content-boundary incident; preserve that claim and limits."},
        "registry": {"path": str(REGISTRY), "actual_training_launches": curriculum_state["actual_training_launches"],
                     "formal_training_endpoints_complete": curriculum_state["formal_training_endpoints_complete"],
                     "full_comparison_complete": curriculum_state["full_comparison_complete"],
                     "rng_reference_status": curriculum_state["initial_rng_reference_status"]},
        "postclosure_actual_constructors": post_runs,
        "other_reference_and_restore_checks": {"CPU_MPS_rng_reference": "three CPU/MPS generator-state receipts only; registration purpose says no model/environment/training; no game environment or episode seed fields", "outputs": ref_outputs,
            "restore_probe": {"path": str(restore_probe_path), "status": restore_probe_receipt["status"], "conclusion": "prepared only; no registered/runtime-qualified constructor run"},
            "runnable_reference_probe": {"path": str(runnable_ref_path), "status": runnable_ref_receipt["status"], "conclusion": "pending_notrun; no additional constructor"}},
        "unique_extended_actual_seed_count": len(extended_actual),
        "extended_seed_union_sha256_canonical_json": hashlib.sha256(json.dumps(sorted(extended_actual), separators=(",", ":")).encode()).hexdigest(),
        "reserved_and_candidate_range_hits_in_extended_actual_history": {k: len(v) for k, v in range_hits.items()},
        "D300_actual_unique_seed_count": len(eval_seeds), "D300_constructor_events": eval_events_count,
        "D400_and_D500": {"ranges": {k: [v[0], v[1]] for k, v in NEW.items()},
                           "seed_vector_sha256_u32be": seed_vector_hashes, "counts": {"D400_dev": len(d4), "D500_confirm": len(d5)},
                           "hits_in_closure_conservative_set": {"D400_dev": len(set(d4) & history), "D500_confirm": len(set(d5) & history)},
                           "hits_in_extended_actual_constructor_union": {"D400_dev": len(set(d4) & extended_actual), "D500_confirm": len(set(d5) & extended_actual)},
                           "within_or_cross_range_duplicates": 0,
                           "status": "verified_no_hits_within_reconciled_scope; parent must accept scope and reserve before use"},
        "remaining_limits": ["No universal workspace-wide nonuse claim; unrelated or unrecorded execution outside the accepted324 recorded-family scope is not adjudicated.",
                             "R2 closure records 122 bounded file roles in seven groups and a prior qualification-content search boundary incident; parent accepted the narrower learner-history scope, not clean-room isolation.",
                             "Current registry and specific retained run artifacts extend the earlier closure; registry state is a mutable snapshot, and it does not prove absent unrecorded runs."],
        "source_pin_file": str(source_pin_path),
        "checks": {"all_six_formal_run_registrations_match_manifest": True,
                   "training_pool_candidates_outside_reserved_ranges": not exclusion_hits["historical_reserved_range"] and not exclusion_hits["new_cohort_range"],
                   "D400_D500_disjoint_from_closure_and_postclosure_actuals": True,
                   "CPU_MPS_reference_excluded_as_no_environment_construction": True}}
    with open(OUT / "seed-reconciliation.json", "w") as f:
        json.dump(reconciliation, f, indent=2, sort_keys=True); f.write("\n")
    pool = {"schema": "control_training_seed_candidate_inventory_v1",
            "source_scope": "Only completed environment.completions from three accepted formal CONTROL worker-result final snapshots. No curriculum, parent, probe, failed-attempt, D300 evaluation, or B/E outcome source contributes candidates.",
            "source_proof": [source_descriptor(row["result_path"]) for row in control_source_rows],
            "source_registration_proof": sorted({(row["registration_path"], SOURCES[row["registration_path"]]["sha256"]) for row in control_source_rows}),
            "raw_completed_control_episode_rows": len(control_source_rows), "unique_actual_training_seeds": len(pool_records),
            "dedupe_key": "native_info.seed.actual_seed (u32); each seed appears once with all completed control-run observations retained",
            "classification": "median completed alive_frames across observed control replicas; hard_alive_lt_1000 iff median<1000, otherwise alive_ge_1000; per-seed replica disagreement retained",
            "excluded_range_names": list(RESERVED) + list(NEW), "candidate_exclusions": dict(exclusion_hits),
            "pool_counts": dict(Counter(r["class_by_median_alive_frames"] for r in eligible)),
            "proposed_deterministic_pool512": {"status": "proposal_only_root_pins_selection", "strata": {"hard_alive_lt_1000": 256, "alive_ge_1000": 256},
                "selection_rule": "Within each median-alive stratum, rank by SHA256('rl-followup-seed-pool512-v1:{actual_seed}:20261027') ascending; take first 256. IDs are reproducible and contain no evaluation cohort seeds.",
                "entries": selected},
            "candidate_seeds": pool_records}
    with open(OUT / "training-pool-candidates.json", "w") as f:
        json.dump(pool, f, indent=2, sort_keys=True); f.write("\n")
    with open(OUT / "training-pool-candidates.csv", "w", newline="") as f:
        fields = ["actual_seed", "class_by_median_alive_frames", "median_alive_frames", "min_alive_frames", "max_alive_frames", "replica_observation_count", "observations_disagree_at_1000", "eligible_after_reserved_exclusions", "selected_pool512"]
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        selected_seeds = {r["actual_seed"] for r in selected}
        for row in pool_records:
            w.writerow({"actual_seed": row["actual_seed"], "class_by_median_alive_frames": row["class_by_median_alive_frames"],
                        "median_alive_frames": row["median_alive_frames"], "min_alive_frames": row["min_alive_frames"],
                        "max_alive_frames": row["max_alive_frames"], "replica_observation_count": row["replica_observation_count"],
                        "observations_disagree_at_1000": row["observations_disagree_at_1000"],
                        "eligible_after_reserved_exclusions": not row["reserved_range_hits"] and not row["new_cohort_hits"],
                        "selected_pool512": row["actual_seed"] in selected_seeds})
    receipt = {"schema": "rl_followup_seed_reconciliation_receipt_v1", "outputs_owned_only": str(OUT),
               "source_pins_path": str(source_pin_path), "source_pin_count": len(SOURCES),
               "reconciliation_path": str(OUT / "seed-reconciliation.json"),
               "training_pool_path": str(OUT / "training-pool-candidates.json"),
               "candidate_csv_path": str(OUT / "training-pool-candidates.csv"),
               "no_training_evaluation_model_native_torch_checkpoint_or_ledger_writes": True,
               "reserved_range_names": list(RESERVED), "new_ranges": {k: [v[0], v[1]] for k, v in NEW.items()},
               "D300_hits_in_new_ranges": 0, "D400_D500_actual_history_hits": 0,
               "historical_scope_accepted_by_parent": acceptance["supported_freshness_claim"]}
    with open(OUT / "receipt.json", "w") as f:
        json.dump(receipt, f, indent=2, sort_keys=True); f.write("\n")
    print(json.dumps({"unique_extended_actual_seeds": len(extended_actual), "D300_unique_seeds": len(eval_seeds),
        "pool_raw_completed_rows": len(control_source_rows), "pool_unique_candidates": len(pool_records),
        "pool_classes": dict(Counter(r["class_by_median_alive_frames"] for r in eligible)),
        "selected_512": len(selected), "range_hits": reconciliation["reserved_and_candidate_range_hits_in_extended_actual_history"],
        "D400_D500_status": reconciliation["D400_and_D500"]["status"], "source_pin_count": len(SOURCES)}, indent=2))

if __name__ == "__main__": main()
