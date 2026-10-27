"""Controls for replayed receipts, preclaim identity, and exact frozen API names."""
import ast
import copy
import importlib
import json
import random
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import attempt_claim as claims
import driver_binding as binding
import test_transition as fixtures
import transition


class RegressionTests(unittest.TestCase):
    def fixture(self):
        value = fixtures.TransitionTests('test_success_saved_lr_noop_preserves_full_and_content_hash')
        value.setUp()
        self.addCleanup(value.doCleanups)
        return value

    def pins(self, value):
        return patch.object(transition, '_sha256_file', side_effect=lambda path: (
            transition.ACCEPTED_PARENT_RECEIPT_SHA256 if str(path).endswith('parent-receipt.json')
            else fixtures.rr.ACCEPTED_CHECKPOINT_SHA256))

    def record(self, value):
        return {'run_id': 'synthetic-run-1', 'study_id': fixtures.STUDY, 'replica': fixtures.REPLICA,
                'arm': 'control_constant_3e-5', 'vector_sha256': value.vector_hash,
                'parent_checkpoint_sha256': fixtures.rr.ACCEPTED_CHECKPOINT_SHA256}

    def test_replayed_mapping_and_duck_callback_rejected_before_restore(self):
        value = self.fixture()
        path = value.path / 'replayed.claim'
        record = self.record(value)
        receipt = claims.AttemptClaim(path, record).claim()
        replay = {'path': str(path), 'record': record, 'receipt': receipt}
        duck = types.SimpleNamespace(path=path, claim=lambda: receipt)
        for supplied in (replay, duck):
            with self.subTest(kind=type(supplied).__name__), self.pins(value), \
                 patch.object(transition, 'EXPECTED_PARENT', value.expected), \
                 patch.object(fixtures, 'AttemptClaim', return_value=supplied):
                with self.assertRaisesRegex(ValueError, 'receipt reuse is forbidden'):
                    value.call()
                self.assertEqual(value.restores, 0)

    def test_wrong_claim_identity_leaves_fixed_path_unspent(self):
        value = self.fixture()
        path = value.path / 'wrong.claim'
        record = {**self.record(value), 'run_id': 'different-run'}
        claim = claims.AttemptClaim(path, record)
        with self.pins(value), patch.object(transition, 'EXPECTED_PARENT', value.expected), \
             patch.object(fixtures, 'AttemptClaim', return_value=claim):
            with self.assertRaisesRegex(ValueError, 'identity mismatch before claim'):
                value.call()
        self.assertFalse(path.exists())
        self.assertEqual(value.restores, 0)

    def test_mutable_failure_blocks_actual_transition_fresh_session_and_reload(self):
        value = self.fixture()
        with self.pins(value), patch.object(transition, 'EXPECTED_PARENT', dict.fromkeys(value.expected, 'wrong')):
            with self.assertRaisesRegex(ValueError, 'trusted restore did not produce'):
                value.call()
        self.assertEqual(value.restores, 1)
        for reload_module in (False, True):
            if reload_module:
                importlib.reload(transition)
            with self.pins(value), patch.object(transition, 'EXPECTED_PARENT', value.expected):
                with self.assertRaises(FileExistsError):
                    value.call(session=transition.TransitionSession())
            self.assertEqual(value.restores, 1)

    def test_claim_receipt_checks_persisted_bytes(self):
        value = self.fixture()
        path = value.path / 'claim'
        record = self.record(value)
        receipt = claims.AttemptClaim(path, record).claim()
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'durable claim file differs'):
            claims.verify_claim_receipt(receipt, path, record)

    def _binding_fixtures(self):
        root = Path(__file__).resolve().parents[5]
        checkpoint_path = root / binding.CHECKPOINTS_RELATIVE
        identity_path = root / binding.IDENTITY_RELATIVE
        runner_path = root / binding.RUNNER_RELATIVE

        def namespace(path, names):
            parsed = ast.parse(path.read_text())
            nodes = [ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)]
            nodes += [node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name in names]
            self.assertEqual({node.name for node in nodes if isinstance(node, ast.FunctionDef)}, set(names))
            module = types.ModuleType('pinned_ast_fixture')
            module.__file__ = str(path)
            exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), 'exec'), module.__dict__)
            return module

        checkpoint = namespace(checkpoint_path, binding.CHECKPOINT_FUNCTIONS)
        checkpoint.require = namespace(identity_path, ('require',)).require
        checkpoint.copy = copy
        checkpoint.random = random
        checkpoint.np = sys.modules['numpy']
        checkpoint.torch = sys.modules['torch']
        runner = namespace(runner_path, ('worker',))
        return root, checkpoint, runner

    def test_binding_accepts_exact_ast_bodies_and_real_worker_symbol(self):
        root, checkpoint, runner = self._binding_fixtures()
        callbacks = binding.build_callbacks(project_root=root, checkpoint_module=checkpoint,
                                            runner_namespace=runner.__dict__, parent_state={}, model=None,
                                            optimizer=None, capture_module_hash='caller-claim-is-ignored')
        self.assertEqual(callbacks['api_names'], {'restore': 'restore_learner', 'capture': 'capture_rng'})
        self.assertTrue(callable(callbacks['restore_trusted']))
        self.assertTrue(callable(callbacks['rng_capture']))
        # Only function definitions were compiled. Neither callback or runtime module was executed.

    def test_substituted_same_filename_api_helper_and_worker_rejected(self):
        for name in ('capture_rng', 'restore_learner', 'restore_rng',
                     'require_complete_update', 'worker'):
            root, checkpoint, runner = self._binding_fixtures()
            namespace = runner.__dict__ if name == 'worker' else checkpoint.__dict__
            with self.subTest(name=name):
                # Same filename, module globals, and API shape; body differs.
                malicious_code = compile(f'def {name}(*args, **kwargs):\n    raise RuntimeError("substituted")\n',
                                         namespace['__file__'], 'exec')
                replacement = next(item for item in malicious_code.co_consts
                                   if isinstance(item, type((lambda: None).__code__)))
                namespace[name] = types.FunctionType(replacement, namespace, name)
                with self.assertRaisesRegex(ValueError, 'trusted function code mismatch'):
                    binding.build_callbacks(project_root=root, checkpoint_module=checkpoint,
                                            runner_namespace=runner.__dict__, parent_state={}, model=None,
                                            optimizer=None, capture_module_hash=binding.CHECKPOINTS_SHA256)

    def test_mutated_raw_defaults_rejected(self):
        root, checkpoint, runner = self._binding_fixtures()
        checkpoint.capture_rng.__defaults__ = ('mps', None)
        with self.assertRaisesRegex(ValueError, 'capture_rng defaults mismatch'):
            binding.build_callbacks(project_root=root, checkpoint_module=checkpoint,
                                    runner_namespace=runner.__dict__, parent_state={}, model=None,
                                    optimizer=None)

    def test_require_and_runtime_module_dependencies_are_bound(self):
        for dependency in ('require', 'torch', 'np', 'random', 'copy'):
            root, checkpoint, runner = self._binding_fixtures()
            setattr(checkpoint, dependency, object())
            error = 'identity require dependency mismatch' if dependency == 'require' else 'driver module dependency mismatch'
            with self.subTest(dependency=dependency), self.assertRaisesRegex(ValueError, error):
                binding.build_callbacks(project_root=root, checkpoint_module=checkpoint,
                                        runner_namespace=runner.__dict__, parent_state={}, model=None,
                                        optimizer=None)

    def test_private_require_ignores_substituted_caller_builtins_and_helpers(self):
        root, checkpoint, runner = self._binding_fixtures()
        original_require = checkpoint.require
        malicious_builtins = dict(vars(__import__('builtins')))
        malicious_builtins['ValueError'] = RuntimeError
        checkpoint.require = types.FunctionType(original_require.__code__,
            {'__builtins__': malicious_builtins, '__name__': 'malicious'}, 'require')
        callbacks = binding.build_callbacks(project_root=root, checkpoint_module=checkpoint,
            runner_namespace=runner.__dict__, parent_state={'tag': 'interrupted_mid_update'},
            model=None, optimizer=None)
        # Caller substitutions after build must not alter callback dependencies.
        for name in binding.CHECKPOINT_FUNCTIONS:
            setattr(checkpoint, name, lambda *a, **k: None)
        checkpoint.require = lambda *a, **k: None
        with self.assertRaisesRegex(ValueError, 'Interrupted/incomplete update checkpoint'):
            callbacks['restore_trusted']()

    def test_exact_hostile_require_code_cannot_change_canonical_exception(self):
        root, checkpoint, runner = self._binding_fixtures()
        original = checkpoint.require
        fake_builtins = dict(vars(__import__('builtins')))
        fake_builtins['ValueError'] = RuntimeError
        checkpoint.require = types.FunctionType(original.__code__,
            {'__builtins__': fake_builtins, '__name__': 'hostile'}, 'require')
        callbacks = binding.build_callbacks(project_root=root, checkpoint_module=checkpoint,
            runner_namespace=runner.__dict__, parent_state={'tag': 'interrupted_mid_update'},
            model=None, optimizer=None)
        with self.assertRaisesRegex(ValueError, 'Interrupted/incomplete update checkpoint'):
            callbacks['restore_trusted']()


if __name__ == '__main__':
    unittest.main()
