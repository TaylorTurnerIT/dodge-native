"""Explicit name-based checkpoint420 Adam migration; no RNG/environment restore."""

import copy

import torch

from .models.teacher import OmniscientEntityTeacher


def migrate_adam(old_state, legacy, target, *, learning_rate, adam_eps):
    """Decode legacy serialized IDs using its pinned constructor, then map names.

    Old checkpoints omit param_names. Callers must verify checkpoint and trusted
    legacy source fingerprints before supplying this source-constructor binding.
    No state is copied by target position; new branch/gate state starts absent.
    """
    if not isinstance(legacy, OmniscientEntityTeacher):
        raise TypeError("Trusted legacy constructor required")
    groups = old_state["param_groups"]
    names = dict(legacy.named_parameters())
    if len(groups) != 1 or len(groups[0]["params"]) != len(names):
        raise ValueError("Expected one complete legacy Adam group")
    old_ids = groups[0]["params"]
    if len(set(old_ids)) != len(old_ids) or set(old_state["state"]) != set(old_ids):
        raise ValueError("Legacy Adam state coverage differs")
    declared_names = groups[0].get("param_names", list(names))
    if declared_names != list(names):
        raise ValueError("Legacy Adam name binding differs from pinned constructor")
    state_by_name = dict(zip(declared_names, (old_state["state"][i] for i in old_ids), strict=True))
    for name, parameter in names.items():
        entry = state_by_name[name]
        if set(entry) != {"step", "exp_avg", "exp_avg_sq"}:
            raise ValueError("Unsupported Adam state fields")
        for key in ("exp_avg", "exp_avg_sq"):
            if entry[key].shape != parameter.shape or not bool(torch.isfinite(entry[key]).all()):
                raise ValueError("Adam moment shape/finiteness differs: " + name)
        if entry["step"].numel() != 1 or not bool(torch.isfinite(entry["step"]).all()) or entry["step"].item() <= 0:
            raise ValueError("Adam step counter differs")
    optimizer = torch.optim.Adam(target.parameters(), lr=learning_rate, eps=adam_eps)
    fresh = optimizer.state_dict()
    target_names = [name for name, _ in target.named_parameters()]
    ids_by_name = dict(zip(target_names, fresh["param_groups"][0]["params"], strict=True))
    prefix = "legacy." if hasattr(target, "legacy") else ""
    mapped = {}
    for name, parameter in names.items():
        new_name = prefix + name
        actual = dict(target.named_parameters()).get(new_name)
        if actual is None or actual.shape != parameter.shape or not torch.equal(actual.detach().cpu(), parameter.detach().cpu()):
            raise ValueError("Target legacy parameter differs: " + new_name)
        mapped[ids_by_name[new_name]] = copy.deepcopy(state_by_name[name])
    group = copy.deepcopy(groups[0])
    group.pop("param_names", None)
    group.update(params=fresh["param_groups"][0]["params"], lr=learning_rate, eps=adam_eps)
    optimizer.load_state_dict({"state": mapped, "param_groups": [group]})
    target_parameters = dict(target.named_parameters())
    for name, original in state_by_name.items():
        actual = optimizer.state[target_parameters[prefix+name]]
        for field in ('step','exp_avg','exp_avg_sq'):
            if not torch.equal(actual[field].detach().cpu(),original[field].detach().cpu()):
                raise ValueError('Loaded Adam content differs: '+name+'/'+field)
    manifest = dict(legacy_serialized_id_to_name=dict(zip(map(str, old_ids), declared_names, strict=True)),
                    target_name_to_id=ids_by_name, preserved_legacy_parameters=len(names),
                    new_parameters_without_state=[n for n in target_names if not n.startswith(prefix) or
                                                  n.removeprefix(prefix) not in names],
                    rng_restored=False, simulator_restored=False)
    return optimizer, manifest
