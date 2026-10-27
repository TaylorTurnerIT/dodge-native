"""Cross-interface normal iteration regressions; no game stepping or PPO."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import runner as r
import execute_once as e
from test_contract import registration, make_outputs, full_worker, HERE
from test_contract import FakeProcess, completed


class NormalIteration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=HERE, prefix="normal-contract-")
        self.reg = registration(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_complete_below_competence_is_normal_completion(self):
        make_outputs(self.reg)
        evidence = e.validate_outputs(self.reg, full_worker(), "a" * 64)
        self.assertFalse(evidence["competence_passed"])
        self.assertEqual(evidence["updates_checked"], 72)
        self.assertEqual(evidence["cumulative_counters"]["updates"], 120)

    def test_checkpoint_digest_is_not_registration_digest(self):
        out = make_outputs(self.reg)
        digest = r.sha(out / "checkpoint-000072-candidate.pt")
        self.assertNotEqual(digest, "a" * 64)
        e.validate_outputs(self.reg, full_worker(), "a" * 64)
        with self.assertRaisesRegex(ValueError, "frozen identity"):
            e.validate_outputs(self.reg, full_worker(), digest)

    def test_wrong_future_seed_indices_and_missing_episode_frames_fail(self):
        out = make_outputs(self.reg)
        worker = full_worker(); worker["final_resume_next_episode_indices"] = [5] * 64
        with self.assertRaisesRegex(ValueError, "resume seed"):
            e.validate_outputs(self.reg, worker, "a" * 64)
        records = [json.loads(line) for line in (out / "training-episodes.jsonl").read_text().splitlines()]
        records[1]["info"]["gameplay_frames"] += 1
        (out / "training-episodes.jsonl").write_text("\n".join(json.dumps(v) for v in records))
        with self.assertRaisesRegex(ValueError, "conservation"):
            e.validate_outputs(self.reg, full_worker(), "a" * 64)

    def test_actual_recorded_initial_completion_reset_contract(self):
        source = HERE.parent / "critic-diagnostic-D2-20261025-r2/training-episodes.jsonl"
        records = [json.loads(line) for line in source.read_text().splitlines()]
        initial = next(row for row in records if row["kind"] == "initial")
        completion = next(row["info"] for row in records if row["kind"] == "completed")
        reset = next(row["info"] for row in records if row["kind"] == "reset")
        events = r.ordered_episode_events([completion], [reset], 1)
        result = r.validate_episode_journal([initial] + events)
        self.assertEqual(initial["batch_info"]["next_episode_indices"], [1] * 64)
        self.assertEqual(result["next_episode_indices"][completion["seed"]["slot"]], 2)
        self.assertEqual(events[1]["info"]["indices"], reset["indices"])

    def test_multiple_same_slot_episodes_merge_chronologically(self):
        initial = {"kind": "initial", "info": [{"seed": {"slot": i, "episode": 0}} for i in range(64)],
                   "batch_info": {"next_episode_indices": [1] * 64}}
        completions = [{"rollout_step": step, "seed": {"slot": 0, "episode": ep}}
                       for step, ep in [(80, 1), (40, 0)]]
        resets = [{"rollout_step": step, "indices": [0], "info": [{"seed": {"slot": 0, "episode": ep}}]}
                  for step, ep in [(80, 2), (40, 1)]]
        events = r.ordered_episode_events(completions, resets, 1)
        result = r.validate_episode_journal([initial] + events)
        self.assertEqual(result["next_episode_indices"], [3] + [1] * 63)
        with self.assertRaises(ValueError):
            r.validate_episode_journal([initial] + events[:-1])
        bad = copy.deepcopy(events); bad[1]["info"]["info"][0]["seed"]["episode"] = 3
        with self.assertRaises(ValueError):
            r.validate_episode_journal([initial] + bad)
        with self.assertRaises(ValueError):
            r.validate_episode_journal([initial] + events[:1] + events)

    def test_global_cache_policy_matches_actual_process(self):
        import os
        reg = {"import_policy": {"pycache_prefix": os.environ["PYTHONPYCACHEPREFIX"]}}
        r.check_import_cache(reg)
        with self.assertRaises(ValueError):
            r.check_import_cache({"import_policy": {"pycache_prefix": ""}})

    def test_second_launch_cannot_rewrite_completed_evidence(self):
        out = Path(self.reg["output"]); out.mkdir(parents=True)
        r.save(out / "launch-marker.json", {"single_use": True})
        r.save(out / "execution-result.json", {"status": "passed", "immutable": True})
        regpath = Path(self.temp.name) / "registration.json"
        regpath.write_text(json.dumps(self.reg))
        before = {path.name: path.read_bytes() for path in out.iterdir()}
        with self.assertRaises(FileExistsError):
            e.execute(regpath, "a" * 64)
        self.assertEqual(before, {path.name: path.read_bytes() for path in out.iterdir()})

    def test_launcher_allows_worker_finalization_after_work_deadline(self):
        out = Path(self.reg["output"]); out.mkdir(parents=True)
        r.save(out / "worker-result.json", completed())
        regpath = Path(self.temp.name) / "registration.json"
        regpath.write_text(json.dumps(self.reg))
        now = [0.]
        process = FakeProcess()
        polls = iter([None, 0, 0, 0, 0, 0, 0])
        process.poll = lambda: next(polls, 0)
        def spawn(*args, **kwargs):
            now[0] = 1601.
            return process
        with patch.object(r, "load_registration", return_value=(self.reg, {})), \
             patch.object(r, "check_lease"), patch.object(e, "group_exists", return_value=False), \
             patch.object(e, "validate_outputs", return_value={"updates_checked": 72}), \
             patch.object(e, "stop_owned") as stop:
            code = e.execute(regpath, "a" * 64, clock=lambda: now[0], popen=spawn,
                             sleep=lambda _: now.__setitem__(0, 1602.))
        self.assertEqual(code, 0)
        stop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
