"""Fail-closed parent-callable terminal confirmation auditor. No runtime imports."""
from __future__ import annotations
import hashlib, json, math, subprocess, time
from pathlib import Path

class AuditError(ValueError): pass

def sha(b): return hashlib.sha256(b).hexdigest()
def need(ok, msg):
    if not ok: raise AuditError(msg)
def read_json(path):
    try: return json.loads(Path(path).read_bytes())
    except Exception as e: raise AuditError(f"cannot read JSON: {path}") from e
def file_pin(path, pin, label):
    b=Path(path).read_bytes(); need(sha(b)==pin, f"{label} SHA-256 mismatch"); return b

def _process_rows(pid, ps_runner):
    # Independent ps query; requires target PID, PPID, and process group all absent.
    out=ps_runner(["ps","-axo","pid=,ppid=,pgid="])
    rows=[]
    for line in out.splitlines():
        try: a,b,c=map(int,line.split()); rows.append((a,b,c))
        except Exception: raise AuditError("unparseable ps row")
    return [r for r in rows if pid in r]
def _ps(args): return subprocess.check_output(args,text=True,timeout=5)
def _same_file(path,pin,label): file_pin(path,pin,label)
def _all_registered_pins(reg):
    for key in ("source",):
        for name,path in (("evaluator",reg[key].get("evaluator_path")),("launcher",reg[key].get("launcher_path")),("worker",reg[key].get("worker_path"))):
            _same_file(path,reg[key][name+"_sha256"],name)
    members=reg.get("runtime",{}).get("member_sha256",{})
    need(type(members) is dict and len(members)==13,"registered runtime must pin 13 members")
    for rel,pin in members.items():
        _same_file(Path(reg["runtime"]["root"])/rel,pin,"runtime member")
    for cohort in reg.get("cohorts",{}).values():
        _same_file(cohort["manifest_path"],cohort["manifest_sha256"],"cohort manifest")
    candidates=reg.get("candidates",{})
    need(type(candidates) is dict and len(candidates)==6 and {"324","348"}.issubset(candidates),"six registered candidate checkpoint pins required")
    for cand in candidates.values():
        _same_file(cand["checkpoint_path"],cand["checkpoint_sha256"],"checkpoint")
        _same_file(cand["source_receipt_path"],cand["source_receipt_sha256"],"checkpoint source receipt")
    for item in reg.get("review_records",[]):
        if item.get("kind")=="confirmation_statistics_adapter": continue
        _same_file(item["path"],item["sha256"],"review record")
    refs=[x for x in reg.get("review_records",[]) if x.get("kind")=="confirmation_statistics_adapter"]
    prov=reg.get("provenance",{}).get("statistics",{})
    choices=[(x["path"],x["sha256"]) for x in refs]+([(prov["adapter_path"],prov["adapter_sha256"])] if prov.get("adapter_path") else [])
    need(bool(choices) and all(a==choices[0] for a in choices),"statistics adapter pins absent or disagree")
    _same_file(*choices[0],"statistics adapter")
    exe=next((x for x in reg.get("review_records",[]) if x.get("kind")=="runtime_executable"),None)
    need(exe is not None,"runtime executable pin missing")
    _same_file(exe["path"],exe["sha256"],"runtime executable")
    bench=reg.get("benchmark_measurement",{})
    _same_file(bench["receipt_path"],bench["receipt_sha256"],"accepted benchmark receipt")
    wrapper=read_json(bench["receipt_path"])
    need(wrapper.get("schema")=="expanded_eval_accepted_benchmark_evidence_v1" and wrapper.get("complete") is True,"accepted benchmark wrapper invalid")
    _same_file(wrapper["worker_receipt_path"],wrapper["worker_receipt_sha256"],"benchmark worker receipt")
    _same_file(wrapper["outer_receipt_path"],wrapper["outer_receipt_sha256"],"benchmark outer receipt")
    bout=read_json(wrapper["outer_receipt_path"])
    need(bout.get("raw_exit_code")==0 and bout.get("stop_reason") is None and bout.get("process_group_absent") is True,"benchmark outer postflight failed")

def audit(registration_path, externally_pinned_registration_sha256, raw_supervisor_exit, output_dir_for_new_parent_receipts, *, ps_runner=_ps, clock=time.monotonic):
    need(type(raw_supervisor_exit) is int and raw_supervisor_exit==0,"raw supervisor exit must be integer zero")
    regpath=Path(registration_path); rawreg=regpath.read_bytes(); need(sha(rawreg)==externally_pinned_registration_sha256,"registration external SHA mismatch")
    reg=json.loads(rawreg); need(reg.get("schema")=="expanded_D2_evaluation_registration_v1" and reg.get("mode")=="confirmation","registration schema/mode mismatch")
    need(reg.get("run_id"),"registration must bind confirmation stage/run")
    outer_limit=reg["limits"]["outer_seconds"]
    outdir=Path(reg["output_dir"]); summary=outdir/"confirmation.json"; outerpath=outdir/"confirmation.json.outer-receipt.json"
    outer=json.loads(outerpath.read_bytes())
    need(outer.get("schema")=="expanded_eval_outer_receipt_v1" and outer.get("run_id")==reg["run_id"] and outer.get("registration_sha256")==externally_pinned_registration_sha256,"outer receipt identity mismatch")
    need(type(outer.get("raw_exit_code")) is int and outer["raw_exit_code"]==0 and outer.get("stop_reason") is None,"outer receipt supervisor/worker exit or stop invalid")
    need(type(outer.get("elapsed_seconds")) in (int,float) and math.isfinite(outer["elapsed_seconds"]) and 0<=outer["elapsed_seconds"]<=outer_limit,"outer wall outside registered limit")
    need(outer.get("stage")=="confirmation" and outer.get("candidate_update")==324 and outer.get("cohort")=="confirmation" and outer.get("process_group_absent") is True and outer.get("process_group_remaining")==[],"outer stage/candidate/cohort/process mismatch")
    artifacts=outer.get("output_artifacts"); need(type(artifacts) is list,"outer artifact list missing")
    need(all(type(a) is dict for a in artifacts) and len({a.get("path") for a in artifacts})==len(artifacts),"duplicate or malformed outer artifact")
    required={str(summary),str(outdir/"confirmation-winner.json"),str(outdir/"confirmation-incumbent-348.json")}
    need(required.issubset({a.get("path") for a in artifacts}),"outer receipt lacks required outcome bindings")
    for a in artifacts:
        path=Path(a["path"]); b=path.read_bytes(); need(sha(b)==a.get("sha256") and len(b)==a.get("bytes"),"outer output artifact binding mismatch")
    need(outer.get("evaluator_sha256")==reg["source"]["evaluator_sha256"] and outer.get("worker_sha256")==reg["source"]["worker_sha256"],"outer worker source pin mismatch")
    marker=Path(reg["one_shot_marker"]); m=json.loads(marker.read_bytes())
    need(m.get("run_id")==reg["run_id"] and m.get("registration_sha256")==externally_pinned_registration_sha256 and type(m.get("pid")) is int,"one-shot marker identity/state mismatch")
    hbpath=outdir/"worker-heartbeat.json"; hb=json.loads(hbpath.read_bytes())
    need(hb.get("run_id")==reg["run_id"] and hb.get("registration_sha256")==externally_pinned_registration_sha256,"final heartbeat identity mismatch")
    need(type(hb.get("rss_bytes")) is int and 0<hb["rss_bytes"]<=6*1024**3 and type(hb.get("mps_driver_bytes")) is int and 0<hb["mps_driver_bytes"]<=6*1024**3,"final RSS/MPS caps invalid")
    need(hb.get("phase")=="runtime" and hb.get("driver_initialized") is True,"final runtime heartbeat phase invalid")
    need(m.get("pid") != hb.get("pid"),"supervisor and worker PIDs must differ")
    for pid in (m.get("pid"),hb.get("pid")):
        need(type(pid) is int and pid>1 and not _process_rows(pid,ps_runner),"registered process remains in ps")
    need(not Path(reg["cancel_path"]).exists(),"cancellation file exists")
    cache=Path(reg["runtime"]["pycache_prefix"]); need(cache.is_dir() and not any(cache.iterdir()),"registered empty cache missing or nonempty")
    state=read_json(reg["state_path"]); need(state.get("active_inference_diagnostic")==reg["expected_lease"],"expected lease differs")
    need(all(state.get(k) in (None,False) for k in ("active_long_campaign","active_long","active_inference")),"conflicting legacy lease")
    readme=reg.get("provenance",{}).get("root_readme",{}); rootread=Path(readme["path"]); need(sha(rootread.read_bytes())==readme["sha256"]=="be478416b33c772a7ff9c28f2c974f767c205f7df77bcf7346ab36133d384652","root README pin mismatch")
    _all_registered_pins(reg)
    # Quality payloads are deliberately unopened until lifecycle and integrity gates above pass.
    bundle=json.loads(summary.read_bytes()); need(bundle.get("schema")=="expanded_D2_stage_bundle_v1" and bundle.get("stage")=="confirmation","bundle schema/stage mismatch")
    results=bundle.get("results"); need(type(results) is list and [x.get("candidate_update") for x in results]==[324,348],"bundle result order mismatch")
    result_paths=[outdir/"confirmation-winner.json",outdir/"confirmation-incumbent-348.json"]
    raws=[p.read_bytes() for p in result_paths]
    need(sum(row.get("gameplay_frames",0) for result in results for row in result.get("rows",[]))<=73728000,"campaign raw gameplay cap exceeded")
    for x,b in zip(results,raws):
        result=json.loads(b); need(x==result,"bundle differs from pinned result file")
        elapsed=result.get("elapsed_seconds"); need(type(elapsed) in (int,float) and math.isfinite(elapsed) and elapsed>0,"evaluator elapsed time invalid")
        need(sum(row.get("gameplay_frames",0) for row in result.get("rows",[]))<=73728000,"candidate raw gameplay cap exceeded")
    summarybind=next((a for a in artifacts if a.get("path")==str(summary)),None); need(summarybind and summarybind["sha256"]==sha(summary.read_bytes()),"bundle outer binding mismatch")
    # Adapter is loaded from one pinned buffer; no neighboring imports.
    apath,apin=next((x["path"],x["sha256"]) for x in reg.get("review_records",[]) if x.get("kind")=="confirmation_statistics_adapter")
    adapter_bytes=Path(apath).read_bytes(); need(sha(adapter_bytes)==apin,"adapter changed after source gate")
    import types
    mod=types.ModuleType("pinned_confirmation_adapter"); exec(compile(adapter_bytes,apath,"exec"),mod.__dict__)
    audit_obj={"schema":"parent_expanded_confirmation_terminal_audit_v1","status":"accepted_confirmation_evidence_only_no_promotion","run_id":reg["run_id"],"registration_sha256":externally_pinned_registration_sha256,"raw_supervisor_exit":0,"raw_worker_exit":0,"process_group_absent":True,"promotion":False,"output_artifacts":[{"path":str(p.resolve()),"sha256":sha(b)} for p,b in zip(result_paths,raws)]}
    audit_raw=json.dumps(audit_obj,sort_keys=True,separators=(",",":")).encode()
    stats=mod.analyze(registration_bytes=rawreg,registration_sha256=externally_pinned_registration_sha256,selection_bytes=Path(reg["selection_record"]["path"]).read_bytes(),selection_sha256=reg["selection_record"]["sha256"],audit_bytes=audit_raw,audit_sha256=sha(audit_raw),winner_bytes=raws[0],winner_sha256=sha(raws[0]),winner_path=str(result_paths[0].resolve()),incumbent_bytes=raws[1],incumbent_sha256=sha(raws[1]),incumbent_path=str(result_paths[1].resolve()))
    need(stats.get("winner_update")==324 and stats.get("incumbent_update")==348,"adapter candidate identity mismatch")
    for obj,key in zip(results,("winner","incumbent_348")):
        declared=obj.get("performance"); got=stats[key]
        need(type(declared) is dict and all(declared.get(k)==got[k] for k in ("worst","q1_bottom_quarter_mean","mean","q4_top_quarter_mean","best")),"declared performance differs from recomputation")
    dest=Path(output_dir_for_new_parent_receipts); need(not dest.exists(),"parent receipt directory already exists"); dest.mkdir(parents=True,exist_ok=False)
    audit_path=dest/"audit.json"; stats_path=dest/"statistics.json"
    audit_path.write_bytes(audit_raw); stats_raw=json.dumps(stats,sort_keys=True,indent=2).encode()+b"\n"; stats_path.write_bytes(stats_raw)
    receipt={"schema":"confirmation_terminal_auditor_receipt_v1","run_id":reg["run_id"],"registration_sha256":externally_pinned_registration_sha256,"audit_sha256":sha(audit_raw),"statistics_sha256":sha(stats_raw),"eligibility":stats["eligibility"],"promotion":False}
    (dest/"receipt.json").write_text(json.dumps(receipt,sort_keys=True,indent=2)+"\n")
    return receipt
