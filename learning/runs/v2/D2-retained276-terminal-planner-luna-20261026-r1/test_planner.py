import unittest

from planner import (
    AUDITOR_SHA256, BASELINE_FUTURE_SECONDS, BASELINE_FULL_COST_SECONDS,
    BASELINE_MEAN, BASELINE_SHA256, EXPECTED_UPDATES, REGISTRATION_SHA256,
    BASELINE_RECEIPT_SHA256, OBSERVER_SHA256, WRAPPER_SHA256, build_plan,
)


def evidence(means=None):
    means = means or {u: 2100.0 + u for u in EXPECTED_UPDATES}
    means[276] = BASELINE_MEAN
    candidates, performance, metadata = {}, {}, {}
    for update in EXPECTED_UPDATES:
        digest = BASELINE_SHA256 if update == 276 else f"{update:064x}"
        cert = f"{update + 1:064x}"
        sidecar = f"{update + 3:064x}"
        candidates[str(update)] = {"checkpoint_sha256": digest, "certificate_sha256": cert,
                                   "sidecar_sha256": sidecar}
        performance[str(update)] = {
            "update": update, "checkpoint_sha256": digest, "certificate_sha256": cert,
            "mean_alive_frames": means[update], "q1_bottom16_mean": 500.0 + update,
            "q4_top16_mean": 4000.0 + update, "episodes": 64, "deaths": 64,
            "caps": 0, "death_causes": {"normal_enemy": 64}, "mean_score": 1000000,
        }
        metadata[str(update)] = {
            "phase_update": update, "checkpoint_sha256": digest, "metadata_sha256": f"{update + 2:064x}",
            "sidecar_sha256": sidecar,
            "counters": {"updates": update - 276, "optimizer_steps": 0,
                         "environment_decisions": 0, "raw_frames": 0},
            "cumulative_counters": {"updates": 324 + update - 276, "optimizer_steps": 40352,
                                    "environment_decisions": 5308416, "raw_frames": 21202529},
            "next_episode_indices": [update] * 64,
            "learner_fingerprints": {name: f"{update + n:064x}" for n, name in enumerate(("model", "optimizer", "rng"), 1)},
            "cumulative_selected_checkpoint_trajectory_wall_seconds": 4760.0 + update,
        }
    return {
        "schema": "retained276_terminal_planner_evidence_v1",
        "pins": {"registration_sha256": REGISTRATION_SHA256, "auditor_sha256": AUDITOR_SHA256,
                 "wrapper_sha256": WRAPPER_SHA256},
        "parent": {"phase_update": 276, "checkpoint_sha256": BASELINE_SHA256,
                   "mean_alive_frames": BASELINE_MEAN, "stale": False,
                   "receipt": {"schema": "d2_normal_training_parent_terminal_receipt_v1",
                               "status": "accepted_completed_normal_training_iteration",
                               "receipt_sha256": BASELINE_RECEIPT_SHA256,
                               "checkpoint_sha256": BASELINE_SHA256, "completed_phase_updates": 276,
                               "performance": {"mean_alive_frames": BASELINE_MEAN},
                               "wall_accounting": {"future_checkpoint_trajectory_baseline_seconds": BASELINE_FUTURE_SECONDS,
                                                   "successful_ancestor_and_completed_campaign_cost_seconds": BASELINE_FULL_COST_SECONDS},
                               "counters": {"updates": 324}, "cumulative_counters": {"updates": 324},
                               "next_episode_indices": [276] * 64,
                               "learner_fingerprints": {"model": "a" * 64, "optimizer": "b" * 64, "rng": "c" * 64}}},
        "registration": {"sha256": REGISTRATION_SHA256, "run_id": "D2-retained276-continuation-20261026-r2",
                         "parent_checkpoint_sha256": BASELINE_SHA256, "phase_start": 276,
                         "phase_end": 348, "local_updates": 72, "run_seed": 3791628419,
                         "config_sha256": "f858a63c324fc312f794c0423aa56db2daf60793b62990cd51fa400afe3af628"},
        "audit": {"schema": "d2_retained276_continuation_terminal_wrapper_audit_v1",
                  "mode": "full_parent_only", "auditor_sha256": AUDITOR_SHA256,
                  "wrapper_sha256": WRAPPER_SHA256, "registration_sha256": REGISTRATION_SHA256,
                  "observer_sha256": OBSERVER_SHA256,
                  "status": "all_candidates_audited_pending_parent_terminal_acceptance",
                  "updates_audited": EXPECTED_UPDATES, "pins_checked_before": 13787,
                  "pins_checked_after": 13787, "parent_sha256": BASELINE_SHA256,
                  "stale_parent": False, "candidates": candidates},
        "performance": performance, "candidate_metadata": metadata,
        "terminal": {"execution_status": "passed", "worker_status": "completed",
                     "raw_exits": {"outer": 0, "worker": 0}, "owned_processes_and_groups_absent": True,
                     "source_postflight_passed": True, "final_publication_absent": True,
                     "outer_inclusive_wall_seconds": 1408.0, "aggregate_rss_peak_bytes": 1,
                     "worker_rss_peak_bytes": 1, "mps_driver_peak_bytes": 1, "resources_complete": True,
                     "execution_result_sha256": "1" * 64, "worker_result_sha256": "2" * 64,
                     "observation_sha256": "3" * 64, "resource_log_sha256": "4" * 64,
                     "cumulative_counters": {"updates": 396, "optimizer_steps": 49568,
                                              "environment_decisions": 6488064, "raw_frames": 25916231},
                     "next_episode_indices": [348] * 64},
    }


class PlannerTests(unittest.TestCase):
    def test_no_improvement_preserves_exact276_and_separate_cost_clock(self):
        e = evidence({u: 1000.0 for u in EXPECTED_UPDATES})
        p = build_plan(e)
        self.assertEqual(p["branch"], "retain_exact_current_parent")
        self.assertEqual(p["proposed_update"], 276)
        self.assertEqual(p["proposed_checkpoint_sha256"], BASELINE_SHA256)
        self.assertEqual(p["wall_accounting"]["selected_future_branch_baseline_seconds"], BASELINE_FUTURE_SECONDS)
        self.assertEqual(p["wall_accounting"]["completed_campaign_full_resource_cost_seconds"],
                         BASELINE_FULL_COST_SECONDS + 1408.0)
        self.assertFalse(any(p["authority_flags"].values()))

    def test_better_intermediate_keeps_point_metadata_and_binds_whole_terminal_separately(self):
        e = evidence({u: 2000.0 for u in EXPECTED_UPDATES})
        e["performance"]["300"]["mean_alive_frames"] = 3000.0
        p = build_plan(e)
        self.assertEqual(p["branch"], "select_better_intermediate")
        self.assertEqual(p["proposed_update"], 300)
        self.assertEqual(p["proposed_candidate_metadata"], e["candidate_metadata"]["300"])
        self.assertEqual(p["counter_binding"]["selected_checkpoint_counters"]["updates"], 24)
        self.assertEqual(p["counter_binding"]["completed_terminal_cumulative_counters"]["updates"], 396)
        self.assertTrue(p["counter_binding"]["intermediate_discarded_tail_is_not_checkpoint_ancestry"])
        self.assertEqual(p["wall_accounting"]["selected_future_branch_baseline_seconds"], 5060.0)
        self.assertEqual(p["wall_accounting"]["completed_campaign_full_resource_cost_seconds"],
                         BASELINE_FULL_COST_SECONDS + 1408.0)

    def test_better_endpoint_adds_full_outer_wall_to_future_branch(self):
        e = evidence({u: 2000.0 for u in EXPECTED_UPDATES})
        e["performance"]["348"]["mean_alive_frames"] = 3100.0
        p = build_plan(e)
        self.assertEqual(p["branch"], "select_better_endpoint")
        self.assertEqual(p["proposed_update"], 348)
        self.assertEqual(p["wall_accounting"]["selected_future_branch_baseline_seconds"],
                         BASELINE_FUTURE_SECONDS + 1408.0)
        self.assertFalse(any(p["authority_flags"].values()))

    def test_equal_baseline_and_equal_candidate_means_keep_earlier(self):
        e = evidence({u: BASELINE_MEAN for u in EXPECTED_UPDATES})
        self.assertEqual(build_plan(e)["proposed_update"], 276)
        e["performance"]["300"]["mean_alive_frames"] = 3000.0
        e["performance"]["312"]["mean_alive_frames"] = 3000.0
        self.assertEqual(build_plan(e)["proposed_update"], 300)

    def test_bad_evidence_fails_closed(self):
        mutations = [
            lambda e: e["audit"].update(status="provisional"),
            lambda e: e["terminal"].update(execution_status="failed"),
            lambda e: e["terminal"].update(raw_exits={"outer": 1, "worker": 0}),
            lambda e: e["terminal"].update(aggregate_rss_peak_bytes=6442450945),
            lambda e: e["terminal"].update(observation_sha256="bad"),
            lambda e: e["pins"].update(auditor_sha256="0" * 64),
            lambda e: e["parent"].update(stale=True),
            lambda e: e["parent"]["receipt"].update(receipt_sha256="0" * 64),
            lambda e: e["audit"].update(parent_sha256="f" * 64),
            lambda e: e["performance"]["300"].update(mean_alive_frames=float("nan")),
            lambda e: e["audit"]["candidates"].pop("300"),
            lambda e: e["audit"]["candidates"]["300"].update(checkpoint_sha256="bad"),
            lambda e: e["candidate_metadata"].pop("300"),
            lambda e: e["candidate_metadata"]["300"].update(sidecar_sha256="0" * 64),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                e = evidence()
                mutate(e)
                p = build_plan(e)
                self.assertEqual(p["proposal_status"], "blocked_fail_closed")
                self.assertIsNone(p["proposed_update"])
                self.assertFalse(any(p["authority_flags"].values()))


if __name__ == "__main__":
    unittest.main()
