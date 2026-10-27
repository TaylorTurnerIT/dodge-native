"""Preparation-only paired endpoint evaluator. Import has no runtime side effects."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Callable, Iterable

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "seed-manifest.json"
EXPECTED_MANIFEST_SHA256 = "e11e9d6accb79fcafd1b0e6049c322356edf16601007d2af62da6b59539c886c"
SEEDS = tuple(range(0xD0000040, 0xD0000080))
LABEL = "unselected training-excluded upper-D development block; prior nonuse not proven"
DEATH_CAUSES = ("normal_enemy", "kamikaze_enemy", "kamikaze_explosion",
                "static_pattern_rect", "moving_pattern_rect", "unknown")
UNAVAILABLE = "unavailable"
EXCLUDED_SEED_RANGES = ((2952790016, 2952791015), (3489660928, 3489661055), (3758096384, 3758097383))
CONSTANT = {
    "run_id": "D2-retained324-continuation-20261026-r1",
    "checkpoint_sha256": "e25117bf52f14629a3d2ffada319c49a10c6344763a25506a5f124a76a62199b",
    "endpoint_phase_update": 384,
    "cumulative_update": 432,
}

class ValidationError(ValueError):
    pass

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValidationError(message)

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def load_manifest(path: Path = MANIFEST) -> dict:
    raw = path.read_bytes()
    require(sha256(raw) == EXPECTED_MANIFEST_SHA256, "seed manifest byte SHA-256 differs")
    obj = json.loads(raw)
    require(obj.get("schema") == "paired_LR_supplemental_development_seed_manifest_v1", "manifest schema differs")
    require(obj.get("seed_class") == "upper_D64_unselected_development_namespace", "manifest seed class differs")
    require(obj.get("training_excluded") is True and obj.get("prior_nonuse_proven") is False
            and obj.get("qualification_or_sealed_claim") is False, "manifest claim limits differ")
    require(obj.get("seeds") == list(SEEDS), "manifest ordered seeds differ")
    require(len(set(obj["seeds"])) == 64 and all(type(s) is int and 0 <= s <= 0xffffffff for s in obj["seeds"]),
            "manifest seeds are not unique unsigned 32-bit integers")
    return obj

def _integer(value, name, minimum=0):
    require(type(value) is int and value >= minimum, f"{name} must be integer >= {minimum}")

def validate_rows(rows: Iterable[dict], manifest: dict | None = None, *, allow_unavailable: bool = True) -> list[dict]:
    manifest = manifest or load_manifest()
    rows = list(rows)
    require(len(rows) == 64, "evaluation must contain exactly 64 rows")
    require([r.get("seed") for r in rows] == manifest["seeds"], "rows missing, reordered, duplicated, or outside manifest")
    for row in rows:
        require(isinstance(row, dict), "evaluation row must be an object")
        _integer(row.get("seed"), "seed")
        _integer(row.get("episode_index"), "episode_index")
        require(row["episode_index"] == row["seed"] - SEEDS[0], "episode index/seed identity differs")
        for key in ("alive_frames", "gameplay_frames", "score_raw_fixed", "score_delta_sum_raw_fixed"):
            _integer(row.get(key), key)
        require(row["score_delta_sum_raw_fixed"] == row["score_raw_fixed"], "fixed score accumulation differs")
        require(row.get("startup_frames") == 13, "startup frame count differs")
        require(row["terminated"] != row["truncated"], "episode boundary flags invalid")
        require(row["gameplay_frames"] <= 18000, "gameplay frame cap exceeded")
        if row["terminated"]:
            require(row["alive_frames"] + 1 == row["gameplay_frames"], "fatal-frame conservation differs")
        else:
            require(row["gameplay_frames"] == row["alive_frames"] == 18000,
                    "truncation must occur at exact 18000-frame cap")
        require(type(row.get("terminated")) is bool and type(row.get("truncated")) is bool
                and row["terminated"] != row["truncated"], "episode boundary flags invalid")
        require(type(row.get("score")) in (int, float)
                and row["score"] == row["score_raw_fixed"] / 65536 and math.isfinite(row["score"]),
                "fixed-point score identity or finiteness differs")
        require("objective_return" in row, "objective return missing")
        expected = row["score_delta_sum_raw_fixed"] / 65536 + row["alive_frames"] / 100 - 5 * row["terminated"]
        require(type(row["objective_return"]) in (int, float) and math.isfinite(row["objective_return"])
                and math.isclose(row["objective_return"], expected, rel_tol=0, abs_tol=1e-9),
                "objective return identity differs")
        cause = row.get("death_cause")
        if row["terminated"]:
            require(cause in (*DEATH_CAUSES, UNAVAILABLE), "terminated row death cause unavailable/invalid")
            require(allow_unavailable or cause != UNAVAILABLE, "native evaluation requires death telemetry")
            require(row.get("fatal_gameplay_frame") is None or row["fatal_gameplay_frame"] == row["gameplay_frames"],
                    "fatal frame must equal terminal gameplay frame")
            if cause == UNAVAILABLE:
                require(row.get("fatal_gameplay_frame") is None and row.get("death_observed_lethal_contacts") is None,
                        "unavailable cause carries inferred telemetry")
            else:
                contacts = row.get("death_observed_lethal_contacts")
                require(type(row.get("fatal_gameplay_frame")) is int
                        and row["fatal_gameplay_frame"] == row["gameplay_frames"]
                        and isinstance(contacts, dict) and set(contacts) == set(DEATH_CAUSES)
                        and all(type(v) is int and v >= 0 for v in contacts.values())
                        and (cause == "unknown" or contacts[cause] >= 1), "death telemetry differs")
        else:
            require(cause is None and row.get("fatal_gameplay_frame") is None
                    and row.get("death_observed_lethal_contacts") is None, "truncated row has death telemetry")
    return rows

def summarize_arm(rows: Iterable[dict]) -> dict:
    rows = validate_rows(rows)
    ordered = sorted(rows, key=lambda r: (r["alive_frames"], r["seed"]))
    deaths = [r for r in rows if r["terminated"]]
    return {
        "complete": True, "episodes": 64, "mean_alive_frames": sum(r["alive_frames"] for r in rows) / 64,
        "bottom16_mean_Q1": sum(r["alive_frames"] for r in ordered[:16]) / 16,
        "top16_mean_Q4": sum(r["alive_frames"] for r in ordered[-16:]) / 16,
        "death_cause_counts": {c: sum(r["death_cause"] == c for r in deaths) for c in (*DEATH_CAUSES, UNAVAILABLE)},
        "truncations": sum(r["truncated"] for r in rows), "rows": rows,
    }

def paired_summary(constant_rows: Iterable[dict], linear_rows: Iterable[dict], *,
                   linear_endpoint: dict | None = None, constant_registration_sha256: str | None = None,
                   linear_registration_sha256: str | None = None) -> dict:
    c = validate_rows(constant_rows); l = validate_rows(linear_rows)
    require(isinstance(linear_endpoint, dict), "linear endpoint provenance required")
    validate_endpoint(linear_endpoint, "linear endpoint")
    for digest, label in ((constant_registration_sha256, "constant registration"),
                          (linear_registration_sha256, "linear registration")):
        require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
                f"{label} SHA-256 provenance missing")
    require(linear_endpoint["checkpoint_sha256"] != CONSTANT["checkpoint_sha256"]
            and linear_endpoint["run_id"] != CONSTANT["run_id"], "linear endpoint must differ from constant endpoint")
    require([r["seed"] for r in c] == [r["seed"] for r in l], "arms are not seed-aligned")
    differences = [{"seed": a["seed"], "linear_minus_constant_alive_frames": b["alive_frames"] - a["alive_frames"]}
                   for a, b in zip(c, l)]
    return {"schema": "paired_LR_upperD64_summary_v1", "comparison": "per-seed linear minus constant alive frames",
            "seed_label": LABEL, "constant_endpoint": {**CONSTANT, "registration_sha256": constant_registration_sha256},
            "linear_endpoint": {**linear_endpoint, "registration_sha256": linear_registration_sha256},
            "constant": summarize_arm(c), "linear": summarize_arm(l),
            "mean_paired_alive_frame_difference": sum(x["linear_minus_constant_alive_frames"] for x in differences) / 64,
            "per_seed_differences": differences,
            "interpretation_limits": ["One matched training seed (4200000001); no training replicate uncertainty estimate.",
              "Linear average LR 2e-5 versus constant 3e-5; ordering is not isolated from average LR.",
              "No causal claim about schedule ordering; evaluation score is diagnostic only."]}

def validate_endpoint(endpoint: dict, label: str = "endpoint") -> None:
    digest = endpoint.get("checkpoint_sha256")
    run_id = endpoint.get("run_id")
    require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
            f"{label} checkpoint SHA-256 must be 64 lowercase hex characters")
    require(isinstance(run_id, str) and bool(run_id.strip()), f"{label} run id must be nonempty")
    require(endpoint.get("endpoint_phase_update") == 384 and endpoint.get("cumulative_update") == 432,
            f"{label} endpoint updates differ")


def validate_registration(registration: dict, arm: str, checkpoint_metadata: dict) -> None:
    require(arm in ("constant", "linear"), "arm must be constant or linear")
    require(registration.get("schema") == "paired_LR_upperD64_evaluation_registration_v1", "registration schema differs")
    require(registration.get("manifest_sha256") == EXPECTED_MANIFEST_SHA256, "registration manifest pin differs")
    require(registration.get("seed_label") == LABEL, "registration seed label differs")
    require(registration.get("episode_contract") == {"difficulty": 2, "action_repeat": 4, "raw_frame_cap": 18000,
            "episodes": 64, "batch_size": 1, "action_mode": "deterministic_argmax", "gradients": False,
            "reset_policy": "construct_once_no_reset"}, "registration episode contract differs")
    endpoint = CONSTANT if arm == "constant" else registration.get("linear_endpoint")
    require(isinstance(endpoint, dict), "linear endpoint registration missing")
    validate_endpoint(endpoint, f"{arm} endpoint")
    if arm == "linear":
        require(endpoint["checkpoint_sha256"] != CONSTANT["checkpoint_sha256"]
                and endpoint["run_id"] != CONSTANT["run_id"], "linear endpoint must differ from constant endpoint")
    require(checkpoint_metadata.get("checkpoint_sha256") == endpoint["checkpoint_sha256"], "checkpoint metadata SHA pin differs")
    require(endpoint.get("endpoint_phase_update") == 384 and endpoint.get("cumulative_update") == 432
            and checkpoint_metadata.get("phase_update") == endpoint.get("endpoint_phase_update")
            and checkpoint_metadata.get("cumulative_updates") == endpoint.get("cumulative_update")
            and checkpoint_metadata.get("run_id") == endpoint.get("run_id"),
            "checkpoint endpoint metadata differs")
    if arm == "constant":
        require(endpoint.get("checkpoint_sha256") == CONSTANT["checkpoint_sha256"], "constant checkpoint pin differs")

def evaluate_registered(*, registration_path: str, registration_sha256: str, arm: str,
                         checkpoint_metadata: dict, check_guard: Callable[[], None], output_path: str,
                         collector: Callable | None = None, model=None, env_factory=None,
                         observation_keys=None, death_fields=None) -> dict:
    """Explicit parent-only entry. Collector must implement the frozen D2 loop."""
    p = Path(registration_path); raw = p.read_bytes()
    require(sha256(raw) == registration_sha256, "registration byte SHA-256 differs")
    registration = json.loads(raw)
    validate_registration(registration, arm, checkpoint_metadata)
    manifest = load_manifest()
    require(callable(check_guard), "guard is required")
    check_guard()
    if collector is collect_d2_rows or collector is None:
        require(model is not None and callable(env_factory) and observation_keys and callable(death_fields),
                "native collector requires model, environment factory, observation keys, and death telemetry")
        rows = collect_d2_rows(model=model, env_factory=env_factory, observation_keys=observation_keys,
                               death_fields=death_fields, check_guard=check_guard, allow_unavailable=False)
    else:
        require(callable(collector), "collector must be callable")
        rows = collector(seeds=tuple(manifest["seeds"]), difficulty=2, action_repeat=4,
                         raw_frame_cap=18000, batch_size=1, gradients=False, action_mode="deterministic_argmax",
                         reset_policy="construct_once_no_reset")
    check_guard()
    result = summarize_arm(rows)
    result.update({"arm": arm, "seed_label": LABEL, "manifest_sha256": EXPECTED_MANIFEST_SHA256,
                   "registration_sha256": registration_sha256, "checkpoint_sha256": checkpoint_metadata["checkpoint_sha256"],
                   "run_id": checkpoint_metadata["run_id"], "collector_sha256": _file_sha256(Path(__file__)),
                   "endpoint_phase_update": 384, "cumulative_update": 432,
                   "action_repeat": 4, "difficulty": 2, "raw_frame_cap": 18000,
                   "action_mode": "deterministic_argmax", "gradients": False})
    _write_exclusive_json(Path(output_path), result)
    return result

def collect_d2_rows(*, model, env_factory, observation_keys, death_fields,
                    check_guard: Callable[[], None], device="cpu", allow_unavailable=False) -> list[dict]:
    """D2 deterministic argmax loop; all runtime objects must be explicitly injected."""
    import numpy as np
    import torch
    require(device == "cpu", "this prepared evaluator permits CPU only")
    require(callable(env_factory) and callable(death_fields), "explicit runtime bindings required")
    require(tuple(observation_keys), "observation keys required")
    envs, obs, completed = {}, {}, {}
    import random
    py_rng = random.getstate(); np_rng = np.random.get_state(); torch_rng = torch.get_rng_state().clone()
    weights_before = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()} if hasattr(model, "state_dict") else None
    module_modes = [(module, module.training) for module in model.modules()] if hasattr(model, "modules") else [(model, model.training)]
    grads_before = [(parameter, None if parameter.grad is None else parameter.grad.detach().clone())
                    for parameter in model.parameters()] if hasattr(model, "parameters") else []
    grad_enabled_before = torch.is_grad_enabled()
    model.eval()
    inference_modes = [(module, module.training) for module, _ in module_modes]
    try:
        for i, seed in enumerate(SEEDS):
            check_guard()
            env = env_factory(batch_size=1, action_repeat=4, difficulty=2, patterns_enabled=True,
                              powerups_enabled=True, raw_frame_cap=18000, num_threads=1,
                              chunk_size=1, render_pixels=False, auxiliary_targets=False,
                              seeds_by_slot=[[seed]], excluded_seed_ranges=list(EXCLUDED_SEED_RANGES))
            info = env.episode_info()[0]
            require(info["seed"]["evaluation"] is True and info["seed"]["actual_seed"] == seed
                    and info["startup_frames"] == 13 and info["gameplay_frames"] == 0,
                    "D2 constructor seed/startup differs")
            envs[i] = env; obs[i] = env.observations()
        while envs:
            check_guard()
            active = sorted(envs)
            tensors = {name: torch.from_numpy(np.concatenate([obs[i][name] for i in active], axis=0)).to(device)
                       for name in observation_keys}
            with torch.no_grad():
                logits = model(*(tensors[name] for name in observation_keys)).logits
            require(tuple(logits.shape) == (len(active), 9) and bool(torch.isfinite(logits).all()),
                    "nonfinite or malformed D2 policy output")
            actions = logits.argmax(dim=-1).cpu().numpy()
            del tensors, logits
            for pos, i in enumerate(active):
                check_guard()
                result = envs[i].step(np.array([actions[pos]], dtype=np.int64)); info = result["info"][0]
                terminated, truncated = bool(result["terminated"][0]), bool(result["truncated"][0])
                require(info["seed"]["actual_seed"] == SEEDS[i], "D2 environment seed changed")
                require(not (terminated and truncated) and info["bootstrap"] == (not terminated),
                        "D2 boundary flags differ")
                require(info["score_raw_fixed"] == info["score_delta_sum_raw_fixed"], "D2 score identity failed")
                require(info["startup_frames"] == 13 and 0 <= info["alive_frames"] <= info["gameplay_frames"] <= 18000,
                        "D2 native frame contract differs")
                objective = info["score_raw_fixed"] / 65536 + info["alive_frames"] / 100 - 5 * terminated
                require(math.isclose(info["objective_return"], objective, rel_tol=0, abs_tol=1e-9),
                        "D2 objective identity failed")
                if terminated or truncated:
                    completed[i] = {"episode_index": i, "seed": info["seed"]["actual_seed"],
                        "score_raw_fixed": info["score_raw_fixed"], "score": info["score_raw_fixed"] / 65536,
                        "alive_frames": info["alive_frames"], "gameplay_frames": info["gameplay_frames"],
                        "startup_frames": info["startup_frames"], "objective_return": info["objective_return"],
                        "score_delta_sum_raw_fixed": info["score_delta_sum_raw_fixed"],
                        "terminated": terminated, "truncated": truncated,
                        **death_fields(info, terminated, truncated)}
                    del envs[i], obs[i]
                else:
                    obs[i] = result["observations"]
            check_guard()
    finally:
        mode_changed = any(module.training != training for module, training in inference_modes)
        for module, training in module_modes:
            module.training = training
        rng_changed = (random.getstate() != py_rng or np.random.get_state()[0] != np_rng[0]
                       or not np.array_equal(np.random.get_state()[1], np_rng[1])
                       or np.random.get_state()[2:] != np_rng[2:]
                       or not torch.equal(torch.get_rng_state(), torch_rng))
        random.setstate(py_rng); np.random.set_state(np_rng); torch.set_rng_state(torch_rng)
        if weights_before is not None:
            current = model.state_dict()
            weights_changed = any(not torch.equal(current[k].detach().cpu(), value) for k, value in weights_before.items())
            if weights_changed:
                model.load_state_dict(weights_before, strict=True)
        else:
            weights_changed = False
        grads_changed = False
        for parameter, previous in grads_before:
            current = parameter.grad
            if (previous is None) != (current is None) or (previous is not None and not torch.equal(previous, current.detach())):
                grads_changed = True
                parameter.grad = None if previous is None else previous.clone()
        require(not mode_changed, "policy mode changed during inference; original modes restored")
        require(not rng_changed, "inference changed Python, NumPy, or Torch RNG; original state restored")
        require(not weights_changed, "policy weights or buffers changed during inference; original state restored")
        require(not grads_changed, "policy gradients changed during inference; original gradients restored")
        require(torch.is_grad_enabled() == grad_enabled_before, "global gradient mode changed during inference")
    require(len(completed) == 64, "D2 evaluation incomplete")
    check_guard()
    return validate_rows([completed[i] for i in range(64)], allow_unavailable=allow_unavailable)


def state_dict_sha256(state: dict) -> str:
    digest = hashlib.sha256()
    for name in sorted(state):
        tensor = state[name].detach().cpu().contiguous()
        digest.update(name.encode()); digest.update(b"\0")
        digest.update(str(tensor.dtype).encode()); digest.update(b"\0")
        digest.update(json.dumps(list(tensor.shape), separators=(",", ":")).encode()); digest.update(b"\0")
        digest.update(tensor.numpy().tobytes())
    return digest.hexdigest()


def _write_exclusive_json(path: Path, value: dict) -> None:
    encoded = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".partial", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
        os.link(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _verify_runtime_pins(root: Path, pins: dict) -> None:
    require(isinstance(pins, dict) and pins, "registered runtime source pins missing")
    required = {"Cargo.toml", "Cargo.lock", "crates/dodge-core/Cargo.toml",
                "crates/dodge-rl-env/Cargo.toml", "python/dodge_rl/__init__.py",
                "python/dodge_rl/dev_eval.py", "python/dodge_rl/identity.py",
                "python/dodge_rl/checkpoints.py", "python/dodge_rl/models/__init__.py",
                "python/dodge_rl/models/teacher.py", "crates/dodge-rl-env/src/env.rs",
                "crates/dodge-rl-env/src/python.rs", "docs/v2-m3-run-protocol.json"}
    for crate in ("crates/dodge-core/src", "crates/dodge-rl-env/src"):
        required.update(path.relative_to(root).as_posix() for path in (root / crate).rglob("*.rs") if path.is_file())
    require(required.issubset(pins), "required Python/Rust runtime source pins missing")
    require(any(name.startswith("python/dodge_rl/_native") and name.endswith(".so") for name in pins),
            "compiled native extension pin missing")
    protocol_path = root / "docs/v2-m3-run-protocol.json"
    require(protocol_path.is_file() and _file_sha256(protocol_path) == "9e0d82028011f83e0cf6ddaef5f5e118591158d8a557f6698c82c150d5a69bab",
            "registered native evaluation protocol bytes differ")
    for rel, expected in pins.items():
        path = (root / rel).resolve()
        require(path.is_relative_to(root.resolve()) and path.is_file(), f"pinned runtime file missing: {rel}")
        require(_file_sha256(path) == expected, f"pinned runtime file changed: {rel}")


def build_registered_backend(*, registration: dict, arm: str, source_root: str,
                             checkpoint_path: str, checkpoint_metadata_path: str,
                             check_guard: Callable[[], None], env_factory=None,
                             model_factory=None, checkpoint_loader=None):
    """Explicit future runtime entry. It validates every byte pin before imports, envs, or model construction.

    Fake factories/loaders are accepted only when registration explicitly pins this collector identity
    and caller supplies the exact callback identity declared in registration.backend_identity.
    """
    root = Path(source_root).resolve()
    endpoint = registration.get("constant_endpoint") if arm == "constant" else registration.get("linear_endpoint")
    require(isinstance(endpoint, dict), "endpoint registration missing")
    validate_endpoint(endpoint, f"{arm} endpoint")
    require(isinstance(endpoint.get("metadata_sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", endpoint["metadata_sha256"]) is not None,
            "endpoint metadata SHA-256 missing or invalid")
    require(isinstance(endpoint.get("model_state_dict_sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", endpoint["model_state_dict_sha256"]) is not None,
            "registered model state-dict SHA-256 missing or invalid")
    backend = registration.get("backend_identity")
    require(isinstance(backend, dict), "reviewed backend identity missing")
    collector_sha = _file_sha256(Path(__file__))
    require(backend.get("collector_sha256") == collector_sha, "collector code pin differs")
    model_source = backend.get("model_source")
    require(model_source in backend.get("runtime_source_sha256", {}), "model source is not pinned")
    if arm == "constant":
        require(all(endpoint.get(key) == value for key, value in CONSTANT.items()),
                "constant endpoint differs from frozen endpoint pin")
    _verify_runtime_pins(root, backend.get("runtime_source_sha256", {}))
    checkpoint = Path(checkpoint_path).resolve()
    require(checkpoint.is_file() and _file_sha256(checkpoint) == endpoint.get("checkpoint_sha256"),
            "checkpoint bytes differ from endpoint pin")
    metadata_path = Path(checkpoint_metadata_path).resolve()
    metadata_raw = metadata_path.read_bytes()
    require(_file_sha256(metadata_path) == endpoint.get("metadata_sha256"), "checkpoint metadata bytes differ")
    metadata = json.loads(metadata_raw)
    validate_registration(registration, arm, metadata)
    require(isinstance(endpoint.get("metadata_sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", endpoint["metadata_sha256"]) is not None,
            "endpoint metadata SHA-256 missing or invalid")
    require(metadata.get("checkpoint_sha256") == _file_sha256(checkpoint), "metadata checkpoint hash differs")
    check_guard()
    if env_factory is None or model_factory is None or checkpoint_loader is None:
        require(env_factory is model_factory is checkpoint_loader is None,
                "partial injected backend forbidden")
        import sys
        import torch
        import numpy as np
        python_root = root / "python"
        require(python_root.is_dir(), "registered Python runtime root missing")
        if str(python_root) not in sys.path:
            sys.path.insert(0, str(python_root))
        import dodge_rl
        from dodge_rl.models import OmniscientEntityTeacher
        from dodge_rl.dev_eval import death_fields
        from dodge_rl.identity import OBSERVATION_KEYS
        from dodge_rl.checkpoints import load_checkpoint
        import inspect
        from dodge_rl import dev_eval as dev_eval_module, identity as identity_module, checkpoints as checkpoints_module
        require(Path(dodge_rl.__file__).resolve() == (root / "python/dodge_rl/__init__.py").resolve(),
                "imported package origin differs")
        require(Path(inspect.getfile(OmniscientEntityTeacher)).resolve() == (root / model_source).resolve(),
                "model source origin differs")
        for module, relative in ((dev_eval_module, "python/dodge_rl/dev_eval.py"),
                                 (identity_module, "python/dodge_rl/identity.py"),
                                 (checkpoints_module, "python/dodge_rl/checkpoints.py")):
            require(Path(module.__file__).resolve() == (root / relative).resolve(),
                    f"imported runtime origin differs: {relative}")
        native_path = Path(__import__("dodge_rl._native", fromlist=["__file__"]).__file__).resolve()
        require(native_path.is_relative_to(root), "native extension origin differs")
        require(backend["runtime_source_sha256"].get(native_path.relative_to(root).as_posix()) == _file_sha256(native_path),
                "loaded native extension differs from registered pin")
        env_factory = dodge_rl.VecDodgeEnv
        model_factory = OmniscientEntityTeacher
        checkpoint_loader = lambda path, digest: load_checkpoint(path, expected_sha256=digest)
    else:
        require(backend.get("injected_backend_reviewed") is True, "injected backend lacks review pin")
        require(backend.get("env_factory_identity") == _callable_identity(env_factory)
                and backend.get("model_factory_identity") == _callable_identity(model_factory)
                and backend.get("checkpoint_loader_identity") == _callable_identity(checkpoint_loader),
                "injected backend callback identity differs")
        import inspect
        for callback, pin_name in ((env_factory, backend.get("env_factory_source")),
                                   (model_factory, backend.get("model_factory_source")),
                                   (checkpoint_loader, backend.get("checkpoint_loader_source"))):
            require(isinstance(pin_name, str) and pin_name in backend["runtime_source_sha256"],
                    "injected callback source not pinned")
            source_file = Path(inspect.getsourcefile(callback) or "").resolve()
            require(source_file == (root / pin_name).resolve(), "injected callback source origin differs")
        import sys
        import torch
        import numpy as np
        python_root = root / "python"
        require(python_root.is_dir(), "registered Python runtime root missing")
        if str(python_root) not in sys.path:
            sys.path.insert(0, str(python_root))
        import dodge_rl
        from dodge_rl.dev_eval import death_fields
        from dodge_rl.identity import OBSERVATION_KEYS
        from dodge_rl import dev_eval as dev_eval_module, identity as identity_module, checkpoints as checkpoints_module
        require(Path(dodge_rl.__file__).resolve() == (root / "python/dodge_rl/__init__.py").resolve(),
                "imported package origin differs")
        for module, relative in ((dev_eval_module, "python/dodge_rl/dev_eval.py"),
                                 (identity_module, "python/dodge_rl/identity.py"),
                                 (checkpoints_module, "python/dodge_rl/checkpoints.py")):
            require(Path(module.__file__).resolve() == (root / relative).resolve(),
                    f"imported runtime origin differs: {relative}")
        native_path = Path(__import__("dodge_rl._native", fromlist=["__file__"]).__file__).resolve()
        require(native_path.is_relative_to(root)
                and backend["runtime_source_sha256"].get(native_path.relative_to(root).as_posix()) == _file_sha256(native_path),
                "injected backend native runtime origin or pin differs")
    check_guard()  # before model construction and checkpoint deserialization
    import torch
    rng_before = torch.get_rng_state().clone()
    model = model_factory()
    torch.set_rng_state(rng_before)
    state = checkpoint_loader(checkpoint, endpoint["checkpoint_sha256"])
    weights = state.get("model", state) if isinstance(state, dict) else state
    model.load_state_dict(weights, strict=True)
    model.to("cpu")
    actual_model_sha = state_dict_sha256(model.state_dict())
    require(actual_model_sha == endpoint["model_state_dict_sha256"], "loaded model state-dict bytes differ from registration")
    model._paired_eval_state_dict_sha256 = actual_model_sha
    return model, env_factory, OBSERVATION_KEYS, death_fields


def _callable_identity(value) -> str:
    return f"{getattr(value, '__module__', '')}:{getattr(value, '__qualname__', '')}"


def evaluate_with_registered_backend(*, registration_path: str, registration_sha256: str,
        arm: str, source_root: str, checkpoint_path: str, checkpoint_metadata_path: str,
        check_guard: Callable[[], None], output_path: str) -> dict:
    p = Path(registration_path); raw = p.read_bytes()
    require(sha256(raw) == registration_sha256, "registration byte SHA-256 differs")
    registration = json.loads(raw)
    validate_registration(registration, arm, json.loads(Path(checkpoint_metadata_path).read_text()))
    check_guard()  # guard and byte budget gate must run before backend construction
    model, env_factory, keys, death = build_registered_backend(registration=registration, arm=arm,
        source_root=source_root, checkpoint_path=checkpoint_path,
        checkpoint_metadata_path=checkpoint_metadata_path, check_guard=check_guard)
    rows = collect_d2_rows(model=model, env_factory=env_factory, observation_keys=keys,
        death_fields=death, check_guard=check_guard)
    result = summarize_arm(rows)
    endpoint = registration["constant_endpoint"] if arm == "constant" else registration["linear_endpoint"]
    result.update({"arm": arm, "seed_label": LABEL, "manifest_sha256": EXPECTED_MANIFEST_SHA256,
       "registration_sha256": registration_sha256, "checkpoint_sha256": endpoint["checkpoint_sha256"],
       "run_id": endpoint["run_id"], "model_state_dict_sha256": endpoint["model_state_dict_sha256"],
       "collector_sha256": _file_sha256(Path(__file__)),
       "endpoint_phase_update": 384, "cumulative_update": 432, "action_repeat": 4,
       "difficulty": 2, "raw_frame_cap": 18000, "action_mode": "deterministic_argmax", "gradients": False})
    check_guard()
    _write_exclusive_json(Path(output_path), result)
    return result
