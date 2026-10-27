import copy
import hashlib
import json
import unittest

import adapter


class AdapterContractTests(unittest.TestCase):
    @staticmethod
    def iteration_data():
        metrics = []
        for n in range(1, 81):
            metrics.append({"phase_update": n, "metrics": {"transitions": 16384, "optimizer_steps": 1},
                "counters": {"updates": n, "optimizer_steps": n, "environment_decisions": n * 16384,
                             "raw_frames": n * 40000},
                "update_progress": {"complete": True, "in_update": False}})
        evaluations = []
        for n in adapter.EVAL_UPDATES:
            rows = [{"seed": 0xD0000000 + i, "alive_frames": 2000 + i, "score": float(i)} for i in range(64)]
            performance = {}
            for name in ("alive_frames", "score"):
                values = sorted(row[name] for row in rows)
                performance[name] = {"Q1": sum(values[:16]) / 16,
                    "Q4": sum(values[-16:]) / 16, "mean": sum(values) / 64}
            summary = {"complete": True, "stage": "D2", "episodes": 64, "rows": rows,
                "mean_alive_frames": sum(r["alive_frames"] for r in rows) / 64,
                "mean_score": sum(r["score"] for r in rows) / 64}
            evaluations.append({"phase_update": n, "summary": summary, "performance": performance,
                "checkpoint": f"checkpoint-{n:06d}-candidate.pt", "checkpoint_sha256": "f" * 64,
                "training_eligible": False})
        worker = {"status": "completed", "updates": 80, "raw_exit": 0, "cancelled": False,
            "elapsed_seconds": 1200.0, "peak_rss_bytes": 1000000, "peak_mps_driver_bytes": 1000000,
            "first_failure": None, "first_signal": None, "counters": metrics[-1]["counters"]}
        return metrics, evaluations, worker

    def test_eighty_updates_and_six_evaluations(self):
        rows, evals, worker = self.iteration_data()
        result = adapter.validate_synthetic_iteration(rows, evals, worker)
        self.assertTrue(result["completed_training_iteration"])
        self.assertFalse(result["competence_passed"])
        self.assertFalse(result["progress_passed"])

    def test_failure_and_truncation_rejected(self):
        rows, evals, worker = self.iteration_data()
        with self.assertRaises(ValueError):
            adapter.validate_synthetic_iteration(rows[:-1], evals, worker)
        with self.assertRaises(ValueError):
            worker["status"] = "failed"
            adapter.validate_synthetic_iteration(rows, evals, worker)

    def test_score_never_enters_progress_predicate(self):
        self.assertFalse(adapter.v3_progress_passed({"complete": True, "mean_alive_frames": 3059.99,
                                                     "mean_score": 1e99}))
        self.assertTrue(adapter.v3_progress_passed({"complete": True, "mean_alive_frames": 3060,
                                                    "mean_score": -1e99}))

    def test_checkpoint_is_provisional_at_complete_boundary(self):
        registration = {"policy": {"sha256": "b" * 64},
                        "runtime_sha256": "c" * 64, "native": {"sha256": "d" * 64}}
        identity = {"version": "teacher_identity_v3", "phase": "D2"}
        identity_sha = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        rng = {"python": (), "numpy_global": (), "numpy_generator": None,
               "torch_cpu": b"cpu", "torch_mps": b"mps", "sampling_backend": "torch_global_mps"}
        payload = adapter.checkpoint_payload(model={"weight": b"w"}, optimizer={"state": {}}, rng=rng, registration=registration,
            counters={"updates": 32}, run_seed=810631976, registration_sha256="a" * 64, next_episode_indices=[1] * 64,
            identity=identity, identity_sha256=identity_sha, abandoned_current_episodes=[],
            update_progress={"complete": True, "in_update": False}, cumulative_wall_seconds=4.0)
        self.assertEqual(payload["version"], "teacher_checkpoint_v1")
        self.assertEqual(payload["schema"], "d2_training_v3_checkpoint_v1")
        self.assertEqual(payload["eligibility_status"], "provisional_pending_parent_terminal_receipt")
        self.assertNotIn("diagnostic_only", payload)
        with self.assertRaises(ValueError):
            adapter.checkpoint_payload(model={"weight": b"w"}, optimizer={"state": {}}, rng=rng, registration=registration,
                counters={"updates": 32, "in_update": True}, run_seed=1, registration_sha256="a" * 64,
                identity=identity, identity_sha256=identity_sha, next_episode_indices=[1] * 64,
                abandoned_current_episodes=[], update_progress={"complete": True, "in_update": True},
                cumulative_wall_seconds=4.0)

    def test_seed_is_pinned(self):
        registration = {"policy": {"sha256": "b" * 64},
                        "runtime_sha256": "c" * 64, "native": {"sha256": "d" * 64}}
        identity = {"version": "teacher_identity_v3", "phase": "D2"}
        identity_sha = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        rng = {"python": (), "numpy_global": (), "numpy_generator": None,
               "torch_cpu": b"cpu", "torch_mps": b"mps", "sampling_backend": "torch_global_mps"}
        with self.assertRaises(ValueError):
            adapter.checkpoint_payload(model={"weight": b"w"}, optimizer={"state": {}}, rng=rng,
                registration=registration, counters={"updates": 1}, run_seed=1, registration_sha256="a" * 64,
                identity=identity, identity_sha256=identity_sha, next_episode_indices=[0] * 64,
                abandoned_current_episodes=[], update_progress={"complete": True, "in_update": False},
                cumulative_wall_seconds=4.0)

    def test_episode_seed_indices_carry_without_replay(self):
        initial = {"kind": "initial", "info": [{"seed": {"slot": slot, "episode": 0}} for slot in range(64)],
                   "batch_info": {"next_episode_indices": [0] * 64}}
        records = [initial,
            {"kind": "completed", "phase_update": 1, "info": {"seed": {"slot": 0, "episode": 0}}},
            {"kind": "reset", "phase_update": 1, "indices": [0], "info": [{"seed": {"slot": 0, "episode": 1}}]},
            {"kind": "completed", "phase_update": 2, "info": {"seed": {"slot": 0, "episode": 1}}}]
        result = adapter.validate_episode_journal(records)
        self.assertEqual(result["final_episode_indices"][0], 2)
        records[2]["info"][0]["seed"]["episode"] = 3
        with self.assertRaises(ValueError):
            adapter.validate_episode_journal(records)

    def test_cache_policy_requires_explicit_empty_value(self):
        reg = {"import_policy": {"PYTHONPYCACHEPREFIX": "", "python_flag": "-B"}}
        adapter.check_import_cache(reg, {"PYTHONPYCACHEPREFIX": ""})
        with self.assertRaises(ValueError):
            adapter.check_import_cache(reg, {})
        with self.assertRaises(ValueError):
            adapter.check_import_cache(reg, {"PYTHONPYCACHEPREFIX": "/tmp/cache"})


if __name__ == "__main__":
    unittest.main()
