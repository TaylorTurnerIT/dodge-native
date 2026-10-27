"""Synthetic supervision, episode and normal-checkpoint contracts; no gameplay."""
import copy
import os
import sys
import io
import json
import os
from pathlib import Path
import signal
import tempfile
from types import SimpleNamespace
import unittest
from collections import OrderedDict
from unittest.mock import Mock, patch

import runner as r
import execute_once as e

HERE = Path(__file__).resolve().parent


def registration(root):
    output = root / ("learning/runs/v2/" + r.RUN_ID)
    parent = root / "learning/runs/v2/milestone3-D1-curriculum-r1/checkpoint-000009-candidate.pt"
    native = root / "runtime/dodge_rl/_native.so"
    old = root / "python/dodge_rl/_native.so"
    lineage = {"path": str(parent), "sha256": r.PARENT_SHA,
               "anchor_path": str(root / "anchor.json"), "anchor_sha256": r.ANCHOR_SHA,
               "validation_receipt_path": str(root / "validation.json"), "validation_receipt_sha256": "1" * 64,
               "validator_path": str(root / "validate-transition.py"), "archive_path": str(root / "frozen-source.tar.gz")}
    value = {"schema": "d2_training_iteration_registration_v1", "normal_training_iteration": True, "training_eligible": False,
             "run_id": output.name, "root": str(root), "output": str(output),
             "runtime_root": str(root / "runtime"), "interpreter": str(root / "python"),
             "import_policy": {"pycache_prefix": os.environ.get("PYTHONPYCACHEPREFIX", "")},
             "runner_path": str(HERE / "runner.py"), "launcher_path": str(HERE / "execute_once.py"),
             "state_path": str(root / "state.json"), "config_path": str(root / "config.json"),
             "config_sha256": r.CONFIG_SHA, "runtime_versions": {"python": "3.12", "torch": "x", "numpy": "y"}, "runtime_sha256": "c" * 64,
             "run_seed": 810631976, "timing_policy": "launcher_monotonic_start_plus_registered_limits_v1",
             "cancel_path": str(root / "cancel"), "limits": copy.deepcopy(r.LIMITS), "parent": lineage,
             "native": {"path": str(native), "sha256": r.NEW_NATIVE_SHA,
                        "old_path": str(old), "old_sha256": r.OLD_NATIVE_SHA},
             "expected_lease": {"run_id": output.name, "kind": "D2_training_v3",
                                "authorization": "user_continue_D2_training_v3", "parent_checkpoint_sha256": r.PARENT_SHA}}
    pins = {value[k]: "0" * 64 for k in ("runner_path", "launcher_path", "config_path", "interpreter")}
    pins.update({lineage["path"]: r.PARENT_SHA, lineage["anchor_path"]: r.ANCHOR_SHA,
                 lineage["validation_receipt_path"]: "1" * 64, lineage["validator_path"]: r.VALIDATOR_SHA,
                 lineage["archive_path"]: r.ARCHIVE_SHA, str(native): r.NEW_NATIVE_SHA, str(old): r.OLD_NATIVE_SHA})
    pins[value["config_path"]] = r.CONFIG_SHA
    value["pins"] = pins
    return value


class FakeProcess:
    pid = 987654321
    def __init__(self):
        self.code = 0
        self.waits = []
    def poll(self):
        return self.code
    def wait(self, timeout):
        self.waits.append(timeout)
        self.code = 0
        return 0


def completed():
    return {"status": "completed", "updates": 72, "evaluated_updates": [0, 72],
            "normal_training_iteration": True, "training_eligible": False, "promoted": False,
            "first_failure": None, "elapsed_seconds": 100, "work_elapsed_seconds": 99, "peak_rss_bytes": 100,
            "peak_mps_driver_bytes": 100,
            "counters": {"updates": 72, "optimizer_steps": 72 * 128, "environment_decisions": 72 * 16384, "raw_frames": 72 * 65536}}


def make_outputs(reg):
    out = Path(reg["output"]); out.mkdir(parents=True, exist_ok=True)
    root = HERE.parents[3]
    reg["runtime_root"] = str(root / "learning/runs/v2/critic-diagnostic-parent-prepare-20261025-r1/runtime")
    reg["import_policy"] = {"pycache_prefix": os.environ["PYTHONPYCACHEPREFIX"]}
    sys.path.insert(0, reg["runtime_root"])
    from dodge_rl import checkpoints as ckpt
    pre = {"count": 16384, "target_mean": 2., "target_variance": 4., "prediction_mean": 1.,
           "prediction_variance": 1., "target_prediction_covariance": 2., "residual_mean": 1.,
           "residual_variance": 1., "residual_mse": 2., "explained_variance": .75}
    post = dict(pre, residual_mean=0., residual_variance=.5, residual_mse=.5, explained_variance=.875)
    metric = {"optimizer_steps": 128, "transitions": 16384, "explained_variance": .75,
              "critic_diagnostics": {"version": "same_batch_critic_diagnostics_v1", "pre_update": pre, "post_update": post}}
    with (out / "training-metrics.jsonl").open("w") as stream:
        for update in range(1, 73):
            counters = {"updates": update, "optimizer_steps": update * 128,
                        "environment_decisions": update * 16384, "raw_frames": update * 65536}
            progress = {"complete": True, "in_update": False, "completed_updates": update}
            stream.write(json.dumps({"phase_update": update, "metrics": metric, "counters": counters,
                                    "update_progress": progress}) + "\n")
    initial = {"kind": "initial", "info": [{"seed": {"slot": slot, "episode": 0}} for slot in range(64)],
               "batch_info": {"next_episode_indices": [1] * 64}}
    journal = [initial]
    for episode in range(5):
        completed = [{"seed": {"slot": slot, "episode": episode}, "rollout_step": 0, "gameplay_frames": 14000}
                     for slot in range(64)]
        reset = {"rollout_step": 0, "indices": list(range(64)),
                 "info": [{"seed": {"slot": slot, "episode": episode + 1}} for slot in range(64)]}
        journal.extend(r.ordered_episode_events(completed, [reset], (episode + 1) * 14))
    (out / "training-episodes.jsonl").write_text("\n".join(json.dumps(x) for x in journal) + "\n")
    inherited = {"updates": 48, "optimizer_steps": 6144, "environment_decisions": 786432, "raw_frames": 3139552, "phase_updates": 32, "checkpoint_index": 9}
    reg["parent"]["path"] = str(root / "learning/runs/v2/milestone3-D1-curriculum-r1/checkpoint-000009-candidate.pt")
    rows = [{"seed": 0xD0000000 + i, "alive_frames": 200 + i, "score": i / 2,
             "terminated": True, "truncated": False, "death_cause": "normal_enemy",
             "objective_return": i / 2 + .01 * (200 + i) - 5} for i in range(64)]
    evaluation = {"complete": True, "rows": rows, "mean_alive_frames": 231.5, "mean_score": 15.75,
                  "death_causes": {"normal_enemy": 64}, "deaths": 64, "caps": 0}
    for update in (0, 72):
        path = out / f"checkpoint-{update:06d}-candidate.pt"
        identity = {"version": "teacher_identity_v3", "registration_sha256": "a" * 64, "run_seed": reg["run_seed"]}
        counters = {"updates": update, "optimizer_steps": update * 128,
                    "environment_decisions": update * 16384, "raw_frames": update * 65536}
        state = {"version": "teacher_checkpoint_v1", "schema": "d2_training_v3_checkpoint_v1", "tag": "candidate", "resume_mode": "fresh_env",
                 "eligibility_status": "provisional_pending_parent_terminal_receipt", "registration_sha256": "a" * 64,
                 "identity": identity, "identity_sha256": ckpt.identity_hash(identity),
                 "training_eligible": False, "promoted": False, "run_seed": reg["run_seed"],
                 "config_sha256": reg["config_sha256"], "policy_sha256": r.POLICY_SHA,
                 "native_sha256": reg["native"]["sha256"], "parent_sha256": r.PARENT_SHA, "runtime_sha256": reg["runtime_sha256"],
                 "counters": counters, "inherited_counters": inherited,
                 "cumulative_counters": {key: inherited[key] + counters[key] for key in counters},
                 "next_episode_indices": [1 if update == 0 else 6] * 64,
                 "abandoned_current_episodes": [{"slot": slot, "seed": {"episode": 5}, "gameplay_frames": 3728}
                                                 for slot in range(64)] if update else [],
                 "update_progress": {"complete": True, "in_update": False, "completed_updates": update}}
        digest = ckpt.save_checkpoint(path, state)
        r.save(out / f"development-{update:06d}.json", {"evaluation": evaluation,
               "performance": r.performance(evaluation), "checkpoint": path.name, "checkpoint_sha256": digest,
               "normal_training_iteration": True, "training_eligible": False, "promoted": False,
               "competence_passed": False, "training_state_unchanged": True})
        r.save(Path(str(path) + ".json"), {"eligibility_status": "provisional_pending_parent_terminal_receipt",
               "training_eligible": False, "promoted": False, "checkpoint_sha256": digest})
    return out


def full_worker():
    value = completed()
    inherited = {"updates": 48, "optimizer_steps": 6144, "environment_decisions": 786432, "raw_frames": 3139552, "phase_updates": 32, "checkpoint_index": 9}
    value.update(final_resume_next_episode_indices=[6] * 64, inherited_counters=inherited,
                 cumulative_counters={key: inherited[key] + value["counters"][key] for key in value["counters"]})
    return value


class Contract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="contract-", dir=HERE)
        self.root = Path(self.temp.name)
        self.reg = registration(self.root)
        self.regpath = self.root / "registration.json"
        self.regpath.write_text(json.dumps(self.reg))
    def tearDown(self):
        self.temp.cleanup()

    def test_fingerprint_mapping_canonicalization_and_structural_negatives(self):
        left = {"model": {"weight": [1, 2]}, "adam": {"step": 3}}
        right = OrderedDict([("adam", OrderedDict([("step", 3)])),
                             ("model", OrderedDict([("weight", [1, 2])]))])
        self.assertEqual(r.fingerprint(left), r.fingerprint(right))
        self.assertEqual(r.mismatch_paths(left, right), [])
        self.assertNotEqual(r.fingerprint({"x": [1]}), r.fingerprint({"x": (1,)}))
        self.assertNotEqual(r.fingerprint({"x": 1}), r.fingerprint({"x": 1.0}))
        self.assertEqual(r.fingerprint({"a": 1, "b": 2}), r.fingerprint({"b": 2, "a": 1}))
        self.assertNotEqual(r.fingerprint({"x": [1, 2]}), r.fingerprint({"x": [1, 3]}))
        self.assertIn("$.x[1]", r.mismatch_paths({"x": [1, 2]}, {"x": [1, 3]}))
        self.assertNotEqual(r.fingerprint([1, [2]]), r.fingerprint([1, 2]))

    def test_registration_rejects_lineage_settings_and_eligibility_substitution(self):
        self.assertEqual(r.validate_registration(self.reg), self.reg)
        for edit in (lambda v: v["parent"].update(sha256="0" * 64),
                     lambda v: v["parent"].update(path=str(self.root / "failed-D2.pt")),
                     lambda v: v["limits"].update(max_updates=96),
                     lambda v: v.update(training_eligible=True),
                     lambda v: v.update(run_seed=0xD0000000),
                     lambda v: v["native"].update(sha256=r.OLD_NATIVE_SHA),
                     lambda v: v["pins"].pop(v["parent"]["archive_path"])):
            value = copy.deepcopy(self.reg); edit(value)
            with self.assertRaises(ValueError):
                r.validate_registration(value)

    def test_pin_mismatch_launches_no_process_and_consumes_marker(self):
        launch = Mock()
        with patch.object(r, "load_registration", side_effect=ValueError("Pinned input changed")):
            code = e.execute(self.regpath, "x", popen=launch)
        self.assertEqual(code, 1); launch.assert_not_called()
        result = r.read(Path(self.reg["output"]) / "execution-result.json")
        self.assertEqual(result["actual_worker_launch_count"], 0)
        with self.assertRaises(FileExistsError):
            e.execute(self.regpath, "x", popen=launch)

    def test_external_digest_checked_before_pin_reads(self):
        with patch.object(r, "verify_pins") as verify:
            with self.assertRaisesRegex(ValueError, "External registration"):
                r.load_registration(self.regpath, "0" * 64)
        verify.assert_not_called()

    def test_resource_lease_and_cancel_are_failclosed(self):
        state = Path(self.reg["state_path"])
        state.write_text(json.dumps({"active_long_campaign": self.reg["expected_lease"]}))
        r.check_lease(self.reg)
        state.write_text(json.dumps({"active_long_campaign": None}))
        with self.assertRaisesRegex(ValueError, "lease changed"):
            r.check_lease(self.reg)
        torch = SimpleNamespace(mps=SimpleNamespace(driver_allocated_memory=lambda: 0))
        guard = r.Guard(self.reg, 0., torch, io.StringIO(), clock=lambda: 1.)
        peak = r.LIMITS["RSS_bytes"] + 1
        with patch.object(r, "check_lease"), patch.object(r.resource, "getrusage", return_value=SimpleNamespace(ru_maxrss=peak)):
            with self.assertRaisesRegex(ValueError, "Resource cap"):
                guard.check()
        first = guard.first_failure
        with self.assertRaises(r.Cancelled):
            guard.signal(signal.SIGTERM, None)
        self.assertIs(guard.first_failure, first)

    def test_absolute_deadline_never_resets(self):
        torch = SimpleNamespace(mps=SimpleNamespace(driver_allocated_memory=lambda: 0))
        guard = r.Guard(self.reg, 10., torch, io.StringIO(), clock=lambda: 1610.)
        with self.assertRaisesRegex(ValueError, "budget exhausted"):
            guard.check()
        guard = r.Guard(self.reg, 10., torch, io.StringIO(), clock=lambda: 1810.)
        with self.assertRaisesRegex(ValueError, "budget exhausted"):
            guard.check(finalizing=True)

    def test_cancellation_time_is_first_failure_and_later_signal_does_not_interrupt(self):
        guard = r.Guard(self.reg, 0., None, io.StringIO(), clock=lambda: 12.)
        with self.assertRaises(r.Cancelled):
            guard.signal(signal.SIGINT, None)
        guard.signal(signal.SIGTERM, None)
        self.assertEqual(guard.first_failure, {"monotonic": 12., "kind": "cancelled", "signal": signal.SIGINT})
        self.assertEqual(guard.first_signal, signal.SIGINT)

    def test_moment_and_evaluation_evidence_checked(self):
        out = make_outputs(self.reg)
        self.assertEqual(e.validate_outputs(self.reg, full_worker(), "a" * 64)["updates_checked"], 72)
        path = out / "training-metrics.jsonl"
        rows = [json.loads(x) for x in path.read_text().splitlines()]
        rows[0]["metrics"]["critic_diagnostics"]["pre_update"]["residual_mse"] = 3.
        path.write_text("\n".join(json.dumps(x) for x in rows))
        with self.assertRaisesRegex(ValueError, "Residual moment"):
            e.validate_outputs(self.reg, full_worker(), "a" * 64)

    def test_incomplete_updates_and_invalid_success_flags_rejected(self):
        for key, value in (("updates", 71), ("evaluated_updates", [0, 48]),
                           ("status", "failed"), ("training_eligible", True),
                           ("first_signal", 15), ("first_failure", {"error": "cancel"})):
            result = completed(); result[key] = value
            self.assertFalse(r.valid_worker_result(result))

    def test_nonfinite_and_unexpected_null_metrics_rejected(self):
        r.finite_tree({"explained_variance": None})
        for value in ({"x": float("nan")}, {"x": float("inf")}, {"loss": None}):
            with self.assertRaises(ValueError):
                r.finite_tree(value)

    def run_mocked(self, *, postflight_failure=False, expire=False):
        out = Path(self.reg["output"]); out.mkdir(parents=True)
        r.save(out / "worker-result.json", completed())
        calls = []
        now = [0.]
        def load(*_):
            calls.append("preflight" if len(calls) == 0 else "postflight")
            if postflight_failure and len(calls) > 1:
                raise ValueError("Postflight source changed")
            return self.reg, {}
        def validate(*_):
            calls.append("evidence")
            if expire:
                now[0] = 1800.
            return {"updates_checked": 72}
        process = FakeProcess(); popen = Mock(return_value=process)
        with patch.object(r, "load_registration", side_effect=load), patch.object(r, "check_lease"), \
             patch.object(e, "validate_outputs", side_effect=validate), patch.object(e, "group_exists", return_value=False), \
             patch.object(e, "stop_owned", return_value={"reaped": True}) as stop:
            code = e.execute(self.regpath, "x", clock=lambda: now[0], popen=popen)
        return code, r.read(out / "execution-result.json"), calls, popen, stop

    def test_postflight_precedes_success_and_owned_process_is_directly_waited(self):
        code, result, calls, popen, stop = self.run_mocked()
        self.assertEqual(code, 0); self.assertEqual(result["status"], "passed")
        self.assertEqual(calls, ["preflight", "evidence", "postflight"])
        self.assertTrue(result["directly_reaped"]); self.assertTrue(result["owned_group_absent"])
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        stop.assert_not_called()

    def test_postflight_mutation_rejects_otherwise_complete_worker(self):
        code, result, _, _, stop = self.run_mocked(postflight_failure=True)
        self.assertEqual(code, 1); self.assertEqual(result["status"], "failed")
        self.assertNotIn("postflight_inputs_unchanged", result)
        stop.assert_not_called()  # The group was already reaped and proved absent.

    def test_late_publication_cancel_cannot_return_success(self):
        import inspect
        out = Path(self.reg["output"]); out.mkdir(parents=True)
        r.save(out / "worker-result.json", completed())
        fired = False

        def clock():
            nonlocal fired
            caller = inspect.currentframe().f_back
            if (not fired and caller.f_code.co_name == "execute"
                    and caller.f_locals.get("result", {}).get("status") == "passed"):
                fired = True
                signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
            return 0.

        with patch.object(r, "load_registration", return_value=(self.reg, {})), \
             patch.object(r, "check_lease"), patch.object(e, "group_exists", return_value=False), \
             patch.object(e, "validate_outputs", return_value={"updates_checked": 48}):
            code = e.execute(self.regpath, "x", clock=clock, popen=Mock(return_value=FakeProcess()))
        self.assertTrue(fired)
        self.assertEqual(code, 1)
        failure = r.read(out / "publication-failure.json")
        self.assertEqual(failure["status"], "failed")
        self.assertEqual(failure["parent_signal"]["signal"], signal.SIGTERM)

    def test_postflight_failure_never_signals_a_reused_proven_absent_group(self):
        out = Path(self.reg["output"]); out.mkdir(parents=True)
        r.save(out / "worker-result.json", completed())
        calls = 0

        def load(*_):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError("Postflight input changed")
            return self.reg, {}

        with patch.object(r, "load_registration", side_effect=load), patch.object(r, "check_lease"), \
             patch.object(e, "validate_outputs", return_value={"updates_checked": 48}), \
             patch.object(e, "group_exists", side_effect=[False, True]) as exists, \
             patch.object(e.os, "killpg") as kill:
            code = e.execute(self.regpath, "x", clock=lambda: 0., popen=Mock(return_value=FakeProcess()))
        self.assertEqual(code, 1)
        self.assertEqual(exists.call_count, 1)
        kill.assert_not_called()

    def test_receipt_reserve_not_extended_after_work(self):
        code, result, _, _, _ = self.run_mocked(expire=True)
        self.assertEqual(code, 1); self.assertEqual(result["status"], "failed")
        self.assertNotIn("postflight_inputs_unchanged", result)

    def test_cleanup_targets_only_exact_owned_group(self):
        process = FakeProcess(); process.code = None
        with patch.object(e.os, "killpg") as kill, patch.object(e, "group_exists", return_value=False):
            result = e.stop_owned(process)
        kill.assert_called_once_with(process.pid, signal.SIGTERM)
        self.assertEqual(process.waits, [5]); self.assertTrue(result["reaped"])
        process.pid = os.getpgrp()
        with patch.object(e.os, "killpg") as kill:
            with self.assertRaises(ValueError):
                e.stop_owned(process)
        kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
