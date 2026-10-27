from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import pathlib
import sys
import unittest

import torch

ROOT = pathlib.Path(__file__).resolve().parents[4]
RUNS = ROOT / "learning/runs/v2"
OUT = RUNS / "D2-retained300-runner-luna-20261026-r5"
PARENT = RUNS / "D2-retained276-lr3em5-20261026-r2"
AUDIT = RUNS / "D2-retained276-lr3em5-parent-terminal-audit-20261026-r2"
PREP = OUT
RUNTIME = RUNS / "D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime"
sys.path.insert(0, str(OUT))
sys.path.insert(0, str(RUNTIME))
sys.path.insert(0, str(PREP))
import parent_adapter as adapter
from dodge_rl.checkpoints import load_checkpoint
from dodge_rl.models.teacher import OmniscientEntityTeacher


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load_module("successor_runner", PREP / "runner.py")
fingerprint = runner.fingerprint
CHECKPOINT = PARENT / "checkpoint-000300-candidate.pt"
SELECTED_PATH = AUDIT / "retained-best-candidate-receipt.json"
COST_PATH = AUDIT / "completed-iteration-receipt.json"
META_PATH = PARENT / "checkpoint-000300-candidate.pt.json"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


class ParentAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(min(torch.get_num_threads(), 2))
        cls.state = load_checkpoint(CHECKPOINT, expected_sha256=adapter.CHECKPOINT_SHA)
        cls.receipt = json.loads(SELECTED_PATH.read_text())
        cls.cost = json.loads(COST_PATH.read_text())
        cls.metadata = json.loads(META_PATH.read_text())
        cls.metadata_sha = sha(META_PATH)

    def validate(self, state=None, receipt=None, checkpoint_sha=None,
                 receipt_sha=None, metadata=None, metadata_sha=None):
        return adapter.validate_parent(
            state if state is not None else self.state,
            checkpoint_sha if checkpoint_sha is not None else adapter.CHECKPOINT_SHA,
            receipt if receipt is not None else self.receipt,
            receipt_sha if receipt_sha is not None else adapter.RECEIPT_SHA,
            fingerprint,
            metadata if metadata is not None else self.metadata,
            metadata_sha if metadata_sha is not None else self.metadata_sha,
            self.cost, adapter.COST_RECEIPT_SHA,
        )

    def test_positive_exact_cpu_decoded_inputs_and_restore(self):
        self.assertEqual(sha(CHECKPOINT), adapter.CHECKPOINT_SHA)
        self.assertEqual(sha(SELECTED_PATH), adapter.RECEIPT_SHA)
        self.assertEqual(sha(COST_PATH), adapter.COST_RECEIPT_SHA)
        self.assertIs(self.validate(), self.state)
        self.assertIs(adapter.validate_cost_anchor(self.cost, adapter.COST_RECEIPT_SHA), self.cost)
        model = OmniscientEntityTeacher().cpu()
        optimizer = torch.optim.Adam(model.parameters(), lr=3e-5, eps=1e-5)
        model.load_state_dict(self.state["model"], strict=True)
        optimizer.load_state_dict(self.state["optimizer"])
        self.assertEqual(fingerprint(model.state_dict()), self.receipt["learner_fingerprints"]["model"])
        self.assertEqual(fingerprint(optimizer.state_dict()), self.receipt["learner_fingerprints"]["optimizer"])
        self.assertTrue(all(g["lr"] == 3e-5 and g["eps"] == 1e-5 for g in optimizer.param_groups))
        self.assertEqual(fingerprint(self.state["rng"]), self.receipt["learner_fingerprints"]["rng"])
        self.assertEqual(self.state["rng"]["sampling_backend"], "torch_global_mps")

    def test_wrong_parent_pins_schema_status_and_metadata(self):
        for kwargs in (
            {"checkpoint_sha": "0" * 64}, {"receipt_sha": "0" * 64},
            {"metadata_sha": "0" * 64},
            {"metadata": {**self.metadata, "training_eligible": True}},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.validate(**kwargs)
        for key, value in (("schema", "wrong"), ("status", "wrong"),
                           ("training_continuation_eligible", False),
                           ("stage_promotion_eligible", True), ("competence_passed", True),
                           ("checkpoint_metadata_unchanged", False)):
            receipt = copy.deepcopy(self.receipt); receipt[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.validate(receipt=receipt)
        for key, value in (("schema", "wrong"), ("status", "wrong"),
                           ("training_continuation_eligible", True),
                           ("stage_promotion_eligible", True), ("competence_passed", True),
                           ("checkpoint_metadata_unchanged", False)):
            cost = copy.deepcopy(self.cost); cost[key] = value
            with self.subTest(cost_key=key), self.assertRaises(ValueError):
                adapter.validate_cost_anchor(cost, adapter.COST_RECEIPT_SHA)

    def test_counter_lineage_and_update_mutations(self):
        for path, mutate in (
            (("phase_update",), lambda s: s.__setitem__("phase_update", 336)),
            (("local_update",), lambda s: s.__setitem__("local_update", 60)),
            (("cumulative_counters", "updates"), lambda s: s["cumulative_counters"].__setitem__("updates", 384)),
            (("parent_checkpoint_sha256",), lambda s: s.__setitem__("parent_checkpoint_sha256", adapter.CHECKPOINT_SHA)),
            (("update_progress", "complete"), lambda s: s["update_progress"].__setitem__("complete", False)),
            (("counters", "optimizer_steps"), lambda s: s["counters"].__setitem__("optimizer_steps", 3073)),
            (("inherited_counters", "raw_frames"), lambda s: s["inherited_counters"].__setitem__("raw_frames", 1)),
            (("next_episode_indices", 0), lambda s: s["next_episode_indices"].__setitem__(0, -1)),
            (("config_sha256",), lambda s: s.__setitem__("config_sha256", "0" * 64)),
            (("runtime_sha256",), lambda s: s.__setitem__("runtime_sha256", "0" * 64)),
            (("native_sha256",), lambda s: s.__setitem__("native_sha256", "0" * 64)),
            (("policy_sha256",), lambda s: s.__setitem__("policy_sha256", "0" * 64)),
            (("registration_sha256",), lambda s: s.__setitem__("registration_sha256", "0" * 64)),
            (("cumulative_selected_checkpoint_trajectory_wall_seconds",), lambda s: s.__setitem__("cumulative_selected_checkpoint_trajectory_wall_seconds", 1)),
            (("current_iteration_observed_outer_seconds",), lambda s: s.__setitem__("current_iteration_observed_outer_seconds", 1)),
            (("parent_completed_campaign_cost_baseline_seconds",), lambda s: s.__setitem__("parent_completed_campaign_cost_baseline_seconds", 1)),
            (("cumulative_successful_ancestor_and_completed_campaign_cost_seconds",), lambda s: s.__setitem__("cumulative_successful_ancestor_and_completed_campaign_cost_seconds", 1)),
        ):
            state = copy.deepcopy(self.state); mutate(state)
            with self.subTest(path=path), self.assertRaises(ValueError): self.validate(state=state)

    def test_metadata_hash_and_fingerprint_payload_mutations(self):
        for name, mutate in (
            ("model", lambda s: s["model"].__setitem__(next(iter(s["model"])),
                 s["model"][next(iter(s["model"]))] + 1)),
            ("optimizer", lambda s: s["optimizer"]["state"][next(iter(s["optimizer"]["state"]))]["step"].add_(1)),
            ("adam_moment", lambda s: s["optimizer"]["state"][next(iter(s["optimizer"]["state"]))]["exp_avg"].add_(1)),
            ("epsilon", lambda s: s["optimizer"]["param_groups"][0].__setitem__("eps", 2e-5)),
            ("learning_rate", lambda s: s["optimizer"]["param_groups"][0].__setitem__("lr", 4e-5)),
            ("rng", lambda s: s["rng"]["torch_cpu"].__setitem__(0, 0)),
        ):
            state = copy.deepcopy(self.state); mutate(state)
            with self.subTest(payload=name), self.assertRaises(ValueError): self.validate(state=state)
        meta = dict(self.metadata); meta["promoted"] = True
        with self.assertRaises(ValueError): self.validate(metadata=meta)

    def test_cost_anchor_exact_fields_and_mutations(self):
        self.assertIs(adapter.validate_cost_anchor(self.cost, adapter.COST_RECEIPT_SHA), self.cost)
        for sha_value in ("0" * 64, adapter.COST_RECEIPT_SHA):
            if sha_value == adapter.COST_RECEIPT_SHA:
                continue
            with self.assertRaises(ValueError): adapter.validate_cost_anchor(self.cost, sha_value)
        mutations = (
            ("schema", "d2_completed_training_iteration_receipt_v1"),
            ("status", "accepted_completed_training_iteration_no_best_replacement"),
            ("completed_phase_updates", 300),
            ("completed_local_updates", 24),
            ("cumulative_counters", {"updates": 348}),
            ("training_continuation_eligible", True),
        )
        for key, value in mutations:
            cost = copy.deepcopy(self.cost); cost[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                adapter.validate_cost_anchor(cost, adapter.COST_RECEIPT_SHA)
        for key, value in (("completed_campaign_resource_cost_before_seconds", 1),
                           ("completed_campaign_resource_cost_after_seconds", 1),
                           ("selected_checkpoint_future_baseline_seconds", 1)):
            cost = copy.deepcopy(self.cost); cost["wall_accounting"][key] = value
            with self.subTest(clock=key), self.assertRaises(ValueError):
                adapter.validate_cost_anchor(cost, adapter.COST_RECEIPT_SHA)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class SuccessorRunnerTests(ParentAdapterTests):
    def test_three_argument_restore_api_and_selected_point_rejections(self):
        runner._PARENT_METADATA_PATH = str(META_PATH.resolve())
        runner._PARENT_COST_RECEIPT_PATH = str(COST_PATH.resolve())
        self.assertIs(runner.validate_parent_checkpoint_for_restore(
            self.state, adapter.CHECKPOINT_SHA, self.receipt), self.state)
        for key, value in (("candidate_phase_update", 336), ("candidate_local_update", 60),
                           ("checkpoint_sha256", "0" * 64)):
            receipt = copy.deepcopy(self.receipt); receipt[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                runner.validate_parent_checkpoint_for_restore(self.state, adapter.CHECKPOINT_SHA, receipt)
        state = copy.deepcopy(self.state)
        state["current_iteration_observed_outer_seconds"] += 1
        with self.assertRaises(ValueError): self.validate(state=state)

    def test_entry_evaluation_and_counter_lineage(self):
        evaluation = json.loads((PARENT / "development-000300.json").read_text())["evaluation"]
        self.assertIsNone(runner.validate_entry_evaluation(evaluation, evaluation))
        mutated = copy.deepcopy(evaluation); mutated["rows"][0]["alive_frames"] += 1
        with self.assertRaises(ValueError): runner.validate_entry_evaluation(evaluation, mutated)
        self.assertEqual(runner.continuation_cumulative_counters(
            self.receipt["candidate_cumulative_counters"],
            {"updates": 60, "optimizer_steps": 7680,
             "environment_decisions": 983040, "raw_frames": 3929095}),
            {"updates": 408, "optimizer_steps": 51104,
             "environment_decisions": 6684672, "raw_frames": 26703198})

    def test_worker_is_real_and_has_no_lr_transition(self):
        source = (OUT / "runner.py").read_text()
        self.assertNotIn("lr_transition", source)
        self.assertNotIn("lr-transition.json", source)
        self.assertNotIn("override", source.lower())
        tree = __import__("ast").parse(source)
        names = {node.name: node for node in tree.body if isinstance(node, __import__("ast").FunctionDef)}
        worker_source = __import__("ast").get_source_segment(source, names["worker"])
        self.assertIn("for update in range(1, NEW_UPDATES + 1)", worker_source)
        self.assertIn("ppo_update(model, optimizer", worker_source)
        self.assertIn("evaluate_at(PHASE_START)", worker_source)
        self.assertEqual(runner.EVALUATION_UPDATES, (300, 312, 324, 336, 348, 360))
        self.assertEqual(runner.LEARNING_RATE, 3e-5)
        self.assertEqual(runner.PARENT_LOCAL_UPDATES, 24)
        self.assertEqual(runner.PARENT_TOTAL_UPDATES, 348)
        self.assertEqual(runner.EXPECTED_TOTAL, 408)

    def test_parent_audit_and_distinct_clocks(self):
        decision = AUDIT / "retained-best-decision.json"
        registration = RUNS / "D2-retained276-lr3em5-prepare-luna-20261026-r2/registration.json"
        evaluation_path = PARENT / "development-000300.json"
        evaluation_jsonl = PARENT / "development-000300.jsonl"
        worker_result = PARENT / "worker-result.json"
        full_audit = RUNS / "D2-retained276-lr3em5-auditor-luna-20261026-r2/full-audit.json"
        audit_path = AUDIT / "audit.json"
        paths = {
            "terminal_receipt_path": SELECTED_PATH,
            "completed_cost_receipt_path": COST_PATH,
            "completed_cost_receipt_sha256": sha(COST_PATH),
            "metadata_path": META_PATH,
            "metadata_sha256": sha(META_PATH),
            "audit_path": audit_path, "audit_sha256": sha(audit_path),
            "full_audit_path": full_audit, "full_audit_sha256": sha(full_audit),
            "producing_worker_result_path": worker_result,
            "producing_worker_result_sha256": sha(worker_result),
            "decision_path": decision, "decision_sha256": sha(decision),
            "registration_path": registration, "registration_sha256": sha(registration),
            "source_evaluation_path": evaluation_path,
            "source_evaluation_sha256": sha(evaluation_path),
            "source_evaluation_jsonl_path": evaluation_jsonl,
            "source_evaluation_jsonl_sha256": sha(evaluation_jsonl),
        }
        receipt = json.loads(SELECTED_PATH.read_text())
        runner.validate_parent_terminal_receipt(receipt, {"parent": {k: str(v) if k.endswith("path") else v for k,v in paths.items()}})
        self.assertEqual(runner._PARENT_CLOCKS, {
            "parent_selected_trajectory": 5190.209660791156,
            "parent_selected_iteration": 430.1472566659795,
            "parent_worker_trajectory_end": 6258.458489500165,
            "parent_worker_campaign_cost": 8617.17817400011,
            "new_selected_trajectory_baseline": 5190.209660791156,
            "new_campaign_cost_baseline": 8621.338345875141,
        })

