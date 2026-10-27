"""Independent per-candidate parent gate for the frozen best180 branch."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "learning/runs/v2/D2-best180-branch-prepare-luna-20261026-r1"
REG_PATH = ROOT / "learning/runs/v2/D2-best180-branch-registration-luna-20261026-r2/registration-proposed.json"
REG_SHA = "d6a5aa8cbdd889728b79486f09673215847b6d8e27f93f1ce80eb1cf3e8cc7ba"
PARENT_SHA = "105e0f7a83e154116bd9f0d5eaaf573a896886468c9038f548f5ce7e6377c7ea"
PARENT_RECEIPT_SHA = "7968a62b6e601fab971e4145dbaebfa1995c8f696e6df442ab70fc0435b74903"
UPDATES = (180, 192, 204, 216, 228, 240, 252)

def check(ok, msg):
    if not ok: raise ValueError(msg)

def digest_bytes(b): return hashlib.sha256(b).hexdigest()
def digest(path): return digest_bytes(Path(path).read_bytes())
def stable_json(path):
    p=Path(path); before=p.read_bytes(); value=json.loads(before); after=p.read_bytes()
    check(before == after, f"Input changed while reading: {p}")
    return value, digest_bytes(before)
def stable_lines(path):
    p=Path(path); before=p.read_bytes(); after=p.read_bytes()
    check(before==after and (not before or before.endswith(b"\n")),f"Input changed or append is incomplete: {p}")
    return [json.loads(line) for line in before.splitlines()],digest_bytes(before)
def load_module(name, path):
    spec=importlib.util.spec_from_file_location(name, path); mod=importlib.util.module_from_spec(spec)
    sys.modules[name]=mod; spec.loader.exec_module(mod); return mod

def validate_snapshot_binding(state, reg, parent, runner, update, metric):
    """Small pure metadata gate, also exercised by mutation controls."""
    local=update-runner.PHASE_START
    check(state["phase"]=="D2" and state["phase_update"]==update and state["local_update"]==local,"Candidate phase/local update differs")
    check(state["registration_sha256"]==REG_SHA and state["config_sha256"]==reg["config_sha256"]
          and state["native_sha256"]==reg["native"]["sha256"] and state["runtime_sha256"]==reg["runtime_sha256"]
          and state["policy_sha256"]==runner.POLICY_SHA and state["parent_sha256"]==PARENT_SHA
          and state["parent_checkpoint_sha256"]==PARENT_SHA and state["parent_registration_sha256"]==runner.PARENT_REGISTRATION_SHA
          and state["parent_run_id"]=="D2-gradient-alignment-20261025-r2" and state["run_seed"]==reg["run_seed"],"Candidate frozen identity differs")
    ident=state["identity"]
    check(ident["run_id"]==runner.RUN_ID and ident["run_seed"]==reg["run_seed"]
          and ident["registration_sha256"]==REG_SHA and ident["phase"]=="D2"
          and ident["config_sha256"]==reg["config_sha256"] and ident["architecture"]==parent["identity"]["architecture"],"Identity/config/architecture differs")
    check(state["counters"]==metric["counters"] and metric["local_update"]==local,"Metric counters do not match candidate")
    check(state["inherited_counters"]==parent["cumulative_counters"] and state["parent_abandoned_current_episodes"]==parent["abandoned_current_episodes"],"Inherited counters/parent abandonment differs")
    expected=runner.continuation_cumulative_counters(parent["cumulative_counters"],state["counters"])
    check(state["cumulative_counters"]==expected and expected["updates"]==228+local,"Cumulative parent base differs")

def validate_resume_snapshot(state):
    indices=state["next_episode_indices"]; abandoned=state["abandoned_current_episodes"]
    check(len(indices)==64 and all(type(x) is int and 0<=x<2**64 for x in indices),"Resume next indices invalid")
    check(len(abandoned)==64 and sorted(x["slot"] for x in abandoned)==list(range(64)),"Resume records lack one entry per slot")
    for slot,item in enumerate(sorted(abandoned,key=lambda x:x["slot"])):
        check(item["seed"]["slot"]==slot and item["seed"]["episode"]+1==indices[slot]
              and type(item["gameplay_frames"]) is int and 0<=item["gameplay_frames"]<18000,"Resume seed/frame lineage differs")

def exact_tree(a,b):
    if type(a) is not type(b): return False
    if isinstance(a,dict): return a.keys()==b.keys() and all(exact_tree(a[k],b[k]) for k in a)
    if isinstance(a,(list,tuple)): return len(a)==len(b) and all(exact_tree(x,y) for x,y in zip(a,b))
    try:
        import torch
        if isinstance(a,torch.Tensor): return torch.equal(a,b)
    except ImportError: pass
    try:
        import numpy as np
        if isinstance(a,np.ndarray): return np.array_equal(a,b)
    except ImportError: pass
    return a==b

def audit(reg=REG_PATH):
    reg, reg_hash=stable_json(reg)
    check(reg_hash == REG_SHA, "Registration hash differs")
    runner=load_module("best180_frozen_runner", SRC/"runner.py")
    launcher=load_module("best180_frozen_execute_once", SRC/"execute_once.py")
    check(Path(reg["runner_path"]).resolve() == (SRC/"runner.py").resolve(), "Frozen runner origin differs")
    check(reg["run_id"] == runner.RUN_ID and reg["run_seed"] == 3791628417, "Run identity/seed differs")
    check(reg["parent"]["sha256"] == PARENT_SHA and reg["parent"]["terminal_receipt_sha256"] == PARENT_RECEIPT_SHA,
          "Accepted parent binding differs")
    root=Path(reg["root"]); out=Path(reg["output"]); runtime=Path(reg["runtime_root"])
    sys.path.insert(0, str(runtime)); from dodge_rl import checkpoints as ckpt
    # Original accepted file remains authority; re-saved update 180 is audited as candidate only.
    parent=ckpt.load_checkpoint(Path(reg["parent"]["path"]), expected_sha256=PARENT_SHA); ckpt.require_complete_update(parent)
    receipt=Path(reg["parent"]["terminal_receipt_path"]); check(digest(receipt)==PARENT_RECEIPT_SHA,"Parent receipt changed")
    metrics,metrics_hash=stable_lines(out/"training-metrics.jsonl")
    journal,journal_hash=stable_lines(out/"training-episodes.jsonl")
    inherited=[x for x in journal if x.get("kind")=="abandoned_parent_episode"]
    check(len(inherited)==64 and sorted(x["info"]["slot"] for x in inherited)==list(range(64)),"Accepted parent abandoned journal records incomplete")
    check(sorted((x["info"] for x in inherited),key=lambda x:x["slot"])==sorted(parent["abandoned_current_episodes"],key=lambda x:x["slot"]),"Accepted parent abandoned journal records differ")
    check(all(x.get("reason")=="fresh_environment_at_saved_next_episode_index" and x.get("parent_checkpoint_sha256")==PARENT_SHA for x in inherited),"Accepted parent abandoned journal authority differs")
    certificates={}
    for update in UPDATES:
        cp=out/f"checkpoint-{update:06d}-candidate.pt"; certp=out/f"development-{update:06d}.json"
        sidep=Path(str(cp)+".json")
        for p in (cp,certp,sidep): check(p.is_file() and not p.name.endswith(".partial"),f"Certificate not published: {p.name}")
        cert, cert_hash=stable_json(certp); side, side_hash=stable_json(sidep)
        cp_hash=digest(cp); check(cert["checkpoint"]==cp.name and cert["checkpoint_sha256"]==cp_hash,"Certificate checkpoint hash/name differs")
        check(side["checkpoint_sha256"]==cp_hash and side["eligibility_status"]=="provisional_pending_parent_terminal_receipt"
              and side["training_eligible"] is False and side["promoted"] is False,"Candidate sidecar flags/hash differ")
        state=ckpt.load_checkpoint(cp, expected_sha256=cp_hash); ckpt.require_complete_update(state)
        check(digest(cp)==cp_hash,"Checkpoint changed during independent audit")
        local=update-runner.PHASE_START
        check(state["schema"]=="d2_training_v3_checkpoint_v1" and state["tag"]=="candidate"
              and state["eligibility_status"]=="provisional_pending_parent_terminal_receipt"
              and state["training_eligible"] is False and state["promoted"] is False,"Candidate schema/eligibility differs")
        check(state["registration_sha256"]==REG_SHA and state["config_sha256"]==reg["config_sha256"]
              and state["native_sha256"]==reg["native"]["sha256"] and state["runtime_sha256"]==reg["runtime_sha256"]
              and state["policy_sha256"]==runner.POLICY_SHA and state["parent_sha256"]==PARENT_SHA
              and state["parent_checkpoint_sha256"]==PARENT_SHA and state["parent_registration_sha256"]==runner.PARENT_REGISTRATION_SHA
              and state["parent_run_id"]=="D2-gradient-alignment-20261025-r2" and state["run_seed"]==reg["run_seed"],"Candidate frozen identity differs")
        ident=state["identity"]
        from dodge_rl.identity import identity_hash
        check(state["identity_sha256"]==identity_hash(ident),"Identity hash differs")
        check(state["update_progress"]=={"completed_updates":local,"complete":True,"in_update":False},"Update progress differs")
        row=next((x for x in metrics if x.get("phase_update")==update),None)
        if update==180:
            zero={key:0 for key in ("updates","optimizer_steps","environment_decisions","raw_frames")}
            check(row is None and state["counters"]==zero and state["local_update"]==0,"Entry candidate did not preserve zero local counters")
            check(exact_tree(state["model"],parent["model"]) and exact_tree(state["optimizer"],parent["optimizer"]) and exact_tree(state["rng"],parent["rng"]),"Entry candidate model/Adam/RNG differs from accepted parent")
        else:
            check(row is not None,"Candidate metric row missing")
            validate_snapshot_binding(state,reg,parent,runner,update,row)
            check(row["update_progress"]==state["update_progress"],"Metric update progress differs")
        check(state["inherited_counters"]==parent["cumulative_counters"] and state["parent_abandoned_current_episodes"]==parent["abandoned_current_episodes"],"Inherited counters/parent abandonment differs")
        expected=runner.continuation_cumulative_counters(parent["cumulative_counters"], state["counters"])
        check(state["cumulative_counters"]==expected and expected["updates"]==228+local,"Cumulative parent base differs")
        abandoned=state["abandoned_current_episodes"]
        validate_resume_snapshot(state)
        # Prefix only through this candidate; inherited parent abandon events do not count as new work.
        prefix=[x for x in journal if x.get("kind")=="initial" or x.get("kind")=="abandoned_parent_episode" or x.get("phase_update",0)<=update]
        episode=runner.validate_episode_journal(prefix,parent["next_episode_indices"])
        check(episode["next_episode_indices"]==state["next_episode_indices"],"Snapshot next indices differ from journal prefix")
        check(episode["current_episode_indices"]=={x["slot"]:x["seed"]["episode"] for x in abandoned},"Snapshot current indices differ from journal")
        complete=sum(x["info"]["gameplay_frames"] for x in prefix if x["kind"]=="completed")
        check(complete+sum(x["gameplay_frames"] for x in abandoned)==state["counters"]["raw_frames"],"Prefix raw-frame conservation differs")
        ev=cert["evaluation"]; erows=ev["rows"]
        check(ev["complete"] is True and len(erows)==64 and sorted(x["seed"] for x in erows)==list(range(0xD0000000,0xD0000040)),"Evaluation cohort differs")
        perf=runner.performance(ev)
        check(cert["performance"]==perf and cert["competence_passed"]==(ev["mean_alive_frames"]>=3060),"Evaluation performance/competence differs")
        check(ev["mean_alive_frames"]==sum(x["alive_frames"] for x in erows)/64 and ev["mean_score"]==sum(x["score"] for x in erows)/64,"Evaluation means differ")
        deaths=sum(bool(x["terminated"]) for x in erows); caps=sum(bool(x["truncated"]) for x in erows)
        causes={}
        for item in erows:
            check(bool(item["terminated"]) != bool(item["truncated"]),"Evaluation episode boundary differs")
            if item["terminated"]: causes[item["death_cause"]]=causes.get(item["death_cause"],0)+1
            check(math.isclose(item["objective_return"],item["score"]+.01*item["alive_frames"]-(5 if item["terminated"] else 0),abs_tol=1e-9),"Evaluation objective differs")
        check(deaths==ev["deaths"] and caps==ev["caps"] and deaths+caps==64 and causes=={k:v for k,v in ev["death_causes"].items() if v},"Evaluation death counts differ")
        check(cert["normal_training_iteration"] is True and cert["training_eligible"] is False and cert["promoted"] is False and cert["training_state_unchanged"] is True,"Evaluation eligibility flags differ")
        certificates[update]={"mean_alive_frames":ev["mean_alive_frames"],"mean_score":ev["mean_score"],"checkpoint_sha256":cp_hash,"certificate_sha256":cert_hash,"sidecar_sha256":side_hash,"competence_passed":cert["competence_passed"]}
    best=max(UPDATES,key=lambda u: certificates[u]["mean_alive_frames"])
    # Strict improvement only; output stays proposed until whole parent terminal acceptance.
    original_eval,_=stable_json(root/"learning/runs/v2/D2-gradient-alignment-20261025-r2/development-000180.json")
    if certificates[180]["mean_alive_frames"] <= original_eval["evaluation"]["mean_alive_frames"]: best=None
    result={"schema":"d2_best180_all_candidate_audit_v1","status":"provisional_candidates_only","run_id":runner.RUN_ID,
            "registration_sha256":REG_SHA,"updates":list(UPDATES),"audited_evaluations":len(certificates),
            "launcher_reported_evaluations_checked":2,"original_parent_checkpoint_sha256":PARENT_SHA,
            "original_parent_receipt_sha256":PARENT_RECEIPT_SHA,"proposed_best_update":best,"candidates":certificates,
            "authority_note":"No whole-run acceptance, best replacement, or continuation authority until parent terminal acceptance."}
    rr=out/"run-result.json"; wr=out/"worker-result.json"
    if rr.is_file() and wr.is_file():
        run_result,_=stable_json(rr); worker,_=stable_json(wr)
        if run_result.get("status")=="passed" and worker.get("status")=="completed":
            terminal=launcher.validate_outputs(reg,worker,REG_SHA)
            result["frozen_launcher_terminal_checks"]=terminal
            result["status"]="all_candidates_audited_pending_parent_terminal_acceptance"
        else:
            result["terminal_run_status"]=run_result.get("status")
    result["metrics_sha256"]=metrics_hash; result["episode_journal_sha256"]=journal_hash
    return result

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--output",required=True); args=ap.parse_args()
    result=audit(); Path(args.output).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
