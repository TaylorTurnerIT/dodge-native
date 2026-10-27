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
        alive = i + 1 if died else 18000
        out.append({"episode_index": i, "seed": seed, "startup_frames": 13, "alive_frames": alive,
                    "gameplay_frames": alive + int(died), "score_raw_fixed": i * 65536,
                    "score_delta_sum_raw_fixed": i * 65536,
                    "score": float(i), "terminated": died, "truncated": not died,
                    "objective_return": float(i) + alive / 100 - 5 * int(died),
                    "death_cause": cause,
                    "fatal_gameplay_frame": alive + 1 if died else None,
                    "death_observed_lethal_contacts": ({c: int(c == cause) for c in pe.DEATH_CAUSES} if died else None)})
    return out

class EvaluatorTests(unittest.TestCase):
    def test_manifest_and_metrics(self):
        m = pe.load_manifest()
        s = pe.summarize_arm(rows())
        self.assertEqual(m["seeds"], list(pe.SEEDS))
        self.assertEqual(s["bottom16_mean_Q1"], sum(sorted(r["alive_frames"] for r in rows())[:16]) / 16)
        self.assertEqual(s["top16_mean_Q4"], 18000)
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
        bad = rows(); bad[0]["score_delta_sum_raw_fixed"] += 1
        with self.assertRaises(pe.ValidationError): pe.validate_rows(bad)
        for change in (("gameplay_frames", 17), ("fatal_gameplay_frame", 18), ("startup_frames", 12),
                       ("seed", pe.SEEDS[2]), ("objective_return", 123.0)):
            bad = rows(); bad[1][change[0]] = change[1]
            with self.subTest(change=change), self.assertRaises(pe.ValidationError): pe.validate_rows(bad)
        bad = rows(); bad[0]["gameplay_frames"] = 17999; bad[0]["alive_frames"] = 17999
        with self.assertRaises(pe.ValidationError): pe.validate_rows(bad)

    def test_death_and_unavailable_cause(self):
        bad = rows(); bad[0]["death_cause"] = "unavailable"
        bad[0]["fatal_gameplay_frame"] = 0
        with self.assertRaises(pe.ValidationError): pe.validate_rows(bad)
        good = rows(); good[1]["death_cause"] = "unavailable"
        good[1]["fatal_gameplay_frame"] = None; good[1]["death_observed_lethal_contacts"] = None
        self.assertEqual(pe.summarize_arm(good)["death_cause_counts"]["unavailable"], 1)
        with self.assertRaises(pe.ValidationError): pe.validate_rows(good, allow_unavailable=False)
        bad = rows(); bad[1]["death_observed_lethal_contacts"]["normal_enemy"] = 0
        with self.assertRaises(pe.ValidationError): pe.validate_rows(bad)

    def test_paired_seed_alignment_and_summary(self):
        a, b = rows(), rows()
        b[10]["alive_frames"] += 25; b[10]["gameplay_frames"] += 25; b[10]["fatal_gameplay_frame"] += 25; b[10]["objective_return"] += .25
        linear_ep = {"checkpoint_sha256": "1" * 64, "run_id": "linear-run",
                     "endpoint_phase_update": 384, "cumulative_update": 432}
        result = pe.paired_summary(a, b, linear_endpoint=linear_ep,
                                   constant_registration_sha256="2" * 64, linear_registration_sha256="3" * 64)
        self.assertEqual(result["per_seed_differences"][10]["linear_minus_constant_alive_frames"], 25)
        self.assertEqual(result["mean_paired_alive_frame_difference"], 25 / 64)
        self.assertEqual(result["constant_endpoint"]["registration_sha256"], "2" * 64)
        self.assertEqual(result["linear_endpoint"]["run_id"], "linear-run")
        b[10], b[11] = b[11], b[10]
        with self.assertRaises(pe.ValidationError): pe.paired_summary(a, b, linear_endpoint=linear_ep,
                constant_registration_sha256="2" * 64, linear_registration_sha256="3" * 64)

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
        for bad_endpoint in ({"checkpoint_sha256": None, "run_id": None, "endpoint_phase_update": 384, "cumulative_update": 432},
                             {"checkpoint_sha256": "xyz", "run_id": "r", "endpoint_phase_update": 384, "cumulative_update": 432}):
            reg["linear_endpoint"] = bad_endpoint
            with self.assertRaises(pe.ValidationError): pe.validate_registration(reg, "linear", {"checkpoint_sha256": bad_endpoint["checkpoint_sha256"], "run_id": bad_endpoint["run_id"], "phase_update": 384, "cumulative_updates": 432})

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
            destination = Path(d) / "result.json"
            destination.write_text("prior\n")
            with self.assertRaises(FileExistsError): pe._write_exclusive_json(destination, {"complete": True})
            self.assertEqual(destination.read_text(), "prior\n")


    def test_evaluate_registered_binds_concrete_collector_signature(self):
        from unittest.mock import patch
        contract = {"difficulty": 2, "action_repeat": 4, "raw_frame_cap": 18000,
            "episodes": 64, "batch_size": 1, "action_mode": "deterministic_argmax", "gradients": False,
            "reset_policy": "construct_once_no_reset"}
        registration = {"schema": "paired_LR_upperD64_evaluation_registration_v1",
            "manifest_sha256": pe.EXPECTED_MANIFEST_SHA256, "seed_label": pe.LABEL, "episode_contract": contract}
        with tempfile.TemporaryDirectory() as d:
            raw = json.dumps(registration, sort_keys=True).encode(); reg_path=Path(d)/"reg.json"; reg_path.write_bytes(raw)
            calls=[]
            def native_collector(**kwargs): calls.append(kwargs); return rows()
            with patch.object(pe, "collect_d2_rows", native_collector):
                result=pe.evaluate_registered(registration_path=str(reg_path), registration_sha256=hashlib.sha256(raw).hexdigest(),
                    arm="constant", checkpoint_metadata={"checkpoint_sha256": pe.CONSTANT["checkpoint_sha256"],
                    "run_id": pe.CONSTANT["run_id"], "phase_update":384, "cumulative_updates":432},
                    check_guard=lambda:None, collector=native_collector, model=object(), env_factory=lambda:None,
                    observation_keys=("x",), death_fields=lambda *_:{}, output_path=str(Path(d)/"result.json"))
            self.assertEqual(len(result["rows"]),64)
            self.assertEqual(set(calls[0]), {"model","env_factory","observation_keys","death_fields","check_guard","allow_unavailable"})
            self.assertFalse(calls[0]["allow_unavailable"])

    def test_backend_rejects_wrong_collector_pin_before_callbacks(self):
        constructed=[]
        registration={"constant_endpoint": {**pe.CONSTANT, "metadata_sha256":"a"*64,
            "model_state_dict_sha256":"b"*64}, "backend_identity":{"collector_sha256":"0"*64}}
        def fake_factory(): constructed.append(True)
        with self.assertRaises(pe.ValidationError):
            pe.build_registered_backend(registration=registration, arm="constant", source_root="/missing",
                checkpoint_path="/missing/checkpoint", checkpoint_metadata_path="/missing/metadata",
                check_guard=lambda:None, env_factory=fake_factory, model_factory=fake_factory,
                checkpoint_loader=fake_factory)
        self.assertEqual(constructed,[])

    def test_concrete_collector_fake_policy_and_env(self):
        import numpy as np
        import torch
        from types import SimpleNamespace
        calls = []
        class Env:
            def __init__(self, seed): self.seed, self.n = seed, 0
            def episode_info(self):
                return [{"seed": {"evaluation": True, "actual_seed": self.seed}, "startup_frames": 13, "gameplay_frames": 0}]
            def observations(self): return {"x": np.zeros((1, 1), dtype=np.float32)}
            def step(self, action):
                calls.append((self.seed, int(action[0])))
                self.n += 1
                if self.seed % 2 == 0:
                    return {"info": [{"seed": {"actual_seed": self.seed}, "bootstrap": False,
                        "score_raw_fixed": 0, "score_delta_sum_raw_fixed": 0, "alive_frames": 0,
                        "startup_frames": 13, "objective_return": -5.0, "gameplay_frames": 1,
                        "death_cause": "normal_enemy", "fatal_gameplay_frame": 1,
                        "death_observed_lethal_contacts": {c: int(c == "normal_enemy") for c in pe.DEATH_CAUSES}}],
                        "terminated": [True], "truncated": [False], "observations": self.observations()}
                if self.n == 1:
                    return {"info": [{"seed": {"actual_seed": self.seed}, "bootstrap": True,
                        "score_raw_fixed": 0, "score_delta_sum_raw_fixed": 0, "alive_frames": 4,
                        "startup_frames": 13, "objective_return": .04, "gameplay_frames": 4}],
                        "terminated": [False], "truncated": [False], "observations": self.observations()}
                return {"info": [{"seed": {"actual_seed": self.seed}, "bootstrap": True,
                    "score_raw_fixed": 0, "score_delta_sum_raw_fixed": 0, "alive_frames": 18000,
                    "startup_frames": 13, "objective_return": 180.0, "gameplay_frames": 18000}],
                    "terminated": [False], "truncated": [True], "observations": self.observations()}
        def factory(**kw):
            self.assertEqual(kw["difficulty"], 2); self.assertEqual(kw["action_repeat"], 4)
            self.assertEqual(kw["raw_frame_cap"], 18000); self.assertEqual(kw["excluded_seed_ranges"], list(pe.EXCLUDED_SEED_RANGES))
            self.assertEqual(kw["seeds_by_slot"][0], [kw["seeds_by_slot"][0][0]])
            return Env(kw["seeds_by_slot"][0][0])
        class Policy(torch.nn.Module):
            def __init__(self):
                super().__init__(); self.weight = torch.nn.Parameter(torch.tensor(0.0)); self.mutate = False; self.did_mutate = False
            def forward(self, x):
                self.grad_enabled = torch.is_grad_enabled(); self.batch_sizes = getattr(self, "batch_sizes", []) + [len(x)]
                if self.mutate and not self.did_mutate:
                    self.did_mutate = True; self.weight.data.add_(1); torch.rand(1)
                    self.weight.grad = torch.ones_like(self.weight); self.training = True
                logits = torch.zeros((len(x), 9)); logits[:, 8] = 1
                return SimpleNamespace(logits=logits)
        policy = Policy(); before_weights = {k: v.detach().clone() for k, v in policy.state_dict().items()}
        before_rng = torch.get_rng_state().clone()
        got = pe.collect_d2_rows(model=policy, env_factory=factory, observation_keys=("x",),
            death_fields=lambda info, terminated, truncated: {"death_cause": info.get("death_cause"),
                "fatal_gameplay_frame": info.get("fatal_gameplay_frame"),
                "death_observed_lethal_contacts": info.get("death_observed_lethal_contacts")}, check_guard=lambda: None)
        self.assertEqual(len(got), 64); self.assertTrue(policy.training)
        self.assertFalse(policy.grad_enabled)
        self.assertTrue(all(torch.equal(policy.state_dict()[k], v) for k, v in before_weights.items()))
        self.assertTrue(torch.equal(torch.get_rng_state(), before_rng))
        self.assertEqual([seed for seed, _ in calls], list(pe.SEEDS) + [seed for seed in pe.SEEDS if seed % 2])
        self.assertTrue(all(action == 8 for _, action in calls))
        self.assertEqual(sum(row["terminated"] for row in got), 32)
        self.assertEqual(sum(row["truncated"] for row in got), 32)
        self.assertEqual(policy.batch_sizes, [64, 32])
        policy.mutate = True; policy.did_mutate = False
        before_rng = torch.get_rng_state().clone(); before_weights = {k: v.detach().clone() for k, v in policy.state_dict().items()}
        with self.assertRaises(pe.ValidationError):
            pe.collect_d2_rows(model=policy, env_factory=factory, observation_keys=("x",),
                death_fields=lambda info, terminated, truncated: {"death_cause": info.get("death_cause"),
                    "fatal_gameplay_frame": info.get("fatal_gameplay_frame"),
                    "death_observed_lethal_contacts": info.get("death_observed_lethal_contacts")},
                check_guard=lambda: None)
        self.assertTrue(policy.training)
        self.assertTrue(all(torch.equal(policy.state_dict()[k], v) for k, v in before_weights.items()))
        self.assertIsNone(policy.weight.grad)
        self.assertTrue(torch.equal(torch.get_rng_state(), before_rng))

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
            prior = out.read_bytes()
            with self.assertRaises(FileExistsError):
                pe.evaluate_registered(registration_path=str(p), registration_sha256=hashlib.sha256(raw).hexdigest(),
                    arm="constant", checkpoint_metadata={"checkpoint_sha256": pe.CONSTANT["checkpoint_sha256"],
                    "run_id": pe.CONSTANT["run_id"], "phase_update": 384, "cumulative_updates": 432},
                    check_guard=lambda: None, collector=fake, output_path=str(out))
            self.assertEqual(out.read_bytes(), prior)
            interrupted = Path(d) / "interrupted.json"
            checks = [0]
            def guard():
                checks[0] += 1
                if checks[0] > 1: raise pe.ValidationError("guard stopped")
            def interrupted_collector(**kwargs):
                guard()
                return rows()
            with self.assertRaises(pe.ValidationError):
                pe.evaluate_registered(registration_path=str(p), registration_sha256=hashlib.sha256(raw).hexdigest(),
                    arm="constant", checkpoint_metadata={"checkpoint_sha256": pe.CONSTANT["checkpoint_sha256"],
                    "run_id": pe.CONSTANT["run_id"], "phase_update": 384, "cumulative_updates": 432},
                    check_guard=guard, collector=interrupted_collector, output_path=str(interrupted))
            self.assertFalse(interrupted.exists())

if __name__ == "__main__": unittest.main()
