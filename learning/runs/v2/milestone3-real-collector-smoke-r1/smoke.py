"""Bounded real-API integration test; never creates an optimizer or updates weights."""
import hashlib
import json
from pathlib import Path
import resource
import sys
import time
import traceback

START = time.monotonic()
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PLAN = json.loads((HERE / "plan.json").read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def peak_rss():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def guard():
    if time.monotonic() - START >= PLAN["wall_limit_seconds"]:
        raise RuntimeError("Integration test wall guard expired")
    if peak_rss() > PLAN["RSS_limit_bytes"]:
        raise RuntimeError("Integration test observed peak RSS guard exceeded")


def verify_sources():
    for name, expected in PLAN["source_sha256"].items():
        assert digest(ROOT / name) == expected, name
    assert digest(ROOT / "python/dodge_rl/_native.cpython-312-darwin.so") == PLAN["extension_sha256"]


def main():
    verify_sources()
    import numpy as np
    import torch
    from dodge_rl import VecDodgeEnv
    from dodge_rl.models.teacher import OmniscientEntityTeacher
    from dodge_rl.ppo import PPOConfig, collect_rollout, compute_gae

    torch.set_num_threads(PLAN["CPU_threads"])
    torch.manual_seed(34001)
    model = OmniscientEntityTeacher().cpu()
    before_parameters = {name: value.detach().clone() for name, value in model.state_dict().items()}
    config = dict(PLAN["env"])
    config["excluded_seed_ranges"] = [tuple(pair) for pair in config["excluded_seed_ranges"]]
    env = VecDodgeEnv(**config)
    assert env.batch_info()["effective_excluded_seed_ranges"] == config["excluded_seed_ranges"]
    kwargs = dict(config=PPOConfig(), check_guard=guard)
    first = collect_rollout(model, env, 8, "cpu", **kwargs)
    retained = first.batch.global_feats.clone()
    second = collect_rollout(model, env, 8, "cpu", observation=first.observations, **kwargs)
    assert torch.equal(first.batch.global_feats, retained)
    assert torch.equal(first.batch.next_values[-1], second.batch.values[0])
    summaries = []
    for collection in (first, second):
        batch = collection.batch
        assert batch.shape == (8, 2)
        assert batch.entity_feats.shape == (8, 2, 80, 16)
        for name in ("raw_rewards", "score_delta_raw_fixed", "alive_raw_frames", "elapsed_raw_frames"):
            assert getattr(batch, name) is not None
        assert torch.equal(batch.rewards, batch.raw_rewards * 0.1)
        advantages, returns = compute_gae(batch.rewards, batch.values, batch.next_values,
                                         batch.terminated, batch.truncated)
        rewards = batch.rewards.numpy().astype(np.float64)
        values = batch.values.numpy().astype(np.float64)
        next_values = batch.next_values.numpy().astype(np.float64)
        terminated = batch.terminated.numpy()
        truncated = batch.truncated.numpy()
        # Independent explicit segment sum, rather than the implementation's recurrence.
        reference = np.zeros_like(rewards)
        for start in range(8):
            for slot in range(2):
                multiplier = 1.0
                for step in range(start, 8):
                    delta = rewards[step, slot] - values[step, slot]
                    if not terminated[step, slot]:
                        delta += 0.995 * next_values[step, slot]
                    reference[start, slot] += multiplier * delta
                    if terminated[step, slot] or truncated[step, slot]:
                        break
                    multiplier *= 0.995 * 0.95
        np.testing.assert_allclose(advantages.numpy(), reference, rtol=0, atol=1e-5)
        np.testing.assert_allclose(returns.numpy(), reference + values, rtol=0, atol=1e-5)
        for info in collection.completed_episodes:
            assert not info["seed"]["evaluation"]
            assert all(not low <= info["seed"]["actual_seed"] <= high
                       for low, high in config["excluded_seed_ranges"])
        summaries.append({"transitions": batch.transitions,
                          "raw_frames": int(batch.elapsed_raw_frames.sum()),
                          "completed_episodes": len(collection.completed_episodes),
                          "caps": int(batch.truncated.sum()),
                          "deaths": int(batch.terminated.sum()),
                          "next_episode_indices": collection.batch_info["next_episode_indices"]})
    for name, value in model.state_dict().items():
        assert torch.equal(value, before_parameters[name]), name
    assert all(parameter.grad is None for parameter in model.parameters())
    verify_sources()
    guard()
    return {"status": "passed", "collections": summaries,
            "optimizer_updates": 0, "parameters_unchanged": True,
            "independent_float64_GAE_reference": True,
            "old_rollout_ownership": True, "cross_rollout_value_alignment": True,
            "torch_version": torch.__version__, "numpy_version": np.__version__,
            "device": "cpu", "MPS_used": False,
            "limitations": "Tiny no-update integration test; no learning, performance, or whole-trainer qualification."}


record = {}
try:
    record = main()
except BaseException as error:
    record = {"status": "failed", "error": repr(error), "traceback": traceback.format_exc()}
    raise
finally:
    record.update(elapsed_seconds=time.monotonic() - START,
                  observed_peak_self_RSS_bytes=peak_rss(),
                  source_sha256=PLAN["source_sha256"], extension_sha256=PLAN["extension_sha256"],
                  script_sha256=digest(Path(__file__)), plan_sha256=digest(HERE / "plan.json"))
    with (HERE / "result.json").open("x") as stream:
        json.dump(record, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps(record, sort_keys=True, allow_nan=False))
