"""Synthetic checkpoint420 migration check; no environment or seed pool access.

This is not a training prefix or a survival evaluation. It deliberately replaces
the native package import with a tripwire before loading any runtime modules.
Run in a bounded subprocess, not directly in a persistent notebook kernel.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.abc
import json
import os
from pathlib import Path
import resource
import sys
import time
import uuid
from types import ModuleType


CHECKPOINT_SHA = "7e0de8640f1337261412d91cde6bc692772ff212fbd360f5aad415dc6bc7ed4b"
CPU_CUDA_ATOL = 2e-5
CPU_CUDA_RTOL = 2e-5


class NoNative(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "dodge_rl._native" or fullname.startswith("dodge_rl._native."):
            raise RuntimeError("Native games forbidden in synthetic cloud compatibility")
        return None


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save(path, value):
    # An attempted check can never overwrite an earlier result.
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n"); stream.flush(); os.fsync(stream.fileno())


def fixture_device(name):
    """CUDA memory-limit APIs require an explicit index, even for one GPU."""
    import torch
    return torch.device('cuda', 0) if name == 'cuda' else torch.device(name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--job-nonce", default="local_CPU_fixture")
    args = parser.parse_args()
    if args.device == "cuda" and str(uuid.UUID(args.job_nonce)) != args.job_nonce:
        raise ValueError("Canonical coordinator allocation UUID required")
    if args.device == "cuda" and os.environ.get("DODGE060_BILLING_ADMITTED") != "true":
        raise ValueError("Parent live billing admission absent")
    # Claim before imports or device work; a reconnect must inspect, never repeat.
    save(str(args.output) + ".claimed", {"pid": os.getpid(), "device": args.device,
                                        "job_nonce": args.job_nonce})
    root = Path(__file__).resolve().parent
    for name, directory in (("dodge_rl", root / "runtime_overlay/dodge_rl"),
                            ("dodge_rl.models", root / "runtime_overlay/dodge_rl/models")):
        package = ModuleType(name); package.__path__ = [str(directory)]
        sys.modules[name] = package
    sys.meta_path.insert(0, NoNative())
    started = time.monotonic()
    report = {"schema": "dodge_colab_synthetic_compatibility_result_v1", "record": "DODGE-060",
              "job_nonce": args.job_nonce, "payload_sha256": os.environ.get("DODGE060_PAYLOAD_SHA256"),
              "native_games": 0, "training_frames": 0, "seed_pool_opened": False,
              "heldout_opened": False, "simulator_restored": False,
              "device": args.device, "checkpoint_sha256": CHECKPOINT_SHA}
    try:
        import torch
        import numpy as np
        from dodge_rl.device_runtime import accelerator_bytes, peak_rss_bytes, synchronize
        from dodge_rl.models.teacher import OmniscientEntityTeacher
        from dodge_rl.models.ray_teacher import RayGeometryTeacher
        from dodge_rl.ray_migration import migrate_adam
        from dodge_rl.checkpoints import load_checkpoint, require_complete_update, capture_rng, restore_rng
        from dodge_rl.player_geometry import MAX_PLAYER_SIZE
        from fingerprints import fingerprint
        device = fixture_device(args.device)
        report['device_index'] = device.index
        from numpy._core import _multiarray_umath
        package_files = {"python": sys.executable, "torch_python": torch.__file__,
                         "torch_native": torch._C.__file__, "numpy_python": np.__file__,
                         "numpy_native": _multiarray_umath.__file__}
        provenance = {name: {"path": str(Path(path).resolve()), "sha256": sha(path)}
                      for name, path in package_files.items()}
        save(str(args.output) + ".runtime-provenance.json", {
            "record": "DODGE-060", "job_nonce": args.job_nonce,
            "torch": torch.__version__, "numpy": np.__version__, "python": sys.version,
            "cuda_runtime": torch.version.cuda, "package_origins": provenance,
            "device": device.type, "device_index": device.index,
            "limits": "Observed before synthetic model/optimizer work; no Linux native game extension."})
        torch.set_num_threads(1); torch.set_num_interop_threads(1)
        # Do not let CUDA use lower-precision matrix products without declaration.
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.set_float32_matmul_precision("highest")
        if device.type == "cuda":
            if not torch.cuda.is_available():
                raise ValueError("Requested CUDA unavailable")
            torch.cuda.set_per_process_memory_fraction(
                min(1., 6 * 1024**3 / torch.cuda.get_device_properties(device).total_memory), device)
        torch.random.default_generator.manual_seed(2026103101)
        state = load_checkpoint(args.checkpoint, expected_sha256=CHECKPOINT_SHA)
        require_complete_update(state)
        original_model, original_adam = fingerprint(state["model"]), fingerprint(state["optimizer"])
        legacy = OmniscientEntityTeacher(); legacy.load_state_dict(state["model"], strict=True)
        model = RayGeometryTeacher(legacy, branch_seed=2026103102)
        sizes = (2., 4., 275249 / 65536, MAX_PLAYER_SIZE)
        g = torch.zeros(4, 1, 14); g[:, 0, 4] = torch.tensor(sizes) / 4
        g[:, 0, 0] = torch.tensor((2., 125., 63.5, 2.)) / 64 - 1
        g[:, 0, 1] = torch.tensor((125., 2., 63.5, 2.)) / 64 - 1
        e = torch.zeros(4, 80, 16); t = torch.zeros(4, 80, dtype=torch.int64)
        mask = torch.zeros(4, 80, dtype=torch.bool)
        arrays = (g, e, t, mask)
        with torch.no_grad():
            CPU_reference = legacy(*arrays)
        model.to(device)
        optimizer, migration = migrate_adam(state["optimizer"], legacy, model,
                                             learning_rate=3e-5, adam_eps=1e-5)
        if fingerprint(legacy.state_dict()) != original_model:
            raise ValueError("Migration changed checkpoint420 model")
        for parameter in legacy.parameters():
            entry = optimizer.state[parameter]
            if any(entry[key].device != device for key in ("exp_avg", "exp_avg_sq")):
                raise ValueError("Adam moments on wrong device")
        if optimizer.state.get(model.gate) or any(optimizer.state.get(p) for p in model.branch.parameters()):
            raise ValueError("New branch inherited optimizer state")
        with torch.no_grad():
            before = legacy(*(x.to(device) for x in arrays)); after = model(*arrays)
        if not all(torch.equal(getattr(before, k), getattr(after, k)) for k in ("logits", "values", "latent")):
            raise ValueError("Zero-gate same-device warm-start differs")
        if not all(torch.equal(a, b) for a, b in zip(before.attentions, after.attentions, strict=True)):
            raise ValueError("Zero-gate same-device attention differs")
        CPU_CUDA_differences = {}
        for key in ("logits", "values", "latent"):
            left, right = getattr(CPU_reference, key), getattr(before, key).cpu()
            CPU_CUDA_differences[key] = float((left - right).abs().max())
            if not torch.allclose(left, right, atol=CPU_CUDA_ATOL, rtol=CPU_CUDA_RTOL):
                raise ValueError("CPU/device float32 numerical parity differs: " + key)
        for bad in (4.5, float("nan"), float("inf")):
            invalid = g.clone(); invalid[0, 0, 4] = bad / 4
            try:
                model(invalid, e, t, mask)
            except ValueError:
                pass
            else:
                raise ValueError("Malformed geometry accepted")
        # Exercise real Adam on a disposable synthetic copy, never a game batch.
        # Gate zero implies branch gradients exactly zero on this first step.
        output = model(*arrays)
        loss = output.logits.square().mean() + output.values.square().mean()
        loss.backward()
        if model.gate.grad is None or not bool(torch.isfinite(model.gate.grad)):
            raise ValueError("Gate gradient missing/nonfinite")
        for parameter in model.branch.parameters():
            if parameter.grad is None or bool(parameter.grad.ne(0).any()):
                raise ValueError("Zero gate leaked branch gradient")
        torch.nn.utils.clip_grad_norm_(model.parameters(), .5)
        optimizer.step(); optimizer.zero_grad(set_to_none=True)
        if not all(bool(torch.isfinite(p).all()) for p in model.parameters()):
            raise ValueError("Synthetic Adam produced nonfinite parameters")
        saved_rng = capture_rng(device)
        restore_rng(saved_rng, device)
        if device.type == "cuda" and not torch.equal(saved_rng["torch_cuda"], torch.cuda.get_rng_state(device)):
            raise ValueError("CUDA RNG roundtrip differs")
        synchronize(device)
        rss = peak_rss_bytes(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        memory = accelerator_bytes(device)
        if rss >= 6 * 1024**3 or memory >= 6 * 1024**3:
            raise ValueError("Separate6GiB synthetic compatibility ceiling exceeded")
        if sha(args.checkpoint) != CHECKPOINT_SHA:
            raise ValueError("Checkpoint changed")
        origins = {name: {"path": str(Path(module.__file__).resolve()), "sha256": sha(module.__file__)}
                   for name, module in sys.modules.items()
                   if name.startswith("dodge_rl.") and getattr(module, "__file__", None)}
        report.update(status="synthetic_420_migration_passed", torch=torch.__version__,
            numpy=np.__version__, python=sys.version, platform=sys.platform,
            GPU=None if device.type == "cpu" else torch.cuda.get_device_name(device),
            cuda_runtime=torch.version.cuda, runtime_origins=origins,
            package_origins=provenance,
            source_model_fingerprint=original_model, source_Adam_fingerprint=original_adam,
            migration=migration, same_device_zero_gate_exact=True,
            CPU_device_numeric_tolerance={"atol": CPU_CUDA_ATOL, "rtol": CPU_CUDA_RTOL},
            CPU_device_max_absolute_differences=CPU_CUDA_differences,
            legal_size_edges_passed=list(sizes), malformed_size_rejected=True,
            synthetic_optimizer_steps=1, peak_RSS_bytes=rss, accelerator_reserved_bytes=memory,
            accelerator_peak_reserved_bytes=(0 if device.type == "cpu" else torch.cuda.max_memory_reserved(device)),
            accelerator_peak_allocated_bytes=(0 if device.type == "cpu" else torch.cuda.max_memory_allocated(device)),
            elapsed_seconds=time.monotonic() - started,
            limits="Synthetic only; not native/Linux environment or training throughput qualification.")
        save(args.output, report)
        print(json.dumps(report, sort_keys=True, allow_nan=False))
    except BaseException as error:
        report.update(status="synthetic_compatibility_failed", error=repr(error),
                      elapsed_seconds=time.monotonic() - started)
        save(str(args.output) + ".first-failure.json", report)
        raise


if __name__ == "__main__":
    main()
