"""Synthetic CPU controls for retained324 scheduled-auditor validators."""
from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

import binding_builder as bb
import lr_schedule
import schedule_contract as sc
import wrapper
import audit_candidates as auditor

OWN = Path(__file__).resolve().parent


def checkpoint(local: int, *, group_count: int = 2) -> dict:
    cumulative = sc.ORIGIN + local
    lr = sc.expected_lr(cumulative)
    return {
        "lr_schedule": {
            "schedule_origin_cumulative_update": sc.ORIGIN,
            "horizon_updates": sc.HORIZON,
            "completed_schedule_updates": local,
            "schedule_spec_sha256": lr_schedule.SCHEDULE_SPEC_SHA256,
            "optimizer_param_group_count": group_count,
        },
        "optimizer": {"param_groups": [{"lr": lr} for _ in range(group_count)]},
        "inherited_counters": {"updates": sc.ORIGIN},
        "cumulative_counters": {"updates": cumulative},
    }


def metric(local: int, *, group_count: int = 2) -> dict:
    cumulative = sc.ORIGIN + local
    return {
        "cumulative_updates": cumulative,
        "lr_schedule": {
            "schedule_origin_cumulative_update": sc.ORIGIN,
            "horizon_updates": sc.HORIZON,
            "completed_schedule_updates": local,
            "schedule_spec_sha256": lr_schedule.SCHEDULE_SPEC_SHA256,
            "optimizer_param_group_count": group_count,
        },
        "optimizer_group_lrs": [sc.expected_lr(cumulative) for _ in range(group_count)],
    }


class ScheduleValidation(unittest.TestCase):
    def test_checkpoint_entry_midpoint_and_horizon(self):
        for local in (0, 12, 60):
            state = checkpoint(local)
            self.assertEqual(sc.validate_checkpoint_schedule(
                state, inherited_updates=372, local_updates=local,
                cumulative_updates=372 + local), sc.expected_lr(372 + local))

    def test_all_sixty_metric_lrs_validate(self):
        rows = [metric(local) for local in range(1, 61)]
        values = sc.validate_progression(rows, group_count=2)
        self.assertEqual(len(values), 60)
        self.assertEqual(values[0], 3e-5)
        self.assertEqual(values[-1], 1e-5)
        self.assertEqual(len(set(values)), 60)

    def test_frozen_manifest_binds_schedule_helper_and_spec(self):
        lr_schedule.verify_frozen_manifest(OWN)

    def test_wrong_fixed_or_stale_saved_lr_fails(self):
        state = checkpoint(12)
        state["optimizer"]["param_groups"][1]["lr"] = 3e-5
        with self.assertRaises(sc.ScheduleAuditError):
            sc.validate_checkpoint_schedule(state, inherited_updates=372,
                                            local_updates=12, cumulative_updates=384)

    def test_missing_metric_lr_fields_and_wrong_lr_fail(self):
        bad = metric(12)
        del bad["optimizer_group_lrs"]
        with self.assertRaises(sc.ScheduleAuditError):
            sc.validate_metric_schedule(bad, inherited_updates=372, local_update=12, group_count=2)
        bad = metric(12)
        bad["optimizer_group_lrs"] = [3e-5, 3e-5]
        with self.assertRaises(sc.ScheduleAuditError):
            sc.validate_metric_schedule(bad, inherited_updates=372, local_update=12, group_count=2)

    def test_stale_progress_and_cumulative_math_fail(self):
        state = checkpoint(12)
        with self.assertRaises(sc.ScheduleAuditError):
            sc.validate_checkpoint_schedule(state, inherited_updates=372,
                                            local_updates=11, cumulative_updates=383)
        with self.assertRaises(sc.ScheduleAuditError):
            sc.validate_checkpoint_schedule(state, inherited_updates=372,
                                            local_updates=12, cumulative_updates=385)
        bad = metric(12)
        bad["cumulative_updates"] = 383
        with self.assertRaises(sc.ScheduleAuditError):
            sc.validate_metric_schedule(bad, inherited_updates=372, local_update=12, group_count=2)

    def test_missing_wrong_origin_horizon_spec_and_group_count_fail(self):
        mutations = (
            lambda s: s.pop("schedule_origin_cumulative_update"),
            lambda s: s.__setitem__("schedule_origin_cumulative_update", 371),
            lambda s: s.__setitem__("horizon_updates", 59),
            lambda s: s.__setitem__("schedule_spec_sha256", "0" * 64),
            lambda s: s.__setitem__("optimizer_param_group_count", 3),
        )
        for mutate in mutations:
            state = checkpoint(12)
            mutate(state["lr_schedule"])
            with self.subTest(state=state["lr_schedule"]), self.assertRaises(sc.ScheduleAuditError):
                sc.validate_checkpoint_schedule(state, inherited_updates=372,
                                                local_updates=12, cumulative_updates=384)

    def test_wrong_inherited_origin_and_short_full_progression_fail(self):
        with self.assertRaises(sc.ScheduleAuditError):
            sc.validate_checkpoint_schedule(checkpoint(0), inherited_updates=360,
                                            local_updates=0, cumulative_updates=360)
        with self.assertRaises(sc.ScheduleAuditError):
            sc.validate_progression([metric(i) for i in range(1, 60)], group_count=2)


class Boundaries(unittest.TestCase):
    def test_binding_builder_requires_exact_explicit_source_digests(self):
        path = OWN / "lr_schedule.py"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(bb.checked_bytes(path, digest, "source"), path.read_bytes())
        with self.assertRaises(ValueError):
            bb.checked_bytes(path, "0" * 64, "source")
        with self.assertRaises(ValueError):
            bb.checked_bytes(path, "", "source")

    def test_binding_builder_positive_uses_actual_package_and_pinned_observer(self):
        registration = bb.REGISTRATION
        observer = bb.OBSERVER
        source_pins = {str((OWN / name).resolve()): hashlib.sha256((OWN / name).read_bytes()).hexdigest()
                       for name in bb.SOURCE_NAMES}
        manifest = {
            "schema": "d2_retained324_linear_auditor_review_assembly_v1",
            "run_id": bb.RUN_ID,
            "registration": {"path": str(registration.resolve()), "sha256": bb.REGISTRATION_SHA256},
            "frozen_manifest": {"path": str(bb.FROZEN_MANIFEST.resolve()),
                                "sha256": hashlib.sha256(bb.FROZEN_MANIFEST.read_bytes()).hexdigest()},
            "auditor_sources": source_pins,
        }
        fixture = OWN / "review-assembly-fixture.json"
        fixture.write_text(json.dumps(manifest, sort_keys=True))
        try:
            review_sha = hashlib.sha256(fixture.read_bytes()).hexdigest()
            binding = bb.build_binding(
                registration=registration, registration_sha256=bb.REGISTRATION_SHA256,
                reviewed_manifest=fixture, reviewed_manifest_sha256=review_sha,
                observer_source=observer, observer_sha256=bb.OBSERVER_SHA256,
                frozen_manifest=bb.FROZEN_MANIFEST,
                frozen_manifest_sha256=hashlib.sha256(bb.FROZEN_MANIFEST.read_bytes()).hexdigest())
            self.assertEqual(binding["registration"]["path"], str(registration.resolve()))
            self.assertEqual(binding["auditor_sources"], source_pins)
            self.assertEqual(binding["observer_source"]["sha256"], bb.OBSERVER_SHA256)
            manifest["registration"]["path"] = str(OWN / "wrong-registration.json")
            fixture.write_text(json.dumps(manifest, sort_keys=True))
            with self.assertRaises(ValueError):
                bb.build_binding(
                    registration=registration, registration_sha256=bb.REGISTRATION_SHA256,
                    reviewed_manifest=fixture,
                    reviewed_manifest_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
                    observer_source=observer, observer_sha256=bb.OBSERVER_SHA256,
                    frozen_manifest=bb.FROZEN_MANIFEST,
                    frozen_manifest_sha256=hashlib.sha256(bb.FROZEN_MANIFEST.read_bytes()).hexdigest())
        finally:
            fixture.unlink(missing_ok=True)

    def test_external_binding_digest_gates_reject_wrong_expected_hash(self):
        payload = b'{"schema":"fixture"}\n'
        expected = hashlib.sha256(payload).hexdigest()
        self.assertEqual(auditor.binding_digest(payload, expected), expected)
        self.assertEqual(wrapper.binding_digest(payload, expected), expected)
        with self.assertRaises(auditor.AuditError):
            auditor.binding_digest(payload, "0" * 64)
        with self.assertRaises(wrapper.WrapperError):
            wrapper.binding_digest(payload, "0" * 64)

    def test_schedule_modules_load_only_from_pinned_own_paths(self):
        pins = {str((OWN / name).resolve()): hashlib.sha256((OWN / name).read_bytes()).hexdigest()
                for name in ("lr_schedule.py", "schedule_contract.py")}
        contract, helper = auditor.load_bound_schedule_modules(pins)
        self.assertEqual(Path(contract.__file__).resolve(), (OWN / "schedule_contract.py").resolve())
        self.assertEqual(Path(helper.__file__).resolve(), (OWN / "lr_schedule.py").resolve())
        pins[str((OWN / "lr_schedule.py").resolve())] = "0" * 64
        with self.assertRaises(auditor.AuditError):
            auditor.load_bound_schedule_modules(pins)

    def test_metric_rows_bind_actual_validator_to_schedule_evidence(self):
        pins = {str((OWN / name).resolve()): hashlib.sha256((OWN / name).read_bytes()).hexdigest()
                for name in ("lr_schedule.py", "schedule_contract.py")}
        auditor.load_bound_schedule_modules(pins)

        class Runner:
            @staticmethod
            def finite_tree(value):
                return None

            @staticmethod
            def validate_gradient_alignment(value):
                return None

        rows = []
        for local in (1, 2):
            row = metric(local)
            row.update({"phase_update": 324 + local, "local_update": local,
                        "metrics": {"optimizer_steps": 1, "transitions": 16384},
                        "counters": {"updates": local, "optimizer_steps": local,
                                     "environment_decisions": local * 16384},
                        "update_progress": {"completed_updates": local, "complete": True,
                                            "in_update": False}})
            rows.append(row)
        self.assertEqual(auditor.validate_metric_rows(Runner, rows, 2, 2), 2)
        bad = copy.deepcopy(rows)
        bad[1]["optimizer_group_lrs"][0] = 3e-5
        with self.assertRaises(auditor.AuditError):
            auditor.validate_metric_rows(Runner, bad, 2, 2)

    def test_saved_lr_guard_rejects_non_mapping_counters(self):
        pins = {str((OWN / name).resolve()): hashlib.sha256((OWN / name).read_bytes()).hexdigest()
                for name in ("lr_schedule.py", "schedule_contract.py")}
        auditor.load_bound_schedule_modules(pins)
        with self.assertRaises(auditor.AuditError):
            auditor.check_saved_lr({"inherited_counters": [], "cumulative_counters": {}}, 0)

    def test_actual_package_contract_rejects_parent_substitution(self):
        import json
        reg = json.loads(bb.REGISTRATION.read_bytes())
        reg["parent"]["sha256"] = "0" * 64
        with self.assertRaises(auditor.AuditError):
            auditor.validate_actual_package(reg, bb.REGISTRATION_SHA256)

    def test_inventory_hash_boundary(self):
        path = OWN / "lr_schedule.py"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(wrapper.verify_pins({str(path): digest}), 1)
        with self.assertRaises(wrapper.WrapperError):
            wrapper.verify_pins({str(path): "0" * 64})

    def test_resource_and_cleanup_boundaries(self):
        reg = {"pins": {"source": "sha"}, "expected_lease": {"owner": "parent"}}
        observation = {
            "outer_raw_exit": 0, "worker_raw_exit": 0, "first_event": None,
            "launch_count": 1, "outer_limit_seconds": 1800,
            "outer_inclusive_wall_seconds": 100, "max_aggregate_rss_bytes": 10,
            "aggregate_rss_limit_bytes": 100, "mps_limit_bytes": 100,
            "outer_process_absent": True, "worker_process_absent": True,
            "worker_group_absent": True, "success_authoritative": True,
            "postflight": {"lease": {"active_long_campaign_exact": True,
                "active_inference_campaign": None, "active_inference_lease": None,
                "active_inference_diagnostic": None},
                "pins": {"checked": 1, "failures": []},
                "cache_empty_after": True, "publication_failure_absent": True},
        }
        execution = {"actual_worker_launch_count": 1, "observed_worker_raw_exit": 0,
                     "status": "passed", "worker_pid": 99999999, "owned_pgid": 99999998}
        worker = {"status": "completed", "first_failure": None,
                  "peak_rss_bytes": 10, "peak_mps_driver_bytes": 10}
        wrapper.terminal_gates(observation, execution, worker, reg)
        for key, value in (("max_aggregate_rss_bytes", 101), ("outer_process_absent", False),
                           ("worker_process_absent", False), ("worker_group_absent", False)):
            bad = copy.deepcopy(observation)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(wrapper.WrapperError):
                wrapper.terminal_gates(bad, execution, worker, reg)
        bad = copy.deepcopy(observation)
        bad["postflight"]["lease"]["active_long_campaign_exact"] = False
        with self.assertRaises(wrapper.WrapperError):
            wrapper.terminal_gates(bad, execution, worker, reg)


if __name__ == "__main__":
    unittest.main()
