"""CPU-only executable controls for retained324 auditor helpers; no continuation outputs read."""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

import audit_candidates as a
import wrapper as w

ROOT = a.ROOT
FREEZE = ROOT / "learning/runs/v2/D2-retained324-continuation-prepare-luna-20261026-r2"
PARENT = ROOT / "learning/runs/v2/D2-retained300-continuation-20261026-r1/checkpoint-000324-candidate.pt"
PARENT_EVAL = ROOT / "learning/runs/v2/D2-retained300-continuation-20261026-r1/development-000324.json"


def load_source(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class AuditorControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        torch.set_num_threads(2)
        cls.schema = load_source("registration_schema", FREEZE / "registration_schema.py")
        cls.adapter = load_source("parent_adapter", FREEZE / "parent_adapter.py")
        cls.runner = load_source("runner_cpu_controls", FREEZE / "runner.py")
        cls.parent = torch.load(PARENT, map_location="cpu", weights_only=False)
        cls.parent_eval = json.loads(PARENT_EVAL.read_text())
        cls.receipt = json.loads(Path(a.REG_PATH).read_text())["parent"]
        cls.reg = json.loads(Path(a.REG_PATH).read_text())

    def ctx(self):
        return {"runner": self.runner, "parent": self.parent}

    def test_real_selected324_parent_decodes_on_cpu_and_matches_frozen_identity(self):
        self.assertEqual(self.parent["phase_update"], 324)
        self.assertEqual(self.parent["local_update"], 24)
        self.assertEqual(self.parent["cumulative_counters"]["updates"], 372)
        self.assertEqual(a.SELECTED_TRAJECTORY_BASELINE, 5678.9823631240915)
        self.assertEqual(a.CAMPAIGN_COST_BASELINE, 9758.365427209174)
        self.assertNotEqual(self.parent["cumulative_successful_ancestor_and_completed_campaign_cost_seconds"], a.CAMPAIGN_COST_BASELINE)
        self.assertEqual(self.runner.fingerprint(self.parent["model"]), self.runner.fingerprint(self.parent["model"]))
        self.assertEqual(a.choose_best({324: a.BASELINE_MEAN_ALIVE, 336: a.BASELINE_MEAN_ALIVE}), 324)

    def test_entry_requires_exact_model_adam_rng_from_selected324(self):
        entry = copy.deepcopy(self.parent)
        entry.update(phase_update=324, local_update=0)
        a.validate_entry_state(self.ctx(), entry)
        for component in ("model", "optimizer", "rng"):
            bad = copy.deepcopy(entry)
            bad[component] = {} if isinstance(bad[component], dict) else ["wrong-parent"]
            with self.subTest(component=component), self.assertRaises(a.AuditError):
                a.validate_entry_state(self.ctx(), bad)
        later = copy.deepcopy(entry)
        later["phase_update"] = 336
        later["model"] = {}
        with self.assertRaises(a.AuditError):
            a.validate_entry_state(self.ctx(), later)

    def test_new_clock_baselines_are_distinct_and_stale_clock_rejected(self):
        current = 100.0
        state = {"current_iteration_observed_outer_seconds": current,
            "cumulative_selected_checkpoint_trajectory_wall_seconds": a.SELECTED_TRAJECTORY_BASELINE + current,
            "cumulative_successful_ancestor_and_completed_campaign_cost_seconds": a.CAMPAIGN_COST_BASELINE + current,
            "selected_parent_checkpoint_trajectory_baseline_seconds": a.SELECTED_TRAJECTORY_BASELINE,
            "parent_completed_campaign_cost_baseline_seconds": a.CAMPAIGN_COST_BASELINE}
        a.validate_wall(state, 12)
        stale = copy.deepcopy(state)
        stale["cumulative_selected_checkpoint_trajectory_wall_seconds"] += 1
        with self.assertRaises(a.AuditError): a.validate_wall(stale, 12)

    def test_selected_parent_mismatch_rejected_by_frozen_adapter(self):
        receipt = json.loads(Path(self.reg["parent"]["terminal_receipt_path"]).read_text())
        self.runner.validate_parent_terminal_receipt(receipt, self.reg)
        self.runner._PARENT_METADATA_PATH = self.reg["parent"]["metadata_path"]
        self.runner._PARENT_COST_RECEIPT_PATH = self.reg["parent"]["completed_cost_receipt_path"]
        self.runner.validate_parent_checkpoint_for_restore(self.parent, a.PARENT_SHA, receipt)
        wrong = copy.deepcopy(self.parent)
        wrong["phase_update"] = 336
        with self.assertRaises((ValueError, RuntimeError)):
            self.runner.validate_parent_checkpoint_for_restore(wrong, a.PARENT_SHA, receipt)

    def test_entry_restoration_receipt_cannot_cover_fake_candidate(self):
        ctx = self.ctx()
        real = {"matched": {"model": True, "Adam": True, "RNG": True}, "parent_sha256": a.PARENT_SHA,
                "components": {k: {"expected_sha256": self.runner.fingerprint(v),
                    "restored_sha256": self.runner.fingerprint(v), "matched": True}
                    for k, v in (("model", self.parent["model"]), ("Adam", self.parent["optimizer"]), ("RNG", self.parent["rng"]))}}
        a.audit_entry_restoration(ctx, real)
        fake = copy.deepcopy(real)
        fake["components"]["Adam"]["restored_sha256"] = "0" * 64
        with self.assertRaises(a.AuditError):
            a.audit_entry_restoration(ctx, fake)
        candidate = copy.deepcopy(self.parent)
        candidate.update(phase_update=324, local_update=0)
        candidate["optimizer"] = {}
        with self.assertRaises(a.AuditError):
            a.validate_entry_state(ctx, candidate)

    def test_raw_frame_conservation_negative_control(self):
        runner = type("Runner", (), {"validate_episode_journal": staticmethod(lambda rows, indices: {
            "next_episode_indices": [1] * 64, "current_episode_indices": {i: 0 for i in range(64)}})})()
        ctx = {"runner": runner, "parent": {"next_episode_indices": [0] * 64,
            "abandoned_current_episodes": [{"slot": i, "seed": {"slot": i, "episode": 0}, "gameplay_frames": 1} for i in range(64)]},
            "journal": [{"kind": "abandoned_parent_episode", "info": {"slot": i}, "reason": "fresh_environment_at_saved_next_episode_index",
                         "parent_checkpoint_sha256": a.PARENT_SHA} for i in range(64)] +
                       [{"kind": "completed", "phase_update": 336, "info": {"gameplay_frames": 2}}]}
        state = {"next_episode_indices": [1] * 64,
            "abandoned_current_episodes": [{"slot": i, "seed": {"slot": i, "episode": 0}, "gameplay_frames": 1} for i in range(64)],
            "counters": {"raw_frames": 66}}
        # Call actual helper with 64 exact parent records and a conserved synthetic prefix.
        parent_abandoned = ctx["parent"]["abandoned_current_episodes"]
        ctx["parent"]["abandoned_current_episodes"] = copy.deepcopy(state["abandoned_current_episodes"])
        ctx["parent"]["next_episode_indices"] = [0] * 64
        ctx["journal"][0:64] = [{"kind": "abandoned_parent_episode", "info": item,
            "reason": "fresh_environment_at_saved_next_episode_index", "parent_checkpoint_sha256": a.PARENT_SHA}
            for item in parent_abandoned]
        a.validate_resume(ctx, 336, state)
        bad = copy.deepcopy(state); bad["counters"]["raw_frames"] += 1
        with self.assertRaises(a.AuditError):
            a.validate_resume(ctx, 336, bad)

    def test_metric_gradient_coverage_and_stale_probe_rejected(self):
        moment = {"defined": False, "dot": 0.0, "actor_norm": 0.0, "weighted_critic_norm": 0.0}
        groups = {k: copy.deepcopy(moment) for k in ("layers.0", "layers.1", "embeddings_and_input_projections", "final_norm")}
        diag = {**moment, "backend": "cpu_shadow", "measures_live_MPS_gradients": False,
                "snapshot": "first_minibatch_pre_optimizer_step", "probe_count": 1, "minibatch_count": 512, "groups": groups,
                "coverage": {"parameters": 1, "elements": 1, "actor_used": 1, "critic_used": 1},
                "live_preclip_grad_norm": 0.0, "live_clip_coefficient": 1.0}
        row = {"phase_update": 325, "local_update": 1, "metrics": {"optimizer_steps": 1,
            "transitions": 16384, "gradient_alignment_diagnostics": diag},
            "counters": {"updates": 1, "optimizer_steps": 1, "environment_decisions": 16384},
            "update_progress": {"completed_updates": 1, "complete": True, "in_update": False}}
        class R:
            finite_tree = staticmethod(lambda value: None)
            validate_gradient_alignment = staticmethod(audit_runner_gradient)
        self.assertEqual(a.validate_metric_rows(R, [row], 1), 1)
        stale = copy.deepcopy(row); stale["metrics"]["gradient_alignment_diagnostics"]["snapshot"] = "post_update"
        with self.assertRaises((a.AuditError, ValueError)):
            a.validate_metric_rows(R, [stale], 1)
        with self.assertRaises(a.AuditError):
            a.validate_metric_rows(R, [], 1)

    def test_observer_instantiation_hash_and_no_launch_contract(self):
        record = {"schema": "retained324_same_lr_observer_instantiation_v1",
            "observer_sha256": w.OBSERVER_SHA, "registration_sha256": a.REG_SHA,
            "actual_launches": 0, "one_shot_marker_absent": True}
        self.assertTrue(a.validate_observer_instantiation(record))
        for key, value in (("observer_sha256", "0" * 64), ("registration_sha256", "1" * 64),
                           ("actual_launches", 1), ("one_shot_marker_absent", False)):
            bad = copy.deepcopy(record); bad[key] = value
            with self.subTest(key=key), self.assertRaises(a.AuditError):
                a.validate_observer_instantiation(bad)

    def test_all_evaluation_rows_death_accounting_and_survival_summary(self):
        rows = copy.deepcopy(self.parent_eval["evaluation"]["rows"])
        ev = copy.deepcopy(self.parent_eval["evaluation"])
        cert = {"checkpoint": "checkpoint-000324-candidate.pt", "checkpoint_sha256": "a" * 64,
                "phase_update": 324, "local_update": 0, "normal_training_iteration": True,
                "training_eligible": False, "promoted": False, "training_state_unchanged": True,
                "evaluation": ev, "performance": self.parent_eval["performance"], "competence_passed": False}
        side = {"checkpoint_sha256": "a" * 64, "eligibility_status": "provisional_pending_parent_terminal_receipt",
                "training_eligible": False, "promoted": False}
        class Gate:
            @staticmethod
            def progress_passed(*args): return False
        class R:
            performance = staticmethod(lambda value: self.parent_eval["performance"])
        ctx = {"runner": R, "survival_gate": Gate}
        a.validate_certificate(ctx, 324, cert, side, rows, cert["checkpoint"], "a" * 64)
        a.validate_entry_against_parent(cert, rows)
        bad_parent = copy.deepcopy(cert)
        bad_parent["evaluation"]["rows"][0]["score"] += 1
        with self.assertRaises(a.AuditError):
            a.validate_entry_against_parent(bad_parent, rows)
        bad = copy.deepcopy(rows); bad[0]["death_cause"] = "synthetic_wrong_cause"
        with self.assertRaises(a.AuditError):
            a.validate_certificate(ctx, 324, cert, side, bad, cert["checkpoint"], "a" * 64)


def audit_runner_gradient(diag):
    return AuditorControls.runner.validate_gradient_alignment(diag)


if __name__ == "__main__":
    unittest.main()
