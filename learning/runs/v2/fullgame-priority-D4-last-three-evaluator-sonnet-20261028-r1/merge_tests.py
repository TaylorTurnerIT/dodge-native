"""CPU fake tests for the offline six-model merge: synthetic parts and producers in tmp dirs only.

No Torch/native import, no model, no checkpoint deserialization, no real D4 outcome is read.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import binding as b
import build_registration as builder
import comparison
import merge
import paired_statistics as stats
from tests import ProducerWorld, row

DELTAS = {1: 5, 2: 10, 3: 30}          # priority-minus-uniform shift per matched pair (constant over seeds)


def base_alive(replica, i):
    return 50+((i*37+replica*131) % 2500)


def policy_rows(policy_id, tamper=None):
    replica = int(policy_id.split('-')[1]); delta = DELTAS[replica] if policy_id.endswith('opening_priority') else 0
    causes = ('normal_enemy', 'kamikaze_enemy', 'kamikaze_explosion', 'static_pattern_rect', 'moving_pattern_rect')
    rows = [row(i, base_alive(replica, i)+delta, causes[(i+replica) % 5]) for i in range(1024)]
    if tamper:
        tamper(rows)
    return rows


def write(path, value):
    Path(path).write_text(json.dumps(value))


class Study:
    """Two audited parts over six fake producers; mutate attributes before build() to break one property."""

    def __init__(self, tmp):
        self.tmp = Path(tmp); self.c = b.contracts()
        self.worlds = {}
        for replica in (1, 2, 3):
            for arm in b.ARMS:
                self.worlds[f'replica-{replica}-{arm}'] = ProducerWorld(tmp, replica=replica, arm=arm).write()
        self.tamper_rows = {}; self.stored_edit = None; self.reg_edit = {}; self.last_audit_status = merge.PART_AUDIT_STATUS
        self.skip_last_audit = False; self.last_staging_edit = None

    def policy(self, name):
        return builder.policy_entry(self.worlds[name].layout(), self.c)[0]

    def intervals(self, rows, ids, pair, label):
        with mock.patch.object(b, 'POLICIES', ids), mock.patch.object(b, 'PRIMARY_PAIR', pair):
            value = stats.paired_intervals({k: rows[k] for k in ids}, b.BOOTSTRAP)
        comp = value['comparisons']; comp[label] = comp.pop('replica-3-priority_minus_uniform')
        return value

    def part(self, name, ids, pair, label, run_id, token, extra_reg, audit_status=None):
        d = self.tmp/name; out = d/'worker-output'; ctl = d/'dispatch'/run_id
        out.mkdir(parents=True); ctl.mkdir(parents=True)
        (d/'x.py').write_text(f'x={name!r}\n'); write(d/'source-manifest.json', dict(files={'x.py': b.sha(d/'x.py')}))
        policies = [self.policy(n) for n in ids]
        reg = dict(schema='fake', status='parent_registered', run_id=run_id, source_manifest_sha256=b.sha(d/'source-manifest.json'),
            study_id=b.STUDY, backend='mps', backend_pins=b.BACKEND_PINS, evaluator_source=str(b.SOURCE),
            runtime_root=str(b.SOURCE/'runtime'), runtime_manifest_sha256=b.RUNTIME_SHA,
            input_manifest_sha256=b.sha(b.SOURCE/'input-manifest.json'), runtime_versions=dict(python='3.12.15'),
            seeds=b.SEEDS, cohort=dict(name='D4', range=list(b.D4), count=1024, d5_range=list(b.D5), d5_state='unopened'),
            exclusion_union=[list(b.D4), list(b.D5)], evaluation_rng_seed=b.EVAL_RNG_SEED, bootstrap=b.BOOTSTRAP,
            semantics=b.SEMANTICS, limits=dict(work_seconds=7352), interpreter='/py', provenance=b.PROVENANCE,
            cohort_state='reserved_parent_approved', history_state='freshness_parent_approved', reservation_state='parent_reserved',
            policies=policies, expected_lease=dict(owner_token=token), staging=extra_reg)
        reg.update(self.reg_edit.get(name, {}))
        write(d/'registration-final.json', reg); reg_sha = b.sha(d/'registration-final.json')
        rows = {n: policy_rows(n, self.tamper_rows.get(n)) for n in ids}
        events = []
        for n in ids:
            receipt = dict(policy_id=n, registration_sha256=reg_sha, checkpoint_sha256=self.policy(n)['checkpoint_sha256'],
                action_mode='sampled_categorical', normal_start=True, cutoff_enabled=False, promoted=False,
                rows=rows[n], summary=comparison.summarize(policy_rows(n), b.SEEDS))
            write(out/(n+'.json'), receipt)
            write(out/(n+'.claim'), dict(policy_id=n, registration_sha256=reg_sha, checkpoint_sha256=receipt['checkpoint_sha256']))
            for i in range(1024):
                events.append(json.dumps(dict(kind='evaluation_constructor', policy_id=n, episode_index=i), separators=(',', ':')))
                events.append(json.dumps(dict(kind='evaluation_step', policy_id=n, episode_index=i), separators=(',', ':')))
                events.append(json.dumps(dict(kind='evaluation_completed', policy_id=n, row={}), separators=(',', ':')))
        (out/'evaluation-events.jsonl').write_text('\n'.join(events)+'\n')
        (out/'resources.jsonl').write_text('{}\n')
        stored = dict(policies={n: comparison.summarize(policy_rows(n), b.SEEDS) for n in ids},
                      paired_conditional_seed_intervals=self.intervals({n: policy_rows(n) for n in ids}, tuple(ids), pair, label))
        if self.stored_edit and name == 'last':
            self.stored_edit(stored)
        write(out/'comparison.json', stored)
        write(out/'worker-result.json', dict(status='completed', run_id=run_id, registration_sha256=reg_sha,
            completed_policies=list(ids), rows_completed=3072, comparison_sha256=b.sha(out/'comparison.json'), constructors=3072,
            automatic_selection=False, promoted=False, training_eligible=False))
        write(ctl/'artifact-manifest.json', {p.name: b.sha(p) for p in out.iterdir() if p.is_file()})
        if name == 'last' and self.skip_last_audit:
            return d
        audit = dict(status=audit_status or merge.PART_AUDIT_STATUS, registration_sha256=reg_sha,
            source_manifest_sha256=reg['source_manifest_sha256'], raw_worker_exit_code=0, raw_observer_exit_code=0,
            comparison_sha256=b.sha(out/'comparison.json'), intervals_independently_recomputed=True,
            main_training_state_written=False, d5_opened=False, automatic_selection=False, promoted=False,
            training_eligible=False, accounting=dict(completed_episodes=3072, constructors=3072, native_steps=10**6,
                                                     raw_frames_including_startup=4*10**6))
        write(d/'parent-terminal-audit.json', audit); audit_sha = b.sha(d/'parent-terminal-audit.json')
        write(d/'lease-release.json', dict(status='exact_lease_cleared_after_durable_parent_audit', audit_sha256=audit_sha))
        write(d/'evaluation-resource-ledger.json', dict(active_evaluation_lease=None, terminal_complete=True, d5_opened=False,
            main_state_written=False, parent_audit_sha256=audit_sha, run_id=run_id))
        write(d/'execution-exit.json', dict(raw_observer_exit_code=0, observer_directly_reaped=True, registration_sha256=reg_sha))
        write(d/'parent-execution.json', dict(registration_sha256=reg_sha))
        return d

    def build(self):
        first_ids = b.FIRST_PART_POLICIES
        later = [dict(id=n, checkpoint_path=self.policy(n)['checkpoint_path']) for n in b.POLICIES]
        first = self.part('first', first_ids, ('replica-1-opening_priority', 'replica-1-uniform'), 'replica-1-priority_minus_uniform',
                          'first-run', 'a'*32, dict(later_three=later, later_three_required_by_this_run=False))
        self.first_pins = dict(source_manifest_sha256=b.sha(first/'source-manifest.json'),
            registration_final_sha256=b.sha(first/'registration-final.json'),
            comparison_sha256=b.sha(first/'worker-output/comparison.json'))
        staging = dict(first_part=dict(registration_final_sha256=self.first_pins['registration_final_sha256'],
            comparison_sha256=self.first_pins['comparison_sha256'], parent_terminal_audit_sha256=b.sha(first/'parent-terminal-audit.json'),
            source_manifest_sha256=self.first_pins['source_manifest_sha256']), first_part_re_evaluated_by_this_run=False)
        if self.last_staging_edit:
            self.last_staging_edit(staging)
        last = self.part('last', b.POLICIES, ('replica-3-opening_priority', 'replica-3-uniform'), 'replica-3-priority_minus_uniform',
                         'last-run', 'b'*32, staging, audit_status=self.last_audit_status)
        return first, last

    def merge(self, **kw):
        first, last = self.build()
        return merge.merge(first, last, first_pins=self.first_pins, reproduce_identity=True, **kw)


class MergeTests(unittest.TestCase):
    def study(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        return Study(tmp.name)

    def test_six_policy_identity_seed_settings_merge_and_labels(self):
        s = self.study(); report = s.merge()
        self.assertEqual(list(report['policies']), list(b.SIX_POLICIES))
        self.assertEqual(len({v['producer']['checkpoint_sha256'] for v in report['policies'].values()}), 6)
        self.assertEqual(len({v['producer']['run_id'] for v in report['policies'].values()}), 6)
        for name, value in report['policies'].items():
            self.assertEqual(value['summary'], comparison.summarize(policy_rows(name), b.SEEDS))
            self.assertEqual(value['summary']['episodes'], 1024)
            self.assertEqual(set(value['summary']['performance']), {'Worst', 'Q1', 'Mean', 'Q4', 'Best'})
            self.assertEqual(set(value['summary']['milestones']), {str(h) for h in (1000, 2000, 4000, 8000, 12000, 18000)})
            self.assertEqual(sum(value['summary']['death_causes'].values())+value['summary']['caps'], 1024)
        self.assertEqual(report['settings'], dict(semantics=b.SEMANTICS, evaluation_rng_seed=2026102802, bootstrap=b.BOOTSTRAP))
        self.assertEqual(report['cohort']['range'], list(b.D4)); self.assertEqual(report['cohort']['d5_state'], 'unopened')
        self.assertEqual(report['cohort']['count'], 1024)
        self.assertEqual((report['parts']['first']['policies'], report['parts']['last']['policies']),
                         (list(b.FIRST_PART_POLICIES), list(b.POLICIES)))
        for flag in ('launch_authority', 'automatic_selection', 'promoted', 'd5_opened', 'new_native_or_model_evaluation'):
            self.assertIs(report[flag], False)

    def test_pairs_and_average_are_exact_shifts(self):
        report = merge_report = self.study().merge()
        for k in (1, 2, 3):
            pair = report['pairs'][f'pair_{k}']
            self.assertEqual((pair['minuend'], pair['subtrahend']), (f'replica-{k}-opening_priority', f'replica-{k}-uniform'))
            self.assertTrue(all(v == DELTAS[k] for v in pair['metric_differences'].values()), pair['metric_differences'])
            label = f'replica-{k}-priority_minus_uniform'
            iv = report['conditional_paired_seed_intervals']['comparisons'][label]['performance']
            self.assertTrue(all(i['low'] == i['high'] == DELTAS[k] for i in iv.values()))   # constant shift: no seed variation
        avg = report['pair_average']
        self.assertEqual(avg['role'], 'descriptive_average_of_three_matched_pairs'); self.assertEqual(avg['pairs'], 3)
        self.assertTrue(all(v == 15 for v in avg['metric_differences'].values()))
        iv = report['conditional_paired_seed_intervals']['comparisons'][merge.AVERAGE]['performance']
        self.assertTrue(all(i['low'] == i['high'] == 15 for i in iv.values()))
        for h in avg['milestone_rate_differences']:
            rates = [report['pairs'][f'pair_{k}']['milestone_rate_differences'][h] for k in (1, 2, 3)]
            self.assertAlmostEqual(avg['milestone_rate_differences'][h], sum(rates)/3)
        self.assertEqual(set(report['conditional_paired_seed_intervals']['comparisons']),
                         {'replica-1-priority_minus_uniform', 'replica-2-priority_minus_uniform',
                          'replica-3-priority_minus_uniform', merge.AVERAGE})

    def test_uncertainty_is_conditional_not_training_population(self):
        u = self.study().merge()['uncertainty']
        self.assertEqual(u['kind'], 'conditional_evaluation_seed_resampling_only')
        self.assertIs(u['training_population_inference'], False)
        self.assertEqual((u['training_replicas'], u['training_runs'], u['evaluation_seeds'], u['evaluation_episodes_total']), (3, 6, 1024, 6144))
        self.assertIn('not 3072', u['note']); self.assertIn('not training replicates', u['note'])
        self.assertEqual(u['resampling_unit'], 'paired_evaluation_seed')
        report = self.study().merge()
        self.assertEqual(report['conditional_paired_seed_intervals']['uncertainty'], u)
        self.assertEqual(report['conditional_paired_seed_intervals']['contract'], b.BOOTSTRAP)
        self.assertNotIn('p_value', json.dumps(report))
        self.assertIn('training-population inference is not made', report['interpretation'])

    def test_inert_until_both_audits_accepted(self):
        s = self.study(); s.skip_last_audit = True
        with self.assertRaises(merge.NotReady):
            s.merge()
        s = self.study(); s.last_audit_status = 'failed_partial'
        with self.assertRaises(merge.NotReady):
            s.merge()
        with self.assertRaises(merge.NotReady):                  # real package: audit absent while training/eval pending
            merge.verify_part(b.HERE, b.POLICIES)

    def test_wrong_first_part_pins_refused(self):
        s = self.study(); first, last = s.build()
        with self.assertRaisesRegex(ValueError, 'pinned accepted hashes'):
            merge.merge(first, last, first_pins=dict(s.first_pins, comparison_sha256='0'*64))

    def test_fixed_settings_must_match_across_parts(self):
        cohort = dict(name='D4', range=list(b.D4), count=1024, d5_range=list(b.D5), d5_state='unopened')
        edits = {'seeds': dict(seeds=list(reversed(b.SEEDS))),
                 'rng': dict(evaluation_rng_seed=1),
                 'semantics': dict(semantics=dict(b.SEMANTICS, action_repeat=2)),
                 'bootstrap': dict(bootstrap=dict(b.BOOTSTRAP, draws=10)),
                 'runtime': dict(runtime_manifest_sha256='9'*64),
                 'cohort': dict(cohort=dict(cohort, count=2048)),
                 'backend pins': dict(backend_pins=dict(b.BACKEND_PINS, inference_device='cpu'))}
        for label, edit in edits.items():
            with self.subTest(label):
                s = self.study(); s.reg_edit['last'] = edit
                with self.assertRaisesRegex(ValueError, 'differ'):
                    s.merge()

    def test_overlap_duplicate_models_and_reevaluation_refused(self):
        s = self.study(); first, last = s.build()
        a = merge.verify_part(first, b.FIRST_PART_POLICIES); z = merge.verify_part(last, b.POLICIES)
        merge.cross_check(a, z)                                      # baseline passes
        cases = {
            'duplicate checkpoint': lambda a, z: z['producers'][0].update(checkpoint_sha256=a['producers'][0]['checkpoint_sha256']),
            'duplicate producer run': lambda a, z: z['producers'][1].update(run_id=a['producers'][1]['run_id']),
            'same eval run id': lambda a, z: z['reg'].update(run_id=a['reg']['run_id']),
            'same lease token': lambda a, z: z['reg'].update(expected_lease=dict(a['reg']['expected_lease'])),
            'reevaluates first model': lambda a, z: z['reg'].update(policies=[a['reg']['policies'][0]]+z['reg']['policies'][1:]),
            'first part not pinned': lambda a, z: z['reg']['staging']['first_part'].update(comparison_sha256='1'*64),
            'first claims re-eval': lambda a, z: z['reg']['staging'].update(first_part_re_evaluated_by_this_run=True),
            'first did not predeclare last': lambda a, z: a['reg']['staging'].update(later_three=a['reg']['staging']['later_three'][:2]),
            'wrong parent checkpoint': lambda a, z: z['producers'][2].update(parent_checkpoint_sha256='2'*64),
            'missing arm': lambda a, z: z['producers'][2].update(arm='uniform'),
            'D5 opened': lambda a, z: z['reg']['cohort'].update(d5_state='opened'),
        }
        for label, edit in cases.items():
            with self.subTest(label):
                a2, z2 = copy.deepcopy(a), copy.deepcopy(z); edit(a2, z2)
                with self.assertRaises(ValueError):
                    merge.cross_check(a2, z2)

    def test_per_model_rows_must_be_exact_1024_seed_rows(self):
        def reseed(rows):
            rows[5], rows[6] = rows[6], rows[5]                      # reordered seeds
        def drop(rows):
            del rows[-1]
        for label, tamper in (('reordered', reseed), ('dropped', drop)):
            with self.subTest(label):
                s = self.study(); s.tamper_rows['replica-3-uniform'] = tamper
                with self.assertRaisesRegex(ValueError, 'exact seed rows'):
                    s.merge()

    def test_producer_chain_drift_refused(self):
        s = self.study(); first, last = s.build()
        Path(s.policy('replica-2-opening_priority')['checkpoint_path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'pin drift|bytes drift'):
            merge.verify_part(last, b.POLICIES)

    def test_stored_part_interval_mismatch_refused(self):
        def edit(stored):
            comp = stored['paired_conditional_seed_intervals']['comparisons']['replica-3-priority_minus_uniform']
            comp['performance']['Mean']['low'] += 1
        s = self.study(); s.stored_edit = edit
        with self.assertRaisesRegex(ValueError, 'differs from the part audited interval'):
            s.merge()

    def test_output_is_exclusive_and_inert(self):
        s = self.study(); report = s.merge()
        path = Path(s.tmp)/'six-model-merge.json'
        b.save(path, report)
        with self.assertRaises(FileExistsError):
            b.save(path, report)
        self.assertEqual(b.read(path)['schema'], 'fullgame_priority_d4_six_model_merge_v1')
        self.assertIs(b.read(path)['launch_authority'], False)


if __name__ == '__main__':
    unittest.main(verbosity=1)
