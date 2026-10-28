"""Fail-closed terminal audit for full-game seed-priority training receipts; stdlib only."""
from __future__ import annotations
import json
import hashlib
from pathlib import Path
from seed_priority import validate_pool

BINS=((0,1000),(1000,2000),(2000,4000),(4000,8000),(8000,12000),(12000,18000))

def need(value,message):
    if not value: raise ValueError(message)

def _rows(path,strict=False):
    if not Path(path).is_file(): return
    with Path(path).open() as f:
        for line in f:
            if not line.endswith("\n"):
                need(not strict,"torn training event journal"); break
            yield json.loads(line)

def accounting(out,worker,*,strict=False):
    reg=worker.get("registration",worker)
    pool_path=reg.get("training_pool_path",worker.get("training_pool_path"))
    need(type(pool_path)is str,"worker receipt lacks frozen training pool path")
    pool_doc=json.loads(Path(pool_path).read_text())
    pool=validate_pool(pool_doc)["all"]
    seeds=set(pool); episodes=[]; assignments=0; events=0; decisions=0; raw_frames=0
    bins={f"{lo}-{hi}":0 for lo,hi in BINS}; components={"uniform":0,"uniform_floor":0,"hard_priority":0}; strata={"hard":0,"easy":0}
    strata_by_seed={row["seed"]:row["stratum"] for row in pool_doc["seeds"]}
    for event in _rows(Path(out)/"training-events.jsonl",strict=strict):
        events+=1
        if event.get("kind")=="returned_step_cost":
            decisions+=1; raw_frames+=sum(event["elapsed_raw_frames"])
        if event.get("kind")=="initial":
            initial=event.get("assignments",[]); assignments+=len(initial)
            for row in initial:
                components[row["sampling_component"]]+=1; strata[row["stratum"]]+=1
        if event.get("kind")=="seeded_reset":
            rows=event.get("assignments",[]); assignments+=len(rows)
            for row in rows:
                components[row["sampling_component"]]+=1; strata[row["stratum"]]+=1
        if event.get("kind")=="collection_complete_before_PPO":
            for row in event.get("completed",[]):
                seed=row.get("seed",{}); actual=seed.get("actual_seed")
                need(seed.get("evaluation") is True and actual in seeds,
                     "completed native seed lacks training-only pool provenance")
                frames=row.get("gameplay_frames")
                need(type(frames)is int and 0<=frames<=18000,"completed full-game frame count invalid")
                episodes.append(row)
                seed_value=seed["actual_seed"]
                need(row.get("sampling_component") in components and row.get("stratum")==strata_by_seed.get(seed_value),
                     "completed episode priority provenance differs")
                for lo,hi in BINS:
                    bins[f"{lo}-{hi}"]+=max(0,min(frames,hi)-lo)
    # In-flight frames are reported separately by final native snapshot and never discarded.
    in_flight=worker.get("final_snapshot",{}).get("current_episode_info",[])
    for row in in_flight:
        seed=row.get("seed",{}); need(seed.get("evaluation") is True and seed.get("actual_seed") in seeds,
                                     "in-flight native seed lacks pool provenance")
        frames=row.get("gameplay_frames")
        need(type(frames)is int and 0<=frames<=18000,"in-flight raw gameplay count invalid")
        for lo,hi in BINS: bins[f"{lo}-{hi}"]+=max(0,min(frames,hi)-lo)
        episode=seed["episode"]; slot=seed["slot"]
        # Final snapshot includes only current native seeds; pool provenance is direct.
        need(seed["actual_seed"] in seeds,"in-flight seed outside accepted pool")
    age_frames=sum(bins.values())
    snapshot=worker.get("final_snapshot",{})
    environment=snapshot.get("environment",snapshot)
    initial_startup=environment.get("initial_startup_frames")
    reset_startup=environment.get("returned_reset_startup_frames")
    reset_count=environment.get("reset_count")
    need(initial_startup==13*64,"constructor startup accounting differs from 13*64")
    need(type(reset_count)is int and reset_count>=0 and reset_startup==13*reset_count,
         "reset startup accounting differs from 13*actual_resets")
    need(age_frames==raw_frames,"age-binned gameplay frames differ from returned native raw frames")
    need(environment.get("observed_native_frames")==raw_frames,
         "adapter native-frame counter differs from event journal")
    need(environment.get("gameplay_frames")==age_frames,
         "adapter gameplay counter differs from age-binned episode totals")
    need(environment.get("initial_startup_frames")+environment.get("reset_startup_frames")
         ==13*(64+reset_count),"constructor/reset startup total differs from 13*(64+actualresets)")
    return {"events":events,"completed_episodes":len(episodes),"seed_assignments":assignments,
            "unique_training_pool_seeds_used":len({x["seed"]["actual_seed"] for x in episodes}),
            "assignment_component_counts":components,"assignment_stratum_counts":strata,
            "completed_episode_rows":episodes,"age_binned_gameplay_frames":bins,
            "age_binned_gameplay_frame_total":age_frames,
            "in_flight_episode_count":len(in_flight),"returned_native_decisions":decisions,
            "returned_native_raw_frames":raw_frames,"sampling_with_replacement":True}

def validate_outputs(reg,worker,registration_sha256):
    need(worker.get("run_id")==reg["run_id"] and worker.get("registration_sha256")==registration_sha256,
         "worker run/registration identity differs")
    need(worker.get("status")=="completed" and worker.get("updates")==60,
         "training did not complete exact global update60 endpoint")
    need(worker.get("training_eligible") is False and worker.get("promoted") is False
         and worker.get("automatic_selection") is False,"training result carries selection authority")
    data=accounting(Path(reg["output"]),{"registration":reg,"final_snapshot":worker.get("final_snapshot",{})},strict=True)
    need(data["returned_native_decisions"]==60*256,"returned native decision count differs")
    counters=worker.get("counters",{})
    need(counters.get("updates")==60 and counters.get("environment_decisions")==983040,
         "registered PPO transition budget differs")
    need(counters.get("raw_frames")==data["returned_native_raw_frames"],
         "worker raw-frame counter differs from returned native costs")
    metrics=list(_rows(Path(reg["output"])/"training-metrics.jsonl",strict=True) or ())
    need(len(metrics)==60 and metrics[-1].get("global_update")==60,
         "exact global60 metrics endpoint missing")
    need(metrics[-1].get("counters")==counters,"terminal metrics counters differ from worker receipt")
    checkpoints=worker.get("integrity_checkpoints",[])
    need(checkpoints and checkpoints[-1].get("global_update")==60
         and checkpoints[-1].get("formal_comparison_endpoint") is True,
         "global60 integrity checkpoint boundary missing")
    checkpoint=Path(checkpoints[-1]["path"])
    need(checkpoint.is_file() and __import__("hashlib").sha256(checkpoint.read_bytes()).hexdigest()==checkpoints[-1].get("sha256"),
         "global60 integrity checkpoint hash differs")
    sidecar=Path(str(checkpoint)+".json")
    need(sidecar.is_file(),"global60 checkpoint receipt missing")
    receipt=json.loads(sidecar.read_text())
    identity=receipt.get("identity")
    identity_hash=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(",",":"),
        ensure_ascii=True,allow_nan=False).encode("ascii")).hexdigest() if isinstance(identity,dict) else None
    need(isinstance(identity,dict) and receipt.get("sha256")==checkpoints[-1]["sha256"]
         and receipt.get("identity_sha256")==identity_hash
         and identity.get("run_id")==reg["run_id"] and identity.get("arm")==reg["arm"]
         and identity.get("replica")==reg["replica"]
         and identity.get("training_pool_sha256")==reg["training_pool_sha256"]
         and identity.get("source_manifest_sha256")==reg["source_manifest_sha256"]
         and identity.get("runtime_manifest_sha256")==reg["runtime_manifest_sha256"]
         and receipt.get("global_update")==60 and receipt.get("phase_update")==384
         and receipt.get("cumulative_update")==432
         and receipt.get("parent_checkpoint_sha256")==reg["parent_checkpoint_sha256"],
         "global60 checkpoint identity/update/parent boundary differs")
    return {"terminal_update":60,"comparison_endpoint":True,"training_eligible":False,
            "promoted":False,"automatic_selection":False,"accounting":{k:v for k,v in data.items() if k!="completed_episode_rows"}}
