from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sys

import pytest
import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
FROZEN_RUNTIME = ROOT / "learning/runs/v2/D2-best180-branch-prepare-luna-20261026-r1/own/runtime"
sys.path.insert(0, str(FROZEN_RUNTIME))
sys.path.insert(0, str(HERE))

from dodge_rl import checkpoints as ckpt  # noqa: E402
from dodge_rl.models.teacher import OmniscientEntityTeacher  # noqa: E402
from resume_lr_override import (ARM_LR, PARENT_LR, apply_resume_lr_override,
                                assert_effective_lr)  # noqa: E402


def fingerprint(value) -> str:
    def visit(item):
        if torch.is_tensor(item):
            return {"dtype": str(item.dtype), "shape": list(item.shape),
                    "bytes": hashlib.sha256(item.detach().cpu().contiguous().numpy().tobytes()).hexdigest()}
        if isinstance(item, dict):
            return {str(k): visit(v) for k, v in sorted(item.items(), key=lambda pair: str(pair[0]))}
        if isinstance(item, (list, tuple)):
            return [visit(v) for v in item]
        return item
    return hashlib.sha256(json.dumps(visit(value), sort_keys=True, default=str).encode()).hexdigest()


def optimizer_without_lr(state):
    state = copy.deepcopy(state)
    for group in state["param_groups"]:
        group.pop("lr")
    return state


def make_loaded_adam():
    model = torch.nn.Linear(3, 2)
    optimizer = torch.optim.Adam(model.parameters(), lr=PARENT_LR, eps=1e-5)
    model(torch.ones(2, 3)).sum().backward()
    optimizer.step()
    optimizer.zero_grad(set_to_none=True)
    # Reload saved Adam state to model the frozen checkpoint restoration path.
    saved = copy.deepcopy(optimizer.state_dict())
    target = torch.optim.Adam(model.parameters(), lr=ARM_LR, eps=1e-5)
    target.load_state_dict(saved)
    return model, target


def test_hook_changes_only_lr_and_rejects_bad_inputs_atomically():
    model, optimizer = make_loaded_adam()
    before_model = fingerprint(model.state_dict())
    before_state = optimizer.state_dict()
    before_other_groups = fingerprint(optimizer_without_lr(before_state))
    before_rng = torch.get_rng_state().clone()
    receipt = apply_resume_lr_override(optimizer, ARM_LR)
    assert receipt["changed_fields"] == ["optimizer.param_groups[*].lr"]
    assert_effective_lr(optimizer)
    assert all(g["lr"] == ARM_LR for g in optimizer.param_groups)
    assert fingerprint(model.state_dict()) == before_model
    assert fingerprint(optimizer_without_lr(optimizer.state_dict())) == before_other_groups
    assert torch.equal(torch.get_rng_state(), before_rng)

    after_good = copy.deepcopy(optimizer.state_dict())
    with pytest.raises(ValueError, match="exactly 0.0001"):
        apply_resume_lr_override(optimizer, 2e-4)
    assert fingerprint(optimizer.state_dict()) == fingerprint(after_good)


def test_parent_group_mismatch_rejected_before_any_group_mutation():
    model = torch.nn.Linear(2, 2)
    optimizer = torch.optim.Adam([{"params": [model.weight], "lr": PARENT_LR},
                                  {"params": [model.bias], "lr": 9e-4}], eps=1e-5)
    before = fingerprint(optimizer.state_dict())
    with pytest.raises(ValueError, match="parent learning rate"):
        apply_resume_lr_override(optimizer, ARM_LR)
    assert fingerprint(optimizer.state_dict()) == before


def test_load_state_dict_after_override_resets_lr_and_is_detected():
    _, optimizer = make_loaded_adam()
    parent_state = copy.deepcopy(optimizer.state_dict())
    apply_resume_lr_override(optimizer, ARM_LR)
    optimizer.load_state_dict(parent_state)
    assert all(g["lr"] == PARENT_LR for g in optimizer.param_groups)
    with pytest.raises(ValueError, match="differs from registered arm"):
        assert_effective_lr(optimizer)


def test_real_accepted_best180_restore_on_cpu_then_override_only_lr():
    checkpoint = ROOT / "learning/runs/v2/D2-gradient-alignment-20261025-r2/checkpoint-000180-candidate.pt"
    expected = "105e0f7a83e154116bd9f0d5eaaf573a896886468c9038f548f5ce7e6377c7ea"
    state = ckpt.load_checkpoint(checkpoint, expected_sha256=expected)
    ckpt.require_complete_update(state)
    model = OmniscientEntityTeacher().to(device="cpu", dtype=torch.float32)
    optimizer = torch.optim.Adam(model.parameters(), lr=ARM_LR, eps=1e-5)
    # The accepted parent records an MPS sampling RNG backend. CPU restore of
    # that RNG is intentionally rejected by the frozen loader. Load exact
    # model/Adam tensors on CPU and leave this process's CPU RNG untouched.
    model.load_state_dict(state["model"], strict=True)
    optimizer.load_state_dict(state["optimizer"])
    assert all(group["lr"] == PARENT_LR for group in optimizer.param_groups)
    assert fingerprint(model.state_dict()) == fingerprint(state["model"])
    assert fingerprint(optimizer_without_lr(optimizer.state_dict())) == fingerprint(
        optimizer_without_lr(state["optimizer"]))
    restored_optimizer = fingerprint(optimizer_without_lr(optimizer.state_dict()))
    restored_model = fingerprint(model.state_dict())
    restored_rng = torch.get_rng_state().clone()
    delta = apply_resume_lr_override(optimizer, ARM_LR)
    assert delta["effective_lr"] == ARM_LR
    assert fingerprint(model.state_dict()) == restored_model
    assert fingerprint(optimizer_without_lr(optimizer.state_dict())) == restored_optimizer
    assert torch.equal(torch.get_rng_state(), restored_rng)
    assert_effective_lr(optimizer)
