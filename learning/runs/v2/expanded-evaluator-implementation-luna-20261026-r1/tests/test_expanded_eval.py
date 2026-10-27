import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

MODULE_PATH = Path(__file__).resolve().parents[1] / "expanded_eval.py"
OWN_DIRECTORY = MODULE_PATH.parent
SPEC = importlib.util.spec_from_file_location("expanded_eval_test", MODULE_PATH)
expanded_eval = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(expanded_eval)


def synthetic_rows(seeds, cap=18000):
    rows = []
    for index, seed in enumerate(seeds):
        truncated = index % 4 == 3
        alive = cap if truncated else 40 + index
        gameplay = cap if truncated else alive + 1
        cause = None if truncated else "unknown" if index % 4 == 2 else "normal_enemy"
        contacts = None if truncated else {name: (1 if name == cause else 0)
            for name in expanded_eval.DEATH_CAUSES[:-1]}
        rows.append({"episode_index": index, "seed": seed, "score_raw_fixed": index * 65536,
            "score_delta_sum_raw_fixed": index * 65536, "score": float(index),
            "alive_frames": alive, "gameplay_frames": gameplay, "startup_frames": 13,
            "objective_return": float(index) + alive / 100 - 5 * (not truncated),
            "terminated": not truncated, "truncated": truncated, "death_cause": cause,
            "fatal_gameplay_frame": gameplay if not truncated else None,
            "death_observed_lethal_contacts": contacts})
    return rows


class FakeEnv:
    def __init__(self, seed, tracker):
        self.seed = seed
        self.tracker = tracker
        self.steps = 0
        tracker["constructed"].append(seed)

    def episode_info(self):
        return [{"seed": {"evaluation": True, "actual_seed": self.seed},
                 "startup_frames": 13, "gameplay_frames": 0}]

    def observations(self):
        return {"global_feats": np.zeros((1, 1), dtype=np.float32)}

    def step(self, action):
        self.steps += 1
        done = self.steps == 2
        truncated = done and self.seed % 4 == 3
        terminated = done and not truncated
        alive = 18000 if truncated else 40 + (self.seed % 31) if done else 10
        gameplay = 18000 if truncated else alive + 1 if done else alive
        cause = None if truncated or not done else "normal_enemy"
        info = {"seed": {"actual_seed": self.seed}, "bootstrap": not terminated,
            "score_raw_fixed": 65536, "score_delta_sum_raw_fixed": 65536,
            "alive_frames": alive, "gameplay_frames": gameplay, "startup_frames": 13,
            "objective_return": 1 + alive / 100 - 5 * terminated,
            "death_cause": cause, "fatal_gameplay_frame": gameplay if terminated else None,
            "death_observed_lethal_contacts": ({name: (1 if name == cause else 0)
              for name in expanded_eval.DEATH_CAUSES[:-1]} if terminated else None)}
        return {"info": [info], "terminated": np.array([terminated]), "truncated": np.array([truncated]),
                "observations": self.observations()}


class FakePolicy:
    _expanded_eval_device = "cpu"

    def __call__(self, feats):
        logits = torch.zeros((feats.shape[0], 9), dtype=torch.float32)
        logits[:, 2] = 1.0
        return type("Output", (), {"logits": logits})()


class ExpandedEvalTests(unittest.TestCase):
    def test_arbitrary_positive_divisible_by_four_rows_and_performance_order(self):
        seeds = list(range(0xD1001000, 0xD1001008))
        rows = expanded_eval._validate_rows(synthetic_rows(seeds), seeds)
        result = expanded_eval._summarize(rows, seeds, 0.0, "a" * 64, 180, "ranking", "b" * 64)
        perf = result["performance"]
        self.assertEqual(list(perf), ["worst", "q1_bottom_quarter_mean", "mean",
                                      "q4_top_quarter_mean", "best"])
        self.assertEqual(perf["worst"], 40)
        self.assertEqual(perf["best"], 18000)
        self.assertEqual(result["episodes"], 8)

    def test_fake_cpu_policy_environment_handles_chunk_remainder_without_filler(self):
        seeds = list(range(0xD1002000, 0xD100200c))
        tracker = {"constructed": []}
        guards = []

        def env_factory(**kwargs):
            seed = kwargs["seeds_by_slot"][0][0]
            self.assertEqual(kwargs["batch_size"], 1)
            self.assertEqual(kwargs["difficulty"], 2)
            self.assertEqual(kwargs["raw_frame_cap"], 18000)
            return FakeEnv(seed, tracker)

        rows = expanded_eval._production_rows(FakePolicy(), env_factory, ("global_feats",),
            lambda info, terminated, truncated: {"death_cause": info["death_cause"],
                "fatal_gameplay_frame": info["fatal_gameplay_frame"],
                "death_observed_lethal_contacts": info["death_observed_lethal_contacts"]},
            seeds, [], lambda: guards.append(1), batch_size=5)
        expanded_eval._validate_rows(rows, seeds)
        self.assertEqual([row["seed"] for row in rows], seeds)
        self.assertEqual(tracker["constructed"], seeds)
        self.assertEqual(sum(row["truncated"] for row in rows), 3)
        self.assertEqual(len(guards), 3 * len(seeds) + 4 * 3)

    def test_frame_death_and_score_conservation_reject_mutations(self):
        seeds = list(range(0xD1003000, 0xD1003008))
        valid = synthetic_rows(seeds)
        expanded_eval._validate_rows(valid, seeds)
        variants = []
        bad = json.loads(json.dumps(valid)); bad[0]["alive_frames"] += 1; variants.append(bad)
        bad = json.loads(json.dumps(valid)); bad[0]["score_delta_sum_raw_fixed"] += 1; variants.append(bad)
        bad = json.loads(json.dumps(valid)); bad[0]["death_observed_lethal_contacts"]["normal_enemy"] = 0; variants.append(bad)
        bad = json.loads(json.dumps(valid)); bad[-1]["gameplay_frames"] -= 1; variants.append(bad)
        for rows in variants:
            with self.assertRaises(expanded_eval.ValidationError):
                expanded_eval._validate_rows(rows, seeds)

    def test_rows_reject_reordering_duplicate_and_remainder(self):
        seeds = list(range(0xD1004000, 0xD1004008))
        rows = synthetic_rows(seeds)
        for mutated in (list(reversed(rows)), [rows[0]] + rows[:-1]):
            with self.assertRaises(expanded_eval.ValidationError):
                expanded_eval._validate_rows(mutated, seeds)
        with self.assertRaises(expanded_eval.ValidationError):
            expanded_eval._validate_rows(rows[:-1], seeds)

    def test_seed_vectors_reject_duplicates_reorder_overlap_and_invalid_counts(self):
        good = {"seeds": list(range(0xD1005000, 0xD1005008))}
        expanded_eval._validate_seed_vector("ranking", good, good["seeds"])
        bad_vectors = [good["seeds"][:-1], [good["seeds"][0], good["seeds"][2], good["seeds"][1], *good["seeds"][3:]],
                       [good["seeds"][0], good["seeds"][0], *good["seeds"][2:]],
                       list(range(0xD0000020, 0xD0000028)),
                       list(range(0xD0000078, 0xD0000080)),
                       list(range(0xB0000100, 0xB0000108)),
                       list(range(0xE0000100, 0xE0000108))]
        for seeds in bad_vectors:
            with self.assertRaises(expanded_eval.ValidationError):
                expanded_eval._validate_seed_vector("ranking", {"seeds": seeds}, seeds)

    def test_benchmark_is_exact_frozen_dev64_seed_vector(self):
        seeds = list(range(0xD0000000, 0xD0000040))
        expanded_eval._validate_seed_vector("benchmark_dev64", {"seeds": seeds}, seeds)
        with self.assertRaises(expanded_eval.ValidationError):
            expanded_eval._validate_seed_vector("benchmark_dev64", {"seeds": seeds[1:] + [seeds[-1] + 1]},
                                                seeds[1:] + [seeds[-1] + 1])

    def test_output_is_exclusive_and_prior_bytes_survive_collision(self):
        with tempfile.TemporaryDirectory(dir=OWN_DIRECTORY) as directory:
            path = Path(directory) / "result.json"
            initial = {"complete": True, "rows": []}
            digest = expanded_eval._write_exclusive(path, initial)
            before = path.read_bytes()
            self.assertEqual(hashlib.sha256(before).hexdigest(), digest)
            with self.assertRaises(FileExistsError):
                expanded_eval._write_exclusive(path, {"complete": False})
            self.assertEqual(path.read_bytes(), before)

    def test_accepted_348_certificate_rows_are_the_golden_benchmark(self):
        rows = [json.loads(line) for line in expanded_eval.INCUMBENT_GOLDEN_ROWS.read_text().splitlines() if line]
        expanded_eval._verify_incumbent_golden_rows(rows)
        corrupted = [dict(row) for row in rows]
        corrupted[0]["alive_frames"] += 1
        with self.assertRaises(expanded_eval.ValidationError):
            expanded_eval._verify_incumbent_golden_rows(corrupted)

    def test_bad_registration_pin_fails_before_guard(self):
        calls = []
        with tempfile.TemporaryDirectory(dir=OWN_DIRECTORY) as directory:
            path = Path(directory) / "registration.json"
            raw = b'{"schema":"wrong"}'
            path.write_bytes(raw)
            with self.assertRaises(expanded_eval.ValidationError):
                expanded_eval.evaluate_registered(registration_path=str(path), registration_sha256=hashlib.sha256(raw).hexdigest(),
                    candidate_update=180, cohort_name="ranking", output_path=str(Path(directory) / "out.json"),
                    check_guard=lambda: calls.append("guard"))
        self.assertEqual(calls, [])

    def test_wrong_registration_hash_fails_before_guard(self):
        calls = []
        with tempfile.TemporaryDirectory(dir=OWN_DIRECTORY) as directory:
            path = Path(directory) / "registration.json"
            path.write_text("{}")
            with self.assertRaises(expanded_eval.ValidationError):
                expanded_eval.evaluate_registered(registration_path=str(path), registration_sha256="0" * 64,
                    candidate_update=180, cohort_name="ranking", output_path=str(Path(directory) / "out.json"),
                    check_guard=lambda: calls.append("guard"))
        self.assertEqual(calls, [])

    def test_bad_candidate_and_cohort_names_fail_before_file_access(self):
        for candidate, cohort in ((181, "ranking"), (180, "B_E")):
            with self.assertRaises(expanded_eval.ValidationError):
                expanded_eval._validate_static("/missing/registration", "0" * 64, candidate, cohort, "/missing/out")


if __name__ == "__main__":
    unittest.main()
