"""Registered PPO learning-rate transition for the resume arm.

Standard library only: the proposed runner imports this module at top level and
must keep its import surface stdlib-only. Every validator runs before the first
write. The only write is optimizer.param_groups[*]["lr"].
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

PARENT_LR = 0.0003
ARM_LR = 0.0001
PARENT_PHASE_UPDATE = 180
PARENT_CONFIG_SHA256 = "2d8eb5626d0debdf5416d0b89610d78ddd56011c3238a82fec72efabe1bd7fe3"
PARENT_CHECKPOINT_SHA256 = "105e0f7a83e154116bd9f0d5eaaf573a896886468c9038f548f5ce7e6377c7ea"
PARENT_RECEIPT_SHA256 = "7968a62b6e601fab971e4145dbaebfa1995c8f696e6df442ab70fc0435b74903"
PARENT_REGISTRATION_SHA256 = "6f4adf808789655a663800a1e4a0613192d02b0c8287d121455ea748fe043916"
DECLARED_TRANSITION = {
    "kind": "restore_adam_moments_then_override_group_lr_v1",
    "parent_lr": PARENT_LR,
    "effective_lr": ARM_LR,
    "changed_fields": ["optimizer.param_groups[*].lr"],
}
CHANGED_CONFIG_FIELDS = ["ppo.learning_rate"]


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(value) -> str:
    """Typed tree digest; byte-identical algorithm to runner.fingerprint (checked by tests)."""
    h = hashlib.sha256()

    def field(tag, payload=b""):
        tag = tag.encode("utf-8")
        h.update(len(tag).to_bytes(8, "big")); h.update(tag)
        h.update(len(payload).to_bytes(8, "big")); h.update(payload)

    def visit(v):
        if hasattr(v, "detach"):
            v = v.detach().cpu().contiguous().numpy()
        if hasattr(v, "dtype") and hasattr(v, "tobytes"):
            field("array", (str(v.dtype) + repr(tuple(v.shape))).encode())
            field("array-bytes", v.tobytes()); return
        if isinstance(v, Mapping):
            field("mapping", len(v).to_bytes(8, "big"))
            for k in sorted(v, key=lambda key: (type(key).__name__, repr(key))):
                field("entry")
                visit(k); visit(v[k])
            field("end-mapping")
        elif isinstance(v, list):
            field("list", len(v).to_bytes(8, "big"))
            for item in v:
                visit(item)
            field("end-list")
        elif isinstance(v, tuple):
            field("tuple", len(v).to_bytes(8, "big"))
            for item in v:
                visit(item)
            field("end-tuple")
        else:
            field("scalar:" + type(v).__module__ + "." + type(v).__qualname__, repr(v).encode())

    visit(value)
    return h.hexdigest()


def without_group_lr(state: Mapping) -> dict:
    """Optimizer state_dict view with only param_groups[*]["lr"] removed.

    Tensors are shared, not copied, so no extra device memory is allocated.
    The input mapping is not modified.
    """
    groups = state.get("param_groups") if isinstance(state, Mapping) else None
    need(isinstance(groups, list) and bool(groups), "Optimizer state has no parameter groups")
    stripped = []
    for index, group in enumerate(groups):
        need(isinstance(group, Mapping) and "lr" in group, f"Parameter group {index} lacks lr")
        stripped.append({key: value for key, value in group.items() if key != "lr"})
    return {**state, "param_groups": stripped}


def assert_effective_lr(optimizer, expected_lr: float = ARM_LR) -> None:
    """Fail closed unless every parameter group carries exactly expected_lr."""
    need(type(expected_lr) is float and expected_lr > 0, "Expected learning rate must be a positive float")
    groups = optimizer.param_groups
    need(bool(groups), "Optimizer has no parameter groups")
    for index, group in enumerate(groups):
        need(type(group.get("lr")) is float and group["lr"] == expected_lr,
             f"Effective optimizer learning rate differs at group {index}")


def _canonical(value) -> str:
    # Typed comparison: 64 vs 64.0 and True vs 1 are different, unlike dict equality.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def validate_config_transition(parent_config: Mapping, arm_config: Mapping) -> dict:
    """Allow exactly ppo.learning_rate 0.0003 -> 0.0001; every other field must match."""
    need(isinstance(parent_config, Mapping) and isinstance(arm_config, Mapping), "Learner configs must be objects")
    parent_ppo, arm_ppo = parent_config.get("ppo"), arm_config.get("ppo")
    need(isinstance(parent_ppo, Mapping) and isinstance(arm_ppo, Mapping), "Learner config lacks a ppo object")
    need(type(parent_ppo.get("learning_rate")) is float and parent_ppo["learning_rate"] == PARENT_LR,
         "Parent config learning rate differs from 0.0003")
    need(type(arm_ppo.get("learning_rate")) is float and arm_ppo["learning_rate"] == ARM_LR,
         "Arm config learning rate differs from 0.0001")

    def without_lr(config):
        return {**config, "ppo": {k: v for k, v in config["ppo"].items() if k != "learning_rate"}}

    need(_canonical(without_lr(parent_config)) == _canonical(without_lr(arm_config)),
         "Arm config differs outside ppo.learning_rate")
    return {"changed_config_fields": list(CHANGED_CONFIG_FIELDS), "parent_lr": PARENT_LR, "arm_lr": ARM_LR}


def validate_arm_binding(reg: Mapping, *, parent_config_file_sha256: str, arm_config_file_sha256: str) -> dict:
    """Bind parent config, arm config, accepted parent checkpoint/receipt, and declared transition."""
    need(isinstance(reg, Mapping), "Registration must be an object")
    parent = reg.get("parent")
    need(isinstance(parent, Mapping), "Registration parent block is missing")
    need(parent_config_file_sha256 == PARENT_CONFIG_SHA256 and reg.get("parent_config_sha256") == PARENT_CONFIG_SHA256,
         "Parent config file identity differs")
    need(isinstance(arm_config_file_sha256, str) and len(arm_config_file_sha256) == 64
         and arm_config_file_sha256 != PARENT_CONFIG_SHA256 and reg.get("config_sha256") == arm_config_file_sha256,
         "Arm config file identity differs from registration or equals the parent config")
    need(parent.get("sha256") == PARENT_CHECKPOINT_SHA256
         and parent.get("terminal_receipt_sha256") == PARENT_RECEIPT_SHA256
         and parent.get("registration_sha256") == PARENT_REGISTRATION_SHA256
         and parent.get("completed_updates") == PARENT_PHASE_UPDATE,
         "Exact accepted parent checkpoint/receipt identity differs")
    need(reg.get("arm_transition") == DECLARED_TRANSITION, "Registered LR transition differs")
    return {"parent_config_file_sha256": PARENT_CONFIG_SHA256, "arm_config_file_sha256": arm_config_file_sha256,
            "parent_checkpoint_sha256": PARENT_CHECKPOINT_SHA256,
            "parent_receipt_sha256": PARENT_RECEIPT_SHA256,
            "parent_registration_sha256": PARENT_REGISTRATION_SHA256}


def apply_resume_lr_override(optimizer, config_lr, declared_transition) -> dict:
    """Validate the declared transition, config LR, and every group; then write group LR.

    No write happens before all checks pass. A failed check leaves the optimizer
    exactly as it was.
    """
    need(declared_transition == DECLARED_TRANSITION, "Registered LR transition differs")
    need(type(config_lr) is float and config_lr == ARM_LR, "Arm config learning rate must be exactly 0.0001")
    groups = optimizer.param_groups
    need(bool(groups), "Optimizer has no parameter groups")
    for index, group in enumerate(groups):
        need(type(group.get("lr")) is float and group["lr"] == PARENT_LR,
             f"Restored parent learning rate differs from 0.0003 at group {index}")
    before = [group["lr"] for group in groups]
    for group in groups:
        group["lr"] = ARM_LR
    assert_effective_lr(optimizer, ARM_LR)
    return {"parent_lr": PARENT_LR, "effective_lr": ARM_LR,
            "changed_fields": list(DECLARED_TRANSITION["changed_fields"]),
            "per_group_lr": [{"index": i, "before": lr, "after": ARM_LR} for i, lr in enumerate(before)]}


def transition_record(parent_state: Mapping, effective_state: Mapping, delta: Mapping, identities: Mapping) -> dict:
    """Full and LR-excluded optimizer fingerprints plus the exact per-group LR delta.

    Both states must be optimizer.state_dict() snapshots taken before and after the
    override. The full fingerprint must change (the LR changed). The LR-excluded
    fingerprint must not change.
    """
    before_full, after_full = fingerprint(parent_state), fingerprint(effective_state)
    before_excluding = fingerprint(without_group_lr(parent_state))
    after_excluding = fingerprint(without_group_lr(effective_state))
    need(before_full != after_full, "Full optimizer fingerprint did not change with the declared LR")
    need(before_excluding == after_excluding, "Adam state changed outside declared parameter-group LR transition")
    return {**delta, **identities,
            "parent_optimizer_fingerprint": before_full,
            "effective_optimizer_fingerprint": after_full,
            "parent_optimizer_fingerprint_excluding_lr": before_excluding,
            "effective_optimizer_fingerprint_excluding_lr": after_excluding,
            "non_lr_fields_changed": []}


def guarded_update(optimizer, expected_lr: float, update_fn, *args, **kwargs):
    """Assert the effective LR immediately before and after one PPO update call."""
    assert_effective_lr(optimizer, expected_lr)
    result = update_fn(*args, **kwargs)
    assert_effective_lr(optimizer, expected_lr)
    return result
