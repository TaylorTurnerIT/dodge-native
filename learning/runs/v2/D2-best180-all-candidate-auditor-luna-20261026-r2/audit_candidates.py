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

def bind_frozen_runner():
    """Bind launcher import `runner` to exact, externally pinned source."""
    expected=SRC/"runner.py"
    existing=sys.modules.get("runner")
    if existing is not None and Path(existing.__file__).resolve()==expected.resolve(): return existing
    if existing is not None: del sys.modules["runner"]
    return load_module("runner",expected)

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
          and ident["config"]==reg["_config"] and ident["parent_checkpoint_sha256"]==PARENT_SHA
          and ident["policy_sha256"]==runner.POLICY_SHA
          and ident["architecture"]==parent["identity"]["architecture"],"Identity/config/architecture differs")
    check(state["counters"]==metric["counters"] and metric["local_update"]==local,"Metric counters do not match candidate")
    check(state["inherited_counters"]==parent["cumulative_counters"] and state["parent_abandoned_current_episodes"]==parent["abandoned_current_episodes"],"Inherited counters/parent abandonment differs")
    expected=runner.continuation_cumulative_counters(parent["cumulative_counters"],state["counters"])
    check(state["cumulative_counters"]==expected and expected["updates"]==228+local,"Cumulative parent base differs")

def validate_resume_snapshot(state):
    indices=state["next_episode_indices"]; abandoned=state["abandoned_current_episodes"]
    check(type(indices) is list and len(indices)==64 and all(type(x) is int and 0<=x<2**64 for x in indices),"Resume next indices invalid")
    check(type(abandoned) is list and len(abandoned)==64 and all(type(x) is dict for x in abandoned)
          and sorted(x["slot"] for x in abandoned)==list(range(64)),"Resume records lack one entry per slot")
    for slot,item in enumerate(sorted(abandoned,key=lambda x:x["slot"])):
        check(type(item["seed"]) is dict and type(item["seed"]["slot"]) is int and type(item["seed"]["episode"]) is int
              and item["seed"]["slot"]==slot and item["seed"]["episode"]+1==indices[slot]
              and type(item["gameplay_frames"]) is int and 0<=item["gameplay_frames"]<18000,"Resume seed/frame lineage differs")

def choose_best(certificates, original_mean):
    chosen=max(certificates,key=lambda u:certificates[u]["mean_alive_frames"])
    return chosen if certificates[chosen]["mean_alive_frames"]>original_mean else None

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

def audit(reg=REG_PATH, provisional=False):
    reg, reg_hash=stable_json(reg)
    check(reg_hash == REG_SHA, "Registration hash differs")
    reconciliation,_=stable_json(ROOT/"learning/runs/v2/D2-best180-branch-parent-launch-20261026-r1/review-reconciliation.json")
    pins=reconciliation["review_inputs_outputs_verified"]
    runner_rel=str(SRC.relative_to(ROOT)/"runner.py"); launcher_rel=str(SRC.relative_to(ROOT)/"execute_once.py")
    check(digest(SRC/"runner.py")==pins[runner_rel] and digest(SRC/"execute_once.py")==pins[launcher_rel],"Frozen runner/launcher source pin differs")
    runner=bind_frozen_runner()
    launcher=load_module("best180_frozen_execute_once", SRC/"execute_once.py")
    check(Path(reg["runner_path"]).resolve() == (SRC/"runner.py").resolve(), "Frozen runner origin differs")
    check(reg["run_id"] == runner.RUN_ID and reg["run_seed"] == 3791628417, "Run identity/seed differs")
    check(reg["parent"]["sha256"] == PARENT_SHA and reg["parent"]["terminal_receipt_sha256"] == PARENT_RECEIPT_SHA,
          "Accepted parent binding differs")
    root=Path(reg["root"]); out=Path(reg["output"]); runtime=Path(reg["runtime_root"])
    config,config_hash=stable_json(reg["config_path"]); reg["_config"]=config
    check(config_hash==reg["config_sha256"],"Frozen config hash differs")
    inventory_path=SRC/"runtime-member-inventory.json"
    check(digest(inventory_path)==reg["pins"][str(inventory_path)],"Runtime inventory registration pin differs")
    inventory,_=stable_json(inventory_path)
    for member,expected in inventory["member_sha256"].items():
        member_path=runtime/member
        check(digest(member_path)==expected,f"Frozen runtime member hash differs: {member}")
    sys.path.insert(0, str(runtime)); from dodge_rl import checkpoints as ckpt
    # Original accepted file remains authority; re-saved update 180 is audited as candidate only.
    parent=ckpt.load_checkpoint(Path(reg["parent"]["path"]), expected_sha256=PARENT_SHA); ckpt.require_complete_update(parent)
    receipt=Path(reg["parent"]["terminal_receipt_path"]); check(digest(receipt)==PARENT_RECEIPT_SHA,"Parent receipt changed")
    parent_sidecar=Path(str(reg["parent"]["path"])+".json"); parent_sidecar_hash=digest(parent_sidecar)
    metrics,metrics_hash=stable_lines(out/"training-metrics.jsonl")
    journal,journal_hash=stable_lines(out/"training-episodes.jsonl")
    inherited=[x for x in journal if x.get("kind")=="abandoned_parent_episode"]
    check(len(inherited)==64 and sorted(x["info"]["slot"] for x in inherited)==list(range(64)),"Accepted parent abandoned journal records incomplete")
    check(sorted((x["info"] for x in inherited),key=lambda x:x["slot"])==sorted(parent["abandoned_current_episodes"],key=lambda x:x["slot"]),"Accepted parent abandoned journal records differ")
    check(all(x.get("reason")=="fresh_environment_at_saved_next_episode_index" and x.get("parent_checkpoint_sha256")==PARENT_SHA for x in inherited),"Accepted parent abandoned journal authority differs")
    published=[]
    for update in UPDATES:
        cp=out/f"checkpoint-{update:06d}-candidate.pt"; certp=out/f"development-{update:06d}.json"; sidep=Path(str(cp)+".json")
        if all(p.is_file() and not p.name.endswith(".partial") for p in (cp,certp,sidep)):
            published.append(update)
        else:
            break
    if provisional:
        check(published and published[0]==180,"No stable published entry certificate")
        updates=tuple(published)
    else:
        updates=UPDATES
    certificates={}; tracked={}
    for update in updates:
        cp=out/f"checkpoint-{update:06d}-candidate.pt"; certp=out/f"development-{update:06d}.json"
        sidep=Path(str(cp)+".json")
        for p in (cp,certp,sidep): check(p.is_file() and not p.name.endswith(".partial"),f"Certificate not published: {p.name}")
        cert, cert_hash=stable_json(certp); side, side_hash=stable_json(sidep)
        cp_hash=digest(cp); check(cert["checkpoint"]==cp.name and cert["checkpoint_sha256"]==cp_hash,"Certificate checkpoint hash/name differs")
        tracked[str(cp)]=cp_hash; tracked[str(certp)]=cert_hash; tracked[str(sidep)]=side_hash
        check(side["checkpoint_sha256"]==cp_hash and side["eligibility_status"]=="provisional_pending_parent_terminal_receipt"
              and side["training_eligible"] is False and side["promoted"] is False,"Candidate sidecar flags/hash differ")
        state=ckpt.load_checkpoint(cp, expected_sha256=cp_hash); ckpt.require_complete_update(state)
        check(digest(cp)==cp_hash,"Checkpoint changed during independent audit")
        local=update-runner.PHASE_START
        check(state["schema"]=="d2_training_v3_checkpoint_v1" and state["tag"]=="candidate"
              and state["eligibility_status"]=="provisional_pending_parent_terminal_receipt"
              and state["training_eligible"] is False and state["promoted"] is False,"Candidate schema/eligibility differs")
        check(state["phase"]=="D2" and state["phase_update"]==update and state["local_update"]==update-runner.PHASE_START
              and state["registration_sha256"]==REG_SHA and state["config_sha256"]==reg["config_sha256"]
              and state["native_sha256"]==reg["native"]["sha256"] and state["runtime_sha256"]==reg["runtime_sha256"]
              and state["policy_sha256"]==runner.POLICY_SHA and state["parent_sha256"]==PARENT_SHA
              and state["parent_checkpoint_sha256"]==PARENT_SHA and state["parent_registration_sha256"]==runner.PARENT_REGISTRATION_SHA
              and state["parent_run_id"]=="D2-gradient-alignment-20261025-r2" and state["run_seed"]==reg["run_seed"],"Candidate frozen identity differs")
        matching_rows=[x for x in metrics if x.get("phase_update")==update]
        row=matching_rows[0] if len(matching_rows)==1 else None
        check(len(matching_rows)==(0 if update==180 else 1),"Candidate metric row count differs")
        if update!=180: validate_snapshot_binding(state,reg,parent,runner,update,row)
        ident=state["identity"]
        from dodge_rl.identity import identity_hash
        check(state["identity_sha256"]==identity_hash(ident),"Identity hash differs")
        check(ident["version"]=="teacher_identity_v3" and ident["run_id"]==runner.RUN_ID
              and ident["phase"]=="D2" and ident["phase_update_start"]==runner.PHASE_START
              and ident["phase_update_end"]==runner.PHASE_END and ident["run_seed"]==reg["run_seed"]
              and ident["registration_sha256"]==REG_SHA and ident["parent_checkpoint_sha256"]==PARENT_SHA
              and ident["policy_sha256"]==runner.POLICY_SHA
              and ident["architecture"]==parent["identity"]["architecture"],"Candidate embedded identity differs")
        progress=state["update_progress"]
        check(type(progress) is dict and progress.get("completed_updates")==local
              and progress.get("complete") is True and progress.get("in_update") is False,"Update progress differs")
        check(ident["config"]==config and ident["parent_checkpoint_sha256"]==PARENT_SHA
              and ident["policy_sha256"]==runner.POLICY_SHA and ident["registration_sha256"]==REG_SHA,
              "Identity config/ancestry/policy/registration differs")
        if update==180:
            zero={key:0 for key in ("updates","optimizer_steps","environment_decisions","raw_frames")}
            check(row is None and state["counters"]==zero and state["local_update"]==0,"Entry candidate did not preserve zero local counters")
            check(exact_tree(state["model"],parent["model"]) and exact_tree(state["optimizer"],parent["optimizer"]) and exact_tree(state["rng"],parent["rng"]),"Entry candidate model/Adam/RNG differs from accepted parent")
        else:
            check(row is not None,"Candidate metric row missing")
            check(row["update_progress"]==state["update_progress"],"Metric update progress differs")
        check(state["inherited_counters"]==parent["cumulative_counters"] and state["parent_abandoned_current_episodes"]==parent["abandoned_current_episodes"],"Inherited counters/parent abandonment differs")
        expected=runner.continuation_cumulative_counters(parent["cumulative_counters"], state["counters"])
        check(state["cumulative_counters"]==expected and expected["updates"]==228+local,"Cumulative parent base differs")
        abandoned=state["abandoned_current_episodes"]
        validate_resume_snapshot(state)
        # Prefix only through this candidate; inherited parent abandon events do not count as new work.
        prefix=[x for x in journal if x.get("kind")=="initial" or x.get("kind")=="abandoned_parent_episode" or x.get("phase_update",0)<=update]
        episode=runner.validate_episode_journal(prefix,parent["next_episode_indices"])
        check(type(episode) is dict and type(episode["next_episode_indices"]) is list
              and type(episode["current_episode_indices"]) is dict
              and episode["next_episode_indices"]==state["next_episode_indices"],"Snapshot next indices differ from journal prefix")
        check(episode["current_episode_indices"]=={x["slot"]:x["seed"]["episode"] for x in abandoned},"Snapshot current indices differ from journal")
        complete=sum(x["info"]["gameplay_frames"] for x in prefix if x["kind"]=="completed")
        check(complete+sum(x["gameplay_frames"] for x in abandoned)==state["counters"]["raw_frames"],"Prefix raw-frame conservation differs")
        ev=cert["evaluation"]; erows=ev["rows"]
        check(type(ev) is dict and ev["complete"] is True and type(erows) is list and len(erows)==64
              and all(type(x) is dict for x in erows)
              and all(type(x["seed"]) is int for x in erows)
              and sorted(x["seed"] for x in erows)==list(range(0xD0000000,0xD0000040)),"Evaluation cohort differs")
        perf=runner.performance(ev)
        check(cert["performance"]==perf and cert["competence_passed"]==(ev["mean_alive_frames"]>=3060),"Evaluation performance/competence differs")
        check(ev["mean_alive_frames"]==sum(x["alive_frames"] for x in erows)/64 and ev["mean_score"]==sum(x["score"] for x in erows)/64,"Evaluation means differ")
        check(all(type(x["terminated"]) is bool and type(x["truncated"]) is bool for x in erows),"Evaluation boundary flags are not booleans")
        deaths=sum(x["terminated"] for x in erows); caps=sum(x["truncated"] for x in erows)
        check(type(ev["deaths"]) is int and type(ev["caps"]) is int
              and type(ev["mean_alive_frames"]) in (int,float) and type(ev["mean_score"]) in (int,float)
              and math.isfinite(ev["mean_alive_frames"]) and math.isfinite(ev["mean_score"]),"Evaluation aggregate types differ")
        causes={}
        for item in erows:
            check(bool(item["terminated"]) != bool(item["truncated"]),"Evaluation episode boundary differs")
            if item["terminated"]: causes[item["death_cause"]]=causes.get(item["death_cause"],0)+1
            check(type(item["alive_frames"]) in (int,float) and type(item["score"]) in (int,float)
                  and type(item["objective_return"]) in (int,float)
                  and all(math.isfinite(item[key]) for key in ("alive_frames","score","objective_return")),"Evaluation metric types differ")
            check(math.isclose(item["objective_return"],item["score"]+.01*item["alive_frames"]-(5 if item["terminated"] else 0),abs_tol=1e-9),"Evaluation objective differs")
        check(deaths==ev["deaths"] and caps==ev["caps"] and deaths+caps==64 and causes=={k:v for k,v in ev["death_causes"].items() if v},"Evaluation death counts differ")
        check(cert["normal_training_iteration"] is True and cert["training_eligible"] is False and cert["promoted"] is False and cert["training_state_unchanged"] is True,"Evaluation eligibility flags differ")
        certificates[update]={"mean_alive_frames":ev["mean_alive_frames"],"mean_score":ev["mean_score"],"checkpoint_sha256":cp_hash,"certificate_sha256":cert_hash,"sidecar_sha256":side_hash,"competence_passed":cert["competence_passed"]}
    best=choose_best(certificates,0)
    # Strict improvement only; output stays proposed until whole parent terminal acceptance.
    original_eval,_=stable_json(root/"learning/runs/v2/D2-gradient-alignment-20261025-r2/development-000180.json")
    best=choose_best(certificates,original_eval["evaluation"]["mean_alive_frames"])
    result={"schema":"d2_best180_all_candidate_audit_v1","status":"provisional_candidates_only","run_id":runner.RUN_ID,
            "registration_sha256":REG_SHA,"updates":list(updates),"audited_evaluations":len(certificates),
            "launcher_reported_evaluations_checked":2,"parent_expected_evaluations_checked":len(certificates),"original_parent_checkpoint_sha256":PARENT_SHA,
            "original_parent_receipt_sha256":PARENT_RECEIPT_SHA,"proposed_best_update":best,"candidates":certificates,
            "pending_updates":[u for u in UPDATES if u not in certificates],
            "full_candidate_set_ready":all(u in certificates for u in UPDATES),
            "original_parent_sidecar_sha256":parent_sidecar_hash,
            "authority_note":"No whole-run acceptance, best replacement, or continuation authority until parent terminal acceptance."}
    execution=out/"execution-result.json"; wr=out/"worker-result.json"
    if not provisional:
        check(execution.is_file() and wr.is_file(),"Full terminal evidence missing")
        run_result,_=stable_json(execution); worker,_=stable_json(wr)
        check(run_result.get("status") in ("passed","completed") and worker.get("status")=="completed","Full terminal status is not successful")
        terminal=launcher.validate_outputs(reg,worker,REG_SHA)
        result["frozen_launcher_terminal_checks"]=terminal
        result["status"]="all_candidates_audited_pending_parent_terminal_acceptance"
    else:
        result["status"]="readonly_published_prefix_provisional"
        result["terminal_acceptance_authority"]=False
        result["best_replacement_authority"]=False
    for path,expected in tracked.items(): check(digest(path)==expected,f"Audited file changed during audit: {Path(path).name}")
    check(digest(out/"training-metrics.jsonl")==metrics_hash and digest(out/"training-episodes.jsonl")==journal_hash,
          "Training journals changed during audit")
    check(digest(receipt)==PARENT_RECEIPT_SHA and digest(Path(reg["parent"]["path"]))==PARENT_SHA
          and digest(parent_sidecar)==parent_sidecar_hash,"Parent authority/sidecar changed during audit")
    result["metrics_sha256"]=metrics_hash; result["episode_journal_sha256"]=journal_hash
    return result

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--output",required=True); ap.add_argument("--provisional",action="store_true"); args=ap.parse_args()
    output=Path(args.output); check(not output.exists(),f"Refusing to overwrite audit output: {output}")
    result=audit(provisional=args.provisional); output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
