import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import torch

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[3]
RUNTIME = ROOT / "learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(RUNTIME))

import paired_eval as pe
import supervisor
import worker


class FakeModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.anchor = torch.nn.Parameter(torch.zeros(()), requires_grad=False)

    def forward(self, global_feats, entity_feats, entity_types, entity_mask):
        return type("Output", (), {"logits": torch.zeros((global_feats.shape[0], 9), device=global_feats.device)})()


class FakeEnv:
    made = []

    def __init__(self, *, seed, stage, **config):
        self.seed = seed
        self.config = config
        self.calls = 0
        self.closed = False
        self.made.append(self)

    def episode_info(self):
        return [{"seed": {"evaluation": True, "actual_seed": self.seed}, "startup_frames": 13}]

    def observations(self):
        return {"global_feats": np.zeros((1, 1, 14), dtype=np.float32),
                "entity_feats": np.zeros((1, 80, 16), dtype=np.float32),
                "entity_types": np.zeros((1, 80), dtype=np.int64),
                "entity_mask": np.zeros((1, 80), dtype=np.bool_)}

    def step(self, actions):
        self.calls += 1
        info = {"seed": {"actual_seed": self.seed}, "bootstrap": True,
                "score_raw_fixed": 0, "score_delta_sum_raw_fixed": 0,
                "score": 0.0, "alive_frames": 4, "gameplay_frames": 4,
                "objective_return": 0.04, "death_cause": None,
                "fatal_gameplay_frame": None, "death_observed_lethal_contacts": None}
        return {"info": [info], "terminated": np.array([False]), "truncated": np.array([True]),
                "observations": None}

    def close(self):
        self.closed = True


def fake_config(seed, stage):
    if stage != "D2":
        raise AssertionError(stage)
    return {"seed": seed, "stage": stage, "batch_size": 1, "action_repeat": 4,
            "difficulty": 2, "patterns_enabled": True, "powerups_enabled": True,
            "raw_frame_cap": 18000, "render_pixels": False, "auxiliary_targets": False,
            "num_threads": 1, "chunk_size": 1,
            "seeds_by_slot": [[seed]],
            "excluded_seed_ranges": [(2952790016, 2952791015), (3489660928, 3489661055),
                                     (3758096384, 3758097383)]}


def fake_rows():
    rows = []
    for item in pe.episode_schedule():
        for index, seed in enumerate(pe.SEEDS):
            rows.append({"checkpoint": item["checkpoint"], "mode": item["mode"],
                         "replicate_seed": item["replicate_seed"], "episode_index": index,
                         "seed": seed, "score_raw_fixed": 0, "score": 0.0,
                         "alive_frames": float(index), "gameplay_frames": index,
                         "terminated": True, "truncated": False, "objective_return": 0.0,
                         "death_cause": "normal_enemy", "fatal_gameplay_frame": index,
                         "death_observed_lethal_contacts": {"normal_enemy": 1}})
    return rows


class PairedEvalTests(unittest.TestCase):
    def test_schedule_has_exact_512_and_argmax_first_for_both_checkpoints(self):
        schedule = pe.episode_schedule()
        self.assertEqual(pe.episode_count(schedule), 512)
        self.assertEqual([(x["checkpoint"], x["mode"]) for x in schedule[:2]],
                         [("best180", "argmax"), ("latest252", "argmax")])
        self.assertTrue(all(x["mode"] == "sampled" for x in schedule[2:]))
        rows = fake_rows()
        summary = pe.summarize_all(rows)
        self.assertEqual(summary["episode_count"], 512)
        self.assertEqual(summary["censored_episode_count"], 0)
        self.assertEqual(summary["paired_contrasts"]["primary_contrast"], "C4_interaction")

    def test_argmax_control_compares_whole_canonical_row_and_fails_closed(self):
        row = {"episode_index": 0, "seed": pe.SEEDS[0], "score_raw_fixed": 0, "score": 0.0,
               "alive_frames": 4, "gameplay_frames": 4, "terminated": False, "truncated": True,
               "objective_return": 0.04, "death_cause": None, "fatal_gameplay_frame": None,
               "death_observed_lethal_contacts": None}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "control.jsonl"
            expected = [dict(row, episode_index=i, seed=seed) for i, seed in enumerate(pe.SEEDS)]
            path.write_text("".join(json.dumps(value) + "\n" for value in expected))
            pe.compare_control(expected, path)
            changed = [dict(value) for value in expected]
            changed[0]["death_observed_lethal_contacts"] = {"normal_enemy": 1}
            with self.assertRaisesRegex(ValueError, "mismatch"):
                pe.compare_control(changed, path)

    def test_fake_env_evaluator_uses_d2_helpers_and_no_real_games(self):
        FakeEnv.made = []
        expected = []
        for index, seed in enumerate(pe.SEEDS):
            expected.append({"episode_index": index, "seed": seed, "score_raw_fixed": 0,
                             "score": 0.0, "alive_frames": 4, "gameplay_frames": 4,
                             "terminated": False, "truncated": True, "objective_return": 0.04,
                             "death_cause": None, "fatal_gameplay_frame": None,
                             "death_observed_lethal_contacts": None})
        with tempfile.TemporaryDirectory() as directory:
            control = Path(directory) / "expected.jsonl"
            control.write_text("".join(json.dumps(row) + "\n" for row in expected))
            rows = worker.evaluate(FakeModel(), checkpoint="best180", mode="argmax",
                                   replicate_seed=None, env_factory=FakeEnv,
                                   config_factory=fake_config, expected_control_path=control)
        self.assertEqual(len(rows), 64)
        self.assertEqual([env.calls for env in FakeEnv.made], [1] * 64)
        self.assertTrue(all(env.closed for env in FakeEnv.made))
        self.assertEqual(rows[0]["checkpoint"], "best180")

    def test_private_rng_is_independent_of_removal_order_and_common_across_checkpoints(self):
        seeds = list(pe.SEEDS[:8])
        def sequence(seed, replicate=64001):
            stream = pe.UniformStream(replicate, seed)
            return [stream.next() for _ in range(3)]
        original = {seed: sequence(seed) for seed in seeds}
        reordered = {}
        for seed in reversed(seeds[1:]):
            reordered[seed] = sequence(seed)
        self.assertEqual({seed: original[seed] for seed in reordered}, reordered)
        self.assertEqual(original[seeds[0]], sequence(seeds[0]))
        self.assertNotEqual(original[seeds[0]], sequence(seeds[0], 64002))

    def test_inverse_cdf_float64_normalization_zeroes_and_exact_boundaries(self):
        self.assertEqual(pe.inverse_cdf([0.25, 0.0, 0.75], 0.0), 0)
        self.assertEqual(pe.inverse_cdf([0.25, 0.0, 0.75], 0.25), 2)
        self.assertEqual(pe.inverse_cdf([0.0, 0.5, 0.5], 0.999999999999), 2)
        with self.assertRaisesRegex(ValueError, "sum to zero"):
            pe.inverse_cdf([0.0, 0.0], 0.5)

    def test_canonical_tails_are_bottom_top_sixteen_means_not_percentiles(self):
        value = pe._tail_means(range(64))
        self.assertEqual(value, {"bottom16_mean": 7.5, "top16_mean": 55.5, "all64_mean": 31.5})
        self.assertNotEqual(value["bottom16_mean"], float(np.quantile(np.arange(64), 0.25)))

    def test_checkpoint_receipt_and_terminal_status_substitution_rejected(self):
        best = worker.EXPECTED_RECEIPT_DETAILS["best180"]
        self.assertNotEqual(best["checkpoint_sha256"], worker.EXPECTED_RECEIPT_DETAILS["latest252"]["checkpoint_sha256"])
        self.assertEqual(supervisor.terminal_status(worker_status="complete", raw_exit=0,
                         child_reaped=True, group_absent=True, guard_ok=True, publication_ok=True),
                         "complete_pending_parent_acceptance")
        for kwargs in ({"raw_exit": 1}, {"child_reaped": False}, {"group_absent": False},
                       {"guard_ok": False}, {"publication_ok": False}):
            baseline = {"worker_status": "complete", "raw_exit": 0, "child_reaped": True,
                        "group_absent": True, "guard_ok": True, "publication_ok": True}
            baseline.update(kwargs)
            self.assertNotEqual(supervisor.terminal_status(**baseline), "complete_pending_parent_acceptance")

    def test_both_pinned_v3_checkpoints_load_strictly_and_receipt_substitution_fails(self):
        from dodge_rl import checkpoints
        from dodge_rl.models.teacher import OmniscientEntityTeacher
        for label in pe.CHECKPOINTS:
            checkpoint_path, checkpoint_hash = worker.EXPECTED_INPUTS[f"{label}_checkpoint"]
            receipt_path, _ = worker.EXPECTED_INPUTS[f"{label}_receipt"]
            state = checkpoints.load_checkpoint(ROOT / checkpoint_path, expected_sha256=checkpoint_hash)
            checkpoints.require_complete_update(state)
            receipt = json.loads((ROOT / receipt_path).read_text())
            worker.validate_checkpoint_receipt_binding(state, receipt, label, checkpoints.identity_hash)
            with torch.random.fork_rng(devices=[]):
                model = OmniscientEntityTeacher()
            model.load_state_dict(state["model"], strict=True)
            model.requires_grad_(False)
            self.assertFalse(any(parameter.requires_grad for parameter in model.parameters()))
            self.assertEqual(sum(parameter.numel() for parameter in model.parameters()), 321290)
            substituted = dict(receipt)
            substituted["checkpoint_sha256"] = worker.EXPECTED_INPUTS[
                "latest252_checkpoint" if label == "best180" else "best180_checkpoint"][1]
            with self.assertRaisesRegex(ValueError, "Checkpoint/terminal receipt binding differs"):
                worker.validate_checkpoint_receipt_binding(state, substituted, label, checkpoints.identity_hash)

    def test_cancellation_and_postpublication_guard_failures_reject_success_status(self):
        self.assertEqual(supervisor.terminal_status(worker_status="complete", raw_exit=0,
                         child_reaped=True, group_absent=True, guard_ok=False, publication_ok=True),
                         "failed_postflight_or_publication")
        self.assertEqual(supervisor.terminal_status(worker_status="complete", raw_exit=0,
                         child_reaped=True, group_absent=True, guard_ok=True, publication_ok=False),
                         "failed_postflight_or_publication")


if __name__ == "__main__":
    unittest.main()
