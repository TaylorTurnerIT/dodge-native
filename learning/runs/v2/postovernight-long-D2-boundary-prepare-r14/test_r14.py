"""Actual CPython scheduling, first-callback-failure chronology and exact r14 deltas.

Signals are modeled by calling the unchanged ProcessLatch.handle directly.
No OS signal delivery, timer installation, lifecycle/stress or ML run occurs.
Reader threads use real stdlib threading and real interval operations.
"""
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
import ast
import hashlib
import json
import math
import os
import signal
import sys
import tempfile
import threading
import time
import unittest
import lifecycle as life
import long_d2 as c
import long_d2_executor as e
import current_delta as delta
import importlib.util
from types import SimpleNamespace

H = Path(__file__).resolve().parent
BASE = H / 'r11-source'
R12 = H / 'r12-source'
A = Path(os.environ['VALIDATION_DIR'])
SCHEDULING_HELPERS = set(delta.SCHEDULING_HELPERS)


class OtherBaseException(BaseException):
    pass


class R14(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix=self._testMethodName + '-', dir=A))
        self.original = sys.getswitchinterval()
        self.addCleanup(self.restore_test_interval)

    def restore_test_interval(self):
        # Independent fixture cleanup: midpoint of the observed microsecond bin.
        # Test intervals are small positive integer microseconds, never huge floats.
        ticks = round(self.original / 1e-6)
        sys.setswitchinterval((ticks + .5) / 1e6)
        self.assertEqual(sys.getswitchinterval(), self.original)

    def save(self, name, value):
        with (self.d / (name + '.json')).open('x') as stream:
            json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write('\n')

    def guard(self, callback):
        return c.Guard(time.monotonic() + 10, lambda: None, callback, None,
                       rss=lambda: 1, peak=lambda: 1)

    def test_01_success_scoped_and_outside_unchanged(self):
        sys.setswitchinterval(.005)
        before = sys.getswitchinterval()
        with c.boundary_switch_interval():
            inside = sys.getswitchinterval()
            self.assertGreater(inside, 0)
            self.assertLessEqual(inside, c.BOUNDARY_SWITCH_INTERVAL)
        self.assertEqual(sys.getswitchinterval(), before)
        self.save('success', dict(before=before, inside=inside, after=sys.getswitchinterval()))

    def test_02_Stop_preserves_same_exception_and_interval(self):
        error = c.Stop('callback cancellation', 'cancelled')
        with self.assertRaises(c.Stop) as raised:
            with c.boundary_switch_interval():
                raise error
        self.assertIs(raised.exception, error)
        self.assertEqual(sys.getswitchinterval(), self.original)

    def test_03_other_BaseException_KeyboardInterrupt_GeneratorExit(self):
        for error in (OtherBaseException('base'), KeyboardInterrupt('keyboard'), GeneratorExit('generator')):
            with self.subTest(kind=type(error).__name__):
                with self.assertRaises(type(error)) as raised:
                    with c.boundary_switch_interval():
                        raise error
                self.assertIs(raised.exception, error)
                self.assertEqual(sys.getswitchinterval(), self.original)

    def test_04_setter_raises_after_install_restores_without_callback(self):
        real = sys.setswitchinterval
        error = OtherBaseException('injected after install')
        entered = []
        def setting(value):
            real(value)
            if value == c.BOUNDARY_SWITCH_INTERVAL:
                raise error
        with patch.object(sys, 'setswitchinterval', setting):
            with self.assertRaises(OtherBaseException) as raised:
                with c.boundary_switch_interval():
                    entered.append(True)
        self.assertIs(raised.exception, error)
        self.assertEqual(entered, [])
        self.assertEqual(sys.getswitchinterval(), self.original)

    def cleanup_interruption(self, *, after_set=False, callback_error=None):
        real = sys.setswitchinterval
        sys.setswitchinterval(.005)
        original = sys.getswitchinterval()
        latch = life.ProcessLatch()
        latch.deadline = time.monotonic() + 10
        first = [True]
        calls = []
        def setting(value):
            calls.append(value)
            if value == original and first[0]:
                first[0] = False
                if after_set:
                    real(value)
                # Model precisely the existing signal handler's raised Stop.
                latch.handle(signal.SIGTERM, None)
            real(value)
        with patch.object(sys, 'setswitchinterval', setting):
            with self.assertRaisesRegex(c.Stop, 'Cancellation latched') as raised:
                with c.boundary_switch_interval():
                    if callback_error is not None:
                        raise callback_error
        self.assertEqual(raised.exception.outcome, 'cancelled')
        self.assertEqual(sys.getswitchinterval(), original)
        self.assertEqual(latch.cancellation_requests, 1)
        self.assertEqual(latch.phase, 'FAILURE')
        self.assertEqual(calls.count(original), 1 if after_set else 2)
        if callback_error is not None:
            self.assertIs(raised.exception.__context__, callback_error)
        self.save('modeled-signal', dict(actual_OS_signal=False, after_set=after_set,
            calls=calls, restored=original, cancellation_requests=latch.cancellation_requests))

    def test_05_one_modeled_signal_before_first_cleanup_set_outer_recovers(self):
        self.cleanup_interruption()

    def test_06_one_modeled_signal_after_first_cleanup_set_propagates(self):
        self.cleanup_interruption(after_set=True)

    def test_07_callback_error_and_one_cleanup_signal_both_retained(self):
        self.cleanup_interruption(callback_error=OtherBaseException('callback base error'))
        # Corrected primary chronology: through actual Guard and unchanged reporting.
        error = OtherBaseException('callback base error through Guard')
        x = self.scenario(callback_error=error)
        self.assertIs(x.raised, error)
        self.assertIsInstance(x.raised.__cause__, c.Stop)
        self.assertEqual(x.descriptor['timestamp'], 100.)
        self.assertEqual(x.until, 110.)

    def test_08_nested_nondefault_exact_LIFO_restoration(self):
        sys.setswitchinterval(.002731)
        original = sys.getswitchinterval()
        with c.boundary_switch_interval():
            outer = sys.getswitchinterval()
            with c.boundary_switch_interval():
                self.assertEqual(sys.getswitchinterval(), outer)
            self.assertEqual(sys.getswitchinterval(), outer)
        self.assertEqual(sys.getswitchinterval(), original)
        self.save('nested', dict(original=original, outer=outer, final=sys.getswitchinterval()))

    def test_09_already_short_intervals_never_lengthened_or_truncated(self):
        for interval in (.000001, .000017, .00005, .000099, .0001):
            with self.subTest(interval=interval):
                sys.setswitchinterval(interval)
                observed = sys.getswitchinterval()
                with c.boundary_switch_interval():
                    self.assertEqual(sys.getswitchinterval(), observed)
                    with c.boundary_switch_interval():
                        self.assertEqual(sys.getswitchinterval(), observed)
                self.assertEqual(sys.getswitchinterval(), observed)

    def test_10_quantization_negative_control_and_actual_restoration_helper(self):
        sys.setswitchinterval(.0001)
        saved = sys.getswitchinterval()
        sys.setswitchinterval(saved)
        truncated = sys.getswitchinterval()
        self.assertNotEqual(truncated, saved, 'Registered CPython negative control must expose truncation')
        c.restore_boundary_switch_interval(saved)
        self.assertEqual(sys.getswitchinterval(), saved)
        rows = []
        for interval in (.000001, .000017, .000099, .0001, .000731, .002731, .005, .02):
            sys.setswitchinterval(interval)
            observed = sys.getswitchinterval()
            sys.setswitchinterval(.000002)
            c.restore_boundary_switch_interval(observed)
            self.assertEqual(sys.getswitchinterval(), observed)
            rows.append(dict(requested=interval, observed=observed, restored=sys.getswitchinterval()))
        self.save('quantization', dict(saved=saved, blind_restore=truncated, rows=rows))

    def test_11_simultaneous_reader_observes_callback_and_after(self):
        entered, read, finished = threading.Event(), threading.Event(), threading.Event()
        observations, errors = [], []
        def reader():
            try:
                if not entered.wait(2):
                    raise AssertionError('callback entry not observed')
                observations.append(sys.getswitchinterval())
                read.set()
                if not finished.wait(2):
                    raise AssertionError('callback completion not observed')
                observations.append(sys.getswitchinterval())
            except BaseException as error:
                errors.append(repr(error))
                read.set()
        thread = threading.Thread(target=reader, name='r14-interval-reader')
        thread.start()
        def callback():
            entered.set()
            self.assertTrue(read.wait(2))
            self.assertFalse(errors)
            return 'one callback'
        try:
            guard = self.guard(callback)
            guard.full_check(True)
        finally:
            entered.set()
            finished.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(observations), 2)
        self.assertLessEqual(observations[0], c.BOUNDARY_SWITCH_INTERVAL)
        self.assertEqual(observations[1], self.original)
        self.save('reader', dict(observations=observations, thread_absent=True, actual_stdlib_thread=True))

    def test_12_actual_Guard_calls_original_callback_once_under_only_verify_lock(self):
        calls = []
        marker = {'sentinel': 'actual callback return'}
        def callback():
            self.assertTrue(guard.verify_lock._is_owned())
            self.assertFalse(guard.lock._is_owned())
            self.assertLessEqual(sys.getswitchinterval(), c.BOUNDARY_SWITCH_INTERVAL)
            calls.append(True)
            return marker
        guard = self.guard(callback)
        self.assertIs(guard.verify, callback)
        guard.full_check(True)
        self.assertEqual(calls, [True])
        self.assertIs(guard.boundaries[0]['observation'], marker)
        self.assertEqual(guard.boundaries[0]['verdict'], 'passed')
        self.assertEqual(sys.getswitchinterval(), self.original)
        self.assertIsNone(c.VERIFY_LOCAL.stats)

    def test_13_Guard_Stop_stays_fatal_and_interval_restored(self):
        error = c.Stop('integrity mismatch', 'identity_or_lease_failure')
        calls = []
        def callback():
            calls.append(True)
            raise error
        guard = self.guard(callback)
        with self.assertRaises(c.Stop) as raised:
            guard.full_check(True)
        self.assertIs(raised.exception, error)
        self.assertIs(guard.failure, error)
        with self.assertRaises(c.Stop) as sticky:
            guard.full_check(True)
        self.assertIs(sticky.exception, error)
        self.assertEqual(calls, [True])
        self.assertEqual(guard.boundaries[0]['verdict'], 'failed')
        self.assertEqual(sys.getswitchinterval(), self.original)

    def test_14_Guard_other_BaseException_propagates_latches_Stop_and_restores(self):
        error = OtherBaseException('integrity callback base exception')
        guard = self.guard(lambda: (_ for _ in ()).throw(error))
        with self.assertRaises(OtherBaseException) as raised:
            guard.full_check(True)
        self.assertIs(raised.exception, error)
        self.assertIsInstance(guard.failure, c.Stop)
        with self.assertRaises(c.Stop):
            guard.check()
        self.assertEqual(guard.boundaries[0]['verdict'], 'failed')
        self.assertNotIn('observation', guard.boundaries[0])
        self.assertEqual(sys.getswitchinterval(), self.original)

    def test_15_cleanup_exception_cannot_publish_Guard_success(self):
        real = sys.setswitchinterval
        calls, injected = [], []
        error = c.Stop('modeled cleanup interruption', 'cancelled')
        def setting(value):
            if value == self.original and not injected:
                injected.append(True)
                raise error
            real(value)
        guard = self.guard(lambda: calls.append(True))
        with patch.object(sys, 'setswitchinterval', setting):
            with self.assertRaises(c.Stop) as raised:
                guard.full_check(True)
        self.assertIs(raised.exception, error)
        self.assertIs(guard.failure, error)
        self.assertEqual(calls, [True])
        self.assertEqual(guard.boundaries[0]['verdict'], 'failed')
        self.assertNotIn('observation', guard.boundaries[0])
        self.assertEqual(sys.getswitchinterval(), self.original)

    def test_16_nonmain_helper_rejected_before_setter_or_callback(self):
        errors, callbacks, setters = [], [], []
        real = sys.setswitchinterval
        def setting(value):
            setters.append(value)
            real(value)
        def entry():
            try:
                with c.boundary_switch_interval():
                    callbacks.append(True)
            except BaseException as error:
                errors.append(error)
        with patch.object(sys, 'setswitchinterval', setting):
            thread = threading.Thread(target=entry)
            thread.start()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], c.Stop)
        self.assertIn('main-thread ownership', str(errors[0]))
        self.assertEqual(callbacks, [])
        self.assertEqual(setters, [])
        self.assertEqual(sys.getswitchinterval(), self.original)

    def test_17_nonmain_Guard_forced_failure_and_safety_only_sampler_supported(self):
        callbacks, errors = [], []
        guard = self.guard(lambda: callbacks.append(True))
        def entry():
            try:
                guard.sample(full=False)
                guard.full_check(True)
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=entry)
        thread.start()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIs(guard.failure, errors[0])
        self.assertEqual(callbacks, [])
        self.assertIsNotNone(guard.last_sample)
        self.assertEqual(guard.boundaries[0]['verdict'], 'failed')
        self.assertEqual(sys.getswitchinterval(), self.original)

    def test_18_independent_Guards_same_main_thread_restore_outer_then_original(self):
        values = []
        inner = self.guard(lambda: values.append(('inner', sys.getswitchinterval())))
        def outer_callback():
            outer = sys.getswitchinterval()
            values.append(('outer', outer))
            inner.full_check(True)
            self.assertEqual(sys.getswitchinterval(), outer)
        outer = self.guard(outer_callback)
        outer.full_check(True)
        self.assertEqual(values[0][1], values[1][1])
        self.assertEqual([x[0] for x in values], ['outer', 'inner'])
        self.assertEqual(sys.getswitchinterval(), self.original)


    def test_19_strict_byte_projection_delta_vs_r11_and_r12_and_protected_bytes(self):
        current = (H / 'long_d2.py').read_text()
        original = (BASE / 'long_d2.py').read_text()
        previous = (R12 / 'long_d2.py').read_text()
        # Whole-controller strict projection: only listed strings/helpers are removed.
        self.assertEqual(delta.project_to_r11_with_sha(current, c.PROTOCOL_SHA256), original)
        self.assertEqual(delta.project_to_r12(current).replace(c.PROTOCOL_SHA256, delta.R12_SHA), previous)
        for name in ('long_d2_executor.py', 'lifecycle.py', 'processes.py', 'boundary_integrity.py',
                     'freeze.py', 'source_equality.py', 'synthetic.py', 'os_checks.py',
                     'stress.py', 'fixture_guards.py', 'fixture_preconditions.py',
                     'parent_command.py', 'rehearsal.py', 'model_r11.py'):
            self.assertEqual((H / name).read_bytes(), (BASE / name).read_bytes(), name + ' r11')
            self.assertEqual((H / name).read_bytes(), (R12 / name).read_bytes(), name + ' r12')
        old_blocks = {n.name: ast.get_source_segment(original, n) for n in ast.parse(original).body
                      if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
        new_blocks = {n.name: ast.get_source_segment(current, n) for n in ast.parse(current).body
                      if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
        self.assertEqual(set(new_blocks) - set(old_blocks), SCHEDULING_HELPERS)
        self.assertEqual([name for name in old_blocks if old_blocks[name] != new_blocks[name]], ['Guard'])
        def methods(text):
            guard = next(n for n in ast.parse(text).body if isinstance(n, ast.ClassDef) and n.name == 'Guard')
            return {n.name: ast.get_source_segment(text, n) for n in guard.body if isinstance(n, ast.FunctionDef)}
        before, after = methods(original), methods(current)
        self.assertEqual(set(before), set(after))
        self.assertEqual([name for name in before if before[name] != after[name]], ['full_check'])
        for name in ('observed_failure', 'primary_error', 'worker_failure', 'record_primary_failure'):
            self.assertEqual(old_blocks[name], new_blocks[name], name)
        self.save('exact-delta', dict(controller_projection_to_r11_byte_equal=True,
            controller_projection_to_r12_byte_equal=True, changed_existing_top_level_blocks=['Guard'],
            changed_Guard_methods=['full_check'], added_helpers=sorted(SCHEDULING_HELPERS),
            r14_additions='early callback catch + masked-cleanup propagation in Guard.full_check only'))

    def test_20_protocol_r10_chain_from_exact_r9_and_r8_and_current_bindings(self):
        r8 = json.loads((BASE / 'protocol-r8-proposal.json').read_text())
        raw9 = (R12 / 'protocol-r9-proposal.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw9).hexdigest(), delta.R12_SHA)
        self.assertEqual(raw9, (H / 'protocol-r9-proposal.json').read_bytes())
        r9 = json.loads(raw9)
        r10 = json.loads((H / 'protocol-r10-proposal.json').read_text())
        chronology = r10.pop('first_callback_failure_chronology')
        self.assertEqual(r10.pop('registered_at_utc') > r9['registered_at_utc'], True)
        normalized = json.loads(json.dumps(r10).replace('prepare-r14/', 'prepare-r12/'))
        r9_cmp = dict(r9)
        r9_cmp.pop('registered_at_utc')
        self.assertEqual(normalized, r9_cmp)
        # r8 -> r9 allowed delta, retained as historical chain.
        r9_chain = dict(r9)
        declaration = r9_chain.pop('boundary_scheduling')
        r9_chain['registered_at_utc'] = r8['registered_at_utc']
        self.assertEqual(json.loads(json.dumps(r9_chain).replace('prepare-r12/', 'prepare-r11/')), r8)
        self.assertEqual(declaration['interval_seconds'], .0001)
        self.assertIn('original verification-callback exception', chronology['scope'])
        self.assertEqual(hashlib.sha256((H / 'protocol-r10-proposal.json').read_bytes()).hexdigest(), c.PROTOCOL_SHA256)
        self.assertTrue(c.PREPARE_REL.endswith('prepare-r14'))
        self.assertTrue(c.PROTOCOL_REL.endswith('protocol-r10.json'))
        self.assertEqual(c.CONFIG_SHA256, r10['config_sha256'])
        self.assertEqual(r10['config']['phase_settings']['run_seed'], 5562873868232098305)
        self.assertEqual(r10['parent_checkpoint_sha256'],
                         'ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f')
        self.assertFalse((c.ORIGINAL_ROOT / c.PROTOCOL_REL).exists(), 'Parent owns external publication')
        self.assertFalse(any((H / name).exists() for name in
            ('classification.json', 'long-identity.json', 'registration.json', 'capsule-final', 'required-lease.json')))

    def scan_sources(self):
        protocol = json.loads((BASE / 'protocol-r8-proposal.json').read_text())
        pins = {n: d for n, d in protocol['base_identity']['sources'].items() if n.endswith('.py')}
        identity = {}
        for name, digest in pins.items():
            data = (c.ORIGINAL_ROOT / name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest, name)
            identity[name] = data.decode()
        controller = {p.name: p.read_text() for p in sorted(H.glob('*.py'))}
        return controller, identity

    def test_21_runtime_vs_test_setter_scan_classifies_and_reports_helpers(self):
        controller, identity = self.scan_sources()
        classes = delta.classify_python(controller, identity)
        sources = dict(controller)
        sources.update(identity)
        self.assertEqual(set(classes), set(sources))
        kinds = {k: sorted(n for n in classes if classes[n] == k) for k in ('runtime', 'test', 'tooling')}
        self.assertEqual(kinds['runtime'], sorted(list(delta.RUNTIME_CONTROLLER) +
            [n for n in identity if n.startswith('python/dodge_rl/')]))
        self.assertEqual(len([n for n in identity if n.startswith('python/dodge_rl/')]), 9)
        self.assertEqual(len([n for n in identity if n.startswith('python/tests/')]), 9)
        report = delta.scan_setters(sources, classes)
        self.assertEqual(report['runtime_competing'], [])
        self.assertTrue(report['runtime_allowed'])
        self.assertEqual({s['path'] for s in report['runtime_allowed']}, {'long_d2.py'})
        self.assertTrue(all(s['scope'].split('.')[0] in SCHEDULING_HELPERS for s in report['runtime_allowed']))
        env_sites = [s for s in report['test'] if s['path'] == 'python/tests/test_env.py']
        self.assertGreaterEqual(len(env_sites), 2, 'Known setter-using GIL witness test helper must be reported')
        self.assertTrue(all(s['path'].startswith(('python/tests/', 'test_')) for s in report['test']))
        source = (H / 'long_d2.py').read_text()
        guard = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == 'Guard')
        start = next(n for n in guard.body if isinstance(n, ast.FunctionDef) and n.name == 'start')
        monitor = next(n for n in start.body if isinstance(n, ast.FunctionDef) and n.name == 'monitor')
        self.assertIn('self.sample(full=False)', ast.get_source_segment(source, monitor))
        self.assertNotIn('full_check', ast.get_source_segment(source, monitor))
        self.save('setter-scan', dict(runtime_allowed=report['runtime_allowed'],
            runtime_competing=report['runtime_competing'], test_helper_sites=report['test'],
            tooling_sites=report['tooling'], classes=kinds,
            test_env_sha256=hashlib.sha256(identity['python/tests/test_env.py'].encode()).hexdigest(),
            identity_python_hash_verified=len(identity),
            scope='Bounded registered controller and registered identity Python only; no whole-program, third-party or native absence claim.',
            ownership='Main-thread cooperation, not enforcement against hostile setters.'))

    def injected_report(self, path, kind, text='\nimport sys\nsys.setswitchinterval(1)\n'):
        controller, identity = self.scan_sources()
        classes = delta.classify_python(controller, identity)
        sources = dict(controller)
        sources.update(identity)
        sources[path] = sources.get(path, '') + text
        classes[path] = kind
        return delta.scan_setters(sources, classes)

    def test_22_injected_setter_in_runtime_source_is_rejected_but_test_source_is_only_reported(self):
        for path in ('python/dodge_rl/injected_runtime.py', 'lifecycle.py', 'processes.py', 'long_d2_executor.py'):
            with self.subTest(runtime=path):
                report = self.injected_report(path, 'runtime')
                self.assertEqual([s['path'] for s in report['runtime_competing']], [path])
        outside = self.injected_report('long_d2.py', 'runtime', '\ndef competing_setter():\n    import sys\n    sys.setswitchinterval(1)\n')
        self.assertEqual([s['scope'] for s in outside['runtime_competing']], ['competing_setter'])
        dynamic = self.injected_report('python/dodge_rl/dynamic.py', 'runtime', "\nimport sys\ngetattr(sys, 'setswitchinterval')(1)\n")
        self.assertEqual([s['path'] for s in dynamic['runtime_competing']], ['python/dodge_rl/dynamic.py'])
        for path in ('python/tests/test_injected.py', 'test_injected_controller.py'):
            with self.subTest(test=path):
                report = self.injected_report(path, 'test')
                self.assertEqual(report['runtime_competing'], [])
                self.assertIn(path, [s['path'] for s in report['test']])

    def test_23_classification_coverage_has_no_arbitrary_omission_or_double_class(self):
        controller, identity = self.scan_sources()
        classes = delta.classify_python(controller, identity)
        sources = dict(controller)
        sources.update(identity)
        with self.assertRaises(AssertionError):
            delta.classify_python(list(controller) + ['mystery_unclassified.py'], identity)
        with self.assertRaises(AssertionError):
            delta.classify_python(controller, list(identity) + ['elsewhere/other.py'])
        with self.assertRaises(AssertionError):
            delta.classify_python(list(controller) + ['long_d2.py'], identity)
        omitted = dict(classes)
        omitted.pop('lifecycle.py')
        with self.assertRaises(AssertionError):
            delta.scan_setters(sources, omitted)
        unscanned = dict(sources)
        unscanned.pop('lifecycle.py')
        with self.assertRaises(AssertionError):
            delta.scan_setters(unscanned, classes)

    def test_24_safety_only_and_nonforced_work_never_sets_interval(self):
        callbacks, setters = [], []
        real = sys.setswitchinterval
        def setting(value):
            setters.append(value)
            real(value)
        guard = self.guard(lambda: callbacks.append(True))
        with patch.object(sys, 'setswitchinterval', setting):
            guard.check()
            guard.sample(full=False)
            guard.full_check(False)
        self.assertEqual(callbacks, [])
        self.assertEqual(setters, [])
        self.assertEqual(sys.getswitchinterval(), self.original)

    def scenario(self, module=None, *, callback_error=None, callback_at=100., cleanup_signal=signal.SIGTERM,
                 cleanup_at=101., pre_latch=None, in_callback=None, peer=None):
        """Actual Guard + unchanged observed_failure + FailurePool, fake clock.
        Signals are modeled by calling ProcessLatch.handle directly (no OS signal)."""
        m = module or c
        sys.setswitchinterval(.002731)
        original = sys.getswitchinterval()
        now = [95.]
        fake = lambda: now[0]
        latch = life.ProcessLatch()
        latch.deadline = 200.
        pool = life.FailurePool(90.)
        calls, first, real = [], [True], sys.setswitchinterval
        def callback():
            calls.append(sys.getswitchinterval())
            if in_callback is not None:
                in_callback(guard)
            now[0] = callback_at
            if callback_error is not None:
                raise callback_error
            return 'one observation'
        def setting(value):
            if value == original and first[0] and cleanup_at is not None:
                first[0] = False
                now[0] = cleanup_at
                latch.handle(cleanup_signal, None)
            real(value)
        guard = m.Guard(200., lambda: None, callback, None, clock=fake, rss=lambda: 1, peak=lambda: 1)
        with patch.object(time, 'monotonic', fake), patch.object(life, 'ACTIVE', latch), \
                patch.object(sys, 'setswitchinterval', setting):
            if pre_latch is not None:
                now[0] = 97.
                latch.record(pre_latch)
                now[0] = 95.
            if peer is not None:
                now[0] = peer['timestamp']
                pool.fail(c.Stop('earlier peer failure', 'resource_stop'), peer['timestamp'], dict(peer), peer=True)
                now[0] = 95.
            with self.assertRaises(BaseException) as raised:
                guard.full_check(True)
            primary, descriptor = m.observed_failure(raised.exception, guard, 'worker')
            until = pool.fail(primary, descriptor['timestamp'], descriptor)
        self.assertEqual(sys.getswitchinterval(), original)
        self.assertEqual(len(calls), 1, 'No duplicate callback')
        self.assertLessEqual(calls[0], c.BOUNDARY_SWITCH_INTERVAL)
        self.assertEqual(guard.boundaries[0]['verdict'], 'failed')
        self.assertNotIn('observation', guard.boundaries[0])
        return SimpleNamespace(raised=raised.exception, guard=guard, latch=latch, pool=pool, primary=primary,
                               descriptor=descriptor, until=until, original=original, calls=calls)

    def test_25_callback_Stop_at_100_over_restore_cancellation_at_101(self):
        error = c.Stop('callback integrity failure', 'identity_or_lease_failure')
        x = self.scenario(callback_error=error)
        self.assertIs(x.raised, error)
        self.assertIsInstance(x.raised.__cause__, c.Stop)
        self.assertEqual(str(x.raised.__cause__), 'Cancellation latched')
        self.assertIs(x.guard.failure, error)
        self.assertEqual(x.guard.failure_at, 100.)
        self.assertIs(x.primary, error)
        self.assertEqual((x.descriptor['timestamp'], x.descriptor['kind']), (100., 'safety_monitor'))
        self.assertEqual((x.pool.first, x.until), (100., 110.), 'Cleanup deadline 110, not 111')
        # Later cancellation still latched and represented, never success.
        self.assertEqual((x.latch.first_cancel_at, x.latch.cancellation_requests), (101., 1))
        self.assertIn('Cancellation latched', x.guard.boundaries[0]['cleanup_error'])
        self.assertIn('callback integrity failure', x.guard.boundaries[0]['error'])
        self.assertIn('Cancellation latched', x.guard.timings[0]['cleanup_error'])
        with self.assertRaises(c.Stop):
            x.guard.check()
        self.save('stop-100-cancel-101', dict(descriptor=x.descriptor, until=x.until, modeled_signal=True))

    def test_26_non_Stop_BaseException_callback_keeps_source_100(self):
        error = OtherBaseException('callback non-Stop')
        x = self.scenario(callback_error=error)
        self.assertIs(x.raised, error)
        self.assertIs(x.raised.__cause__.__class__, c.Stop)
        self.assertIsInstance(x.guard.failure, c.Stop)
        self.assertEqual(x.guard.failure_at, 100.)
        self.assertEqual((x.descriptor['timestamp'], x.descriptor['kind']), (100., 'safety_monitor'))
        self.assertEqual((x.pool.first, x.until), (100., 110.))
        self.assertEqual((x.latch.first_cancel_at, x.latch.cancellation_requests), (101., 1))

    def test_27_callback_with_earlier_valid_descriptor_retains_it(self):
        error = c.Stop('callback with earlier descriptor', 'identity_or_lease_failure')
        earlier = dict(timestamp=96., kind='peer_failure_observed', outcome='identity_or_lease_failure',
                       role='peer', timing_basis='peer_catch_observation', signal=None)
        error.first_failure_descriptor = dict(earlier)
        x = self.scenario(callback_error=error)
        self.assertIs(x.raised, error)
        self.assertIs(x.primary, error)
        self.assertEqual(x.descriptor, earlier)
        self.assertEqual((x.pool.first, x.until), (96., 106.))
        self.assertEqual(x.guard.failure_at, 100.)
        self.assertEqual(x.latch.first_cancel_at, 101.)

    def test_28_earlier_cancel_alarm_guard_and_peer_still_win(self):
        error = c.Stop('callback after earlier failure', 'identity_or_lease_failure')
        cancel = self.scenario(callback_error=error, pre_latch=signal.SIGTERM)
        self.assertEqual((cancel.descriptor['kind'], cancel.descriptor['timestamp'], cancel.until), ('cancel', 97., 107.))
        self.assertIs(cancel.raised, error)
        error = c.Stop('callback after earlier alarm', 'identity_or_lease_failure')
        alarm = self.scenario(callback_error=error, pre_latch=signal.SIGALRM)
        self.assertEqual((alarm.descriptor['kind'], alarm.descriptor['timestamp'], alarm.until), ('alarm', 97., 107.))
        error = c.Stop('callback after earlier guard failure', 'identity_or_lease_failure')
        def earlier_guard(guard):
            guard.failure, guard.failure_at = c.Stop('earlier resource stop', 'resource_stop'), 98.
        guard = self.scenario(callback_error=error, in_callback=earlier_guard)
        self.assertEqual((guard.descriptor['kind'], guard.descriptor['timestamp'], guard.until), ('safety_monitor', 98., 108.))
        self.assertEqual(guard.guard.failure_at, 98.)
        self.assertEqual(str(guard.primary), 'earlier resource stop')
        error = c.Stop('callback after earlier peer', 'identity_or_lease_failure')
        peer = dict(timestamp=96., kind='peer_failure', outcome='resource_stop', role='peer',
                    timing_basis='peer_observation', signal=None)
        result = self.scenario(callback_error=error, peer=peer)
        self.assertEqual(result.pool.first_global, peer)
        self.assertEqual((result.pool.first, result.until), (96., 106.))
        self.assertIs(result.raised, error)

    def test_29_cleanup_only_failure_stays_fatal_and_never_success(self):
        for number, kind in ((signal.SIGTERM, 'cancel'), (signal.SIGALRM, 'alarm')):
            with self.subTest(signal=int(number)):
                x = self.scenario(cleanup_signal=number)
                self.assertIsInstance(x.raised, c.Stop)
                self.assertIs(x.guard.failure, x.raised)
                self.assertEqual(x.guard.failure_at, 101.)
                self.assertEqual(x.descriptor['timestamp'], 101.)
                self.assertEqual(x.guard.boundaries[0]['error'], repr(x.raised))
                self.assertNotIn('cleanup_error', x.guard.boundaries[0])
                with self.assertRaises(c.Stop):
                    x.guard.check()

    def test_30_later_alarm_during_restore_also_keeps_callback_primary(self):
        error = c.Stop('callback before alarm', 'identity_or_lease_failure')
        x = self.scenario(callback_error=error, cleanup_signal=signal.SIGALRM)
        self.assertIs(x.raised, error)
        self.assertEqual(str(x.raised.__cause__), 'Lifetime wall alarm')
        self.assertEqual((x.descriptor['timestamp'], x.descriptor['kind'], x.until), (100., 'safety_monitor', 110.))
        self.assertEqual(x.latch.first_alarm_at, 101.)

    def test_31_source_intact_r12_negative_control_demonstrates_original_bug(self):
        spec = importlib.util.spec_from_file_location('long_d2_r12_negative_control', R12 / 'long_d2.py')
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        self.assertEqual(old.PREPARE_REL.rsplit('-', 1)[1], 'r12')
        error = c.Stop('callback integrity failure', 'identity_or_lease_failure')
        x = self.scenario(old, callback_error=error)
        self.assertIsNot(x.raised, error, 'r12 propagates the later cleanup error')
        self.assertEqual(str(x.raised), 'Cancellation latched')
        self.assertIs(x.raised.__context__, error, 'Original survives only in exception context')
        self.assertEqual((x.guard.failure_at, x.descriptor['timestamp'], x.descriptor['kind']), (101., 101., 'safety_monitor'))
        self.assertEqual(x.until, 111.)
        self.save('r12-negative-control', dict(bug_reproduced=True, source='r12-source/long_d2.py',
            descriptor=x.descriptor, until=x.until, modeled_signal=True, suite_not_rerun=True))
