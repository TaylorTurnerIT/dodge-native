import copy
import hashlib
import unittest
from pathlib import Path

import runner as r


def registration_fixture():
    root = "/checkout"
    return {
        "schema": "d2_training_v3_continuation_registration_v1",
        "normal_training_iteration": True,
        "training_eligible": False,
        "limits": copy.deepcopy(r.LIMITS),
        "run_id": r.RUN_ID,
        "run_seed": 810631976,
        "timing_policy": "launcher_monotonic_start_plus_registered_limits_v1",
        "root": root,
        "output": root + "/learning/runs/v2/" + r.RUN_ID,
        "runtime_root": root + "/runtime",
        "interpreter": root + "/python",
        "runner_path": root + "/runner.py",
        "launcher_path": root + "/execute_once.py",
        "state_path": root + "/state.json",
        "config_path": root + "/config.json",
        "config_sha256": r.CONFIG_SHA,
        "runtime_versions": {"python": "3.12", "torch": "2.x", "numpy": "2.x"},
        "import_policy": {"pycache_prefix": root + "/empty-cache"},
        "parent": {
            "path": root + "/learning/runs/v2/D2-continuation-20261025-r1/checkpoint-000132-candidate.pt",
            "sha256": r.PARENT_SHA,
            "registration_sha256": r.PARENT_REGISTRATION_SHA,
            "phase": "D2",
            "completed_updates": 132,
            "terminal_receipt_path": root + "/parent-terminal-receipt.json",
            "terminal_receipt_sha256": r.PARENT_RECEIPT_SHA,
        },
        "native": {"sha256": r.NEW_NATIVE_SHA, "old_sha256": r.OLD_NATIVE_SHA, "path": root + "/runtime/dodge_rl/native.so", "old_path": root + "/native-old.so"},
        "cancel_path": root + "/cancel",
        "expected_lease": {"run_id": r.RUN_ID, "kind": "D2_gradient_alignment", "authorization": "user_continue_D2_training_v3", "parent_checkpoint_sha256": r.PARENT_SHA},
        "runtime_transition": {"source_runtime_root": root + "/learning/runs/v2/critic-diagnostic-parent-prepare-20261025-r1/runtime", "old_ppo_sha256": r.OLD_PPO_SHA, "new_ppo_sha256": r.NEW_PPO_SHA, "old_gradient_alignment_sha256": None, "new_gradient_alignment_sha256": r.NEW_ALIGNMENT_SHA, "semantics": r.ALIGNMENT_MEANING},
    }


def accepted_receipt():
    root = Path("/checkout")
    candidate = str((root / "learning/runs/v2/D2-continuation-20261025-r1/checkpoint-000132-candidate.pt").resolve())
    return {
        "schema": r.PARENT_RECEIPT_SCHEMA,
        "status": "accepted_completed_normal_training_iteration",
        "training_continuation_eligible": True,
        "stage_promotion_eligible": False,
        "competence_passed": False,
        "checkpoint_metadata_edited": False,
        "run_id": "D2-continuation-20261025-r1",
        "phase": "D2",
        "completed_phase_updates": 132,
        "completed_local_updates": 60,
        "raw_outer_exit": 0,
        "raw_worker_exit": 0,
        "publication_failure_present": False,
        "cancellation_lineage": [],
        "checkpoint_sha256": r.PARENT_SHA,
        "registration_sha256": r.PARENT_REGISTRATION_SHA,
        "inclusive_iteration_wall_seconds": 1034.278296417091,
        "cumulative_D2_inclusive_wall_seconds": r.PARENT_WALL_SECONDS,
        "cumulative_counters": {"updates": 180},
        "checkpoint_path": candidate,
        "artifacts": {candidate: r.PARENT_SHA},
    }


class ContinuationContract(unittest.TestCase):
    def test_exact_successful_normal_parent_receipt_fixture_accepted(self):
        reg = r.validate_registration(registration_fixture())
        self.assertEqual(r.validate_parent_terminal_receipt(accepted_receipt(), reg), accepted_receipt())

    def test_real_parent_receipt_binds_exact_candidate_and_registration(self):
        root = next(parent for parent in Path(__file__).resolve().parents if (parent / "docs/SPEC_PRIVILEGED_VIT_RL.md").is_file())
        path = root / "learning/runs/v2/d2-continuation-parent-terminal-audit-20261025-r1/parent-terminal-receipt.json"
        receipt = r.read(path)
        reg = registration_fixture()
        reg["root"] = str(root)
        reg["parent"]["path"] = str(root / "learning/runs/v2/D2-continuation-20261025-r1/checkpoint-000132-candidate.pt")
        reg["parent"]["terminal_receipt_path"] = str(path)
        reg["parent"]["terminal_receipt_sha256"] = r.sha(path)
        self.assertEqual(r.sha(reg["parent"]["path"]), r.PARENT_SHA)
        self.assertEqual(receipt["registration_sha256"], r.PARENT_REGISTRATION_SHA)
        self.assertEqual(r.validate_parent_terminal_receipt(receipt, reg), receipt)

    def test_failed_interrupted_cancelled_incomplete_or_mismatched_parent_rejected(self):
        edits = [
            {"status": "failed"}, {"training_continuation_eligible": False},
            {"completed_phase_updates": 71}, {"raw_outer_exit": 1},
            {"raw_worker_exit": 1}, {"inclusive_iteration_wall_seconds": 1800.1},
            {"checkpoint_sha256": "0" * 64}, {"registration_sha256": "0" * 64},
            {"phase": "D1"}, {"competence_passed": True}, {"stage_promotion_eligible": True},
        ]
        reg = r.validate_registration(registration_fixture())
        for edit in edits:
            receipt = accepted_receipt(); receipt.update(edit)
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                r.validate_parent_terminal_receipt(receipt, reg)
        with self.assertRaisesRegex(ValueError, "receipt is absent"):
            r.validate_parent_terminal_receipt({}, reg)

    def test_registration_rejects_failed_lineage_and_scope_changes(self):
        for edit in (
            lambda x: x["parent"].update(sha256="0" * 64),
            lambda x: x["parent"].update(registration_sha256="0" * 64),
            lambda x: x["parent"].update(completed_updates=71),
            lambda x: x["limits"].update(total_seconds=1801),
            lambda x: x.update(run_seed=1),
            lambda x: x.update(training_eligible=True),
            lambda x: x.update(output="/checkout/learning/runs/v2/other"),
        ):
            reg = registration_fixture(); edit(reg)
            with self.assertRaises(ValueError):
                r.validate_registration(reg)

    def test_episode_seed_continuation_uses_saved_nonzero_indices_and_current_plus_one(self):
        starts = [81 + (slot % 7) for slot in range(64)]
        info = [{"seed": {"slot": slot, "episode": starts[slot]}} for slot in range(64)]
        records = [
            {"kind": "abandoned_parent_episode", "info": {"seed": {"episode": 80}}},
            {"kind": "initial", "info": info,
             "batch_info": {"next_episode_indices": [value + 1 for value in starts]}},
        ]
        records.extend(r.ordered_episode_events(
            [{"seed": {"slot": 0, "episode": starts[0]}, "rollout_step": 3, "gameplay_frames": 20}],
            [{"rollout_step": 3, "indices": [0],
              "info": [{"seed": {"slot": 0, "episode": starts[0] + 1}}]}], r.PHASE_START + 1))
        result = r.validate_episode_journal(records, starts)
        self.assertEqual(result["next_episode_indices"][0], starts[0] + 2)
        self.assertEqual(result["next_episode_indices"][1:], [value + 1 for value in starts[1:]])
        bad = copy.deepcopy(records); bad[1]["info"][0]["seed"]["episode"] = 0
        with self.assertRaisesRegex(ValueError, "(?i)initial current/future"):
            r.validate_episode_journal(bad, starts)

    def test_parent_cost_and_local_counters_compose_without_recharging_or_erasing(self):
        self.assertEqual(r.PARENT_WALL_SECONDS, 2222.619523167091)
        parent = {"updates": 180, "optimizer_steps": 22784,
                  "environment_decisions": 2949120, "raw_frames": 11776109}
        final = {"updates": 48, "optimizer_steps": 6000,
                 "environment_decisions": 786432, "raw_frames": 3072}
        self.assertEqual(r.continuation_cumulative_counters(parent, final), {
            "updates": 228, "optimizer_steps": 28784,
            "environment_decisions": 3735552, "raw_frames": 11779181})
        self.assertEqual(r.LIMITS["max_updates"], 48)
        self.assertEqual(r.LIMITS["eval_updates"], [132, 180])
        self.assertEqual((r.PHASE_START, r.PHASE_END, r.PARENT_TOTAL_UPDATES, r.EXPECTED_TOTAL), (132, 180, 180, 228))
        self.assertEqual(r.LIMITS["work_seconds"], 1600)
        self.assertEqual(r.LIMITS["total_seconds"], 1800)

    def test_fingerprint_canonicalizes_mapping_order_but_checks_tensor_contract(self):
        import torch
        a = {"model": {"weight": torch.tensor([1.0, 2.0])}, "step": 2}
        b = {"step": 2, "model": {"weight": torch.tensor([1.0, 2.0])}}
        self.assertEqual(r.fingerprint(a), r.fingerprint(b))
        self.assertNotEqual(r.fingerprint(a), r.fingerprint({"step": 2.0, "model": b["model"]}))
        self.assertIn("<dtype>", " ".join(r.mismatch_paths(a, {"step": 2, "model": {"weight": a["model"]["weight"].double()}})))
        self.assertIn("<shape>", " ".join(r.mismatch_paths(a, {"step": 2, "model": {"weight": a["model"]["weight"].reshape(2, 1)}})))
        changed = a["model"]["weight"].clone(); changed[0] += 1
        self.assertNotEqual(r.fingerprint(a), r.fingerprint({"step": 2, "model": {"weight": changed}}))

    def test_checkpoint_file_and_registration_hash_are_distinct_authorities(self):
        reg = registration_fixture()
        reg_digest = hashlib.sha256(b"prospective continuation registration").hexdigest()
        self.assertNotEqual(reg_digest, r.PARENT_SHA)
        self.assertNotEqual(reg_digest, r.PARENT_REGISTRATION_SHA)
        state = {"checkpoint_sha256": r.PARENT_SHA, "registration_sha256": r.PARENT_REGISTRATION_SHA}
        self.assertEqual(state["checkpoint_sha256"], reg["parent"]["sha256"])
        self.assertEqual(state["registration_sha256"], reg["parent"]["registration_sha256"])


if __name__ == "__main__":
    unittest.main()
