"""Bounded CPU teacher training and held-out evaluation entry point."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import tempfile
from typing import Any

from .seeds import manifest_hash, seed_manifest


def write_json(path: Path, value: Any) -> None:
    """Publish a complete receipt without replacing any existing file."""
    body = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as file:
            temporary = Path(file.name)
            file.write(body)
            file.flush()
            os.fsync(file.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def source_manifest() -> dict[str, Any]:
    """Fingerprint the learner sources and the installed native extension."""
    package = Path(__file__).resolve().parent
    learning = package.parents[1]
    files = list(package.glob("*.py"))
    native = learning / "native"
    if native.is_dir():
        files.extend(native.glob("src/*.rs"))
        files.extend(path for path in (native / "build.rs", native / "Cargo.toml", native / "Cargo.lock", learning / "pyproject.toml") if path.is_file())
    digests = {}
    for file in sorted(files):
        if file.parent == package:
            name = f"python/dodge_learning/{file.name}"
        else:
            name = str(file.relative_to(learning))
        digests[name] = hashlib.sha256(file.read_bytes()).hexdigest()
    from . import _native

    extension = Path(_native.__file__)
    body = {"files": digests, "native_extension_sha256": hashlib.sha256(extension.read_bytes()).hexdigest()}
    body["manifest_sha256"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    return body


def _prepare_teacher(arguments: argparse.Namespace, config: Any, manifest: dict[str, Any]):
    """Build an owned entity teacher or validate a weights-only warm start.

    A warm start deliberately resets optimizer, rollout, episode order, and
    sampling RNG state. It never transfers the parent's qualification result.
    """
    import torch

    from .entity_teacher import EntityActorCritic, EntityTeacherConfig
    from .teacher import TeacherConfig

    architecture = getattr(arguments, "architecture", "entity_transformer")
    dimensions = {
        "embed_dim": getattr(arguments, "embed_dim", 128),
        "depth": getattr(arguments, "depth", 2),
        "num_heads": getattr(arguments, "num_heads", 4),
    }
    representation = {
        "attention_prior": getattr(arguments, "attention_prior", 1.0),
        "relative_geometry": getattr(arguments, "relative_geometry", False),
        "kind_embedding_scale": getattr(arguments, "kind_embedding_scale", 1.0),
    }
    warm_start = getattr(arguments, "warm_start", None)
    if architecture not in ("entity_transformer", "legacy_mlp"):
        raise ValueError("architecture must be entity_transformer or legacy_mlp")
    model_config = EntityTeacherConfig(**dimensions, **representation)
    if architecture == "legacy_mlp":
        if warm_start is not None:
            raise ValueError("warm starts require the entity_transformer architecture")
        if dimensions != {"embed_dim": 128, "depth": 2, "num_heads": 4}:
            raise ValueError("entity model dimensions do not apply to legacy_mlp")
        if representation != {"attention_prior": 1.0, "relative_geometry": False, "kind_embedding_scale": 1.0}:
            raise ValueError("entity representation settings do not apply to legacy_mlp")
        return None, asdict(TeacherConfig()), None
    if warm_start is None:
        with torch.random.fork_rng(devices=[]):
            torch.random.default_generator.manual_seed(config.seed)
            model = EntityActorCritic(model_config)
        return model, asdict(model_config), None

    from .checkpoints import load_teacher_checkpoint
    from .env import NativeEnvironment
    from .teacher_eval import (
        _match_provenance,
        _require_default_benchmark,
        _verify_source_identity,
    )

    parent_path = Path(warm_start).expanduser().resolve()
    loaded = load_teacher_checkpoint(parent_path)
    if not isinstance(loaded.model, EntityActorCritic):
        raise ValueError("warm starts require an entity-transformer checkpoint")
    if loaded.model.config != model_config:
        raise ValueError("warm-start dimensions and representation settings must match the declared entity model configuration")
    metadata = loaded.metadata
    if manifest_hash(metadata["seed_manifest"]) != manifest_hash(manifest):
        raise ValueError("warm starts require the unchanged frozen seed manifest")
    if metadata["training_config"]["train_seeds"] != list(config.train_seeds):
        raise ValueError("warm starts require the unchanged training seed sequence")
    _, verified = _verify_source_identity(metadata["source_manifest"])
    if not verified:
        raise ValueError("warm starts require complete matching runtime source fingerprints")
    training_files = ("ppo.py", "checkpoints.py", "teacher_run.py")
    if metadata["metrics"].get("method") == "heuristic_bootstrap":
        training_files += ("teacher_bootstrap.py",)
    elif metadata["metrics"].get("method") == "representation_ablation_supervised":
        training_files += ("teacher_representation_ablation.py",)
    elif metadata["metrics"].get("method") == "teacher_onset_ablation_supervised":
        training_files += ("teacher_onset_ablation.py", "teacher_representation_ablation.py")
    elif metadata["metrics"].get("method") == "teacher_fit_budget_supervised":
        training_files += (
            "teacher_fit_budget.py", "teacher_onset_ablation.py",
            "teacher_representation_ablation.py", "policies.py", "seeds.py",
        )
    package = Path(__file__).resolve().parent
    training_identity = {}
    for name in training_files:
        key = f"python/dodge_learning/{name}"
        actual_hash = hashlib.sha256((package / name).read_bytes()).hexdigest()
        if metadata["source_manifest"].get("files", {}).get(key) != actual_hash:
            raise ValueError(f"warm-start training source fingerprint mismatch: {key}")
        training_identity[key] = actual_hash
    provenance = metadata["metrics"]["provenance"]
    _require_default_benchmark(provenance)
    with NativeEnvironment(
        seed=config.train_seeds[0], max_episode_frames=config.max_episode_frames,
        action_repeat=1, discount=config.gamma,
    ) as environment:
        current = environment.current()["info"]["provenance"]
        _require_default_benchmark(current)
        _match_provenance(current, provenance)
    receipt = {
        "parent_checkpoint": {
            "path": str(parent_path), "sha256": loaded.sha256,
            "format_version": metadata["format_version"], "kind": metadata["kind"],
            "frames_collected": metadata["metrics"].get("frames_collected"),
        },
        "optimizer_state": "fresh",
        "rollout_state": "fresh",
        "training_seed_order": "restart_from_first_training_seed",
        "sampling_rngs": "fresh_private_rngs_from_run_seed",
        "exact_resume": False,
        "qualification_transferred": False,
        "training_source_identity": training_identity,
    }
    return loaded.model, asdict(model_config), receipt


def run_training(arguments: argparse.Namespace) -> dict[str, Any]:
    import torch

    from .checkpoints import save_teacher_checkpoint
    from .ppo import PPOConfig, train_teacher

    manifest = seed_manifest()
    config = PPOConfig(
        total_frames=arguments.frames,
        max_seconds=arguments.max_seconds,
        rollout_steps=arguments.rollout_steps,
        epochs=arguments.epochs,
        minibatch_size=arguments.minibatch_size,
        learning_rate=arguments.learning_rate,
        reward_scale=getattr(arguments, "reward_scale", 0.01),
        gamma=getattr(arguments, "gamma", 0.99),
        gae_lambda=getattr(arguments, "gae_lambda", 0.95),
        value_coef=getattr(arguments, "value_coef", 0.5),
        critic_trunk_grad=not getattr(arguments, "detach_critic_trunk", False),
        entropy_coef=getattr(arguments, "entropy_coef", 0.01),
        max_grad_norm=getattr(arguments, "max_grad_norm", 0.5),
        torch_threads=getattr(arguments, "torch_threads", 1),
        max_episode_frames=arguments.episode_frames,
        seed=arguments.seed,
        train_seeds=tuple(manifest["train"]),
    )
    if arguments.evaluate_smoke:
        if type(arguments.smoke_frames) is not int or not 1 <= arguments.smoke_frames <= 18_000:
            raise ValueError("smoke_frames must be an integer from 1 to 18000")
        if not 0 < arguments.evaluation_seconds <= 1800 or not math.isfinite(arguments.evaluation_seconds):
            raise ValueError("evaluation_seconds must be finite and in (0, 1800]")
    architecture = getattr(arguments, "architecture", "entity_transformer")
    model, model_config, warm_start = _prepare_teacher(arguments, config, manifest)
    output = arguments.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = source_manifest()
    write_json(output / "seeds.json", manifest)
    write_json(output / "source.json", sources)
    write_json(output / "config.json", {
        **asdict(config), "architecture": architecture,
        "model_config": model_config, "warm_start": warm_start,
    })
    started = datetime.now(timezone.utc).isoformat()
    progress_file = output / "progress.jsonl"

    def progress(metrics: dict[str, Any]) -> None:
        with progress_file.open("a") as file:
            file.write(json.dumps(metrics, sort_keys=True, allow_nan=False) + "\n")

    try:
        training_options = {"progress_callback": progress, "architecture": architecture}
        if model is not None:
            training_options["model"] = model
        result = train_teacher(config, **training_options)
        if warm_start is not None:
            result.metrics["warm_start"] = warm_start
        checkpoint = save_teacher_checkpoint(
            output / "teacher.pt", result, seed_manifest=manifest, source_manifest=sources
        )
        report = {
            "schema_version": 1,
            "kind": "state_teacher_training",
            "architecture": architecture,
            "model_config": model_config,
            "warm_start": warm_start,
            "started_at_utc": started,
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "python_version": platform.python_version(),
            "torch_version": str(torch.__version__),
            "machine": platform.machine(),
            "macos_version": platform.mac_ver()[0],
            "seed_manifest_sha256": manifest_hash(manifest),
            "checkpoint": checkpoint,
            "metrics": result.metrics,
            "student_collection_allowed": False,
            "qualification": "not_evaluated",
        }
        if arguments.evaluate_smoke:
            from .teacher_eval import evaluate_checkpoint

            evaluation = evaluate_checkpoint(
                output / "teacher.pt", split="smoke", max_frames=arguments.smoke_frames,
                compare_baselines=True, max_seconds=arguments.evaluation_seconds,
            )
            write_json(output / "smoke-evaluation.json", evaluation)
            report["smoke_evaluation"] = "smoke-evaluation.json"
            report["qualification"] = "not_evaluated_smoke_only"
        write_json(output / "run.json", report)
    except Exception as error:
        write_json(output / "failure.json", {
            "started_at_utc": started, "error_type": type(error).__name__, "error": str(error),
            "student_collection_allowed": False,
        })
        raise
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    train = commands.add_parser("train", help="bounded CPU PPO run; never collect student data")
    train.add_argument("--output-dir", type=Path, required=True)
    train.add_argument("--architecture", choices=("entity_transformer", "legacy_mlp"), default="entity_transformer")
    train.add_argument("--frames", type=int, default=10_000)
    train.add_argument("--max-seconds", type=float, default=1800)
    train.add_argument("--rollout-steps", type=int, default=256)
    train.add_argument("--epochs", type=int, default=4)
    train.add_argument("--minibatch-size", type=int, default=64)
    train.add_argument("--learning-rate", type=float, default=3e-4)
    train.add_argument("--reward-scale", type=float, default=0.01, help="scale PPO targets while reporting raw survival returns")
    train.add_argument("--gamma", type=float, default=0.99)
    train.add_argument("--gae-lambda", type=float, default=0.95)
    train.add_argument("--value-coef", type=float, default=0.5)
    train.add_argument(
        "--detach-critic-trunk", action="store_true",
        help="let the entity critic head learn without value gradients entering the policy transformer",
    )
    train.add_argument("--entropy-coef", type=float, default=0.01)
    train.add_argument("--max-grad-norm", type=float, default=0.5)
    train.add_argument("--torch-threads", type=int, default=1)
    train.add_argument("--embed-dim", type=int, default=128, help="entity-transformer width")
    train.add_argument("--depth", type=int, default=2, help="entity-transformer block count")
    train.add_argument("--num-heads", type=int, default=4, help="entity-transformer attention heads")
    train.add_argument("--attention-prior", type=float, default=1.0, help="finite current-physical-entity attention multiplier")
    train.add_argument("--relative-geometry", action="store_true", help="express physical entity geometry relative to the player")
    train.add_argument("--kind-embedding-scale", type=float, default=1.0, help="scale initial entity-kind embeddings")
    train.add_argument("--warm-start", type=Path, help="validated entity weights; fresh optimizer, rollouts, and RNGs")
    train.add_argument("--episode-frames", type=int, default=18_000)
    train.add_argument("--seed", type=int, default=7)
    train.add_argument("--evaluate-smoke", action="store_true")
    train.add_argument("--smoke-frames", type=int, default=1000)
    train.add_argument("--evaluation-seconds", type=float, default=300)
    evaluate = commands.add_parser("evaluate", help="evaluate a saved state teacher on held-out seeds")
    evaluate.add_argument("--checkpoint", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    evaluate.add_argument("--split", choices=("smoke", "validation"), default="smoke")
    evaluate.add_argument("--max-frames", type=int, default=1000)
    evaluate.add_argument("--seed-count", type=int)
    evaluate.add_argument("--max-seconds", type=float, default=300)
    evaluate.add_argument("--qualify", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "train":
            report = run_training(arguments)
            print(json.dumps({"output_dir": str(arguments.output_dir), "metrics": report["metrics"], "qualification": report["qualification"]}, allow_nan=False))
        else:
            from .teacher_eval import evaluate_checkpoint

            if arguments.output.exists():
                raise FileExistsError(f"refusing to replace {arguments.output}")
            report = evaluate_checkpoint(
                arguments.checkpoint, split=arguments.split, max_frames=arguments.max_frames,
                seed_count=arguments.seed_count, compare_baselines=True,
                qualify=arguments.qualify, max_seconds=arguments.max_seconds,
            )
            write_json(arguments.output, report)
            print(json.dumps({"output": str(arguments.output), "qualification": report.get("qualification")}, allow_nan=False))
    except (ValueError, RuntimeError, OSError, TypeError) as error:
        parser.exit(2, f"teacher {arguments.command} failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
