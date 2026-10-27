"""Bounded assembled diagnostic for entity teacher, image student, and losses.

The native game supplies one paired observation on a fixed training seed. An
untrained, frozen teacher produces diagnostic targets; the visual student runs
one backward pass. No optimizer, checkpoint, dataset, or qualification result
is created. Elapsed time includes diagnostics and is not an inference benchmark.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from typing import Any

TRAIN_SEED = 1000
MODEL_SEED = 0


def _has_visible_spatial(state: dict[str, Any]) -> bool:
    """Detect a representable footprint without running or querying a policy."""
    x0, y0, x1, y1 = state["capture_bounds"]
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(128, x1), min(128, y1)
    for row in state["entities"]:
        if not row["spatial"]:
            continue
        left, top, right, bottom = row["bounds"]
        if right == left:
            right += 1
        if bottom == top:
            bottom += 1
        if min(right, x1) > max(left, x0) and min(bottom, y1) > max(top, y0):
            return True
    return False


def run_architecture_smoke(device: str = "cpu", *, max_frames: int = 64) -> dict[str, Any]:
    """Run one native-pixel forward/backward check within 1..128 game frames."""
    if device not in ("cpu", "mps"):
        raise ValueError("device must be cpu or mps")
    if isinstance(max_frames, bool) or not isinstance(max_frames, int) or not 1 <= max_frames <= 128:
        raise ValueError("max_frames must be an integer from 1 to 128")

    import numpy as np
    import torch

    from .distillation import distillation_losses
    from .entity_teacher import EntityActorCritic, batch_entities, encode_entities
    from .env import NativeEnvironment
    from .pixels import PixelHistory
    from .policies import AvoidancePolicy
    from .smoke import resolve_device
    from .vit import ViTPolicy

    selected = resolve_device(device)
    started = time.perf_counter()
    previous_threads = torch.get_num_threads()
    torch.set_num_threads(1)
    try:
        history = PixelHistory(length=4)
        game_frames = 0
        with NativeEnvironment(seed=TRAIN_SEED, action_repeat=1, max_episode_frames=max_frames) as environment:
            observation = environment.current()
            start_frame = observation["info"]["frame"]
            history.reset(observation["pixels"], frame_id=start_frame)
            avoidance = AvoidancePolicy()
            while not _has_visible_spatial(observation["privileged_state"]):
                info = observation["info"]
                if game_frames >= max_frames or info["terminated"] or info["truncated"]:
                    break
                observation = environment.step(avoidance.act(observation))
                elapsed = observation["info"]["elapsed_native_frames"]
                if elapsed != 1:
                    raise RuntimeError("assembled diagnostic requires one native frame per step")
                game_frames += elapsed
                history.append(observation["pixels"], frame_id=observation["info"]["frame"])
            if history.frames[-1] != observation["pixels"]:
                raise RuntimeError("image history and teacher state are not paired at one returned frame")
            if environment.student_observation() != observation["pixels"]:
                raise RuntimeError("pixel-only observation differs from the returned teacher observation")

        provenance = observation["info"]["provenance"]
        if provenance.get("privileged_schema_version") != 1 or provenance.get("action_repeat") != 1:
            raise RuntimeError("assembled diagnostic requires privileged schema 1 and action repeat 1")
        encoded = encode_entities(observation["privileged_state"])
        batch = batch_entities([encoded], device=selected)
        raw_entity_count = len(observation["privileged_state"]["entities"])
        if encoded.features.shape[0] != raw_entity_count or int(batch.mask.sum().item()) != raw_entity_count:
            raise RuntimeError("privileged entity encoding dropped source rows")
        images = torch.from_numpy(np.asarray(history.gray_chw(), dtype=np.float32)).reshape(1, 4, 128, 128).to(selected)
        with torch.random.fork_rng(devices=[]):
            torch.random.default_generator.manual_seed(MODEL_SEED)
            teacher = EntityActorCritic().to(selected).eval().requires_grad_(False)
            student = ViTPolicy().to(selected).train()
        with torch.no_grad():
            teacher_output = teacher.distillation_outputs(batch)
        student_output = student.distillation_outputs(images)
        losses = distillation_losses(
            student_output.logits, student_output.latent, student_output.attention,
            teacher_output.logits, teacher_output.latent, teacher_output.attention,
            batch.bounds, batch.spatial, batch.mask, batch.capture_bounds,
            grid_size=8,
        )
        losses.total.backward()
        gradients = [parameter.grad for parameter in student.parameters()]
        if any(gradient is None or not bool(torch.isfinite(gradient).all()) for gradient in gradients):
            raise RuntimeError("student produced missing or nonfinite parameter gradients")
        max_gradient = max(float(gradient.detach().abs().max().item()) for gradient in gradients)
        if max_gradient == 0:
            raise RuntimeError("student produced no nonzero parameter gradients")
        teacher_gradients_absent = all(parameter.grad is None for parameter in teacher.parameters())
        if not teacher_gradients_absent:
            raise RuntimeError("frozen teacher received distillation gradients")
        if selected.type == "mps":
            torch.mps.synchronize()
        loss_values = {
            name: float(getattr(losses, name).detach().cpu().item())
            for name in ("total", "action", "latent", "attention")
        }
        return {
            "diagnostic": "native_entity_teacher_vit_three_loss_backward",
            "trained_policy": False,
            "teacher_trained": False,
            "game_evaluation": False,
            "qualification": "not_evaluated",
            "student_collection_allowed": False,
            "optimizer_steps": 0,
            "checkpoint_written": False,
            "dataset_written": False,
            "device": str(selected),
            "seed": TRAIN_SEED,
            "model_seed": MODEL_SEED,
            "max_native_frames": max_frames,
            "game_frames": game_frames,
            "start_frame": start_frame,
            "paired_frame": observation["info"]["frame"],
            "paired_pixel_sha256": hashlib.sha256(observation["pixels"]).hexdigest(),
            "state_hash": observation["info"]["state_hash"],
            "pixel_hash": observation["info"]["pixel_hash"],
            "same_snapshot_pair_verified": True,
            "provenance": provenance,
            "teacher_parameters": sum(parameter.numel() for parameter in teacher.parameters()),
            "student_parameters": sum(parameter.numel() for parameter in student.parameters()),
            "privileged_entity_count": raw_entity_count,
            "encoded_entity_count": int(batch.mask.sum().item()),
            "nonspatial_entity_count": int((batch.mask & ~batch.spatial).sum().item()),
            "spatial_entity_count": int((batch.mask & batch.spatial).sum().item()),
            "valid_attention_rows": losses.attention_rows,
            "losses": loss_values,
            "shapes": {
                "images": list(images.shape),
                "teacher_logits": list(teacher_output.logits.shape),
                "teacher_latent": list(teacher_output.latent.shape),
                "teacher_attention": list(teacher_output.attention.shape),
                "student_logits": list(student_output.logits.shape),
                "student_latent": list(student_output.latent.shape),
                "student_attention": list(student_output.attention.shape),
            },
            "student_gradients_finite": True,
            "max_abs_student_gradient": max_gradient,
            "teacher_gradients_absent": teacher_gradients_absent,
            "torch_version": str(torch.__version__),
            "python_version": platform.python_version(),
            "elapsed_seconds": time.perf_counter() - started,
        }
    finally:
        torch.set_num_threads(previous_threads)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    parser.add_argument("--max-frames", type=int, default=64)
    arguments = parser.parse_args(argv)
    try:
        report = run_architecture_smoke(arguments.device, max_frames=arguments.max_frames)
    except (ValueError, RuntimeError, ImportError) as error:
        parser.exit(2, f"architecture smoke failed: {error}\n")
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
