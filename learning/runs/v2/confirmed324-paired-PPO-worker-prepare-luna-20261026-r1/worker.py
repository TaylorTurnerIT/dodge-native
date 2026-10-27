"""Prepared paired PPO worker. Import safe: no project, Torch, MPS, or game imports."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
STUDY="paired-lr-confirmed324-20261026-r1"
ARMS=("A_constant_3e-5","B_linear_3e-5_to_1e-5_over_60")
PARENT={"checkpoint_sha256":"c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc","cumulative_update":372,"phase_update":324,"receipt_sha256":"76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08","acceptance_sha256":"3e84979c4c8da76d0f98666a23f90eb15c1e813ca5edf1001e19daebaf4d5bbd"}
R5_SOURCE="learning/runs/v2/confirmed324-private-bindings-repair-luna-20261026-r5"
R5_PINS={"attempt_claim.py":"bf993c076c6c3270a3efb89f42d3ca86a070a044da286b42b4803790c3759206","driver_binding.py":"aba05ce927a32fd01c07256d9d798a82bf4a9ff74e4dd0eacbf7de337e055abd","fingerprints.py":"6ef9cf3f08fe800f54230801a921a2f5c82e47e5013ef3087ead6499d2533d61","rng_reference.py":"9abfb7f892fc3a0b62d665a390effcfd7cbf4161ccf1ade3a9240d9392172917","transition.py":"bda044d213db3424a3b578c7c63cb30d942e9c8e5527c1e854abe03abcf83e03"}
VECTOR_SHA="33ada951394fd3ce674955d43de1919b1cd3c2192e066722e33d5b49549c070b"
BASELINE_RUNNER_SHA="108ba55ad78aa26166acb14f67cc6466da6293ccee3d272e1fe6e775ebf2ac60"
PPO_CONTRACT={"gamma":0.995,"gae_lambda":0.95,"adam_eps":0.00001,"clip_coef":0.2,"vf_coef":0.5,"ent_coef":0.01,"max_grad_norm":0.5,"update_epochs":4,"minibatch_size":512,"batch_size":16384,"reward_scale":0.1}
REFERENCE_FIELDS={"constructor_init_seed","python_random_seed","numpy_global_seed","torch_cpu_global_seed","action_sampler_torch_mps_seed","env_master_seed"}
EXCLUSIONS=((2952790016,2952791015),(3489660928,3489661055),(3758096384,3758097383),(3506438144,3506439167),(3523215360,3523217407))
def digest_file(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""): h.update(b)
 return h.hexdigest()
def lr_for(arm,cumulative_update):
 if arm not in ARMS or type(cumulative_update) is not int or not 373<=cumulative_update<=432: raise ValueError("invalid arm or cumulative update")
 return 3e-5 if arm==ARMS[0] else 3e-5+(1e-5-3e-5)*(cumulative_update-373)/59
def verify_registration(reg,root):
 if not isinstance(reg,dict) or reg.get("schema")!="paired_confirmed324_registration_v1" or reg.get("status")!="parent_review_required_not_launchable": raise ValueError("wrong or launchable registration")
 if reg.get("parent")!=PARENT or reg.get("study_id")!=STUDY: raise ValueError("parent or study identity mismatch")
 arm,replica=reg.get("arm"),reg.get("replica")
 if arm not in ARMS or type(replica) is not int or replica not in (1,2,3): raise ValueError("invalid replica or arm")
 refs=reg.get("measured_references")
 if not isinstance(refs,dict) or refs.get("status")!="measured_accepted" or refs.get("parent_checkpoint_sha256")!=PARENT["checkpoint_sha256"] or refs.get("fields")!=sorted(REFERENCE_FIELDS): raise ValueError("measured RNG references missing or unaccepted")
 vectors=reg.get("vectors"); v=vectors.get(str(replica)) if isinstance(vectors,dict) else None
 if not isinstance(v,dict) or v.get("vector_sha256")!=reg.get("vector_sha256"): raise ValueError("registered seed vector missing")
 seeds=v.get("seeds")
 if not isinstance(seeds,dict) or set(seeds)!=REFERENCE_FIELDS: raise ValueError("seed vector fields differ")
 canonical=json.dumps({"study_id":STUDY,"replica":replica,"seeds":seeds},sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()
 if hashlib.sha256(canonical).hexdigest()!=v.get("vector_sha256"): raise ValueError("seed vector content hash mismatch")
 if reg.get("exclusion_union")!=[list(x) for x in EXCLUSIONS]: raise ValueError("exclusion union differs")
 idx=v.get("env_control",{}).get("episode_indices")
 if not isinstance(idx,list) or len(idx)!=64 or idx!=reg.get("initial_episode_indices"): raise ValueError("confirmed324 initial episode indices differ")
 try: canonical_vectors=__import__("json").loads((Path(root)/"learning/runs/v2/confirmed324-seed-vectors-parent-20261026-r1/seed-vectors.json").read_text())["vectors"]
 except Exception as exc: raise ValueError("pinned vector source unreadable") from exc
 pinned=next((x for x in canonical_vectors if x.get("replica")==replica),None)
 if pinned!=v: raise ValueError("registered vector differs from pinned proposal")
 if type(reg.get("pair_id")) is not str or not reg["pair_id"]: raise ValueError("pair identity required")
 claim_path=Path(reg.get("attempt_claim_path",""))
 if not claim_path.is_absolute(): raise ValueError("registered absolute attempt claim path required")
 if reg.get("source_pins")!=R5_PINS: raise ValueError("R5 source pins differ")
 vector_path=Path(root)/"learning/runs/v2/confirmed324-seed-vectors-parent-20261026-r1/seed-vectors.json"
 if not vector_path.is_file() or digest_file(vector_path)!=VECTOR_SHA: raise ValueError("confirmed324 seed-vector source pin mismatch")
 baseline=Path(root)/"learning/runs/v2/D2-retained300-continuation-freeze-20261026-r5/runner.py"
 if not baseline.is_file() or digest_file(baseline)!=BASELINE_RUNNER_SHA: raise ValueError("accepted baseline runner pin mismatch")
 for name,sha in R5_PINS.items():
  path=Path(root)/R5_SOURCE/name
  if not path.is_file() or digest_file(path)!=sha: raise ValueError("R5 source pin mismatch: "+name)
 return arm,replica,seeds,v
def prepare_run(reg,root,api,callbacks,claim,env_factory,output,*,max_updates=60):
 arm,replica,seeds,vector=verify_registration(reg,root)
 if max_updates!=60: raise ValueError("registered update bound is exactly 60")
 receipt_path=Path(reg["measured_references"].get("receipt_path","")); receipt_sha=reg["measured_references"].get("receipt_sha256")
 if not receipt_path.is_absolute() or type(receipt_sha) is not str or len(receipt_sha)!=64 or not receipt_path.is_file() or digest_file(receipt_path)!=receipt_sha: raise ValueError("measured-reference receipt pin missing or changed")
 refs=reg["measured_references"].get("replicas",{}).get(str(replica))
 if not isinstance(refs,dict) or set(refs)!=REFERENCE_FIELDS or any(type(x) is not str or len(x)!=64 or any(c not in "0123456789abcdef" for c in x) for x in refs.values()): raise ValueError("replica measured references incomplete")
 if reg.get("schedule")!={"updates":60,"cumulative_origin":372,"cumulative_first":373,"cumulative_last":432,"phase_start":325,"phase_end":384,"candidate_local_updates":[12,24,36,48,60],"candidate_cumulative_updates":[384,396,408,420,432],"candidate_phase_updates":[336,348,360,372,384]}: raise ValueError("registered counter schedule differs")
 if reg.get("ppo")!=PPO_CONTRACT: raise ValueError("preserved PPO controls differ")
 api.event("pins_verified")
 api.seed_initialization(seeds["constructor_init_seed"])
 model,optimizer=api.construct_model_adam(); api.event("model_adam_constructed")
 cap=callbacks.capture_rng
 raw=cap()
 if not isinstance(raw,dict) or set(raw)!={"python","numpy_global","numpy_generator","torch_cpu","torch_mps","sampling_backend"}: raise ValueError("raw six-key RNG capture required")
 api.event("raw_six_key_capture")
 callbacks.restore_trusted(model,optimizer)
 restored=api.fingerprints(model,optimizer,cap())
 if restored!=reg["expected_parent_fingerprints"]: raise ValueError("restored parent fingerprints differ")
 transition=callbacks.transition(model=model,optimizer=optimizer,seeds=seeds,reference=refs,arm=arm,replica=replica,reg=reg,claim=claim,api=api)
 if transition.get("status")!="transition_complete": raise ValueError("verified transition did not complete")
 api.event("transition_complete")
 indices=vector["env_control"]["episode_indices"]
 env=env_factory(master_seed=seeds["env_master_seed"],exclusions=EXCLUSIONS,initial_episode_indices=indices); api.event("environment_constructed")
 for local in range(1,61):
  cumulative=372+local; api.set_learning_rate(optimizer,lr_for(arm,cumulative))
  result=api.complete_ppo_update(model,optimizer,env,local_update=local,cumulative_update=cumulative,phase_update=324+local,episode_indices=indices)
  if not isinstance(result,dict) or result.get("complete") is not True: raise ValueError("incomplete PPO update")
  api.journal_update(local,cumulative,324+local,result)
  if local in (12,24,36,48,60): api.save_complete_candidate(output,local,cumulative,324+local,model,optimizer,cap(),result)
 api.finish_without_promotion(output,arm=arm,replica=replica,cumulative_update=432,phase_update=384)
 return {"status":"completed_adapter_execution","updates":60,"arm":arm,"replica":replica}
