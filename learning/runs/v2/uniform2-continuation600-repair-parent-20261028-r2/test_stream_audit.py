"""Synthetic CPU-only tests for stream completeness and package audit receipt gates."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]/'uniform2-continuation600-luna-20261028-r2'
sys.path.insert(0, str(PACKAGE))
import audit
import binding as b
import seeds
from audit_segment_streams import validate_events

POOL = list(range(512))


def fixture():
    identity = dict(study_id=b.PRODUCER_STUDY, replica=2, master=123456789)
    reg = dict(parent=dict(expected_identity=dict(seed_vector={'seeds': {'env_master_seed': identity['master']}}),
                           initial_episode_indices=[0]*b.SLOTS),
               exclusion_union=[[1000, 1010]])
    events = []
    starts = [0]*b.SLOTS
    for segment in range(b.SEGMENTS):
        base = segment*b.SEGMENT_UPDATES
        streams, components = seeds.segment_streams(POOL, identity, starts, episodes=8)
        seed_digests, component_digests = seeds.digests(streams, components)
        events.append(dict(kind='segment_initial', segment=segment, global_update_base=base,
                           next_episode_indices=list(starts), slot_stream_sha256=seed_digests,
                           slot_component_sha256=component_digests))
        end = list(starts)
        for slot in range(b.SLOTS):
            episode = starts[slot]+1
            row = dict(slot=slot, episode=episode, seed=streams[slot][episode])
            key = base+1, slot
            events.append(dict(kind='assignments', update=key[0], decision=key[1], rows=[row]))
            events.append(dict(kind='returned_reset', update=key[0], decision=key[1], slots=[slot],
                               startup_frames=b.STARTUP))
            end[slot] = episode+1
            if slot % 2 == 0:
                episode = starts[slot]+2
                row2 = dict(slot=slot, episode=episode, seed=streams[slot][episode])
                key2 = base+2, slot
                events.append(dict(kind='assignments', update=key2[0], decision=key2[1], rows=[row2]))
                events.append(dict(kind='returned_reset', update=key2[0], decision=key2[1], slots=[slot],
                                   startup_frames=b.STARTUP))
                end[slot] = episode+1
        events.append(dict(kind='segment_end', segment=segment, global_update=base+b.SEGMENT_UPDATES,
                           next_episode_indices=list(end), abandoned=[{}]*b.SLOTS))
        starts = end
    return reg, events


class StreamCoverageTests(unittest.TestCase):
    def check(self, reg, events):
        return validate_events(reg, events, POOL, episodes=8)

    def test_complete_varying_per_slot_coverage_passes(self):
        checked = self.check(*fixture())
        self.assertEqual(len(checked), b.SEGMENTS)
        self.assertTrue(all(row['complete_slot_episode_coverage'] for row in checked))

    def test_incomplete_segment_rejected(self):
        reg, events = fixture()
        events = [e for e in events if not (e['kind'] == 'segment_end' and e['segment'] == 4)]
        with self.assertRaises(ValueError): self.check(reg, events)

    def test_missing_assignment_event_rejected(self):
        reg, events = fixture()
        events = [e for e in events if not (e['kind'] == 'assignments' and e['update'] == 1)]
        with self.assertRaises(ValueError): self.check(reg, events)

    def test_missing_assignment_row_rejected(self):
        reg, events = fixture()
        row = next(e for e in events if e['kind'] == 'assignments' and e['update'] == 1)
        row['rows'] = []
        with self.assertRaises(ValueError): self.check(reg, events)

    def test_duplicate_episode_rejected(self):
        reg, events = fixture()
        first = next(e for e in events if e['kind'] == 'assignments' and e['update'] == 1 and e['decision'] == 0)
        second = next(e for e in events if e['kind'] == 'assignments' and e['update'] == 2 and e['decision'] == 0)
        second['rows'][0]['episode'] = first['rows'][0]['episode']
        with self.assertRaises(ValueError): self.check(reg, events)

    def test_extra_episode_rejected(self):
        reg, events = fixture()
        row = next(e for e in events if e['kind'] == 'assignments' and e['update'] == 1)
        row['rows'][0]['episode'] = 7
        with self.assertRaises(ValueError): self.check(reg, events)

    def test_reset_without_matching_assignment_rejected(self):
        reg, events = fixture()
        events = [e for e in events if not (e['kind'] == 'assignments' and e['update'] == 1)]
        with self.assertRaises(ValueError): self.check(reg, events)

    def test_assignment_reset_slot_mismatch_rejected(self):
        reg, events = fixture()
        reset = next(e for e in events if e['kind'] == 'returned_reset' and e['update'] == 1)
        reset['slots'] = [1]
        with self.assertRaises(ValueError): self.check(reg, events)


class ReceiptGateTests(unittest.TestCase):
    def valid_receipt(self):
        segments = [dict(segment=i, resets=4, assignments=4, stream_digests_verified=True,
                         complete_slot_episode_coverage=True, seed_exclusions_verified=True,
                         initial_constructor_assignments_derived=True, initial_constructor_seed_sha256='a'*64)
                    for i in range(b.SEGMENTS)]
        return dict(schema='uniform2_continuation600_stream_audit_v2',
                    status='passed_all_ten_stream_digests_complete_assignments_and_exclusions',
                    registration_sha256='regsha', journal_sha256='journalsha',
                    checker_sha256=b.sha(b.STREAM_AUDITOR), segments=segments,
                    checked_before_main_lease_release=True, evaluation_outcomes_read=False)

    def assert_bad(self, receipt):
        reg = dict(input_pins={str(b.STREAM_AUDITOR.resolve()): b.sha(b.STREAM_AUDITOR)})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'receipt.json'
            path.write_text(json.dumps(receipt))
            with self.assertRaises(ValueError):
                audit.validate_stream_receipt(reg, path, {'seed_assignments': 4*b.SEGMENTS},
                                              'journalsha', 'regsha')

    def test_missing_receipt_rejected(self):
        reg = dict(input_pins={str(b.STREAM_AUDITOR.resolve()): b.sha(b.STREAM_AUDITOR)})
        with self.assertRaises(FileNotFoundError):
            audit.validate_stream_receipt(reg, '/no/such/receipt.json', {'seed_assignments': 40},
                                          'journalsha', 'regsha')

    def test_valid_receipt_passes(self):
        reg = dict(input_pins={str(b.STREAM_AUDITOR.resolve()): b.sha(b.STREAM_AUDITOR)})
        receipt = self.valid_receipt()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'receipt.json'; path.write_text(json.dumps(receipt))
            result = audit.validate_stream_receipt(reg, path, {'seed_assignments': 4*b.SEGMENTS},
                                                   'journalsha', 'regsha')
        self.assertEqual(result['segments'], b.SEGMENTS)

    def test_wrong_registration_journal_checker_hashes_rejected(self):
        for field, value in [('registration_sha256', 'wrong'), ('journal_sha256', 'wrong'),
                             ('checker_sha256', 'wrong')]:
            receipt = self.valid_receipt(); receipt[field] = value
            with self.subTest(field=field): self.assert_bad(receipt)

    def test_incomplete_segments_or_assignments_rejected(self):
        receipt = self.valid_receipt(); receipt['segments'].pop()
        self.assert_bad(receipt)
        receipt = self.valid_receipt(); receipt['segments'][3]['complete_slot_episode_coverage'] = False
        self.assert_bad(receipt)

    def test_accounting_mismatch_rejected(self):
        reg = dict(input_pins={str(b.STREAM_AUDITOR.resolve()): b.sha(b.STREAM_AUDITOR)})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'receipt.json'; path.write_text(json.dumps(self.valid_receipt()))
            with self.assertRaises(ValueError):
                audit.validate_stream_receipt(reg, path, {'seed_assignments': 41}, 'journalsha', 'regsha')


if __name__ == '__main__':
    unittest.main(verbosity=2)
