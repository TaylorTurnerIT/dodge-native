"""Exact copied source controls plus strict actual native API-shape checks."""
from pathlib import Path
import copy
import json
import sys
import unittest

OUT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(OUT), str(OUT / 'tests'), str(OUT / 'successor')]
from common import digest, write

kind = sys.argv[1]
if kind == 'binding':
    import binding_controls as controls
    class ActualAPI(unittest.TestCase):
        def test_no_python_only_constructor_flag(self):
            with self.assertRaises(TypeError):
                controls.native.VecDodgeEnv(practice_cutoff=True)
            with self.assertRaises(TypeError):
                controls.native.VecDodgeEnv(evaluation=False)

        def test_no_python_only_cutoff_flag_or_writable_boundary(self):
            env = controls.synthetic_env()
            before = digest(dict(info=env.episode_info(), observations=env.observations()))
            with self.assertRaises(TypeError):
                env.truncate_practice([0], [1000], truncated=True)
            with self.assertRaises(AttributeError):
                env.truncated = True
            self.assertEqual(before, digest(dict(info=env.episode_info(), observations=env.observations())))
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(controls.BindingTests),
                               unittest.defaultTestLoader.loadTestsFromTestCase(ActualAPI)])
else:
    assert kind == 'fake'
    import torch
    torch.set_num_threads(1)
    suite = unittest.defaultTestLoader.discover(str(OUT / 'tests'))
result = unittest.TextTestRunner(verbosity=2, failfast=True).run(suite)
report = {'kind': kind, 'tests_run': result.testsRun, 'success': result.wasSuccessful(),
          'failures': [(str(t), detail) for t, detail in result.failures],
          'errors': [(str(t), detail) for t, detail in result.errors]}
if kind == 'fake':
    from test_collector import EVIDENCE
    report['fake_controls'] = EVIDENCE
    assert not any(n == '_native' or n == 'dodge_rl' or n.startswith('dodge_rl.') for n in sys.modules)
else:
    report['binary_path'] = str(controls.BINARY)
    report['binary_sha256'] = controls.MANIFEST['sha256']
write('results/' + kind + '-controls-repaired.json', report)
raise SystemExit(not result.wasSuccessful())
