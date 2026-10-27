"""Death-cause telemetry in development rows.

Fake-environment tests cover dev_eval from source. The final test exercises
whichever extension binary is currently importable and skips when it predates
the source change; it never builds or installs an extension.
"""
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from dodge_rl import dev_eval as d
from dodge_rl.dev_eval import DEATH_CAUSES, death_fields
from dodge_rl.identity import OBSERVATION_KEYS

CONTACTS = {name: 0 for name in DEATH_CAUSES}


class Policy(torch.nn.Module):
    def forward(self, g, e, types, mask):
        return SimpleNamespace(logits=torch.zeros((len(g), 9)), values=torch.zeros(len(g)))


def make_env(telemetry="new", terminate=True):
    class Env:
        def __init__(self, **cfg):
            self.seed, self.calls = cfg["seeds_by_slot"][0][0], 0
            self.index = (self.seed - 0xD0000000) % 6

        def episode_info(self):
            return [{"seed": {"evaluation": True, "actual_seed": self.seed}, "startup_frames": 13}]

        def observations(self):
            return {"global_feats": np.zeros((1, 1, 14), np.float32),
                    "entity_feats": np.zeros((1, 80, 16), np.float32),
                    "entity_types": np.zeros((1, 80), np.int64),
                    "entity_mask": np.zeros((1, 80), bool)}

        def step(self, actions):
            self.calls += 1
            done = self.calls == 2
            dead = done and terminate
            alive = self.calls - int(dead)
            info = {"seed": {"actual_seed": self.seed}, "bootstrap": not dead,
                    "score_raw_fixed": 0, "score_delta_sum_raw_fixed": 0, "alive_frames": alive,
                    "gameplay_frames": self.calls, "objective_return": alive / 100 - 5 * dead}
            if telemetry == "new":
                cause = DEATH_CAUSES[self.index]
                contacts = dict(CONTACTS)
                contacts[cause] = 1
                info.update(death_cause=cause if dead else None,
                            fatal_gameplay_frame=self.calls if dead else None,
                            death_observed_lethal_contacts=contacts if dead else None)
            return {"info": [info], "terminated": np.array([dead]),
                    "truncated": np.array([done and not dead]), "observations": self.observations()}
    return Env


def test_rows_persist_first_cause_frame_and_contacts_for_every_cause():
    result = d.evaluate(Policy(), "D1", env_factory=make_env())
    rows = result["rows"]
    assert {row["death_cause"] for row in rows} == set(DEATH_CAUSES)
    for row in rows:
        assert row["fatal_gameplay_frame"] == row["gameplay_frames"] == 2
        assert row["death_observed_lethal_contacts"][row["death_cause"]] == 1
    assert sum(result["death_causes"].values()) == result["deaths"] == 64
    assert result["death_causes"]["unavailable"] == 0
    d.validate_summary(result)


def test_cap_truncated_rows_have_no_cause():
    result = d.evaluate(Policy(), "D1", env_factory=make_env(terminate=False))
    assert result["caps"] == 64 and result["deaths"] == 0
    assert all(row["death_cause"] is None and row["fatal_gameplay_frame"] is None
               and row["death_observed_lethal_contacts"] is None for row in result["rows"])
    assert sum(result["death_causes"].values()) == 0


def test_binary_without_telemetry_is_marked_unavailable_not_guessed():
    result = d.evaluate(Policy(), "D1", env_factory=make_env(telemetry="old"))
    assert {row["death_cause"] for row in result["rows"]} == {"unavailable"}
    assert result["death_causes"]["unavailable"] == 64
    assert all(row["fatal_gameplay_frame"] is None for row in result["rows"])


@pytest.mark.parametrize("patch", [
    {"death_cause": "mystery"},
    {"fatal_gameplay_frame": 1},
    {"death_cause": "normal_enemy", "death_observed_lethal_contacts": CONTACTS},
    {"death_observed_lethal_contacts": {"normal_enemy": 1}},
    {"death_observed_lethal_contacts": None},
])
def test_inconsistent_terminated_telemetry_is_rejected(patch):
    info = {"gameplay_frames": 2, "death_cause": "normal_enemy", "fatal_gameplay_frame": 2,
            "death_observed_lethal_contacts": {**CONTACTS, "normal_enemy": 1}, **patch}
    with pytest.raises(ValueError):
        death_fields(info, True, False)


def test_telemetry_on_live_or_truncated_episode_is_rejected():
    info = {"gameplay_frames": 5, "death_cause": "normal_enemy", "fatal_gameplay_frame": 5,
            "death_observed_lethal_contacts": CONTACTS}
    with pytest.raises(ValueError):
        death_fields(info, False, True)


def test_diagnostics_do_not_enter_policy_inputs():
    observations = make_env()(seeds_by_slot=[[d.development_seeds()[0]]]).observations()
    assert list(observations) == list(OBSERVATION_KEYS)
    assert observations["global_feats"].shape == (1, 1, 14)
    assert observations["entity_feats"].shape == (1, 80, 16)
    assert not any("death" in key for key in observations)


def test_summary_revalidates_persisted_contact_data_and_cause_totals():
    result = d.evaluate(Policy(), "D1", env_factory=make_env())
    result["death_causes"]["normal_enemy"] += 1
    with pytest.raises(ValueError, match="summary differs"):
        d.validate_summary(result)
    result["death_causes"]["normal_enemy"] -= 1
    result["rows"][0]["fatal_gameplay_frame"] += 1
    with pytest.raises(ValueError, match="telemetry differs"):
        d.validate_summary(result)


def test_legacy_rows_count_as_unavailable_without_rewriting_evidence():
    result = d.evaluate(Policy(), "D1", env_factory=make_env(telemetry="old"))
    for row in result["rows"]:
        for key in ("death_cause", "fatal_gameplay_frame", "death_observed_lethal_contacts"):
            row.pop(key)
    summary = d.summarize(result["rows"], "D1", result["elapsed_seconds"])
    assert summary["death_causes"]["unavailable"] == summary["deaths"] == 64
    assert not any("death_cause" in row for row in result["rows"])


def test_importable_binary_reports_consistent_telemetry_or_skips():
    from dodge_rl import VecDodgeEnv
    env = VecDodgeEnv(**d.development_environment_config(d.development_seeds()[0], "D1"))
    info = env.episode_info()[0]
    if "death_cause" not in info:
        pytest.skip("importable extension predates death telemetry source (no build performed)")
    assert info["death_cause"] is None and info["fatal_gameplay_frame"] is None
    assert info["death_observed_lethal_contacts"] is None
    observations = env.observations()
    assert not any("death" in key for key in observations)
