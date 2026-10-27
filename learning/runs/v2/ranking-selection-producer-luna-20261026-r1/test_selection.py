import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import selection


def write(path, value):
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def result(update, score, pins, identities):
    rows = []
    for i, seed in enumerate(selection.SEEDS):
        alive = min(selection.CAP, score)
        rows.append({"seed": seed, "episode_index": i, "alive_frames": alive,
                     "gameplay_frames": alive + 1, "score_raw_fixed": 0, "score": 0,
                     "objective_return": alive / 100 - 5, "terminated": True,
                     "truncated": False, "death_cause": "synthetic"})
    perf = selection._performance([r["alive_frames"] for r in rows])
    return {"schema": "expanded_D2_candidate_evaluation_v1", "complete": True,
            "candidate_update": update, "checkpoint_sha256": pins[update],
            "cohort_name": "ranking", "cohort_sha256": identities["cohort"],
            "episodes": 1024, "performance": perf, "rows": rows,
            "registration_sha256": identities["registration"],
            "evaluator_sha256": identities["evaluator"],
            "runtime_sha256": identities["runtime"],
            "manifest_sha256": identities["manifest"]}


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.pins = {u: ("%064x" % u) for u in selection.UPDATES}
        self.ident = {"evaluator": "e" * 64, "runtime": "r" * 64,
                      "cohort": "c" * 64, "manifest": "m" * 64}
        self.reg = {"run_id": "synthetic-run", "candidates": {str(u): {"checkpoint_sha256": self.pins[u]} for u in selection.UPDATES}}
        self.reg_path = self.d / "registration.json"
        self.reg_pin = write(self.reg_path, self.reg)
        self.ident["registration"] = self.reg_pin
        self.paths, self.summaries, self.means = {}, [], {}
        for update in selection.UPDATES:
            path = self.d / ("result-%s.json" % update)
            value = result(update, update, self.pins, self.ident)
            pin = write(path, value)
            self.paths[update] = (str(path), pin)
            self.summaries.append({"candidate_update": update, "checkpoint_sha256": self.pins[update], "performance": value["performance"]})
            self.means[update] = value["performance"]["mean"]
        self.outer_path = self.d / "outer.json"
        self.outer_pin = write(self.outer_path, {"raw_exit_code": 0, "stop_reason": None,
            "process_group_absent": True, "registration_sha256": self.reg_pin,
            "evaluator_sha256": self.ident["evaluator"], "runtime_sha256": self.ident["runtime"]})

    def produce(self, winner, scores=None):
        if scores:
            self.paths.clear(); self.summaries.clear(); self.means.clear()
            for update in selection.UPDATES:
                path = self.d / ("result-%s.json" % update)
                value = result(update, scores[update], self.pins, self.ident)
                pin = write(path, value); self.paths[update] = (str(path), pin)
                self.summaries.append({"candidate_update": update, "checkpoint_sha256": self.pins[update], "performance": value["performance"]})
                self.means[update] = value["performance"]["mean"]
        bundle = self.d / "bundle.json"
        write(bundle, {"schema": selection.SCHEMA, "selection_only": True,
                       "winner_update": winner, "candidate_results": self.summaries})
        output = self.d / "selection.json"
        return selection.produce_selection(str(bundle), selection.sha256(bundle),
            str(self.reg_path), self.reg_pin, str(self.outer_path), self.outer_pin,
            self.paths, self.ident["evaluator"], self.ident["runtime"], self.ident["cohort"],
            self.ident["manifest"], str(output)), output

    def test_bundle_to_record_and_validator(self):
        record, output = self.produce(348)
        validated = selection.validate_selection_record(str(output), selection.sha256(output),
            str(self.reg_path), self.reg_pin, self.paths, "synthetic-run",
            self.ident["evaluator"], self.ident["runtime"], self.ident["cohort"], self.ident["manifest"])
        self.assertEqual(validated["winner_update"], 348)
        self.assertEqual(record["confirmation_status"], "no_confirmation")
        self.assertFalse(record["invocable_confirmation_record"])

    def test_rejects_wrong_bundle_winner(self):
        with self.assertRaisesRegex(ValueError, "recomputed argmax"):
            self.produce(180)

    def test_tie_chooses_earlier_phase(self):
        scores = {u: 700 for u in selection.UPDATES}
        record, _ = self.produce(180, scores)
        self.assertEqual(record["winner_update"], 180)

    def test_validator_rejects_tampered_winner(self):
        record, output = self.produce(348)
        record["winner_update"] = 180
        write(output, record)
        with self.assertRaisesRegex(ValueError, "recomputed argmax"):
            selection.validate_selection_record(str(output), selection.sha256(output),
                str(self.reg_path), self.reg_pin, self.paths, "synthetic-run",
                self.ident["evaluator"], self.ident["runtime"], self.ident["cohort"], self.ident["manifest"])

    def tearDown(self):
        self.tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
