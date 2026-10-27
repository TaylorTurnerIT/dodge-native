"""Full launcher output contract fixtures; synthetic only, no environment or training."""
import copy
import json
import os
from types import ModuleType
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import execute_once as e
import runner as r


class ContinuationOutputs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent, prefix="outputs-")
        self.root = Path(self.temp.name)
        self.out = self.root / "output"
        self.out.mkdir()
        self.parent_path = self.root / "parent.pt"
        self.cache = Path(os.environ["PYTHONPYCACHEPREFIX"])
        self.reg = {"import_policy": {"pycache_prefix": str(self.cache)}, "output": str(self.out), "root": str(self.root),
                    "runtime_root": str(self.root / "runtime"), "config_sha256": r.CONFIG_SHA,
                    "native": {"sha256": r.NEW_NATIVE_SHA}, "runtime_sha256": "b" * 64,
                    "run_seed": 810631976,
                    "parent": {"path": str(self.parent_path)}}
        self.reg["runtime_versions"] = {"python": "3.12", "torch": "2.x", "numpy": "2.x"}
        self.registration_sha = "a" * 64
        self.initial = [101 + slot % 5 for slot in range(64)]
        self.parent = {"cumulative_counters": {"updates": 120, "optimizer_steps": 15000,
                        "environment_decisions": 1900000, "raw_frames": 7000000},
                       "next_episode_indices": self.initial}
        self._make_fixture()

    def tearDown(self):
        self.temp.cleanup()

    def _make_fixture(self):
        pre = {"count": 16384, "target_mean": 2., "target_variance": 4.,
               "prediction_mean": 1., "prediction_variance": 1., "target_prediction_covariance": 2.,
               "residual_mean": 1., "residual_variance": 1., "residual_mse": 2., "explained_variance": .75}
        post = dict(pre, residual_mean=0., residual_variance=.5, residual_mse=.5, explained_variance=.875)
        metric = {"optimizer_steps": 2, "transitions": 16384, "explained_variance": .75,
                  "critic_diagnostics": {"version": "same_batch_critic_diagnostics_v1", "pre_update": pre, "post_update": post}}
        rows = []
        for local in range(1, r.NEW_UPDATES + 1):
            counters = {"updates": local, "optimizer_steps": local * 2,
                        "environment_decisions": local * 16384, "raw_frames": local * 64}
            rows.append({"phase_update": r.PHASE_START + local, "local_update": local,
                         "metrics": metric, "counters": counters,
                         "update_progress": {"completed_updates": local, "complete": True, "in_update": False}})
        (self.out / "training-metrics.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
        journal = [{"kind": "initial", "info": [{"seed": {"slot": i, "episode": self.initial[i]}} for i in range(64)],
                    "batch_info": {"next_episode_indices": [i + 1 for i in self.initial]}}]
        (self.out / "training-episodes.jsonl").write_text("".join(json.dumps(row) + "\n" for row in journal))
        eval_rows = [{"seed": 0xD0000000 + i, "alive_frames": 2000 + i, "score": float(i),
                      "terminated": True, "truncated": False, "death_cause": "normal_enemy",
                      "objective_return": float(i) + .01 * (2000 + i) - 5} for i in range(64)]
        evaluation = {"complete": True, "rows": eval_rows, "mean_alive_frames": 2031.5,
                      "mean_score": 31.5, "death_causes": {"normal_enemy": 64}, "deaths": 64, "caps": 0}
        for phase in (r.PHASE_START, r.PHASE_END):
            local = phase - r.PHASE_START
            candidate = self.out / f"checkpoint-{phase:06d}-candidate.pt"
            candidate.write_bytes(f"synthetic checkpoint {phase}".encode())
            digest = r.sha(candidate)
            certificate = {"evaluation": evaluation, "performance": r.performance(evaluation),
                           "checkpoint": candidate.name, "checkpoint_sha256": digest,
                           "phase_update": phase, "local_update": local,
                           "normal_training_iteration": True, "training_eligible": False,
                           "promoted": False, "competence_passed": False,
                           "training_state_unchanged": True}
            r.save(self.out / f"development-{phase:06d}.json", certificate)
            r.save(Path(str(candidate) + ".json"), {"eligibility_status": "provisional_pending_parent_terminal_receipt",
                "training_eligible": False, "promoted": False, "checkpoint_sha256": digest})
        self.final_path = self.out / "checkpoint-000132-candidate.pt"
        self.final_sha = r.sha(self.final_path)
        self.final_state = {"schema": "d2_training_v3_checkpoint_v1",
            "eligibility_status": "provisional_pending_parent_terminal_receipt", "registration_sha256": self.registration_sha,
            "config_sha256": r.CONFIG_SHA, "policy_sha256": r.POLICY_SHA, "runtime_sha256": "b" * 64,
            "native_sha256": r.NEW_NATIVE_SHA, "parent_sha256": r.PARENT_SHA, "run_seed": 810631976,
            "identity": {"registration_sha256": self.registration_sha, "run_seed": 810631976},
            "training_eligible": False, "promoted": False,
            "counters": rows[-1]["counters"], "inherited_counters": self.parent["cumulative_counters"],
            "cumulative_counters": {key: self.parent["cumulative_counters"][key] + rows[-1]["counters"][key]
                                    for key in rows[-1]["counters"]},
            "next_episode_indices": [i + 1 for i in self.initial],
            "update_progress": {"completed_updates": r.NEW_UPDATES, "complete": True, "in_update": False},
            "phase_update": r.PHASE_END, "local_update": r.NEW_UPDATES,
            "parent_inclusive_wall_seconds": r.PARENT_WALL_SECONDS,
            "parent_checkpoint_sha256": r.PARENT_SHA,
            "abandoned_current_episodes": [{"slot": i, "seed": {"episode": self.initial[i]}, "gameplay_frames": 60} for i in range(64)]}
        self.worker = {"status": "completed", "updates": r.NEW_UPDATES,
            "evaluated_updates": [r.PHASE_START, r.PHASE_END], "normal_training_iteration": True,
            "training_eligible": False, "promoted": False, "first_failure": None, "first_signal": None,
            "work_elapsed_seconds": 1500., "elapsed_seconds": 1510.,
            "current_iteration_wall_seconds": 1500., "parent_inclusive_wall_seconds": r.PARENT_WALL_SECONDS,
            "cumulative_D2_inclusive_wall_seconds": r.PARENT_WALL_SECONDS + 1500.,
            "peak_rss_bytes": 100, "peak_mps_driver_bytes": 100,
            "counters": rows[-1]["counters"], "phase_updates": [r.PHASE_START, r.PHASE_END],
            "inherited_counters": self.parent["cumulative_counters"],
            "cumulative_counters": self.final_state["cumulative_counters"],
            "final_resume_next_episode_indices": self.final_state["next_episode_indices"]}

    def _validate(self, worker=None):
        import sys
        sys.path.insert(0, self.reg["runtime_root"])
        fake_ckpt = type("Checkpoints", (), {
            "load_checkpoint": staticmethod(lambda path, **kw: self.parent if str(path) == str(self.parent_path) else self.final_state),
            "require_complete_update": staticmethod(lambda state: None)})
        package = ModuleType("dodge_rl")
        package.checkpoints = fake_ckpt
        with patch.dict("sys.modules", {"dodge_rl": package, "dodge_rl.checkpoints": fake_ckpt}):
            return e.validate_outputs(self.reg, worker or self.worker, self.registration_sha)

    def test_complete_60_update_fixture_from_accepted_parent_to_180_cumulative(self):
        evidence = self._validate()
        self.assertEqual(evidence["updates_checked"], 60)
        self.assertNotEqual(evidence["final_checkpoint_sha256"], self.registration_sha)
        self.assertEqual(evidence["cumulative_counters"]["updates"], 180)
        self.assertEqual(r.LIMITS["eval_updates"], [72, 132])

    def test_rejects_counter_seed_wall_and_hash_substitution(self):
        mutations = (
            lambda: self._edit_metric(0, "local_update", 0),
            lambda: self._edit_metric(59, "phase_update", 131),
            lambda: self._edit_metric(59, "counters", {"updates": 59}),
            lambda: self._edit_worker("final_resume_next_episode_indices", [0] * 64),
            lambda: self._edit_worker("cumulative_D2_inclusive_wall_seconds", 1188.34122675),
            lambda: self._edit_worker("current_iteration_wall_seconds", 1700.),
            lambda: self._edit_cert_hash("checkpoint-000132-candidate.pt", "0" * 64),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                for item in self.out.iterdir():
                    if item.is_file(): item.unlink()
                self._make_fixture()
                mutate()
                with self.assertRaises(ValueError): self._validate()

    def _edit_metric(self, index, key, value):
        path = self.out / "training-metrics.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[index][key] = value
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))

    def _edit_worker(self, key, value):
        self.worker[key] = value

    def _edit_cert_hash(self, name, digest):
        path = self.out / "development-000132.json"
        value = r.read(path); value["checkpoint_sha256"] = digest; path.write_text(json.dumps(value))


if __name__ == "__main__":
    unittest.main()
