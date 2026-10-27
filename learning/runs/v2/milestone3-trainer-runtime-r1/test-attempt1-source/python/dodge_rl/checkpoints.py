"""Atomic immutable checkpoints with strict fresh-environment lineage."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import random
import tempfile

import numpy as np
import torch

from .identity import check_same_run, file_hash, identity_hash, read_protocol, require

REJECTED_PARENT_TAGS = {"interrupted_mid_update", "failure", "timeout", "probe_diagnostic"}


def capture_rng(device: str | torch.device = "cpu", numpy_generator=None) -> dict:
    device = torch.device(device)
    return {"python": random.getstate(), "numpy_global": np.random.get_state(),
            "numpy_generator": None if numpy_generator is None else copy.deepcopy(numpy_generator.bit_generator.state),
            "torch_cpu": torch.get_rng_state().clone(),
            "torch_mps": torch.mps.get_rng_state().clone() if device.type == "mps" else None,
            "sampling_backend": f"torch_global_{device.type}"}


def restore_rng(state: dict, device: str | torch.device = "cpu", numpy_generator=None) -> None:
    device = torch.device(device)
    require(state["sampling_backend"] == f"torch_global_{device.type}", "Sampling RNG backend changed")
    random.setstate(state["python"])
    np.random.set_state(state["numpy_global"])
    torch.set_rng_state(state["torch_cpu"].cpu())
    if state["numpy_generator"] is not None:
        require(numpy_generator is not None, "Owned NumPy generator was not supplied for restore")
        numpy_generator.bit_generator.state = copy.deepcopy(state["numpy_generator"])
    if device.type == "mps":
        require(state["torch_mps"] is not None, "MPS RNG state missing")
        torch.mps.set_rng_state(state["torch_mps"].cpu())


def _cpu_copy(value):
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().clone()
    if isinstance(value, dict):
        return {k: _cpu_copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_cpu_copy(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_cpu_copy(v) for v in value)
    return copy.deepcopy(value)


def episode_resume_state(env, batch_size: int) -> tuple[list[int], list[dict]]:
    infos = copy.deepcopy(env.episode_info())
    next_indices = env.batch_info()["next_episode_indices"]
    require(len(infos) == len(next_indices) == batch_size, "Resume slot count changed")
    abandoned = []
    for index, (info, next_index) in enumerate(zip(infos, next_indices, strict=True)):
        require(type(next_index) is int and next_index == info["seed"]["episode"] + 1 and next_index < 2**64,
                "Next episode index is missing, exhausted, or not current+1")
        if not info["terminated"] and not info["truncated"]:
            abandoned.append({"kind": "abandoned_on_fresh_env_resume", "slot": index,
                              "seed": info["seed"], "gameplay_frames": info["gameplay_frames"],
                              "score_raw_fixed": info["score_raw_fixed"]})
    return list(next_indices), abandoned


def make_state(model, optimizer, identity: dict, counters: dict, *, env=None,
               tag: str = "periodic", progress=None, device="cpu", parent_sha256=None) -> dict:
    batch_size = identity["config"]["batch_size"]
    next_indices, abandoned = ([0] * batch_size, []) if env is None else episode_resume_state(env, batch_size)
    return {"version": "teacher_checkpoint_v1", "identity": identity,
            "identity_sha256": identity_hash(identity), "model": _cpu_copy(model.state_dict()),
            "optimizer": _cpu_copy(optimizer.state_dict()), "rng": capture_rng(device),
            "counters": copy.deepcopy(counters), "next_episode_indices": next_indices,
            "abandoned_episodes": abandoned, "resume_mode": "fresh_env", "tag": tag,
            "update_progress": copy.deepcopy(progress or {}), "parent_checkpoint_sha256": parent_sha256}


def save_checkpoint(path: Path, state: dict) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.exists(), f"Checkpoint already exists: {path}")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".partial", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            torch.save(state, stream)
            stream.flush()
            os.fsync(stream.fileno())
        # Publishing a hard link is atomic and refuses an existing destination,
        # unlike a check followed by a replacing rename.
        os.link(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return file_hash(path)


def load_checkpoint(path: Path, expected_identity: dict | None = None,
                    expected_sha256: str | None = None) -> dict:
    path = Path(path)
    if expected_sha256 is not None:
        require(file_hash(path) == expected_sha256, "Checkpoint file hash mismatch")
    state = torch.load(path, map_location="cpu", weights_only=False)
    require(state["version"] == "teacher_checkpoint_v1" and state["resume_mode"] == "fresh_env",
            "Unknown checkpoint or resume format")
    require(identity_hash(state["identity"]) == state["identity_sha256"], "Checkpoint identity hash mismatch")
    if expected_identity is not None:
        check_same_run(state["identity"], expected_identity)
    return state


def restore_learner(state: dict, model, optimizer, device="cpu") -> None:
    model.load_state_dict(state["model"], strict=True)
    optimizer.load_state_dict(state["optimizer"])
    restore_rng(state["rng"], device)


def evaluation_path(checkpoint_path: Path) -> Path:
    return Path(str(checkpoint_path) + ".evaluation.json")


def validate_transition(parent_path: Path, target_identity: dict) -> tuple[dict, dict]:
    parent_hash = file_hash(parent_path)
    parent = load_checkpoint(parent_path)
    require(parent["tag"] not in REJECTED_PARENT_TAGS, "Interrupted/failure/probe checkpoint cannot advance")
    old_identity = copy.deepcopy(parent["identity"])
    new_identity = copy.deepcopy(target_identity)
    old_cfg, new_cfg = old_identity.pop("config"), new_identity.pop("config")
    old_identity.pop("config_sha256")
    new_identity.pop("config_sha256")
    require(old_identity == new_identity, "Transition changed source/runtime/architecture/reward/gate identity")
    protocol = read_protocol()
    require([old_cfg["phase"], new_cfg["phase"]] in protocol["transitions"], "Unregistered curriculum transition")
    require(new_cfg["parent_checkpoint_sha256"] == parent_hash, "Transition parent hash differs")
    allowed = {"phase", "phase_settings", "parent_checkpoint_sha256"}
    require({k: v for k, v in old_cfg.items() if k not in allowed}
            == {k: v for k, v in new_cfg.items() if k not in allowed},
            "Transition changed learner/device/environment settings")
    # Config validation checks the entire target phase row, including fixed budget.
    from .identity import validate_config
    validate_config(new_cfg)
    validate_config(old_cfg)
    certificate = json.loads(evaluation_path(parent_path).read_text())
    require(certificate["checkpoint_sha256"] == parent_hash
            and certificate["phase"] == old_cfg["phase"]
            and certificate["complete"] is True and certificate["passed"] is True,
            "Transition parent has no completed passing hash-bound evaluation")
    from .dev_eval import pilot_improved, progress_passed
    if old_cfg["phase"] == "pilot":
        require(pilot_improved(certificate["before"], certificate["evaluations"]["D1"])
                and certificate["actor_gradient_seen"] and certificate["critic_gradient_seen"]
                and certificate["completed_training_updates"] > 0,
                "Pilot transition proof does not satisfy registered improvement/gradient conditions")
    else:
        require(progress_passed(old_cfg["phase"], certificate["evaluations"]),
                "Curriculum transition proof does not meet progress gates")
    require(not parent["update_progress"].get("in_update", False), "Parent update was interrupted")
    return parent, certificate
