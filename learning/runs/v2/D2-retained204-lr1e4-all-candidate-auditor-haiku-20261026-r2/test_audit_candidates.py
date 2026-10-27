"""CPU-only controls for the retained-204 lr1e-4 auditor (r2).

Positive controls load the real accepted parent and published candidates read-only.
Negative controls mutate deep copies of those real states. No MPS, no training writes,
no game runs. Run with: python -B -m unittest test_audit_candidates (PYTHONPYCACHEPREFIX set).
"""
import copy
import json
import math
import unittest

import audit_candidates as a

_CACHE = {}


def ctx():
    """One frozen load per process: load_registration may run only once per interpreter."""
    if not _CACHE:
        runner, reg, config = a.load_frozen()
        ckpt, survival_gate, identity_hash = a.import_runtime(reg)
        journal_raw = (a.RUN / "training-episodes.jsonl").read_bytes()
        metrics_raw = (a.RUN / "training-metrics.jsonl").read_bytes()
        journal, _ = a.parse_journal(journal_raw, strict=False)
        metrics, _ = a.parse_journal(metrics_raw, strict=False)
        built = a.build_context(runner, reg, config, ckpt, survival_gate, identity_hash, journal, metrics)
        states = {}
        for update in (a.PHASE_START, 216):
            paths = a.expected_candidate_paths(update)
            digest = a.sha_file(paths["checkpoint"])
            state = ckpt.load_checkpoint(paths["checkpoint"], expected_sha256=digest)
            ckpt.require_complete_update(state)
            states[update] = state
        built["states"] = states
        built["entry_cert"], _ = a.stable_json(a.RUN / "development-000204.json")
        built["entry_rows"], _ = a.parse_journal(a.read_stable(a.RUN / "development-000204.jsonl"), strict=True)
        built["launcher"] = a.load_pinned_module("execute_once_frozen", a.PREP / "execute_once.py", a.LAUNCHER_SHA)
        _CACHE.update(built)
    return _CACHE


def lr_record():
    return a.stable_json(a.RUN / "lr-transition.json")[0]


class PositiveControls(unittest.TestCase):
    def test_frozen_runner_binds_verified_helper(self):
        c = ctx()
        self.assertIsNotNone(c["runner"]._VERIFIED_TRANSITION)
        self.assertIs(c["launcher"].r, c["runner"])

    def test_validator_helper_call_on_real_entry_state(self):
        # Same call as the frozen validate_outputs line: r._VERIFIED_TRANSITION.assert_saved_optimizer_lr(embedded, 0.0001).
        c = ctx()
        c["launcher"].r._VERIFIED_TRANSITION.assert_saved_optimizer_lr(c["states"][a.PHASE_START], 0.0001)

    def test_lr_record_recomputed_from_real_cpu_optimizers(self):
        c = ctx()
        recomputed = a.lr_transition_recomputed(c, c["states"][a.PHASE_START])
        self.assertEqual(recomputed, lr_record())
        self.assertEqual(recomputed["parent_optimizer_fingerprint"], "4073bfade1694b2ca0e35cb702fa321c3f7e1f24f04533d7bd4082b40b903b8c")
        self.assertEqual(recomputed["effective_optimizer_fingerprint"], "d62b1eb7afca91585b1440618d3c66bf0cf4a48c9fa1b542d98f1e2ed4780b06")
        self.assertEqual(recomputed["parent_optimizer_fingerprint_excluding_lr"], recomputed["effective_optimizer_fingerprint_excluding_lr"])

    def test_entry_restoration_binds_parent_components(self):
        c = ctx()
        a.audit_entry_restoration(c, a.stable_json(a.RUN / "entry-restoration.json")[0])

    def test_entry_cert_matches_accepted_204_source(self):
        c = ctx()
        a.validate_entry_against_base(c, c["entry_cert"], c["entry_rows"])

    def test_candidate_216_passes_all_gates(self):
        c = ctx()
        state = c["states"][216]
        a.validate_state_identity(c, 216, state)
        a.validate_resume(c, 216, state)
        cert, _ = a.stable_json(a.RUN / "development-000216.json")
        rows, _ = a.parse_journal(a.read_stable(a.RUN / "development-000216.jsonl"), strict=True)
        side, _ = a.stable_json(a.RUN / "checkpoint-000216-candidate.pt.json")
        summary = a.validate_certificate(c, 216, cert, side, rows, "checkpoint-000216-candidate.pt",
                                         a.sha_file(a.RUN / "checkpoint-000216-candidate.pt"), state)
        self.assertAlmostEqual(summary["mean_alive_frames"], 1577.703125)

    def test_choose_best_strict_and_tie_keeps_baseline(self):
        self.assertEqual(a.choose_best({204: 1921.171875, 216: 1577.0, 228: 1950.0, 240: 1940.0}), 228)
        self.assertIsNone(a.choose_best({204: 1921.171875, 228: 1921.171875}))
        self.assertIsNone(a.choose_best({204: 1921.171875, 228: 1921.171874}))

    def test_partial_journal_tail_prefix_mode_only(self):
        raw = b'{"kind": "initial"}\n{"kind": "comp'
        records, consumed = a.parse_journal(raw, strict=False)
        self.assertEqual(records, [{"kind": "initial"}])
        self.assertEqual(consumed, b'{"kind": "initial"}\n')
        with self.assertRaises(a.AuditError):
            a.parse_journal(raw, strict=True)


class NegativeControls(unittest.TestCase):
    def mutated(self, update=216):
        return copy.deepcopy(ctx()["states"][update])

    def test_forged_lr_record_fingerprint_rejected(self):
        c = ctx()
        forged = dict(lr_record(), effective_optimizer_fingerprint="0" * 64)
        self.assertNotEqual(a.lr_transition_recomputed(c, c["states"][a.PHASE_START]), forged)
        with self.assertRaises(a.AuditError):
            a.audit_lr_record(c, c["states"][a.PHASE_START], forged)

    def test_forged_lr_record_identity_rejected(self):
        c = ctx()
        forged = dict(lr_record(), candidate_receipt_sha256="1" * 64)
        with self.assertRaises(a.AuditError):
            a.audit_lr_record(c, c["states"][a.PHASE_START], forged)

    def test_adam_moment_mutation_rejected_by_helper(self):
        c = ctx()
        entry = self.mutated(a.PHASE_START)
        first = next(iter(entry["optimizer"]["state"].values()))
        first["exp_avg"].add_(1e-3)
        with self.assertRaises(ValueError):
            a.lr_transition_recomputed(c, entry)

    def test_entry_wrong_lr_rejected(self):
        c = ctx()
        entry = self.mutated(a.PHASE_START)
        entry["optimizer"]["param_groups"][0]["lr"] = 0.0003
        with self.assertRaises(ValueError):
            c["lr_helper"].assert_saved_optimizer_lr(entry, 0.0001)

    def test_entry_restoration_forged_digest_rejected(self):
        c = ctx()
        forged, _ = a.stable_json(a.RUN / "entry-restoration.json")
        forged["components"]["Adam"]["expected_sha256"] = "2" * 64
        with self.assertRaises(a.AuditError):
            a.audit_entry_restoration(c, forged)

    def test_wrong_native_sha_rejected(self):
        c = ctx()
        state = self.mutated(216)
        state["native_sha256"] = "3" * 64
        with self.assertRaises(a.AuditError):
            a.validate_state_identity(c, 216, state)

    def test_run_seed_drift_rejected(self):
        c = ctx()
        state = self.mutated(216)
        state["run_seed"] = state["run_seed"] + 1
        with self.assertRaises(a.AuditError):
            a.validate_state_identity(c, 216, state)

    def test_identity_hash_forgery_rejected(self):
        c = ctx()
        state = self.mutated(216)
        state["identity"]["phase_update_end"] = 264
        with self.assertRaises(a.AuditError):
            a.validate_state_identity(c, 216, state)

    def test_identity_config_drift_rejected(self):
        c = ctx()
        state = self.mutated(216)
        state["identity"]["config"] = {**state["identity"]["config"], "device": "cpu"}
        state["identity_sha256"] = c["identity_hash"](state["identity"])
        with self.assertRaises(a.AuditError):
            a.validate_state_identity(c, 216, state)

    def test_parent_300_base_rejected(self):
        c = ctx()
        state = self.mutated(216)
        state["cumulative_counters"]["updates"] += 48
        with self.assertRaises(a.AuditError):
            a.validate_state_identity(c, 216, state)

    def test_counter_drift_from_metric_row_rejected(self):
        c = ctx()
        state = self.mutated(216)
        state["counters"]["environment_decisions"] += 1
        with self.assertRaises(a.AuditError):
            a.validate_state_identity(c, 216, state)

    def test_entry_nonzero_local_counters_rejected(self):
        c = ctx()
        state = self.mutated(a.PHASE_START)
        state["counters"]["updates"] = 1
        with self.assertRaises(a.AuditError):
            a.validate_state_identity(c, a.PHASE_START, state)

    def test_wall_formula_drift_rejected(self):
        c = ctx()
        state = self.mutated(216)
        state["cumulative_successful_ancestor_and_completed_campaign_cost_seconds"] += 1.0
        with self.assertRaises(a.AuditError):
            a.validate_state_identity(c, 216, state)

    def test_next_index_out_of_u64_rejected(self):
        c = ctx()
        state = self.mutated(216)
        state["next_episode_indices"][0] = 2**64
        with self.assertRaises(a.AuditError):
            a.validate_resume(c, 216, state)

    def test_abandoned_seed_lineage_drift_rejected(self):
        c = ctx()
        state = self.mutated(216)
        state["abandoned_current_episodes"][5]["seed"]["episode"] += 1
        with self.assertRaises(a.AuditError):
            a.validate_resume(c, 216, state)

    def test_abandoned_slot_duplicate_rejected(self):
        c = ctx()
        state = self.mutated(216)
        state["abandoned_current_episodes"][1]["slot"] = 0
        with self.assertRaises(a.AuditError):
            a.validate_resume(c, 216, state)

    def test_raw_frame_conservation_drift_rejected(self):
        c = ctx()
        state = self.mutated(216)
        state["counters"]["raw_frames"] += 1
        with self.assertRaises(a.AuditError):
            a.validate_resume(c, 216, state)

    def test_nonfinite_checkpoint_tensor_rejected(self):
        state = self.mutated(216)
        first = next(iter(state["model"].values()))
        first.view(-1)[0] = float("nan")
        with self.assertRaises(a.AuditError):
            a.finite_tensors(state["model"])

    def _cert_inputs(self):
        cert, _ = a.stable_json(a.RUN / "development-000216.json")
        rows, _ = a.parse_journal(a.read_stable(a.RUN / "development-000216.jsonl"), strict=True)
        side, _ = a.stable_json(a.RUN / "checkpoint-000216-candidate.pt.json")
        return copy.deepcopy(cert), copy.deepcopy(rows), side

    def _validate_cert(self, cert, rows, side):
        return a.validate_certificate(ctx(), 216, cert, side, rows, "checkpoint-000216-candidate.pt",
                                      a.sha_file(a.RUN / "checkpoint-000216-candidate.pt"), self.mutated(216))

    def test_jsonl_row_drift_rejected(self):
        cert, rows, side = self._cert_inputs()
        rows[3]["alive_frames"] += 1
        with self.assertRaises(a.AuditError):
            self._validate_cert(cert, rows, side)

    def test_objective_formula_drift_rejected(self):
        cert, rows, side = self._cert_inputs()
        for cert_row, row in zip(cert["evaluation"]["rows"], rows):
            cert_row["objective_return"] += 0.5
            row["objective_return"] += 0.5
        with self.assertRaises(a.AuditError):
            self._validate_cert(cert, rows, side)

    def test_both_boundary_flags_rejected(self):
        cert, rows, side = self._cert_inputs()
        cert["evaluation"]["rows"][0]["truncated"] = True
        rows[0] = cert["evaluation"]["rows"][0]
        with self.assertRaises(a.AuditError):
            self._validate_cert(cert, rows, side)

    def test_death_cause_aggregate_drift_rejected(self):
        cert, rows, side = self._cert_inputs()
        cert["evaluation"]["death_causes"]["normal_enemy"] += 1
        with self.assertRaises(a.AuditError):
            self._validate_cert(cert, rows, side)

    def test_seed_cohort_drift_rejected(self):
        cert, rows, side = self._cert_inputs()
        cert["evaluation"]["rows"][0]["seed"] += 1
        rows[0]["seed"] += 1
        with self.assertRaises(a.AuditError):
            self._validate_cert(cert, rows, side)

    def test_competence_flag_flip_rejected(self):
        cert, rows, side = self._cert_inputs()
        cert["competence_passed"] = True
        with self.assertRaises(a.AuditError):
            self._validate_cert(cert, rows, side)

    def test_sidecar_eligibility_drift_rejected(self):
        cert, rows, side = self._cert_inputs()
        side["promoted"] = True
        with self.assertRaises(a.AuditError):
            self._validate_cert(cert, rows, side)

    def test_entry_certificate_row_drift_rejected(self):
        c = ctx()
        cert = copy.deepcopy(c["entry_cert"])
        cert["evaluation"]["rows"][0]["score"] += 1.0
        with self.assertRaises(a.AuditError):
            a.validate_entry_against_base(c, cert, c["entry_rows"])

    def test_journal_consumed_prefix_is_stable_bytes(self):
        raw = b'{"kind": "initial"}\n'
        _, consumed = a.parse_journal(raw + b'{"kind": "compl', strict=False)
        self.assertEqual(consumed, raw)
        self.assertEqual(a.sha_bytes(raw), a.sha_bytes(consumed))


if __name__ == "__main__":
    unittest.main()
