import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import paired_eval as pe


def rows():
    out = []
    for i, seed in enumerate(pe.SEEDS):
        died = i % 4 != 0
        cause = "normal_enemy" if died else None
        out.append({"episode_index": i, "seed": seed, "alive_frames": i * 10,
                    "gameplay_frames": i * 10, "score_raw_fixed": i * 65536,
                    "score": float(i), "terminated": died, "truncated": not died,
                    "death_cause": cause,
                    "fatal_gameplay_frame": i * 10 if died else None,
                    "death_observed_lethal_contacts": ({c: int(c == cause) for c in pe.DEATH_CAUSES} if died else None)})
    return out

class EvaluatorTests(unittest.TestCase):
    def test_manifest_and_metrics(self):
        m = pe.load_manifest()
        s = pe.summarize_arm(rows())
        self.assertEqual(m["seeds"], list(pe.SEEDS))
        self.assertEqual(s["bottom16_mean_Q1"], sum(range(16)) * 10 / 16)
        self.assertEqual(s["top16_mean_Q4"], sum(range(48, 64)) * 10 / 16)
        self.assertEqual(s["truncations"], 16)
        self.assertEqual(s["death_cause_counts"]["normal_enemy"], 48)

    def test_rejects_duplicate_missing_reordered_wrong_seed(self):
        base = rows()
        for bad in (base[:-1], [base[1], base[0], *base[2:]], [dict(x) for x in base]):
            if len(bad) == 64 and bad[0]["seed"] == base[0]["seed"]:
                bad[1]["seed"] = bad[0]["seed"]
            with self.subTest(length=len(bad)):
                with self.assertRaises(pe.ValidationError): pe.validate_rows(bad)
        bad = rows(); bad[0]["seed"] = 1
        with self.assertRaises(pe.ValidationError): pe.validate_rows(bad)

    def test_rejects_frame_score_and_boundary_errors(self):
        for field, value in (("alive_frames", -1), ("gameplay_frames", 18001), ("score", float("nan")),
                             ("score_raw_fixed", -1)):
            bad = rows(); bad[0][field] = value
            with self.subTest(field=field), self.assertRaises(pe.ValidationError): pe.validate_rows(bad)
        bad = rows(); bad[0]["terminated"] = bad[0]["truncated"] = True
        with self.assertRaises(pe.ValidationError): pe.validate_rows(bad)

    def test_death_and_unavailable_cause(self):
        bad = rows(); bad[0]["death_cause"] = "unavailable"
        bad[0]["fatal_gameplay_frame"] = 0
        with self.assertRaises(pe.ValidationError): pe.validate_rows(bad)
        good = rows(); good[1]["death_cause"] = "unavailable"
        good[1]["fatal_gameplay_frame"] = None; good[1]["death_observed_lethal_contacts"] = None
        self.assertEqual(pe.summarize_arm(good)["death_cause_counts"]["unavailable"], 1)
        bad = rows(); bad[1]["death_observed_lethal_contacts"]["normal_enemy"] = 0
        with self.assertRaises(pe.ValidationError): pe.validate_rows(bad)

    def test_paired_seed_alignment_and_summary(self):
        a, b = rows(), rows()
        b[10]["alive_frames"] += 25; b[10]["gameplay_frames"] += 25; b[10]["fatal_gameplay_frame"] += 25
        result = pe.paired_summary(a, b)
        self.assertEqual(result["per_seed_differences"][10]["linear_minus_constant_alive_frames"], 25)
        self.assertEqual(result["mean_paired_alive_frame_difference"], 25 / 64)
        b[10], b[11] = b[11], b[10]
        with self.assertRaises(pe.ValidationError): pe.paired_summary(a, b)

    def test_registration_checkpoint_pin(self):
        reg = {"schema": "paired_LR_upperD64_evaluation_registration_v1",
               "manifest_sha256": pe.EXPECTED_MANIFEST_SHA256, "seed_label": pe.LABEL,
               "episode_contract": {"difficulty": 2, "action_repeat": 4, "raw_frame_cap": 18000,
                   "episodes": 64, "batch_size": 1, "action_mode": "deterministic_argmax", "gradients": False,
                   "reset_policy": "construct_once_no_reset"}}
        meta = {"checkpoint_sha256": pe.CONSTANT["checkpoint_sha256"], "run_id": pe.CONSTANT["run_id"],
                "phase_update": 384, "cumulative_updates": 432}
        pe.validate_registration(reg, "constant", meta)
        with self.assertRaises(pe.ValidationError): pe.validate_registration(reg, "constant", {"checkpoint_sha256": "0"*64, "run_id": pe.CONSTANT["run_id"], "phase_update": 384, "cumulative_updates": 432})
        wrong_endpoint = dict(meta, phase_update=383)
        with self.assertRaises(pe.ValidationError): pe.validate_registration(reg, "constant", wrong_endpoint)
        reg["linear_endpoint"] = {"checkpoint_sha256": "1"*64, "run_id": "linear-run", "endpoint_phase_update": 384, "cumulative_update": 432}
        pe.validate_registration(reg, "linear", {"checkpoint_sha256": "1"*64, "run_id": "linear-run", "phase_update": 384, "cumulative_updates": 432})

    def test_empty_incomplete_and_guard_prevent_output(self):
        with self.assertRaises(pe.ValidationError): pe.summarize_arm([])
        with tempfile.TemporaryDirectory() as d:
            reg = {"schema": "bad"}; p = Path(d) / "registration.json"
            raw = json.dumps(reg).encode(); p.write_bytes(raw)
            called = []
            with self.assertRaises(pe.ValidationError):
                pe.evaluate_registered(registration_path=str(p), registration_sha256=hashlib.sha256(raw).hexdigest(),
                    arm="constant", checkpoint_metadata={}, check_guard=lambda: called.append(True),
                    collector=lambda **kw: rows(), output_path=str(Path(d)/"out.json"))
            self.assertEqual(called, [])

    def test_concrete_collector_fake_policy_and_env(self):
        import numpy as np
        import torch
        from types import SimpleNamespace
        created = []
        class Env:
            def __init__(self, seed):
                self.seed = seed
            def episode_info(self):
                return [{"seed": {"evaluation": True, "actual_seed": self.seed}, "startup_frames": 13}]
            def observations(self): return {"x": np.zeros((1, 1), dtype=np.float32)}
            def step(self, action):
                created.append((self.seed, int(action[0])))
                return {"info": [{"seed": {"actual_seed": self.seed}, "bootstrap": True,
                    "score_raw_fixed": 0, "score_delta_sum_raw_fixed": 0, "alive_frames": 1,
                    "objective_return": .01, "gameplay_frames": 1}],
                    "terminated": [False], "truncated": [True],
                    "observations": {"x": np.zeros((1, 1), dtype=np.float32)}}
        def factory(**kw): return Env(kw["seeds_by_slot"][0][0])
        class Policy:
            training = True
            def eval(self): self.training = False
            def train(self, value): self.training = value
            def __call__(self, x): return SimpleNamespace(logits=torch.zeros((len(x), 9)))
        policy = Policy()
        got = pe.collect_d2_rows(model=policy, env_factory=factory, observation_keys=("x",),
            death_fields=lambda info, terminated, truncated: {"death_cause": None,
                "fatal_gameplay_frame": None, "death_observed_lethal_contacts": None}, check_guard=lambda: None)
        self.assertEqual(len(got), 64); self.assertEqual(policy.training, True)
        self.assertEqual([x[0] for x in created], list(pe.SEEDS))

    def test_explicit_entry_uses_fake_collector_only(self):
        with tempfile.TemporaryDirectory() as d:
            contract = {"difficulty": 2, "action_repeat": 4, "raw_frame_cap": 18000,
                "episodes": 64, "batch_size": 1, "action_mode": "deterministic_argmax", "gradients": False,
                "reset_policy": "construct_once_no_reset"}
            reg = {"schema": "paired_LR_upperD64_evaluation_registration_v1",
                   "manifest_sha256": pe.EXPECTED_MANIFEST_SHA256, "seed_label": pe.LABEL,
                   "episode_contract": contract}
            raw = json.dumps(reg, sort_keys=True).encode(); p = Path(d)/"reg.json"; p.write_bytes(raw)
            calls = []
            def fake(**kwargs): calls.append(kwargs); return rows()
            out = Path(d)/"summary.json"
            got = pe.evaluate_registered(registration_path=str(p), registration_sha256=hashlib.sha256(raw).hexdigest(),
                arm="constant", checkpoint_metadata={"checkpoint_sha256": pe.CONSTANT["checkpoint_sha256"], "run_id": pe.CONSTANT["run_id"],
                    "phase_update": 384, "cumulative_updates": 432},
                check_guard=lambda: None, collector=fake, output_path=str(out))
            self.assertTrue(out.exists()); self.assertEqual(len(got["rows"]), 64)
            self.assertEqual(calls[0]["seeds"], pe.SEEDS)
            self.assertFalse(calls[0]["gradients"])

if __name__ == "__main__": unittest.main()
