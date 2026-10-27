"""Inert transition contract. Runtime, checkpoint, environment, and launch work stay external."""
from __future__ import annotations
from collections.abc import Mapping

EXPECTED_PARENT = {"model":"3b72815fef4d8fa0084044739f5a5eaf9f74971b36dff9d8b26ed3bea5c562bc","Adam":"cf5e2a7ac5d3f7f131a26f7c2b8b778b7692850cff606a0ea9080941b960451c","RNG":"cb96ee8d2c40114a51abb8031dc7457a6da6d1be7262c6a4859bd34cab5813af"}
SEED_FIELDS=("constructor_init_seed","python_random_seed","numpy_global_seed","torch_cpu_global_seed","action_sampler_torch_mps_seed","env_master_seed")
U32_MAX,I63_MAX,U64_MAX=(1<<32)-1,(1<<63)-1,(1<<64)-1
REJECTED_MASTERS=frozenset({810631976,3192039780,3791628417,4200000000,4200000001,5562881586070242562})
EXPECTED_EXCLUSION_RANGES=tuple(sorted(((0xD3000000,0xD30003FF),(2952790016,2952791015),(3489660928,3489661055),(3758096384,3758097383),(3506438144,3506439167),(3523215360,3523217407))))
OLD_CONTROLLER_PROVENANCE={"origin":372,"horizon":60,"completed":0,"saved_lr":3e-5,"schedule":"none"}
ARMS={"control_constant_3e-5","progressive1000_curriculum_constant_3e-5"}
ACCEPTED_PARENT_RECEIPT_SHA256="76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08"

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
    if type(cumulative_update)is not int or not 373<=cumulative_update<=432: raise ValueError("controller update must be in [373, 432]")
    return 3e-5

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
    if len(normalized)<6 or len(set(normalized))!=len(normalized): raise ValueError("exclusion union requires at least six unique ranges")
    if any(a[1]>=b[0] for a,b in zip(normalized,normalized[1:])): raise ValueError("exclusion ranges overlap")
    if not all(any(lo<=a and hi>=b for lo,hi in normalized) for a,b in EXPECTED_EXCLUSION_RANGES): raise ValueError("future environment requires full historical and new cohort union")
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

def transition(*, session: TransitionSession, attempt_claim, backend: str, seeds: Mapping[str, object],
               pair: Mapping[str, object], verify_trusted_source, restore_trusted,
               model, optimizer, rng_capture, pinned_rng_reference: Mapping[str, object],
               python_api, numpy_api, torch_api, pair_id: str, arm: str,
               study_id: str, replica: int, torch_version: str, run_id: str) -> dict:
    """Validate all immutable pins, then restore and seed once. No retry."""
    from fingerprints import fingerprint, optimizer_content_fingerprint
    from rng_reference import load_bound_reference
    import hashlib
    from pathlib import Path

    if session._started:
        raise RuntimeError("transition session already consumed; no retry")
    if backend != "mps" or not torch_api.backends.mps.is_available():
        raise ValueError("MPS backend unavailable")
    if arm not in ARMS or not pair_id or type(run_id) is not str or not run_id:
        raise ValueError("run_id, pair_id, and recognized arm required")
    validate_pair(pair)
    if pair["pair_id"] != pair_id or dict(seeds) != dict(pair["A"]):
        raise ValueError("transition seeds must match validated pair")
    validate_seeds(seeds)
    if not isinstance(pinned_rng_reference, Mapping):
        raise ValueError("pinned external RNG reference required")
    required = {"receipt_path", "receipt_sha256", "vector_sha256"}
    if set(pinned_rng_reference) != required:
        raise ValueError("pinned RNG reference fields mismatch")

    source = verify_trusted_source()
    if not isinstance(source, Mapping):
        raise ValueError("trusted source receipt missing")
    if source.get("receipt_sha256") != ACCEPTED_PARENT_RECEIPT_SHA256:
        raise ValueError("trusted source receipt SHA-256 mismatch")
    if source.get("checkpoint_sha256") != rng_reference_checkpoint_sha256():
        raise ValueError("accepted checkpoint SHA-256 mismatch")
    if source.get("checkpoint_fingerprints") != EXPECTED_PARENT:
        raise ValueError("trusted source checkpoint fingerprints mismatch")
    receipt_fps = source.get("learner_fingerprints")
    if receipt_fps != EXPECTED_PARENT:
        raise ValueError("parent receipt learner_fingerprints mismatch")

    checkpoint_path = Path(source.get("checkpoint_path", ""))
    if not checkpoint_path.is_file():
        raise ValueError("accepted checkpoint file missing")
    if _sha256_file(checkpoint_path) != rng_reference_checkpoint_sha256():
        raise ValueError("accepted checkpoint file SHA-256 mismatch")
    receipt_path = Path(source.get("receipt_path", ""))
    if not receipt_path.is_file() or _sha256_file(receipt_path) != ACCEPTED_PARENT_RECEIPT_SHA256:
        raise ValueError("accepted parent receipt file SHA-256 mismatch")

    reference = load_bound_reference(
        receipt_path=pinned_rng_reference["receipt_path"],
        expected_receipt_sha256=pinned_rng_reference["receipt_sha256"],
        expected_study_id=study_id, expected_replica=replica,
        expected_seed_vector=dict(seeds),
        expected_vector_sha256=pinned_rng_reference["vector_sha256"],
        expected_torch_version=torch_version,
    )
    if set(reference) != {"torch_cpu_global_seed", "action_sampler_torch_mps_seed"}:
        raise ValueError("bound RNG reference fields mismatch")

    from attempt_claim import AttemptClaim, canonical_claim, verify_claim_receipt
    claim_record = {"run_id": run_id, "study_id": study_id, "replica": replica,
                    "arm": arm, "vector_sha256": pinned_rng_reference["vector_sha256"],
                    "parent_checkpoint_sha256": rng_reference_checkpoint_sha256()}
    if type(attempt_claim) is not AttemptClaim:
        raise ValueError("concrete persistent AttemptClaim required; receipt reuse is forbidden")
    if attempt_claim.payload != canonical_claim(claim_record):
        raise ValueError("attempt claim binding identity mismatch before claim")
    claim_receipt = attempt_claim.claim()
    verify_claim_receipt(claim_receipt, attempt_claim.path, claim_record)
    session._started = True
    restore_trusted()
    restored = _live_fingerprints(model, optimizer, rng_capture, fingerprint,
                                  optimizer_content_fingerprint)
    if restored != EXPECTED_PARENT:
        raise ValueError("trusted restore did not produce accepted parent fingerprints")

    python_api.seed(seeds["python_random_seed"])
    numpy_api.seed(seeds["numpy_global_seed"])
    torch_api.manual_seed(seeds["torch_cpu_global_seed"])
    torch_api.mps.manual_seed(seeds["action_sampler_torch_mps_seed"])
    evidence = {
        "torch_cpu_initial_seed": torch_api.initial_seed(),
        "torch_cpu_rng_state_sha256": fingerprint(torch_api.get_rng_state()),
        "torch_mps_rng_state_sha256": fingerprint(torch_api.mps.get_rng_state()),
    }
    if evidence["torch_cpu_initial_seed"] != seeds["torch_cpu_global_seed"]:
        raise ValueError("CPU RNG read-back mismatch")
    if evidence["torch_cpu_rng_state_sha256"] != reference["torch_cpu_global_seed"]:
        raise ValueError("CPU state digest mismatch")
    if evidence["torch_mps_rng_state_sha256"] != reference["action_sampler_torch_mps_seed"]:
        raise ValueError("MPS state digest mismatch")
    after_seed = _live_fingerprints(model, optimizer, rng_capture, fingerprint,
                                    optimizer_content_fingerprint)
    if after_seed["model"] != restored["model"] or after_seed["Adam"] != restored["Adam"]:
        raise ValueError("reseeding changed model or Adam state")

    groups = optimizer.param_groups
    if not isinstance(groups, list) or not groups:
        raise ValueError("optimizer must have parameter groups")
    before_lr_model = fingerprint(model.state_dict())
    before_lr_adam = fingerprint(optimizer.state_dict())
    before_lr_content = optimizer_content_fingerprint(optimizer.state_dict())
    for group in groups:
        group["lr"] = controller_lr(arm, 373)
    effective_lr = [group.get("lr") for group in groups]
    if any(type(value) not in (int, float) or value != controller_lr(arm, 373) for value in effective_lr):
        raise ValueError("effective LR read-back mismatch")
    after_lr_model = fingerprint(model.state_dict())
    after_lr_adam = fingerprint(optimizer.state_dict())
    after_lr_content = optimizer_content_fingerprint(optimizer.state_dict())
    if after_lr_model != before_lr_model:
        raise ValueError("model changed after LR override")
    if after_lr_content != before_lr_content:
        raise ValueError("optimizer contents changed beyond LR")
    # Saved LR is already 3e-5; no-op override may preserve full Adam hash.
    return {
        "pair_id": pair_id, "arm": arm, "backend": backend,
        "study_id": study_id, "replica": replica, "seed_vector": dict(seeds),
        "vector_sha256": pinned_rng_reference["vector_sha256"],
        "constructor_seed_status": "driver_deferred_not_applied",
        "environment_seed_status": "driver_deferred_not_applied",
        "seed_evidence": evidence, "parent_fingerprints": restored,
        "post_lr_fingerprints": {"model": after_lr_model, "Adam": after_lr_adam,
                                  "Adam_content_excluding_lr": after_lr_content},
        "required_fingerprint_contract": "full model and Adam exact through reseed; post-LR optimizer content exact excluding only param_groups[].lr",
        "fingerprint_contract_status": "concrete state_dict fingerprints verified",
        "old_controller_provenance": dict(OLD_CONTROLLER_PROVENANCE),
        "new_controller": {"kind": "constant",
                           "origin": 372, "horizon": 60, "first_update": 373,
                           "last_update": 432, "start_lr": 3e-5,
                           "end_lr": 3e-5},
    }


def rng_reference_checkpoint_sha256():
    from rng_reference import ACCEPTED_CHECKPOINT_SHA256
    return ACCEPTED_CHECKPOINT_SHA256


def _sha256_file(path):
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _live_fingerprints(model, optimizer, rng_capture, fingerprint,
                       optimizer_content_fingerprint):
    captured = rng_capture()
    if not isinstance(captured, Mapping) or set(captured) != {"python", "numpy_global", "numpy_generator", "torch_cpu", "torch_mps", "sampling_backend"}:
        raise ValueError("rng_capture must return pinned capture_rng raw six-key format")
    return {"model": fingerprint(model.state_dict()),
            "Adam": fingerprint(optimizer.state_dict()),
            "RNG": fingerprint(captured)}
