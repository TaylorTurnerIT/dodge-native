"""Pure final-iteration wall-guard regressions; no real array/native dependencies."""
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
SOURCE = Path(os.environ['SUPERVISOR_UNDER_TEST']).resolve()
SPEC = importlib.util.spec_from_file_location('selected_throughput_supervisor', SOURCE)
H = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(H)
PLAN = json.loads((ROOT / 'learning/runs/v2/milestone2-validation-harness-r1/campaign-plan.json').read_text())
CASES = Path(os.environ['THROUGHPUT_CASES']).resolve()
CASES.mkdir(exist_ok=False)


class Vector:
    def __init__(self, values):
        self.values = list(values)
    def sum(self):
        return sum(self.values)
    def tobytes(self):
        return b''.join(struct.pack('<q', int(v)) for v in self.values)
    def __or__(self, other):
        return Vector(a or b for a, b in zip(self.values, other.values))
    def tolist(self):
        return list(self.values)


class Matrix:
    def __init__(self, shape):
        self.shape = shape
    def __iter__(self):
        for _ in range(self.shape[0]):
            yield Vector([0] * self.shape[1])
    def astype(self, *args, **kwargs):
        return self
    def tobytes(self):
        return struct.pack('<QQ', *self.shape)


class Generator:
    def integers(self, _low, _high, size, dtype):
        return Matrix(size)


NP = SimpleNamespace(int64='synthetic-int64',
    random=SimpleNamespace(PCG64=lambda seed: seed, Generator=lambda seed: Generator()),
    flatnonzero=lambda vector: Vector(index for index, value in enumerate(vector.values) if value))


class ThroughputGuardTests(unittest.TestCase):
    def setUp(self):
        self.output = CASES / self.id().split('.')[-1]
        self.output.mkdir(exist_ok=False)
        self.clock = SimpleNamespace(mono=0.0)
        self.endpoint = 59.9
        self.late_reset = False
        self.early_overrun = False
        self.instances = []
        owner = self
        stage = next(stage for stage in PLAN['stages'] if stage['name'] == 'throughput')
        self.warmup = stage['warmup_step_calls']
        self.measured = stage['measured_step_calls']

        class Env:
            def __init__(self, **config):
                self.config = config
                self.calls = 0
                self.reset_calls = 0
                self.observation_calls = 0
                self.batch_info_calls = 0
                owner.clock.mono = 0.0
                owner.instances.append(self)
            def episode_info(self):
                return [{'seed': {'slot': slot, 'episode': 0, 'counter': 0, 'actual_seed': slot + 1}}
                    for slot in range(self.config['batch_size'])]
            def step(self, _vector):
                self.calls += 1
                call = self.calls - owner.warmup
                if owner.early_overrun and call == 1000:
                    owner.clock.mono = 60.1
                elif call == owner.measured - 1:
                    owner.clock.mono = 59.9
                elif call == owner.measured:
                    owner.clock.mono = 59.9 if owner.late_reset else owner.endpoint
                batch = self.config['batch_size']
                ended = owner.late_reset and call == owner.measured
                return {'elapsed_raw_frames': Vector([4] * batch),
                    'score_delta_raw_fixed': Vector([0] * batch),
                    'terminated': Vector([ended] + [False] * (batch - 1)),
                    'truncated': Vector([False] * batch)}
            def reset_done(self, indices):
                self.reset_calls += 1
                owner.clock.mono = owner.endpoint
                return {'info': [{'seed': {'slot': i, 'episode': 1, 'counter': 0, 'actual_seed': 100 + i}} for i in indices]}
            def observations(self):
                self.observation_calls += 1
                return {'synthetic': True}
            def batch_info(self):
                self.batch_info_calls += 1
                return {'synthetic': True}

        self.Env = Env
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(H.time, 'monotonic', side_effect=lambda: self.clock.mono))
        self.stack.enter_context(patch.object(H, 'validate_observation'))
        self.stack.enter_context(patch.object(H, 'array_digest', return_value='synthetic-stable-neural-hash'))

    def invoke(self):
        return H.worker_throughput(NP, self.Env, PLAN, self.output)

    def assert_rejected_before_measurement_acceptance(self):
        with self.assertRaisesRegex(ValueError, 'Throughput config wall guard exceeded'):
            self.invoke()
        self.assertEqual(len(self.instances), 1, 'must not start next configuration after overrun')
        self.assertEqual(self.instances[0].observation_calls, 0, 'must reject before accepting final observations')
        self.assertEqual(self.instances[0].batch_info_calls, 0, 'must not append accepted measurement')
        self.assertEqual(list(self.output.iterdir()), [], 'must reject before completed measurement seed log')

    def test_completed_last_step_over_60_seconds_rejected(self):
        self.endpoint = 60.1
        self.assert_rejected_before_measurement_acceptance()
        self.assertEqual(self.instances[0].calls, self.warmup + self.measured)

    def test_completed_last_reset_over_60_seconds_rejected(self):
        self.endpoint = 60.1
        self.late_reset = True
        self.assert_rejected_before_measurement_acceptance()
        self.assertEqual(self.instances[0].calls, self.warmup + self.measured)
        self.assertEqual(self.instances[0].reset_calls, 1)

    def test_completed_under_60_seconds_keeps_full_paired_workload(self):
        self.endpoint = 59.9
        result = self.invoke()
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(len(result['measurements']), 4)
        self.assertEqual(len(self.instances), 4)
        for measurement in result['measurements']:
            self.assertEqual(measurement['wall_seconds'], 59.9)
            self.assertEqual(measurement['measured_step_calls'], 2000)
            self.assertEqual(measurement['warmup_step_calls'], 200)
            self.assertEqual(measurement['environment_decisions'], 64000)
            self.assertEqual(measurement['raw_gameplay_frames'], 256000)
        self.assertTrue(all(env.calls == self.warmup + self.measured for env in self.instances))

    def test_exactly_60_seconds_preserves_inclusive_boundary(self):
        self.endpoint = 60.0
        result = self.invoke()
        self.assertEqual(result['status'], 'passed')
        self.assertEqual([row['wall_seconds'] for row in result['measurements']], [60.0] * 4)

    def test_existing_pre_iteration_guard_stops_earlier_overrun(self):
        self.early_overrun = True
        self.assert_rejected_before_measurement_acceptance()
        self.assertEqual(self.instances[0].calls, self.warmup + 1000)


if __name__ == '__main__':
    print(json.dumps({'selected_executed_source': str(SOURCE),
        'selected_executed_source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'native_execution': False, 'numpy_import': False}, sort_keys=True), flush=True)
    unittest.main(verbosity=2)
