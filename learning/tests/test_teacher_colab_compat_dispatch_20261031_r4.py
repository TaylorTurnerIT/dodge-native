"""No Colab calls: real dummy subprocesses, shared-lease CAS and receipt files."""
import io
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'experiments/teacher_colab_compat_dispatch_20261031_r4.py'
spec = importlib.util.spec_from_file_location('t4_controller', MODULE)
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
GUARD = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/experiments/teacher_ray_colab_t4_r3/billing_guard.py')
billing = c.load_module(GUARD, c.sha(GUARD), 'real_t4_billing_guard')


class FakeClock:
    def __init__(self): self.value = 0
    def now(self): return self.value
    def sleep(self, seconds): self.value += seconds


def bundle(nonce, payload, *, bad_nonce=False, failed=False, memory=1024):
    identity = dict(record='DODGE-060', job_nonce='foreign' if bad_nonce else nonce,
                    payload_sha256=payload, native_games=0, training_frames=0, trained_weights_saved=False)
    package_origins = {key: dict(path='/usr/lib/' + key, sha256='e'*64)
                       for key in ['python', 'torch_python', 'torch_native', 'numpy_python', 'numpy_native']}
    versions = dict(torch='fixture', numpy='fixture', python='fixture', cuda_runtime='fixture')
    return {
        'bootstrap-result.json': dict(identity, schema='dodge_colab_synthetic_receipt_bundle_v1',
                                     status='failed' if failed else 'complete'),
        'CUDA-compatibility.json': dict(identity, schema='dodge_colab_synthetic_compatibility_result_v1',
            status='synthetic_420_migration_passed', device='cuda', device_index=0, GPU='Tesla T4',
            same_device_zero_gate_exact=True, synthetic_optimizer_steps=1,
            **versions, platform='linux', checkpoint_sha256=
                '7e0de8640f1337261412d91cde6bc692772ff212fbd360f5aad415dc6bc7ed4b',
            source_model_fingerprint='a'*64, source_Adam_fingerprint='b'*64, migration={},
            seed_pool_opened=False, heldout_opened=False, simulator_restored=False,
            runtime_origins={'dodge_rl.fixture': dict(path='/content/fixture/source/runtime.py', sha256='c'*64)},
            package_origins=package_origins,
            CPU_device_numeric_tolerance=dict(atol=2e-5, rtol=2e-5), peak_RSS_bytes=memory,
            accelerator_peak_reserved_bytes=memory, accelerator_peak_allocated_bytes=memory),
        'watchdog.json': dict(identity, schema='dodge_colab_synthetic_watchdog_result_v1',
            status='complete', device='cuda', child_returncode=0, owned_group_absent=True,
            peak_group_RSS_bytes=memory, peak_sampled_CUDA_driver_process_bytes=memory),
        'CUDA-compatibility.json.runtime-provenance.json': dict(record='DODGE-060', job_nonce=nonce,
            package_origins=package_origins, **versions)}


def write_bundle(path, docs):
    with tarfile.open(path, 'w') as archive:
        for name, value in docs.items():
            data = json.dumps(value).encode(); member = tarfile.TarInfo(name); member.size = len(data)
            archive.addfile(member, io.BytesIO(data))


class DummyTransport:
    def __init__(self, reg, clock, mode='success'):
        self.reg, self.clock, self.mode = reg, clock, mode
        self.allocated = False; self.assigned = False; self.work = False
        self.nonce = None; self.actions = []; self.process = None
        self.balance = 100.; self.observations = 0

    def snapshot(self, timeout):
        self.actions.append('snapshot'); self.clock.value += .01
        if not self.allocated:
            active = self.mode == 'preexisting'
            return dict(raw=dict(currentBalance=100., consumptionRateHourly=2. if active else 0.,
                                 assignmentsCount=int(active)),
                        assignments=[dict(endpoint='foreign', accelerator='T4')] if active else [], session=None)
        if self.mode == 'connection_lost' and self.work: raise TimeoutError('fixture connection lost')
        if self.mode == 'provider_removed' and self.work: self.assigned = False
        self.observations += 1
        if self.mode != 'delayed_balance': self.balance -= .001
        rate = 0. if self.mode == 'zero_rate' else 2.
        if self.mode == 'over_rate': rate = 4.
        if self.mode == 'debit': self.balance = 93.9
        if self.mode == 'lease_lost' and self.work:
            Path(self.reg['state_path']).write_text(json.dumps(dict(active_long_campaign={'foreign': True})))
        if self.mode == 'cancel' and self.work:
            (self.output / 'cancel.requested').write_text('cancel')
        return dict(raw=dict(currentBalance=self.balance, consumptionRateHourly=rate if self.assigned else 0.,
                             assignmentsCount=int(self.assigned)),
                    assignments=[dict(endpoint='owned-endpoint', accelerator='T4')] if self.assigned else [],
                    session=None)

    def allocate(self, nonce, output, timeout):
        self.actions.append('allocate'); self.allocated = self.assigned = True
        self.nonce, self.output = nonce, Path(output)
        claim = c.read(self.output / 'dispatch.claimed')
        assert claim['notebook_hash'] == nonce
        assert c.read(self.reg['state_path'])['active_long_campaign'] == self.reg['expected_lease']
        if self.mode == 'ambiguous': raise TimeoutError('Do not publish secret-token=fixture')
        owned = dict(name=self.reg['session_name'], endpoint='owned-endpoint', accelerator='T4', notebook_hash=nonce)
        c.save(self.output / 'owned-endpoint.json', owned)
        if self.mode == 'response_lost': raise TimeoutError('Do not publish proxy-token=fixture')
        return owned

    def upload(self, local, remote, timeout): self.actions.append('upload')

    def start(self, nonce, timeout):
        self.actions.append('exec'); self.work = True
        long = self.mode in ['provider_removed', 'connection_lost', 'suspend', 'lease_lost', 'cancel']
        code = 'import time; time.sleep(60)' if long else 'pass'
        self.process = subprocess.Popen([sys.executable, '-B', '-c', code], start_new_session=True,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if self.mode == 'suspend': self.clock.value += 2000
        return self.process

    def poll(self, process):
        if self.mode in ['provider_removed', 'connection_lost', 'suspend', 'lease_lost', 'cancel']: return process.poll()
        return process.wait(timeout=3)

    def stop_local(self, process):
        self.actions.append('stop_local')
        c.SDKTransport.stop_local(self, process)

    def download(self, remote, local, timeout):
        self.actions.append('download')
        if self.mode == 'download_missing': raise FileNotFoundError('fixture missing receipt')
        write_bundle(local, bundle(self.nonce, self.reg['payload_sha256'],
            bad_nonce=self.mode == 'bad_nonce', failed=self.mode == 'failed_receipt',
            memory=6*2**30 if self.mode == 'memory' else 1024))

    def unassign(self, endpoint, output, timeout):
        self.actions.append('unassign'); assert endpoint == 'owned-endpoint'
        if self.mode != 'false_stop_text': self.assigned = False


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.parent = self.root / 'parent'; self.parent.mkdir()
        self.state = self.root / 'state.json'; self.old = {'owner': 'failed056'}
        self.new = {'owner': 'new057'}
        self.state.write_text(json.dumps(dict(active_long_campaign=self.old, unrelated=[1, 2, 3])))
        self.reg = dict(state_path=str(self.state), expected_lease=self.new,
            session_name='colab057-t4-synthetic', uploads=[dict(local='source', remote='/content/source')],
            download_remote='/content/receipts.tar', payload_sha256='f'*64)
        cpu = self.root / 'cpu.json'
        cpu.write_text(json.dumps(dict(source_model_fingerprint='a'*64, source_Adam_fingerprint='b'*64,
            migration={}, runtime_origins={'dodge_rl.fixture': dict(sha256='c'*64)})))
        self.reg.update(prior_assigned_seconds_upper_bound=36.729438066482544, prior_cost_upper_estimate_CU=0.03060786505540212, CPU_420_receipt_path=str(cpu), remote_root='/content/fixture',
            source_root='/fixture/source', source_pins={'/fixture/source/runtime.py': 'c'*64})
        self.plan = dict(registration_sha256='a'*64, review_sha256='b'*64)
        self.disposition = dict(record='DODGE-059', campaign_success=False, exact_lease=self.old,
                                state_path=str(self.state), prior_assigned_seconds_upper_bound=self.reg['prior_assigned_seconds_upper_bound'])
        self.output = self.parent / 'dispatch'; self.clock = FakeClock()
        self.patch = patch.object(c, 'PARENT', self.parent); self.patch.start()

    def tearDown(self):
        self.patch.stop(); self.temp.cleanup()

    def run_mode(self, mode):
        transport = DummyTransport(self.reg, self.clock, mode)
        controller = c.Controller(self.reg, self.plan, self.output, transport,
                                  billing.BillingGuard, self.clock, self.clock.sleep)
        if mode in ['success', 'delayed_balance']: result = controller.run(self.disposition)
        else:
            with self.assertRaises((ValueError, TimeoutError)): controller.run(self.disposition)
            result = None
        if transport.process is not None: self.assertIsNotNone(transport.process.poll())
        return transport, result

    def test_success_actual_CAS_dummy_child_and_receipts_before_teardown(self):
        t, result = self.run_mode('success')
        self.assertEqual(c.read(self.state), dict(active_long_campaign=self.new, unrelated=[1, 2, 3]))
        self.assertEqual(result['status'], 'compatibility_complete_pending_coordinator_acceptance')
        self.assertFalse(result['lease_released'])
        self.assertEqual(t.actions.count('allocate'), 1)
        self.assertLess(t.actions.index('download'), t.actions.index('unassign'))
        self.assertEqual(c.read(self.output / 'failure-disposition.json')['record'], 'DODGE-059')
        self.assertTrue(c.read(self.output / 'teardown.json')['budget_within_limits'])

    def test_unknown_allocation_never_retries_or_stops_unowned_runtime(self):
        t, _ = self.run_mode('ambiguous')
        self.assertEqual(t.actions.count('allocate'), 1)
        self.assertNotIn('unassign', t.actions)
        self.assertNotIn('exec', t.actions)
        self.assertEqual(c.read(self.output / 'cleanup-first-failure.json')['status'],
                         'allocation_outcome_ambiguous_no_unowned_stop')
        self.assertNotIn('secret-token', (self.output / 'first-failure.json').read_text())

    def test_response_loss_uses_durable_exact_endpoint_ownership(self):
        t, _ = self.run_mode('response_lost')
        self.assertIn('unassign', t.actions)
        self.assertEqual(t.actions.count('allocate'), 1)
        self.assertEqual(c.read(self.output / 'teardown.json')['status'], 'owned_assignment_absent')

    def test_preexisting_assignment_prevents_claim_or_handoff(self):
        t, _ = self.run_mode('preexisting')
        self.assertNotIn('allocate', t.actions); self.assertFalse(self.output.exists())
        self.assertEqual(c.read(self.state)['active_long_campaign'], self.old)

    def test_bad_rates_or_debit_stop_before_fixture_and_teardown(self):
        for mode in ['zero_rate', 'over_rate', 'debit']:
            with self.subTest(mode=mode):
                self.output = self.parent / mode
                self.state.write_text(json.dumps(dict(active_long_campaign=self.old)))
                t, _ = self.run_mode(mode)
                self.assertNotIn('exec', t.actions); self.assertIn('unassign', t.actions)
                self.assertTrue((self.output / 'first-failure.json').exists())
                self.assertEqual(c.read(self.state)['active_long_campaign'], self.new)

    def test_delayed_balance_completes_without_false_stale_failure(self):
        t, result = self.run_mode('delayed_balance')
        self.assertTrue(t.work)
        self.assertEqual(result['status'], 'compatibility_complete_pending_coordinator_acceptance')
        self.assertEqual(t.actions.count('allocate'), 1)
        self.assertEqual(c.read(self.output / 'teardown.json')['removal_classification'],
                         'coordinator_requested_release')

    def test_provider_removal_is_not_reported_as_our_release_or_idle_reclamation(self):
        t, _ = self.run_mode('provider_removed')
        self.assertNotIn('unassign', t.actions)
        receipt = c.read(self.output / 'teardown.json')
        self.assertEqual(receipt['removal_classification'], 'assignment_absent_before_our_release_request')
        self.assertFalse(receipt['release_requested_by_coordinator'])
        self.assertEqual(receipt['provider_termination_reason'], 'unknown')

    def test_connection_loss_never_claims_Google_removed_VM(self):
        t, _ = self.run_mode('connection_lost')
        self.assertIn('unassign', t.actions)
        self.assertFalse(c.read(self.output / 'first-failure.json')['assignment_absent_before_our_release_request'])
        self.assertEqual(c.read(self.output / 'cleanup-first-failure.json')['status'], 'teardown_unconfirmed')

    def test_suspend_counts_toward_budget_and_preserves_absence_proof(self):
        t, _ = self.run_mode('suspend')
        self.assertIn('unassign', t.actions)
        teardown = c.read(self.output / 'teardown.json')
        self.assertEqual(teardown['status'], 'owned_assignment_absent')
        self.assertFalse(teardown['budget_within_limits'])

    def test_lease_loss_does_not_restore_or_clear_foreign_owner(self):
        t, _ = self.run_mode('lease_lost')
        self.assertIn('unassign', t.actions)
        self.assertEqual(c.read(self.state)['active_long_campaign'], {'foreign': True})

    def test_coordinator_cancel_stops_owned_work(self):
        t, _ = self.run_mode('cancel')
        self.assertIn('stop_local', t.actions); self.assertIn('unassign', t.actions)

    def test_false_stop_text_is_not_absence_proof(self):
        t, _ = self.run_mode('false_stop_text')
        self.assertTrue(t.assigned)
        self.assertEqual(c.read(self.output / 'cleanup-first-failure.json')['status'], 'teardown_unconfirmed')
        self.assertTrue((self.output / 'first-failure.json').exists())

    def test_bad_missing_failure_or_overmemory_receipts_keep_lease_and_cleanup(self):
        for mode in ['bad_nonce', 'download_missing', 'failed_receipt', 'memory']:
            with self.subTest(mode=mode):
                self.output = self.parent / mode
                self.state.write_text(json.dumps(dict(active_long_campaign=self.old)))
                t, _ = self.run_mode(mode)
                self.assertIn('unassign', t.actions)
                self.assertTrue((self.output / 'first-failure.json').exists())
                self.assertEqual(c.read(self.state)['active_long_campaign'], self.new)

    def test_consumed_output_cannot_reallocate(self):
        t, _ = self.run_mode('success')
        transport = DummyTransport(self.reg, self.clock)
        controller = c.Controller(self.reg, self.plan, self.output, transport,
                                  billing.BillingGuard, self.clock, self.clock.sleep)
        with self.assertRaises(FileExistsError): controller.run(self.disposition)
        self.assertNotIn('allocate', transport.actions)

    def test_symlink_output_cannot_redirect_claims_or_global_lease(self):
        outside = self.root / 'outside'; outside.mkdir(); self.output.symlink_to(outside)
        transport = DummyTransport(self.reg, self.clock)
        controller = c.Controller(self.reg, self.plan, self.output, transport,
                                  billing.BillingGuard, self.clock, self.clock.sleep)
        with self.assertRaisesRegex(ValueError, 'real coordinator'): controller.run(self.disposition)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(c.read(self.state)['active_long_campaign'], self.old)

    def test_continuous_clock_counts_suspend_and_cannot_reverse(self):
        with patch.object(c.time, 'time', side_effect=[100., 5000., 105.]), \
             patch.object(c.time, 'monotonic', side_effect=[200., 201., 202.]):
            clock = c.Clock(); self.assertEqual(clock.now(), 4900.); self.assertEqual(clock.now(), 4900.)

    def completed_terminal(self):
        transport, terminal = self.run_mode('success')
        c.save(self.output / 'parent-terminal-audit.json', terminal)
        return transport

    def test_durable_accepted_audit_precedes_normal_exact_release(self):
        transport = self.completed_terminal(); original = c.save
        def ordered(path, value):
            if Path(path).name == 'coordinator-terminal-audit.json':
                self.assertEqual(c.read(self.state)['active_long_campaign'], self.new)
            if Path(path).name == 'lease-release.json':
                self.assertTrue((self.output / 'coordinator-terminal-audit.json').exists())
                self.assertIsNone(c.read(self.state)['active_long_campaign'])
            return original(path, value)
        with patch.object(c, 'validate_plan', return_value=self.reg), patch.object(c, 'save', side_effect=ordered):
            audit = c.accept_terminal(self.plan, self.output, transport)
        self.assertEqual(audit['status'], 'accepted_synthetic_cuda_compatibility')
        self.assertEqual(c.read(self.state), dict(active_long_campaign=None, unrelated=[1, 2, 3]))

    def test_wrong_terminal_lease_never_writes_accepted_audit(self):
        transport = self.completed_terminal()
        self.state.write_text(json.dumps(dict(active_long_campaign={'foreign': True})))
        with patch.object(c, 'validate_plan', return_value=self.reg):
            with self.assertRaisesRegex(ValueError, 'terminal lease'):
                c.accept_terminal(self.plan, self.output, transport)
        self.assertFalse((self.output / 'coordinator-terminal-audit.json').exists())

    def test_terminal_acceptance_cannot_repeat_or_create_partial_evidence(self):
        transport = self.completed_terminal()
        with patch.object(c, 'validate_plan', return_value=self.reg):
            c.accept_terminal(self.plan, self.output, transport)
            before = {p.name: p.read_bytes() for p in self.output.iterdir()}
            with self.assertRaisesRegex(ValueError, 'already exists'):
                c.accept_terminal(self.plan, self.output, transport)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.output.iterdir()})

    def test_foreign_local_session_blocks_upload_exec_and_download(self):
        self.output.mkdir()
        owned = dict(name='session', endpoint='ours', accelerator='T4')
        c.save(self.output / 'owned-endpoint.json', owned)
        config = self.root / 'private-sessions.json'
        config.write_text(json.dumps({'session': dict(name='session', endpoint='foreign',
                                                     accelerator='T4', token='secret')}))
        transport = object.__new__(c.SDKTransport); transport.output = self.output
        transport.reg = dict(session_name='session', cli_config_path=str(config))
        with self.assertRaisesRegex(ValueError, 'no longer matches'): transport.require_owned_session()

    def test_tar_traversal_or_failure_member_is_never_extracted_or_accepted(self):
        archive = self.root / 'unsafe.tar'
        docs = bundle('nonce', 'payload'); docs['../outside.json'] = dict(secret='not extracted')
        write_bundle(archive, docs)
        with self.assertRaisesRegex(ValueError, 'Unsafe'): c.validate_receipts(archive, 'nonce', 'payload')
        self.assertFalse((self.root / 'outside.json').exists())
        docs = bundle('nonce', 'payload'); docs['first-failure.json'] = dict(error='fixture')
        write_bundle(archive, docs)
        with self.assertRaisesRegex(ValueError, 'Failure receipt'): c.validate_receipts(archive, 'nonce', 'payload')

    def test_remote_provenance_migration_and_origin_changes_reject(self):
        archive = self.root / 'receipts.tar'
        for field, value in [('source_model_fingerprint', 'foreign'), ('migration', {'changed': True}),
                             ('runtime_origins', {}), ('platform', 'darwin'), ('seed_pool_opened', True)]:
            with self.subTest(field=field):
                docs = bundle('nonce', 'payload'); docs['CUDA-compatibility.json'][field] = value
                write_bundle(archive, docs)
                with self.assertRaises(ValueError): c.validate_receipts(archive, 'nonce', 'payload', self.reg)
        docs = bundle('nonce', 'payload')
        docs['CUDA-compatibility.json.runtime-provenance.json']['job_nonce'] = 'foreign'
        write_bundle(archive, docs)
        with self.assertRaisesRegex(ValueError, 'provenance'):
            c.validate_receipts(archive, 'nonce', 'payload', self.reg)

    def test_corrupt_handoff_blocks_terminal_acceptance_and_release(self):
        transport = self.completed_terminal()
        path = self.output / 'lease-handoff.json'; data = c.read(path)
        data['review_sha256'] = 'foreign'; path.write_text(json.dumps(data))
        with patch.object(c, 'validate_plan', return_value=self.reg):
            with self.assertRaisesRegex(ValueError, 'handoff identity'):
                c.accept_terminal(self.plan, self.output, transport)
        self.assertEqual(c.read(self.state)['active_long_campaign'], self.new)
        self.assertFalse((self.output / 'coordinator-terminal-audit.json').exists())


class PlanValidationTests(unittest.TestCase):
    """Validate real frozen inputs with synthetic review files; no account access."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        freeze = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-teacher-ray-geometry-20261030/learning/runs/v2/teacher-ray-colab-cuda-compat-20261031-r2/owner-source-freeze-r1.json')
        self.reg = copy.deepcopy(c.read(freeze))
        authority_path = c.PARENT / 'authority-r4.json'; authority = c.read(authority_path)
        launcher = GUARD.with_name('remote_entry.py')
        self.reg.update(record='DODGE-060', accelerator='T4', authority_path=str(authority_path),
            authority_sha256=c.sha(authority_path), expected_lease=authority['expected_lease'],
            prior_assigned_seconds_upper_bound=authority['prior_assigned_seconds_upper_bound'],
            prior_cost_upper_estimate_CU=authority['prior_cost_upper_estimate_CU'],
            limits=authority['limits'], billing_guard_path=str(GUARD), billing_guard_sha256=c.sha(GUARD),
            exec_script=str(launcher), exec_script_sha256=c.sha(launcher),
            download_remote='/content/dodge-ray060-receipts.tar')
        self.reg['source_pins'].update({str(GUARD):c.sha(GUARD),str(launcher):c.sha(launcher)})
        self.reg['input_pins'][str(authority_path)] = c.sha(authority_path)
        for asset in self.reg['uploads']:
            asset['remote'] = asset['remote'].replace('dodge-ray057','dodge-ray060')

        self.reg.update(schema='dodge_colab_synthetic_registration_v1',
            owner_freeze_path=str(freeze), owner_freeze_sha256=c.sha(freeze),
            empty_pycache=str(self.root / 'cache'), cli_config_path=str(self.root / 'private.json'))
        Path(self.reg['empty_pycache']).mkdir()
        self.reg['source_pins'].update({str(MODULE): c.sha(MODULE), str(c.BASE): c.BASE_SHA})
        self.reg['input_pins'].update({str(freeze): c.sha(freeze),
            self.reg['CPU_420_receipt_path']: self.reg['CPU_420_receipt_sha256']})

    def tearDown(self): self.temp.cleanup()

    def plan(self):
        regpath = self.root / 'registration.json'; regpath.write_text(json.dumps(self.reg))
        review = self.root / 'review.json'
        review.write_text(json.dumps(dict(status='no_blocking_findings', registration_sha256=c.sha(regpath),
            coordinator_source_pins={str(MODULE): c.sha(MODULE), str(c.BASE): c.BASE_SHA})))
        return dict(registration_path=str(regpath), registration_sha256=c.sha(regpath),
                    review_path=str(review), review_sha256=c.sha(review),
                    authority_path=self.reg['authority_path'], authority_sha256=self.reg['authority_sha256'])

    def test_complete_real_frozen_pin_set_validates_without_account_calls(self):
        self.assertEqual(c.validate_plan(self.plan())['accelerator'], 'T4')

    def test_duplicate_upload_or_unregistered_guard_reject(self):
        original = copy.deepcopy(self.reg)
        for mode in ['duplicate', 'guard', 'limits', 'state']:
            self.reg = copy.deepcopy(original)
            if mode == 'duplicate': self.reg['uploads'].append(self.reg['uploads'][0])
            if mode == 'guard': self.reg['billing_guard_sha256'] = '0'*64
            if mode == 'limits': self.reg['limits']['maximum_existing_compute_units'] = 9
            if mode == 'state': self.reg['state_path'] = '/tmp/foreign-ledger.json'
            with self.subTest(mode=mode), self.assertRaises(ValueError): c.validate_plan(self.plan())

    def test_input_drift_and_cache_fault_block_work_but_not_owned_cleanup(self):
        changed = self.root / 'input.txt'; changed.write_text('before')
        self.reg['input_pins'][str(changed)] = c.sha(changed)
        plan = self.plan(); changed.write_text('after')
        with self.assertRaisesRegex(ValueError, 'source/input changed'): c.validate_plan(plan)
        self.assertEqual(c.validate_plan(plan, cleanup=True)['record'], 'DODGE-060')
        del self.reg['input_pins'][str(changed)]
        (Path(self.reg['empty_pycache']) / 'fault').write_text('preserve')
        plan = self.plan()
        with self.assertRaisesRegex(ValueError, 'empty cache'): c.validate_plan(plan)
        self.assertEqual(c.validate_plan(plan, cleanup=True)['record'], 'DODGE-060')

    def test_foreign_review_registration_binding_rejects(self):
        plan = self.plan(); path = Path(plan['review_path']); review = c.read(path)
        review['registration_sha256'] = '0'*64; path.write_text(json.dumps(review))
        plan['review_sha256'] = c.sha(path)
        with self.assertRaisesRegex(ValueError, 'Independent exact review'): c.validate_plan(plan)


class OfficialSDKContractTests(unittest.TestCase):
    def test_actual_SDK_origins_accept_registered_tmp_alias_without_network(self):
        script = '''
import importlib.util, json, socket
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
def forbidden(*args, **kwargs):
    raise AssertionError("Network forbidden in actual SDK snapshot fixture")
socket.create_connection = forbidden
import colab_cli.common
from colab_cli.consumption import CcuInfo
source = Path('learning/experiments/teacher_colab_compat_dispatch_20261031_r4.py')
spec=importlib.util.spec_from_file_location('actual_sdk_fixture',source)
controller=importlib.util.module_from_spec(spec); spec.loader.exec_module(controller)
freeze=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-teacher-ray-geometry-20261030/learning/runs/v2/teacher-ray-colab-cuda-compat-20261031-r2/owner-source-freeze-r1.json')
reg=json.loads(freeze.read_text())
client=SimpleNamespace(colab_domain='https://colab.research.google.com',
    _issue_request=lambda *a,**k:CcuInfo(currentBalance=100.,consumptionRateHourly=0.,assignmentsCount=0),
    list_assignments=lambda:[])
state=SimpleNamespace(client=client,store=SimpleNamespace(get=lambda name:None))
with patch.object(colab_cli.common,'State',return_value=state):
    snapshot=controller.sdk_adapter(reg,None,'snapshot')
assert len(snapshot['cli_loaded_origins']) >= 7
assert snapshot['assignments']==[] and snapshot['session'] is None
print('actual_SDK_tmp_alias_snapshot_passed')
'''
        result = subprocess.run(['/tmp/dodge-colab-cli-20261031-venv/bin/python', '-B', '-c', script],
            capture_output=True, text=True, timeout=15, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                COLAB_CLI_ASSIGN_RETRIES='0', COLAB_CLI_REQUEST_TIMEOUT='15'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'actual_SDK_tmp_alias_snapshot_passed')

    def test_installed_standard_T4_request_matches_default_shape_without_network(self):
        script = '''
import socket
from types import SimpleNamespace
def forbidden(*args, **kwargs):
    raise AssertionError("Network forbidden in SDK request-builder fixture")
socket.create_connection = forbidden
from colab_cli.client import Client, Variant, Accelerator, Shape
import uuid
client = SimpleNamespace(colab_domain='https://colab.research.google.com')
arguments = (client, uuid.UUID('00000000-0000-0000-0000-000000000057'), Variant.GPU, Accelerator.T4)
assert Client._build_assign_url(*arguments, Shape.STANDARD) == Client._build_assign_url(*arguments, None)
print('standard_T4_request_matches_default')
'''
        result = subprocess.run(['/tmp/dodge-colab-cli-20261031-venv/bin/python', '-B', '-c', script],
            capture_output=True, text=True, timeout=15,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'standard_T4_request_matches_default')


class SDKAdapterTests(unittest.TestCase):
    """Provider models are fakes; file claims and secret/session ordering are real."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.output = self.root / 'output'; self.output.mkdir()
        self.nonce = '00000000-0000-0000-0000-000000000057'
        self.statepath = self.root / 'state.json'; self.lease = {'owner': '057'}
        self.statepath.write_text(json.dumps(dict(active_long_campaign=self.lease)))
        self.config = self.root / 'private.json'
        self.reg = dict(expected_lease=self.lease, state_path=str(self.statepath),
                        session_name='owned057', cli_config_path=str(self.config), input_pins={})
        c.save(self.output / 'dispatch.claimed', dict(expected_lease=self.lease, notebook_hash=self.nonce))
        c.save(self.output / 'allocation.claimed', dict(notebook_hash=self.nonce))
        self.assign_calls = []; self.unassign_calls = []; self.sessions = {}; self.fail_store = False
        value = lambda name: types.SimpleNamespace(value=name)
        proxy = types.SimpleNamespace(token='PROXY_SECRET', url='https://proxy.invalid/PRIVATE_SECRET',
                                      expires_at=lambda: None)
        self.response = types.SimpleNamespace(endpoint='ours', accelerator=value('T4'), runtime_proxy_info=proxy)
        def assign(*args, **kwargs): self.assign_calls.append((args, kwargs)); return self.response
        def add(session):
            if self.fail_store: raise OSError('fixture store failure')
            self.sessions[session.name] = session
            self.config.write_text(json.dumps({session.name: vars(session)}))
        store = types.SimpleNamespace(get=lambda name: self.sessions.get(name), add=add,
                                     remove=lambda name: self.sessions.pop(name, None))
        raw = types.SimpleNamespace(model_dump=lambda **kwargs:
            dict(currentBalance=100., consumptionRateHourly=2., assignmentsCount=1))
        listed = types.SimpleNamespace(endpoint='ours', accelerator=value('T4'), runtime_proxy_info=proxy)
        client = types.SimpleNamespace(assign=assign, unassign=lambda endpoint: self.unassign_calls.append(endpoint),
            colab_domain='https://colab.research.google.com', _issue_request=lambda *a, **k: raw,
            list_assignments=lambda: [listed])
        state = types.SimpleNamespace(client=client, store=store)
        def module(name, **items):
            m = types.ModuleType(name)
            for key, item in items.items(): setattr(m, key, item)
            return m
        modules = {'colab_cli': module('colab_cli'),
            'colab_cli.common': module('colab_cli.common', State=lambda: state),
            'colab_cli.auth': module('colab_cli.auth', AuthProvider=types.SimpleNamespace(OAUTH2='oauth2')),
            'colab_cli.client': module('colab_cli.client',
                Accelerator=types.SimpleNamespace(T4=value('T4')), Variant=types.SimpleNamespace(GPU=value('GPU')),
                Shape=types.SimpleNamespace(STANDARD=0)),
            'colab_cli.consumption': module('colab_cli.consumption', CcuInfo=object),
            'colab_cli.state': module('colab_cli.state', SessionState=lambda **kwargs: types.SimpleNamespace(**kwargs))}
        self.modules = patch.dict(sys.modules, modules); self.modules.start()
        self.env = patch.dict(os.environ, COLAB_CLI_ASSIGN_RETRIES='0', COLAB_CLI_REQUEST_TIMEOUT='15')
        self.env.start(); self.umask = os.umask(0o077)

    def tearDown(self):
        os.umask(self.umask); self.env.stop(); self.modules.stop(); self.temp.cleanup()

    def allocate(self):
        return c.sdk_adapter(self.reg, self.output, 'allocate', self.nonce)

    def test_sdk_persists_uuid_and_redacted_endpoint_without_proxy_secrets(self):
        owned = self.allocate()
        self.assertEqual(len(self.assign_calls), 1)
        self.assertEqual(str(self.assign_calls[0][0][0]), self.nonce)
        self.assertEqual(c.read(self.output / 'sdk-allocation.claimed')['notebook_hash'], self.nonce)
        self.assertNotIn('SECRET', json.dumps(owned))
        self.assertNotIn('SECRET', (self.output / 'owned-endpoint.json').read_text())
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)

    def test_sdk_second_call_cannot_allocate_even_if_private_session_entry_is_lost(self):
        self.allocate(); self.sessions.clear()
        with self.assertRaises(FileExistsError): self.allocate()
        self.assertEqual(len(self.assign_calls), 1)

    def test_endpoint_proof_precedes_secret_session_store_failure(self):
        self.fail_store = True
        with self.assertRaises(OSError): self.allocate()
        self.assertEqual(c.read(self.output / 'owned-endpoint.json')['endpoint'], 'ours')
        c.sdk_adapter(self.reg, self.output, 'unassign', endpoint='ours')
        self.assertEqual(self.unassign_calls, ['ours'])

    def test_sdk_unassign_requires_exact_endpoint_proof(self):
        self.allocate()
        with self.assertRaisesRegex(ValueError, 'ownership proof'):
            c.sdk_adapter(self.reg, self.output, 'unassign', endpoint='foreign')
        self.assertEqual(self.unassign_calls, [])

    def test_sdk_cleanup_allowed_after_lease_loss_without_overwriting_new_owner(self):
        self.allocate(); self.statepath.write_text(json.dumps(dict(active_long_campaign={'foreign': True})))
        c.sdk_adapter(self.reg, self.output, 'unassign', endpoint='ours')
        self.assertEqual(self.unassign_calls, ['ours'])
        self.assertEqual(c.read(self.statepath)['active_long_campaign'], {'foreign': True})

    def test_wrong_lease_or_enabled_allocation_retries_prevents_sdk_assignment(self):
        self.statepath.write_text(json.dumps(dict(active_long_campaign=None)))
        with self.assertRaisesRegex(ValueError, 'global compatibility lease'): self.allocate()
        self.assertEqual(self.assign_calls, [])
        self.statepath.write_text(json.dumps(dict(active_long_campaign=self.lease)))
        with patch.dict(os.environ, COLAB_CLI_ASSIGN_RETRIES='3'):
            with self.assertRaisesRegex(ValueError, 'retry/timeout'): self.allocate()
        self.assertEqual(self.assign_calls, [])

    def test_sdk_snapshot_publishes_only_redacted_session_assignment_fields(self):
        self.allocate()
        snapshot = c.sdk_adapter(self.reg, self.output, 'snapshot')
        self.assertNotIn('SECRET', json.dumps(snapshot))
        self.assertEqual(set(snapshot['assignments'][0]), {'endpoint', 'accelerator'})
        self.assertEqual(set(snapshot['session']), {'name', 'endpoint', 'accelerator', 'variant', 'machine_shape'})


if __name__ == '__main__': unittest.main(verbosity=2)
