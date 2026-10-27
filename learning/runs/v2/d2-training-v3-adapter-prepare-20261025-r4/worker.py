"""Single-use v3 D2 PPO worker. Imports learner/native code only after pin checks."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import signal
import sys
import time
import traceback

import adapter
import helper as util


def main(registration_path, expected_sha, started):
    registration_path = Path(registration_path).resolve()
    adapter.need(adapter.sha(registration_path) == expected_sha, "Registration hash differs")
    reg = json.loads(registration_path.read_text())
    adapter.validate_registration(reg, reg["root"])
    adapter.need(Path(__file__).resolve() == Path(reg["runner_path"]).resolve(),
                 "Worker source path differs from registration")
    adapter.need(Path(sys.executable).resolve() == Path(reg["interpreter"]).resolve(),
                 "Worker interpreter differs from registration")
    adapter.check_import_cache(reg)
    sys.path.insert(0, reg["runtime_root"])
    import numpy as np
    import torch
    import dodge_rl
    from dodge_rl import checkpoints as ckpt
    from dodge_rl.dev_eval import evaluate, validate_summary
    from dodge_rl.identity import identity_hash
    from dodge_rl.models.teacher import OmniscientEntityTeacher
    from dodge_rl.ppo import PPOConfig, collect_rollout, ppo_update

    adapter.need(Path(dodge_rl.__file__).resolve() == Path(reg["runtime_root"], "dodge_rl/__init__.py").resolve(),
                 "Imported runtime package differs")
    adapter.need({"python": sys.version.split()[0], "torch": str(torch.__version__),
                  "numpy": str(np.__version__)} == reg["runtime_versions"], "Runtime versions differ")
    config = json.loads(Path(reg["config_path"]).read_text())
    adapter.need(config["ppo"] == util.PPO and config["device"] == "mps"
                 and config["batch_size"] == 64 and config["rollout_steps"] == 256
                 and config["action_repeat"] == 4 and config["num_threads"] == 4
                 and config["chunk_size"] == 8 and config["excluded_seed_ranges"] == util.RANGES,
                 "Frozen learner/environment settings differ")
    out = Path(reg["output"])
    result = {"status": "failed", "updates": 0, "evaluated_updates": [],
              "training_eligible": False, "first_failure": None}
    util.LIMITS = adapter.LIMITS
    with (out / "resources.jsonl").open("x") as resources:
        guard = util.Guard(reg, started, torch, resources)
        previous = {n: signal.getsignal(n) for n in (signal.SIGINT, signal.SIGTERM)}
        for number in previous:
            signal.signal(number, guard.signal)
        try:
            guard.check()
            adapter.check_import_cache(reg)
            result["import_policy_checked_pre_project_import"] = True
            torch.set_num_threads(4)
            adapter.need(torch.backends.mps.is_available(), "MPS unavailable")
            parent = ckpt.load_checkpoint(Path(reg["parent"]["path"]), expected_sha256=adapter.PARENT_SHA)
            ckpt.require_complete_update(parent)
            adapter.need(parent["tag"] == "candidate" and parent["identity"]["config"]["phase"] == "D1",
                         "Parent is not accepted D1 candidate")
            model = OmniscientEntityTeacher().to(device="mps", dtype=torch.float32)
            adapter.need(model.architecture_description() == parent["identity"]["architecture"], "Architecture differs")
            optimizer = torch.optim.Adam(model.parameters(), lr=util.PPO["learning_rate"], eps=util.PPO["adam_eps"])
            ckpt.restore_learner(parent, model, optimizer, "mps")
            restored = {"model": model.state_dict(), "Adam": optimizer.state_dict(), "RNG": ckpt.capture_rng("mps")}
            expected = {"model": parent["model"], "Adam": parent["optimizer"], "RNG": parent["rng"]}
            equal = {key: util.fingerprint(restored[key]) == util.fingerprint(expected[key]) for key in restored}
            util.save(out / "entry-restoration.json", {"matched": equal,
                "components": {key: {"matched": equal[key], "restored_sha256": util.fingerprint(restored[key]),
                "expected_sha256": util.fingerprint(expected[key]),
                "mismatch_paths": util.mismatch_paths(restored[key], expected[key])} for key in restored},
                "before_environment_or_gradients": True, "parent_sha256": adapter.PARENT_SHA})
            adapter.need(all(equal.values()), "Accepted D1 restoration differs")
            identity = {"version": "teacher_identity_v3", "run_id": reg["run_id"],
                "phase": "D2", "parent_checkpoint_sha256": adapter.PARENT_SHA,
                "config_sha256": reg["pins"][reg["config_path"]],
                "policy_sha256": reg["policy"]["sha256"], "runtime_sha256": reg["runtime_sha256"],
                "native_sha256": reg["native"]["sha256"],
                "architecture": model.architecture_description(), "config": config}
            identity_sha = identity_hash(identity)
            env = dodge_rl.VecDodgeEnv(batch_size=64, action_repeat=4, difficulty=2,
                patterns_enabled=True, powerups_enabled=True, raw_frame_cap=18000, num_threads=4,
                chunk_size=8, render_pixels=False, auxiliary_targets=False, run_seed=reg["run_seed"],
                initial_episode_indices=[0] * 64,
                excluded_seed_ranges=[tuple(v) for v in reg["seed_excluded_ranges"]])
            observation, ppo = env.observations(), PPOConfig(**config["ppo"])
            counters = {"updates": 0, "optimizer_steps": 0, "environment_decisions": 0, "raw_frames": 0}
            progress = {"phase": "between_updates", "complete": True, "in_update": False,
                        "completed_updates": 0}
            with (out / "training-episodes.jsonl").open("x") as episodes, \
                 (out / "training-metrics.jsonl").open("x") as metrics:
                util.emit(episodes, {"kind": "initial", "phase_update": 0,
                                     "info": env.episode_info(), "batch_info": env.batch_info()})

                def evaluate_at(update):
                    guard.check()
                    before = {"model": util.fingerprint(model.state_dict()),
                              "Adam": util.fingerprint(optimizer.state_dict()),
                              "RNG": util.fingerprint(ckpt.capture_rng("mps")),
                              "env": util.fingerprint([env.episode_info(), env.batch_info()])}
                    next_indices, abandoned = ckpt.episode_resume_state(env, 64)
                    state = adapter.checkpoint_payload(model=ckpt._cpu_copy(model.state_dict()),
                        optimizer=ckpt._cpu_copy(optimizer.state_dict()), rng=ckpt.capture_rng("mps"),
                        registration=reg, registration_sha256=expected_sha, counters=dict(counters),
                        run_seed=reg["run_seed"], identity=identity, identity_sha256=identity_sha,
                        next_episode_indices=next_indices, abandoned_current_episodes=abandoned,
                        update_progress=dict(progress), cumulative_wall_seconds=time.monotonic() - started)
                    path = out / f"checkpoint-{update:06d}-candidate.pt"
                    digest = ckpt.save_checkpoint(path, state)
                    with (out / f"evaluation-{update:06d}.jsonl").open("x") as stream:
                        summary = evaluate(model, "D2", "mps", check_guard=guard.check, episode_stream=stream)
                    validate_summary(summary)
                    after = {"model": util.fingerprint(model.state_dict()),
                             "Adam": util.fingerprint(optimizer.state_dict()),
                             "RNG": util.fingerprint(ckpt.capture_rng("mps")),
                             "env": util.fingerprint([env.episode_info(), env.batch_info()])}
                    adapter.need(before == after, "Evaluation changed learner, RNG, or environment state")
                    summary_record = {"phase_update": update, "summary": summary,
                        "performance": util.performance(summary), "checkpoint": path.name,
                        "checkpoint_sha256": digest, "training_state_unchanged": True,
                        "training_eligible": False}
                    util.save(out / f"evaluation-{update:06d}.json", summary_record)
                    result["evaluated_updates"].append(update)
                    print(json.dumps({"phase_update": update, "performance": summary_record["performance"]}), flush=True)

                evaluate_at(0)
                for update in range(1, 73):
                    guard.check()
                    collection = collect_rollout(model, env, 256, "mps", observation=observation,
                                                 config=ppo, check_guard=guard.check)
                    observation = collection.observations
                    events = [(item["rollout_step"], 0, "completed", item) for item in collection.completed_episodes]
                    for reset in collection.reset_info:
                        events.append((reset["rollout_step"], 1, "reset", reset))
                    for step, _, kind, item in sorted(events):
                        util.emit(episodes, {"kind": kind, "phase_update": update,
                            "rollout_step": step, **item} if kind == "completed" else
                            {"kind": "reset", "phase_update": update, "rollout_step": step,
                             "indices": item["indices"], "info": item["info"]})
                    value = ppo_update(model, optimizer, collection.batch, ppo, check_guard=guard.check,
                                       progress=progress, critic_diagnostics=True)
                    util.finite_tree(value)
                    diag = value["critic_diagnostics"]
                    adapter.need(diag["version"] == "same_batch_critic_diagnostics_v1", "Critic diagnostic schema differs")
                    pre, post = diag["pre_update"], diag["post_update"]
                    adapter.need(pre["target_mean"] == post["target_mean"] and
                                 pre["target_variance"] == post["target_variance"], "Diagnostic targets changed")
                    old_ev, direct_ev = value["explained_variance"], pre["explained_variance"]
                    adapter.need((old_ev is None and direct_ev is None) or
                        (old_ev is not None and direct_ev is not None and math.isclose(old_ev, direct_ev, rel_tol=1e-6, abs_tol=1e-6)),
                        "Direct/legacy explained variance differs")
                    counters["updates"] = update
                    counters["optimizer_steps"] += value["optimizer_steps"]
                    counters["environment_decisions"] += collection.batch.actions.numel()
                    counters["raw_frames"] += int(collection.batch.elapsed_raw_frames.sum().item())
                    result["updates"] = update
                    util.emit(metrics, {"phase_update": update, "metrics": value,
                        "counters": dict(counters), "update_progress": dict(progress),
                        "elapsed_seconds": time.monotonic() - started})
                    if update in adapter.EVAL_UPDATES:
                        evaluate_at(update)
                    guard.check()
            result.update(status="completed", counters=counters)
            guard.check(finalizing=True)
        except BaseException as error:
            result.update(error=repr(error), traceback=traceback.format_exc(),
                update_progress=locals().get("progress", {}), first_failure=guard.first_failure or
                {"monotonic": time.monotonic(), "error": repr(error)}, first_signal=guard.first_signal)
        finally:
            try:
                guard.last_sample = -math.inf
                guard.check(finalizing=True)
                adapter.check_import_cache(reg)
                result["import_policy_checked_final"] = True
            except BaseException as final_error:
                result["status"] = "failed"
                result.setdefault("error", repr(final_error))
                result["finalization_error"] = repr(final_error)
                result.setdefault("first_failure", guard.first_failure or {"error": repr(final_error)})
            for number, handler in previous.items():
                signal.signal(number, handler)
            result.update(elapsed_seconds=time.monotonic() - started, peak_rss_bytes=guard.peak_rss,
                          peak_mps_driver_bytes=guard.peak_mps)
            util.save(out / "worker-result.json", result)
    return 0 if result.get("status") == "completed" and result.get("updates") == 72 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--registration", required=True)
    parser.add_argument("--registration-sha256", required=True)
    parser.add_argument("--started", required=True, type=float)
    args = parser.parse_args()
    raise SystemExit(main(args.registration, args.registration_sha256, args.started))
