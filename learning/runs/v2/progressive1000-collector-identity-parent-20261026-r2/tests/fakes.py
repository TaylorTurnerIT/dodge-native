"""Tiny synthetic fixtures only. No native/model/checkpoint imports or study seeds."""
import copy
from types import SimpleNamespace

import numpy as np
import torch
from torch import nn

from successor.curriculum import HISTORICAL_RANGES


def info(slot, episode=0, frame=0, *, terminated=False, truncated=False):
    alive = frame - int(terminated)
    return {"seed": {"slot": slot, "episode": episode, "counter": 0,
                     "actual_seed": 100 + slot + 64 * episode, "evaluation": False},
        "startup_frames": 13, "gameplay_frames": frame, "alive_frames": alive,
        "score_raw_fixed": 0, "score": 0.0, "score_delta_sum_raw_fixed": 0,
        "objective_return": alive / 100 - 5 * terminated,
        "terminated": terminated, "truncated": truncated, "bootstrap": not terminated,
        "death_cause": "synthetic" if terminated else None,
        "fatal_gameplay_frame": frame if terminated else None,
        "death_observed_lethal_contacts": {"synthetic": 1} if terminated else None,
        "diagnostics": {"raw_history_samples": frame + 1}}


class FakeEnv:
    """Owned-return fake; native API tests here establish fixture behavior only."""
    def __init__(self, count=4, deaths=None):
        self.infos = [info(slot) for slot in range(count)]
        self.deaths = deaths or {}
        self.cutoffs, self.resets, self.actions = [], [], []
        self.corruption = None
        self.step_calls = 0

    def batch_info(self):
        return {"batch_size": len(self.infos), "action_repeat": 4,
                "raw_frame_cap": 18000, "seed_mode": {"mode": "training"},
                "effective_excluded_seed_ranges": list(HISTORICAL_RANGES)}

    def episode_info(self):
        return copy.deepcopy(self.infos)

    def observations(self):
        n = len(self.infos)
        result = {"global_feats": np.zeros((n, 1, 14), np.float32),
            "entity_feats": np.zeros((n, 80, 16), np.float32),
            "entity_types": np.zeros((n, 80), np.int64),
            "entity_mask": np.ones((n, 80), np.bool_)}
        for slot, row in enumerate(self.infos):
            # Distinct final and reset tags expose bootstrap leakage.
            result["global_feats"][slot, 0, 0] = row["gameplay_frames"] / 1000 + 10 * row["seed"]["episode"]
            result["global_feats"][slot, 0, 1] = row["diagnostics"]["raw_history_samples"]
        return result

    def step(self, actions):
        self.step_calls += 1
        self.actions.append(np.asarray(actions).copy())
        elapsed, alive = [], []
        for slot, old in enumerate(self.infos):
            assert not old["terminated"] and not old["truncated"]
            frame = old["gameplay_frames"] + 4
            death_frame = self.deaths.get((slot, old["seed"]["episode"]))
            death = death_frame is not None and old["gameplay_frames"] < death_frame <= frame
            if death:
                frame = death_frame
            dt = frame - old["gameplay_frames"]
            elapsed.append(dt)
            alive.append(dt - death)
            self.infos[slot] = info(slot, old["seed"]["episode"], frame,
                                    terminated=death, truncated=frame == 18000 and not death)
        result = {"observations": self.observations(), "info": self.episode_info(),
            "elapsed_raw_frames": np.array(elapsed, np.int64),
            "alive_raw_frames": np.array(alive, np.int64),
            "score_delta_raw_fixed": np.zeros(len(self.infos), np.int64),
            "terminated": np.array([row["terminated"] for row in self.infos], np.bool_),
            "truncated": np.array([row["truncated"] for row in self.infos], np.bool_)}
        result["rewards"] = (result["alive_raw_frames"] / 100 - 5 * result["terminated"]).astype(np.float32)
        self.last_result = result
        return result

    def truncate_practice(self, indices, horizons):
        assert len(indices) == len(horizons) and len(indices) == len(set(indices))
        for slot, horizon in zip(indices, horizons):
            assert type(slot) is int and 0 <= slot < len(self.infos)
            assert type(horizon) is int and 0 < horizon < 18000 and horizon % 1000 == 0
            row = self.infos[slot]
            assert not row["terminated"] and not row["truncated"]
            assert row["gameplay_frames"] == horizon and horizon % 4 == 0
        self.cutoffs.append((list(indices), list(horizons)))
        for slot in indices:
            self.infos[slot]["truncated"] = True
        if self.corruption == "reward":
            self.infos[indices[0]]["objective_return"] += 1
        elif self.corruption == "other_slot":
            self.infos[(indices[0] + 1) % len(self.infos)]["seed"]["counter"] += 1
        elif self.corruption == "history":
            self.infos[indices[0]]["diagnostics"]["raw_history_samples"] += 1
        elif self.corruption == "step_payload":
            self.last_result["rewards"][0] += 1
        rows = [copy.deepcopy(self.infos[slot]) for slot in indices]
        if self.corruption == "order":
            rows.reverse()
        if self.corruption == "short":
            rows.pop()
        return rows

    def reset_done(self, indices):
        assert indices == sorted(set(indices))
        assert all(self.infos[slot]["terminated"] or self.infos[slot]["truncated"] for slot in indices)
        self.resets.append(list(indices))
        for slot in indices:
            self.infos[slot] = info(slot, self.infos[slot]["seed"]["episode"] + 1)
        return {"observations": self.observations(),
                "info": [copy.deepcopy(self.infos[slot]) for slot in indices]}


class TinyNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.actor_head = nn.Linear(1, 9)
        self.critic_head = nn.Linear(1, 1)
        with torch.no_grad():
            self.actor_head.weight.zero_()
            self.actor_head.bias.zero_()
            self.critic_head.weight.fill_(1)
            self.critic_head.bias.zero_()

    def forward(self, global_feats, entity_feats, entity_types, entity_mask):
        value = global_feats[:, 0, :1]
        return SimpleNamespace(logits=self.actor_head(value), values=self.critic_head(value).squeeze(-1))
