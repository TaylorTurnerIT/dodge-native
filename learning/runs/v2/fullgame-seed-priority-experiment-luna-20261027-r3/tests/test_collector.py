"""Bounded CPU unit tests. Artificial fixtures and RNG states are not study seeds."""
import copy
from dataclasses import asdict, fields
import importlib.util
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
import torch

from successor import ppo
from successor.curriculum import (Assignment, CurriculumAdapter, HISTORICAL_RANGES,
    PINNED_PPO, PreparedUpdates, equal, validate_seed_union)
from successor.scheduler_reference import Completion, Scheduler
from fakes import FakeEnv, TinyNet, info

EVIDENCE = {}
DIGEST = "a" * 64  # Synthetic hash fixture, no actual vector/seeds.


class BoundaryFixtureScheduler(Scheduler):
    """Homogeneous stage assignments for existing boundary-only cases.

    Actual mixed assignments are exercised separately in test_maintenance.py.
    """
    def assign(self):
        generation, _horizon, ordinal = super().assign()
        return generation, 1000*(generation+1), ordinal


def adapter(env, enabled=True):
    with patch('successor.curriculum.Scheduler',BoundaryFixtureScheduler):
        return CurriculumAdapter(env, enabled=enabled, digest=DIGEST, replica=1,
                                 exclusion_ranges=HISTORICAL_RANGES)


def collect(env, boundary, steps, model=None, observation=None):
    model = TinyNet() if model is None else model
    return ppo.collect_rollout(model, env, steps, "cpu", config=PINNED_PPO,
                              boundary_adapter=boundary, observation=observation)


def scalar_gae(rewards, values, next_values, terminated, truncated, gamma, lam):
    """Independent Python-float scalar recurrence, slot by slot."""
    out = [[0.0 for _ in rewards[0]] for _ in rewards]
    for slot in range(len(rewards[0])):
        later = 0.0
        for t in reversed(range(len(rewards))):
            bootstrap_value = 0.0 if terminated[t][slot] else next_values[t][slot]
            residual = rewards[t][slot] + gamma * bootstrap_value - values[t][slot]
            later = residual if terminated[t][slot] or truncated[t][slot] else residual + gamma * lam * later
            out[t][slot] = later
    return out


class BoundaryTests(unittest.TestCase):
    def test_mixed_death_cutoff_continuing_cap_final_values_and_one_reset(self):
        env = FakeEnv(4, deaths={(0, 0): 1000})
        boundary = adapter(env)
        # Artificial cross-rollout state: all episodes still have normal-start
        # histories in this fake. This is not native runtime/parity evidence.
        env.infos = [info(0, frame=996), info(1, frame=996),
                     info(2, frame=996), info(3, frame=17996)]
        boundary.assignments[2] = Assignment(1, 2000, 2)
        boundary.assignments[3] = Assignment(17, 18000, 3)
        boundary.begin_update(1)
        result = collect(env, boundary, 1)
        self.assertEqual(env.cutoffs, [([1], [1000])])
        self.assertEqual(env.resets, [[0, 1, 3]])
        self.assertEqual(result.batch.terminated.tolist(), [[True, False, False, False]])
        self.assertEqual(result.batch.truncated.tolist(), [[False, True, False, True]])
        self.assertEqual(result.batch.next_values.tolist(), [[0.0, 1.0, 1.0, 18.0]])
        self.assertEqual([row["seed"]["episode"] for row in env.infos], [1, 1, 0, 1])
        self.assertEqual(result.batch.alive_raw_frames.tolist(), [[3, 4, 4, 4]])
        self.assertAlmostEqual(result.batch.raw_rewards[0, 0].item(), -4.97, places=5)
        self.assertEqual([r["success"] for r in boundary.completions], [False, True, True])
        self.assertEqual([r["slot"] for r in boundary.completions], [0, 1, 3])
        self.assertTrue(all("generation" not in row for row in result.completed_episodes))
        self.assertEqual(boundary.scheduler.update, 0)
        EVIDENCE["mixed_boundary"] = {"terminated": result.batch.terminated.tolist(),
            "truncated": result.batch.truncated.tolist(), "next_values": result.batch.next_values.tolist(),
            "native_cutoff_requests": env.cutoffs, "combined_resets": env.resets,
            "episode_indices_after_reset": [row["seed"]["episode"] for row in env.infos]}
        # Native owned final results remain valid after reset and later stepping.
        saved = result.batch.next_values.clone()
        env.step(np.zeros(4, np.int64))
        self.assertTrue(torch.equal(saved, result.batch.next_values))

    def test_scalar_gae_oracle_and_no_next_episode_leak(self):
        env = FakeEnv(4, deaths={(0, 0): 1000})
        boundary = adapter(env)
        env.infos = [info(slot, frame=996) for slot in range(3)] + [info(3, frame=17996)]
        boundary.assignments[2] = Assignment(1, 2000, 2)
        boundary.assignments[3] = Assignment(17, 18000, 3)
        boundary.begin_update(1)
        batch = collect(env, boundary, 3).batch
        args = [getattr(batch, name).double() if name not in ("terminated", "truncated")
                else getattr(batch, name) for name in
                ("rewards", "values", "next_values", "terminated", "truncated")]
        advantages, returns = ppo.compute_gae(*args, PINNED_PPO.gamma, PINNED_PPO.gae_lambda)
        expected = torch.tensor(scalar_gae(*[x.tolist() for x in args],
            PINNED_PPO.gamma, PINNED_PPO.gae_lambda), dtype=torch.float64)
        torch.testing.assert_close(advantages, expected, rtol=0, atol=1e-12)
        torch.testing.assert_close(returns, expected + batch.values.double(), rtol=0, atol=1e-12)
        self.assertAlmostEqual(advantages[0, 1].item(), args[0][0, 1].item()
                               + .995 * 1.0 - args[1][0, 1].item())
        self.assertAlmostEqual(advantages[0, 0].item(), args[0][0, 0].item() - args[1][0, 0].item())

    def test_decision255_boundary_and_cross_rollout_episode_persistence(self):
        env = FakeEnv(2, deaths={(0, 0): 24})
        boundary = adapter(env)
        boundary.begin_update(1)
        first = collect(env, boundary, 256)
        self.assertIn((255, 0), [(r["decision"], r["slot"]) for r in boundary.completions])
        self.assertEqual(env.cutoffs, [([1], [1000]), ([0], [1000])])
        self.assertEqual(env.infos[1]["gameplay_frames"], 24)
        self.assertEqual(env.infos[0]["gameplay_frames"], 0)
        self.assertEqual(boundary.assignments[1].ordinal, 3)
        # Emulate the private post-PPO boundary only in this collector unit test.
        boundary._finish_after_ppo()
        boundary.begin_update(2)
        second = collect(env, boundary, 256, observation=first.observations)
        self.assertEqual(second.batch.shape, (256, 2))
        self.assertIn((243, 1), [(r["decision"], r["slot"]) for r in boundary.completions if r["update"] == 2])
        self.assertEqual(env.infos[0]["seed"]["episode"], 3)
        self.assertEqual(env.infos[1]["seed"]["episode"], 2)
        self.assertEqual(boundary.scheduler.update, 1)
        self.assertEqual([row["ordinal"] for row in boundary.assignment_events], list(range(7)))
        snap = boundary.snapshot()
        self.assertEqual(snap["gameplay_frames_including_fatal"], 512 * 2 * 4)
        self.assertEqual(snap["initial_construction_startup_frames"], 26)
        self.assertEqual(snap["reset_startup_frames"], 5 * 13)
        self.assertEqual(sum(r["executed_gameplay_frames"] for r in snap["interval_exposure"]), 4096)
        self.assertEqual(sum(r["raw_frames"] for r in snap["update_exposure"]), 4096)
        self.assertEqual(len(snap["in_flight"]), 2)

    def test_true_death_precedence_at_hminus1_h_and_no_hplus1_simulation(self):
        for fatal_frame in (999, 1000, 1001):
            with self.subTest(fatal_frame=fatal_frame):
                env = FakeEnv(1, deaths={(0, 0): fatal_frame})
                boundary = adapter(env)
                env.infos = [info(0, frame=996)]
                boundary.begin_update(1)
                result = collect(env, boundary, 1)
                death = fatal_frame <= 1000
                self.assertEqual(result.batch.terminated.item(), death)
                self.assertEqual(result.batch.truncated.item(), not death)
                self.assertEqual(env.cutoffs, [] if death else [([0], [1000])])
                self.assertEqual(result.completed_episodes[0]["gameplay_frames"], min(fatal_frame, 1000))
                self.assertEqual(result.completed_episodes[0]["death_cause"], "synthetic" if death else None)

    def test_overshoot_and_misalignment_reject_before_extra_simulation(self):
        for frame in (997, 1000, 1004):
            with self.subTest(frame=frame):
                env = FakeEnv(1)
                boundary = adapter(env)
                env.infos = [info(0, frame=frame)]
                boundary.begin_update(1)
                with self.assertRaises(ValueError):
                    collect(env, boundary, 1)
                self.assertEqual(env.step_calls, 0)
                self.assertEqual(env.cutoffs, [])
                self.assertEqual(env.resets, [])

    def test_corrupt_native_return_fails_closed_without_reset_or_fake_flags(self):
        for corruption in ("reward", "other_slot", "history", "step_payload", "order", "short"):
            with self.subTest(corruption=corruption):
                env = FakeEnv(2)
                boundary = adapter(env)
                env.infos = [info(slot, frame=996) for slot in range(2)]
                env.corruption = corruption
                boundary.begin_update(1)
                with self.assertRaises(ValueError):
                    collect(env, boundary, 1)
                self.assertEqual(env.resets, [])
                self.assertEqual(boundary.scheduler.update, 0)
                self.assertFalse(env.last_result["truncated"].any())

    def test_missing_native_method_never_falls_back_to_flags(self):
        env = FakeEnv(1)
        boundary = adapter(env)
        env.infos = [info(0, frame=996)]
        env.truncate_practice = None
        boundary.begin_update(1)
        with self.assertRaises(TypeError):
            collect(env, boundary, 1)
        self.assertFalse(env.last_result["truncated"].any())
        self.assertEqual(env.resets, [])

    def test_native_cutoff_precedes_inherited_audit_and_final_storage(self):
        env = FakeEnv(1)
        boundary = adapter(env)
        env.infos = [info(0, frame=996)]
        boundary.begin_update(1)
        original = ppo._audit_step
        audited_flags = []
        def observe(result, *args):
            self.assertEqual(env.cutoffs, [([0], [1000])])
            audited_flags.append(result["truncated"].tolist())
            return original(result, *args)
        with patch.object(ppo, "_audit_step", side_effect=observe):
            batch = collect(env, boundary, 1).batch
        self.assertEqual(audited_flags, [[True]])
        self.assertTrue(batch.truncated.item())

    def test_post_step_guard_failure_keeps_returned_frame_cost(self):
        env = FakeEnv(1)
        boundary = adapter(env)
        boundary.begin_update(1)
        def guard():
            if env.step_calls:
                raise RuntimeError("synthetic post-step guard")
        with self.assertRaisesRegex(RuntimeError, "synthetic post-step guard"):
            ppo.collect_rollout(TinyNet(), env, 1, "cpu", config=PINNED_PPO,
                               boundary_adapter=boundary, check_guard=guard)
        snap = boundary.snapshot()
        self.assertEqual(snap["returned_native_gameplay_frames_unaudited"], 4)
        self.assertEqual(snap["returned_work_not_accepted_by_audit"], 4)
        self.assertEqual(snap["raw_frames_total_including_returned_unaudited_work"], 17)
        self.assertEqual(snap["accepted_raw_frames_total"], 13)
        self.assertEqual(boundary.scheduler.update, 0)

    def test_post_reset_guard_failure_keeps_startup_cost_without_assignment(self):
        env = FakeEnv(1)
        boundary = adapter(env)
        env.infos = [info(0, frame=996)]
        boundary.begin_update(1)
        def guard():
            if env.resets:
                raise RuntimeError("synthetic post-reset guard")
        with self.assertRaisesRegex(RuntimeError, "synthetic post-reset guard"):
            ppo.collect_rollout(TinyNet(), env, 1, "cpu", config=PINNED_PPO,
                               boundary_adapter=boundary, check_guard=guard)
        snap = boundary.snapshot()
        self.assertEqual(snap["returned_reset_startup_frames_unaudited"], 13)
        self.assertEqual(snap["reset_startup_frames"], 0)
        self.assertEqual(snap["raw_frames_total_including_returned_unaudited_work"], 30)
        self.assertEqual(snap["normal_reset_count"], 0)
        self.assertEqual(len(snap["assignments"]), 1)
        self.assertEqual(boundary.scheduler.update, 0)
        row = snap["in_flight"][0]
        self.assertEqual(row["native_info"]["seed"]["episode"], 1)
        self.assertEqual(row["assignment_status"], "unassigned_unaudited")
        self.assertTrue(all(row[key] is None for key in ("generation", "horizon", "ordinal")))
        self.assertEqual(boundary.assignment_seeds[0]["episode"], 0)
        self.assertEqual(boundary.scheduler.assignment_ordinal, 1)

    def test_successful_reset_snapshot_uses_new_episode_assignment(self):
        env = FakeEnv(1)
        boundary = adapter(env)
        env.infos = [info(0, frame=996)]
        boundary.begin_update(1)
        collect(env, boundary, 1)
        row = boundary.snapshot()["in_flight"][0]
        self.assertEqual(row["native_info"]["seed"]["episode"], 1)
        self.assertEqual(row["assignment_status"], "assigned")
        self.assertEqual(row["ordinal"], 1)
        self.assertEqual(row["horizon"], 1000)
        self.assertEqual(len(boundary.assignment_events), 2)

    def test_same_slot_episode_number_but_different_seed_has_no_assignment(self):
        env = FakeEnv(1)
        boundary = adapter(env)
        env.infos[0]["seed"]["actual_seed"] += 1
        before = boundary.scheduler.assignment_ordinal
        row = boundary.snapshot()["in_flight"][0]
        self.assertEqual(row["assignment_status"], "unassigned_unaudited")
        self.assertTrue(all(row[key] is None for key in ("generation", "horizon", "ordinal")))
        self.assertEqual(boundary.scheduler.assignment_ordinal, before)
        self.assertEqual(len(boundary.assignment_events), 1)

    def test_control_matches_frozen_collector_all_buffers_and_rng(self):
        frozen_path = Path(__file__).resolve().parents[2] / 'D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime/dodge_rl/ppo.py'
        spec = importlib.util.spec_from_file_location("frozen_ppo_cpu_source_only", frozen_path)
        frozen = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = frozen
        spec.loader.exec_module(frozen)
        env1, env2 = FakeEnv(4, deaths={(0, 0): 1000}), FakeEnv(4, deaths={(0, 0): 1000})
        model1, model2 = TinyNet(), TinyNet()
        model2.load_state_dict(model1.state_dict())
        boundary = adapter(env2, False)
        boundary.begin_update(1)
        state = torch.random.get_rng_state()
        left = frozen.collect_rollout(model1, env1, 256, "cpu", config=frozen.PPOConfig(learning_rate=3e-5))
        after = torch.random.get_rng_state()
        torch.random.set_rng_state(state)
        right = collect(env2, boundary, 256, model2)
        self.assertTrue(torch.equal(after, torch.random.get_rng_state()))
        buffer_hashes = {}
        for field in fields(ppo.RolloutBatch):
            l, r = getattr(left.batch, field.name), getattr(right.batch, field.name)
            self.assertTrue(l is None and r is None or torch.equal(l, r), field.name)
            if r is not None:
                buffer_hashes[field.name] = hashlib.sha256(r.numpy().tobytes()).hexdigest()
        self.assertTrue(equal(left.observations, right.observations))
        self.assertTrue(equal(left.completed_episodes, right.completed_episodes))
        self.assertTrue(equal(left.reset_info, right.reset_info))
        self.assertEqual(env1.resets, env2.resets)
        self.assertEqual(env2.cutoffs, [])
        self.assertIsNone(boundary.scheduler)
        EVIDENCE["disabled_control_vs_frozen_source"] = {"all_buffers_exact": True,
            "buffer_hashes": buffer_hashes, "post_collection_rng_exact": True,
            "observations_completions_resets_exact": True, "practice_calls": len(env2.cutoffs),
            "transitions": right.batch.transitions, "limits": "synthetic CPU fixtures only; no native parity"}
        self.assertTrue(all("generation" not in asdict(right.batch) for _ in (0,)))

    def test_promotion_after_old_generation_reset_and_old_inflight_no_credit(self):
        env = FakeEnv(2)
        boundary = adapter(env)
        scheduler = boundary.scheduler
        for update in range(1, 10):
            scheduler.finish_update(update, [Completion(i // 64, i % 64, 0, 1000, True)
                for i in range(200)] if update == 1 else [])
        boundary.completed_updates = 9
        boundary.begin_update(10)
        collect(env, boundary, 256)
        self.assertEqual(scheduler.generation, 0)
        assignments = copy.deepcopy(boundary.assignments)
        self.assertTrue(boundary._finish_after_ppo()["promoted"])
        self.assertEqual(boundary.assignments, assignments)
        self.assertTrue(all(row.generation == 0 for row in assignments.values()))
        boundary.begin_update(11)
        collect(env, boundary, 256)
        self.assertTrue(all(row.generation == 1 for row in boundary.assignments.values()))
        self.assertTrue(all(row["generation"] == 0 for row in boundary.completions if row["update"] == 11))
        boundary._finish_after_ppo()
        self.assertEqual(scheduler.target_episodes, 0)
        self.assertEqual(scheduler.stage_updates, 1)
        self.assertEqual([row["ordinal"] for row in boundary.assignment_events[-2:]], [0, 1])
        EVIDENCE["old_generation"] = {"promotion_boundary": 10, "old_inflight_frozen": True,
            "old_completions_new_mastery_credit": scheduler.target_episodes,
            "new_stage_completed_updates": scheduler.stage_updates}

    def test_exposure_fatal_boundary_reach_without_alive_success_and_partial_stop(self):
        env = FakeEnv(2, deaths={(0, 0): 1000})
        boundary = adapter(env)
        boundary.begin_update(1)
        collect(env, boundary, 256)
        snap = boundary.snapshot()
        interval = snap["interval_exposure"][0]
        self.assertEqual(interval["executed_gameplay_frames"], 2048)
        self.assertEqual(interval["boundary_reaches"], 2)
        self.assertEqual(interval["alive_through"], 1)
        self.assertEqual(interval["interval_entries"], 4)
        self.assertEqual([row["native_info"]["gameplay_frames"] for row in snap["in_flight"]], [24, 24])
        self.assertEqual(snap["completed_updates"], 0)
        self.assertEqual(snap["pending_update"], 1)
        EVIDENCE["raw_frame_cost_and_partial_stop"] = {key: snap[key] for key in (
            "gameplay_frames_including_fatal", "initial_construction_startup_frames",
            "reset_startup_frames", "normal_reset_count",
            "raw_frames_total_including_returned_unaudited_work", "accepted_raw_frames_total",
            "interval_exposure", "update_exposure", "completed_updates", "pending_update")}


class UnionAndUpdateTests(unittest.TestCase):
    def test_explicit_future_union_strict_validation_without_five_range_change(self):
        expanded = tuple(sorted((*HISTORICAL_RANGES, (10, 20))))
        self.assertEqual(validate_seed_union(expanded), expanded)
        for bad in (None, (), ((0, 2**32-1),), HISTORICAL_RANGES[::-1],
                    HISTORICAL_RANGES[:-1], tuple(sorted((*HISTORICAL_RANGES, (True, 2)))),
                    tuple(sorted((*HISTORICAL_RANGES, (0, 100), (50, 200))))):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_seed_union(bad)
        env = FakeEnv(1)
        with self.assertRaisesRegex(ValueError, "union differs"):
            CurriculumAdapter(env, enabled=True, digest=DIGEST, replica=1, exclusion_ranges=expanded)
        env.infos[0]["seed"]["actual_seed"] = HISTORICAL_RANGES[0][0]
        with self.assertRaises(ValueError):
            adapter(env)

    def test_wrapper_real_cpu_ppo_then_finish_fixed64x256(self):
        env, model = FakeEnv(64), TinyNet()
        boundary = adapter(env)
        optimizer = torch.optim.Adam(model.parameters(), lr=3e-5, eps=1e-5)
        runner = PreparedUpdates(model, optimizer, boundary)
        collection, metrics, result = runner.update_once()
        self.assertEqual(collection.batch.shape, (256, 64))
        self.assertEqual(result["completed_update"], 1)
        self.assertEqual(boundary.scheduler.update, 1)
        self.assertEqual(boundary.scheduler.stage_updates, 1)
        self.assertEqual(runner.actual_optimizer_steps, metrics["optimizer_steps"])
        self.assertEqual(metrics["optimizer_steps"], 32 * metrics["epochs_completed"])
        self.assertLessEqual(metrics["optimizer_steps"], 128)
        self.assertTrue(all(group["lr"] == 3e-5 for group in optimizer.param_groups))
        self.assertEqual(env.cutoffs, [(list(range(64)), [1000] * 64)])
        EVIDENCE["wrapper_one_synthetic_update"] = {"shape": list(collection.batch.shape),
            "transitions": metrics["transitions"], "actual_optimizer_steps": metrics["optimizer_steps"],
            "epochs_completed": metrics["epochs_completed"], "boundary": result,
            "global_completed_updates": boundary.completed_updates, "constant_lr": 3e-5}
        with self.assertRaises(ValueError):
            boundary._finish_after_ppo()

    def test_failed_ppo_does_not_charge_or_promote_and_session_cannot_retry(self):
        env, model = FakeEnv(64), TinyNet()
        boundary = adapter(env)
        runner = PreparedUpdates(model, torch.optim.Adam(model.parameters(), lr=3e-5, eps=1e-5), boundary)
        with patch.object(ppo, "ppo_update", side_effect=RuntimeError("synthetic PPO failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic PPO failure"):
                runner.update_once()
        self.assertEqual(boundary.scheduler.update, 0)
        self.assertEqual(boundary.scheduler.stage_updates, 0)
        self.assertEqual(boundary.pending_update, 1)
        self.assertEqual(runner.state, "failed")
        self.assertEqual(len(boundary.completions), 64)
        before = env.step_calls
        with self.assertRaises(ValueError):
            runner.update_once()
        self.assertEqual(env.step_calls, before)

    def test_no_update61_no_drain_and_full_config_required(self):
        env, model = FakeEnv(64), TinyNet()
        boundary = adapter(env, False)
        optimizer = torch.optim.Adam(model.parameters(), lr=3e-5, eps=1e-5)
        runner = PreparedUpdates(model, optimizer, boundary)
        boundary.completed_updates = 60
        before = boundary.snapshot()
        with self.assertRaisesRegex(ValueError, "terminal global60"):
            runner.update_once()
        self.assertEqual(env.step_calls, 0)
        self.assertEqual(boundary.snapshot(), before)
        for config in (ppo.PPOConfig(), ppo.PPOConfig(learning_rate=3e-5, target_kl=.1)):
            with self.assertRaisesRegex(ValueError, "full pinned PPO"):
                PreparedUpdates(model, optimizer, adapter(FakeEnv(64)), config=config)

    def test_actual_optimizer_steps_vary_under_unchanged_kl(self):
        env, model = FakeEnv(2), TinyNet()
        batch = ppo.collect_rollout(model, env, 4, "cpu", config=PINNED_PPO).batch
        # Synthetic stale-policy batch forces inherited epoch-end KL stopping;
        # settings remain identical. No actual policy/checkpoint is used.
        stale = copy.deepcopy(batch)
        stale.old_log_probs -= 1
        metrics = []
        for candidate_batch in (batch, stale):
            candidate = copy.deepcopy(model)
            optimizer = torch.optim.Adam(candidate.parameters(), lr=3e-5, eps=1e-5)
            progress = {}
            result = ppo.ppo_update(candidate, optimizer, candidate_batch, PINNED_PPO, progress=progress)
            metrics.append(result)
            self.assertEqual(result["optimizer_steps"], result["epochs_completed"])
            self.assertEqual(progress["optimizer_steps"], result["optimizer_steps"])
            self.assertTrue(progress["complete"])
        self.assertEqual([row["optimizer_steps"] for row in metrics], [4, 1])
        self.assertEqual([row["early_stop_kl"] for row in metrics], [False, True])
        self.assertEqual(asdict(PINNED_PPO)["target_kl"], .03)
        EVIDENCE["unchanged_kl_variable_steps"] = {"target_kl": .03, "learning_rate": 3e-5,
            "actual_optimizer_steps": [row["optimizer_steps"] for row in metrics],
            "epochs_completed": [row["epochs_completed"] for row in metrics],
            "early_stop_kl": [row["early_stop_kl"] for row in metrics],
            "no_topup": True, "fixture": "eight transitions, ordinary vs synthetic stale logprobs"}


if __name__ == "__main__":
    torch.set_num_threads(1)
    unittest.main(verbosity=2, failfast=True)
