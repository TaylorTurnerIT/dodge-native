"""CPU-only controls for the retained-204 lr1e-4 auditor. No MPS, no training output reads."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import audit_candidates as a

PARENT = {"updates": 252, "optimizer_steps": 3000, "environment_decisions": 252 * 16384, "raw_frames": 900000}
PARENT_NEXT = list(range(64))
POLICY = "bfcbee1609cec0180495c957cf4b5e0b31356f395e2a706217cc9225647d23ae"
RUN_ID = "D2-retained204-lr1e4-20261026-r1"
PREG = "d6a5aa8cbdd889728b79486f09673215847b6d8e27f93f1ce80eb1cf3e8cc7ba"


def candidate(update=216):
    local = update - 204
    counters = {"updates": local, "optimizer_steps": 128 * local, "environment_decisions": 16384 * local, "raw_frames": 1000 * local}
    if local == 0:
        counters = dict(a.ENTRY_ZERO)
    cumulative = {k: PARENT[k] + counters[k] for k in counters}
    cur = 400.0 + local
    return {
        "schema": "d2_training_v3_checkpoint_v1", "tag": "candidate",
        "eligibility_status": "provisional_pending_parent_terminal_receipt", "training_eligible": False, "promoted": False,
        "phase": "D2", "phase_update": update, "local_update": local,
        "registration_sha256": a.REG_SHA, "config_sha256": a.CONFIG_SHA, "policy_sha256": POLICY,
        "parent_sha256": a.PARENT_SHA, "parent_checkpoint_sha256": a.PARENT_SHA, "parent_registration_sha256": PREG,
        "parent_run_id": "D2-best180-branch-luna-20261026-r1",
        "identity": {"run_id": RUN_ID, "phase_update_start": 204, "phase_update_end": 276,
                     "registration_sha256": a.REG_SHA, "parent_checkpoint_sha256": a.PARENT_SHA, "policy_sha256": POLICY},
        "update_progress": {"complete": True, "in_update": False, "completed_updates": local},
        "optimizer": {"param_groups": [{"lr": 0.0001, "eps": 1e-05}]},
        "counters": counters, "inherited_counters": dict(PARENT), "cumulative_counters": cumulative,
        "next_episode_indices": [i + 1 for i in PARENT_NEXT],
        "current_iteration_observed_outer_seconds": cur,
        "cumulative_selected_checkpoint_trajectory_wall_seconds": a.SELECTED_BASE_WALL + cur,
        "cumulative_successful_ancestor_and_completed_campaign_cost_seconds": a.CAMPAIGN_BASE_WALL + cur,
        "selected_parent_checkpoint_trajectory_baseline_seconds": a.SELECTED_BASE_WALL,
        "parent_completed_campaign_cost_baseline_seconds": a.CAMPAIGN_BASE_WALL,
    }


def meta(state, update=216):
    return a.validate_candidate_metadata(state, update, parent_cumulative=PARENT, parent_next=PARENT_NEXT,
                                         reg_sha=a.REG_SHA, config_sha=a.CONFIG_SHA, policy_sha=POLICY,
                                         parent_run_id="D2-best180-branch-luna-20261026-r1",
                                         parent_registration_sha=PREG, run_id=RUN_ID)


class PositiveControls(unittest.TestCase):
    def test_entry_and_midrun_candidates_pass(self):
        self.assertEqual(meta(candidate(204), 204), 400.0)
        self.assertEqual(meta(candidate(216), 216), 412.0)

    def test_cumulative_base_is_252_not_300(self):
        state = candidate(216)
        self.assertEqual(state["cumulative_counters"]["updates"], 252 + 12)

    def test_choose_best_strict_and_no_endpoint(self):
        means = {204: 1921.171875, 216: 1921.171875, 228: 1950.0, 240: 1940.0, 276: 1930.0}
        self.assertEqual(a.choose_best(means), 228)
        self.assertIsNone(a.choose_best({204: 1921.171875, 276: 1921.171875}))

    def test_fail_closed_prefix_journal_ignores_partial_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.jsonl"
            path.write_bytes(b'{"kind": "initial"}\n{"kind": "comp')
            records, _ = a.complete_lines(path, strict=False)
            self.assertEqual(records, [{"kind": "initial"}])
            with self.assertRaises(a.AuditError):
                a.complete_lines(path, strict=True)


class NegativeControls(unittest.TestCase):
    def test_wrong_lr_rejected(self):
        state = candidate(216)
        state["optimizer"]["param_groups"][0]["lr"] = 0.0003
        with self.assertRaises(a.AuditError):
            meta(state)

    def test_identity_phase_end_drift_rejected(self):
        state = candidate(216)
        state["identity"]["phase_update_end"] = 264
        with self.assertRaises(a.AuditError):
            meta(state)

    def test_parent_300_base_rejected(self):
        state = candidate(216)
        state["cumulative_counters"]["updates"] += 48
        with self.assertRaises(a.AuditError):
            meta(state)

    def test_decision_count_drift_rejected(self):
        state = candidate(216)
        state["counters"]["environment_decisions"] += 1
        with self.assertRaises(a.AuditError):
            meta(state)

    def test_entry_nonzero_local_counters_rejected(self):
        state = candidate(204)
        state["counters"]["updates"] = 1
        with self.assertRaises(a.AuditError):
            meta(state, 204)

    def test_wall_formula_drift_rejected(self):
        state = candidate(216)
        state["cumulative_counters"] = dict(state["cumulative_counters"])
        state["cumulative_successful_ancestor_and_completed_campaign_cost_seconds"] += 1.0
        with self.assertRaises(a.AuditError):
            meta(state)

    def test_nonfinite_wall_rejected(self):
        state = candidate(216)
        state["current_iteration_observed_outer_seconds"] = float("nan")
        with self.assertRaises(a.AuditError):
            meta(state)

    def _prefix_fixture(self, future_frames=999, raw_frames=None):
        runner = type("R", (), {})()
        runner.validate_episode_journal = lambda rows, initial: {"next_episode_indices": [i + 1 for i in PARENT_NEXT]}
        state = candidate(216)
        state["abandoned_current_episodes"] = [{"slot": s, "seed": {"slot": s, "episode": s}, "gameplay_frames": 5} for s in range(64)]
        state["counters"]["raw_frames"] = 320 if raw_frames is None else raw_frames
        journal = [{"kind": "initial", "info": []}]
        journal += [{"kind": "abandoned_parent_episode", "info": {"slot": s}} for s in range(64)]
        journal += [{"kind": "completed", "phase_update": 228, "info": {"gameplay_frames": future_frames}}]
        return runner, state, journal

    def test_prefix_journal_excludes_future_events(self):
        runner, state, journal = self._prefix_fixture(future_frames=999)
        a.validate_prefix_journal(journal, 216, runner, PARENT_NEXT, state)

    def test_prefix_journal_conservation_drift_rejected(self):
        runner, state, journal = self._prefix_fixture(raw_frames=321)
        with self.assertRaises(a.AuditError):
            a.validate_prefix_journal(journal, 216, runner, PARENT_NEXT, state)

    def test_choose_best_tie_below_baseline_retains(self):
        self.assertIsNone(a.choose_best({204: 1921.171875, 228: 1921.171874}))

    def test_output_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "out.json"
            target.write_text("{}")
            with self.assertRaises(FileExistsError):
                with target.open("x") as stream:
                    stream.write("x")


if __name__ == "__main__":
    unittest.main()
