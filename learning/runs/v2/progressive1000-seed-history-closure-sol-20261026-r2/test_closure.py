"""Independent stdlib arithmetic/provenance controls; no project runtime imports."""
import hashlib
import json
from pathlib import Path
import unittest

import close_history as audit
import seed_controls as copied

HERE=Path(__file__).resolve().parent

def load(name):
    return json.loads((HERE/name).read_bytes())

class ClosureControls(unittest.TestCase):
    def test_independent_derivation_against_76_logged_rust_references(self):
        refs=load('history-reconstruction.json')['reference_vectors']
        self.assertEqual(len(refs),76)
        for row in refs:
            self.assertEqual(audit.independent_seed(row['run_master_seed'],row['slot'],row['episode']),
                             (row['counter'],row['actual_seed']))

    def test_early_B_only_algorithm_against_16_original_rust_vectors(self):
        path=audit.RUNS/'milestone2-wrapper-r1/trajectory.json'
        obj=json.loads(path.read_bytes())
        self.assertEqual(len(obj['seed_vectors']),16)
        for row in obj['seed_vectors']:
            self.assertEqual(audit.independent_seed(row['run'],row['slot'],row['episode'],((0xB0000000,0xB00003E7),)),
                             (row['counter'],row['actual_seed']))

    def test_full_original_journal_replay_has_no_unmatched_records(self):
        check=load('cohort-collision-check.json')
        self.assertEqual(check['journal_derivation_mismatches'],[])
        self.assertEqual(check['original_training_observed_seed_count'],70301)
        self.assertEqual(len(load('campaign-closure.json')),19)

    def test_terminal_bounds_cover_failed_reset_endpoint_and_offsets(self):
        for run in load('campaign-closure.json'):
            starts=run['initial_episode_indices']
            ends=run['possible_inclusive_episode_end']
            last=run['maximum_observed_own_episode_indices']
            self.assertEqual(len(starts),64)
            self.assertEqual(ends,[x+1 for x in last])
            self.assertTrue(all(a<=b for a,b in zip(starts,last)))
            if run['actual_final_resume_episode_indices'] is not None:
                self.assertTrue(all(e>=n for e,n in zip(ends,run['actual_final_resume_episode_indices'])))
        # A failed reset can mutate index 18 while last successful row says 17.
        # A bound ending at the successful row would miss the attempted seed.
        current=17
        attempted=current+1
        self.assertNotIn(attempted,range(current+1))
        self.assertIn(attempted,range(current+2))

    def test_unused_prefix_is_preserved_and_not_called_consumed(self):
        row=load('97593849-reconciliation.json')
        self.assertEqual(audit.independent_seed(4200000000,44,48),(0,97593849))
        self.assertEqual(row['actual_registered_construction_start_episode_slot44'],262)
        self.assertFalse(row['historical_observed'])
        self.assertFalse(row['in_tight_known_attempt_coverage'])
        self.assertTrue(row['in_retained_R1_zero_origin_envelope'])
        self.assertIn(97593849,load('merged-conservative-seeds.json')['sorted_unique_seed_values'])

    def test_exact_proposal_pins_unchanged(self):
        for name,expected in [('seed-vectors.json','698557ed337cf795c1e587ca325a7a3d2645391837b0df18d8857987e634febf'),
                              ('cohort.json','dd0d28697823eb3d3171789befb46da6f09b928f89328b3c91cb69a353104f45')]:
            self.assertEqual(hashlib.sha256((HERE/name).read_bytes()).hexdigest(),expected)

    def test_all_1096_paths_accounted_without_conflating_files_and_campaigns(self):
        paths=load('r1-unresolved-path-closure.json')['paths']
        self.assertEqual(len(paths),1096)
        self.assertEqual(len({r['path'] for r in paths}),1096)
        self.assertEqual(sum(r['status'].startswith('unresolved') for r in paths),122)
        self.assertTrue(all(r['input_sha256'] for r in paths if r['status']!='unresolved_seed_metadata_only_needed'))
        self.assertTrue(all(r['reason_or_needed_action'] for r in paths))

    def test_nested_journals_excluded_only_by_actual_byte_proof(self):
        report=load('nested-journal-proof.json')
        self.assertEqual(report['counts'],{'empty_no_seed_content':837,'exact_ancestor_copy':2})
        for row in report['paths']:
            if row['classification']=='empty_no_seed_content':
                self.assertEqual(row['bytes'],0)
                self.assertEqual(row['sha256'],hashlib.sha256(b'').hexdigest())
            else:
                self.assertEqual(row['sha256'],hashlib.sha256((audit.ROOT/row['identical_original']).read_bytes()).hexdigest())

    def test_six_directories_and_observer_duplicate_receipts(self):
        self.assertEqual(len(load('six-directory-closure.json')),6)
        for n in (1,2):
            original=audit.RUNS/f'critic-diagnostic-D2-20261025-r{n}/worker-result.json'
            observer=audit.RUNS/f'critic-diagnostic-execution-observer-20261025-r{n}/worker-result.json'
            self.assertEqual(original.read_bytes(),observer.read_bytes())

    def test_d3_no_attempt_is_scoped_to_registered_M3_campaign(self):
        row=load('d3-no-attempt.json')
        self.assertEqual(row['registered_master'],5562881586070242563)
        self.assertTrue(row['original_closeout_status'].startswith('not_started'))
        self.assertEqual(row['matching_D3_run_freeze_execution_paths'],[])
        self.assertIn('No attempt for the registered M3 D3 campaign',row['conclusion'])

    def test_merged_coverage_superset_and_cohort_collision_detector(self):
        merged=set(load('merged-conservative-seeds.json')['sorted_unique_seed_values'])
        old=set(load('observed-seeds.json')['real_observed_sorted_unique_seeds'])
        new=set(load('additional-observed-seeds.json')['new_sorted_unique_seed_values'])
        self.assertTrue(old|new<=merged)
        self.assertEqual(len(old|new),87579)
        cohort=set(range(0xD3000000,0xD3000400))
        self.assertEqual(merged&cohort,set())
        self.assertEqual((merged|{0xD3000007})&cohort,{0xD3000007})
        self.assertTrue(load('cohort-collision-check.json')['proposal_retained'])

    def test_no_freshness_or_qualification_isolation_approval(self):
        self.assertFalse(load('cohort-collision-check.json')['freshness_approval'])
        self.assertFalse(load('cohort-collision-check.json')['cohort_reservation'])
        self.assertFalse(load('boundary-incident.json')['qualification_content_isolation_passed'])
        self.assertTrue(load('boundary-incident.json')['excluded_from_seed_collision_evidence'])

if __name__=='__main__':unittest.main(verbosity=2)
