"""Explicit, parent-leased M3 teacher experiments. No B/E evaluation or retries.

Prepare with ``config`` then ``freeze``. Actual ``probe``, ``pilot`` and ``stage``
commands require the root's matching frozen-review lease in the existing ledger.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import time
import traceback

import numpy as np
import torch

from . import checkpoints as ckpt
from .dev_eval import evaluate, pilot_improved, progress_passed
from .identity import (ROOT, OBSERVATION_KEYS, build_identity, canonical_bytes, check_frozen,
                       default_config, file_hash, identity_hash, read_protocol, require,
                       training_env_config, validate_config, verify_training_env)
from .models.teacher import OmniscientEntityTeacher
from .ppo import PPOConfig, collect_rollout, ppo_update
from .supervision import (CUTOFF, RSS_LIMIT, Guard, GuardStop, assert_lease, check_budget,
                          cancellation_signals, current_rss_bytes, emit, stop_owned, utc_now)


def save_json(path: Path, value) -> None:
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def read_config(path: Path, expected_hash: str | None = None) -> dict:
    raw = path.read_bytes()
    if expected_hash is not None:
        require(hashlib.sha256(raw).hexdigest() == expected_hash, "Registered config document changed")
    return validate_config(json.loads(raw))


def verify_inputs(args, config: dict) -> dict:
    require(file_hash(args.config) == args.config_sha256, "Registered config document changed")
    frozen = check_frozen(args.identity, args.identity_sha256, config)
    require(file_hash(args.config) == args.config_sha256, "Config changed during identity verification")
    if args.resume_checkpoint is not None:
        require(file_hash(args.resume_checkpoint) == args.resume_checkpoint_sha256,
                "Resume checkpoint changed after authorization")
    if args.parent_checkpoint is not None:
        require(file_hash(args.parent_checkpoint) == config["parent_checkpoint_sha256"],
                "Transition parent changed after authorization")
    return frozen


def synchronize(device) -> None:
    if torch.device(device).type == "mps":
        torch.mps.synchronize()


def seed_initialization(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def make_optimizer(model, config: dict):
    ppo = PPOConfig(**config["ppo"])
    return torch.optim.Adam(model.parameters(), lr=ppo.learning_rate, eps=ppo.adam_eps)


def require_raw_diagnostics(batch) -> None:
    for name in ("raw_rewards", "score_delta_raw_fixed", "alive_raw_frames", "elapsed_raw_frames"):
        require(getattr(batch, name, None) is not None, f"Collected batch omitted mandatory {name}")


def remaining_phase_budget(config: dict, resume_state: dict | None) -> tuple[float, float]:
    # A checkpoint cannot account for worker time consumed after its publication.
    # Until parent-owned terminal receipt anchoring exists, no same-phase restart
    # may derive a new allowance from checkpoint-local consumption counters.
    require(resume_state is None,
            "Same-phase resume disabled: no parent-owned cumulative terminal receipt budget anchor")
    return 0.0, float(config["phase_settings"]["budget_seconds"])


def choose_probe_device(measurements: list[dict]) -> tuple[str, list[str]]:
    require(all(row["status"] in {"completed", "unavailable"} for row in measurements),
            "Device probe correctness failure prevents device selection")
    completed = [row for row in measurements if row["status"] == "completed"]
    require(bool(completed), "No complete device measurement")
    reference = next((row for row in completed if row["device"] == "cpu"), completed[0])
    work = (reference["optimizer_steps"], reference["metrics"]["epochs_completed"])
    comparable = [row for row in completed
                  if (row["optimizer_steps"], row["metrics"]["epochs_completed"]) == work]
    excluded = [row["device"] for row in completed if row not in comparable]
    return min(comparable, key=lambda row: row["measured_inference_plus_update_seconds"])["device"], excluded


class TrainingEnvLog:
    """Stream returned native boundaries even if collection later stops early."""

    def __init__(self, inner, counters, stream):
        self.inner, self.counters, self.stream = inner, counters, stream

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def step(self, actions):
        result = self.inner.step(actions)
        self.counters["environment_decisions"] += len(actions)
        self.counters["raw_frames"] += int(result["elapsed_raw_frames"].sum())
        for info in result["info"]:
            if info["terminated"] or info["truncated"]:
                emit(self.stream, {"kind": "native_completed_episode", "info": info,
                                   "observed_before_collection_acceptance": True})
        return result

    def reset_done(self, indices):
        result = self.inner.reset_done(indices)
        emit(self.stream, {"kind": "native_reset", "indices": list(indices), "info": result["info"]})
        return result


class Experiment:
    def __init__(self, args, config: dict, identity: dict, guard: Guard):
        self.args, self.config, self.identity, self.guard = args, config, identity, guard
        self.directory = args.run_dir
        if args.resume_checkpoint is not None:
            state = ckpt.load_checkpoint(args.resume_checkpoint, identity, args.resume_checkpoint_sha256)
            ckpt.require_complete_update(state)
            remaining_phase_budget(config, state)
        self.device = torch.device(config["device"])
        require(self.device.type == "cpu" or torch.backends.mps.is_available(), "MPS is unavailable")
        self.model = OmniscientEntityTeacher().to(self.device)
        self.optimizer = make_optimizer(self.model, config)
        self.ppo = PPOConfig(**config["ppo"])
        self.env = None
        self.observation = None
        self.progress = {}
        self.counters = {"updates": 0, "phase_updates": 0, "optimizer_steps": 0,
                         "environment_decisions": 0, "raw_frames": 0, "checkpoint_index": 0}
        self.last_metrics = None
        self.actor_gradient_seen = self.critic_gradient_seen = False
        self.large_kl_iterations = 0
        self.context = {"D1_competence_demonstrated": False}
        self.episodes = (self.directory / "training-episodes.jsonl").open("x")
        self.metrics = (self.directory / "training-metrics.jsonl").open("x")
        self.guard.check(force=True)
        if args.parent_checkpoint is not None:
            state, certificate = ckpt.validate_transition(args.parent_checkpoint, identity)
            ckpt.restore_learner(state, self.model, self.optimizer, self.device)
            self.counters = copy.deepcopy(state["counters"])
            self.counters["phase_updates"] = 0
            self.context = copy.deepcopy(state.get("run_context", self.context))
            self.large_kl_iterations = self.context.get("large_kl_iterations", 0)
            self.last_metrics = self.context.get("last_metrics")
            self.context.pop("pilot_before", None)
            self.context.pop("pilot_initial_checkpoint", None)
            self.context.pop("pilot_initial_checkpoint_sha256", None)
            if state["identity"]["config"]["phase"] in {"D1", "D2"}:
                self.context["D1_competence_demonstrated"] = True
            for abandoned in state["abandoned_episodes"]:
                emit(self.episodes, {**abandoned, "reason": "curriculum_namespace_transition"})
            save_json(self.directory / "parent-lineage.json", {
                "parent_checkpoint": str(args.parent_checkpoint),
                "parent_sha256": file_hash(args.parent_checkpoint),
                "parent_evaluation": certificate, "transition_to": config["phase"]})
            self.make_environment([0] * config["batch_size"])
        else:
            require(config["phase"] in {"probe", "pilot"}, "Long stage requires an explicit eligible parent")

    def close(self):
        self.episodes.close()
        self.metrics.close()

    def make_environment(self, initial_episode_indices=None):
        from . import VecDodgeEnv
        self.guard.check()
        self.env = TrainingEnvLog(VecDodgeEnv(**training_env_config(self.config, initial_episode_indices)),
                                  self.counters, self.episodes)
        metadata = verify_training_env(self.env, self.config, initial_episode_indices)
        emit(self.episodes, {"kind": "initial", "info": self.env.episode_info(), "batch_info": metadata})
        self.observation = self.env.observations()
        self.guard.check()

    def checkpoint(self, tag: str) -> tuple[Path, str]:
        self.counters["checkpoint_index"] += 1
        path = self.directory / f"checkpoint-{self.counters['checkpoint_index']:06d}-{tag}.pt"
        state = ckpt.make_state(self.model, self.optimizer, self.identity, self.counters,
                               env=self.env, tag=tag, progress=self.progress, device=self.device,
                               parent_sha256=self.config["parent_checkpoint_sha256"])
        self.context.update(actor_gradient_seen=self.actor_gradient_seen,
                            critic_gradient_seen=self.critic_gradient_seen,
                            large_kl_iterations=self.large_kl_iterations,
                            last_metrics=copy.deepcopy(self.last_metrics),
                            consumed_wall_seconds=self.args.consumed_wall_seconds
                            + time.monotonic() - self.args.execution_started_monotonic)
        state["run_context"] = copy.deepcopy(self.context)
        state["counter_semantics"] = "Successful public step returns; native partial exceptions require retained per-slot diagnostics."
        digest = ckpt.save_checkpoint(path, state)
        # The checkpoint already contains these records; this stream makes their
        # fresh-environment semantics inspectable without loading Torch data.
        emit(self.episodes, {"kind": "checkpoint_resume_boundary", "checkpoint_sha256": digest,
                            "next_episode_indices": state["next_episode_indices"],
                            "abandoned_on_resume": state["abandoned_episodes"]})
        return path, digest

    def evaluate_checkpoint(self, path: Path, digest: str, *, pilot_before=None) -> dict:
        phase = self.config["phase"]
        stages = ["D2", "D3"] if phase == "D3" else ["D1" if phase == "pilot" else phase]
        evaluations = {}
        for stage in stages:
            self.guard.check(force=True)
            log = self.directory / f"{path.stem}-{stage}-development.jsonl"
            with log.open("x") as stream:
                evaluations[stage] = evaluate(self.model, stage, self.device,
                                               check_guard=self.guard.check, episode_stream=stream)
            self.guard.check(force=True)
        require(file_hash(path) == digest, "Evaluated checkpoint changed")
        if phase == "pilot":
            after = evaluations["D1"]
            require(pilot_before is not None, "Pilot baseline missing")
            passed = (pilot_improved(pilot_before, after) and self.actor_gradient_seen
                      and self.critic_gradient_seen and self.counters["phase_updates"] > 0)
            if self.last_metrics is not None and self.last_metrics["entropy"] < 0.3 \
                    and not progress_passed("D1", {"D1": after}):
                passed = False
            certificate = {"phase": phase, "checkpoint_sha256": digest, "complete": True,
                           "passed": passed, "before": pilot_before, "evaluations": evaluations,
                           "actor_gradient_seen": self.actor_gradient_seen,
                           "critic_gradient_seen": self.critic_gradient_seen,
                           "completed_training_updates": self.counters["phase_updates"]}
        else:
            certificate = {"phase": phase, "checkpoint_sha256": digest, "complete": True,
                           "passed": bool(progress_passed(phase, evaluations)),
                           "evaluations": evaluations}
        save_json(ckpt.evaluation_path(path), certificate)
        self.guard.check(force=True)
        return certificate

    def update_once(self):
        self.guard.check()
        require(self.env is not None, "Training environment missing")
        collection = collect_rollout(self.model, self.env, self.config["rollout_steps"],
                                     self.device, observation=self.observation,
                                     config=self.ppo, check_guard=self.guard.check)
        require_raw_diagnostics(collection.batch)
        self.observation = collection.observations
        emit(self.episodes, {"kind": "collection_accepted", "update": self.counters["updates"],
                            "completed_episodes": len(collection.completed_episodes),
                            "reset_events": len(collection.reset_info),
                            "transitions": collection.batch.transitions,
                            "returned_raw_frames": int(collection.batch.elapsed_raw_frames.sum().item())})
        self.progress = {}
        self.last_metrics = ppo_update(self.model, self.optimizer, collection.batch, self.ppo,
                                       check_guard=self.guard.check, progress=self.progress)
        self.counters["updates"] += 1
        self.counters["phase_updates"] += 1
        self.counters["optimizer_steps"] += self.last_metrics["optimizer_steps"]
        self.actor_gradient_seen |= self.last_metrics["actor_grad_norm"] > 0
        self.critic_gradient_seen |= self.last_metrics["critic_grad_norm"] > 0
        self.large_kl_iterations = self.large_kl_iterations + 1 if self.last_metrics["approx_kl"] > 0.1 else 0
        emit(self.metrics, {"at_utc": utc_now().isoformat(), "counters": self.counters,
                            "metrics": self.last_metrics})
        if self.large_kl_iterations >= 3:
            raise GuardStop("Approximate KL exceeded 0.1 on three consecutive iterations")
        self.guard.check()

    def pilot(self) -> dict:
        if "pilot_before" in self.context:
            before = self.context["pilot_before"]
            initial_path = Path(self.context["pilot_initial_checkpoint"])
            initial_hash = self.context["pilot_initial_checkpoint_sha256"]
        else:
            initial_path, initial_hash = self.checkpoint("pilot_initial")
            with (self.directory / "pilot-before-development.jsonl").open("x") as stream:
                before = evaluate(self.model, "D1", self.device, check_guard=self.guard.check, episode_stream=stream)
            self.context.update(pilot_before=before, pilot_initial_checkpoint=str(initial_path.resolve()),
                                pilot_initial_checkpoint_sha256=initial_hash)
        save_json(self.directory / "pilot-before.json", {"checkpoint_sha256": initial_hash, **before})
        self.context["D1_competence_demonstrated"] |= bool(progress_passed("D1", {"D1": before}))
        if self.env is None:
            self.make_environment()
        reserve = max(30.0, 2 * before["elapsed_seconds"]) + 10.0
        while self.guard.deadline - time.monotonic() > reserve:
            self.update_once()
            if self.counters["phase_updates"] % 8 == 0:
                self.checkpoint("periodic")
        require(self.counters["phase_updates"] > 0, "Pilot completed no learner update")
        self.guard.check(force=True)
        end_path, end_hash = self.checkpoint("candidate")
        certificate = self.evaluate_checkpoint(end_path, end_hash, pilot_before=before)
        return {"status": "passed" if certificate["passed"] else "pilot_failed",
                "phase": "pilot", "initial_checkpoint": initial_path.name,
                "initial_checkpoint_sha256": initial_hash, "checkpoint": end_path.name,
                "checkpoint_sha256": end_hash, "evaluation": certificate,
                "counters": self.counters, "B_opened": False}

    def stage(self) -> dict:
        require(self.env is not None, "Stage was not initialized from an eligible checkpoint")
        while True:
            if self.counters["phase_updates"] % 16 == 0:
                path, digest = self.checkpoint("candidate")
                certificate = self.evaluate_checkpoint(path, digest)
                if certificate["passed"]:
                    return {"status": "passed", "phase": self.config["phase"],
                            "checkpoint": path.name, "checkpoint_sha256": digest,
                            "evaluation": certificate, "counters": self.counters, "B_opened": False}
                results = certificate["evaluations"]
                competence = self.context["D1_competence_demonstrated"] or (
                    "D1" in results and progress_passed("D1", {"D1": results["D1"]}))
                if self.last_metrics is not None and self.last_metrics["entropy"] < 0.3 and not competence:
                    raise GuardStop("Entropy below 0.3 before demonstrated D1 competence")
            self.update_once()
            if self.counters["phase_updates"] % 8 == 0 and self.counters["phase_updates"] % 16:
                self.checkpoint("periodic")

    def probe(self) -> dict:
        self.make_environment()
        path, initial_hash = self.checkpoint("probe_diagnostic")
        starting_weights = copy.deepcopy(self.model.cpu().state_dict())
        self.device = torch.device("cpu")
        collected_at = time.monotonic()
        collection = collect_rollout(self.model, self.env, self.config["rollout_steps"], "cpu",
                                     config=self.ppo, check_guard=self.guard.check)
        require_raw_diagnostics(collection.batch)
        collection_wall = time.monotonic() - collected_at
        for info in collection.completed_episodes:
            emit(self.episodes, {"kind": "probe_completed", "info": info})
        for reset in collection.reset_info:
            emit(self.episodes, {"kind": "probe_reset", **reset})
        # Keep the actual on-policy buffer and its RNG state as diagnostic evidence.
        buffer_path = self.directory / "probe-rollout.pt"
        buffer_hash = ckpt.save_checkpoint(buffer_path, {"batch": collection.batch,
            "sampling_rng": ckpt.capture_rng("cpu"), "initial_checkpoint_sha256": initial_hash,
            "tag": "probe_diagnostic"})
        starting_rng = ckpt.capture_rng("cpu")
        measurements = []
        for device_name in self.config["probe_devices"]:
            self.guard.check(force=True)
            if device_name == "mps" and not torch.backends.mps.is_available():
                measurements.append({"device": device_name, "status": "unavailable"})
                continue
            try:
                device = torch.device(device_name)
                candidate = copy.deepcopy(self.model).to(device)
                candidate.load_state_dict(starting_weights)
                optimizer = make_optimizer(candidate, self.config)
                ckpt.restore_rng(starting_rng, "cpu")
                candidate.eval()
                synchronize(device)
                inference_at = time.monotonic()
                with torch.no_grad():
                    for step in range(self.config["rollout_steps"]):
                        self.guard.check()
                        output = candidate(*(getattr(collection.batch, name)[step].to(device)
                                              for name in OBSERVATION_KEYS))
                        require(bool(torch.isfinite(output.logits).all())
                                and bool(torch.isfinite(output.values).all()), "Nonfinite device probe")
                        del output
                synchronize(device)
                inference_wall = time.monotonic() - inference_at
                synchronize(device)
                update_at = time.monotonic()
                progress = {}
                metrics = ppo_update(candidate, optimizer, collection.batch, self.ppo,
                                     check_guard=self.guard.check, progress=progress)
                synchronize(device)
                update_wall = time.monotonic() - update_at
                diagnostic_identity = copy.deepcopy(self.identity)
                state = ckpt.make_state(candidate, optimizer, diagnostic_identity, self.counters,
                                        env=self.env, tag="probe_diagnostic", progress=progress,
                                        device=device)
                state["actual_measured_device"] = device_name
                final = self.directory / f"probe-{device_name}-updated.pt"
                digest = ckpt.save_checkpoint(final, state)
                measurements.append({"device": device_name, "status": "completed",
                    "inference_wall_seconds": inference_wall, "update_wall_seconds": update_wall,
                    "measured_inference_plus_update_seconds": inference_wall + update_wall,
                    "optimizer_steps": metrics["optimizer_steps"], "metrics": metrics,
                    "checkpoint": final.name, "checkpoint_sha256": digest})
                del candidate, optimizer
            except GuardStop:
                raise
            except Exception as error:
                failure = {"device": device_name, "status": "failed", "error": repr(error),
                           "traceback": traceback.format_exc(), "automatic_retry": False}
                save_json(self.directory / f"probe-{device_name}-failure.json", failure)
                measurements.append(failure)
                raise
        selected, incomparable = choose_probe_device(measurements)
        self.guard.check(force=True)
        return {"status": "passed", "phase": "probe", "selected_device": selected,
                "measurements": measurements, "frozen_rollout_collection_wall_seconds": collection_wall,
                "frozen_rollout": buffer_path.name, "frozen_rollout_sha256": buffer_hash,
                "initial_checkpoint": path.name, "initial_checkpoint_sha256": initial_hash,
                "weights_discarded_from_training": True, "B_opened": False,
                "devices_excluded_from_speed_selection_for_unequal_update_work": incomparable,
                "timing_scope": "Same starting weights and real frozen rollout; completed inference and PPO update, collection wall reported separately. Not a closed-loop training SPS estimate."}


def worker(args) -> int:
    with cancellation_signals() as cancellation:
        return _run_worker(args, cancellation)


def _run_worker(args, cancellation) -> int:
    started = time.monotonic()
    config = read_config(args.config, args.config_sha256)
    require(config["phase"] == args.phase, "Command and registered phase differ")
    require(getattr(args, "resume_checkpoint", None) is None,
            "Same-phase resume disabled: no parent-owned cumulative terminal receipt budget anchor")
    require(args.consumed_wall_seconds == 0,
            "Worker cannot accept checkpoint-local consumed phase budget")
    require(0 <= args.consumed_wall_seconds < config["phase_settings"]["budget_seconds"]
            and args.execution_started_monotonic <= time.monotonic()
            and abs(args.deadline_monotonic - args.execution_started_monotonic
                    - (config["phase_settings"]["budget_seconds"] - args.consumed_wall_seconds)) < 1e-6,
            "Worker deadline does not preserve the registered consumed phase budget")
    remaining = args.deadline_monotonic - time.monotonic()
    require(0 < remaining <= config["phase_settings"]["budget_seconds"], "Worker deadline exceeds registered budget")
    require(utc_now().timestamp() + remaining + 600 <= CUTOFF.timestamp(),
            "Worker deadline and receipt reserve exceed cutoff")
    identity = verify_inputs(args, config)
    torch.set_num_threads(config["num_threads"])
    seed_initialization(config["phase_settings"].get("initialization_seed", 0))
    experiment = None
    with (args.run_dir / "worker-resources.jsonl").open("x") as resources:
        guard = Guard(deadline=args.deadline_monotonic, run_id=args.run_id,
                      identity_sha256=args.identity_sha256, config_sha256=args.config_sha256,
                      stream=resources, identity_check=lambda: verify_inputs(args, config),
                      mps=config["device"] == "mps" or (args.phase == "probe" and torch.backends.mps.is_available()))
        try:
            guard.check(force=True)
            experiment = Experiment(args, config, identity, guard)
            if args.phase == "probe":
                result = experiment.probe()
            elif args.phase == "pilot":
                result = experiment.pilot()
            else:
                result = experiment.stage()
            guard.check(force=True)
            result.update(identity_sha256=args.identity_sha256, config_sha256=args.config_sha256,
                          elapsed_seconds=time.monotonic() - started,
                          maximum_observed_RSS_bytes=guard.maximum_rss,
                          maximum_MPS_driver_bytes=guard.maximum_mps)
            save_json(args.run_dir / "worker-result.json", result)
            return 0 if result["status"] == "passed" else 1
        except BaseException as error:
            cancellation.defer()
            result = {"status": "failed", "phase": args.phase, "error": repr(error),
                      "traceback": traceback.format_exc(), "identity_sha256": args.identity_sha256,
                      "config_sha256": args.config_sha256, "elapsed_seconds": time.monotonic() - started,
                      "maximum_observed_RSS_bytes": guard.maximum_rss,
                      "maximum_MPS_driver_bytes": guard.maximum_mps, "B_opened": False}
            if experiment is not None:
                tag = "interrupted_mid_update" if experiment.progress.get("in_update", False) else (
                    "timeout" if isinstance(error, GuardStop) and "wall" in str(error) else "failure")
                try:
                    path, digest = experiment.checkpoint(tag)
                    result.update(checkpoint=path.name, checkpoint_sha256=digest, checkpoint_tag=tag,
                                  update_progress=experiment.progress)
                except BaseException as checkpoint_error:
                    result["checkpoint_error"] = repr(checkpoint_error)
            save_json(args.run_dir / "worker-result.json", result)
            return 1
        finally:
            cancellation.defer()
            if experiment is not None:
                experiment.close()


def run_supervised(args) -> int:
    with cancellation_signals() as cancellation:
        return _run_supervised(args, cancellation)


def _run_supervised(args, cancellation) -> int:
    started = time.monotonic()
    config = read_config(args.config)
    phase = config["phase"]
    require((args.command == phase) or (args.command == "stage" and phase == args.stage),
            "Command and registered phase differ")
    resume_state = None
    args.resume_checkpoint_sha256 = None
    if args.resume_checkpoint is not None:
        args.resume_checkpoint_sha256 = file_hash(args.resume_checkpoint)
        resume_state = ckpt.load_checkpoint(args.resume_checkpoint, expected_sha256=args.resume_checkpoint_sha256)
        ckpt.require_complete_update(resume_state)
    consumed, remaining = remaining_phase_budget(config, resume_state)
    check_budget(utc_now(), math.ceil(remaining))
    identity_digest, config_digest = file_hash(args.identity), file_hash(args.config)
    args.identity_sha256, args.config_sha256 = identity_digest, config_digest
    assert_lease(args.run_id, identity_digest, config_digest)
    verify_inputs(args, config)
    require(not (args.resume_checkpoint is not None and args.parent_checkpoint is not None),
            "Choose resume or transition parent")
    if phase in {"probe", "pilot"}:
        require(args.parent_checkpoint is None, "Fresh probe/pilot cannot inherit weights")
    if phase == "probe":
        require(args.resume_checkpoint is None, "Probe cannot resume")
    args.run_dir.mkdir(parents=True, exist_ok=False)
    deadline = started + remaining
    command = [sys.executable, "-B", "-m", "dodge_rl.train_teacher", "_worker",
               "--phase", phase, "--config", str(args.config.resolve()),
               "--identity", str(args.identity.resolve()), "--run-id", args.run_id,
               "--run-dir", str(args.run_dir.resolve()), "--identity-sha256", identity_digest,
               "--config-sha256", config_digest, "--deadline-monotonic", str(deadline),
               "--consumed-wall-seconds", str(consumed), "--execution-started-monotonic", str(started)]
    for field in ("resume_checkpoint", "parent_checkpoint"):
        value = getattr(args, field)
        if value is not None:
            command += ["--" + field.replace("_", "-"), str(value.resolve())]
    if args.resume_checkpoint_sha256 is not None:
        command += ["--resume-checkpoint-sha256", args.resume_checkpoint_sha256]
    save_json(args.run_dir / "registered-config.json", config)
    save_json(args.run_dir / "identity.json", json.loads(args.identity.read_bytes()))
    save_json(args.run_dir / "launch-command.json", {"argv": command, "cwd": str(ROOT),
        "started_at_utc": utc_now().isoformat(), "identity_sha256": identity_digest,
        "config_sha256": config_digest, "deadline_monotonic": deadline})
    result = {"status": "failed", "run_id": args.run_id, "phase": phase,
              "identity_sha256": identity_digest, "config_sha256": config_digest,
              "automatic_retries": 0, "limits_relaxed": False, "B_opened": False,
              "guard_semantics": "Cooperative worker RSS/MPS and external sampled RSS/wall; no unsampled hard-OS memory claim."}
    active = None
    with (args.run_dir / "supervisor-resources.jsonl").open("x") as resources, \
            (args.run_dir / "worker-stdout.log").open("xb") as stdout:
        guard = Guard(deadline=deadline, run_id=args.run_id, identity_sha256=identity_digest,
                      config_sha256=config_digest, stream=resources,
                      identity_check=lambda: verify_inputs(args, config), mps=False)
        try:
            guard.check(force=True)
            cancellation.defer()
            active = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=subprocess.STDOUT,
                                      start_new_session=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
            cancellation.resume()
            save_json(args.run_dir / "owned-process.json", {"owned_pid": active.pid, "owned_pgid": active.pid})
            while active.poll() is None:
                guard.check(force=True)
                try:
                    rss = current_rss_bytes(active.pid)
                except ValueError:
                    if active.poll() is not None:
                        break
                    raise
                emit(resources, {"at_utc": utc_now().isoformat(), "owned_worker_pid": active.pid,
                                 "worker_rss_bytes": rss})
                if rss > RSS_LIMIT:
                    raise GuardStop("External observed worker RSS guard exceeded")
                time.sleep(0.5)
            result["worker_exit_code"] = active.wait(timeout=5)
            guard.check(force=True)
            worker_result = json.loads((args.run_dir / "worker-result.json").read_text())
            require(worker_result["identity_sha256"] == identity_digest
                    and worker_result["config_sha256"] == config_digest, "Worker result identity differs")
            require(result["worker_exit_code"] == 0 and worker_result["status"] == "passed",
                    f"Worker failed: {worker_result.get('error', worker_result['status'])}")
            hashes = {str(p.relative_to(args.run_dir)): file_hash(p) for p in sorted(args.run_dir.rglob("*")) if p.is_file()}
            guard.check(force=True)
            result.update(status="passed", worker_result=worker_result)
        except BaseException as error:
            cancellation.defer()
            result.update(status="failed", error=repr(error), traceback=traceback.format_exc())
        finally:
            cancellation.defer()
            if active is not None and result["status"] != "passed":
                result["owned_process_stop"] = stop_owned(active)
            elapsed = time.monotonic() - started
            result.update(finished_at_utc=utc_now().isoformat(), elapsed_seconds=elapsed,
                          consumed_phase_wall_seconds=consumed + elapsed,
                          prior_consumed_wall_seconds=consumed)
            save_json(args.run_dir / "run-result.json", result)
            hashes = {str(p.relative_to(args.run_dir)): file_hash(p) for p in sorted(args.run_dir.rglob("*")) if p.is_file()}
            save_json(args.run_dir / "artifact-sha256.json", hashes)
    return 0 if result["status"] == "passed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    config = sub.add_parser("config", help="Write a new registered configuration; no training")
    config.add_argument("--phase", choices=("probe", "pilot", "D1", "D2", "D3"), required=True)
    config.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    config.add_argument("--parent-checkpoint", type=Path)
    config.add_argument("--output", type=Path, required=True)
    freeze = sub.add_parser("freeze", help="Pin current source/runtime/config; no training")
    freeze.add_argument("--config", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    for name in ("probe", "pilot", "stage", "_worker"):
        run = sub.add_parser(name)
        run.add_argument("--config", type=Path, required=True)
        run.add_argument("--identity", type=Path, required=True)
        run.add_argument("--run-dir", type=Path, required=True)
        run.add_argument("--run-id", required=True)
        run.add_argument("--resume-checkpoint", type=Path)
        run.add_argument("--parent-checkpoint", type=Path)
        if name == "stage":
            run.add_argument("--stage", choices=("D1", "D2", "D3"), required=True)
        if name == "_worker":
            run.add_argument("--phase", choices=("probe", "pilot", "D1", "D2", "D3"), required=True)
            run.add_argument("--identity-sha256", required=True)
            run.add_argument("--config-sha256", required=True)
            run.add_argument("--deadline-monotonic", type=float, required=True)
            run.add_argument("--consumed-wall-seconds", type=float, required=True)
            run.add_argument("--execution-started-monotonic", type=float, required=True)
            run.add_argument("--resume-checkpoint-sha256")
    args = parser.parse_args()
    if args.command == "config":
        parent = None if args.parent_checkpoint is None else file_hash(args.parent_checkpoint)
        value = default_config(args.phase, args.device, parent)
        save_json(args.output, value)
        print(json.dumps({"config": str(args.output), "config_sha256": file_hash(args.output)}))
        return 0
    if args.command == "freeze":
        value = build_identity(read_config(args.config))
        save_json(args.output, value)
        print(json.dumps({"identity": str(args.output), "identity_sha256": file_hash(args.output),
                          "config_sha256": file_hash(args.config),
                          "semantic_config_sha256": value["config_sha256"]}))
        return 0
    return worker(args) if args.command == "_worker" else run_supervised(args)


if __name__ == "__main__":
    raise SystemExit(main())
