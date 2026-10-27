from copy import deepcopy
import unittest

from dodge_learning.seeds import manifest_hash, seed_manifest, validate_manifest


class SeedManifestTests(unittest.TestCase):
    def test_splits_are_fixed_disjoint_and_copies_are_independent(self):
        manifest = seed_manifest()
        self.assertEqual([len(manifest[name]) for name in ("train", "smoke", "validation", "test")], [100, 10, 100, 100])
        self.assertEqual(manifest_hash(manifest), manifest_hash(deepcopy(manifest)))
        manifest["train"][0] = 999
        self.assertEqual(seed_manifest()["train"][0], 1000)

    def test_cross_split_and_within_split_rng_aliases_are_rejected(self):
        manifest = seed_manifest()
        manifest["train"][0] = 0
        manifest["smoke"][0] = 1
        with self.assertRaises(ValueError):
            validate_manifest(manifest)
        manifest = seed_manifest()
        manifest["train"] = [0, 1]
        with self.assertRaises(ValueError):
            validate_manifest(manifest)
