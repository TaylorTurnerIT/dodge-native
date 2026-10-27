"""Controls for result provenance and bootstrap stream continuity."""
import json
import unittest

import numpy as np

import adapter
from test_adapter import enc, fixture, make_result, H


def replace_result(arguments, key, value):
    arguments[key + '_bytes'] = enc(value)
    arguments[key + '_sha256'] = adapter.sha(arguments[key + '_bytes'])
    audit = json.loads(arguments['audit_bytes'])
    index = 0 if key == 'winner' else 1
    audit['output_artifacts'][index]['sha256'] = arguments[key + '_sha256']
    arguments['audit_bytes'] = enc(audit)
    arguments['audit_sha256'] = adapter.sha(arguments['audit_bytes'])


class RegistrationBindingTests(unittest.TestCase):
    def test_repinned_foreign_or_missing_result_registration_rejected(self):
        for key in ('winner', 'incumbent'):
            for remove in (False, True):
                with self.subTest(result=key, missing=remove):
                    arguments = fixture()
                    result = json.loads(arguments[key + '_bytes'])
                    if remove:
                        result.pop('registration_sha256')
                    else:
                        result['registration_sha256'] = '0' * 64
                    replace_result(arguments, key, result)
                    with self.assertRaisesRegex(adapter.ContractError, 'registration_sha256 mismatch'):
                        adapter.analyze(**arguments)

    def test_bootstrap_stream_matches_different_chunk_boundaries(self):
        arguments = fixture()
        incumbent = np.arange(adapter.N, dtype=np.int64) % 173 + 100
        difference = np.arange(adapter.N, dtype=np.int64) % 47 - 20
        cohort = json.loads(arguments['registration_bytes'])['cohorts']['confirmation']['manifest_sha256']
        winner = make_result(324, H('a'), cohort, 'cpu', (incumbent + difference).tolist(),
                             arguments['registration_sha256'])
        baseline = make_result(348, adapter.INCUMBENT, cohort, 'cpu', incumbent.tolist(),
                               arguments['registration_sha256'])
        replace_result(arguments, 'winner', winner)
        replace_result(arguments, 'incumbent', baseline)
        actual = adapter.analyze(**arguments)
        generator = np.random.Generator(np.random.PCG64(4200261026))
        reference = []
        for start in range(0, 20000, 257):
            count = min(257, 20000 - start)
            indices = generator.integers(0, 2048, size=(count, 2048), dtype=np.int64)
            reference.extend(difference[indices].mean(axis=1))
        expected = float(np.quantile(reference, .05, method='linear'))
        self.assertEqual(actual['paired_bootstrap_lower_bound_5pct'], expected)
        self.assertEqual(actual['finite_cohort_mean_difference_winner_minus_348'], float(difference.mean()))


if __name__ == '__main__':
    unittest.main()
