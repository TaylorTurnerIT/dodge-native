"""Synthetic specification tests only; dummy vectors reserve no study seeds."""

from collections import Counter
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from scheduler_reference import (
    Completion, DOMAIN, Scheduler, assignment_block, canonical, vector_hash,
)

SEEDS = dict(constructor_init_seed=1, python_random_seed=2, numpy_global_seed=3,
             torch_cpu_global_seed=4, action_sampler_torch_mps_seed=5,
             env_master_seed=6)
DIGEST = vector_hash("SYNTHETIC-NOT-RESERVED", 1, SEEDS)


def rows(flags, generation=0, horizon=None):
    if horizon is None:
        horizon = 1000 * (generation + 1)
    return [Completion(i // 64, i % 64, generation, horizon, flag)
            for i, flag in enumerate(flags)]


def window(successes):
    return [True] * successes + [False] * (100 - successes)


def finish_empty(scheduler, count):
    for _ in range(count):
        scheduler.finish_update(scheduler.update + 1, [])


class AssignmentTests(unittest.TestCase):
    def test_canonical_r5_vector_encoding(self):
        payload = {"study_id": "SYNTHETIC-NOT-RESERVED", "replica": 1,
                   "seeds": SEEDS}
        exact = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False).encode("utf-8")
        self.assertEqual(DIGEST, hashlib.sha256(exact).hexdigest())
        self.assertNotEqual(DIGEST, vector_hash("SYNTHETIC-NOT-RESERVED", 2, SEEDS))
        self.assertEqual(canonical("\u00e9"), b'"\\u00e9"')

    def test_invalid_vectors_rejected(self):
        for change in ({"constructor_init_seed": 2**32},
                       {"numpy_global_seed": -1}, {"env_master_seed": True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                vector_hash("SYNTHETIC", 1, {**SEEDS, **change})
        with self.assertRaises(ValueError):
            vector_hash("SYNTHETIC", 1, {**SEEDS, "extra": 7})

    def test_replica_ids_match_accepted_transition_contract(self):
        for replica in (1, 2, 3):
            self.assertEqual(len(vector_hash("SYNTHETIC", replica, SEEDS)), 64)
        for replica in (0, 4, -1, True, 1.0):
            with self.subTest(replica=replica), self.assertRaises(ValueError):
                vector_hash("SYNTHETIC", replica, SEEDS)

    def test_all_stage_quotas_and_remainder_fairness(self):
        self.assertEqual(assignment_block(DIGEST, 0, 5), (1000,) * 100)
        for generation in range(1, 18):
            totals = Counter()
            q, r = divmod(30, generation)
            for block in range(generation):
                counts = Counter(assignment_block(DIGEST, generation, block))
                self.assertEqual(counts[1000 * (generation + 1)], 70)
                self.assertEqual(sum(counts.values()), 100)
                for i in range(generation):
                    self.assertIn(counts[1000 * (i + 1)], (q, q + 1))
                    totals[i] += counts[1000 * (i + 1)]
            self.assertEqual(set(totals.values()), {30})
            self.assertLess(r, generation)

    def test_permutation_matches_independent_wire_rule(self):
        generation, block = 7, 3
        base = [8000] * 70
        for i in range(7):
            base += [1000 * (i + 1)] * (4 + (i in (6, 0)))
        order = sorted(range(100), key=lambda i: (
            hashlib.sha256(json.dumps(
                [DOMAIN, DIGEST, generation, block, i], sort_keys=True,
                separators=(",", ":"), ensure_ascii=True,
                allow_nan=False).encode("utf-8")).digest(), i))
        self.assertEqual(assignment_block(DIGEST, generation, block),
                         tuple(base[i] for i in order))

    def test_digest_ties_use_base_index(self):
        class SameHash:
            def digest(self):
                return bytes(32)
        with patch("scheduler_reference.hashlib.sha256", return_value=SameHash()):
            block = assignment_block(DIGEST, 1, 0)
        self.assertEqual(block, (2000,) * 70 + (1000,) * 30)

    def test_stream_ordinal_partial_blocks_and_entry_reset(self):
        scheduler = Scheduler(DIGEST)
        assigned = [scheduler.assign() for _ in range(105)]
        self.assertEqual([row[2] for row in assigned], list(range(105)))
        scheduler.finish_update(1, rows(window(90) * 2))
        finish_empty(scheduler, 9)
        self.assertEqual(scheduler.assign(),
                         (1, assignment_block(DIGEST, 1, 0)[0], 0))

    def test_hash_isolation_no_rng_imports_or_calls(self):
        import ast
        from pathlib import Path
        tree = ast.parse((Path(__file__).resolve().parents[1] / "successor/scheduler_reference.py").read_text())
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module)
        self.assertEqual(imports, {"dataclasses", "hashlib", "json"})
        self.assertEqual(assignment_block(DIGEST, 9, 2),
                         assignment_block(DIGEST, 9, 2))


class MasteryTests(unittest.TestCase):
    def test_89_90_91_success_threshold(self):
        for successes in (89, 90, 91):
            scheduler = Scheduler(DIGEST)
            result = scheduler.finish_update(1, rows(window(successes)))
            self.assertEqual(result["window_results"], [successes >= 90])

    def test_199_200_targets_and_9_10_updates(self):
        scheduler = Scheduler(DIGEST)
        scheduler.finish_update(1, rows([True] * 199))
        finish_empty(scheduler, 8)
        self.assertEqual((scheduler.stage_updates, scheduler.target_episodes), (9, 199))
        self.assertEqual(scheduler.generation, 0)
        result = scheduler.finish_update(10, rows([True]))
        self.assertTrue(result["promoted"])
        self.assertEqual((scheduler.stage_updates, scheduler.target_episodes,
                          scheduler.streak, scheduler.partial), (0, 0, 0, []))

    def test_early_passes_survive_until_update10(self):
        scheduler = Scheduler(DIGEST)
        scheduler.finish_update(1, rows(window(90) * 2))
        finish_empty(scheduler, 8)
        self.assertEqual(scheduler.generation, 0)
        finish_empty(scheduler, 1)
        self.assertEqual(scheduler.mastered, [(1000, 10)])

    def test_later_failed_window_erases_preminimum_passes(self):
        scheduler = Scheduler(DIGEST)
        scheduler.finish_update(1, rows(window(90) * 2))
        scheduler.finish_update(2, rows(window(89)))
        finish_empty(scheduler, 8)
        self.assertEqual((scheduler.generation, scheduler.streak), (0, 0))

    def test_same_update_pass_pass_fail_never_promotes(self):
        scheduler = Scheduler(DIGEST)
        finish_empty(scheduler, 9)
        result = scheduler.finish_update(10, rows(window(90) * 2 + window(89)))
        self.assertEqual(result["window_results"], [True, True, False])
        self.assertFalse(result["promoted"])

    def test_pass_fail_pass_is_only_one_consecutive_pass(self):
        scheduler = Scheduler(DIGEST)
        finish_empty(scheduler, 9)
        scheduler.finish_update(10, rows(window(90) + window(89) + window(91)))
        self.assertEqual((scheduler.generation, scheduler.streak), (0, 1))

    def test_partial_window_carries_and_does_not_erase_streak(self):
        scheduler = Scheduler(DIGEST)
        scheduler.finish_update(1, rows([True] * 99))
        result = scheduler.finish_update(2, rows([False]))
        self.assertEqual(result["window_results"], [True])
        self.assertEqual(scheduler.partial, [])
        scheduler.finish_update(3, rows(window(90) + [False] * 99))
        finish_empty(scheduler, 7)
        self.assertEqual(scheduler.generation, 1)
        self.assertEqual(scheduler.partial, [])

    def test_whole_simultaneous_batch_uses_slot_order(self):
        scheduler = Scheduler(DIGEST)
        scheduler.finish_update(1, rows([True] * 89 + [False] * 10))
        batch = [Completion(0, 1, 0, 1000, False),
                 Completion(0, 0, 0, 1000, True)]
        result = scheduler.finish_update(2, batch)
        self.assertEqual(result["window_results"], [True])
        self.assertEqual(scheduler.partial, [False])

    def test_stable_update_order_and_whole_input_validation(self):
        scheduler = Scheduler(DIGEST)
        before = copy.deepcopy(scheduler)
        bad = rows([True]) + [Completion(0, 0, 0, 1000, False)]
        with self.assertRaises(ValueError):
            scheduler.finish_update(1, bad)
        self.assertEqual(scheduler, before)
        with self.assertRaises(ValueError):
            scheduler.finish_update(2, [])
        self.assertEqual(scheduler, before)

    def test_old_inflight_and_earlier_practice_never_count(self):
        scheduler = Scheduler(DIGEST)
        old_assignment = scheduler.assign()
        scheduler.finish_update(1, rows([True] * 200))
        finish_empty(scheduler, 9)
        mixed = rows([True] * 200, generation=0)
        mixed += [Completion(4, slot, 1, 1000, True) for slot in range(64)]
        scheduler.finish_update(11, mixed)
        self.assertEqual(old_assignment, (0, 1000, 0))
        self.assertEqual((scheduler.stage_updates, scheduler.target_episodes), (1, 0))

    def test_one_promotion_even_with_many_passing_windows(self):
        scheduler = Scheduler(DIGEST)
        finish_empty(scheduler, 9)
        scheduler.finish_update(10, rows([True] * 2000))
        self.assertEqual(scheduler.generation, 1)
        self.assertEqual(scheduler.mastered, [(1000, 10)])
        self.assertEqual(scheduler.stage_updates, 0)

    def test_global60_six_stage_ceiling_and_terminal_entry(self):
        scheduler = Scheduler(DIGEST)
        for update in range(1, 61):
            scheduler.finish_update(update, rows([True] * 200, scheduler.generation))
        self.assertEqual(scheduler.mastered,
                         [(1000 * i, 10 * i) for i in range(1, 7)])
        self.assertEqual((scheduler.horizon, scheduler.stage_updates), (7000, 0))
        with self.assertRaises(ValueError):
            scheduler.finish_update(61, [])
        with self.assertRaises(ValueError):
            scheduler.assign()

    def test_18000_has_no_next_stage(self):
        # Artificial state tests terminal-stage semantics, not pilot reachability.
        scheduler = Scheduler(DIGEST, generation=17)
        scheduler.finish_update(1, rows([True] * 200, 17))
        finish_empty(scheduler, 10)
        self.assertEqual(scheduler.generation, 17)
        self.assertEqual(scheduler.mastered, [(18000, 10)])
        self.assertTrue(scheduler.stage_mastered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
