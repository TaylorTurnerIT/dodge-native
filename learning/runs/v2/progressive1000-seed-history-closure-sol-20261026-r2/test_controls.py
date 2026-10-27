"""Synthetic/arithmetic checks only. No actual environment or RNG API access."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import unittest

import seed_controls as s

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]


def load(name):
    return json.loads((HERE / name).read_bytes())


class Controls(unittest.TestCase):
    def test_01_owned_empty_cache(self):
        self.assertTrue(sys.dont_write_bytecode)
        self.assertEqual(Path(sys.pycache_prefix), HERE / "empty-pycache")
        self.assertEqual(list((HERE / "empty-pycache").iterdir()), [])

    def test_02_rust_historical_reference_vectors(self):
        # Expected values came from pinned original JSONL seed metadata, not
        # from the function under test. Every original journal also replays.
        refs = load("history-reconstruction.json")["reference_vectors"]
        self.assertEqual(len(refs), 76)
        for row in refs:
            got = s.training_seed(row["run_master_seed"], row["slot"], row["episode"])
            self.assertEqual((got["counter"], got["actual_seed"]), (row["counter"], row["actual_seed"]))
        self.assertEqual(load("history-reconstruction.json")["unmatched"], [])

    def test_03_rust_forced_B_D_E_edges(self):
        # Exact candidates and expected result from pinned Rust reservation test.
        rows = [0xB0000000, 0xB00003E7, 0xD0000000, 0xD000007F,
                0xE0000000, 0xE00003E7, 0xE00003E8]
        self.assertEqual(s.reject(lambda c: rows[c], s.normalize(s.HISTORICAL_RANGES)), (6, 0xE00003E8))

    def test_04_rust_normalization_reference(self):
        self.assertEqual(s.normalize([(9, 12), (0, 3), (4, 8), (s.U32, s.U32)]),
                         ((0, 12), s.NAMED_RANGES["B"], (s.U32, s.U32)))

    def test_05_invalid_and_full_union(self):
        for value in [[(8, 7)], [(0, s.U32)], [(0, 100), (101, s.U32)],
                      [(True, 1)], [(0, 1.0)], [(-1, 5)], [(0, s.U32 + 1)], [[1]]]:
            with self.assertRaises(ValueError):
                s.normalize(value)

    def test_06_six_range_union_is_canonical(self):
        union = s.normalize(list(s.NAMED_RANGES.values()))
        self.assertEqual([list(p) for p in union], load("proposed-exclusions.json")["canonical_sorted_merged_union"])
        self.assertEqual(len(union), 6)
        self.assertEqual(s.normalize(list(reversed(union)) + list(union)), union)

    def test_07_every_named_boundary_rejects(self):
        union = s.normalize(list(s.NAMED_RANGES.values()))
        candidates = [x for pair in union for x in pair] + [42]
        self.assertEqual(s.reject(lambda c: candidates[c], union), (12, 42))
        for lo, hi in union:
            self.assertFalse(s.inside(lo - 1, union))
            self.assertFalse(s.inside(hi + 1, union))

    def test_08_missing_new_cohort_fails_both_arms_before_construction(self):
        five = s.normalize([v for k, v in s.NAMED_RANGES.items() if k != "new_D2_evaluation_cohort"])
        six = s.normalize(list(s.NAMED_RANGES.values()))
        for arm in ("control", "curriculum"):
            with self.assertRaises(ValueError):
                s.require_training_union(five, arm)
            self.assertEqual(s.require_training_union(six, arm), six)
            with self.assertRaises(ValueError):
                s.require_training_union(tuple(reversed(six)), arm)

    def test_09_bounded_rejection_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "bounded control exhausted"):
            s.reject(lambda c: 0xD3000000, s.normalize(list(s.NAMED_RANGES.values())), budget=3)

    def test_10_native_tuple_rehash_on_forced_candidate(self):
        original = s.training_seed(7, 0, 0)
        seed = original["actual_seed"]
        rejected = s.training_seed(7, 0, 0, [(seed, seed)])
        self.assertGreater(rejected["counter"], original["counter"])
        self.assertNotEqual(rejected["actual_seed"], seed)
        self.assertNotEqual(s.candidate(1, 0, 0, 0), s.candidate(1 + (1 << 32), 0, 0, 0))
        # Rust uses wrapping additions even at u64 limits.
        self.assertIsInstance(s.candidate(s.U64, s.U64, s.U64, s.U64), int)

    def test_11_new_study_tokens_and_no_replica_reuse(self):
        obj = load("seed-vectors.json")
        self.assertEqual(obj["study_id"], s.STUDY_ID)
        masters = obj["derivation"]["prior_masters_rejected"]
        for i, row in enumerate(obj["vectors"], 1):
            self.assertEqual(s.derive(i, masters), row)
        for field in s.BOUNDS:
            self.assertEqual(len({row["seeds"][field] for row in obj["vectors"]}), 3)

    def test_12_canonical_vector_hash_matches_accepted_R5_function(self):
        path = REPO / "learning/runs/v2/confirmed324-probe-finalization-repair-sol-20261026-r5/probe.py"
        tree = ast.parse(path.read_bytes())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "canonical_vector_sha256")
        # Compile ONLY the pure canonical JSON hash function, never import or
        # execute probe capture, Torch, NumPy, native code, or policy RNG.
        namespace = {"hashlib": hashlib, "json": json}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
        for row in load("seed-vectors.json")["vectors"]:
            self.assertEqual(namespace[function.name](s.STUDY_ID, row["replica"], row["seeds"]), row["vector_sha256"])
            self.assertNotEqual(s.vector_hash("different-study", row["replica"], row["seeds"]), row["vector_sha256"])
            self.assertEqual(s.vector_hash(s.STUDY_ID, row["replica"], dict(reversed(list(row["seeds"].items())))), row["vector_sha256"])

    def test_13_reject_incomplete_or_noninteger_vectors(self):
        seeds = load("seed-vectors.json")["vectors"][0]["seeds"]
        for changed in [{**seeds, "torch_cpu_global_seed": True}, {**seeds, "env_master_seed": 0},
                        {**seeds, "extra": 1}, {k: v for k, v in seeds.items() if k != "numpy_global_seed"}]:
            with self.assertRaises(ValueError):
                s.vector_hash(s.STUDY_ID, 1, changed)
        for replica in (True, 0, 4, 1.0):
            with self.assertRaises(ValueError):
                s.vector_hash(s.STUDY_ID, replica, seeds)

    def test_14_all_192_initial_controls_and_offsets(self):
        obj = load("seed-vectors.json")
        union = s.normalize(list(s.NAMED_RANGES.values()))
        for vector, controls in zip(obj["vectors"], load("initial-slot-controls.json")["replicas"]):
            rows = controls["slots"]
            self.assertEqual(len(rows), 64)
            self.assertEqual(len({r["actual_seed"] for r in rows}), 64)
            for slot, row in enumerate(rows):
                self.assertEqual(row["episode"], obj["parent"]["next_episode_indices"][slot])
                self.assertEqual(row, s.training_seed(vector["seeds"]["env_master_seed"], slot, row["episode"], union))
                self.assertFalse(s.inside(row["actual_seed"], union))

    def test_15_cohort_exact_no_replacement(self):
        cohort = load("cohort.json")
        self.assertEqual(cohort["seeds"], list(range(0xD3000000, 0xD3000400)))
        self.assertEqual(cohort["planned_episodes"], 7 * 1024)
        self.assertEqual(s.digest(cohort["seeds"]), cohort["seeds_canonical_sha256"])

    def test_16_bounded_future_controls_reproduce_and_preserve_collision(self):
        vectors = load("seed-vectors.json")
        union = s.normalize(list(s.NAMED_RANGES.values()))
        controls = load("future-controls.json")
        self.assertFalse(controls["entire_future_stream_covered"])
        for vector, control in zip(vectors["vectors"], controls["replicas"]):
            rows = [s.training_seed(vector["seeds"]["env_master_seed"], slot, episode, union)
                    for slot, start in enumerate(vectors["parent"]["next_episode_indices"])
                    for episode in range(start, start + 512)]
            self.assertEqual(s.digest(rows), control["rows_canonical_sha256"])
            self.assertEqual(control["new_cohort_hits"], [])
            self.assertTrue(all(not s.inside(r["actual_seed"], union) for r in rows))
        overlap = controls["replicas"][0]["historical_observed_or_envelope_collisions"]
        self.assertEqual(len(overlap), 1)
        self.assertEqual(overlap[0]["actual_seed"], 97593849)
        self.assertFalse(overlap[0]["in_real_observed"])
        self.assertTrue(overlap[0]["in_conservative_envelope"])

    def test_17_partial_coverage_stays_closed(self):
        coverage = load("coverage-map.json")
        self.assertEqual(coverage["claim_status"], "BLOCKED_PARTIAL_HISTORY_NO_FRESHNESS_AUTHORITY")
        self.assertEqual(coverage["real_observed_cohort_collisions"], [])
        self.assertEqual(coverage["conservative_envelope_cohort_collisions"], [])
        self.assertFalse(coverage["proposed_cohort_changed"])
        self.assertGreater(len(coverage["known_coverage_gaps"]), 0)
        self.assertTrue(all(type(x) is int and 0 <= x <= s.U32 for x in load("observed-seeds.json")["real_observed_sorted_unique_seeds"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
