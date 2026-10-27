"""Risk-directed immutable checkpoint and curriculum lineage tests."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import random
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from dodge_rl import checkpoints as c
from dodge_rl.dev_eval import development_seeds, summarize
from dodge_rl.identity import default_config, identity_hash

torch.set_num_threads(4)


def simple_identity(config=None):
    config = default_config("pilot") if config is None else config
    return {"config": config, "config_sha256": identity_hash(config),
            "sources": {"source.py": "unchanged"}, "runtime": {"device": config["device"]},
            "architecture": {"tokens": 81, "width": 128}, "gate": "fixed"}


def eval_result(score, alive, stage="D1"):
    cap = 2000 if stage == "D1" else 18000
    rows = []
    for i, seed in enumerate(development_seeds()):
        terminated = alive < cap
        rows.append({"episode_index": i, "seed": seed, "score_raw_fixed": int(score * 65536),
                     "score": score, "alive_frames": alive, "gameplay_frames": alive + int(terminated),
                     "terminated": terminated, "truncated": not terminated,
                     "objective_return": score + alive / 100 - 5 * terminated})
    return summarize(rows, stage, .1)


def learner():
    model = torch.nn.Linear(2, 1)
    return model, torch.optim.Adam(model.parameters(), lr=.003)


def checkpoint(path, *, tag="candidate", identity=None):
    model, optimizer = learner()
    state = c.make_state(model, optimizer, simple_identity() if identity is None else identity,
                         {"updates": 1}, tag=tag)
    digest = c.save_checkpoint(path, state)
    return state, digest


def certificate(path, digest, *, passed=True, after_score=2):
    proof = {"checkpoint_sha256": digest, "phase": "pilot", "complete": True, "passed": passed,
             "before": eval_result(.5, 500), "evaluations": {"D1": eval_result(after_score, 700)},
             "actor_gradient_seen": True, "critic_gradient_seen": True, "completed_training_updates": 1}
    c.evaluation_path(path).write_text(json.dumps(proof))
    return proof


def test_atomic_publish_never_overwrites(tmp_path):
    path = tmp_path / "state.pt"
    checkpoint(path)
    original = path.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        checkpoint(path)
    assert path.read_bytes() == original


def test_failed_temporary_write_does_not_publish_or_damage_existing(tmp_path, monkeypatch):
    old = tmp_path / "old.pt"
    checkpoint(old)
    original = old.read_bytes()
    def interrupted(_state, stream):
        stream.write(b"incomplete")
        raise OSError("synthetic interrupted save")
    monkeypatch.setattr(c.torch, "save", interrupted)
    with pytest.raises(OSError, match="synthetic"):
        c.save_checkpoint(tmp_path / "new.pt", {})
    assert old.read_bytes() == original
    assert not (tmp_path / "new.pt").exists()
    partials=list(tmp_path.glob("*.partial"))
    assert len(partials)==1 and partials[0].read_bytes()==b"incomplete"


def test_atomic_publish_collision_after_precheck_refuses_overwrite(tmp_path, monkeypatch):
    real_link = c.os.link
    path = tmp_path / "state.pt"
    def race(source, target):
        Path(target).write_bytes(b"another owner")
        return real_link(source, target)
    monkeypatch.setattr(c.os, "link", race)
    with pytest.raises(FileExistsError):
        checkpoint(path)
    assert path.read_bytes() == b"another owner"


@pytest.mark.parametrize("change", ["source", "untracked", "binary", "device", "config"])
def test_same_run_identity_changes_rejected(tmp_path, change):
    path = tmp_path / "state.pt"
    original = simple_identity()
    checkpoint(path, identity=original)
    other = copy.deepcopy(original)
    if change == "source": other["sources"]["source.py"] = "one-byte-change"
    if change == "untracked": other["sources"]["new.py"] = "new"
    if change == "binary": other["sources"]["_native.so"] = "changed"
    if change == "device": other["runtime"]["device"] = "mps"
    if change == "config": other["config"]["ppo"]["gamma"] = .9
    with pytest.raises(ValueError, match="identity mismatch"):
        c.load_checkpoint(path, other)


def test_checkpoint_file_and_embedded_identity_hashes_checked(tmp_path):
    path = tmp_path / "state.pt"
    state, digest = checkpoint(path)
    assert c.load_checkpoint(path, expected_sha256=digest)["tag"] == "candidate"
    with pytest.raises(ValueError, match="file hash"):
        c.load_checkpoint(path, expected_sha256="0" * 64)
    state["identity"]["sources"]["source.py"] = "tampered"
    c.save_checkpoint(tmp_path / "bad.pt", state)
    with pytest.raises(ValueError, match="identity hash"):
        c.load_checkpoint(tmp_path / "bad.pt")


def test_actual_rng_optimizer_roundtrip_gives_identical_next_update(tmp_path):
    torch.manual_seed(112)
    np.random.seed(113)
    random.seed(114)
    model, optimizer = learner()
    data = torch.tensor([[1., 2.], [3., 4.]])
    optimizer.zero_grad(); model(data).square().mean().backward(); optimizer.step()
    state = c.make_state(model, optimizer, simple_identity(), {"updates": 1})
    path = tmp_path / "state.pt"; c.save_checkpoint(path, state)
    expected_draws = (torch.randn(2, 2), np.random.rand(), random.random())
    optimizer.zero_grad(); model(expected_draws[0]).square().mean().backward(); optimizer.step()
    expected_weights = copy.deepcopy(model.state_dict())
    expected_optimizer = copy.deepcopy(optimizer.state_dict())
    restored, restored_optimizer = learner()
    c.restore_learner(c.load_checkpoint(path, simple_identity()), restored, restored_optimizer)
    actual_draws = (torch.randn(2, 2), np.random.rand(), random.random())
    assert torch.equal(expected_draws[0], actual_draws[0])
    assert expected_draws[1:] == actual_draws[1:]
    restored_optimizer.zero_grad(); restored(actual_draws[0]).square().mean().backward(); restored_optimizer.step()
    for name, value in expected_weights.items(): assert torch.equal(value, restored.state_dict()[name])
    for key, value in expected_optimizer["state"].items():
        for field, tensor in value.items(): assert torch.equal(tensor, restored_optimizer.state_dict()["state"][key][field])


def test_resume_skips_current_episode_and_records_abandonment():
    infos = [{"seed": {"slot": i, "episode": k, "actual_seed": 100+i},
              "gameplay_frames": 9, "score_raw_fixed": 0, "terminated": False, "truncated": False}
             for i, k in enumerate([7, 12])]
    env = SimpleNamespace(episode_info=lambda: infos,
                          batch_info=lambda: {"next_episode_indices": [8, 13]})
    indices, abandoned = c.episode_resume_state(env, 2)
    assert indices == [8, 13]
    assert [row["seed"]["episode"] for row in abandoned] == [7, 12]
    assert all(row["kind"] == "abandoned_on_fresh_env_resume" for row in abandoned)


@pytest.mark.parametrize("indices,batch", [([7,13],2),([None,13],2),([8],2),([8,13],3)])
def test_bad_resume_counters_or_batch_rejected(indices, batch):
    env = SimpleNamespace(episode_info=lambda: [{"seed":{"episode":7}}, {"seed":{"episode":12}}],
                          batch_info=lambda: {"next_episode_indices": indices})
    with pytest.raises(ValueError): c.episode_resume_state(env, batch)


def test_registered_transition_preserves_parent_bytes_and_rng_state(tmp_path):
    path = tmp_path / "pilot.pt"
    parent, digest = checkpoint(path)
    certificate(path, digest)
    original = path.read_bytes()
    target = simple_identity(default_config("D1", parent_sha256=digest))
    loaded, proof = c.validate_transition(path, target)
    assert proof["passed"] and loaded["identity"]["config"]["phase"] == "pilot"
    assert path.read_bytes() == original
    assert torch.equal(loaded["rng"]["torch_cpu"], parent["rng"]["torch_cpu"])


@pytest.mark.parametrize("field", ["lr", "K", "reward", "source", "device", "budget"])
def test_transition_does_not_permit_unregistered_changes(tmp_path, field):
    path = tmp_path / "pilot.pt"; _, digest = checkpoint(path); certificate(path, digest)
    target = simple_identity(default_config("D1", parent_sha256=digest))
    if field == "lr": target["config"]["ppo"]["learning_rate"] = .01
    if field == "K": target["config"]["action_repeat"] = 2
    if field == "reward": target["config"]["ppo"]["reward_scale"] = 1
    if field == "source": target["sources"]["source.py"] = "modified"
    if field == "device": target["runtime"]["device"] = "mps"
    if field == "budget": target["config"]["phase_settings"]["budget_seconds"] = 1801
    with pytest.raises(ValueError): c.validate_transition(path, target)


@pytest.mark.parametrize("tag", sorted(c.REJECTED_PARENT_TAGS))
def test_interrupted_failed_timeout_probe_parent_refused(tmp_path, tag):
    path = tmp_path / "parent.pt"; _, digest = checkpoint(path, tag=tag); certificate(path, digest)
    with pytest.raises(ValueError, match="cannot advance"):
        c.validate_transition(path, simple_identity(default_config("D1", parent_sha256=digest)))


def test_claimed_pilot_pass_without_score_improvement_is_rejected(tmp_path):
    path = tmp_path / "pilot.pt"; _, digest = checkpoint(path); certificate(path, digest, after_score=.5)
    with pytest.raises(ValueError, match="improvement"):
        c.validate_transition(path, simple_identity(default_config("D1", parent_sha256=digest)))


def test_mid_update_progress_is_retained_and_cannot_advance(tmp_path):
    path = tmp_path / "partial.pt"
    model, optimizer = learner()
    progress = {"in_update": True, "complete": False, "epoch": 1, "minibatch": 2, "optimizer_steps": 7}
    state = c.make_state(model, optimizer, simple_identity(), {"updates": 1},
                         tag="interrupted_mid_update", progress=progress)
    digest = c.save_checkpoint(path, state)
    assert c.load_checkpoint(path)["update_progress"] == progress
    certificate(path, digest)
    with pytest.raises(ValueError):
        c.validate_transition(path, simple_identity(default_config("D1", parent_sha256=digest)))
