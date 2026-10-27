"""CPU-only registration and lineage checks; no checkpoint tensor reads."""
from __future__ import annotations

import copy
import hashlib
import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import build_registration as builder
import parent_adapter as adapter
import registration_schema as schema

ROOT = Path("/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79")
V2 = ROOT / "learning/runs/v2"
SELECTED = json.loads((V2 / "D2-retained300-parent-terminal-audit-20261026-r1/retained-best-candidate-receipt.json").read_text())
PRODUCING = json.loads((V2 / "D2-retained300-parent-terminal-audit-20261026-r1/completed-iteration-receipt.json").read_text())
LATEST = json.loads((V2 / "D2-retained324-parent-terminal-audit-20261026-r1/completed-iteration-receipt.json").read_text())


def digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selected_state() -> dict:
    return {
        "counters": SELECTED["candidate_counters"],
        "cumulative_counters": SELECTED["candidate_cumulative_counters"],
        "inherited_counters": SELECTED["inherited_counters"],
        "next_episode_indices": SELECTED["next_episode_indices"],
        "identity_sha256": SELECTED["identity_sha256"],
        "config_sha256": SELECTED["config_sha256"],
        "runtime_sha256": SELECTED["runtime_sha256"],
        "native_sha256": SELECTED["native_sha256"],
        "policy_sha256": SELECTED["policy_sha256"],
        "registration_sha256": SELECTED["registration_sha256"],
        "phase": "D2", "phase_update": 324, "local_update": 24,
        "tag": "candidate", "training_eligible": False, "promoted": False,
        "eligibility_status": "provisional_pending_parent_terminal_receipt",
        "update_progress": {"complete": True, "in_update": False, "completed_updates": 24},
        "parent_checkpoint_sha256": adapter.PARENT_OF_RUN_SHA256,
        "cumulative_selected_checkpoint_trajectory_wall_seconds": adapter.SELECTED_TRAJECTORY_BASELINE_SECONDS,
        "current_iteration_observed_outer_seconds": 488.7727023329353,
        "parent_completed_campaign_cost_baseline_seconds": adapter.PRODUCING_COST_BEFORE_SECONDS,
        "cumulative_successful_ancestor_and_completed_campaign_cost_seconds": 8621.338345875141 + 488.7727023329353,
        "model": SELECTED["learner_fingerprints"]["model"],
        "optimizer": {"fingerprint_fixture": SELECTED["learner_fingerprints"]["optimizer"],
                      "param_groups": [{"lr": 3e-5, "eps": 1e-5}]},
        "rng": SELECTED["learner_fingerprints"]["rng"],
    }


def fingerprint_fixture(value):
    if isinstance(value, dict) and "fingerprint_fixture" in value:
        return value["fingerprint_fixture"]
    return value


class ParentAdapterTests(unittest.TestCase):
    def validate(self, state=None, selected=None, producing=None, latest=None,
                 selected_digest=adapter.SELECTED_RECEIPT_SHA256,
                 producing_digest=adapter.PRODUCING_COST_RECEIPT_SHA256,
                 latest_digest=adapter.LATEST_COST_RECEIPT_SHA256):
        return adapter.validate_parent(
            selected_state() if state is None else state,
            adapter.CHECKPOINT_SHA256,
            SELECTED if selected is None else selected,
            selected_digest,
            fingerprint_fixture,
            {"checkpoint_sha256": adapter.CHECKPOINT_SHA256,
             "eligibility_status": "provisional_pending_parent_terminal_receipt",
             "promoted": False, "training_eligible": False},
            adapter.CHECKPOINT_METADATA_SHA256,
            PRODUCING if producing is None else producing,
            producing_digest,
            LATEST if latest is None else latest,
            latest_digest,
        )

    def test_accepts_selected_checkpoint_with_distinct_latest_cost_anchor(self):
        self.assertEqual(self.validate(), selected_state())

    def test_rejects_wrong_original_selected_receipt_digest(self):
        with self.assertRaisesRegex(ValueError, "byte pin"):
            self.validate(selected_digest="0" * 64)

    def test_rejects_selected_receipt_status_drift(self):
        bad = copy.deepcopy(SELECTED)
        bad["status"] = "accepted_completed_training_iteration_no_best_replacement"
        with self.assertRaisesRegex(ValueError, "authority"):
            self.validate(selected=bad)

    def test_rejects_latest_cost_receipt_digest_drift(self):
        with self.assertRaisesRegex(ValueError, "digest"):
            self.validate(latest_digest="0" * 64)

    def test_rejects_latest_cost_chain_break(self):
        bad = copy.deepcopy(LATEST)
        bad["wall_accounting"]["completed_campaign_resource_cost_before_seconds"] = 9758.0
        with self.assertRaisesRegex(ValueError, "accounting"):
            self.validate(latest=bad)

    def test_rejects_fabricated_competence_authority(self):
        bad = copy.deepcopy(LATEST)
        bad["competence_passed"] = False
        with self.assertRaisesRegex(ValueError, "fabricated"):
            self.validate(latest=bad)

    def test_rejects_original_checkpoint_cost_baseline_rewritten_to_latest(self):
        state = selected_state()
        state["parent_completed_campaign_cost_baseline_seconds"] = adapter.LATEST_COST_BEFORE_SECONDS
        with self.assertRaisesRegex(ValueError, "producing-run cost lineage"):
            self.validate(state=state)

    def test_rejects_changed_selected_checkpoint_sha(self):
        with self.assertRaisesRegex(ValueError, "checkpoint or receipt byte pin"):
            adapter.validate_parent(selected_state(), "0" * 64, SELECTED,
                adapter.SELECTED_RECEIPT_SHA256, fingerprint_fixture,
                {"checkpoint_sha256": adapter.CHECKPOINT_SHA256,
                 "eligibility_status": "provisional_pending_parent_terminal_receipt",
                 "promoted": False, "training_eligible": False},
                adapter.CHECKPOINT_METADATA_SHA256, PRODUCING,
                adapter.PRODUCING_COST_RECEIPT_SHA256, LATEST,
                adapter.LATEST_COST_RECEIPT_SHA256)


class SchemaTests(unittest.TestCase):
    def valid(self):
        return {
            "schema": schema.SCHEMA, "run_id": schema.RUN_ID, "root": str(schema.ROOT),
            "output": str(schema.OUTPUT), "run_seed": schema.RUN_SEED,
            "phase_start": 324, "phase_end": 384, "parent_total_updates": 372,
            "expected_total_updates": 432, "new_updates": 60,
            "evaluation_updates": [324, 336, 348, 360, 372, 384],
            "lr_schedule": {"origin_cumulative_update": 372, "horizon_updates": 60,
                "start_lr": 3e-5, "end_lr": 1e-5,
                "application": "after_rollout_before_ppo_update",
                "group_lr_log": "per_optimizer_group_per_update",
                "spec_sha256": schema.SCHEDULE_SPEC_SHA256,
                "helper_sha256": schema.HELPER_SHA256},
            "training_eligible": False, "promoted": False,
            "normal_training_iteration": True,
        }

    def test_accepts_exact_new_identity_and_schedule(self):
        self.assertEqual(schema.validate_identity(self.valid())["run_id"], schema.RUN_ID)

    def test_rejects_other_run_id_and_schedule_digest(self):
        bad = self.valid(); bad["run_id"] = "D2-retained324-continuation-20261026-r1"
        with self.assertRaisesRegex(ValueError, "identity"):
            schema.validate_identity(bad)
        bad = self.valid(); bad["lr_schedule"]["helper_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "digest"):
            schema.validate_identity(bad)


class BuilderTests(unittest.TestCase):
    def test_missing_immutable_manifests_do_not_create_registration(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "registration.json"
            with self.assertRaises(ValueError):
                builder.build_registration(Path(temp) / "missing-runner.json", "0" * 64,
                                           Path(temp) / "missing-helper.json", "0" * 64,
                                           Path(temp) / "missing-launcher.json", "0" * 64)
            self.assertFalse(out.exists())

    def test_builds_only_from_mocked_immutable_runner_and_helper_manifests(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runner_dir = root / "runner-r3"; runner_dir.mkdir()
            runner = runner_dir / "runner.py"; runner.write_text("# immutable synthetic runner\n")
            helper = runner_dir / "lr_schedule.py"; helper.write_bytes((V2 / "D2-retained324-linear-schedule-prepare-luna-20261026-r1/schedule.py").read_bytes())
            own = root / "own"; own.mkdir()
            launcher = own / "execute_once.py"; launcher.write_text("# reviewed explicit-path launcher fixture\n")
            for name in ("parent_adapter.py", "registration_schema.py", "build_registration.py"):
                (own / name).write_bytes((V2 / "D2-retained324-linear-registration-luna-20261026-r1" / name).read_bytes())
            runner_manifest = root / "runner-manifest.json"
            runner_manifest.write_text(json.dumps({"runner_path": str(runner), "runner_sha256": digest_file(runner)}))
            helper_manifest = root / "helper-manifest.json"
            helper_manifest.write_text(json.dumps({"helper_path": str(helper),
                "helper_sha256": digest_file(helper),
                "schedule_spec_sha256": schema.SCHEDULE_SPEC_SHA256,
                "origin_cumulative_update": 372, "horizon_updates": 60}))
            fake_base = root / "base"; fake_base.mkdir()
            base_registration = json.loads((builder.BASE / "registration.json").read_text())
            source_manifest = json.loads((builder.BASE / "source-manifest.json").read_text())
            (fake_base / "registration.json").write_text(json.dumps(base_registration))
            (fake_base / "source-manifest.json").write_text(json.dumps(source_manifest))
            launcher_manifest = root / "launcher-manifest.json"
            launcher_manifest.write_text(json.dumps({"launcher_path": str(launcher),
                "launcher_sha256": digest_file(launcher),
                "runner_module_path": str(runner),
                "runner_module_plumbing": "explicit_immutable_path"}))
            with mock.patch.multiple(builder, RUNNER_DIR=runner_dir, BASE=fake_base, OWN=own,
                                    SCHEDULE=root / "unused"):
                reg = builder.build_registration(runner_manifest, digest_file(runner_manifest),
                    helper_manifest, digest_file(helper_manifest), launcher_manifest,
                    digest_file(launcher_manifest))
            schema.validate_identity(reg)
            self.assertEqual(len(reg["pins"]), 13846 + 10)
            self.assertEqual(reg["pins"][str(runner.resolve())], digest_file(runner))
            self.assertEqual(reg["pins"][str(helper.resolve())], digest_file(helper))
            self.assertEqual(reg["launcher_path"], str(launcher.resolve()))
            self.assertEqual(reg["launcher_module_contract"]["status"], "immutable_successor_launcher_manifest_verified")
            self.assertEqual(reg["resource_cost_anchor"]["sha256"], adapter.PRODUCING_COST_RECEIPT_SHA256)
            self.assertEqual(reg["latest_resource_cost_anchor"]["sha256"], adapter.LATEST_COST_RECEIPT_SHA256)
            self.assertEqual(reg["authority_limits"]["learner_ancestry_updates_from_discarded_iteration"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
