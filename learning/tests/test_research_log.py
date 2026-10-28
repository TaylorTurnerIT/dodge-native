"""Storage invariants for the local research notebook; no learner or native runtime required."""
import copy
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'research_log.py'
SPEC = importlib.util.spec_from_file_location('research_log', SCRIPT)
log = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(log)


class ResearchLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = log.Store(self.root / 'research.sqlite3', initialize=True)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def create(self, **overrides):
        record = dict(id='TEST-1', project='dodge-native', title='Opening reliability',
                      doing='Compare fixed policies.', expected='Q1 improves.', tags=['opening'])
        return self.store.create({**record, **overrides}, reason='Register hypothesis')

    def evidence(self, **overrides):
        return dict(id='result-1', kind='result', label='Measured result', uri='local:result.json', **overrides)

    def test_durable_reopen_and_revision_conflict(self):
        self.create()
        other = log.Store(self.store.path)
        try:
            self.store.update('TEST-1', {'status': 'running'}, expected_revision=1, reason='Start')
            with self.assertRaisesRegex(ValueError, 'Revision conflict'):
                other.update('TEST-1', {'title': 'Stale writer'}, expected_revision=1, reason='Edit')
            self.assertEqual(other.get('TEST-1')['revision'], 2)
            self.assertEqual(other.check()['status'], 'ok')
        finally:
            other.close()

    def test_predictions_freeze_and_history_is_immutable(self):
        self.create(status='running')
        for patch in ({'expected': 'New prediction'}, {'prediction_timing': 'retrospective'}, {'status': 'planned'}):
            with self.assertRaises(ValueError):
                self.store.update('TEST-1', patch, expected_revision=1, reason='Rewrite')
        self.store.update('TEST-1', {'why': 'A new explanation to test.'}, expected_revision=1, reason='Refine hypothesis')
        history = self.store.history('TEST-1')
        self.assertIsNone(history[0]['snapshot']['why'])
        self.assertEqual(len(history), 2)
        for sql in ('DELETE FROM revisions', "UPDATE revisions SET reason='changed'"):
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'append-only'):
                self.store.db.execute(sql)

    def test_result_authority_and_schema_constraints(self):
        self.create()
        for patch in ({'status': 'completed'}, {'actual_kind': 'progress'}, {'actual': 'A prediction masquerading as fact'},
                      {'actual': 'Done', 'actual_kind': 'audited', 'status': 'completed', 'evidence': [self.evidence()]}):
            with self.assertRaises(ValueError):
                self.store.update('TEST-1', patch, expected_revision=1, reason='Invalid result')
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.db.execute("UPDATE experiments SET actual_kind='observed' WHERE id='TEST-1'")
        self.store.update('TEST-1', dict(status='completed', actual='Q1 rose on this cohort.', actual_kind='audited',
                          evidence=[dict(self.evidence(), kind='audit', sha256='a' * 64)]),
                          expected_revision=1, reason='Record audited finding')
        with self.assertRaisesRegex(ValueError, 'reopen'):
            self.store.update('TEST-1', {'status': 'running'}, expected_revision=2, reason='Reopen')

    def test_failed_mutations_roll_back_all_children_and_revisions(self):
        self.create()
        before = self.store.snapshot()
        for metric in ({'value': float('inf')}, {'value': 1, 'evidence_id': 'missing'}):
            measurement = dict(evidence_id='result-1', model='policy', metric='Q1', value=1, unit='frames')
            measurement.update(metric)
            with self.assertRaises(ValueError):
                self.store.update('TEST-1', {'evidence': [self.evidence()], 'measurements': [measurement]},
                                  expected_revision=1, reason='Invalid metric')
            self.assertEqual(before, self.store.snapshot())
        with self.assertRaises(ValueError):
            self.store.update('TEST-1', {'title': 'Will roll back'}, expected_revision=1, reason=' ')
        self.assertEqual(before, self.store.snapshot())

    def test_cross_experiment_evidence_rejected(self):
        self.create(evidence=[self.evidence()])
        with self.assertRaisesRegex(ValueError, 'belong'):
            self.create(id='TEST-2', measurements=[dict(evidence_id='result-1', model='policy', metric='Q1', value=1, unit='frames')])
        self.assertEqual(len(self.store.list()), 1)

    def test_full_text_updates_and_project_isolation(self):
        self.create(title='Quasar original')
        self.create(id='OTHER-1', project='other', title='Quasar other')
        self.assertEqual([r['id'] for r in self.store.search('quasar', project='dodge-native')], ['TEST-1'])
        self.store.update('TEST-1', {'title': 'Pulsar changed'}, expected_revision=1, reason='Rename')
        self.assertEqual(self.store.search('quasar', project='dodge-native'), [])
        self.assertEqual(len(self.store.search('pulsar " OR 1=1 --', project='dodge-native')), 1)
        self.assertEqual(self.store.search('"* :'), [])
        context = self.store.context('dodge-native')
        self.assertIn('hypotheses', context['interpretation'])
        self.assertNotIn('measurements', context['experiments'][0])
        self.store.check()

    def populated_snapshot(self):
        self.create(id='Z-PARENT')
        self.create(id='A-CHILD', parent_id='Z-PARENT')
        self.store.update('A-CHILD', dict(actual='Q1 = 700.', actual_kind='observed', status='completed',
            evidence=[self.evidence()], measurements=[dict(evidence_id='result-1', model='policy', metric='Q1',
            value=700, unit='frames', cohort='development', sample_count=256)]),
            expected_revision=1, reason='Record result')
        self.store.db.execute('INSERT INTO project_context VALUES (?,?,?,?,?)',
            ('dodge-native', 'goal', log.encoded({'metric': 'Q1'}), 'conversation:decision', log.now()))
        return self.store.snapshot()

    def test_snapshot_roundtrip_preserves_history_links_and_context(self):
        snapshot = self.populated_snapshot()
        restored = log.Store(self.root / 'restored.sqlite3', initialize=True)
        try:
            restored.restore(snapshot)
            self.assertEqual(snapshot, restored.snapshot())
            self.assertEqual(restored.check()['experiments'], 2)
            self.assertEqual(len(restored.search('Q1')), 2)
            with self.assertRaisesRegex(ValueError, 'empty'):
                restored.restore(snapshot)
        finally:
            restored.close()

    def test_corrupt_restore_is_atomic(self):
        snapshot = self.populated_snapshot()
        restored = log.Store(self.root / 'restored.sqlite3', initialize=True)
        try:
            for mutation in ('history', 'latest'):
                broken = copy.deepcopy(snapshot)
                if mutation == 'history':
                    broken['experiments'][0]['history'] = []
                else:
                    broken['experiments'][0]['title'] = 'Different from history'
                with self.assertRaises(ValueError):
                    restored.restore(broken)
                self.assertEqual(restored.check()['experiments'], 0)
        finally:
            restored.close()

    def test_backup_and_export(self):
        expected = self.populated_snapshot()
        self.store.export(self.root / 'snapshot.json')
        self.assertEqual(json.loads((self.root / 'snapshot.json').read_text()), expected)
        with self.assertRaisesRegex(ValueError, 'cannot replace'):
            self.store.export(self.store.path)
        self.assertEqual(self.store.snapshot(), expected)
        backup = self.root / 'backup.sqlite3'
        self.store.backup(backup)
        copied = log.Store(backup)
        try:
            self.assertEqual(copied.snapshot(), expected)
            copied.check()
        finally:
            copied.close()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.store.backup(backup)

    def test_cli_bootstrap_and_automatic_snapshot(self):
        source = self.root / 'source.json'
        source.write_text(json.dumps(self.populated_snapshot()))
        path = self.root / 'cli.sqlite3'
        def cli(*args):
            return subprocess.run([sys.executable, '-B', str(SCRIPT), '--db', str(path), *args],
                                  capture_output=True, text=True)
        result = cli('init', '--from-json', str(source))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(path.with_suffix('.json').exists())
        self.assertEqual(json.loads(cli('check').stdout)['experiments'], 2)
        shown = cli('show', 'A-CHILD')
        self.assertIn("What we're doing:", shown.stdout)
        self.assertIn('Q1 = 700.', shown.stdout)
        patch = self.root / 'patch.json'
        patch.write_text(json.dumps({'why': 'A new candidate explanation.'}))
        result = cli('update', 'A-CHILD', '--expected-revision', '2', '--input', str(patch), '--reason', 'Interpret result')
        self.assertEqual(result.returncode, 0, result.stderr)
        exported = json.loads(path.with_suffix('.json').read_text())
        self.assertEqual(exported['experiments'][0]['revision'], 3)


if __name__ == '__main__':
    unittest.main()
