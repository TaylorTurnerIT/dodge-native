"""Create an owned 512-seed candidate pool from source-pinned parent audit output."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parents[0]/"rl-followup-seed-reservation-parent-20261027-r1"
PARENT=HERE.parents[0]/"rl-next-experiments-parent-20261027-r1"

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()
def read(path): return json.loads(Path(path).read_text())

def build(out_path):
    receipt=read(SOURCE/"receipt.json"); pins=read(SOURCE/"source-pins.json"); candidates=read(SOURCE/"training-pool-candidates.json")
    immutable_doc=read(PARENT/"seed-history-immutable-inputs.json")
    rebound=immutable_doc.get("mutable_input_rebound",{})
    original=rebound.get("original_path");snapshot=rebound.get("immutable_snapshot")
    if not rebound.get("byte_identical_at_acceptance") or not isinstance(original,str) or not isinstance(snapshot,str):
        raise ValueError("parent-accepted immutable ledger mapping required")
    if hashlib.sha256(Path(snapshot).read_bytes()).hexdigest()!=rebound.get("sha256"):
        raise ValueError("parent immutable ledger snapshot hash differs")
    reconciliation=read(SOURCE/"seed-reconciliation.json")
    if receipt.get("schema")!="rl_followup_seed_reconciliation_receipt_v1": raise ValueError("seed reconciliation receipt schema differs")
    if receipt.get("historical_scope_accepted_by_parent") is None: raise ValueError("bounded history scope lacks parent acceptance")
    if receipt.get("D400_D500_actual_history_hits")!=0 or receipt.get("D300_hits_in_new_ranges")!=0:
        raise ValueError("fresh-cohort ancestry check has seed hits")
    if candidates.get("source_scope","").startswith("Only completed environment.completions") is False:
        raise ValueError("candidate pool source must be completed training controls only")
    if candidates.get("proposed_deterministic_pool512",{}).get("status")!="proposal_only_root_pins_selection":
        raise ValueError("parent deterministic pool selection status differs")
    if len(candidates["proposed_deterministic_pool512"]["entries"])!=512:
        raise ValueError("parent selection must contain exactly512 candidates")
    checked=[]
    for path,row in pins["inputs"].items():
        actual=snapshot if path==original else path
        actual_sha=sha(actual)
        if actual_sha!=row["sha256"]: raise ValueError("source-pinned historical input changed: "+path)
        checked.append({"path":actual,"source_path":path,"sha256":actual_sha,"role":row["role"]})
    source_rows={row["actual_seed"]:row for row in candidates["candidate_seeds"]}
    exclusions={"B":[0xB0000000,0xB00003E7],"D128":[0xD0000000,0xD000007F],
        "D100":[0xD1000000,0xD10003FF],"D200":[0xD2000000,0xD20007FF],
        "D300":[0xD3000000,0xD30003FF],"E":[0xE0000000,0xE00003E7],
        "D400_dev":reconciliation["D400_and_D500"]["ranges"]["D400_dev"],
        "D500_confirm":reconciliation["D400_and_D500"]["ranges"]["D500_confirm"]}
    rows=[]
    for entry in candidates["proposed_deterministic_pool512"]["entries"]:
        seed=entry["actual_seed"]; source=source_rows.get(seed)
        if source is None: raise ValueError("selected seed absent from audited candidates")
        stratum="hard" if entry["class_by_median_alive_frames"]=="hard_alive_lt_1000" else "easy"
        observations=source["observations"]
        if not observations: raise ValueError("selected training seed lacks completed-control provenance")
        evidence=[]
        for obs in observations:
            if obs["observation_kind"]!="accepted_worker_result_final_snapshot.environment.completions.native_info":
                raise ValueError("unexpected seed source observation")
            if not obs["run_id"].endswith("control_constant_3e-5"):
                raise ValueError("non-control seed label source")
            evidence.append({"run_id":obs["run_id"],"source_path":obs["source_path"],
                "source_sha256":obs["source_sha256"],"registration_path":obs["registration_path"],
                "registration_sha256":obs["registration_sha256"],"episode_index":obs["completed_episode_index"],
                "alive_frames":obs["alive_frames"],"evaluation":False,"role":"training"})
        rows.append({"seed":seed,"stratum":stratum,"training_evidence":{"role":"training",
            "evaluation":False,"label":"median_alive_lt_1000" if stratum=="hard" else "median_alive_ge_1000",
            "median_alive_frames":entry["median_alive_frames"],"selection_key_sha256":entry["selection_key_sha256"],
            "observations":evidence}})
    if len({r["seed"] for r in rows})!=512 or sum(r["stratum"]=="hard" for r in rows)!=256:
        raise ValueError("parent pool must be 256/256 unique seeds")
    for row in rows:
        if any(lo<=row["seed"]<=hi for low,high in exclusions.values() for lo,hi in [(low,high)]):
            raise ValueError("selected training seed intersects historical or future exclusion")
    doc={"schema":"dodge_seed_priority_pool_v1","status":"candidate_pending_parent_registry_acceptance",
        "role":"training_only","history_closure":"parent_accepted_bounded_scope_no_universal_claim",
        "evaluation_seeds_used_for_selection":False,"parent_scope_claim":receipt["historical_scope_accepted_by_parent"],
        "scope_limits":{"universal_workspace_nonuse_claim":False,"qualification_content_isolation_passed":False,
            "historical_file_roles_unresolved":reconciliation["closure"]["unresolved_file_roles"]},
        "selection_rule":candidates["proposed_deterministic_pool512"]["selection_rule"],
        "source_receipt_path":str(SOURCE/"receipt.json"),"source_receipt_sha256":sha(SOURCE/"receipt.json"),
        "source_pins_path":str(SOURCE/"source-pins.json"),"source_pins_sha256":sha(SOURCE/"source-pins.json"),
        "mutable_ledger_rebound":dict(original_path=original,immutable_snapshot=snapshot,
            sha256=rebound["sha256"],parent_immutable_inputs_path=str(PARENT/"seed-history-immutable-inputs.json"),
            parent_immutable_inputs_sha256=sha(PARENT/"seed-history-immutable-inputs.json")),
        "candidate_manifest_path":str(SOURCE/"training-pool-candidates.json"),
        "candidate_manifest_sha256":sha(SOURCE/"training-pool-candidates.json"),
        "fresh_cohort_receipt_path":str(SOURCE/"seed-reconciliation.json"),
        "fresh_cohort_receipt_sha256":sha(SOURCE/"seed-reconciliation.json"),
        "excluded_seed_ranges":[value for value in exclusions.values()],
        "excluded_range_names":list(exclusions),"verified_input_count":len(checked),
        "verified_inputs":checked,"seeds":rows}
    path=Path(out_path)
    if path.exists():raise FileExistsError("refusing to replace existing candidate pool: "+str(path))
    path.write_text(json.dumps(doc,sort_keys=True,indent=2)+"\n")
    return {"path":str(path),"sha256":sha(path),"seeds":len(rows),"verified_inputs":len(checked),
            "status":doc["status"],"launch_authority":False}

if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument("--output",default=str(HERE/"training-pool-candidate.json"));args=parser.parse_args()
    print(json.dumps(build(args.output),sort_keys=True))
