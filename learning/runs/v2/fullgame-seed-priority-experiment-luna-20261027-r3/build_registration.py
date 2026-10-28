"""Build six inert registration drafts from parent-accepted pool/cohort/RNG inputs."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from seed_priority import validate_pool, sequence_entries, stream_digest, inclusion_probabilities, EPISODES_PER_SLOT
from seed_vectors import STUDY_ID, build as build_vectors
from contracts import PAIR_DIFF_FIELDS

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
ARMS=("uniform","opening_priority")
REGISTRY_DEFAULT=ROOT/"learning/runs/v2/rl-next-experiments-parent-20261027-r1/seed-priority-parent-registry.json"
REF_ROOT=ROOT/"learning/runs/v2/fullgame-priority-rng-reference-parent-20261027-r1"

def read(path):return json.loads(Path(path).read_text())
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,obj):Path(path).write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def build(registry_path,output_dir):
    registry_path=Path(registry_path).resolve(); registry=read(registry_path)
    if registry.get("schema")!="dodge_seed_priority_parent_registry_v1" or registry.get("freshness_accepted") is not True or registry.get("launch_authority") is not False:
        raise ValueError("parent accepted pool and fresh cohorts required; registry grants no launch authority")
    pool_path=Path(registry["training_pool_path"]).resolve(); pool_doc=read(pool_path); pool=validate_pool(pool_doc)
    if digest(pool_path)!=registry["training_pool_file_sha256"] or pool["pool_sha256"]!=registry["pool_sha256"]:
        raise ValueError("accepted training pool file/semantic hash differs")
    if registry.get("future_evaluation_cohorts")!=["D4","D5"] or registry.get("future_evaluation_counts")!={"D4":1024,"D5":2048}:
        raise ValueError("fresh D4 evaluation and D5 confirmation cohorts differ")
    vectors=build_vectors(); starts=vectors["parent_next_episode_indices"]
    contracts=read(HERE/"shared-config.json")
    old=read(ROOT/"learning/runs/v2/progressive1000-monitored-comparison-parent-20261027-r1/progressive1000-confirmed324-20261026-r1-replica-1-control_constant_3e-5/registration-final.json")
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=False)
    (HERE/"attempts").mkdir(exist_ok=True);(HERE/"worker-output").mkdir(exist_ok=True)
    source_sha=digest(HERE/"source-manifest.json");runtime_sha=digest(HERE/"runtime-manifest.json")
    input_sha=digest(HERE/"input-manifest.json")
    with (out/"draft-index.json").open("w") as f:json.dump({"study_id":STUDY_ID,"launch_authority":False,"parent_registry_path":str(registry_path),"parent_registry_sha256":digest(registry_path),"training_pool_path":str(pool_path),"training_pool_file_sha256":digest(pool_path),"training_pool_sha256":pool["pool_sha256"],"future_cohorts":["D4","D5"],"drafts":[]},f,sort_keys=True,indent=2)
    index=read(out/"draft-index.json")
    for vector in vectors["vectors"]:
        replica=vector["replica"]
        for arm in ARMS:
            seed_hashes=[];component_hashes=[]
            for slot,start in enumerate(starts):
                entries=sequence_entries(pool,study_id=STUDY_ID,replica=replica,
                    env_master_seed=vector["seeds"]["env_master_seed"],arm=arm,slot=slot,
                    count=start+EPISODES_PER_SLOT)
                seed_hashes.append(stream_digest([seed for seed,_ in entries]))
                component_hashes.append(stream_digest([component for _,component in entries]))
            run_id=f"{STUDY_ID}-replica-{replica}-{arm}"
            ref=REF_ROOT/"outputs"/f"replica-{replica}.json";approval=REF_ROOT/f"reference-approval-replica-{replica}.json"
            reg={"schema":"dodge_seed_priority_registration_v1","status":"inert_template_NO_LAUNCH",
                "study_id":STUDY_ID,"run_id":run_id,"pair_id":f"{STUDY_ID}-replica-{replica}",
                "replica":replica,"arm":arm,"backend":"mps","purpose":"matched_comparison",
                "vector":vector,"reference":{"receipt_path":str(ref),"receipt_sha256":digest(ref),"vector_sha256":vector["vector_sha256"]},
                "reference_approval":{"path":str(approval),"sha256":digest(approval)},
                "initial_episode_indices":starts,"exclusion_union":registry["exclusion_union"],
                "training_pool_path":str(pool_path),"training_pool_file_sha256":digest(pool_path),
                "training_pool_sha256":pool["pool_sha256"],"episodes_per_slot":EPISODES_PER_SLOT,
                "slot_stream_sha256":seed_hashes,"slot_component_sha256":component_hashes,
                "parent_registry_path":str(registry_path),"parent_registry_sha256":digest(registry_path),
                "parent_checkpoint_sha256":vectors["parent_checkpoint_sha256"],
                "parent_receipt_sha256":vectors["parent_receipt_sha256"],
                "expected_parent_fingerprints":{"model":"3b72815fef4d8fa0084044739f5a5eaf9f74971b36dff9d8b26ed3bea5c562bc","Adam":"cf5e2a7ac5d3f7f131a26f7c2b8b778b7692850cff606a0ea9080941b960451c","RNG":"cb96ee8d2c40114a51abb8031dc7457a6da6d1be7262c6a4859bd34cab5813af"},
                "runtime_root":str(HERE/"runtime"),"runtime_versions":old["runtime_versions"],
                "source_manifest_sha256":source_sha,"runtime_manifest_sha256":runtime_sha,"input_manifest_sha256":input_sha,
                "shared_config":contracts,"ppo":contracts["ppo"],
                "schedule":{"updates":60,"cumulative_origin":372,"cumulative_first":373,"cumulative_last":432,
                    "phase_start":325,"phase_end":384,"integrity_local_updates":[12,24,36,48,60],
                    "formal_evaluation_local_updates":[60],"candidate_selection":False,"promotion":False,"final_drain":False},
                "training_pool_role":"training_only","native_seed_mode":{"mode":"evaluation","meaning":"explicit_seed_list"},
                "native_seed_evaluation_flag_expected":True,
                "priority":{"uniform_floor":0.5,"hard_component":0.5,"sampling_probability":inclusion_probabilities(pool),
                    "frozen_labels":True,"online_refresh":False,"stale_transition_replay":False},
                "future_evaluation_cohorts":["D4","D5"],"cohort_state":"reserved_parent_approved",
                "history_state":"freshness_parent_approved","reservation_state":"parent_reserved",
                "output":str(HERE/"worker-output"/run_id),"attempt_claim_path":str(HERE/"attempts"/(run_id+".claimed")),
                "launch_marker_path":str(HERE/"launch-markers"/(run_id+".json")),
                "interpreter":old["interpreter"],"import_policy":{"dont_write_bytecode":True,"pycache_prefix":str(HERE/"empty-pycache")},
                "state_path":str(ROOT/"learning/runs/v2-orchestration/state.json"),"expected_lease":None,
                "limits":{"work_seconds":3780,"total_seconds":3790,"cleanup_seconds":10,
                    "rss_bytes":6*1024**3,"mps_bytes":6*1024**3,"raw_frames":16712512,"resets":983040,"retries":0},
                "launch_authority":False,"pending_parent_fields":["expected_lease","launch_marker_path","source acceptance","exact output path"],
                "same_pool_uniform_control":True,"matched_pair_differences":list(PAIR_DIFF_FIELDS)}
            path=out/f"replica-{replica}-{arm}.json";write(path,reg)
            index["drafts"].append({"path":str(path),"sha256":digest(path),"run_id":run_id,"replica":replica,"arm":arm})
    write(out/"draft-index.json",index)
    return {"path":str(out),"drafts":len(index["drafts"]),"launch_authority":False,
            "pool_sha256":pool["pool_sha256"],"parent_registry_sha256":digest(registry_path)}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--registry",default=str(REGISTRY_DEFAULT));p.add_argument("--output",default=str(HERE/"registrations"));a=p.parse_args()
    print(json.dumps(build(a.registry,a.output),sort_keys=True))
