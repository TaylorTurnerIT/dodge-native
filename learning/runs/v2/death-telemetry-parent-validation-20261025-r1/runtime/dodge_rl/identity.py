"""Frozen semantic identities and the registered M3 execution protocol."""
from __future__ import annotations

from dataclasses import asdict
import copy
from functools import lru_cache
import hashlib
import importlib
import json
from pathlib import Path
import platform
import sys

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = Path("docs/v2-m3-run-protocol.json")
PROTOCOL_SHA256 = "9e0d82028011f83e0cf6ddaef5f5e118591158d8a557f6698c82c150d5a69bab"
GATE_SHA256 = "e091f8a2fad0a307d289a6d306112606b15df8f8aa0f3a75707ac7cfb2cee803"
CONTRACT_SHA256 = "a1051d82527a9aec1f7967ff8ab217c30263240e032991aeff7b993fd975ba47"
FOUNDATION_PATH = Path("learning/runs/v2-orchestration/milestone2-acceptance-r2.json")
FOUNDATION_IDENTITY = Path("learning/runs/v2/milestone2-campaign-freeze-r4/frozen-identity.json")
EXTENSION_SHA256 = "967c7249acd52339d1818dcbe94e63ee734aea914c3497eb59a7e945a6e95583"
OBSERVATION_KEYS = ("global_feats", "entity_feats", "entity_types", "entity_mask")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def canonical_bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def identity_hash(value) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_protocol(root: Path = ROOT) -> dict:
    path = root / PROTOCOL_PATH
    require(file_hash(path) == PROTOCOL_SHA256, "Registered execution protocol changed")
    value = json.loads(path.read_text())
    require(value["qualification_sha256"] == GATE_SHA256, "Qualification definition changed")
    return value


def default_config(phase: str, device: str = "cpu", parent_sha256: str | None = None) -> dict:
    from .ppo import PPOConfig
    protocol = read_protocol()
    require(phase in protocol["seed_namespace_table"], "Unknown registered phase")
    require(device in {"cpu", "mps"}, "Device must be cpu or mps")
    if phase == "probe":
        require(device == "cpu", "Probe collects its frozen buffer on CPU before comparing devices")
    row = protocol["seed_namespace_table"][phase]
    if phase in {"D1", "D2", "D3"}:
        require(isinstance(parent_sha256, str) and len(parent_sha256) == 64,
                "Curriculum stages require a registered parent checkpoint hash")
    else:
        require(parent_sha256 is None, "Fresh probe/pilot cannot inherit checkpoint weights")
    return {
        "version": "teacher_registered_config_v1", "phase": phase, "device": device,
        "phase_settings": row, "protocol_sha256": PROTOCOL_SHA256,
        "qualification_sha256": GATE_SHA256, "contract_sha256": CONTRACT_SHA256,
        "parent_checkpoint_sha256": parent_sha256,
        "batch_size": protocol["training_batch_size"],
        "rollout_steps": protocol["rollout_decisions"],
        "num_threads": protocol["training_threads"], "chunk_size": protocol["training_chunk_size"],
        "training_raw_frame_cap": 18000, "action_repeat": 4,
        "powerups_enabled": True, "render_pixels": False, "auxiliary_targets": False,
        "excluded_seed_ranges": protocol["training_excluded_ranges"],
        "ppo": asdict(PPOConfig()), "dtype": "float32", "running_normalization": False,
        "probe_devices": ["cpu", "mps"] if phase == "probe" else [],
        "development_layout": protocol["development"]["environment_layout"],
        "sampling_backend": "torch_global_cpu" if phase == "probe" else f"torch_global_{device}",
    }


def validate_config(config: dict) -> dict:
    expected = default_config(config.get("phase"), config.get("device"),
                              config.get("parent_checkpoint_sha256"))
    require(config == expected, "Configuration differs from registered phase/defaults")
    return config


def source_inventory(root: Path = ROOT) -> dict[str, str]:
    paths = set()
    for base in (root / "python/dodge_rl", root / "python/tests", root / "crates"):
        for path in base.rglob("*"):
            relative = path.relative_to(base)
            if path.is_file() and not {"__pycache__", ".pytest_cache", "target", "build"}.intersection(relative.parts):
                if base.name == "dodge_rl" or path.suffix in {".py", ".rs", ".toml", ".lock"}:
                    paths.add(path)
    for name in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", ".cargo/config.toml",
                 "assets/dodge.p8", "python/pyproject.toml", "python/requirements-local-mac.txt",
                 "docs/SPEC_PRIVILEGED_VIT_RL.md", "docs/implementation-plan-v2.md",
                 "docs/v2-environment-contract.md", "docs/v2-teacher-training-plan.md",
                 "docs/v2-m3-component-contract.md", "docs/teacher-qualification-v2.json",
                 str(PROTOCOL_PATH)):
        path = root / name
        require(path.is_file(), f"Identity input missing: {name}")
        paths.add(path)
    return {str(path.relative_to(root)): file_hash(path) for path in sorted(paths)}


def foundation_identity(root: Path = ROOT) -> dict:
    acceptance = json.loads((root / FOUNDATION_PATH).read_text())
    require(acceptance["status"] == "M2_accepted_for_M3_implementation", "M2 is not accepted")
    old = json.loads((root / FOUNDATION_IDENTITY).read_text())
    require(file_hash(root / FOUNDATION_IDENTITY) == acceptance["frozen_identity_sha256"],
            "Accepted M2 identity document changed")
    native_inputs = {name: value for name, value in old["source_sha256"].items()
                     if name.startswith("crates/") or name in {
                         "Cargo.toml", "Cargo.lock", "rust-toolchain.toml", ".cargo/config.toml",
                         "assets/dodge.p8", "python/pyproject.toml", "python/requirements-local-mac.txt",
                         "python/dodge_rl/__init__.py"}}
    for name, value in native_inputs.items():
        require(file_hash(root / name) == value, f"Accepted native/build input changed: {name}")
    for name, value in old["binary_and_receipt_sha256"].items():
        require(file_hash(Path(name)) == value, f"Accepted binary/build receipt changed: {name}")
    extension = importlib.import_module("dodge_rl._native")
    path = Path(extension.__file__).resolve()
    require(file_hash(path) == EXTENSION_SHA256 == old["runtime"]["extension_sha256"],
            "Installed extension differs from accepted M2 binary")
    return {"acceptance_sha256": file_hash(root / FOUNDATION_PATH),
            "identity_sha256": acceptance["frozen_identity_sha256"],
            "native_inputs": native_inputs, "extension_path": str(path),
            "extension_sha256": EXTENSION_SHA256,
            "binary_and_receipt_sha256": old["binary_and_receipt_sha256"]}


@lru_cache(maxsize=1)
def _architecture_description() -> dict:
    from .models.teacher import OmniscientEntityTeacher
    rng = torch.get_rng_state()
    try:
        return OmniscientEntityTeacher().architecture_description()
    finally:
        torch.set_rng_state(rng)


def build_identity(config: dict, root: Path = ROOT) -> dict:
    from .ppo import PPOConfig
    validate_config(config)
    protocol = read_protocol(root)
    require(file_hash(root / "docs/teacher-qualification-v2.json") == GATE_SHA256,
            "Registered qualification JSON changed")
    require(file_hash(root / "docs/v2-m3-component-contract.md") == CONTRACT_SHA256,
            "Component contract changed")
    return {
        "version": "teacher_semantic_identity_v1", "config": config,
        "config_sha256": identity_hash(config), "sources": source_inventory(root),
        "foundation": foundation_identity(root), "architecture": copy.deepcopy(_architecture_description()),
        "ppo": PPOConfig(**config["ppo"]).description(),
        "reward_version": "score_plus_0.01_alive_minus_5_termination_v1",
        "observation_schema_version": "dodge_global14_entity80x16_v2_r2",
        "seed_stream_version": protocol["seed_stream_version"],
        "seed_exclusion_version": protocol["seed_exclusion_version"],
        "effective_excluded_seed_ranges": protocol["training_excluded_ranges"],
        "runtime": {"python": sys.version, "interpreter": str(Path(sys.executable).resolve()),
                    "interpreter_sha256": file_hash(Path(sys.executable).resolve()),
                    "torch": str(torch.__version__), "numpy": np.__version__,
                    "platform": platform.platform(), "machine": platform.machine(),
                    "mps_available": bool(torch.backends.mps.is_available())},
    }


def check_same_run(saved: dict, current: dict) -> None:
    require(saved == current, "Same-run identity mismatch")


def check_frozen(identity_path: Path, expected_document_hash: str, config: dict,
                 root: Path = ROOT) -> dict:
    raw = identity_path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected_document_hash, "Frozen identity document changed")
    frozen = json.loads(raw)
    check_same_run(frozen, build_identity(config, root))
    require(file_hash(identity_path) == expected_document_hash, "Identity changed during verification")
    return frozen


def training_env_config(config: dict, initial_episode_indices=None) -> dict:
    validate_config(config)
    row = config["phase_settings"]
    value = {"batch_size": config["batch_size"], "action_repeat": 4,
             "difficulty": row["difficulty"], "patterns_enabled": row["patterns_enabled"],
             "powerups_enabled": True, "raw_frame_cap": 18000,
             "num_threads": config["num_threads"], "chunk_size": config["chunk_size"],
             "render_pixels": False, "auxiliary_targets": False, "run_seed": row["run_seed"],
             "excluded_seed_ranges": [tuple(pair) for pair in config["excluded_seed_ranges"]]}
    if initial_episode_indices is not None:
        require(len(initial_episode_indices) == config["batch_size"]
                and all(type(i) is int and 0 <= i < 2**64 for i in initial_episode_indices),
                "Invalid fresh-environment episode indices")
        value["initial_episode_indices"] = list(initial_episode_indices)
    return value


def verify_training_env(env, config: dict, initial_episode_indices=None) -> dict:
    protocol = read_protocol()
    metadata = env.batch_info()
    require(metadata["effective_excluded_seed_ranges"] == [tuple(x) for x in protocol["training_excluded_ranges"]]
            or metadata["effective_excluded_seed_ranges"] == protocol["training_excluded_ranges"],
            "Effective training exclusions differ from B/D/E")
    for key in ("seed_stream_version", "seed_exclusion_version"):
        require(metadata[key] == protocol[key], f"Environment {key} differs")
    require(metadata["seed_mode"] == {"mode": "training", "run_seed": config["phase_settings"]["run_seed"]},
            "Training seed namespace differs")
    expected = [0] * config["batch_size"] if initial_episode_indices is None else list(initial_episode_indices)
    require(metadata["initial_episode_indices"] == expected, "Initial episode indices were not echoed")
    require(metadata["batch_size"] == config["batch_size"] and metadata["action_repeat"] == 4,
            "Environment batch/action repeat differs")
    infos = env.episode_info()
    require(len(infos) == len(expected), "Episode metadata count differs")
    for slot, (info, episode) in enumerate(zip(infos, expected, strict=True)):
        seed = info["seed"]
        require(seed["slot"] == slot and seed["episode"] == episode and not seed["evaluation"],
                "Fresh training slot identity differs")
        require(all(not low <= seed["actual_seed"] <= high for low, high in protocol["training_excluded_ranges"]),
                "Reserved seed constructed")
        require(info["startup_frames"] == 13 and info["gameplay_frames"] == 0,
                "Fresh training environment did not start correctly")
    return metadata
