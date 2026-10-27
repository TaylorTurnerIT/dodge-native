"""CPU-only tests for the registered resume LR transition. No games, MPS, or game-weight steps.

Toy Adam steps populate moments only. The real-checkpoint test loads the accepted
parent model and Adam tensors on CPU; it does not restore the MPS sampling RNG.
"""
from __future__ import annotations

import ast
import builtins
import copy
import importlib.util
import json
import random
import subprocess
import sys
import symtable
from pathlib import Path

import numpy as np
import pytest
import torch

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PROPOSED = HERE / "proposed-adapter"
FROZEN_RUNNER = ROOT / "learning/runs/v2/D2-best180-branch-prepare-luna-20261026-r1/runner.py"
RUNTIME = ROOT / "learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime"
PARENT = ROOT / "learning/runs/v2/D2-gradient-alignment-20261025-r2/checkpoint-000180-candidate.pt"
PARENT_CONFIG = ROOT / "learning/runs/v2/milestone3-D2-freeze-r1/D2-config.json"
DRAFT_ARM_CONFIG = HERE / "draft-arm-config-lr1e-4.json"
DIFF = HERE / "arm-adapter.diff"

sys.path.insert(0, str(PROPOSED))
import resume_lr_transition as lrt  # noqa: E402
from resume_lr_transition import (ARM_LR, DECLARED_TRANSITION, PARENT_LR,  # noqa: E402
                                  apply_resume_lr_override, assert_effective_lr,
                                  fingerprint, guarded_update, sha256_file,
                                  transition_record, validate_arm_binding,
                                  validate_config_transition, without_group_lr)

ARM_SHA = "f858a63c324fc312f794c0423aa56db2daf60793b62990cd51fa400afe3af628"
PARENT_CONFIG_SHA = lrt.PARENT_CONFIG_SHA256
PARENT_SHA = lrt.PARENT_CHECKPOINT_SHA256


def load_frozen_runner():
    spec = importlib.util.spec_from_file_location("frozen_d2_runner", FROZEN_RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot_rng():
    return {"python": random.getstate(), "numpy": np.random.get_state(),
            "torch_cpu": torch.get_rng_state().clone()}


def make_toy_restored(seed=0):
    """Toy Linear model with populated Adam moments; restored into a fresh Adam at 3e-4."""
    torch.manual_seed(seed)
    model = torch.nn.Linear(3, 2)
    trained = torch.optim.Adam(model.parameters(), lr=PARENT_LR, eps=1e-5)
    model(torch.ones(2, 3)).sum().backward()
    trained.step()
    trained.zero_grad(set_to_none=True)
    parent_state = copy.deepcopy(trained.state_dict())
    restored = torch.optim.Adam(model.parameters(), lr=PARENT_LR, eps=1e-5)
    restored.load_state_dict(copy.deepcopy(parent_state))
    return model, restored, parent_state


def registration(config_sha=ARM_SHA):
    return {"parent_config_sha256": PARENT_CONFIG_SHA, "config_sha256": config_sha,
            "parent": {"sha256": PARENT_SHA, "terminal_receipt_sha256": lrt.PARENT_RECEIPT_SHA256,
                       "registration_sha256": lrt.PARENT_REGISTRATION_SHA256, "completed_updates": 180},
            "arm_transition": copy.deepcopy(DECLARED_TRANSITION)}


def identities():
    return {"parent_config_file_sha256": PARENT_CONFIG_SHA, "arm_config_file_sha256": ARM_SHA,
            "parent_checkpoint_sha256": PARENT_SHA}


def mutate(config, path, value):
    result = copy.deepcopy(config)
    node = result
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return result


@pytest.fixture(scope="module")
def parent_config():
    return json.loads(PARENT_CONFIG.read_text())


# ---- shared primitives --------------------------------------------------------

def test_fingerprint_matches_frozen_runner_on_toy_and_nested_values():
    frozen = load_frozen_runner()
    _, optimizer, _ = make_toy_restored()
    samples = [optimizer.state_dict(), {"a": (1, 2.5, None, "x")}, [torch.arange(4.0)], np.arange(3)]
    for sample in samples:
        assert fingerprint(sample) == frozen.fingerprint(sample)


def test_without_group_lr_strips_only_lr_and_does_not_mutate_input():
    _, optimizer, _ = make_toy_restored()
    state = optimizer.state_dict()
    before = fingerprint(state)
    stripped = without_group_lr(state)
    assert all("lr" not in group for group in stripped["param_groups"])
    assert stripped["param_groups"][0]["eps"] == 1e-5 and stripped["param_groups"][0]["betas"] == (0.9, 0.999)
    assert stripped["state"] is state["state"]
    assert fingerprint(state) == before
    assert state["param_groups"][0]["lr"] == PARENT_LR


def test_without_group_lr_rejects_group_without_lr():
    with pytest.raises(ValueError, match="lacks lr"):
        without_group_lr({"param_groups": [{"eps": 1e-5}], "state": {}})


# ---- declared config and registration transition -----------------------------

def test_draft_arm_config_is_bound_by_file_hash_and_differs_only_in_learning_rate(parent_config):
    assert sha256_file(DRAFT_ARM_CONFIG) == ARM_SHA
    arm = json.loads(DRAFT_ARM_CONFIG.read_text())
    assert validate_config_transition(parent_config, arm) == {
        "changed_config_fields": ["ppo.learning_rate"], "parent_lr": PARENT_LR, "arm_lr": ARM_LR}
    assert sha256_file(PARENT_CONFIG) == PARENT_CONFIG_SHA


@pytest.mark.parametrize("path,value,match", [
    (("batch_size",), 65, "outside ppo.learning_rate"),
    (("batch_size",), 64.0, "outside ppo.learning_rate"),       # typed: 64.0 is not 64
    (("ppo", "gamma"), 0.99, "outside ppo.learning_rate"),
    (("ppo", "ent_coef"), 0.02, "outside ppo.learning_rate"),
    (("device",), "cpu", "outside ppo.learning_rate"),
    (("excluded_seed_ranges", 0, 0), 2952790017, "outside ppo.learning_rate"),
    (("phase_settings", "run_seed"), 1, "outside ppo.learning_rate"),
    (("parent_checkpoint_sha256",), PARENT_SHA, "outside ppo.learning_rate"),
    (("ppo", "learning_rate"), 0.0002, "Arm config learning rate differs"),
])
def test_extra_config_mutation_rejected(parent_config, path, value, match):
    arm = mutate(mutate(parent_config, ("ppo", "learning_rate"), ARM_LR), path, value)
    with pytest.raises(ValueError, match=match):
        validate_config_transition(parent_config, arm)


def test_config_transition_rejects_added_top_level_or_ppo_key(parent_config):
    arm = mutate(parent_config, ("ppo", "learning_rate"), ARM_LR)
    arm["extra_top"] = 1
    with pytest.raises(ValueError, match="outside ppo.learning_rate"):
        validate_config_transition(parent_config, arm)
    arm = mutate(parent_config, ("ppo", "learning_rate"), ARM_LR)
    arm["ppo"]["max_steps"] = 1
    with pytest.raises(ValueError, match="outside ppo.learning_rate"):
        validate_config_transition(parent_config, arm)


def test_arm_binding_accepts_declared_identity():
    binding = validate_arm_binding(registration(), parent_config_file_sha256=PARENT_CONFIG_SHA,
                                   arm_config_file_sha256=ARM_SHA)
    assert binding["parent_config_file_sha256"] == PARENT_CONFIG_SHA and binding["arm_config_file_sha256"] == ARM_SHA
    assert binding["parent_checkpoint_sha256"] == PARENT_SHA


@pytest.mark.parametrize("mutator,kwargs,match", [
    (lambda r: r, {"parent_config_file_sha256": "0" * 64}, "Parent config file identity"),
    (lambda r: r.update(parent_config_sha256="0" * 64), {}, "Parent config file identity"),
    (lambda r: r, {"arm_config_file_sha256": "1" * 64}, "Arm config file identity"),
    (lambda r: r.update(config_sha256=PARENT_CONFIG_SHA), {"arm_config_file_sha256": PARENT_CONFIG_SHA},
     "equals the parent config"),
    (lambda r: r["parent"].update(sha256="0" * 64), {}, "parent checkpoint/receipt"),
    (lambda r: r["parent"].update(terminal_receipt_sha256="0" * 64), {}, "parent checkpoint/receipt"),
    (lambda r: r["parent"].update(registration_sha256="0" * 64), {}, "parent checkpoint/receipt"),
    (lambda r: r["parent"].update(completed_updates=228), {}, "parent checkpoint/receipt"),
    (lambda r: r["arm_transition"].update(effective_lr=0.0002), {}, "Registered LR transition differs"),
    (lambda r: r["arm_transition"]["changed_fields"].append("optimizer.param_groups[*].eps"), {},
     "Registered LR transition differs"),
    (lambda r: r.pop("arm_transition"), {}, "Registered LR transition differs"),
])
def test_arm_binding_rejects_wrong_hashes_and_transition(mutator, kwargs, match):
    reg = registration()
    mutator(reg)
    args = {"parent_config_file_sha256": PARENT_CONFIG_SHA, "arm_config_file_sha256": ARM_SHA}
    args.update(kwargs)
    with pytest.raises(ValueError, match=match):
        validate_arm_binding(reg, **args)


# ---- optimizer transition (toy moments only; no game weights) ----------------

def test_valid_transition_keeps_moments_model_rng_and_mode_and_asserts_before_callback():
    model, optimizer, parent_state = make_toy_restored()
    assert any(torch.count_nonzero(s["exp_avg"]) > 0 for s in optimizer.state_dict()["state"].values())
    model_before = fingerprint(model.state_dict())
    moments_before = fingerprint(without_group_lr(optimizer.state_dict()))
    full_before_state = optimizer.state_dict()
    rng_before = snapshot_rng()
    training_before, grad_before = model.training, torch.is_grad_enabled()

    delta = apply_resume_lr_override(optimizer, ARM_LR, copy.deepcopy(DECLARED_TRANSITION))
    after_state = optimizer.state_dict()

    seen = {}

    def simulated_update(opt, marker):
        seen["lr"] = [group["lr"] for group in opt.param_groups]
        return {"simulated": marker}

    assert guarded_update(optimizer, ARM_LR, simulated_update, optimizer, "update-1") == {"simulated": "update-1"}
    assert seen["lr"] == [ARM_LR]
    assert fingerprint(model.state_dict()) == model_before
    assert fingerprint(without_group_lr(optimizer.state_dict())) == moments_before
    after_rng = snapshot_rng()
    assert fingerprint(after_rng) == fingerprint(rng_before)
    assert model.training == training_before and torch.is_grad_enabled() == grad_before

    record = transition_record(full_before_state, after_state, delta, identities())
    assert record["parent_optimizer_fingerprint"] == fingerprint(parent_state)
    assert record["effective_optimizer_fingerprint"] != record["parent_optimizer_fingerprint"]
    assert (record["parent_optimizer_fingerprint_excluding_lr"]
            == record["effective_optimizer_fingerprint_excluding_lr"] == moments_before)
    assert record["per_group_lr"] == [{"index": 0, "before": PARENT_LR, "after": ARM_LR}]
    assert record["non_lr_fields_changed"] == []
    assert record["arm_config_file_sha256"] == ARM_SHA and record["parent_config_file_sha256"] == PARENT_CONFIG_SHA


def test_invalid_transitions_leave_optimizer_unchanged():
    cases = {
        "declared_transition_changed": (lambda: dict(DECLARED_TRANSITION, effective_lr=0.0002), ARM_LR,
                                        "Registered LR transition differs"),
        "config_lr_2e-4": (lambda: copy.deepcopy(DECLARED_TRANSITION), 0.0002, "exactly 0.0001"),
        "config_lr_string": (lambda: copy.deepcopy(DECLARED_TRANSITION), "0.0001", "exactly 0.0001"),
        "config_lr_int_zero": (lambda: copy.deepcopy(DECLARED_TRANSITION), 0, "exactly 0.0001"),
    }
    for name, (transition, config_lr, match) in cases.items():
        _, optimizer, _ = make_toy_restored()
        before_fp, before_lrs = fingerprint(optimizer.state_dict()), [g["lr"] for g in optimizer.param_groups]
        with pytest.raises(ValueError, match=match):
            apply_resume_lr_override(optimizer, config_lr, transition())
        assert fingerprint(optimizer.state_dict()) == before_fp, name
        assert [g["lr"] for g in optimizer.param_groups] == before_lrs, name


def test_mismatched_restored_group_lr_rejected_with_no_partial_write():
    model = torch.nn.Linear(2, 2)
    optimizer = torch.optim.Adam([{"params": [model.weight], "lr": PARENT_LR},
                                  {"params": [model.bias], "lr": 9e-4}], eps=1e-5)
    before_fp = fingerprint(optimizer.state_dict())
    with pytest.raises(ValueError, match="differs from 0.0003 at group 1"):
        apply_resume_lr_override(optimizer, ARM_LR, copy.deepcopy(DECLARED_TRANSITION))
    assert optimizer.param_groups[0]["lr"] == PARENT_LR
    assert fingerprint(optimizer.state_dict()) == before_fp


def test_post_override_group_drift_detected_before_callback():
    _, optimizer, _ = make_toy_restored()
    apply_resume_lr_override(optimizer, ARM_LR, copy.deepcopy(DECLARED_TRANSITION))
    optimizer.param_groups[0]["lr"] = PARENT_LR
    calls = []
    with pytest.raises(ValueError, match="differs at group 0"):
        guarded_update(optimizer, ARM_LR, lambda: calls.append("update"))
    assert calls == []


def test_load_state_dict_after_override_is_detected_before_callback():
    _, optimizer, parent_state = make_toy_restored()
    apply_resume_lr_override(optimizer, ARM_LR, copy.deepcopy(DECLARED_TRANSITION))
    optimizer.load_state_dict(copy.deepcopy(parent_state))
    assert optimizer.param_groups[0]["lr"] == PARENT_LR
    calls = []
    with pytest.raises(ValueError, match="differs at group 0"):
        guarded_update(optimizer, ARM_LR, lambda: calls.append("update"))
    assert calls == []


def test_assert_effective_lr_rejects_nonfloat_expected_value():
    _, optimizer, _ = make_toy_restored()
    with pytest.raises(ValueError, match="positive float"):
        assert_effective_lr(optimizer, 0)


# ---- real accepted parent, CPU model and Adam tensors only -------------------

def test_real_accepted_parent_cpu_model_and_adam_then_hook_only_changes_lr():
    sys.path.insert(0, str(RUNTIME))
    from dodge_rl import checkpoints as ckpt
    from dodge_rl.models.teacher import OmniscientEntityTeacher

    sidecar = Path(str(PARENT) + ".json")
    before_files = (sha256_file(PARENT), sha256_file(sidecar))
    frozen = load_frozen_runner()
    state = ckpt.load_checkpoint(PARENT, expected_sha256=PARENT_SHA)
    ckpt.require_complete_update(state)
    frozen.validate_parent_checkpoint_for_restore(state, frozen.PARENT_SHA)

    model = OmniscientEntityTeacher().to(device="cpu", dtype=torch.float32)
    optimizer = torch.optim.Adam(model.parameters(), lr=PARENT_LR, eps=1e-5)
    # Frozen restore_learner needs the MPS sampling RNG and is intentionally not used here.
    model.load_state_dict(state["model"], strict=True)
    optimizer.load_state_dict(state["optimizer"])
    assert fingerprint(model.state_dict()) == fingerprint(state["model"])
    assert fingerprint(without_group_lr(optimizer.state_dict())) == fingerprint(without_group_lr(state["optimizer"]))
    assert all(group["lr"] == PARENT_LR for group in optimizer.param_groups)

    model_before = fingerprint(model.state_dict())
    full_before_state = optimizer.state_dict()
    moments_before = fingerprint(without_group_lr(full_before_state))
    rng_before = snapshot_rng()
    training_before = model.training

    reg = registration(ARM_SHA)
    identity = validate_arm_binding(reg, parent_config_file_sha256=sha256_file(PARENT_CONFIG),
                                    arm_config_file_sha256=sha256_file(DRAFT_ARM_CONFIG))
    assert identity["parent_checkpoint_sha256"] == sha256_file(PARENT)
    delta = apply_resume_lr_override(optimizer, ARM_LR, reg["arm_transition"])
    record = transition_record(full_before_state, optimizer.state_dict(), delta, identity)

    assert fingerprint(model.state_dict()) == model_before
    assert fingerprint(without_group_lr(optimizer.state_dict())) == moments_before
    assert fingerprint(snapshot_rng()) == fingerprint(rng_before)
    assert model.training == training_before
    assert_effective_lr(optimizer, ARM_LR)
    assert record["per_group_lr"] == [{"index": 0, "before": PARENT_LR, "after": ARM_LR}]
    assert record["parent_optimizer_fingerprint_excluding_lr"] == record["effective_optimizer_fingerprint_excluding_lr"]
    assert record["parent_checkpoint_sha256"] == PARENT_SHA
    assert before_files == (sha256_file(PARENT), sha256_file(sidecar))


# ---- source integration without running the worker ---------------------------

def undefined_names(source: str, filename: str) -> list[str]:
    top = symtable.symtable(source, filename, "exec")
    module_defined = {s.get_name() for s in top.get_symbols()
                      if s.is_assigned() or s.is_imported() or s.is_namespace()}

    def unresolved(name):
        return name not in module_defined and not hasattr(builtins, name) and not name.startswith("__")

    problems = [f"<module>:{s.get_name()}" for s in top.get_symbols()
                if s.is_referenced() and unresolved(s.get_name())]

    def walk(table):
        for sym in table.get_symbols():
            if sym.is_referenced() and sym.is_global() and unresolved(sym.get_name()):
                problems.append(f"{table.get_name()}:{sym.get_name()}")
        for child in table.get_children():
            walk(child)

    for child in top.get_children():
        walk(child)
    return sorted(set(problems))


def test_undefined_name_checker_catches_the_prototype_defect():
    assert undefined_names("def f():\n    return without_group_lr(1)\n", "probe.py") == ["f:without_group_lr"]


def test_proposed_runner_has_no_undefined_names_and_frozen_baseline_is_clean():
    assert undefined_names(FROZEN_RUNNER.read_text(), str(FROZEN_RUNNER)) == []
    assert undefined_names((PROPOSED / "runner.py").read_text(), "runner.py") == []


def test_proposed_runner_top_level_imports_are_stdlib_plus_shared_module():
    tree = ast.parse((PROPOSED / "runner.py").read_text())
    modules = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            modules |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            modules.add(node.module.split(".")[0])
    assert modules <= set(sys.stdlib_module_names) | {"resume_lr_transition"}
    assert "resume_lr_transition" in modules


def test_proposed_runner_imports_as_module_with_stdlib_only_surface():
    spec = importlib.util.spec_from_file_location("proposed_arm_runner", PROPOSED / "runner.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.apply_resume_lr_override is lrt.apply_resume_lr_override
    assert module.guarded_update is lrt.guarded_update
    assert module.ARM_LR == ARM_LR and module.CONFIG_SHA == PARENT_CONFIG_SHA


def _function(tree, name):
    return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)


def _call_lines(scope, name):
    lines = []
    for node in ast.walk(scope):
        if isinstance(node, ast.Call):
            func = node.func
            if (isinstance(func, ast.Name) and func.id == name) or (isinstance(func, ast.Attribute) and func.attr == name):
                lines.append(node.lineno)
    return sorted(lines)


def test_proposed_runner_orders_validation_override_assertions_and_update():
    tree = ast.parse((PROPOSED / "runner.py").read_text())
    worker = _function(tree, "worker")
    evaluate_at = _function(worker, "evaluate_at")

    load_line = _call_lines(worker, "load_registration")
    apply_lines = _call_lines(worker, "apply_resume_lr_override")
    guarded_lines = _call_lines(worker, "guarded_update")
    assert len(load_line) == len(apply_lines) == len(guarded_lines) == 1
    assert load_line[0] < apply_lines[0] < guarded_lines[0]
    assert any(apply_lines[0] < line < guarded_lines[0] for line in _call_lines(worker, "assert_effective_lr"))

    assert _call_lines(worker, "ppo_update") == []
    guard_call = next(n for n in ast.walk(worker) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "guarded_update")
    assert ast.unparse(guard_call.args[1]) == "ARM_LR" and ast.unparse(guard_call.args[2]) == "ppo_update"
    assert any(isinstance(loop, ast.For) and any(n is guard_call for n in ast.walk(loop)) for loop in ast.walk(worker))
    assert _call_lines(worker, "collect_rollout")[0] < guarded_lines[0]

    apply_call = next(n for n in ast.walk(worker) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "apply_resume_lr_override")
    assert ast.unparse(apply_call.args[0]) == "optimizer"
    assert ast.unparse(apply_call.args[1]) == "config['ppo']['learning_rate']"
    assert ast.unparse(apply_call.args[2]) == "reg['arm_transition']"

    assert all(line < apply_lines[0] for line in _call_lines(worker, "load_state_dict"))
    record_lines = _call_lines(worker, "transition_record")
    assert record_lines and all(line > apply_lines[0] for line in record_lines)

    save_checkpoint_line = _call_lines(evaluate_at, "save_checkpoint")[0]
    assert any(line < save_checkpoint_line for line in _call_lines(evaluate_at, "assert_effective_lr"))

    assert '"lr-transition.json"' in (PROPOSED / "runner.py").read_text()
    assert "validate_config_transition" in ast.unparse(_function(tree, "load_registration"))
    assert "validate_arm_binding" in ast.unparse(_function(tree, "load_registration"))


def test_arm_diff_applies_to_frozen_runner_copy_and_yields_proposed_file(tmp_path):
    target = tmp_path / "learning/runs/v2/D2-best180-branch-prepare-luna-20261026-r1"
    target.mkdir(parents=True)
    (target / "runner.py").write_bytes(FROZEN_RUNNER.read_bytes())
    subprocess.run(["git", "apply", "--check", str(DIFF)], cwd=tmp_path, check=True)
    subprocess.run(["git", "apply", str(DIFF)], cwd=tmp_path, check=True)
    assert sha256_file(target / "runner.py") == sha256_file(PROPOSED / "runner.py")
    assert sha256_file(FROZEN_RUNNER) == "8807b5200f10d6d8ba5414a793a1e44ebb34479744744992ef4f5adf0513637b"
