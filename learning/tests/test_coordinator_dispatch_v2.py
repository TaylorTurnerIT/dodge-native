"""Temporary-ledger tests only: no native games, learner, or live ledger writes."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


MODULE = Path(__file__).resolve().parents[1] / 'experiments/coordinator_dispatch_v2.py'
spec = importlib.util.spec_from_file_location('coordinator_dispatch', MODULE)
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.state = self.root / 'state.json'; self.old = dict(owner='failed051')
        self.new = dict(owner='new053'); self.state.write_text(json.dumps(
            dict(active_long_campaign=self.old, unrelated=dict(retain=[1,2,3]))))

    def tearDown(self):
        self.temp.cleanup()

    def test_exact_non_null_CAS_preserves_unrelated_state(self):
        c.exact_handoff(self.state, self.old, self.new)
        self.assertEqual(c.read(self.state), dict(active_long_campaign=self.new,
            unrelated=dict(retain=[1,2,3])))

    def test_foreign_lease_rejected_without_modification(self):
        original = self.state.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Exact predecessor lease differs'):
            c.exact_handoff(self.state, dict(owner='foreign'), self.new)
        self.assertEqual(self.state.read_bytes(), original)

    def test_null_and_same_owner_transfers_rejected(self):
        original = self.state.read_bytes()
        for old,new in [(None,self.new),(self.old,None),(self.old,self.old)]:
            with self.assertRaisesRegex(ValueError, 'non-null'):
                c.exact_handoff(self.state,old,new)
        self.assertEqual(self.state.read_bytes(),original)

    def test_receipts_cannot_replace_existing_evidence(self):
        f = self.root / 'evidence.json'; c.save(f,dict(original=True))
        before = f.read_bytes()
        with self.assertRaises(FileExistsError): c.save(f,dict(original=False))
        self.assertEqual(f.read_bytes(),before)
        self.assertTrue(Path(str(f)+'.partial').exists())

    def fixture(self):
        reg = dict(record='DODGE-053',expected_lease=self.new)
        disposition = dict(schema='synthetic_failure_fixture',exact_old_lease=self.old,
            state_path=str(self.state),old_campaign_failed=True)
        plan = dict(record='DODGE-053',registration_sha256='r'*64,review_sha256='v'*64,
            dispatch_template=dict(record='DODGE-053',expected_lease=self.new))
        return reg,disposition,plan

    def test_durable_failure_disposition_precedes_exact_handoff(self):
        reg,disposition,plan=self.fixture();directory=self.root/'dispatch'
        original=c.exact_handoff
        def ordered(*args):
            self.assertTrue((directory/'dispatch.claimed').exists())
            receipt=c.read(directory/'failure-disposition.json')
            self.assertTrue(receipt['old_campaign_failed'])
            self.assertEqual(c.read(self.state)['active_long_campaign'],self.old)
            return original(*args)
        with patch.object(c,'QUEUE',self.root),patch.object(c,'validate',return_value=reg), \
             patch.object(c,'failed_predecessor_audit',return_value=disposition), \
             patch.object(c,'exact_handoff',side_effect=ordered):
            result=c.dispatch(plan,directory)
        self.assertEqual(c.read(self.state)['active_long_campaign'],self.new)
        gate=c.read(result['dispatch_path']);handoff=c.read(gate['handoff_path'])
        self.assertTrue(handoff['never_cleared_to_null'])
        self.assertEqual(handoff['failure_disposition_sha256'],gate['failure_disposition_sha256'])
        self.assertEqual(c.sha(result['dispatch_path']),result['dispatch_sha256'])

    def test_failure_after_CAS_keeps_new_lease_and_claim(self):
        reg,disposition,plan=self.fixture();directory=self.root/'dispatch';original=c.save
        def fail_handoff(path,value):
            if Path(path).name=='lease-handoff.json': raise OSError('fixture IO failure')
            return original(path,value)
        with patch.object(c,'QUEUE',self.root),patch.object(c,'validate',return_value=reg), \
             patch.object(c,'failed_predecessor_audit',return_value=disposition), \
             patch.object(c,'save',side_effect=fail_handoff):
            with self.assertRaisesRegex(OSError,'fixture IO failure'):c.dispatch(plan,directory)
        self.assertEqual(c.read(self.state)['active_long_campaign'],self.new)
        self.assertTrue((directory/'dispatch.claimed').exists())
        self.assertEqual(c.read(directory/'first-failure.json')['lease_value'],self.new)
        self.assertFalse((directory/'dispatch.json').exists())

    def test_bad_source_gate_never_claims_or_mutates_lease(self):
        original=self.state.read_bytes();directory=self.root/'dispatch'
        with patch.object(c,'validate',side_effect=ValueError('bad review')):
            with self.assertRaisesRegex(ValueError,'bad review'):c.dispatch({},directory)
        self.assertEqual(self.state.read_bytes(),original)
        self.assertFalse(directory.exists())

    def validation_fixture(self):
        package=self.root/'packet';package.mkdir();(package/'empty-pycache').mkdir()
        authority=self.root/'authority-r2.json'
        c.save(authority,dict(schema='teacher_training_queue_authority_v2',
            limits=dict(AC_required=False),first_screens_only=True,no_claim_or_lease_reset=True))
        source=package/'source.py';source.write_text('unchanged source\n')
        reg=self.root/'registration.json'
        c.save(reg,dict(record='DODGE-053',expected_lease=self.new,package=str(package),
            coordinator_authority_path=str(authority),coordinator_authority_sha256=c.sha(authority),
            jobs=[1,2,3,4],frame_target=11796480,work_seconds=5400,receipt_seconds=180,
            campaign_total_seconds=22320,rss_bytes=6*2**30,mps_bytes=6*2**30,
            source_pins={str(source):c.sha(source)},input_pins={}))
        review=self.root/'review.json';ready=self.root/'ready.json'
        c.save(review,dict(status='no_blocking_findings',registration_sha256=c.sha(reg),
            coordinator_source_pins={str(MODULE.resolve()):c.sha(MODULE)}))
        c.save(ready,dict(status='frozen_training_candidate_requires_independent_review_and_coordinator_handoff',registration_sha256=c.sha(reg)))
        plan=dict(record='DODGE-053')
        for kind,path in [('registration',reg),('review',review),('readiness',ready),('authority',authority)]:
            plan[kind+'_path']=str(path);plan[kind+'_sha256']=c.sha(path)
        plan['dispatch_template']=dict(plan,expected_lease=self.new)
        return plan,package,source

    def test_exact_pins_and_battery_authority_validate(self):
        plan,package,source=self.validation_fixture()
        with patch.object(c,'QUEUE',self.root):
            self.assertEqual(c.validate(plan)['expected_lease'],self.new)
        self.assertFalse((package/'launch.claimed').exists())

    def test_changed_source_cannot_pass_review_binding(self):
        plan,package,source=self.validation_fixture();source.write_text('changed source\n')
        with patch.object(c,'QUEUE',self.root):
            with self.assertRaisesRegex(ValueError,'Successor pin changed'):c.validate(plan)
        self.assertFalse((package/'launch.claimed').exists())

    def test_already_consumed_successor_rejected(self):
        plan,package,source=self.validation_fixture();(package/'attempt.claimed').write_text('preserved')
        with patch.object(c,'QUEUE',self.root):
            with self.assertRaisesRegex(ValueError,'Successor already consumed'):c.validate(plan)
        self.assertEqual((package/'attempt.claimed').read_text(),'preserved')


    def assert_bad_readiness_never_mutates(self, status):
        plan,package,source=self.validation_fixture()
        readiness=c.read(plan['readiness_path'])
        if status is None: readiness.pop('status')
        else: readiness['status']=status
        Path(plan['readiness_path']).write_text(json.dumps(readiness))
        plan['readiness_sha256']=c.sha(plan['readiness_path'])
        plan['dispatch_template']['readiness_sha256']=plan['readiness_sha256']
        original=self.state.read_bytes();directory=self.root/'dispatch'
        with patch.object(c,'QUEUE',self.root):
            with self.assertRaisesRegex(ValueError,'Readiness differs'):
                c.dispatch(plan,directory)
        self.assertEqual(self.state.read_bytes(),original)
        self.assertFalse(directory.exists())
        self.assertFalse((package/'attempt.claimed').exists())

    def test_missing_readiness_status_never_claims_or_handoffs(self):
        self.assert_bad_readiness_never_mutates(None)

    def test_wrong_readiness_status_never_claims_or_handoffs(self):
        self.assert_bad_readiness_never_mutates('not_ready')


if __name__ == '__main__':
    unittest.main(verbosity=2)
