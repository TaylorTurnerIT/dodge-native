"""Inert source-pinned adapter builder for a future authorized driver."""
from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

CHECKPOINTS_RELATIVE = Path("learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime/dodge_rl/checkpoints.py")
CHECKPOINTS_SHA256 = "807141943a742c6e9fdd34274c191b3c318134cc7fb0c1c6256874cadee1cbc3"
RUNNER_RELATIVE = Path("learning/runs/v2/D2-retained300-continuation-freeze-20261026-r5/runner.py")
RUNNER_SHA256 = "108ba55ad78aa26166acb14f67cc6466da6293ccee3d272e1fe6e775ebf2ac60"
RAW_RNG_KEYS = frozenset({"python", "numpy_global", "numpy_generator", "torch_cpu", "torch_mps", "sampling_backend"})


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_pinned_sources(project_root):
    root = Path(project_root).resolve()
    files = ((CHECKPOINTS_RELATIVE, CHECKPOINTS_SHA256), (RUNNER_RELATIVE, RUNNER_SHA256))
    verified = {}
    for rel, expected in files:
        path = (root / rel).resolve()
        if root not in path.parents or not path.is_file() or _sha256(path) != expected:
            raise ValueError(f"pinned trusted source mismatch: {rel}")
        verified[str(rel)] = {"path": str(path), "sha256": expected}
    return verified


def build_callbacks(*, project_root, checkpoint_module, runner_namespace, parent_state,
                    model, optimizer, capture_module_hash):
    """Return exact trusted restore/capture callbacks after origin and hash checks.

    This builder never imports project modules. The future driver supplies already
    loaded modules after its own authorization gate.
    """
    sources = verify_pinned_sources(project_root)
    if getattr(checkpoint_module, "__file__", None) is None:
        raise ValueError("checkpoint module must expose its source file")
    expected_path = sources[str(CHECKPOINTS_RELATIVE)]["path"]
    if Path(checkpoint_module.__file__).resolve() != Path(expected_path):
        raise ValueError("checkpoint module origin mismatch")
    if capture_module_hash != CHECKPOINTS_SHA256:
        raise ValueError("checkpoint module verified hash mismatch")
    restore = getattr(checkpoint_module, "restore_learner", None)
    capture = getattr(checkpoint_module, "capture_rng", None)
    if not callable(restore) or not callable(capture):
        raise ValueError("pinned capture_rng and restore_learner APIs required")
    if Path(inspect.getsourcefile(restore) or "").resolve() != Path(expected_path) or Path(inspect.getsourcefile(capture) or "").resolve() != Path(expected_path):
        raise ValueError("trusted API function origin mismatch")
    worker = runner_namespace.get("worker") if isinstance(runner_namespace, dict) else None
    runner_file = runner_namespace.get("__file__") if isinstance(runner_namespace, dict) else None
    expected_runner = sources[str(RUNNER_RELATIVE)]["path"]
    if worker is None or not callable(worker) or Path(runner_file or "").resolve() != Path(expected_runner):
        raise ValueError("pinned runner worker origin required")
    if Path(inspect.getsourcefile(worker) or "").resolve() != Path(expected_runner):
        raise ValueError("runner worker function origin mismatch")

    def restore_trusted():
        return restore(parent_state, model, optimizer, "mps")

    def rng_capture():
        raw = capture("mps")
        if not isinstance(raw, dict) or set(raw) != RAW_RNG_KEYS:
            raise ValueError("capture_rng must return the pinned raw six-key RNG dictionary")
        return raw

    return {"restore_trusted": restore_trusted, "rng_capture": rng_capture,
            "verified_sources": sources, "api_names": {"restore": "restore_learner", "capture": "capture_rng"}}
