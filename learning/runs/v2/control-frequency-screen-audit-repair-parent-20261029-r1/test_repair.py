"""Filesystem rejection cases and complete preservation of the reviewed auditor."""
import json
from pathlib import Path
import tempfile
import unittest

import repair_contract as contract


class CacheDispositionTests(unittest.TestCase):
    def test_absence_is_read_only_and_rejects_all_existing_states(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'cache'
            contract.require_absent_cache(path)
            self.assertFalse(path.exists())
            path.mkdir()
            with self.assertRaises(ValueError):
                contract.require_absent_cache(path)
            (path / 'unexpected.pyc').write_bytes(b'preserve')
            with self.assertRaises(ValueError):
                contract.require_absent_cache(path)
            self.assertEqual((path / 'unexpected.pyc').read_bytes(), b'preserve')
            (path / 'unexpected.pyc').unlink()
            path.rmdir()
            path.write_bytes(b'file')
            with self.assertRaises(ValueError):
                contract.require_absent_cache(path)
            path.unlink()
            path.symlink_to(Path(temporary) / 'missing-target')
            with self.assertRaises(ValueError):
                contract.require_absent_cache(path)
            self.assertTrue(path.is_symlink())

    def test_auditor_matches_explicit_source_delta(self):
        delta = json.loads((contract.HERE / 'reviewed-delta.json').read_text())
        original = Path(delta['original_path'])
        self.assertEqual(contract.digest(original), delta['original_sha256'])
        expected = original.read_text()
        for change in delta['replacements']:
            self.assertEqual(expected.count(change['before']), 1)
            expected = expected.replace(change['before'], change['after'])
        self.assertEqual(expected, (contract.HERE / 'accept_saved_screen.py').read_text())

    def test_review_receipt_is_required_and_hash_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path = root / 'plan.json'
            review_path = root / 'review.json'
            plan = dict(independent_review_path=str(review_path), pins={})
            plan_path.write_text(json.dumps(plan))
            review = dict(status='no_blocking_findings', role='independent_source_review',
                          blocking_findings_remaining=0, plan_sha256=contract.digest(plan_path),
                          reviewed_pins={})
            review_path.write_text(json.dumps(review))
            approval = dict(status='accepted_independent_review_of_outcome_blind_cache_disposition',
                            blocking_findings_remaining=0, plan_sha256=contract.digest(plan_path),
                            reviewer_role='independent_source_review', review_path=str(review_path),
                            review_sha256=contract.digest(review_path),
                            pins={str(review_path): contract.digest(review_path)})
            contract.validate_review_approval(approval, plan, plan_path)
            unsigned = {k: v for k, v in approval.items() if k != 'review_path'}
            with self.assertRaises((ValueError, KeyError)):
                contract.validate_review_approval(unsigned, plan, plan_path)
            wrong_role = dict(approval, reviewer_role='self_review')
            with self.assertRaises(ValueError):
                contract.validate_review_approval(wrong_role, plan, plan_path)
            review_path.write_text(json.dumps(dict(review, status='blocked')))
            with self.assertRaises(ValueError):
                contract.validate_review_approval(approval, plan, plan_path)


if __name__ == '__main__':
    unittest.main()
