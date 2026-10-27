"""Exercise actual finalizer publication flow with synthetic inputs under one temporary directory.

No production runtime, checkpoint, lease, or ledger is accessed. Evidence validation and
checkpoint loading are explicit stubs; publication, state comparisons, and atomic commit are real.
"""
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class PublicationControl(unittest.TestCase):
    def test_actual_publication_preserves_schedule_unrelated_tasks_and_mode(self):
        self._exercise_case()

    def test_missing_selected_identity_leaves_zero_publication_files(self):
        self._exercise_case("selected_identity")

    def test_malformed_last_certificate_leaves_zero_publication_files(self):
        self._exercise_case("last_certificate")

    def _exercise_case(self, fault=None):
        source = Path(os.environ.get("FINALIZER_TEST_SOURCE", Path(__file__).with_name("finalize_parent.py")))
        spec = importlib.util.spec_from_file_location("synthetic_finalizer", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            own = root / "out"
            own.mkdir()
            run = root / "run"
            run.mkdir()
            prep = root / "prep"
            prep.mkdir()
            auditor = root / "auditor"
            auditor.mkdir()
            observer = root / "observer"
            observer.mkdir()
            assembly = root / "assembly"
            assembly.mkdir()
            statepath = root / "state.json"
            lease = {"run_id": "synthetic_linear_trial"}
            initial = {"active_long_campaign": lease, "postcritic_training_work": {},
                       "training_parent_selection_policy": {}, "tasks": {"unrelated": {"status": "working"}}}
            statepath.write_text(json.dumps(initial))
            statepath.chmod(0o640)
            schedule = {"origin_cumulative_update": 372, "horizon_updates": 60}
            schedule_sha = module.canonical_sha(schedule)
            for directory in (prep, auditor):
                (directory / "lr_schedule.py").write_text("SCHEDULE_SPEC = " + repr(schedule) + "\n")
            reg_path = prep / "registration.json"
            full_path = auditor / "full-audit.json"
            obs_path = observer / "observation.json"
            reconciliation = own / "review-reconciliation.json"
            review = root / "review.md"
            incumbent = root / "incumbent.pt"
            old_receipt = root / "old-receipt.json"
            old_certificate = root / "old-certificate.json"
            cost_path = root / "cost.json"
            checkpoint = run / "checkpoint-000348-candidate.pt"
            sidecar = Path(str(checkpoint) + ".json")
            digest = "a" * 64
            lrs = [2.2203389830508478e-5]
            saved_schedule = {"schedule_origin_cumulative_update": 372, "horizon_updates": 60,
                              "completed_schedule_updates": 24, "schedule_spec_sha256": schedule_sha}
            selected = {"config_sha256": digest, "runtime_sha256": digest, "native_sha256": digest,
                        "policy_sha256": digest, "cumulative_selected_checkpoint_trajectory_wall_seconds":
                        5678.9823631240915 + 400.0, "current_iteration_observed_outer_seconds": 400.0,
                        "counters": {"updates": 24}, "cumulative_counters": {"updates": 396},
                        "inherited_counters": {"updates": 372}, "next_episode_indices": list(range(64)),
                        "identity": {"synthetic": True}, "identity_sha256": digest,
                        "run_seed": 42, "lr_schedule": saved_schedule}
            alive = [867] * 15 + [868] + [2760] * 7 + [2761] * 25 + [6003] * 2 + [6004] * 14
            causes = ["normal_enemy"] * 25 + ["static_pattern_rect"] * 15 + ["kamikaze_enemy"] * 15 + ["moving_pattern_rect"] * 9
            rows = [{"alive_frames": a, "terminated": True, "death_cause": c} for a, c in zip(alive, causes)]
            certificate = {"checkpoint_sha256": module.SELECTED_SHA, "competence_passed": True,
                           "evaluation": {"rows": rows, "complete": True, "mean_alive_frames": 3098.125,
                                          "mean_score": 1, "deaths": 64, "caps": 0}}
            means = {"324": 2939.40625, "336": 2531.3125, "348": 3098.125,
                     "360": 2535.140625, "372": 2646.5625, "384": 2270.59375}
            candidates = {k: {"mean_alive_frames": mean, "checkpoint_sha256": module.SELECTED_SHA if k == "348" else digest,
                              "sidecar_sha256": digest, "certificate_sha256": digest,
                              "component_fingerprints": {"model": digest}, "performance": {"synthetic": mean},
                              "deaths": 64, "caps": 0}
                          for k, mean in means.items()}
            old = {"performance": {"mean_alive_frames": 2939.40625, "q1_bottom16_mean": 767.5,
                                   "q4_top16_mean": 5468.6875, "death_causes": {}},
                   "evaluation_path": str(old_certificate), "evaluation_sha256": digest}
            reg = {"state_path": str(statepath), "expected_lease": lease,
                   "cancel_path": str(root / "cancel"), "pins": {},
                   "import_policy": {"pycache_prefix": str(root / "cache")},
                   "config_sha256": digest, "runtime_sha256": digest, "policy_sha256": digest,
                   "native": {"sha256": digest}, "parent": {
                       "latest_resource_cost_anchor": {"path": str(cost_path)}, "registration_sha256": digest},
                   "lr_schedule_path": str(prep / "lr_schedule.py"), "lr_schedule_sha256": digest,
                   "lr_schedule": {**schedule, "spec_sha256": schedule_sha}, "run_id": "synthetic_linear_trial",
                   "run_seed": 42}
            audit = {"candidates": candidates, "terminal_record_sha256": {str(obs_path): digest},
                     "tracked_file_sha256": {}}
            obs = {"outer_inclusive_wall_seconds": 1131.1351048339857}
            worker = {"cumulative_selected_checkpoint_trajectory_wall_seconds": 6806.37175508199,
                      "current_iteration_observed_outer_seconds": 1127.0, "elapsed_seconds": 1127.0,
                      "counters": {"updates": 60}, "cumulative_counters": {"updates": 432}}
            data = {reg_path: reg, full_path: {"audit": audit}, obs_path: obs,
                    run / "execution-result.json": {}, run / "worker-result.json": worker,
                    old_receipt: old, sidecar: {"provisional": True},
                    cost_path: {"wall_accounting": {"completed_campaign_resource_cost_after_seconds": 10824.835578584221}}}
            for key in candidates:
                cert = json.loads(json.dumps(certificate))
                if key != "348":
                    total = int(means[key] * 64)
                    per_row, remainder = divmod(total, 64)
                    for index, row in enumerate(cert["evaluation"]["rows"]):
                        row["alive_frames"] = per_row + (index < remainder)
                    cert["evaluation"]["mean_alive_frames"] = means[key]
                data[run / f"development-{int(key):06d}.json"] = cert
            if fault == "selected_identity":
                del selected["identity"]
            if fault == "last_certificate":
                del data[run / "development-000384.json"]["evaluation"]["rows"][-1]["alive_frames"]
            pins = {reg_path: module.REG_SHA, full_path: module.FULL_SHA, obs_path: digest,
                    auditor / "audit-binding.json": module.BINDING_SHA,
                    reconciliation: module.RECONCILIATION_SHA, review: module.REVIEW_SHA,
                    checkpoint: module.SELECTED_SHA, incumbent: module.INCUMBENT_SHA,
                    old_receipt: module.OLD_RECEIPT_SHA, prep / "lr_schedule.py": digest}

            def synthetic_read(path):
                path = Path(path)
                return data[path] if path in data else json.loads(path.read_text())

            def synthetic_sha(path):
                path = Path(path)
                if path in pins:
                    return pins[path]
                return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else digest

            replacements = {"ROOT": root, "BASE": root, "OWN": own, "EXPECTED_OWN": own,
                            "PREP": prep, "RUN": run, "OBSERVER": observer, "AUDITOR": auditor,
                            "ASSEMBLY": assembly, "REVIEW": review, "RECONCILIATION": reconciliation,
                            "REG_PATH": reg_path, "FULL_PATH": full_path, "OBS_PATH": obs_path,
                            "INCUMBENT": incumbent, "OLD_RECEIPT": old_receipt,
                            "SCHEDULE_SPEC_SHA": schedule_sha, "read": synthetic_read, "sha": synthetic_sha,
                            "validate_review_reconciliation": lambda: {"selected_candidate": 348},
                            "_verify_registered_evidence": lambda *args: None,
                            "_assert_empty_cache": lambda *args: None,
                            "_check_live_process_absence": lambda *args: {},
                            "_load_selected_state": lambda *args: (selected, None, {"model": digest}, lrs[0], lrs, saved_schedule)}
            with patch.multiple(module, **replacements), redirect_stdout(io.StringIO()):
                if fault:
                    with self.assertRaises(KeyError):
                        module._validate_and_finalize()
                    self.assertEqual(list(own.iterdir()), [])
                    self.assertEqual(json.loads(statepath.read_text()), initial)
                    return
                module._validate_and_finalize()
            receipt = json.loads((own / "retained-best-candidate-receipt.json").read_text())
            committed = json.loads(statepath.read_text())
            self.assertEqual(receipt["schedule"]["metadata"], saved_schedule)
            self.assertEqual(receipt["candidate_cumulative_counters"]["updates"], 396)
            self.assertTrue(receipt["training_continuation_eligible"])
            self.assertFalse(receipt["qualification_passed"])
            self.assertEqual(committed["training_parent_selection_policy"]["current_parent_phase_update"], 348)
            self.assertEqual(committed["tasks"], initial["tasks"])
            self.assertIsNone(committed["active_long_campaign"])
            self.assertEqual(statepath.stat().st_mode & 0o777, 0o640)
            self.assertEqual(committed, json.loads((own / "state-after-lease-clear.json").read_text()))
            self.assertTrue((own / "output-manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
