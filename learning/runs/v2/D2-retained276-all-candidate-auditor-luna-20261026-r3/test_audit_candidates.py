"""CPU-only controls for the retained-276 continuation auditor (276 -> 348).

Positive controls read the accepted parent checkpoint and the accepted parent 276 evaluation.
Negative controls mutate deep copies of a synthetic entry state built from that real parent, and
mutate copies of the real parent-276 certificate. No MPS, no training writes, no game runs.
Run: PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=<prep>/empty-pycache python -B -m unittest test_audit_candidates
The live lease is not checked here (enforce_lease=False); the audit and wrapper always check it.
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
        runner, reg, config = a.load_frozen(enforce_lease=False)
        ckpt, survival_gate, identity_hash = a.import_runtime(reg)
        _CACHE.update(a.build_context(runner, reg, config, ckpt, survival_gate, identity_hash, [], []))
    return _CACHE


def parent_eval_cert():
    """Accepted parent 276 certificate, re-labelled as an entry candidate certificate for validator input."""
    base, _ = a.stable_json(a.PARENT_RUN / "development-000276.json")
    cert = copy.deepcopy(base)
    cert["phase_update"], cert["local_update"] = a.PHASE_START, 0
    cert["checkpoint"], cert["checkpoint_sha256"] = "checkpoint-000276-candidate.pt", a.PARENT_SHA
    side = {"checkpoint_sha256": a.PARENT_SHA, "eligibility_status": "provisional_pending_parent_terminal_receipt",
            "training_eligible": False, "promoted": False}
    rows, _ = a.parse_journal(a.read_stable(a.PARENT_RUN / "development-000276.jsonl"), strict=True)
    return cert, side, rows


def entry_state(c):
    """Synthetic entry candidate: exact parent model, Adam, and RNG; zero local counters; 276 identity."""
    parent, reg = c["parent"], c["reg"]
    identity = {"version": "teacher_identity_v3", "run_id": a.RUN_ID, "phase": "D2",
                "phase_update_start": a.PHASE_START, "phase_update_end": a.PHASE_END, "run_seed": a.RUN_SEED,
                "config": c["config"], "parent_checkpoint_sha256": a.PARENT_SHA,
                "parent_terminal_receipt_sha256": a.PARENT_RECEIPT_SHA, "parent_config_sha256": a.CONFIG_SHA,
                "policy_sha256": a.POLICY_SHA, "registration_sha256": a.REG_SHA,
                "architecture": parent["identity"]["architecture"]}
    wall = 12.5
    return {"version": "teacher_checkpoint_v1", "schema": "d2_training_v3_checkpoint_v1", "resume_mode": "fresh_env",
            "tag": "candidate", "phase": "D2", "eligibility_status": "provisional_pending_parent_terminal_receipt",
            "training_eligible": False, "promoted": False, "parent_sha256": a.PARENT_SHA, "identity": identity,
            "identity_sha256": c["identity_hash"](identity), "config_sha256": a.CONFIG_SHA, "policy_sha256": a.POLICY_SHA,
            "native_sha256": a.NEW_NATIVE_SHA, "run_seed": a.RUN_SEED, "runtime_sha256": reg["runtime_sha256"],
            "registration_sha256": a.REG_SHA, "model": copy.deepcopy(parent["model"]),
            "optimizer": copy.deepcopy(parent["optimizer"]), "rng": copy.deepcopy(parent["rng"]),
            "counters": dict(a.ENTRY_ZERO), "inherited_counters": dict(parent["cumulative_counters"]),
            "cumulative_counters": dict(parent["cumulative_counters"]), "phase_update": a.PHASE_START, "local_update": 0,
            "selected_parent_checkpoint_trajectory_baseline_seconds": a.SELECTED_TRAJECTORY_BASELINE,
            "parent_completed_campaign_cost_baseline_seconds": a.CAMPAIGN_COST_BASELINE,
            "current_iteration_observed_outer_seconds": wall,
            "cumulative_selected_checkpoint_trajectory_wall_seconds": a.SELECTED_TRAJECTORY_BASELINE + wall,
            "cumulative_successful_ancestor_and_completed_campaign_cost_seconds": a.CAMPAIGN_COST_BASELINE + wall,
            "update_progress": {"complete": True, "in_update": False, "completed_updates": 0},
            "next_episode_indices": list(parent["next_episode_indices"]),
            "abandoned_current_episodes": copy.deepcopy(parent["abandoned_current_episodes"]),
            "parent_abandoned_current_episodes": copy.deepcopy(parent["abandoned_current_episodes"]),
            "parent_run_id": a.PARENT_RUN_ID, "parent_registration_sha256": a.PARENT_REGISTRATION_SHA,
            "parent_checkpoint_sha256": a.PARENT_SHA}


def rehash(c, state):
    state["identity_sha256"] = c["identity_hash"](state["identity"])
    return state


class PositiveControls(unittest.TestCase):
    def test_constants_bind_frozen_runner(self):
        runner = ctx()["runner"]
        self.assertEqual((a.PHASE_START, a.PHASE_END), (runner.PHASE_START, runner.PHASE_END))
        self.assertEqual(tuple(runner.EVALUATION_UPDATES), a.UPDATES)
        self.assertEqual((a.NEW_UPDATES, runner.EXPECTED_TOTAL), (72, 396))
        self.assertEqual(a.RUN_ID, runner.RUN_ID)
        self.assertEqual(a.SELECTED_TRAJECTORY_BASELINE, runner.SELECTED_TRAJECTORY_BASELINE_SECONDS)
        self.assertEqual(a.CAMPAIGN_COST_BASELINE, runner.COMPLETED_CAMPAIGN_COST_BASELINE_SECONDS)
        self.assertEqual(a.POLICY_SHA, runner.POLICY_SHA)
        self.assertEqual(a.PARENT_RECEIPT_SHA, runner.PARENT_RECEIPT_SHA)
        self.assertEqual(a.PARENT_REGISTRATION_SHA, runner.PARENT_REGISTRATION_SHA)
        self.assertEqual(a.NEW_NATIVE_SHA, runner.NEW_NATIVE_SHA)
        self.assertEqual(a.SEED_COHORT[0], 0xD0000000)
        self.assertEqual(len(a.SEED_COHORT), 64)

    def test_registration_and_outputs_bound(self):
        c = ctx()
        self.assertEqual(a.sha_file(a.REG_PATH), a.REG_SHA)
        self.assertEqual(c["reg"]["expected_outputs"], a.expected_outputs())
        self.assertEqual(len(c["reg"]["expected_outputs"]), 9 + 4 * 7)
        self.assertEqual(c["reg"]["run_seed"], a.RUN_SEED)

    def test_real_parent_endpoint_accepted_by_frozen_validator(self):
        c = ctx()
        self.assertEqual(c["parent"]["cumulative_counters"]["updates"], a.PARENT_TOTAL_UPDATES)
        self.assertEqual(c["parent"]["cumulative_counters"]["optimizer_steps"], 40352)
        self.assertEqual(c["parent"]["phase_update"], a.PHASE_START)

    def test_accepted_prior_metrics_match_frozen_ppo_schema(self):
        c = ctx()
        ppo_path = a.Path(c["reg"]["runtime_root"]) / "dodge_rl/ppo.py"
        ppo_source = a.read_stable(ppo_path).decode("utf-8")
        self.assertEqual(a.sha_file(ppo_path), c["reg"]["pins"][str(ppo_path)])
        self.assertIn('"transitions": count', ppo_source)
        self.assertIn('metrics["gradient_alignment_diagnostics"] = alignment_result', ppo_source)
        path = a.ROOT / "learning/runs/v2/D2-retained204-lr1e4-20261026-r1/training-metrics.jsonl"
        metrics, _ = a.parse_journal(a.read_stable(path), strict=True)
        self.assertEqual(len(metrics), 72)
        prior_audit, _ = a.stable_json(
            a.ROOT / "learning/runs/v2/D2-retained204-lr1e4-parent-terminal-audit-20261026-r1/full-audit.json")
        self.assertEqual(prior_audit["audit"]["metrics_consumed_sha256"], a.sha_file(path))
        for row in metrics:
            value = row["metrics"]
            self.assertEqual(value["transitions"], a.DECISIONS_PER_UPDATE)
            self.assertIn("gradient_alignment_diagnostics", value)
            c["runner"].validate_gradient_alignment(value["gradient_alignment_diagnostics"])

    def test_parent_276_evaluation_is_the_entry_baseline(self):
        cert, _, rows = parent_eval_cert()
        a.validate_entry_against_parent(cert, rows)
        self.assertEqual(sum(r["alive_frames"] for r in rows) / 64, a.BASELINE_MEAN_ALIVE)

    def test_real_parent_276_certificate_passes_validator(self):
        c = ctx()
        cert, side, rows = parent_eval_cert()
        summary = a.validate_certificate(c, a.PHASE_START, cert, side, rows, cert["checkpoint"], a.PARENT_SHA)
        self.assertEqual(summary["mean_alive_frames"], a.BASELINE_MEAN_ALIVE)
        self.assertEqual(summary["deaths"], 64)
        self.assertEqual(summary["competence_passed"], False)

    def test_synthetic_entry_state_passes_identity_saved_lr_and_entry_checks(self):
        c = ctx()
        state = entry_state(c)
        a.validate_state_identity(c, a.PHASE_START, state)
        a.validate_entry_state(c, state)
        a.check_saved_lr(state)

    def test_choose_best_strict_and_tie_keeps_earlier(self):
        base = a.BASELINE_MEAN_ALIVE
        self.assertIsNone(a.choose_best({288: base, 300: base - 1}))
        self.assertEqual(a.choose_best({288: base + 5, 300: base + 9, 312: base + 9}), 300)
        self.assertEqual(a.choose_best({288: base + 1}), 288)

    def test_retained_best_is_monotone_not_latest_endpoint(self):
        base = a.BASELINE_MEAN_ALIVE
        means = {288: base + 100, 300: base + 50, 312: base + 100, 324: base + 300, 336: base + 250, 348: base + 300}
        ordered = sorted(means.items())
        self.assertEqual(a.retained_best(ordered), 324)
        self.assertEqual(a.choose_best(means), 324)
        self.assertNotEqual(a.retained_best(ordered), 348)

    def test_retained_best_tie_with_baseline_keeps_entry(self):
        self.assertIsNone(a.retained_best([(288, a.BASELINE_MEAN_ALIVE)]))

    def test_partial_journal_tail_prefix_mode_only(self):
        raw = b'{"a": 1}\n{"b": 2}\n{"c"'
        rows, consumed = a.parse_journal(raw, strict=False)
        self.assertEqual(rows, [{"a": 1}, {"b": 2}])
        self.assertEqual(consumed, b'{"a": 1}\n{"b": 2}\n')
        with self.assertRaisesRegex(a.AuditError, "incomplete"):
            a.parse_journal(raw, strict=True)

    def test_cumulative_composition_from_accepted_parent(self):
        c = ctx()
        local = {"updates": 72, "optimizer_steps": 9216, "environment_decisions": 1179648, "raw_frames": 4713702}
        total = c["runner"].continuation_cumulative_counters(c["parent"]["cumulative_counters"], local)
        self.assertEqual(total["updates"], a.PARENT_TOTAL_UPDATES + 72)
        self.assertEqual(total["optimizer_steps"], 40352 + 9216)
        self.assertEqual(total["environment_decisions"], 5308416 + 1179648)
        self.assertEqual(total["raw_frames"], 21202529 + 4713702)

    def test_effective_lr_record_matches_parent_without_mutation(self):
        c = ctx()
        n = len(c["parent"]["optimizer"]["param_groups"])
        fp = c["runner"].fingerprint(c["parent"]["optimizer"])
        record = {"parent_group_lrs": [a.LR_ARM] * n, "restored_group_lrs": [a.LR_ARM] * n,
                  "expected_learning_rate": a.LR_ARM, "mutation_applied": False,
                  "parent_optimizer_fingerprint": fp, "restored_optimizer_fingerprint": fp}
        a.validate_effective_lr_record(c["runner"], record, c["parent"])


class EntryNegativeControls(unittest.TestCase):
    def assertRejects(self, state, pattern, update=a.PHASE_START):
        c = ctx()
        with self.assertRaisesRegex(a.AuditError, pattern):
            a.validate_state_identity(c, update, state)
            a.validate_entry_state(c, state)

    def test_run_seed_drift_rejected(self):
        c = ctx()
        s = entry_state(c)
        s["run_seed"] = a.RUN_SEED + 1
        self.assertRejects(s, "registration/config/policy/native/runtime/seed")

    def test_identity_hash_forgery_rejected(self):
        c = ctx()
        s = entry_state(c)
        s["identity"]["run_seed"] += 1
        self.assertRejects(s, "Identity hash differs")

    def test_identity_parent_receipt_drift_rejected(self):
        c = ctx()
        s = rehash(c, entry_state(c))
        s["identity"]["parent_terminal_receipt_sha256"] = "00" * 32
        s = rehash(c, s)
        self.assertRejects(s, "Embedded identity")

    def test_identity_phase_window_drift_rejected(self):
        c = ctx()
        s = entry_state(c)
        s["identity"]["phase_update_end"] = 336
        s = rehash(c, s)
        self.assertRejects(s, "Embedded identity")

    def test_parent_identity_drift_rejected(self):
        c = ctx()
        s = entry_state(c)
        s["parent_registration_sha256"] = "00" * 32
        self.assertRejects(s, "Candidate parent identity differs")

    def test_nonzero_entry_counters_rejected(self):
        c = ctx()
        s = entry_state(c)
        s["counters"] = {**a.ENTRY_ZERO, "updates": 1}
        self.assertRejects(s, "zero local counters")

    def test_entry_nonzero_raw_frames_rejected(self):
        c = ctx()
        s = entry_state(c)
        s["counters"] = {**a.ENTRY_ZERO, "raw_frames": 5}
        self.assertRejects(s, "zero local counters")

    def test_cumulative_base_drift_rejected(self):
        c = ctx()
        s = entry_state(c)
        s["cumulative_counters"] = {**s["cumulative_counters"], "updates": a.PARENT_TOTAL_UPDATES + 1}
        self.assertRejects(s, "Cumulative counter base")

    def test_wall_formula_drift_rejected(self):
        c = ctx()
        s = entry_state(c)
        s["cumulative_selected_checkpoint_trajectory_wall_seconds"] += 1.0
        self.assertRejects(s, "Wall formula differs")

    def test_parent_3352_baseline_rejected(self):
        c = ctx()
        s = entry_state(c)
        s["selected_parent_checkpoint_trajectory_baseline_seconds"] = 3352.0462366251204
        self.assertRejects(s, "Wall baselines differ")

    def test_wrong_saved_group_lr_rejected(self):
        c = ctx()
        s = entry_state(c)
        s["optimizer"]["param_groups"][0]["lr"] = 0.0003
        with self.assertRaisesRegex(a.AuditError, "LR"):
            a.check_saved_lr(s)

    def test_integer_lr_rejected(self):
        c = ctx()
        s = entry_state(c)
        s["optimizer"]["param_groups"][0]["lr"] = 1
        with self.assertRaisesRegex(a.AuditError, "LR"):
            a.check_saved_lr(s)

    def test_adam_moment_drift_rejected(self):
        c = ctx()
        s = entry_state(c)
        first = next(iter(s["optimizer"]["state"].values()))
        first["exp_avg"].add_(1.0)
        with self.assertRaisesRegex(a.AuditError, "Entry Adam"):
            a.validate_entry_state(c, s)

    def test_model_drift_rejected(self):
        c = ctx()
        s = entry_state(c)
        key = next(k for k, v in s["model"].items() if v.is_floating_point())
        s["model"][key].add_(1e-3)
        with self.assertRaisesRegex(a.AuditError, "Entry model or RNG"):
            a.validate_entry_state(c, s)

    def test_nonfinite_model_tensor_rejected(self):
        c = ctx()
        s = entry_state(c)
        key = next(k for k, v in s["model"].items() if v.is_floating_point())
        s["model"][key].view(-1)[0] = float("nan")
        with self.assertRaisesRegex(a.AuditError, "Nonfinite tensor"):
            a.finite_tensors(s["model"])

    def test_nonfinite_adam_tensor_rejected(self):
        c = ctx()
        s = entry_state(c)
        first = next(iter(s["optimizer"]["state"].values()))
        first["exp_avg_sq"].view(-1)[0] = float("inf")
        with self.assertRaisesRegex(a.AuditError, "Nonfinite tensor"):
            a.finite_tensors(s["optimizer"])

    def test_entry_restoration_forged_match_rejected(self):
        c = ctx()
        forged = {"matched": {"model": True, "Adam": False, "RNG": True}, "parent_sha256": a.PARENT_SHA,
                  "components": {}}
        with self.assertRaisesRegex(a.AuditError, "Entry restoration"):
            a.audit_entry_restoration(c, forged)

    def test_effective_lr_mutation_flag_rejected(self):
        c = ctx()
        n = len(c["parent"]["optimizer"]["param_groups"])
        fp = c["runner"].fingerprint(c["parent"]["optimizer"])
        record = {"parent_group_lrs": [a.LR_ARM] * n, "restored_group_lrs": [a.LR_ARM] * n,
                  "expected_learning_rate": a.LR_ARM, "mutation_applied": True,
                  "parent_optimizer_fingerprint": fp, "restored_optimizer_fingerprint": fp}
        with self.assertRaisesRegex(a.AuditError, "Effective learning-rate record"):
            a.validate_effective_lr_record(c["runner"], record, c["parent"])

    def test_effective_lr_fingerprint_drift_rejected(self):
        c = ctx()
        n = len(c["parent"]["optimizer"]["param_groups"])
        record = {"parent_group_lrs": [a.LR_ARM] * n, "restored_group_lrs": [a.LR_ARM] * n,
                  "expected_learning_rate": a.LR_ARM, "mutation_applied": False,
                  "parent_optimizer_fingerprint": "00" * 32, "restored_optimizer_fingerprint": "00" * 32}
        with self.assertRaisesRegex(a.AuditError, "fingerprints"):
            a.validate_effective_lr_record(c["runner"], record, c["parent"])


class CertificateNegativeControls(unittest.TestCase):
    def test_entry_row_drift_against_parent_rejected(self):
        cert, _, rows = parent_eval_cert()
        cert["evaluation"]["rows"][0]["alive_frames"] += 1
        with self.assertRaisesRegex(a.AuditError, "certificate rows differ"):
            a.validate_entry_against_parent(cert, rows)

    def test_entry_jsonl_drift_against_parent_rejected(self):
        cert, _, rows = parent_eval_cert()
        rows[3]["score"] += 1
        with self.assertRaisesRegex(a.AuditError, "JSONL rows differ"):
            a.validate_entry_against_parent(cert, rows)

    def test_certificate_jsonl_row_drift_rejected(self):
        c = ctx()
        cert, side, rows = parent_eval_cert()
        rows[0]["alive_frames"] += 1
        with self.assertRaisesRegex(a.AuditError, "JSONL rows differ"):
            a.validate_certificate(c, a.PHASE_START, cert, side, rows, cert["checkpoint"], a.PARENT_SHA)

    def test_certificate_training_eligible_rejected(self):
        c = ctx()
        cert, side, rows = parent_eval_cert()
        cert["training_eligible"] = True
        with self.assertRaisesRegex(a.AuditError, "eligibility flags"):
            a.validate_certificate(c, a.PHASE_START, cert, side, rows, cert["checkpoint"], a.PARENT_SHA)

    def test_certificate_competence_flip_rejected(self):
        c = ctx()
        cert, side, rows = parent_eval_cert()
        cert["competence_passed"] = True
        with self.assertRaisesRegex(a.AuditError, "Recorded competence flag"):
            a.validate_certificate(c, a.PHASE_START, cert, side, rows, cert["checkpoint"], a.PARENT_SHA)

    def test_certificate_seed_cohort_drift_rejected(self):
        c = ctx()
        cert, side, rows = parent_eval_cert()
        rows[0]["seed"] += 1000
        cert["evaluation"]["rows"][0]["seed"] += 1000
        with self.assertRaisesRegex(a.AuditError, "cohort|JSONL"):
            a.validate_certificate(c, a.PHASE_START, cert, side, rows, cert["checkpoint"], a.PARENT_SHA)

    def test_certificate_objective_drift_rejected(self):
        c = ctx()
        cert, side, rows = parent_eval_cert()
        seed = rows[5]["seed"]
        for row in rows + cert["evaluation"]["rows"]:
            if row["seed"] == seed:
                row["objective_return"] += 0.5
        with self.assertRaisesRegex(a.AuditError, "Objective formula"):
            a.validate_certificate(c, a.PHASE_START, cert, side, rows, cert["checkpoint"], a.PARENT_SHA)

    def test_certificate_death_cause_drift_rejected(self):
        c = ctx()
        cert, side, rows = parent_eval_cert()
        cert["evaluation"]["death_causes"]["normal_enemy"] += 1
        with self.assertRaisesRegex(a.AuditError, "Death-cause aggregate"):
            a.validate_certificate(c, a.PHASE_START, cert, side, rows, cert["checkpoint"], a.PARENT_SHA)

    def test_sidecar_eligibility_drift_rejected(self):
        c = ctx()
        cert, side, rows = parent_eval_cert()
        side["promoted"] = True
        with self.assertRaisesRegex(a.AuditError, "Sidecar flags"):
            a.validate_certificate(c, a.PHASE_START, cert, side, rows, cert["checkpoint"], a.PARENT_SHA)


class RuntimeOriginNegativeControls(unittest.TestCase):
    def test_module_outside_runtime_rejected(self):
        c = ctx()
        import types
        reg = c["reg"]
        fake = types.SimpleNamespace(__file__="/tmp/not-runtime/dodge_rl/__init__.py")
        with self.assertRaisesRegex(a.AuditError, "outside runtime root"):
            a.runtime_origins(reg, a.Path(reg["runtime_root"]).resolve(), {"dodge_rl": fake})

    def test_unpinned_runtime_member_rejected(self):
        c = ctx()
        import types
        reg = c["reg"]
        runtime = a.Path(reg["runtime_root"]).resolve()
        fake = types.SimpleNamespace(__file__=str(runtime / "dodge_rl/checkpoints.py"))
        forged = copy.deepcopy(reg)
        forged["runtime_continuity"]["member_sha256"]["dodge_rl/checkpoints.py"] = "00" * 32
        with self.assertRaisesRegex(a.AuditError, "not a pinned runtime member"):
            a.runtime_origins(forged, runtime, {"dodge_rl.checkpoints": fake})

    def test_wrong_native_digest_rejected(self):
        import sys
        c = ctx()
        reg = copy.deepcopy(c["reg"])
        runtime = a.Path(reg["runtime_root"]).resolve()
        reg["runtime_continuity"]["member_sha256"]["dodge_rl/_native.cpython-312-darwin.so"] = "11" * 32
        with self.assertRaisesRegex(a.AuditError, "not a pinned runtime member"):
            a.runtime_origins(reg, runtime, sys.modules)


class BytecodeAndLauncherControls(unittest.TestCase):
    def test_prefix_is_registered_empty_directory(self):
        self.assertEqual(str(a.PREP / "empty-pycache"), ctx()["reg"]["import_policy"]["pycache_prefix"])
        self.assertEqual(list((a.PREP / "empty-pycache").iterdir()), [])

    def test_frozen_launcher_binds_audited_runner(self):
        c = ctx()
        launcher = a.load_pinned_module("execute_once_frozen", a.PREP / "execute_once.py", a.LAUNCHER_SHA)
        self.assertIs(launcher.r, c["runner"])

    def test_pinned_source_digest_mismatch_rejected(self):
        with self.assertRaisesRegex(a.AuditError, "digest differs"):
            a.load_pinned_module("bogus_runner", a.PREP / "runner.py", "00" * 32)


def later_candidate(c, update=288):
    """Synthetic 288 candidate with a real-shaped metric chain (12 updates of 128 steps each)."""
    local = update - a.PHASE_START
    rows, steps = [], 0
    for k in range(1, local + 1):
        steps += 128
        counters = {"updates": k, "optimizer_steps": steps, "environment_decisions": k * a.DECISIONS_PER_UPDATE,
                    "raw_frames": 0}
        progress = {"completed_updates": k, "complete": True, "in_update": False}
        rows.append({"phase_update": a.PHASE_START + k, "local_update": k, "metrics": {"optimizer_steps": 128,
                     "transitions": a.DECISIONS_PER_UPDATE}, "counters": counters, "update_progress": progress})
    c2 = dict(c)
    c2["metrics"] = rows
    c2["rows_by_phase"] = {r["phase_update"]: [r] for r in rows}
    state = entry_state(c)
    state["phase_update"], state["local_update"] = update, local
    state["counters"] = dict(rows[-1]["counters"])
    state["update_progress"] = dict(rows[-1]["update_progress"])
    state["cumulative_counters"] = c["runner"].continuation_cumulative_counters(c["parent"]["cumulative_counters"],
                                                                              state["counters"])
    wall = 900.0
    state["current_iteration_observed_outer_seconds"] = wall
    state["cumulative_selected_checkpoint_trajectory_wall_seconds"] = a.SELECTED_TRAJECTORY_BASELINE + wall
    state["cumulative_successful_ancestor_and_completed_campaign_cost_seconds"] = a.CAMPAIGN_COST_BASELINE + wall
    return c2, state


class LaterCandidateControls(unittest.TestCase):
    def test_later_candidate_counters_and_cumulative_pass(self):
        c2, state = later_candidate(ctx())
        a.validate_state_identity(c2, 288, state)
        self.assertEqual(state["cumulative_counters"]["updates"], a.PARENT_TOTAL_UPDATES + 12)

    def test_later_candidate_missing_metric_row_rejected(self):
        c2, state = later_candidate(ctx())
        c2["rows_by_phase"] = {}
        with self.assertRaisesRegex(a.AuditError, "metric row count"):
            a.validate_state_identity(c2, 288, state)

    def test_later_candidate_counter_drift_rejected(self):
        c2, state = later_candidate(ctx())
        state["counters"]["optimizer_steps"] += 1
        with self.assertRaisesRegex(a.AuditError, "do not match its metric row"):
            a.validate_state_identity(c2, 288, state)

    def test_later_candidate_progress_drift_rejected(self):
        c2, state = later_candidate(ctx())
        state["update_progress"]["completed_updates"] = 11
        with self.assertRaisesRegex(a.AuditError, "Update progress differs|do not match"):
            a.validate_state_identity(c2, 288, state)

    def test_later_candidate_cumulative_base_drift_rejected(self):
        c2, state = later_candidate(ctx())
        state["cumulative_counters"]["environment_decisions"] += 1
        with self.assertRaisesRegex(a.AuditError, "Cumulative counter base"):
            a.validate_state_identity(c2, 288, state)

    def test_later_candidate_wall_formula_drift_rejected(self):
        c2, state = later_candidate(ctx())
        state["cumulative_successful_ancestor_and_completed_campaign_cost_seconds"] -= 2.0
        with self.assertRaisesRegex(a.AuditError, "Wall formula differs"):
            a.validate_state_identity(c2, 288, state)

    def test_later_candidate_entry_only_fields_not_reused(self):
        c2, state = later_candidate(ctx())
        state["phase_update"] = 300
        with self.assertRaisesRegex(a.AuditError, "phase/local update differs"):
            a.validate_state_identity(c2, 288, state)

    def test_selection_ignores_latest_endpoint_when_retained_is_higher(self):
        base = a.BASELINE_MEAN_ALIVE
        means = {288: base + 40, 300: base + 10, 312: base + 90, 324: base + 20, 336: base + 5, 348: base - 1}
        self.assertEqual(a.choose_best(means), 312)
        self.assertEqual(a.retained_best(sorted(means.items())), 312)
        self.assertNotEqual(a.retained_best(sorted(means.items())), 348)


if __name__ == "__main__":
    unittest.main()
