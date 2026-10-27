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

PARENT_LR = 0.0001
ARM_LR = 0.00003
PARENT_PHASE_UPDATE = 276
PARENT_CONFIG_SHA256 = "f858a63c324fc312f794c0423aa56db2daf60793b62990cd51fa400afe3af628"
PARENT_CHECKPOINT_SHA256 = "0b5cf72b4eb9629fa4f10ce2cecb3625b56f8787c0eca6395b9fe17161e6b292"
PARENT_RECEIPT_SHA256 = "d64d0f803d02a8d2c33da9fa0ba862f06ba7d9c56dcf4f0494e559a49e48fcc4"
PARENT_REGISTRATION_SHA256 = "68063348dede3050c4a8852c6314f4c95fd3a623e89c9499413f2325f4edad44"
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
    """Allow exactly ppo.learning_rate 0.0001 -> 0.00003; every other field must match."""
    need(isinstance(parent_config, Mapping) and isinstance(arm_config, Mapping), "Learner configs must be objects")
    parent_ppo, arm_ppo = parent_config.get("ppo"), arm_config.get("ppo")
    need(isinstance(parent_ppo, Mapping) and isinstance(arm_ppo, Mapping), "Learner config lacks a ppo object")
    need(type(parent_ppo.get("learning_rate")) is float and parent_ppo["learning_rate"] == PARENT_LR,
         "Parent config learning rate differs from 0.0001")
    need(type(arm_ppo.get("learning_rate")) is float and arm_ppo["learning_rate"] == ARM_LR,
         "Arm config learning rate differs from 0.00003")

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
         and parent.get("phase_update") == PARENT_PHASE_UPDATE,
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
    need(type(config_lr) is float and config_lr == ARM_LR, "Arm config learning rate must be exactly 0.00003")
    groups = optimizer.param_groups
    need(bool(groups), "Optimizer has no parameter groups")
    for index, group in enumerate(groups):
        need(type(group.get("lr")) is float and group["lr"] == PARENT_LR,
             f"Restored parent learning rate differs from 0.0001 at group {index}")
    before = [group["lr"] for group in groups]
    for group in groups:
        group["lr"] = ARM_LR
    assert_effective_lr(optimizer, ARM_LR)
    return {"parent_lr": PARENT_LR, "effective_lr": ARM_LR,
            "changed_fields": list(DECLARED_TRANSITION["changed_fields"]),
            "per_group_lr": [{"index": i, "before": lr, "after": ARM_LR} for i, lr in enumerate(before)]}


def begin_transition_record(parent_state: Mapping, identities: Mapping) -> dict:
    """Hash the live state before mutation; hashes remain immutable across LR writes."""
    return {**identities,
            "parent_optimizer_fingerprint": fingerprint(parent_state),
            "parent_optimizer_fingerprint_excluding_lr": fingerprint(without_group_lr(parent_state)),
            "parent_group_lr": [group["lr"] for group in parent_state["param_groups"]]}


def transition_record(before: Mapping, effective_state: Mapping, delta: Mapping) -> dict:
    """Compare post-override state with immutable pre-override fingerprints."""
    after_full = fingerprint(effective_state)
    after_excluding = fingerprint(without_group_lr(effective_state))
    need(before["parent_optimizer_fingerprint"] != after_full,
         "Full optimizer fingerprint did not change with the declared LR")
    non_lr_fields_changed = ([] if before["parent_optimizer_fingerprint_excluding_lr"] == after_excluding
                             else ["optimizer state or parameter-group fields excluding lr"])
    need(not non_lr_fields_changed,
         "Adam state changed outside declared parameter-group LR transition")
    old_lrs = before["parent_group_lr"]
    new_lrs = [group["lr"] for group in effective_state["param_groups"]]
    need(len(old_lrs) == len(new_lrs), "Optimizer parameter-group count changed")
    changes = [{"index": i, "before": old, "after": new}
               for i, (old, new) in enumerate(zip(old_lrs, new_lrs)) if old != new]
    need(changes and all(type(item["before"]) is float and item["before"] == PARENT_LR
                         and type(item["after"]) is float and item["after"] == ARM_LR
                         for item in changes)
         and len(changes) == len(old_lrs), "Actual optimizer LR delta differs")
    return {**before, **delta,
            "effective_optimizer_fingerprint": after_full,
            "effective_optimizer_fingerprint_excluding_lr": after_excluding,
            "actual_group_lr_delta": changes,
            "non_lr_fields_changed": non_lr_fields_changed}


def assert_saved_optimizer_lr(state: Mapping, expected_lr: float = ARM_LR) -> None:
    """Check serialized checkpoint optimizer groups immediately before save."""
    optimizer = state.get("optimizer") if isinstance(state, Mapping) else None
    need(isinstance(optimizer, Mapping), "Checkpoint optimizer state missing")
    groups = optimizer.get("param_groups")
    need(isinstance(groups, list) and bool(groups), "Checkpoint optimizer groups missing")
    for index, group in enumerate(groups):
        need(type(group.get("lr")) is float and group["lr"] == expected_lr,
             f"Saved checkpoint optimizer learning rate differs at group {index}")


def guarded_update(optimizer, expected_lr: float, update_fn, *args, **kwargs):
    """Assert the effective LR immediately before and after one PPO update call."""
    assert_effective_lr(optimizer, expected_lr)
    result = update_fn(*args, **kwargs)
    assert_effective_lr(optimizer, expected_lr)
    return result
