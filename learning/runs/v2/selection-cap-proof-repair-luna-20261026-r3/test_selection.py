import json
import tempfile
import unittest
from pathlib import Path

import selection


def write(path, value):
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    return selection.sha256(path)


def row(i, alive, capped=False):
    score_raw = 65536
    return {"episode_index": i, "seed": selection.SEEDS[i], "score_raw_fixed": score_raw,
            "score_delta_sum_raw_fixed": score_raw, "score": 1.0,
            "objective_return": 1 + alive / 100 - (0 if capped else 5),
            "alive_frames": alive, "gameplay_frames": alive if capped else alive + 1,
            "startup_frames": 13, "terminated": not capped, "truncated": capped,
            "death_cause": None if capped else "normal_enemy",
            "fatal_gameplay_frame": None if capped else alive + 1,
            "death_observed_lethal_contacts": None if capped else {
                cause: (1 if cause == "normal_enemy" else 0) for cause in selection.DEATH_CAUSES[:-1]}}


def make_result(update, alive, reg_sha, checkpoint, cohort_sha, caps=0):
    rows = [row(i, selection.CAP if i < caps else alive, i < caps)
            for i in range(1024)]
    values = [r["alive_frames"] for r in rows]
    ordered, q = sorted(values), len(values) // 4
    return {"schema": "expanded_D2_candidate_evaluation_v1", "complete": True,
            "registration_sha256": reg_sha, "candidate_update": update,
            "checkpoint_sha256": checkpoint, "cohort_name": "ranking",
            "cohort_sha256": cohort_sha, "episodes": 1024, "caps": caps,
            "death_causes": {cause: (1024 - caps if cause == "normal_enemy" else 0)
                             for cause in selection.DEATH_CAUSES},
            "performance": {"worst": ordered[0], "q1_bottom_quarter_mean": sum(ordered[:q]) / q,
                "mean": sum(values) / len(values), "q4_top_quarter_mean": sum(ordered[-q:]) / q,
                "best": ordered[-1]},
            "elapsed_seconds": 1.25, "rows": rows, "model_state_dict_sha256": "m" * 64,
            "backend": "cpu"}


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.manifest = self.d / "manifest.json"
        self.cohort_sha = write(self.manifest, {"count": 1024, "seeds": list(selection.SEEDS)})
        self.pins = {u: "%064x" % u for u in selection.UPDATES}
        self.reg = {"schema": "expanded_D2_evaluation_registration_v1", "mode": "ranking",
            "run_id": "synthetic-rank-run", "source": {"evaluator_sha256": "e" * 64,
            "worker_sha256": "w" * 64}, "runtime": {"backend": "cpu", "member_sha256": {
            "member-%02d" % i: "%064x" % i for i in range(13)}},
            "candidates": {str(u): {"phase_update": u, "checkpoint_sha256": self.pins[u],
                "checkpoint_path": "/synthetic/checkpoint-%d" % u,
                "source_receipt_path": "/synthetic/receipt-%d" % u,
                "source_receipt_sha256": "s" * 64} for u in selection.UPDATES},
            "cohorts": {"ranking": {"manifest_path": str(self.manifest),
                "manifest_sha256": self.cohort_sha, "count": 1024}}}
        self.regpath = self.d / "registration.json"
        self.regsha = write(self.regpath, self.reg)
        self.paths, self.results = {}, {}
        self.caps = 1
        for update in selection.UPDATES:
            path = self.d / ("candidate-%d.json" % update)
            result = make_result(update, 1000 + update, self.regsha, self.pins[update],
                                 self.cohort_sha, self.caps)
            self.paths[update], self.results[update] = path, result
        self.summary, self.outer = self.d / "summary.json", self.d / "outer.json"
        self.refresh()

    def bindings(self):
        return {u: (str(p), selection.sha256(p)) for u, p in self.paths.items()}

    def refresh(self, winner=None):
        for u, path in self.paths.items():
            write(path, self.results[u])
        if winner is None:
            winner = max(selection.UPDATES,
                         key=lambda u: (self.results[u]["performance"]["mean"], -u))
        self.summary_sha = write(self.summary, {"schema": selection.RANKING_SCHEMA,
            "selection_only": True, "winner_update": winner,
            "candidate_results": [self.results[u] for u in selection.UPDATES]})
        artifacts = [{"path": str(self.summary.resolve()), "sha256": self.summary_sha}]
        artifacts += [{"path": str(self.paths[u].resolve()), "sha256": selection.sha256(self.paths[u])}
                      for u in selection.UPDATES]
        self.outer_sha = write(self.outer, {"schema": "expanded_eval_outer_receipt_v1",
            "run_id": self.reg["run_id"], "registration_sha256": self.regsha,
            "stage": "ranking", "candidate_update": 348, "cohort": "ranking",
            "raw_exit_code": 0, "stop_reason": None, "process_group_absent": True,
            "output_artifacts": artifacts, "worker_sha256": self.reg["source"]["worker_sha256"],
            "evaluator_sha256": self.reg["source"]["evaluator_sha256"]})

    def produce(self, output=None):
        return selection.produce_selection(str(self.regpath), self.regsha, str(self.summary),
            self.summary_sha, str(self.outer), self.outer_sha, self.bindings(),
            str(output or self.d / "selection.json"))

    def validate(self, record_path=None, record_sha=None):
        record_path = record_path or self.d / "selection.json"
        return selection.validate_selection_record(str(record_path), record_sha or selection.sha256(record_path),
            str(self.regpath), self.regsha, str(self.summary), self.summary_sha,
            str(self.outer), self.outer_sha, self.bindings())

    def test_cap_record_replays_full_proof_chain(self):
        record = self.produce()
        self.assertEqual(record["winner_update"], 348)
        self.assertEqual(record["ranking_summary_sha256"], self.summary_sha)
        self.assertEqual(record["outer_receipt_sha256"], self.outer_sha)
        self.assertEqual(self.validate(), record)

    def test_all_1024_seeds_are_ordered_and_valid(self):
        result = self.results[180]
        self.assertEqual([r["seed"] for r in result["rows"]], list(selection.SEEDS))
        result["rows"][512], result["rows"][513] = result["rows"][513], result["rows"][512]
        self.refresh()
        with self.assertRaisesRegex(ValueError, "seed"):
            self.produce()

    def test_wrong_flags_frame_and_telemetry_rejected(self):
        mutations = [
            (lambda r: r.update(terminated=False), "boundary flags"),
            (lambda r: r.update(gameplay_frames=r["alive_frames"]), "fatal-frame"),
            (lambda r: r.update(fatal_gameplay_frame=None), "telemetry"),
            (lambda r: r.update(death_observed_lethal_contacts=None), "telemetry"),
        ]
        for mutate, message in mutations:
            with self.subTest(message=message):
                self.tearDown()
                self.setUp()
                mutate(self.results[180]["rows"][2])
                self.refresh()
                with self.assertRaisesRegex(ValueError, message):
                    self.produce()

    def test_invalid_cap_frames_and_flags_rejected(self):
        r = self.results[180]["rows"][0]
        r["gameplay_frames"] = selection.CAP + 1
        self.refresh()
        with self.assertRaisesRegex(ValueError, "raw frame bound"):
            self.produce()

    def test_outer_status_and_artifact_binding_rejected(self):
        record = self.produce()
        outer = json.loads(self.outer.read_text())
        outer["raw_exit_code"] = 1
        self.outer_sha = write(self.outer, outer)
        with self.assertRaisesRegex(ValueError, "outer receipt"):
            self.validate(record_sha=selection.sha256(self.d / "selection.json"))
        self.refresh()
        record = self.produce(self.d / "other.json")
        outer = json.loads(self.outer.read_text())
        outer["output_artifacts"].pop()
        self.outer_sha = write(self.outer, outer)
        with self.assertRaisesRegex(ValueError, "does not bind candidate"):
            self.validate(self.d / "other.json", selection.sha256(self.d / "other.json"))

    def test_summary_drift_and_wrong_winner_rejected(self):
        out = self.d / "selection.json"
        self.produce()
        self.refresh(180)
        with self.assertRaisesRegex(ValueError, "row argmax"):
            self.validate(out, selection.sha256(out))

    def test_metrics_tie_stale_registration_and_count(self):
        self.results[180]["performance"]["mean"] += 1
        self.refresh()
        with self.assertRaisesRegex(ValueError, "performance mismatch"):
            self.produce()
        for result in self.results.values():
            for i, r in enumerate(result["rows"]):
                result["rows"][i] = row(i, 700)
            result["caps"] = 0
            result["death_causes"] = {cause: (1024 if cause == "normal_enemy" else 0)
                                       for cause in selection.DEATH_CAUSES}
            result["performance"] = {"worst": 700, "q1_bottom_quarter_mean": 700,
                "mean": 700, "q4_top_quarter_mean": 700, "best": 700}
        self.refresh(180)
        self.assertEqual(self.produce(self.d / "tie.json")["winner_update"], 180)
        self.results[180]["registration_sha256"] = "0" * 64
        self.refresh()
        with self.assertRaisesRegex(ValueError, "registration_sha256"):
            self.produce(self.d / "stale.json")
        self.tearDown()
        self.setUp()
        self.results[180]["rows"].pop()
        self.refresh()
        with self.assertRaisesRegex(ValueError, "episode count"):
            self.produce(self.d / "count.json")

    def test_348_winner_stays_noninvocable_and_collision_preserves_bytes(self):
        out = self.d / "collision.json"
        out.write_bytes(b"preserve-me\n")
        with self.assertRaises(FileExistsError):
            self.produce(out)
        self.assertEqual(out.read_bytes(), b"preserve-me\n")
        for u in selection.UPDATES:
            self.results[u] = make_result(u, 1000 + u, self.regsha, self.pins[u], self.cohort_sha)
        self.refresh(348)
        record = self.produce(self.d / "incumbent.json")
        self.assertEqual(record["winner_update"], 348)
        self.assertEqual(record["confirmation_status"], "no_confirmation")
        self.assertFalse(record["invocable_confirmation_record"])

    def tearDown(self):
        self.tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
