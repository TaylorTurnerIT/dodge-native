import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import selection


def write(path, obj):
    path.write_text(json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n")
    return selection.sha256(path)


def make_result(update, value, reg_sha, checkpoint, cohort_sha):
    rows = []
    for i, seed in enumerate(selection.SEEDS):
        alive = value
        rows.append({"episode_index": i, "seed": seed, "score_raw_fixed": 0,
                     "score": 0.0, "objective_return": alive / 100 - 5,
                     "alive_frames": alive, "gameplay_frames": alive + 1,
                     "startup_frames": 0, "score_delta_sum_raw_fixed": 0,
                     "terminated": True, "truncated": False,
                     "death_cause": "normal_enemy", "fatal_gameplay_frame": None,
                     "death_observed_lethal_contacts": None})
    return {"schema": "expanded_D2_candidate_evaluation_v1", "complete": True,
            "candidate_update": update, "checkpoint_sha256": checkpoint,
            "cohort_name": "ranking", "cohort_sha256": cohort_sha,
            "episodes": 1024, "caps": 0,
            "death_causes": {cause: (1024 if cause == "normal_enemy" else 0)
                              for cause in selection.DEATH_CAUSES},
            "performance": {"worst": value, "q1_bottom_quarter_mean": float(value),
                "mean": float(value), "q4_top_quarter_mean": float(value), "best": value},
            "elapsed_seconds": 1.25, "rows": rows,
            "evidence_limit": "ranking is selection-only; confirmation is one conditional winner-vs-348 comparison",
            "registration_sha256": reg_sha, "model_state_dict_sha256": "m" * 64,
            "backend": "cpu"}


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.manifest = self.d / "ranking-manifest.json"
        write(self.manifest, {"count": 1024, "seeds": list(selection.SEEDS)})
        self.cohort_sha = selection.sha256(self.manifest)
        self.pins = {u: ("%064x" % u) for u in selection.UPDATES}
        self.reg = {"schema": "expanded_D2_evaluation_registration_v1", "mode": "ranking",
            "run_id": "synthetic-rank-run", "source": {"evaluator_sha256": "e" * 64,
            "worker_sha256": "w" * 64}, "runtime": {"backend": "cpu", "member_sha256": {"member-%02d" % i: ("%064x" % i) for i in range(13)}},
            "candidates": {str(u): {"phase_update": u, "checkpoint_sha256": self.pins[u],
                "checkpoint_path": "/synthetic/checkpoint-%d" % u,
                "source_receipt_path": "/synthetic/receipt-%d" % u,
                "source_receipt_sha256": "s" * 64} for u in selection.UPDATES},
            "cohorts": {"ranking": {"manifest_path": str(self.manifest),
                "manifest_sha256": self.cohort_sha, "count": 1024}}}
        self.regpath = self.d / "registration.json"
        self.regsha = write(self.regpath, self.reg)
        self.result_paths, self.results = {}, {}
        for u in selection.UPDATES:
            path = self.d / ("candidate-%d.json" % u)
            result = make_result(u, 1000 + u, self.regsha, self.pins[u], self.cohort_sha)
            self.result_paths[u] = path
            self.results[u] = result
            write(path, result)
        self.summary = self.d / "ranking-bundle.json"
        self.outer = self.d / "outer.json"
        self.refresh()

    def refresh(self, winner=None):
        if winner is None:
            winner = max(selection.UPDATES, key=lambda u: (self.results[u]["performance"]["mean"], -u))
        for u, path in self.result_paths.items():
            write(path, self.results[u])
        self.summary_sha = write(self.summary, {"schema": selection.RANKING_SCHEMA,
            "selection_only": True, "winner_update": winner,
            "candidate_results": [self.results[u] for u in selection.UPDATES]})
        artifacts = [{"path": str(self.summary.resolve()), "sha256": self.summary_sha}]
        artifacts += [{"path": str(self.result_paths[u].resolve()), "sha256": selection.sha256(self.result_paths[u])} for u in selection.UPDATES]
        self.outer_sha = write(self.outer, {"schema": "expanded_eval_outer_receipt_v1",
            "run_id": self.reg["run_id"], "registration_sha256": self.regsha,
            "stage": "ranking", "candidate_update": 348, "cohort": "ranking",
            "raw_exit_code": 0, "stop_reason": None, "process_group_absent": True,
            "output_artifacts": artifacts, "worker_sha256": self.reg["source"]["worker_sha256"],
            "evaluator_sha256": self.reg["source"]["evaluator_sha256"]})

    def produce(self):
        return selection.produce_selection(str(self.regpath), self.regsha,
            str(self.summary), self.summary_sha, str(self.outer), self.outer_sha,
            {u: (str(p), selection.sha256(p)) for u, p in self.result_paths.items()},
            str(self.d / "selection.json"))

    def test_current_result_shape_and_validator(self):
        record = self.produce()
        out = self.d / "selection.json"
        validated = selection.validate_selection_record(str(out), selection.sha256(out),
            str(self.regpath), self.regsha,
            {u: (str(p), selection.sha256(p)) for u, p in self.result_paths.items()})
        self.assertEqual(validated["winner_update"], 348)
        self.assertEqual(record["confirmation_status"], "no_confirmation")
        self.assertFalse(record["invocable_confirmation_record"])

    def test_wrong_summary_winner_rejected(self):
        self.refresh(180)
        with self.assertRaisesRegex(ValueError, "row argmax"):
            self.produce()

    def test_wrong_1024_count_rejected(self):
        result = self.results[180]
        result["rows"] = result["rows"][:-1]
        result["episodes"] = 1023
        self.refresh()
        with self.assertRaisesRegex(ValueError, "episodes"):
            self.produce()

    def test_stale_registration_hash_rejected(self):
        self.results[180]["registration_sha256"] = "0" * 64
        self.refresh()
        with self.assertRaisesRegex(ValueError, "registration_sha256"):
            self.produce()

    def test_mean_mismatch_rejected(self):
        self.results[180]["performance"]["mean"] += 1
        self.refresh()
        with self.assertRaisesRegex(ValueError, "performance mismatch: mean"):
            self.produce()

    def test_tie_chooses_earlier_update(self):
        for result in self.results.values():
            for row in result["rows"]:
                row["alive_frames"] = 700
                row["gameplay_frames"] = 701
                row["objective_return"] = 2
            result["performance"] = {"worst": 700, "q1_bottom_quarter_mean": 700.0,
                "mean": 700.0, "q4_top_quarter_mean": 700.0, "best": 700}
        self.refresh(180)
        self.assertEqual(self.produce()["winner_update"], 180)

    def test_tampered_selection_winner_rejected(self):
        self.produce()
        out = self.d / "selection.json"
        record = json.loads(out.read_text())
        record["winner_update"] = 180
        write(out, record)
        with self.assertRaisesRegex(ValueError, "refs/winner"):
            selection.validate_selection_record(str(out), selection.sha256(out),
                str(self.regpath), self.regsha,
                {u: (str(p), selection.sha256(p)) for u, p in self.result_paths.items()})

    def tearDown(self):
        self.tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
