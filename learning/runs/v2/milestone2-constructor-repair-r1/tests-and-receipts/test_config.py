"""Pure JSON-to-PyO3 range adapter regressions; no native imports."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
SOURCE = Path(os.environ['SUPERVISOR_UNDER_TEST']).resolve()
SPEC = importlib.util.spec_from_file_location('selected_constructor_supervisor', SOURCE)
H = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(H)


class ConstructorConfigTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((ROOT / 'learning/runs/v2/milestone2-validation-harness-r1/campaign-plan.json').read_text())

    def test_json_ranges_are_tuple_pairs_with_exact_reserved_values(self):
        self.assertTrue(all(type(pair) is list for pair in self.plan['effective_reserved_ranges']))
        ranges = H.base_config(self.plan)['excluded_seed_ranges']
        self.assertEqual(ranges, [(2952790016, 2952791015), (3489660928, 3489661055), (3758096384, 3758097383)])
        self.assertTrue(all(type(pair) is tuple for pair in ranges))

    def test_base_config_preserves_plan_and_other_defaults(self):
        original = copy.deepcopy(self.plan)
        value = H.base_config(self.plan)
        self.assertEqual(self.plan, original)
        self.assertEqual(value['run_seed'], self.plan['training_run_seed'])
        self.assertEqual((value['batch_size'], value['action_repeat'], value['difficulty'], value['raw_frame_cap']), (8, 4, 2, 18000))
        self.assertTrue(value['patterns_enabled'] and value['powerups_enabled'])

    def test_explicit_overrides_still_take_precedence(self):
        override = [(12, 23)]
        value = H.base_config(self.plan, batch_size=9, raw_frame_cap=17, excluded_seed_ranges=override)
        self.assertEqual(value['batch_size'], 9)
        self.assertEqual(value['raw_frame_cap'], 17)
        self.assertIs(value['excluded_seed_ranges'], override)


if __name__ == '__main__':
    unittest.main(verbosity=2)
