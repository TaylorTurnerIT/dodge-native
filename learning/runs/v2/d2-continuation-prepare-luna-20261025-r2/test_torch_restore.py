"""Restore exact accepted parent model/Adam/RNG; no environment, rollout, eval, or gradient."""
import hashlib
import os
from pathlib import Path
import sys

import torch

import runner

ROOT = Path(__file__).resolve().parents[4]
PARENT = ROOT / "learning/runs/v2/D2-training-v3-20261025-r1/checkpoint-000072-candidate.pt"
RUNTIME = ROOT / "learning/runs/v2/critic-diagnostic-parent-prepare-20261025-r1/runtime"


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
    assert state["update_progress"]["completed_updates"] == 72
    assert state["training_eligible"] is False and state["promoted"] is False
    assert state["registration_sha256"] == runner.PARENT_REGISTRATION_SHA
    assert state["cumulative_counters"]["updates"] == 120
    assert len(state["next_episode_indices"]) == len(state["abandoned_current_episodes"]) == 64

    model = OmniscientEntityTeacher().to(device="mps", dtype=torch.float32)
    optimizer = torch.optim.Adam(model.parameters(), lr=runner.PPO["learning_rate"], eps=runner.PPO["adam_eps"])
    ckpt.restore_learner(state, model, optimizer, "mps")
    actual = {"model": model.state_dict(), "Adam": optimizer.state_dict(), "RNG": ckpt.capture_rng("mps")}
    expected = {"model": state["model"], "Adam": state["optimizer"], "RNG": state["rng"]}
    equality = {key: runner.fingerprint(actual[key]) == runner.fingerprint(expected[key]) for key in actual}
    details = {key: runner.mismatch_paths(actual[key], expected[key]) for key in actual}
    assert all(equality.values()), {"matched": equality, "mismatch_paths": details}
    assert before == (digest(PARENT), digest(sidecar)), "Parent checkpoint or metadata changed"
    print("actual accepted D2 parent model/Adam/MPS RNG restore passed; no environment or optimizer step")


if __name__ == "__main__":
    main()
