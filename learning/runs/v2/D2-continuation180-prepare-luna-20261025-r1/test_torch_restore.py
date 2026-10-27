"""Restore exact accepted parent model/Adam/RNG; no environment, rollout, eval, or gradient."""
import hashlib
import os
from pathlib import Path
import sys

import torch

import runner

ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "docs/SPEC_PRIVILEGED_VIT_RL.md").is_file())
PARENT = ROOT / "learning/runs/v2/D2-gradient-alignment-20261025-r2/checkpoint-000180-candidate.pt"
RUNTIME = Path(__file__).resolve().parents[1] / "D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    sidecar = Path(str(PARENT) + ".json")
    before = (digest(PARENT), digest(sidecar))
    assert torch.backends.mps.is_available(), "MPS required for exact saved RNG backend restore"
    sys.path.insert(0, str(RUNTIME))
    from dodge_rl import checkpoints as ckpt
    from dodge_rl.models.teacher import OmniscientEntityTeacher
    state = ckpt.load_checkpoint(PARENT, expected_sha256=runner.PARENT_SHA)
    ckpt.require_complete_update(state)
    assert state["tag"] == "candidate" and state["phase"] == "D2"
    assert state["update_progress"]["complete"] is True
    assert state["update_progress"]["completed_updates"] == 48
    assert state["training_eligible"] is False and state["promoted"] is False
    assert state["registration_sha256"] == runner.PARENT_REGISTRATION_SHA
    assert state["cumulative_counters"]["updates"] == 228
    assert len(state["next_episode_indices"]) == len(state["abandoned_current_episodes"]) == 64

    model = OmniscientEntityTeacher().to(device="mps", dtype=torch.float32)
    optimizer = torch.optim.Adam(model.parameters(), lr=runner.PPO["learning_rate"], eps=runner.PPO["adam_eps"])
    assert len(optimizer.param_groups) == 1
    group = optimizer.param_groups[0]
    assert group["lr"] == runner.PPO["learning_rate"] and group["eps"] == runner.PPO["adam_eps"]
    assert group["betas"] == (.9, .999) and group["weight_decay"] == 0
    assert group["amsgrad"] is False and group["maximize"] is False
    ckpt.restore_learner(state, model, optimizer, "mps")
    rng_first = ckpt.capture_rng("mps")
    rng_second = ckpt.capture_rng("mps")
    assert runner.fingerprint(rng_first) == runner.fingerprint(rng_second), "Repeated RNG capture consumed RNG state"
    actual = {"model": model.state_dict(), "Adam": optimizer.state_dict(), "RNG": rng_first}
    expected = {"model": state["model"], "Adam": state["optimizer"], "RNG": state["rng"]}
    equality = {key: runner.fingerprint(actual[key]) == runner.fingerprint(expected[key]) for key in actual}
    details = {key: runner.mismatch_paths(actual[key], expected[key]) for key in actual}
    assert all(equality.values()), {"matched": equality, "mismatch_paths": details}
    assert before == (digest(PARENT), digest(sidecar)), "Parent checkpoint or metadata changed"
    print("actual accepted D2 parent model/Adam/MPS RNG restore passed; no environment or optimizer step")


if __name__ == "__main__":
    main()
