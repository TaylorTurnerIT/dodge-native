"""Inert transition contract. Runtime, checkpoint, environment, and launch work stay external."""
from __future__ import annotations
from collections.abc import Mapping

EXPECTED_PARENT = {"model":"b106e8e1ef0645b357ae8877587e2668aa239435c845223dd9481b6fa3ad399f","Adam":"29108e8441b859f02e149b8e52e8cb9d36bbe8d739eef8a7435ab392be4c523e","RNG":"831d8fa20b4b9aca009382ccb69f9516336b83540850d86b5cdc53a07ba380ad"}
SEED_FIELDS=("constructor_init_seed","python_random_seed","numpy_global_seed","torch_cpu_global_seed","action_sampler_torch_mps_seed","env_master_seed")
U32_MAX,I63_MAX,U64_MAX=(1<<32)-1,(1<<63)-1,(1<<64)-1
REJECTED_MASTERS=frozenset({810631976,3192039780,3791628417,4200000000,4200000001,5562881586070242562})
EXPECTED_EXCLUSION_RANGES=tuple(sorted(((2952790016,2952791015),(3489660928,3489661055),(3758096384,3758097383),(3506438144,3506439167),(3523215360,3523217407))))
OLD_CONTROLLER_PROVENANCE={"origin":372,"horizon":60,"completed":24,"saved_lr":2.2203389830508474e-5}
ARMS={"A_constant_3e-5","B_linear_3e-5_to_1e-5_over_60"}
ACCEPTED_PARENT_RECEIPT_SHA256="cb3645899b5cb660d26d44645e00b3f53c5d0c8341b645b3b78af6b651d8b016"

class TransitionSession:
    """One attempt per process/run; mutable-phase failure consumes this session."""
    def __init__(self): self._started=False

def validate_seeds(seeds: Mapping[str,object]) -> None:
    if set(seeds)!=set(SEED_FIELDS): raise ValueError("seed vector must contain exactly six explicit fields")
    bounds={"constructor_init_seed":(1,U32_MAX),"numpy_global_seed":(0,U32_MAX),"python_random_seed":(1,I63_MAX),"torch_cpu_global_seed":(1,I63_MAX),"action_sampler_torch_mps_seed":(1,I63_MAX),"env_master_seed":(1,U64_MAX)}
    for k,(lo,hi) in bounds.items():
        v=seeds[k]
        if type(v) is not int or not lo<=v<=hi: raise ValueError(f"{k} outside [{lo}, {hi}]")
    if seeds["env_master_seed"] in REJECTED_MASTERS: raise ValueError("finite-history prior master seed rejected")

def controller_lr(arm: str,cumulative_update: int)->float:
    if arm not in ARMS: raise ValueError("unknown arm")
    if type(cumulative_update)is not int or not 397<=cumulative_update<=456: raise ValueError("controller update must be in [397, 456]")
    if arm=="A_constant_3e-5": return 3e-5
    u=cumulative_update-396
    return 1e-5 if u==60 else 3e-5-2e-5*(u-1)/59

def validate_pair(pair: Mapping[str,object])->None:
    if set(pair)!={"pair_id","A","B"} or not isinstance(pair["pair_id"],str) or not pair["pair_id"]: raise ValueError("pair requires one pair_id and exactly A/B")
    validate_seeds(pair["A"]); validate_seeds(pair["B"])
    if dict(pair["A"])!=dict(pair["B"]): raise ValueError("paired arms must use identical complete seed vector")

def _normalize_range(row):
    if isinstance(row,Mapping): lo,hi=row.get("low"),row.get("high")
    else:
        try: lo,hi=row
        except Exception as e: raise ValueError("range must be [low, high] or low/high mapping") from e
    if type(lo)is not int or type(hi)is not int or lo<0 or hi>U32_MAX or lo>hi: raise ValueError("invalid exclusion range bounds/order")
    return lo,hi

def validate_exclusion_controls(ranges,episode_controls)->None:
    normalized=tuple(sorted(_normalize_range(r) for r in ranges))
    if len(normalized)!=5 or len(set(normalized))!=5: raise ValueError("exclusion union requires five unique ranges")
    if any(a[1]>=b[0] for a,b in zip(normalized,normalized[1:])): raise ValueError("exclusion ranges overlap")
    if normalized!=EXPECTED_EXCLUSION_RANGES: raise ValueError("future environment requires exact five-range exclusion union")
    if len(episode_controls)!=64: raise ValueError("environment controls must cover 64 per-slot episode indices")
    slots=set()
    for row in episode_controls:
        if set(row)!={"slot","episode_index","first_actual_seed","rejection_counter"}: raise ValueError("control row has missing or unexpected fields")
        slot=row["slot"]
        if type(slot)is not int or not 0<=slot<64 or slot in slots: raise ValueError("missing or duplicate control slot")
        slots.add(slot)
        if type(row["episode_index"])is not int or row["episode_index"]<0: raise ValueError("invalid episode index")
        seed=row["first_actual_seed"]
        if type(seed)is not int or not 0<=seed<=U32_MAX: raise ValueError("first actual seed outside u32")
        if any(lo<=seed<=hi for lo,hi in normalized): raise ValueError("first actual seed collides with exclusion union")
        if type(row["rejection_counter"])is not int or row["rejection_counter"]<0: raise ValueError("invalid seed rejection counter")

def transition(*,session: TransitionSession,backend: str,seeds: Mapping[str,object],pair: Mapping[str,object],verify_trusted_source,restore_trusted,current_fingerprints,expected_state_digests: Mapping[str,str],state_fingerprint,python_api,numpy_api,torch_api,optimizer,pair_id: str,arm: str)->dict:
    """Verify trusted source, restore, then seed CPU and MPS. No retry."""
    if session._started: raise RuntimeError("transition session already consumed; no retry")
    if backend!="mps" or not torch_api.backends.mps.is_available(): raise ValueError("MPS backend unavailable")
    if arm not in ARMS or not pair_id: raise ValueError("pair_id and recognized arm required")
    validate_pair(pair)
    if pair["pair_id"]!=pair_id or dict(seeds)!=dict(pair["A"]): raise ValueError("transition seeds must match validated pair")
    validate_seeds(seeds)
    if set(expected_state_digests)!={"torch_cpu_global_seed","action_sampler_torch_mps_seed"} or any(not isinstance(v,str) or len(v)!=64 for v in expected_state_digests.values()): raise ValueError("real preflight state digests required")
    source=verify_trusted_source()
    if not isinstance(source,Mapping) or source.get("receipt_sha256")!=ACCEPTED_PARENT_RECEIPT_SHA256 or source.get("checkpoint_fingerprints")!=EXPECTED_PARENT: raise ValueError("trusted source receipt/checkpoint fingerprints mismatch")
    session._started=True
    restore_trusted()
    restored=current_fingerprints()
    if restored!=EXPECTED_PARENT: raise ValueError("trusted restore did not produce accepted parent fingerprints")
    python_api.seed(seeds["python_random_seed"]); numpy_api.seed(seeds["numpy_global_seed"])
    torch_api.manual_seed(seeds["torch_cpu_global_seed"])
    torch_api.mps.manual_seed(seeds["action_sampler_torch_mps_seed"])
    evidence={"torch_cpu_initial_seed":torch_api.initial_seed(),"torch_cpu_rng_state_sha256":state_fingerprint(torch_api.get_rng_state()),"torch_mps_rng_state_sha256":state_fingerprint(torch_api.mps.get_rng_state())}
    if evidence["torch_cpu_initial_seed"]!=seeds["torch_cpu_global_seed"]: raise ValueError("CPU RNG read-back mismatch")
    if evidence["torch_cpu_rng_state_sha256"]!=expected_state_digests["torch_cpu_global_seed"]: raise ValueError("CPU state digest mismatch")
    if evidence["torch_mps_rng_state_sha256"]!=expected_state_digests["action_sampler_torch_mps_seed"]: raise ValueError("MPS state digest mismatch")
    after=current_fingerprints()
    if after["model"]!=restored["model"] or after["Adam"]!=restored["Adam"]: raise ValueError("reseeding changed model or Adam state")
    groups=optimizer.param_groups
    if not isinstance(groups,list) or not groups: raise ValueError("optimizer must have parameter groups")
    old_groups=[dict(g) for g in groups]
    old_state=optimizer.state.copy()
    for g in groups: g["lr"]=controller_lr(arm,397)
    final=current_fingerprints()
    if final["model"]!=restored["model"] or final["Adam"]!=restored["Adam"]: raise ValueError("model/Adam fingerprint changed after LR override")
    for old,g in zip(old_groups,groups):
        if {k:v for k,v in old.items() if k!="lr"}!={k:v for k,v in g.items() if k!="lr"}: raise ValueError("optimizer group field changed beyond LR")
    if optimizer.state!=old_state: raise ValueError("optimizer moments/steps changed")
    return {"pair_id":pair_id,"arm":arm,"backend":backend,"seed_evidence":evidence,"parent_fingerprints":restored,"required_fingerprint_contract":"model exact; Adam exact excluding param_group.lr; optimizer.state moments/steps unchanged", "fingerprint_contract_status":"callback definition not supplied or verified here","old_controller_provenance":dict(OLD_CONTROLLER_PROVENANCE),"new_controller":{"kind":"constant" if arm=="A_constant_3e-5" else "linear","origin":396,"horizon":60,"first_update":397,"last_update":456,"start_lr":3e-5,"end_lr":1e-5}}
