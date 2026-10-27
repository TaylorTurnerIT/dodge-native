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
                     "endpoint_phase_update": 384, "cumulative_update": 432, "metadata_sha256":"a"*64, "model_state_dict_sha256":"b"*64, "source_audit_sha256":"c"*64,
                     "source_audit_path":"/fixture/audit.json","metadata_path":"/fixture/meta.json",
                     "derivation_receipt_path":"/fixture/receipt.json","derivation_receipt_sha256":"e"*64}
        result = pe.paired_summary(a, b, linear_endpoint=linear_ep,
                                   constant_registration_sha256="2" * 64, linear_registration_sha256="3" * 64)
        self.assertEqual(result["per_seed_differences"][10]["linear_minus_constant_alive_frames"], 25)
        self.assertEqual(result["mean_paired_alive_frame_difference"], 25 / 64)
        self.assertEqual(result["constant_endpoint"]["registration_sha256"], "2" * 64)
        self.assertEqual(result["linear_endpoint"]["run_id"], "linear-run")
        b[10], b[11] = b[11], b[10]
        with self.assertRaises(pe.ValidationError): pe.paired_summary(a, b, linear_endpoint=linear_ep,
                constant_registration_sha256="2" * 64, linear_registration_sha256="3" * 64)

    def test_metadata_attestation_contract_and_rejects_bad_claims(self):
        registration = self.registration()
        endpoint = registration["constant_endpoint"]
        good = self.metadata("constant")
        pe.validate_registration(registration, "constant", good)
        for field, value in (("run_id", None), ("checkpoint_sha256", "0"*64),
                             ("phase_update", 383), ("cumulative_updates", 431),
                             ("model_state_dict_sha256", "f"*64), ("source_audit_sha256", "e"*64),
                             ("source_audit_path", "/wrong/audit.json")):
            bad = dict(good, **{field: value})
            with self.subTest(field=field), self.assertRaises(pe.ValidationError):
                pe.validate_registration(registration, "constant", bad)
        for field, value in (("checkpoint_sha256", None), ("run_id", ""),
                             ("endpoint_phase_update", 383), ("cumulative_update", 431),
                             ("metadata_sha256", None), ("model_state_dict_sha256", "bad")):
            bad = dict(endpoint, **{field: value})
            with self.subTest(endpoint_field=field), self.assertRaises(pe.ValidationError):
                pe.validate_endpoint(bad)

    @staticmethod
    def metadata(arm):
        return json.loads(Path(pe.METADATA_RECEIPT.parent / f"{arm}-endpoint-metadata.json").read_text())

    @staticmethod
    def endpoint(arm):
        data = EvaluatorTests.metadata(arm)
        receipt = json.loads(pe.METADATA_RECEIPT.read_text())["endpoints"][arm]
        return {"run_id":data["run_id"],"checkpoint_sha256":data["checkpoint_sha256"],
            "endpoint_phase_update":data["phase_update"],"cumulative_update":data["cumulative_updates"],
            "metadata_sha256":receipt["sha256"],"metadata_path":receipt["path"],
            "model_state_dict_sha256":data["model_state_dict_sha256"],
            "source_audit_sha256":data["source_audit_sha256"],"source_audit_path":data["source_audit_path"],
            "derivation_receipt_sha256":pe.METADATA_RECEIPT_SHA256,
            "derivation_receipt_path":str(pe.METADATA_RECEIPT)}

    @staticmethod
    def registration():
        provenance={name:{"path":str(path),"sha256":digest}
                    for name,(path,digest) in pe.TRAINING_REGISTRATIONS.items()}
        members=pe._training_member_map()
        return {"schema":"paired_LR_upperD64_evaluation_registration_v2",
            "manifest_sha256":pe.EXPECTED_MANIFEST_SHA256,"seed_label":pe.LABEL,
            "runtime_root":str(pe.RUNTIME_ROOT),"runtime_member_sha256":members,
            "training_provenance":provenance,
            "backend_identity":{"collector_sha256":"f"*64,"model_source":pe.MODEL_SOURCE,
                "runtime_member_sha256":members},
            "episode_contract":{"difficulty":2,"action_repeat":4,"raw_frame_cap":18000,"episodes":64,
                "batch_size":1,"action_mode":"deterministic_argmax","gradients":False,
                "reset_policy":"construct_once_no_reset"},
            "constant_endpoint":EvaluatorTests.endpoint("constant"),
            "linear_endpoint":EvaluatorTests.endpoint("linear")}

    def test_runtime_layout_and_member_map_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(pe.ValidationError): pe._verify_runtime_pins(Path(d), {})
            root = Path(d); (root / "dodge_rl").mkdir()
            with self.assertRaises(pe.ValidationError): pe._verify_runtime_pins(root, {"dodge_rl/_native.cpython-312-darwin.so":"0"*64})
        self.assertEqual(pe.RUNTIME_MEMBERS, {"dodge_rl/__init__.py", "dodge_rl/_native.cpython-312-darwin.so",
            "dodge_rl/checkpoints.py", "dodge_rl/dev_eval.py", "dodge_rl/identity.py",
            "dodge_rl/models/__init__.py", "dodge_rl/models/teacher.py"})
        self.assertEqual(pe.MODEL_SOURCE, "dodge_rl/models/teacher.py")

    def test_runtime_preflight_rejects_bad_pin_before_any_constructor(self):
        registration=self.registration()
        registration["backend_identity"]["collector_sha256"]=pe._file_sha256(Path(pe.__file__))
        constructed=[]
        for bad_root, bad_map in ((Path("/repo-root"), registration["runtime_member_sha256"]),
            (pe.RUNTIME_ROOT, {**registration["runtime_member_sha256"],
                "dodge_rl/_native.cpython-312-darwin.so":"9"*64}),
            (pe.RUNTIME_ROOT, {key:value for key,value in registration["runtime_member_sha256"].items()
                if key != "dodge_rl/models/teacher.py"})):
            with self.subTest(root=str(bad_root),members=len(bad_map)), self.assertRaises(pe.ValidationError):
                pe._build_registered_backend(registration=registration,arm="constant",source_root=str(bad_root),
                    checkpoint_path="/missing/checkpoint.pt",checkpoint_metadata_path=registration["constant_endpoint"]["metadata_path"],
                    check_guard=lambda:None,env_factory=lambda:constructed.append("env"),
                    model_factory=lambda:constructed.append("model"),checkpoint_loader=lambda *_:constructed.append("loader"))
        self.assertEqual(constructed,[])

    def test_shadowed_module_rejected_before_import(self):
        with self.assertRaises(pe.ValidationError): pe._assert_no_preloaded_runtime({"dodge_rl": object()})

    def test_manifest_rejection_precedes_any_runtime_factory(self):
        from unittest.mock import patch
        called=[]
        with tempfile.TemporaryDirectory() as d:
            bad=Path(d)/"manifest.json"; bad.write_text("{}")
            registration=Path(d)/"registration.json"; registration.write_text("{}")
            with patch.object(pe, "MANIFEST", bad), self.assertRaises(pe.ValidationError):
                pe.evaluate_with_registered_backend(registration_path=str(registration), registration_sha256="0"*64,
                    arm="constant",source_root=d,checkpoint_path=d,checkpoint_metadata_path=d,
                    check_guard=lambda:called.append("guard"),output_path=str(Path(d)/"out"))
        self.assertEqual(called, [])

    def test_caller_claims_entrypoint_absent(self):
        self.assertFalse(hasattr(pe, "evaluate_registered"))

    def test_registration_schema_is_not_open_to_caller_fake_backend(self):
        registration=self.registration()
        registration["injected_backend_reviewed"]=True
        with self.assertRaises(pe.ValidationError): pe.validate_registration(registration,"constant",self.metadata("constant"))

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

if __name__ == "__main__": unittest.main()
