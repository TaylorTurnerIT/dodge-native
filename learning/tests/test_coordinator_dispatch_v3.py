"""Real temporary-ledger transactions only; no games, learner, or live writes."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'experiments/coordinator_dispatch_v3.py'
spec = importlib.util.spec_from_file_location('coordinator_v3', MODULE)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.queue = self.root / 'queue'; self.queue.mkdir()
        self.old_dir = self.root / 'failed055'; self.old_dir.mkdir()
        self.package = self.root / 'successor056'; self.package.mkdir()
        self.state = self.root / 'state.json'
        self.old_lease = dict(owner='failed055', promoted=False)
        self.new_lease = dict(kind='teacher_ray_training_screen', owner_token='new056',
            package=str(self.package), run_id='successor056', promoted=False)
        self.write(self.state, dict(active_long_campaign=self.old_lease, unrelated=[1, 2, 3]))
        self.failed_fixture()
        self.plan = self.successor_fixture()
        self.output = self.queue / 'dispatch056'
        self.original = self.state.read_bytes()
        self.patches = [patch.object(c, 'QUEUE', self.queue),
            patch.object(c, 'PREDECESSOR', self.old_dir),
            patch.object(c, 'PREDECESSOR_SHA', c.sha(self.old_dir / 'registration-r3.json')),
            patch.object(c.subprocess, 'check_output', return_value='')]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return c.sha(path)

    def failed_fixture(self):
        runtime = self.old_dir / 'runtime'; runtime.mkdir()
        leaf = runtime / 'module.py'; leaf.write_text('old runtime\n')
        reg = dict(expected_lease=self.old_lease, state_path=str(self.state),
            source_pins={}, input_pins={str(leaf): c.sha(leaf)},
            runtime_root=str(runtime), runtime_members=['module.py'],
            checkpoint_sha256='420', model_fingerprint='model420', adam_fingerprint='adam420',
            replicas={'1': {'seed': 1}, '2': {'seed': 2}}, arms={'control': 'fixed', 'rays': 'fixed'},
            ppo={'learning_rate': 3e-5}, exclusions=[[10, 20]], IO_reserve_seconds=120)
        regsha = self.write(self.old_dir / 'registration-r3.json', reg)
        control = self.old_dir / 'outputs/r1-control'; control.mkdir(parents=True)
        final = control / 'checkpoint-036.pt'; final.write_bytes(b'fixture diagnostic checkpoint')
        evidence = dict(counts=dict(frames=2359296, updates=36),
            exit_sha256=self.write(control / 'exit.json', dict(raw_exit_code=0,
                observed_exit_code=0, directly_reaped=True, group_absent=True, pgid=1234)),
            result_sha256=self.write(control / 'result.json', {'fixture': 'complete'}),
            prefix_sha256=self.write(control / 'prefix-qualification.json', {'fixture': 'accepted'}),
            final_checkpoint=dict(path=str(final), sha256=c.sha(final)))
        self.write(control / 'parent-job-audit.json', dict(status='accepted_training_trajectory',
            registration_sha256=regsha, evidence=evidence))
        out = self.old_dir / 'outputs/r1-rays'; out.mkdir(parents=True)
        self.write(out / 'first-failure.json', dict(status='first_failure_preserved_lease_held',
            error="ValueError('Player center/size outside admitted physics range')",
            observed_gameplay_frames=522304))
        self.write(out / 'exit.json', dict(raw_exit_code=1, observed_exit_code=1,
            directly_reaped=True, group_absent=True, pgid=1235))
        rows = [dict(kind='update_complete', gameplay_frames_total=65536 * i) for i in range(1, 8)]
        rows.append(dict(kind='update_failure', partial_gameplay_frames=63552))
        (out / 'updates.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
        (out / 'native-events.jsonl').write_text('{"fixture":"journal"}\n')
        self.write(self.old_dir / 'first-failure.json',
            dict(status='first_failure_preserved_lease_held', completed_jobs=[evidence]))
        self.write(self.old_dir / 'launch.claimed', dict(pid=1233))
        (self.old_dir / 'empty-pycache').mkdir()

    def successor_fixture(self):
        old = c.read(self.old_dir / 'registration-r3.json')
        runtime = self.package / 'runtime'; runtime.mkdir()
        leaf = runtime / 'module.py'; leaf.write_text('new runtime\n')
        interpreter = self.root / 'python'; interpreter.write_text('fixture interpreter\n')
        source = self.package / 'worker.py'; source.write_text('fixture source\n')
        authority = self.queue / 'authority-r3.json'
        authoritysha = self.write(authority, dict(schema='teacher_training_queue_authority_v3',
            predecessor_record='DODGE-055', successor_record='DODGE-056',
            fresh_successor_attempts_authorized=1, no_claim_or_lease_reset=True,
            limits=dict(battery_operation_allowed=True, AC_required=False)))
        reg = dict(schema='dodge_ray_training_registration_v1', record='DODGE-056',
            package=str(self.package), run_id='successor056', expected_lease=self.new_lease,
            authority_path=str(authority), authority_sha256=authoritysha,
            source_pins={str(source): c.sha(source)},
            input_pins={str(leaf): c.sha(leaf), str(interpreter): c.sha(interpreter)},
            runtime_root=str(runtime), runtime_members=['module.py'], interpreter=str(interpreter),
            jobs=[dict(id=name) for name in ['r1-control', 'r1-rays', 'r2-rays', 'r2-control']],
            frame_target=2359296, updates=36, envs=64, rollout=1024, action_repeat=1,
            effective_minibatch=2048, microbatch=512, checkpoint_updates=[12, 24, 36], prefix_updates=2,
            work_seconds=5400, receipt_seconds=180, campaign_total_seconds=22320,
            rss_bytes=6*2**30, mps_bytes=6*2**30, battery_operation_allowed=True, AC_required=False,
            evaluation_games=0, promotion=False, no_retry=True, no_automatic_resume=True,
            coordinator_thread='fixture-coordinator')
        for key in ['checkpoint_sha256', 'model_fingerprint', 'adam_fingerprint', 'replicas',
                    'arms', 'ppo', 'exclusions', 'IO_reserve_seconds']: reg[key] = old[key]
        for job in reg['jobs']: (self.package / 'outputs' / job['id']).mkdir(parents=True)
        (self.package / 'empty-pycache').mkdir()
        regpath = self.package / 'registration.json'; regsha = self.write(regpath, reg)
        digest = c.verify_pins(reg)
        origins = {'fixture': dict(path=str(leaf), sha256=c.sha(leaf))}
        preflight = self.package / 'preflight.json'
        preflightsha = self.write(preflight, dict(status='CPU_runtime_import_and_420_migration_passed',
            registration_sha256=regsha, runtime_manifest_sha256=digest,
            interpreter=str(interpreter), interpreter_sha256=c.sha(interpreter), loaded_origins=origins))
        readiness = self.package / 'readiness.json'
        self.write(readiness, dict(status='CPU_source_and_420_migration_ready',
            registration_sha256=regsha, expected_lease=self.new_lease, runtime_manifest_sha256=digest,
            CPU_preflight_path=str(preflight), CPU_preflight_sha256=preflightsha, runtime_origins=origins))
        review = self.package / 'review.json'
        self.write(review, dict(status='no_blocking_findings', registration_sha256=regsha,
            coordinator_source_pins={str(MODULE.resolve()): c.sha(MODULE),
                                     str(c.BASE.resolve()): c.sha(c.BASE)}))
        plan = dict(record='DODGE-056')
        for key, path in [('registration', regpath), ('review', review),
                          ('readiness', readiness), ('authority', authority)]:
            plan[key + '_path'] = str(path); plan[key + '_sha256'] = c.sha(path)
        plan['dispatch_template'] = dict(plan, schema='coordinator_exact_training_dispatch_v1',
            status='dispatched_once', stage='training', one_attempt=True,
            coordinator_thread='fixture-coordinator', expected_lease=self.new_lease)
        return plan

    def rebind(self, kind, value):
        path = Path(self.plan[kind + '_path'])
        self.write(path, value)
        self.plan[kind + '_sha256'] = c.sha(path)
        self.plan['dispatch_template'][kind + '_sha256'] = c.sha(path)

    def assert_no_dispatch(self):
        self.assertEqual(self.state.read_bytes(), self.original)
        self.assertFalse(self.output.exists())
        self.assertFalse((self.package / 'launch.claimed').exists())

    def test_exact_source_runtime_preflight_authority_validate_without_mutation(self):
        self.assertEqual(c.validate(self.plan)['expected_lease'], self.new_lease)
        self.assert_no_dispatch()

    def test_real_failed_capsule_evidence_is_acknowledged_as_failure(self):
        evidence = c.failed_predecessor_audit()
        self.assertEqual(evidence['record'], 'DODGE-055')
        self.assertIs(evidence['campaign_success'], False)
        self.assertEqual(evidence['exact_lease'], self.old_lease)
        self.assert_no_dispatch()

    def test_durable_disposition_precedes_real_non_null_CAS(self):
        original = c.exact_handoff
        def ordered(path, old, new):
            self.assertTrue((self.output / 'dispatch.claimed').exists())
            receipt = c.read(self.output / 'failure-disposition.json')
            self.assertIs(receipt['campaign_success'], False)
            self.assertEqual(c.read(self.state)['active_long_campaign'], self.old_lease)
            return original(path, old, new)
        with patch.object(c, 'exact_handoff', side_effect=ordered): result = c.dispatch(self.plan, self.output)
        self.assertEqual(c.read(self.state), dict(active_long_campaign=self.new_lease, unrelated=[1, 2, 3]))
        gate = c.read(result['dispatch_path'])
        handoff = c.read(gate['lease_handoff_path'])
        self.assertEqual(handoff['previous_lease'], self.old_lease)
        self.assertEqual(handoff['replacement_lease'], self.new_lease)
        self.assertEqual(c.sha(gate['failure_disposition_path']), handoff['failure_disposition_sha256'])
        self.assertFalse((self.package / 'launch.claimed').exists())

    def test_repeated_dispatch_cannot_reset_or_replace_receipts(self):
        c.dispatch(self.plan, self.output)
        before = {p.name: p.read_bytes() for p in self.output.iterdir()}
        with self.assertRaisesRegex(ValueError, 'not held'): c.dispatch(self.plan, self.output)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.output.iterdir()})

    def test_foreign_lease_never_creates_claim(self):
        self.write(self.state, dict(active_long_campaign={'foreign': True}))
        self.original = self.state.read_bytes()
        with self.assertRaisesRegex(ValueError, 'not held'): c.dispatch(self.plan, self.output)
        self.assert_no_dispatch()

    def test_output_symlink_cannot_redirect_receipts_outside_queue(self):
        outside = self.root / 'unrelated'; outside.mkdir()
        self.output.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'real direct child'):
            c.dispatch(self.plan, self.output)
        self.assertEqual(self.state.read_bytes(), self.original)
        self.assertTrue(self.output.is_symlink())
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.package / 'launch.claimed').exists())

    def test_output_symlink_inside_queue_is_also_rejected(self):
        inside = self.queue / 'other-dispatch'; inside.mkdir()
        self.output.symlink_to(inside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'real direct child'):
            c.dispatch(self.plan, self.output)
        self.assertEqual(self.state.read_bytes(), self.original)
        self.assertEqual(list(inside.iterdir()), [])

    def test_output_symlink_swap_during_mkdir_is_rejected_before_claim(self):
        outside = self.root / 'unrelated'; outside.mkdir()
        original = Path.mkdir
        def replaced(path, *args, **kwargs):
            if path == self.output:
                path.symlink_to(outside, target_is_directory=True)
            else:
                return original(path, *args, **kwargs)
        with patch.object(Path, 'mkdir', replaced):
            with self.assertRaisesRegex(ValueError, 'changed while creating'):
                c.dispatch(self.plan, self.output)
        self.assertEqual(self.state.read_bytes(), self.original)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.package / 'launch.claimed').exists())

    def test_invalid_template_schema_status_or_attempt_rejected_before_claim(self):
        original = copy.deepcopy(self.plan['dispatch_template'])
        for key, value in [('schema', 'wrong'), ('status', 'ready'), ('stage', 'evaluation'),
                           ('one_attempt', False), ('record', 'DODGE-055')]:
            with self.subTest(key=key):
                self.plan['dispatch_template'] = dict(original, **{key: value})
                with self.assertRaisesRegex(ValueError, 'template'): c.dispatch(self.plan, self.output)
                self.assert_no_dispatch()

    def test_missing_template_attempt_rejected_before_claim(self):
        self.plan['dispatch_template'].pop('one_attempt')
        with self.assertRaises(KeyError): c.dispatch(self.plan, self.output)
        self.assert_no_dispatch()

    def test_wrong_readiness_status_rejected_before_claim(self):
        ready = c.read(self.plan['readiness_path']); ready['status'] = 'not_ready'; self.rebind('readiness', ready)
        with self.assertRaisesRegex(ValueError, 'Readiness'): c.dispatch(self.plan, self.output)
        self.assert_no_dispatch()

    def test_wrong_readiness_runtime_rejected_before_claim(self):
        ready = c.read(self.plan['readiness_path']); ready['runtime_manifest_sha256'] = 'wrong'; self.rebind('readiness', ready)
        with self.assertRaisesRegex(ValueError, 'runtime binding'): c.dispatch(self.plan, self.output)
        self.assert_no_dispatch()

    def test_unregistered_runtime_member_rejected_before_claim(self):
        (self.package / 'runtime' / 'extra.py').write_text('unregistered')
        with self.assertRaisesRegex(ValueError, 'inventory'): c.dispatch(self.plan, self.output)
        self.assert_no_dispatch()

    def test_modified_successor_source_rejected_before_claim(self):
        (self.package / 'worker.py').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'pin changed'): c.dispatch(self.plan, self.output)
        self.assert_no_dispatch()

    def test_modified_old_capsule_rejected_before_claim(self):
        (self.old_dir / 'runtime/module.py').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'pin changed'): c.dispatch(self.plan, self.output)
        self.assert_no_dispatch()

    def test_missing_independent_coordinator_review_rejected_before_claim(self):
        review = c.read(self.plan['review_path']); review['coordinator_source_pins'] = {}; self.rebind('review', review)
        with self.assertRaisesRegex(ValueError, 'independently reviewed'): c.dispatch(self.plan, self.output)
        self.assert_no_dispatch()

    def test_multiple_successors_authority_rejected_before_claim(self):
        authority = c.read(self.plan['authority_path']); authority['fresh_successor_attempts_authorized'] = 2
        self.rebind('authority', authority)
        with self.assertRaisesRegex(ValueError, 'authority'): c.dispatch(self.plan, self.output)
        self.assert_no_dispatch()

    def test_consumed_successor_rejected_before_claim(self):
        (self.package / 'launch.claimed').write_text('preserve')
        with self.assertRaisesRegex(ValueError, 'already consumed'): c.dispatch(self.plan, self.output)
        self.assertEqual(self.state.read_bytes(), self.original)
        self.assertFalse(self.output.exists())

    def test_output_weights_prevent_dispatch(self):
        (self.package / 'outputs/r1-rays/weights.pt').write_bytes(b'preserve')
        with self.assertRaisesRegex(ValueError, 'not empty'): c.dispatch(self.plan, self.output)
        self.assert_no_dispatch()

    def test_alive_old_group_rejected_before_claim(self):
        with patch.object(c.subprocess, 'check_output', return_value='1233 1233\n'):
            with self.assertRaisesRegex(ValueError, 'group remains'): c.dispatch(self.plan, self.output)
        self.assert_no_dispatch()

    def test_control_checkpoint_tampering_rejected_before_claim(self):
        (self.old_dir / 'outputs/r1-control/checkpoint-036.pt').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'checkpoint differs'): c.dispatch(self.plan, self.output)
        self.assert_no_dispatch()

    def test_cas_race_preserves_foreign_owner_and_first_failure(self):
        original = c.exact_handoff
        def raced(*args):
            self.write(self.state, dict(active_long_campaign={'foreign': 'arrived'}))
            return original(*args)
        with patch.object(c, 'exact_handoff', side_effect=raced):
            with self.assertRaisesRegex(ValueError, 'lease differs'): c.dispatch(self.plan, self.output)
        self.assertEqual(c.read(self.state)['active_long_campaign'], {'foreign': 'arrived'})
        self.assertTrue((self.output / 'dispatch.claimed').exists())
        self.assertTrue((self.output / 'failure-disposition.json').exists())
        self.assertTrue((self.output / 'first-failure.json').exists())
        self.assertFalse((self.output / 'dispatch.json').exists())

    def test_post_CAS_receipt_failure_keeps_new_lease_and_evidence(self):
        original = c.save
        def interrupted(path, value):
            if Path(path).name == 'lease-handoff.json': raise OSError('fixture interrupted I/O')
            return original(path, value)
        with patch.object(c, 'save', side_effect=interrupted):
            with self.assertRaisesRegex(OSError, 'interrupted'): c.dispatch(self.plan, self.output)
        self.assertEqual(c.read(self.state)['active_long_campaign'], self.new_lease)
        self.assertTrue((self.output / 'failure-disposition.json').exists())
        self.assertTrue((self.output / 'first-failure.json').exists())
        self.assertFalse((self.output / 'dispatch.json').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
