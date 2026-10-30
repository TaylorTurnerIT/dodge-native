"""Scratch CPU models only; never restore a campaign model or execute games."""

import copy
import io
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import pytest
import torch

from dodge_rl.models.ray_teacher import RayGeometryTeacher
from dodge_rl.models.teacher import OmniscientEntityTeacher
from test_clearance_rays_source import scene


def synthetic_inputs():
    data = scene(boxes=[(1, 70, 60, 75, 68, True), (7, 60, 70, 68, 75, False)])
    return tuple(torch.tensor(value, dtype=dtype, device="cpu") for value, dtype in zip(
        data, (torch.float32, torch.float32, torch.int64, torch.bool), strict=True,
    ))


def scratch_legacy(seed=831, cls=OmniscientEntityTeacher):
    with torch.random.fork_rng(devices=[]):
        torch.random.default_generator.manual_seed(seed)
        return cls().cpu().eval()


def assert_exact(left, right):
    for a, b in zip((left.logits, left.values, left.latent, *left.attentions),
                    (right.logits, right.values, right.latent, *right.attentions), strict=True):
        assert torch.equal(a, b)


def test_constructor_preserves_cpu_rng_legacy_parameters_and_nonzero_branch(monkeypatch):
    legacy = scratch_legacy()
    before = copy.deepcopy(legacy.state_dict())
    rng = torch.get_rng_state().clone()

    def no_accelerator(*args, **kwargs):
        raise AssertionError("Accelerator RNG call forbidden")

    monkeypatch.setattr(torch.mps, "manual_seed", no_accelerator)
    monkeypatch.setattr(torch.cuda, "manual_seed_all", no_accelerator)
    model = RayGeometryTeacher(legacy, branch_seed=142)
    assert torch.equal(rng, torch.get_rng_state())
    assert model.gate.item() == 0
    assert all(torch.equal(value, before[key]) for key, value in legacy.state_dict().items())
    assert all(p.requires_grad for p in model.parameters())
    assert all(torch.count_nonzero(layer.weight) > 0 for layer in (model.branch[0], model.branch[2]))
    added = sum(p.numel() for p in model.parameters()) - sum(p.numel() for p in legacy.parameters())
    assert added == 11329
    assert model.architecture_description()["parameter_count"] == 332619
    assert json.loads(json.dumps(model.architecture_description())) == model.architecture_description()


@pytest.mark.parametrize("training", [True, False])
def test_zero_gate_exact_logits_values_latent_attention(training):
    legacy = scratch_legacy()
    model = RayGeometryTeacher(legacy).train(training)
    data = synthetic_inputs()
    with torch.no_grad():
        assert_exact(legacy(*data), model(*data))


def test_legacy_encode_refactor_matches_pinned_prechange_source_exactly():
    # Source-only provenance oracle. Execute the old model *definition* with
    # fresh synthetic weights; never load a checkpoint or import native code.
    root = Path(__file__).resolve().parents[2]
    source = subprocess.run(
        ["git", "show", "309a2238e3a7947109a48bd5adac1a0333bb7918:python/dodge_rl/models/teacher.py"],
        cwd=root, check=True, text=True, capture_output=True,
    ).stdout
    module = ModuleType("_ray_prechange_source")
    sys.modules[module.__name__] = module
    try:
        exec(compile(source, "<pinned-prechange-teacher>", "exec"), module.__dict__)
        old = scratch_legacy(cls=module.OmniscientEntityTeacher)
        new = scratch_legacy()
        assert list(old.state_dict()) == list(new.state_dict())
        for name, value in old.state_dict().items():
            assert torch.equal(value, new.state_dict()[name])
        with torch.no_grad():
            assert_exact(old(*synthetic_inputs()), new(*synthetic_inputs()))
        assert old.architecture_description() == new.architecture_description()
    finally:
        del sys.modules[module.__name__]


def test_gate_gets_gradient_then_nonzero_gate_routes_branch_gradient():
    model = RayGeometryTeacher(scratch_legacy())
    data = synthetic_inputs()
    result = model(*data)
    (result.logits[:, 0].sum() + result.values.sum()).backward()
    assert torch.isfinite(model.gate.grad) and model.gate.grad.abs() > 0
    assert all(p.grad is not None and torch.count_nonzero(p.grad) == 0 for p in model.branch.parameters())
    model.zero_grad(set_to_none=True)
    with torch.no_grad():
        model.gate.fill_(0.25)  # Synthetic gradient routing, no optimizer/fitting.
    result = model(*data)
    (result.logits[:, 0].sum() + result.values.sum()).backward()
    assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.branch.parameters())
    assert sum(p.grad.abs().sum() for p in model.branch.parameters()) > 0
    assert sum(p.grad.abs().sum() for p in model.legacy.actor_head.parameters()) > 0
    assert sum(p.grad.abs().sum() for p in model.legacy.critic_head.parameters()) > 0


def test_open_gate_padding_invariance_and_represented_geometry_sensitivity(monkeypatch):
    model = RayGeometryTeacher(scratch_legacy())
    with torch.no_grad():
        model.gate.fill_(0.5)
    data = synthetic_inputs()
    changed = [value.clone() for value in data]
    changed[1][~changed[3]] = float("nan")
    changed[2][~changed[3]] = 999
    with torch.no_grad():
        fixed_encoding = model.legacy.encode(*data)
        monkeypatch.setattr(model.legacy, "encode", lambda *args: fixed_encoding)
        before = model(*data)
        assert_exact(before, model(*changed))
        changed[1][0, 0, 0] += 0.1
        # Legacy encoding is held fixed, so this change must pass through rays.
        assert not torch.equal(before.latent, model(*changed).latent)
    with pytest.raises(TypeError):
        model(*data, hidden_history_valid=True)


def test_synthetic_serialization_roundtrip_in_memory_only():
    model = RayGeometryTeacher(scratch_legacy(), branch_seed=71)
    with torch.no_grad():
        model.gate.fill_(0.25)
    buffer = io.BytesIO()
    torch.save(model.state_dict(), buffer)
    buffer.seek(0)
    other = RayGeometryTeacher(scratch_legacy(seed=2), branch_seed=3)
    other.load_state_dict(torch.load(buffer, weights_only=True, map_location="cpu"), strict=True)
    with torch.no_grad():
        assert_exact(model(*synthetic_inputs()), other(*synthetic_inputs()))


def test_adapter_validates_valid_rows_before_legacy_encoder(monkeypatch):
    legacy = scratch_legacy()
    model = RayGeometryTeacher(legacy)

    def forbidden_encoder(*args):
        raise AssertionError("Invalid inputs must fail before encode")

    monkeypatch.setattr(legacy, "encode", forbidden_encoder)
    data = list(synthetic_inputs())
    data[1][0, 0, 0] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        model(*data)


def test_adapter_rejects_wrong_dtype_and_non_cpu_without_device_allocation():
    model = RayGeometryTeacher(scratch_legacy())
    data = list(synthetic_inputs())
    data[0] = data[0].double()
    with pytest.raises(TypeError, match="float32"):
        model(*data)
    meta = [value.to(device="meta") for value in synthetic_inputs()]
    with pytest.raises(ValueError, match="CPU"):
        model(*meta)
    with pytest.raises(ValueError, match="CPU"):
        RayGeometryTeacher(scratch_legacy().double())


def test_branch_ignores_global_default_dtype_and_native_module_not_loaded():
    legacy = scratch_legacy()
    previous = torch.get_default_dtype()
    try:
        torch.set_default_dtype(torch.float64)
        model = RayGeometryTeacher(legacy)
        assert all(p.dtype == torch.float32 and p.device.type == "cpu" for p in model.parameters())
    finally:
        torch.set_default_dtype(previous)
    assert "dodge_rl._native" not in sys.modules
