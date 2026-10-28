"""Pure-stdlib proposed six-key RNG vectors; no runtime, model, or environment imports."""
import hashlib, json
STUDY_ID="fullgame-seed-priority-luna-20261027-r1"
DOMAIN="D2-LAYERB-RNG-VECTOR-V1"
SCHEMA="d2_layerb_proposed_rng_seed_vectors_v3"
PARENT_CHECKPOINT_SHA256="c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc"
PARENT_RECEIPT_SHA256="76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08"
BOUNDS={"constructor_init_seed":(1,2**32-1,4),"python_random_seed":(1,2**63-1,8),
"numpy_global_seed":(0,2**32-1,4),"torch_cpu_global_seed":(1,2**63-1,8),
"action_sampler_torch_mps_seed":(1,2**63-1,8),"env_master_seed":(1,2**64-1,8)}
PRIOR_MASTERS={810631976,3192039780,3791628417,4200000000,4200000001,5562881586070242562}
RESERVED=((0xB0000000,0xB00003E7),(0xD0000000,0xD000007F),(0xE0000000,0xE00003E7),
          (0xD1000000,0xD10003FF),(0xD2000000,0xD20007FF),(0xD3000000,0xD30003FF))
def canonical(v): return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode()
def token(replica,stream,attempt): return hashlib.sha256(f"{DOMAIN}|study={STUDY_ID}|replica={replica}|stream={stream}|attempt={attempt}".encode()).digest()
def reserved(v): return any(lo<=v<=hi for lo,hi in RESERVED)
def derive(replica,stream):
    lo,hi,width=BOUNDS[stream]
    for attempt in range(1<<20):
        value=int.from_bytes(token(replica,stream,attempt)[:width],"big")
        if stream in ("constructor_init_seed","numpy_global_seed"): value &= 0xffffffff
        if lo<=value<=hi and not (stream=="env_master_seed" and (reserved(value) or value in PRIOR_MASTERS)):
            return value,attempt
    raise RuntimeError("seed derivation exhausted")
PARENT_NEXT_EPISODE_INDICES=[268, 277, 270, 278, 292, 268, 293, 285, 309, 285, 289, 291, 272, 291, 286, 289, 296, 292, 285, 267, 288, 280, 266, 287, 270, 297, 285, 285, 264, 272, 279, 288, 290, 291, 295, 273, 273, 278, 284, 277, 289, 293, 280, 273, 277, 281, 264, 292, 293, 273, 280, 297, 286, 287, 281, 294, 282, 284, 292, 288, 261, 290, 275, 311]

def build():
    rows=[]
    for replica in (1,2,3):
        seeds={}; attempts={}
        for stream in BOUNDS:
            seeds[stream],attempts[stream]=derive(replica,stream)
        digest=hashlib.sha256(canonical({"study_id":STUDY_ID,"replica":replica,"seeds":seeds})).hexdigest()
        rows.append({"replica":replica,"seeds":seeds,"attempts":attempts,"vector_sha256":digest})
    for field in BOUNDS:
        assert len({r["seeds"][field] for r in rows})==3
    return {"schema":SCHEMA,"status":"proposed_only_not_reserved_not_applied","study_id":STUDY_ID,
      "parent_checkpoint_sha256":PARENT_CHECKPOINT_SHA256,"parent_receipt_sha256":PARENT_RECEIPT_SHA256,"parent_next_episode_indices":PARENT_NEXT_EPISODE_INDICES,
      "domain":DOMAIN,"derivation":"SHA256(domain|study|replica|stream|attempt), first4/8 bytes, reject bounds and prior master seeds",
      "vectors":rows,"launch_authority":False}
if __name__=="__main__": print(json.dumps(build(),indent=2,sort_keys=True))
