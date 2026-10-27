"""Authored only, NOT RUN here. Parent must authorize extension construction.

These input tests do not establish successful cutoff or accepted-runtime parity.
Use the native class directly; the Python collector/adapter is a separate lane.
"""
import os
import unittest


class PendingBindingInputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("PROGRESSIVE1000_PARENT_BINDING_TESTS") != "1":
            raise unittest.SkipTest("Parent integration gate: extension import and construction not authorized in preparation lane")
        import numpy
        from dodge_rl import _native
        cls.np = numpy
        cls.native = _native

    def setUp(self):
        self.env = self.native.VecDodgeEnv(batch_size=2, seeds_by_slot=[[31, 131], [32, 132]])

    def assert_unchanged(self, indices, horizons):
        info = self.env.episode_info()
        observation = self.env.observations()
        with self.assertRaises((TypeError, ValueError, OverflowError)):
            self.env.truncate_practice(indices, horizons)
        self.assertEqual(self.env.episode_info(), info)
        after = self.env.observations()
        self.assertEqual(after.keys(), observation.keys())
        for name, before in observation.items():
            if isinstance(before, self.np.ndarray):
                self.np.testing.assert_array_equal(before, after[name])
            else:
                self.assertEqual(before, after[name])
        self.assertFalse(self.env.is_poisoned())

    def test_strict_integer_inputs_for_both_arguments(self):
        np = self.np
        invalid = [True, 0.0, "0", [False], [1.0], ["1"], [2**100],
                   np.array([True]), np.array([1.0]), np.array([1], dtype=np.int32),
                   np.array([2**64 - 1], dtype=np.uint64),
                   np.array([[1]], dtype=np.int64)]
        for value in invalid:
            with self.subTest(value=repr(value), argument="indices"):
                self.assert_unchanged(value, [1000])
            with self.subTest(value=repr(value), argument="horizons"):
                self.assert_unchanged([0], value)

    def test_checked_negative_overflow_shape_and_native_validation(self):
        for indices, horizons in [([-1], [1000]), ([0], [-1000]), ([0], [2**32]),
                                  ([0, 1], [1000]), ([0], [1000, 1000]),
                                  ([0, 0], [1000, 1000]), ([2], [1000]),
                                  ([0], [0]), ([0], [1001]), ([0], [18000]),
                                  ([0], [1000])]:  # At frame zero: wrong-frame rejection.
            with self.subTest(indices=indices, horizons=horizons):
                self.assert_unchanged(indices, horizons)

    def test_empty_sequences_return_owned_list(self):
        self.assertEqual(self.env.truncate_practice([], []), [])
        self.assertEqual(self.env.truncate_practice((), ()), [])
        self.assertEqual(self.env.truncate_practice(self.np.array([], dtype=self.np.int64),
                                                  self.np.array([], dtype=self.np.int64)), [])
