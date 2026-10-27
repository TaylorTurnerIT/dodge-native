"""Discriminating finalization tests; same fixtures run exact frozen r1 or r2.

Only the real supervisor orchestration executes. Worker, clock, guard and owned
cleanup are bounded synthetic fixtures; no native/model/MPS imports occur.
"""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
TARGET = Path(os.environ.get('FINALIZATION_RUNNER', str(HERE / 'runner.py'))).resolve()
spec = importlib.util.spec_from_file_location('finalization_target', TARGET)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

COUNTS = {'inference_calls': 113, 'native_step_calls': 991, 'environments_created': 768,
          'decisions_logged': 303, 'episodes_completed': 768, 'evaluations_completed': 12,
          'control_matches': {'entry': {'matched': True}, 'phase96': {'matched': True}}}


class FinalizationTests(unittest.TestCase):
    def fixture(self, *, delay_stage=None, delay=1, worker_end=599.8,
                cleanup=0, stop_update=None, worker_status='complete', save_error=False):
        clock = [0.0]
        with tempfile.TemporaryDirectory(dir=HERE) as td:
            base = Path(td)
            root, original = base / 'capsule', base / 'original'
            root.mkdir(); original.mkdir()
            dummy = root / 'dummy.py'
            dummy.write_text('# synthetic worker identity only\n')
            digest = r.sha(dummy)
            (root / 'capsule-manifest.json').write_text(json.dumps({'files': {'dummy.py': digest}}))
            p = {'run_id': 'fixture_only', 'output': 'fixture_campaign', 'runner': 'dummy.py'}
            state = base / 'fixture-state.json'
            state.write_text(json.dumps({'active_long_campaign': {
                'kind': 'M3_action_mode_diagnostic', 'authorization': 'new_postovernight_inference_only',
                'run_id': 'fixture_only', 'protocol_sha256': r.PROTOCOL_SHA256,
                'harness_sha256': digest,
                'frozen_capsule_manifest_sha256': r.sha(root / 'capsule-manifest.json'),
                'frozen_capsule_path': str(root)}}))
            output = original / p['output']
            args = argparse.Namespace(protocol=base / 'fixture-protocol.json', output=output, state_path=state)
            def advance(stage):
                if delay_stage == stage:
                    clock[0] += delay
            class Guard:
                failure = None
                def __init__(self, deadline, verify, stream):
                    self.deadline = deadline
                def start(self): pass
                def check(self):
                    r.require(clock[0] < self.deadline, '600-second diagnostic deadline reached (fixture)')
                def sample(self): self.check()
                def close(self): advance('guard_close')
                def receipt(self): return {'latched_failure': None}
            class Process:
                pid = 987654321
                returncode = 0 if worker_status == 'complete' else 1
                def poll(self): return self.returncode
            def spawn(*a, **kw):
                wr = dict(r.baseline_result(), **COUNTS, status=worker_status)
                if worker_status != 'complete':
                    wr.update(episodes_completed=17, evaluations_completed=0, inference_calls=8)
                (output / 'worker-result.json').write_text(json.dumps(wr))
                (output / 'decisions.jsonl').write_text('{"fixture":true}\n')
                clock[0] = worker_end
                return Process()
            def stop(process):
                clock[0] += cleanup
                return dict({'reaped': True, 'group_empty': True, 'errors': []}, **(stop_update or {}))
            calls = [0]
            real_verify, real_sha, real_save = r.verify_files, r.sha, r.save
            def verify(pins):
                calls[0] += 1
                real_verify(pins)
                if calls[0] == 2: advance('final_verification')
            def sha(path):
                value = real_sha(path)
                if Path(path).parent == output and Path(path).name == 'decisions.jsonl':
                    advance('output_hash')
                if Path(path).name == 'artifact-manifest.json': advance('manifest_hash')
                return value
            saved = []
            def save(path, value):
                name = Path(path).name.lstrip('.').removesuffix('.pending')
                saved.append(name)
                real_save(path, value)
                stage = {'run-result.json': 'serialization', 'artifact-manifest.json': 'manifest_publication',
                         'finalization-result.json': 'terminal_publication'}.get(name)
                if saved.count(name) == 1:
                    advance(stage)
                    if (save_error is True and name == 'artifact-manifest.json') or save_error == name:
                        raise OSError('fixture late manifest publication failure')
            with ExitStack() as stack:
                patches = {'ROOT': root, 'ORIGINAL_ROOT': original, '__file__': str(dummy),
                    'LAUNCH_MONOTONIC': 0.0, 'registered_protocol': lambda path: p,
                    'assert_readonly_capsule': lambda manifest: None,
                    'input_pins': lambda *a: ({str(dummy): digest}, {}),
                    'DiagnosticGuard': Guard, 'stop_owned': stop, 'verify_files': verify,
                    'sha': sha, 'save': save,
                    'time': SimpleNamespace(monotonic=lambda: clock[0], sleep=lambda seconds: None)}
                for name, value in patches.items(): stack.enter_context(patch.object(r, name, value))
                stack.enter_context(patch.object(r.subprocess, 'Popen', side_effect=spawn))
                code = r.supervise(args)
            result = json.loads((output / 'run-result.json').read_text())
            stable = output / 'artifact-manifest.json'
            manifest = json.loads(stable.read_text()) if stable.exists() else None
            if manifest is not None:
                self.assertEqual(manifest['run-result.json'], real_sha(output / 'run-result.json'))
                for name, digest in manifest.items(): self.assertEqual(real_sha(output / name), digest)
            terminal = output / 'finalization-result.json'
            terminal = json.loads(terminal.read_text()) if terminal.exists() else None
            if terminal and manifest is not None:
                self.assertEqual(terminal['artifact_manifest_sha256'], real_sha(stable))
                self.assertEqual(terminal['status'], result['status'])
            return code, result, manifest, terminal, clock[0], (output / 'artifact-manifest-unavailable.json').exists()

    def assert_late_failed(self, stage):
        code, result, manifest, terminal, wall, unavailable = self.fixture(delay_stage=stage)
        self.assertEqual(code, 1, f'{stage}: late finalization must fail, observed wall={wall}')
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(result['partial'])
        self.assertGreaterEqual(result['actual_total_wall_seconds'], 600)
        self.assertTrue(result['deadline_expired'])
        self.assertIsNone(manifest, 'Late failure must revoke the stale stable manifest')
        self.assertTrue(unavailable)
        self.assertEqual(terminal['status'], 'failed')
        self.assertEqual(result['episodes_completed'], 768)

    def test_late_guard_close_fails(self): self.assert_late_failed('guard_close')
    def test_late_final_verification_fails(self): self.assert_late_failed('final_verification')
    def test_late_output_hash_fails(self): self.assert_late_failed('output_hash')
    def test_late_serialization_fails(self): self.assert_late_failed('serialization')
    def test_late_manifest_publication_fails(self): self.assert_late_failed('manifest_publication')
    def test_late_manifest_hash_fails(self): self.assert_late_failed('manifest_hash')
    def test_late_terminal_publication_fails(self): self.assert_late_failed('terminal_publication')

    def test_reaped_nonempty_group_suppresses_manifest(self):
        self.assert_unproven({'group_empty': False})

    def test_reaped_missing_group_proof_suppresses_manifest(self):
        self.assert_unproven({'group_empty': None})

    def test_unreaped_leader_suppresses_manifest(self):
        self.assert_unproven({'reaped': False})

    def test_reaped_group_probe_errors_suppress_manifest(self):
        self.assert_unproven({'errors': ['fixture group probe error']})

    def test_reaped_group_probe_error_suppresses_manifest(self):
        self.assert_unproven({'error': 'fixture group probe error'})

    def assert_unproven(self, update):
        code, result, manifest, terminal, wall, unavailable = self.fixture(stop_update=update, worker_end=10)
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'failed')
        self.assertIsNone(manifest, 'Reaped leader cannot prove its descendants stopped writing')
        self.assertTrue(unavailable)
        self.assertEqual(terminal['status'], 'failed')

    def test_bounded_success_has_consistent_manifest_and_worker_counts(self):
        code, result, manifest, terminal, wall, unavailable = self.fixture(
            worker_end=598, cleanup=.1, delay_stage='output_hash', delay=.2)
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'complete')
        self.assertFalse(result['partial'])
        self.assertIsNotNone(manifest)
        self.assertFalse(unavailable)
        self.assertLess(terminal['actual_total_wall_seconds'], 600)
        self.assertGreaterEqual(terminal['actual_total_wall_seconds'], 598.3)
        self.assertEqual(terminal['status'], 'complete')
        self.assertTrue(result['completion_requires_terminal_receipt'])
        for name, value in COUNTS.items(): self.assertEqual(result[name], value)

    def test_partial_worker_counts_preserved(self):
        code, result, manifest, terminal, wall, unavailable = self.fixture(worker_status='failed', worker_end=10)
        self.assertEqual(code, 1)
        self.assertEqual(result['episodes_completed'], 17)
        self.assertEqual(result['inference_calls'], 8)
        self.assertEqual(result['evaluations_completed'], 0)
        self.assertEqual(terminal['status'], 'failed')

    def test_cleanup_reserve_cannot_buy_normal_finalization(self):
        code, result, manifest, terminal, wall, unavailable = self.fixture(worker_end=599, cleanup=9)
        self.assertEqual(code, 1)
        self.assertEqual(result['cleanup_seconds'], 9)
        self.assertEqual(result['actual_execution_wall_seconds'], 599)
        self.assertGreaterEqual(result['actual_total_wall_seconds'], 608)
        self.assertTrue(result['deadline_expired'])
        self.assertIsNone(manifest)

    def test_cleanup_over_10_seconds_fails_even_before_deadline(self):
        code, result, manifest, terminal, wall, unavailable = self.fixture(worker_end=10, cleanup=10.1)
        self.assertEqual(code, 1)
        self.assertTrue(result['cleanup_reserve_exceeded'])

    def test_worker_crossing_deadline_cannot_use_cleanup_reserve(self):
        code, result, manifest, terminal, wall, unavailable = self.fixture(worker_end=600.1, cleanup=1)
        self.assertEqual(code, 1)
        self.assertTrue(result['deadline_expired'])
        self.assertEqual(result['actual_execution_wall_seconds'], 600.1)

    def test_late_run_result_exception_retains_failed_terminal(self):
        code, result, manifest, terminal, wall, unavailable = self.fixture(
            worker_end=10, save_error='run-result.json')
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'failed')
        self.assertIsNone(manifest)
        self.assertEqual(terminal['status'], 'failed')

    def test_late_terminal_exception_revokes_manifest(self):
        code, result, manifest, terminal, wall, unavailable = self.fixture(
            worker_end=10, save_error='finalization-result.json')
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'failed')
        self.assertIsNone(manifest)
        self.assertEqual(terminal['status'], 'failed')

    def test_late_publication_exception_revokes_success(self):
        code, result, manifest, terminal, wall, unavailable = self.fixture(worker_end=10, save_error=True)
        self.assertEqual(code, 1)
        self.assertIsNone(manifest)
        self.assertTrue(unavailable)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(terminal['status'], 'failed')


if __name__ == '__main__':
    print(json.dumps({'target': str(TARGET), 'sha256': hashlib.sha256(TARGET.read_bytes()).hexdigest()}), flush=True)
    unittest.main(verbosity=2)
