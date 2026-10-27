import json
import gc
import inspect
import os
from pathlib import Path
import resource
import sys
import tempfile
import time
import unittest
from unittest import mock
import weakref

import numpy as np
import torch

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[3]
RUNTIME = ROOT / "learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(RUNTIME))

import paired_eval as pe
import supervisor
import worker


class FakeModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.anchor = torch.nn.Parameter(torch.zeros(()), requires_grad=False)

    def forward(self, global_feats, entity_feats, entity_types, entity_mask):
        return type("Output", (), {"logits": torch.zeros((global_feats.shape[0], 9), device=global_feats.device)})()


class FakeEnv:
    made = []

    def __init__(self, *, seed, stage, **config):
        self.seed = seed
        self.config = config
        self.calls = 0
        self.made.append(self)

    def episode_info(self):
        return [{"seed": {"evaluation": True, "actual_seed": self.seed}, "startup_frames": 13}]

    def observations(self):
        return {"global_feats": np.zeros((1, 1, 14), dtype=np.float32),
                "entity_feats": np.zeros((1, 80, 16), dtype=np.float32),
                "entity_types": np.zeros((1, 80), dtype=np.int64),
                "entity_mask": np.zeros((1, 80), dtype=np.bool_)}

    def step(self, actions):
        self.calls += 1
        truncated = self.calls >= 3
        info = {"seed": {"actual_seed": self.seed}, "bootstrap": True,
                "score_raw_fixed": 0, "score_delta_sum_raw_fixed": 0,
                "score": 0.0, "alive_frames": 4 * self.calls, "gameplay_frames": 4 * self.calls,
                "objective_return": 0.04 * self.calls,
                "death_cause": None if truncated else None,
                "fatal_gameplay_frame": None, "death_observed_lethal_contacts": None}
        return {"info": [info], "terminated": np.array([False]), "truncated": np.array([truncated]),
                "observations": None if truncated else self.observations()}

def fake_config(seed, stage):
    if stage != "D2":
        raise AssertionError(stage)
    return {"seed": seed, "stage": stage, "batch_size": 1, "action_repeat": 4,
            "difficulty": 2, "patterns_enabled": True, "powerups_enabled": True,
            "raw_frame_cap": 18000, "render_pixels": False, "auxiliary_targets": False,
            "num_threads": 1, "chunk_size": 1,
            "seeds_by_slot": [[seed]],
            "excluded_seed_ranges": [(2952790016, 2952791015), (3489660928, 3489661055),
                                     (3758096384, 3758097383)]}


def fake_rows():
    rows = []
    for item in pe.episode_schedule():
        for index, seed in enumerate(pe.SEEDS):
            rows.append({"checkpoint": item["checkpoint"], "mode": item["mode"],
                         "replicate_seed": item["replicate_seed"], "episode_index": index,
                         "seed": seed, "score_raw_fixed": 0, "score": 0.0,
                         "alive_frames": float(index), "gameplay_frames": index,
                         "terminated": True, "truncated": False, "objective_return": 0.0,
                         "death_cause": "normal_enemy", "fatal_gameplay_frame": index,
                         "death_observed_lethal_contacts": {"normal_enemy": 1}})
    return rows


class PairedEvalTests(unittest.TestCase):
    def test_frozen_protocol_names_review_provider_without_haiku_substitution(self):
        protocol = json.loads((HERE / "protocol-proposed.json").read_text())
        self.assertEqual(protocol["run_id"], "latest-best-paired-eval-prepare-luna-20261026-r5")
        self.assertEqual(protocol["review_provenance"]["r2_review_status"], "closed_by_parent_reconciliation")
        self.assertEqual(protocol["review_provenance"]["r3_review_status"],
                         "frozen_review_findings_1_to_5_addressed_in_r4")
        self.assertEqual(protocol["review_provenance"]["r4_review_status"], "pending_frozen_review")
        policy = protocol["resources"]["sampling_policy"]
        self.assertEqual(policy["freshness_seconds"], 1.0)
        self.assertIn("unmeasured", policy)
        self.assertEqual(policy["startup_sample_seconds"], 10.0)
        lease = protocol["lease_contract"]["active_inference_diagnostic"]
        self.assertIn("review_provider", lease)
        self.assertIn("review_receipt_sha256", protocol["lease_contract"]["required_review_fields"])
        self.assertNotIn("haiku_review_status", lease)
        self.assertNotIn("haiku_review_receipt_sha256", lease)

    def test_schedule_has_exact_512_and_argmax_first_for_both_checkpoints(self):
        schedule = pe.episode_schedule()
        self.assertEqual(pe.episode_count(schedule), 512)
        self.assertEqual([(x["checkpoint"], x["mode"]) for x in schedule[:2]],
                         [("best204", "argmax"), ("latest252", "argmax")])
        self.assertTrue(all(x["mode"] == "sampled" for x in schedule[2:]))
        rows = fake_rows()
        summary = pe.summarize_all(rows)
        self.assertEqual(summary["episode_count"], 512)
        self.assertEqual(summary["censored_episode_count"], 0)
        self.assertEqual(summary["paired_contrasts"]["primary_contrast"], "C4_interaction")
        self.assertEqual(pe.paired_bootstrap(rows), pe.paired_bootstrap(rows))
        self.assertEqual(set(summary["paired_contrasts"]["contrasts"]), set(pe.CONTRAST_NAMES))
        self.assertEqual(summary["per_checkpoint_mode"]["best204_argmax"]["death_denominators"]["episodes"], 64)
        self.assertEqual(summary["per_checkpoint_mode"]["best204_sampled"]["death_denominators"]["episodes"], 192)
        self.assertEqual(set(summary["per_checkpoint_mode"]["best204_sampled"]["replicate_summaries"]),
                         {"64001", "64002", "64003"})

    def test_argmax_control_compares_whole_canonical_row_and_fails_closed(self):
        row = {"episode_index": 0, "seed": pe.SEEDS[0], "score_raw_fixed": 0, "score": 0.0,
               "alive_frames": 4, "gameplay_frames": 4, "terminated": False, "truncated": True,
               "objective_return": 0.04, "death_cause": None, "fatal_gameplay_frame": None,
               "death_observed_lethal_contacts": None}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "control.jsonl"
            expected = [dict(row, episode_index=i, seed=seed) for i, seed in enumerate(pe.SEEDS)]
            path.write_text("".join(json.dumps(value) + "\n" for value in expected))
            pe.compare_control(expected, path)
            changed = [dict(value) for value in expected]
            changed[0]["death_observed_lethal_contacts"] = {"normal_enemy": 1}
            with self.assertRaisesRegex(ValueError, "mismatch"):
                pe.compare_control(changed, path)

    def test_fake_env_evaluator_uses_d2_helpers_and_no_real_games(self):
        from dodge_rl.dev_eval import development_environment_config
        actual_config = development_environment_config(pe.SEEDS[0], "D2")
        self.assertEqual({key: actual_config[key] for key in ("batch_size", "action_repeat", "difficulty",
                         "patterns_enabled", "powerups_enabled", "raw_frame_cap", "render_pixels",
                         "auxiliary_targets", "num_threads", "chunk_size")},
                         {"batch_size": 1, "action_repeat": 4, "difficulty": 2,
                          "patterns_enabled": True, "powerups_enabled": True, "raw_frame_cap": 18000,
                          "render_pixels": False, "auxiliary_targets": False,
                          "num_threads": 1, "chunk_size": 1})
        FakeEnv.made = []
        expected = []
        for index, seed in enumerate(pe.SEEDS):
            expected.append({"episode_index": index, "seed": seed, "score_raw_fixed": 0,
                             "score": 0.0, "alive_frames": 12, "gameplay_frames": 12,
                             "terminated": False, "truncated": True, "objective_return": 0.12,
                             "death_cause": None, "fatal_gameplay_frame": None,
                             "death_observed_lethal_contacts": None})
        with tempfile.TemporaryDirectory() as directory:
            control = Path(directory) / "expected.jsonl"
            control.write_text("".join(json.dumps(row) + "\n" for row in expected))
            rows = worker.evaluate(FakeModel(), checkpoint="best204", mode="argmax",
                                   replicate_seed=None, env_factory=FakeEnv,
                                   config_factory=fake_config, expected_control_path=control)
        self.assertEqual(len(rows), 64)
        self.assertEqual([env.calls for env in FakeEnv.made], [3] * 64)
        self.assertTrue(all(not hasattr(env, "close") for env in FakeEnv.made))
        self.assertEqual(rows[0]["checkpoint"], "best204")
        self.assertEqual(rows[0]["alive_frames"], 12)

    def test_fake_native_contract_failure_drops_refs_without_masking_step_error(self):
        class FailingEnv(FakeEnv):
            made = []
            ref = None
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                type(self).ref = weakref.ref(self)
                type(self).made.clear()
            def step(self, actions):
                raise AttributeError("original step failure")

        with self.assertRaisesRegex(AttributeError, "original step failure"):
            worker.evaluate(FakeModel(), checkpoint="best204", mode="argmax", replicate_seed=None,
                            env_factory=FailingEnv,
                            config_factory=lambda seed, stage: dict(fake_config(seed, stage), raw_frame_cap=4),
                            seeds=(pe.SEEDS[0],), fixture=True)
        gc.collect()
        self.assertIsNone(FailingEnv.ref())

    def test_completed_row_count_survives_later_arm_episode_failure(self):
        class PartialFailureEnv(FakeEnv):
            made = []
            def step(self, actions):
                self.calls += 1
                if self.seed != pe.SEEDS[0] and self.calls >= 3:
                    raise RuntimeError("later episode failed")
                self.calls -= 1
                return super().step(actions)
        persisted, counted = [], []
        with self.assertRaisesRegex(RuntimeError, "later episode failed"):
            worker.evaluate(FakeModel(), checkpoint="best204", mode="argmax", replicate_seed=None,
                            env_factory=PartialFailureEnv, config_factory=fake_config,
                            episode_sink=persisted.append, on_episode_row=counted.append)
        self.assertEqual(len(persisted), 1)
        self.assertEqual(counted, persisted)

    def test_evaluator_preserves_terminal_row_fields(self):
        class TerminalEnv(FakeEnv):
            def step(self, actions):
                info = {"seed": {"actual_seed": self.seed}, "bootstrap": False,
                        "score_raw_fixed": 0, "score_delta_sum_raw_fixed": 0,
                        "score": 0.0, "alive_frames": 4, "gameplay_frames": 4,
                        "objective_return": -4.96}
                return {"info": [info], "terminated": np.array([True]),
                        "truncated": np.array([False]), "observations": None}
        rows = worker.evaluate(FakeModel(), checkpoint="best204", mode="argmax", replicate_seed=None,
                               env_factory=TerminalEnv,
                               config_factory=lambda seed, stage: dict(fake_config(seed, stage), raw_frame_cap=4),
                               seeds=(pe.SEEDS[0],), fixture=True)
        self.assertTrue(rows[0]["terminated"])
        self.assertEqual(rows[0]["death_cause"], "unavailable")
        self.assertIsNone(rows[0]["fatal_gameplay_frame"])

    def test_pinned_native_terminal_control_roundtrips_through_canonicalizer(self):
        from dodge_rl.dev_eval import death_fields
        relative, digest = worker.EXPECTED_INPUTS["best204_development"]
        self.assertEqual(worker.sha256(ROOT / relative), digest)
        source = next(json.loads(line) for line in (ROOT / relative).read_text().splitlines()
                      if json.loads(line)["terminated"])
        info = {key: source[key] for key in ("score_raw_fixed", "alive_frames", "gameplay_frames",
                                             "objective_return", "death_cause", "fatal_gameplay_frame",
                                             "death_observed_lethal_contacts")}
        info.update(seed={"actual_seed": source["seed"]}, bootstrap=False,
                    score_delta_sum_raw_fixed=source["score_raw_fixed"])
        row = worker._canonical_row(source["episode_index"], source["seed"], info,
                                    True, False, death_fields)
        self.assertEqual(row["death_cause"], source["death_cause"])
        self.assertEqual(row["fatal_gameplay_frame"], source["fatal_gameplay_frame"])
        self.assertEqual(row["death_observed_lethal_contacts"],
                         source["death_observed_lethal_contacts"])

    def test_actual_native_fixture_contract_terminal_and_reference_release(self):
        from dodge_rl import VecDodgeEnv
        from dodge_rl.dev_eval import development_environment_config

        class FixedLeftPolicy(FakeModel):
            calls = 0
            def forward(self, global_feats, entity_feats, entity_types, entity_mask):
                logits = torch.full((global_feats.shape[0], 9), -1.0)
                logits[:, 1 + (self.calls % 8)] = 1.0
                self.calls += 1
                return type("Output", (), {"logits": logits})()

        self.assertTrue(all(callable(getattr(VecDodgeEnv, name, None))
                            for name in ("episode_info", "observations", "reset_done", "step")))
        self.assertFalse(hasattr(VecDodgeEnv, "close"))
        signature = inspect.signature(VecDodgeEnv)
        self.assertEqual(signature.parameters["action_repeat"].default, 4)
        self.assertEqual(signature.parameters["raw_frame_cap"].default, 18000)
        fixture_seed = pe.SEEDS[0]
        made = [0]
        def native_factory(**config):
            env = VecDodgeEnv(**config)
            made[0] += 1
            return env
        def native_config(seed, stage):
            config = development_environment_config(seed, stage)
            config["difficulty"] = 3
            config["raw_frame_cap"] = 128
            return config
        persisted = []
        started = time.monotonic()
        rows = worker.evaluate(FixedLeftPolicy(), checkpoint="best204", mode="argmax", replicate_seed=None,
                               env_factory=native_factory, config_factory=native_config,
                               seeds=(fixture_seed,), episode_sink=persisted.append,
                               on_episode_row=lambda row: None, fixture=True)
        elapsed = time.monotonic() - started
        gc.collect()
        self.assertLessEqual(rows[0]["gameplay_frames"], 128)
        self.assertLessEqual(rows[0]["gameplay_frames"] // 4, 32)
        self.assertTrue(rows[0]["truncated"], "bounded native fixture should reach its cap cleanly")
        self.assertEqual(persisted, rows)
        self.assertEqual(made[0], 1)
        self.assertLess(elapsed, 30.0)
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_bytes = peak if sys.platform == "darwin" else peak * 1024
        self.assertLess(peak_bytes, 6 * 1024**3)
        # Artifact destination is caller-owned: only an explicit env path writes; default writes nothing.
        destination = os.environ.get("PAIRED_EVAL_FIXTURE_RESULT")
        if destination:
            Path(destination).write_text(json.dumps({
                "schema": "paired_eval_native_fixture_result_v1", "seed": fixture_seed,
                "difficulty": 3, "action_repeat": 4, "raw_frame_cap": 128,
                "decision_count": rows[0]["gameplay_frames"] // 4,
                "elapsed_seconds": elapsed, "process_peak_rss_bytes": peak_bytes,
                "row": rows[0], "status": "bounded_cap_truncation",
                "terminal_observation": "No native death within the authorized 32-decision fixture cap.",
            }, sort_keys=True, indent=2) + "\n")

    def test_actual_native_failure_cleanup_drops_wrapper_and_preserves_error(self):
        from dodge_rl import VecDodgeEnv
        from dodge_rl.dev_eval import development_environment_config

        state = {"released": False}
        class FailingNativeProxy:
            def __init__(self, **config):
                self.native = VecDodgeEnv(**config)
            def episode_info(self):
                return self.native.episode_info()
            def observations(self):
                return self.native.observations()
            def step(self, _actions):
                raise RuntimeError("injected fixture step failure")
            def __del__(self):
                state["released"] = True
        def native_config(seed, stage):
            config = development_environment_config(seed, stage)
            config["raw_frame_cap"] = 4
            return config
        with self.assertRaisesRegex(RuntimeError, "injected fixture step failure"):
            worker.evaluate(FakeModel(), checkpoint="best204", mode="argmax", replicate_seed=None,
                            env_factory=FailingNativeProxy, config_factory=native_config,
                            seeds=(pe.SEEDS[0],), fixture=True)
        gc.collect()
        self.assertTrue(state["released"])

    def test_resource_reader_ignores_partial_tail_and_fails_closed_when_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "resources.jsonl"
            complete = json.dumps({"monotonic": 10.0, "rss_bytes": 123, "mps_driver_bytes": 456})
            path.write_bytes((complete + "\n{\"monotonic\":").encode())
            self.assertEqual(supervisor.latest_resource_sample(path, clock=lambda: 10.5)["rss_bytes"], 123)
            self.assertEqual(supervisor.read_resource_log(path)[1], len(b"{\"monotonic\":"))
            self.assertEqual(supervisor.latest_resource_sample(path, clock=lambda: 11.0)["rss_bytes"], 123)
            with self.assertRaisesRegex(ValueError, "stale"):
                supervisor.latest_resource_sample(path, clock=lambda: 11.01)
            # Partial-only first line is the same startup state as an empty log: unknown, not an error.
            path.write_bytes(b"{\"monotonic\":")
            self.assertIsNone(supervisor.latest_resource_sample(path, clock=lambda: 10.5))
            path.write_bytes(b"")
            self.assertIsNone(supervisor.latest_resource_sample(path, clock=lambda: 10.5))
            # Malformed COMPLETE samples still fail closed.
            path.write_bytes(b"{\"monotonic\": 1.0}\n")
            with self.assertRaisesRegex(ValueError, "malformed"):
                supervisor.latest_resource_sample(path, clock=lambda: 1.0)
            path.write_bytes(b"not-json\n")
            with self.assertRaises(ValueError):
                supervisor.latest_resource_sample(path, clock=lambda: 1.0)

    def test_freshness_clock_is_read_after_sample_so_new_sample_is_never_negative_age(self):
        # Sample written after the loop clock (10.0) but before the post-read clock (10.3).
        # The old loop-clock ordering would give age -0.2 and abort a healthy run.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "resources.jsonl"
            newer = json.dumps({"monotonic": 10.2, "rss_bytes": 1, "mps_driver_bytes": 2})
            path.write_bytes((newer + "\n").encode())
            loop_clock = 10.0
            reads = iter([10.3])
            sample = supervisor.latest_resource_sample(path, clock=lambda: next(reads))
            self.assertEqual(sample["mps_driver_bytes"], 2)
            self.assertGreater(sample["monotonic"], loop_clock)
            # Negative controls: a clock earlier than the sample (negative age) and a too-old sample both fail closed.
            with self.assertRaisesRegex(ValueError, "stale"):
                supervisor.latest_resource_sample(path, clock=lambda: 10.19)
            with self.assertRaisesRegex(ValueError, "stale"):
                supervisor.latest_resource_sample(path, clock=lambda: 10.2 + supervisor.FRESHNESS_SECONDS + 0.01)

    def test_resource_sampler_error_before_first_sample_is_unknown_and_fails_closed(self):
        def broken_probe():
            raise RuntimeError("injected MPS probe failure")
        with tempfile.TemporaryDirectory() as directory:
            sampler = worker.ResourceSampler(Path(directory) / "resources.jsonl", probe=broken_probe, period=0.01)
            sampler.start()
            with self.assertRaisesRegex(ValueError, "startup bound|sampler failed"):
                sampler.wait_first_sample(timeout=5.0)
            with self.assertRaisesRegex(ValueError, "injected MPS probe failure"):
                sampler.require_live()
            self.assertIsNone(supervisor.latest_resource_sample(Path(directory) / "resources.jsonl"))
            sampler.stop_event.set()
            sampler.thread.join(timeout=2.0)

    def test_resource_sampler_stopped_or_missing_first_sample_blocks_worker_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            sampler = worker.ResourceSampler(Path(directory) / "resources.jsonl",
                                             probe=lambda: (1, 2), period=0.01)
            with self.assertRaisesRegex(ValueError, "not running"):
                sampler.require_live()
            sampler.start()
            sampler.wait_first_sample(timeout=5.0)
            sampler.require_live()
            sampler.close()
            with self.assertRaisesRegex(ValueError, "not running"):
                sampler.require_live()

    def test_synthetic_gil_and_fsync_contention_freshness_measurement(self):
        # Synthetic only: a Python GIL spinner plus extra fsync traffic next to the real sampler loop.
        # It is not the real worker and does not validate production MPS load. Records observed gaps.
        import threading as _threading
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "resources.jsonl"
            stop = _threading.Event()
            def spin():
                value = 0
                while not stop.is_set():
                    value = (value + 1) % 1000003
            def fsync_churn():
                with (Path(directory) / "churn.bin").open("wb") as stream:
                    while not stop.is_set():
                        stream.write(b"x" * 65536)
                        stream.flush()
                        os.fsync(stream.fileno())
            threads = [_threading.Thread(target=spin, daemon=True), _threading.Thread(target=fsync_churn, daemon=True)]
            sampler = worker.ResourceSampler(path, probe=lambda: (1, 2), period=supervisor.SAMPLE_SECONDS)
            for thread in threads:
                thread.start()
            sampler.start()
            try:
                sampler.wait_first_sample(timeout=5.0)
                ages = []
                started = time.monotonic()
                while time.monotonic() - started < 2.0:
                    sample = supervisor.latest_resource_sample(path, clock=time.monotonic)
                    ages.append(time.monotonic() - sample["monotonic"])
                    time.sleep(0.05)
            finally:
                sampler.close()
                stop.set()
                for thread in threads:
                    thread.join(timeout=2.0)
            self.assertGreater(len(ages), 10)
            self.assertTrue(all(0.0 <= age <= supervisor.FRESHNESS_SECONDS for age in ages),
                            f"max observed age {max(ages):.4f}s")

    def test_stop_owned_child_signals_surviving_group_after_leader_exit_and_never_after_absence(self):
        class ExitedLeader:
            pid = 424243
            def poll(self):
                return 0
            def wait(self, timeout=None):
                return 0
        signals = []
        states = iter([True, True, False])
        with mock.patch.object(supervisor, "group_exists", side_effect=lambda pgid: next(states, False)), \
             mock.patch.object(supervisor.os, "killpg", side_effect=lambda pgid, number: signals.append(number)):
            result = supervisor.stop_owned_child(ExitedLeader(), drain_seconds=0.5, sleep=lambda _s: None,
                                                 clock=lambda: 0.0)
        self.assertEqual(signals, [supervisor.signal.SIGTERM])
        self.assertEqual(result["raw_exit"], 0)
        self.assertTrue(result["direct_child_reaped"])
        self.assertTrue(result["group_absent_after_reap"])
        # Negative control: absence proven before any signal means no group signal at all.
        signals.clear()
        with mock.patch.object(supervisor, "group_exists", return_value=False), \
             mock.patch.object(supervisor.os, "killpg", side_effect=lambda pgid, number: signals.append(number)):
            result = supervisor.stop_owned_child(ExitedLeader(), sleep=lambda _s: None, clock=lambda: 0.0)
        self.assertEqual(signals, [])
        self.assertEqual(result["signals"], [])
        self.assertTrue(result["group_absent_after_reap"])

    def test_private_rng_is_independent_of_removal_order_and_common_across_checkpoints(self):
        seeds = list(pe.SEEDS[:8])
        def sequence(seed, replicate=64001):
            stream = pe.UniformStream(replicate, seed)
            return [stream.next() for _ in range(3)]
        original = {seed: sequence(seed) for seed in seeds}
        reordered = {}
        for seed in reversed(seeds[1:]):
            reordered[seed] = sequence(seed)
        self.assertEqual({seed: original[seed] for seed in reordered}, reordered)
        self.assertEqual(original[seeds[0]], sequence(seeds[0]))
        self.assertNotEqual(original[seeds[0]], sequence(seeds[0], 64002))

    def test_inverse_cdf_float64_normalization_zeroes_and_exact_boundaries(self):
        self.assertEqual(pe.inverse_cdf([0.25, 0.0, 0.75], 0.0), 0)
        self.assertEqual(pe.inverse_cdf([0.25, 0.0, 0.75], 0.25), 2)
        self.assertEqual(pe.inverse_cdf([0.0, 0.5, 0.5], 0.999999999999), 2)
        with self.assertRaisesRegex(ValueError, "sum to zero"):
            pe.inverse_cdf([0.0, 0.0], 0.5)
        self.assertEqual(pe.sample_logits_cpu(torch.zeros(9, dtype=torch.float32), 0.5), 4)
        underflowed = torch.tensor([0.0] + [-1000.0] * 8, dtype=torch.float32)
        self.assertEqual(pe.sample_logits_cpu(underflowed, 0.999999999999), 0)

    def test_canonical_tails_are_bottom_top_sixteen_means_not_percentiles(self):
        value = pe._tail_means(range(64))
        self.assertEqual(value, {"bottom16_mean": 7.5, "top16_mean": 55.5, "all64_mean": 31.5})
        self.assertNotEqual(value["bottom16_mean"], float(np.quantile(np.arange(64), 0.25)))

    def test_checkpoint_receipt_and_terminal_status_substitution_rejected(self):
        best = worker.EXPECTED_RECEIPT_DETAILS["best204"]
        self.assertNotEqual(best["checkpoint_sha256"], worker.EXPECTED_RECEIPT_DETAILS["latest252"]["checkpoint_sha256"])
        self.assertEqual(supervisor.terminal_status(worker_status="complete", raw_exit=0,
                         child_reaped=True, group_absent=True, guard_ok=True, publication_ok=True),
                         "complete_pending_parent_acceptance")
        for kwargs in ({"raw_exit": 1}, {"child_reaped": False}, {"group_absent": False},
                       {"guard_ok": False}, {"publication_ok": False}):
            baseline = {"worker_status": "complete", "raw_exit": 0, "child_reaped": True,
                        "group_absent": True, "guard_ok": True, "publication_ok": True}
            baseline.update(kwargs)
            self.assertNotEqual(supervisor.terminal_status(**baseline), "complete_pending_parent_acceptance")

    def test_both_pinned_v3_checkpoints_load_strictly_and_receipt_substitution_fails(self):
        from dodge_rl import checkpoints
        from dodge_rl.models.teacher import OmniscientEntityTeacher
        for label in pe.CHECKPOINTS:
            checkpoint_path, checkpoint_hash = worker.EXPECTED_INPUTS[f"{label}_checkpoint"]
            receipt_path, _ = worker.EXPECTED_INPUTS[f"{label}_receipt"]
            state = checkpoints.load_checkpoint(ROOT / checkpoint_path, expected_sha256=checkpoint_hash)
            checkpoints.require_complete_update(state)
            receipt = json.loads((ROOT / receipt_path).read_text())
            anchored_receipt, _audit = worker._receipt_anchor(label, ROOT)
            self.assertEqual(anchored_receipt, receipt)
            worker.validate_checkpoint_receipt_binding(state, receipt, label, checkpoints.identity_hash)
            with torch.random.fork_rng(devices=[]):
                model = OmniscientEntityTeacher()
            model.load_state_dict(state["model"], strict=True)
            model.requires_grad_(False)
            self.assertFalse(any(parameter.requires_grad for parameter in model.parameters()))
            self.assertEqual(sum(parameter.numel() for parameter in model.parameters()), 321290)
            substituted = dict(receipt)
            substituted["checkpoint_sha256"] = worker.EXPECTED_INPUTS[
                "latest252_checkpoint" if label == "best204" else "best204_checkpoint"][1]
            with self.assertRaisesRegex(ValueError, "Checkpoint/terminal receipt binding differs"):
                worker.validate_checkpoint_receipt_binding(state, substituted, label, checkpoints.identity_hash)
            wrong_schema = dict(receipt)
            wrong_schema["schema"] = "d2_normal_training_parent_terminal_receipt_v1" if label == "best204" else "d2_retained_best_candidate_parent_receipt_v1"
            with self.assertRaisesRegex(ValueError, "Checkpoint/terminal receipt binding differs"):
                worker.validate_checkpoint_receipt_binding(state, wrong_schema, label, checkpoints.identity_hash)


    def _run_once_fake_child(self, directory, *, exit_code=0, now=100.0, fail_lease_at=None):
        output = Path(directory) / "run"
        class FakeProcess:
            pid = 424242
            done = False
            result_code = exit_code
            def poll(self):
                return self.result_code if self.done else None
            def wait(self, timeout=None):
                self.done = True
                return exit_code
        process = FakeProcess()
        calls = {"lease": 0}
        def fake_popen(command, **kwargs):
            out = Path(command[command.index("--output") + 1])
            out.mkdir(parents=True)
            (out / "worker-result.json").write_text(json.dumps({"status": "complete" if exit_code == 0 else "failed"}))
            resources = Path(command[command.index("--resource-log") + 1])
            resources.write_text(json.dumps({"monotonic": now, "rss_bytes": 1024,
                                             "mps_driver_bytes": 1024}) + "\n")
            return process
        def lease(*args, **kwargs):
            calls["lease"] += 1
            if fail_lease_at == calls["lease"]:
                raise ValueError("injected lease guard failure")
            return {}
        def stop(proc):
            proc.result_code = -15
            proc.done = True
            return {"owned_pid": proc.pid, "owned_pgid": proc.pid, "raw_exit": -15,
                    "direct_child_reaped": True, "group_absent_after_reap": True,
                    "signals": ["SIGTERM"], "errors": []}
        with mock.patch.object(supervisor, "verify_inputs", return_value={
                "interpreter": {"lexical_venv_path": str(supervisor.ROOT / "python/.venv/bin/python"),
                                "resolved_target": str(Path(__import__("sys").executable).resolve())}}), \
             mock.patch.object(supervisor, "_lease_check", side_effect=lease), \
             mock.patch.object(supervisor, "supervisor_peak_rss", return_value=1024), \
             mock.patch.object(supervisor, "observed_rss", return_value=1024), \
             mock.patch.object(supervisor, "group_exists", return_value=False), \
             mock.patch.object(supervisor, "stop_owned_child", side_effect=stop):
            times = iter([100.0, 100.0, now, now, now, now, now, now, now])
            result = supervisor.run_once(output, python=supervisor.ROOT / "python/.venv/bin/python",
                                         protocol_path=Path("protocol-proposed.json"),
                                         state_path=Path(directory) / "state.json",
                                         clock=lambda: next(times, now), popen=fake_popen,
                                         sleep=lambda _seconds: setattr(process, "done", True))
        return result

    def test_run_once_harmless_child_success_and_worker_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self._run_once_fake_child(directory)
            self.assertEqual(result["status"], "complete_pending_parent_acceptance")
            self.assertEqual(result["worker_launch_count"], 1)
            self.assertEqual(result["raw_worker_exit"], 0)
            self.assertTrue((Path(directory) / "run" / "preparation-receipt.json").is_file())
        with tempfile.TemporaryDirectory() as directory:
            result = self._run_once_fake_child(directory, exit_code=7)
            self.assertEqual(result["status"], "failed_worker")
            self.assertEqual(result["raw_worker_exit"], 7)

    def test_run_once_work_deadline_and_lease_guard_cancel_are_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self._run_once_fake_child(directory, now=700.0)
            self.assertEqual(result["status"], "failed_postflight_or_publication")
            self.assertEqual(result["cancellation_lineage"][0]["kind"], "590_second_work_deadline")
            self.assertIsNotNone(result["owned_process_cleanup"])
            self.assertEqual(result["raw_worker_exit"], -15)
        with tempfile.TemporaryDirectory() as directory:
            result = self._run_once_fake_child(directory, fail_lease_at=2)
            self.assertEqual(result["status"], "failed_postflight_or_publication")
            self.assertEqual(result["cancellation_lineage"][0]["kind"], "lease_or_parent_cancel")
        with tempfile.TemporaryDirectory() as directory:
            result = self._run_once_fake_child(directory, fail_lease_at=4)
            self.assertEqual(result["status"], "failed_postflight_or_publication")
            self.assertIn("publication_failure", result)

    def test_cancellation_and_postpublication_guard_failures_reject_success_status(self):
        self.assertEqual(supervisor.terminal_status(worker_status="complete", raw_exit=0,
                         child_reaped=True, group_absent=True, guard_ok=False, publication_ok=True),
                         "failed_postflight_or_publication")
        self.assertTrue(supervisor.resources_within_limits(1024, 1024))
        self.assertFalse(supervisor.resources_within_limits(supervisor.RSS_LIMIT + 1, 1024))
        self.assertFalse(supervisor.resources_within_limits(1024, supervisor.MPS_LIMIT + 1))
        self.assertEqual(supervisor.terminal_status(worker_status="complete", raw_exit=0,
                         child_reaped=True, group_absent=True, guard_ok=True, publication_ok=False),
                         "failed_postflight_or_publication")


if __name__ == "__main__":
    unittest.main()
