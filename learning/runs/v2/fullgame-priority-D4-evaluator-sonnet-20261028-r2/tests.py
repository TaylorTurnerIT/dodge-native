"""CPU fake tests: synthetic rows and tmp fixtures only; no Torch/native import, model, seed, cohort or checkpoint use."""
from __future__ import annotations
import copy
import hashlib
import io
import json
import os
import platform
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

import binding as b
import build_registration as builder
import comparison
import finalize_registration
import paired_statistics as stats
import terminal
import audit
import launch
import observe
import worker

CAUSES = ('normal_enemy', 'kamikaze_enemy', 'kamikaze_explosion', 'static_pattern_rect', 'moving_pattern_rect')


def row(index=0, alive=3, cause='normal_enemy', truncated=False):
    contacts = dict.fromkeys(('normal_enemy', 'kamikaze_enemy', 'kamikaze_explosion', 'static_pattern_rect',
                              'moving_pattern_rect', 'unknown'), 0)
    if truncated:
        return dict(episode_index=index, seed=b.SEEDS[index], score_raw_fixed=0, score=0.0, alive_frames=18000,
            gameplay_frames=18000, startup_frames=13, objective_return=180.0, score_delta_sum_raw_fixed=0,
            terminated=False, truncated=True, death_cause=None, fatal_gameplay_frame=None,
            death_observed_lethal_contacts=None)
    contacts[cause] = 1
    return dict(episode_index=index, seed=b.SEEDS[index], score_raw_fixed=0, score=0.0, alive_frames=alive,
        gameplay_frames=alive+1, startup_frames=13, objective_return=alive/100-5, score_delta_sum_raw_fixed=0,
        terminated=True, truncated=False, death_cause=cause, fatal_gameplay_frame=alive+1,
        death_observed_lethal_contacts=contacts)


def frames_split(total):
    steps = []
    while total > 0:
        steps.append(min(4, total)); total -= steps[-1]
    return steps


class Cohort(unittest.TestCase):
    def test_d4_identity_and_d5_unopened(self):
        self.assertEqual((b.SEEDS[0], b.SEEDS[-1], len(set(b.SEEDS))), (0xD4000000, 0xD40003FF, 1024))
        self.assertFalse(any(b.D5[0] <= s <= b.D5[1] for s in b.SEEDS))
        registry = b.check_cohort()
        self.assertEqual(registry['future_evaluation_ranges'], {'D4': list(b.D4), 'D5': list(b.D5)})

    def test_provenance_is_bounded_not_universal(self):
        self.assertEqual(b.PROVENANCE['historical_file_roles_unresolved'], 122)
        self.assertIs(b.PROVENANCE['universal_workspace_nonuse_claim'], False)
        self.assertIs(b.PROVENANCE['live_ledger_pinned_as_immutable_history'], False)

    def test_predeclared_layout_matches_remaining_index(self):
        index = b.read(b.REMAIN_HOME/'registration-index-proposal.json')
        expected = {run['run_id'] for run in index['runs']}|{index['first_run_not_included']}
        layouts = b.predeclared_layouts()
        self.assertEqual({l['run_id'] for l in layouts}, expected)
        self.assertEqual([l['policy_id'] for l in layouts], list(b.PRODUCER_POLICIES))
        for l in layouts:
            self.assertTrue(l['checkpoint_path'].endswith('/worker-output/checkpoint-global-060-integrity.pt'))
            self.assertEqual(l['sidecar_path'], l['checkpoint_path']+'.json')
        self.assertTrue(layouts[0]['home'].startswith(str(b.FIRST_HOME)))
        self.assertTrue(all(l['home'].startswith(str(b.REMAIN_HOME)) for l in layouts[1:]))

    def test_plan_file_agrees_with_code(self):
        plan = b.read(b.HERE/'policy-plan.json')
        self.assertIs(plan['launch_authority'], False)
        self.assertEqual([p['id'] for p in plan['policies']], list(b.POLICIES))
        self.assertEqual([p['checkpoint_path'] for p in plan['policies'][:6]],
                         [l['checkpoint_path'] for l in b.predeclared_layouts()])
        self.assertEqual(plan['cohort']['range'], list(b.D4)); self.assertEqual(plan['evaluation_rng_seed'], b.EVAL_RNG_SEED)
        prior = plan['limits']['prior_cost_basis']
        self.assertEqual(plan['limits']['work_seconds_projected'],
                         b.projected_work_seconds(prior['elapsed_seconds'], prior['raw_frames']))
        self.assertEqual(plan['limits']['raw_frames'], b.RAW_CAP)
        self.assertEqual(plan['limits']['total_seconds_projected'], b.total_seconds(plan['limits']['work_seconds_projected']))
        self.assertEqual(plan['limits']['postflight_seconds'], b.POSTFLIGHT_SECONDS)
        self.assertEqual(plan['evaluation_run_id'], b.EVAL_RUN_ID); self.assertTrue(b.EVAL_RUN_ID.endswith('-r2'))


class Budgets(unittest.TestCase):
    def test_arithmetic_covers_registered_7x1024(self):
        self.assertEqual(b.EPISODES, 7*1024)
        self.assertEqual(b.RAW_CAP, 7*1024*(18000+13)); self.assertEqual(b.STEP_CAP, 7*1024*18000)

    def good(self):
        return dict(work_seconds=100, total_seconds=b.total_seconds(100), cleanup_seconds=10, rss_bytes=b.CAP, mps_bytes=b.CAP,
                    raw_frames=b.RAW_CAP, constructors=b.EPISODES, native_steps=b.STEP_CAP, resets=0, retries=0)

    def test_limits(self):
        b.validate_limits(self.good())
        for key in self.good():
            if key == 'work_seconds':
                continue
            bad = self.good(); bad[key] += 1
            with self.subTest(key=key), self.assertRaises(ValueError):
                b.validate_limits(bad)
        bad = self.good(); del bad['constructors']
        with self.assertRaises(ValueError):
            b.validate_limits(bad)

    def test_wall_projection(self):
        self.assertEqual(b.projected_work_seconds(684.9216058750171, 15487746), 17141)
        self.assertLessEqual(17141, 86400)

    def test_postflight_allowance_is_separate_from_work_and_cleanup(self):
        self.assertEqual((b.CLEANUP_SECONDS, b.POSTFLIGHT_SECONDS), (10, 120))
        self.assertEqual(b.total_seconds(17141), 17141+10+120)
        # Allowance covers the prior observed non-worker overhead scaled to the raw ceiling, with margin.
        scaled = (694.3214253749466-684.9216058750171)*b.RAW_CAP/15487746
        self.assertLess(scaled, b.POSTFLIGHT_SECONDS); self.assertGreater(b.POSTFLIGHT_SECONDS/scaled, 1.5)
        good = self.good(); b.validate_limits(good)
        for total in (good['work_seconds']+10, good['work_seconds']+10+119, good['work_seconds']+10+121):
            with self.subTest(total=total), self.assertRaises(ValueError):
                b.validate_limits(dict(good, total_seconds=total))
        with self.assertRaises(ValueError):
            b.validate_limits(dict(good, cleanup_seconds=130))

    def reg(self, **limits):
        value = dict(self.good(), **limits)
        return dict(limits=value, expected_lease={'x': 1}, state_path=None)

    def guard(self, tmp, **limits):
        reg = self.reg(**limits)
        state = Path(tmp)/'state.json'; state.write_text(json.dumps(dict(active_long_campaign={'x': 1})))
        reg['state_path'] = str(state)
        torch = mock.Mock(); torch.mps.driver_allocated_memory.return_value = 1024
        return worker.Guard(reg, worker.time.monotonic(), torch, io.StringIO(), io.StringIO()), torch

    def test_guard_counts_and_enforces_independently(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(b, 'HERE', Path(tmp)):
            guard, _ = self.guard(tmp, constructors=2)
            ctor = lambda i: dict(kind='evaluation_constructor', episode_index=i, info=dict(startup_frames=13, seed=dict(actual_seed=b.SEEDS[i])))
            guard.journal('p', ctor(0)); guard.journal('p', ctor(1))
            self.assertEqual((guard.constructors, guard.raw), (2, 26))
            with self.assertRaisesRegex(ValueError, 'constructor'):
                guard.journal('p', ctor(2))
            guard, _ = self.guard(tmp, native_steps=1)
            step = dict(kind='evaluation_step', episode_index=0, elapsed_raw_frames=4)
            guard.journal('p', step)
            with self.assertRaisesRegex(ValueError, 'step'):
                guard.journal('p', step)
            guard, _ = self.guard(tmp, raw_frames=3)
            with self.assertRaisesRegex(ValueError, 'raw-frame'):
                guard.journal('p', step)

    def test_guard_per_episode_cap_checked_after_journal_row(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(b, 'HERE', Path(tmp)):
            guard, _ = self.guard(tmp)
            step = lambda i, f: dict(kind='evaluation_step', episode_index=i, elapsed_raw_frames=f)
            for _ in range(4500):
                guard.journal('p', step(0, 4))      # exactly 18000 is allowed
            guard.journal('p', step(1, 4))          # a different episode has its own allowance
            with self.assertRaisesRegex(ValueError, 'per-episode'):
                guard.journal('p', step(0, 1))
            self.assertEqual(guard.raw, 4501*4+1)   # offending step stays counted, and was journaled first
            self.assertEqual(len(guard.events.getvalue().splitlines()), 4502)
            guard.journal('q', step(0, 4))          # same index under another policy is independent

    def test_guard_resource_cancel_and_deadline(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(b, 'HERE', Path(tmp)):
            guard, torch = self.guard(tmp)
            guard.check(force=True); self.assertEqual(guard.peak_mps, 1024)
            torch.mps.driver_allocated_memory.return_value = b.CAP+1
            with self.assertRaisesRegex(ValueError, 'RSS/MPS'):
                guard.check(force=True)
            guard, _ = self.guard(tmp, rss_bytes=1)
            with self.assertRaisesRegex(ValueError, 'RSS/MPS'):
                guard.check(force=True)
            guard, _ = self.guard(tmp)
            (Path(tmp)/'cancel').write_text('x')
            with self.assertRaisesRegex(ValueError, 'cancellation'):
                guard.check()
            (Path(tmp)/'cancel').unlink()
            guard, _ = self.guard(tmp, work_seconds=0)
            with self.assertRaisesRegex(ValueError, 'deadline'):
                guard.check()
            guard, _ = self.guard(tmp)
            Path(guard.reg['state_path']).write_text(json.dumps(dict(active_long_campaign=None)))
            with self.assertRaisesRegex(ValueError, 'lease'):
                guard.check(force=True)


class Statistics(unittest.TestCase):
    def test_quarter_summary_and_milestones(self):
        data = [row(i, i+1) for i in range(1024)]
        s = comparison.summarize(data, b.SEEDS)
        self.assertEqual(s['performance'], dict(Worst=1, Q1=128.5, Mean=512.5, Q4=896.5, Best=1024))
        self.assertEqual(list(s['milestones']), [str(h) for h in b.MILESTONES])
        self.assertEqual(s['milestones']['1000']['numerator'], 25); self.assertEqual(s['milestones']['2000']['numerator'], 0)
        self.assertEqual((s['death_causes']['normal_enemy'], s['caps']), (1024, 0))

    def test_causes_and_caps_conserved(self):
        data = [row(i, 10+i % 5, CAUSES[i % 5]) for i in range(1024)]; data[7] = row(7, truncated=True)
        s = comparison.summarize(data, b.SEEDS)
        self.assertEqual((s['caps'], sum(s['death_causes'].values())), (1, 1023))
        self.assertEqual(s['milestones']['18000']['numerator'], 1); self.assertEqual(s['performance']['Best'], 18000)

    def test_incomplete_rows_rejected(self):
        with self.assertRaises(ValueError):
            comparison.summarize([row(i) for i in range(1000)], b.SEEDS)
        with self.assertRaises(ValueError):
            comparison.compare({}, b.SEEDS)

    def policies(self, shift):
        return {name: [dict(alive_frames=10+shift(index)) for _ in b.SEEDS] for index, name in enumerate(b.POLICIES)}

    def test_bootstrap_known_shift_and_roles(self):
        r = stats.paired_intervals(self.policies(lambda i: i), b.BOOTSTRAP)
        one = {key: dict(low=1.0, high=1.0) for key in stats.KEYS}
        for rep in (1, 2, 3):
            self.assertEqual(r['comparisons'][f'replica-{rep}-priority_minus_uniform']['performance'], one)
            self.assertEqual(r['comparisons'][f'replica-{rep}-priority_minus_uniform']['role'], 'primary_priority_minus_uniform')
        self.assertEqual(r['comparisons'][stats.MEAN3]['performance'], one)
        self.assertEqual(r['comparisons']['replica-1-uniform_minus_parent']['performance']['Mean'], dict(low=-6.0, high=-6.0))
        self.assertIn('not 1024 independent training replicates', r['interpretation'])

    def test_bootstrap_uses_shared_paired_indices(self):
        base = [(i*37) % 997+1 for i in range(1024)]
        data = {name: [dict(alive_frames=v) for v in base] for name in b.POLICIES}
        data['replica-2-opening_priority'] = [dict(alive_frames=v+5) for v in base]
        r = stats.paired_intervals(data, b.BOOTSTRAP)
        self.assertEqual(r['comparisons']['replica-2-priority_minus_uniform']['performance'],
                         {key: dict(low=5.0, high=5.0) for key in stats.KEYS})

    def test_bootstrap_milestone_rate_difference(self):
        data = {name: [dict(alive_frames=500)]*1024 for name in b.POLICIES}
        data['replica-1-opening_priority'] = [dict(alive_frames=1500)]*1024
        r = stats.paired_intervals(data, b.BOOTSTRAP)['comparisons']['replica-1-priority_minus_uniform']
        self.assertEqual(r['milestone_rate_differences']['1000'], dict(low=1.0, high=1.0))
        self.assertEqual(r['milestone_rate_differences']['2000'], dict(low=0.0, high=0.0))

    def test_bootstrap_rejects_unregistered(self):
        data = {name: [dict(alive_frames=1)]*1024 for name in b.POLICIES}
        for bad in (dict(b.BOOTSTRAP, draws=1), dict(b.BOOTSTRAP, seed=1)):
            with self.assertRaises(ValueError):
                stats.paired_intervals(data, bad)
        with self.assertRaises(ValueError):
            stats.paired_intervals({k: v for k, v in data.items() if k != b.PARENT_ID}, b.BOOTSTRAP)

    def test_compare_pairs_and_three_pair_summary(self):
        rows = {name: [row(i, 10+index+i % 3) for i in range(1024)] for index, name in enumerate(b.POLICIES)}
        c = comparison.compare(rows, b.SEEDS)
        self.assertEqual(len(c['paired_replicas']), 3); self.assertEqual(c['parent_evaluations'], 1)
        diff = c['paired_replicas'][0]['comparisons']['priority_minus_uniform']
        self.assertEqual(diff['role'], 'primary_matched_pair'); self.assertEqual(diff['metric_differences']['Mean'], 1.0)
        self.assertEqual(c['across_three_descriptive']['priority_minus_uniform']['Mean']['values'], [1.0, 1.0, 1.0])
        self.assertEqual(len(diff['per_seed']), 1024); self.assertFalse(c['promoted'])


class Checkpoints(unittest.TestCase):
    def state(self, expected):
        return dict(schema='progressive1000_integrity_checkpoint_v1', global_update=60, phase_update=384,
            cumulative_update=432, identity=expected, identity_sha256=b.identity_hash(expected), promoted=False,
            automatic_selection=False, training_eligible=False, formal_comparison_endpoint=True)

    def test_identity_and_flags(self):
        expected = dict(registration_sha256='r', successor_runtime=dict(source_manifest_sha256='s'))
        policy = dict(id='replica-1-uniform', producer=dict(expected_identity=expected))
        b.validate_checkpoint(self.state(expected), policy)
        for field, value in [('global_update', 48), ('phase_update', 385), ('identity_sha256', 'a'*64),
                             ('promoted', True), ('training_eligible', True), ('formal_comparison_endpoint', False)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                b.validate_checkpoint(dict(self.state(expected), **{field: value}), policy)
        bad = copy.deepcopy(self.state(expected)); bad['identity']['registration_sha256'] = 'other'
        with self.assertRaises(ValueError):
            b.validate_checkpoint(bad, policy)

    def test_parent_phase(self):
        b.validate_checkpoint(dict(phase_update=324), dict(id=b.PARENT_ID))
        with self.assertRaises(ValueError):
            b.validate_checkpoint(dict(phase_update=325), dict(id=b.PARENT_ID))


class ProducerWorld:
    """Fake accepted producer homes: JSON/bytes only. Consistent by construction; mutate to break."""

    def __init__(self, tmp, replica=1, arm='uniform'):
        self.c = b.contracts(); self.tmp = Path(tmp); self.replica, self.arm = replica, arm
        self.home = self.tmp/f'run-{replica}-{arm}'; (self.home/'worker-output').mkdir(parents=True)
        (self.home/'dispatch').mkdir(); (self.home/'src/runtime').mkdir(parents=True)
        run_id = f'{b.STUDY}-replica-{replica}-{arm}'
        clean = b.read(b.SOURCE/'runtime-manifest.json')['files']
        runtime = dict(clean); runtime['dodge_rl/ppo.py'] = 'f'*64; runtime['dodge_rl/seeded_training.py'] = 'e'*64
        runtime['dodge_rl/seed_priority.py'] = 'd'*64
        self.runtime = runtime
        self.reg = dict(schema='dodge_seed_priority_registration_v1', status='parent_registered', study_id=b.STUDY,
            run_id=run_id, pair_id=f'{b.STUDY}-replica-{replica}', replica=replica, arm=arm, backend='mps',
            training_pool_role='training_only', runtime_root=str(self.home/'src/runtime'),
            runtime_manifest_sha256='', source_manifest_sha256='', runtime_versions=dict(python='3.12.15'),
            shared_config=dict(k=1), vector=dict(v=2), training_pool_sha256='p'*64, slot_stream_sha256=['s'*64],
            exclusion_union=b.read(b.REGISTRY)['exclusion_union'], schedule=dict(updates=60))
        self.audit_extra = {}; self.worker_extra = {}; self.sidecar_extra = {}; self.release_extra = {}
        self.manifest_extra = {}

    def write(self):
        h = self.home; (h/'src/source-manifest.json').write_text(json.dumps(dict(files={})))
        (h/'src/runtime-manifest.json').write_text(json.dumps(dict(files=self.runtime)))
        self.reg['source_manifest_sha256'] = b.sha(h/'src/source-manifest.json')
        self.reg['runtime_manifest_sha256'] = b.sha(h/'src/runtime-manifest.json')
        (h/'registration-final.json').write_text(json.dumps(self.reg))
        digest = b.sha(h/'registration-final.json'); ckpt = h/'worker-output/checkpoint-global-060-integrity.pt'
        ckpt.write_bytes(b'fake checkpoint bytes never deserialized '+bytes(str(self.reg['run_id']), 'ascii'))
        identity = b.learner_identity(self.reg, digest, self.c)
        endpoint = dict(path=str(ckpt), sha256=b.sha(ckpt), global_update=60, phase_update=384, cumulative_update=432,
            formal_comparison_endpoint=True, identity=identity, identity_sha256=b.identity_hash(identity),
            parent_checkpoint_sha256=self.c.references.ACCEPTED_CHECKPOINT_SHA256, training_eligible=False,
            promoted=False, automatic_selection=False); endpoint.update(self.sidecar_extra)
        Path(str(ckpt)+'.json').write_text(json.dumps(endpoint))
        worker_doc = dict(status='completed', updates=60, run_id=self.reg['run_id'], registration_sha256=digest,
            formal_comparison_endpoint=endpoint, training_eligible=False, promoted=False, automatic_selection=False)
        worker_doc.update(self.worker_extra)
        (h/'worker-output/worker-result.json').write_text(json.dumps(worker_doc))
        manifest = {ckpt.name: b.sha(ckpt), ckpt.name+'.json': b.sha(str(ckpt)+'.json'),
                    'worker-result.json': b.sha(h/'worker-output/worker-result.json')}
        manifest.update(self.manifest_extra)
        (h/'dispatch/artifact-manifest.json').write_text(json.dumps(manifest))
        audit_doc = dict(schema='dodge_seed_priority_parent_terminal_audit_v1',
            status='accepted_complete_global_update60_training_receipt', registration_sha256=digest,
            parent_raw_observer_exit_code=0, observer_observed_worker_raw_exit=0, observer_directly_reaped=True,
            postflight_inputs_unchanged=True, terminal=dict(terminal_update=60, comparison_endpoint=True),
            automatic_selection=False, promoted=False, training_eligible=False,
            source_manifest_sha256=self.reg['source_manifest_sha256'],
            runtime_manifest_sha256=self.reg['runtime_manifest_sha256'],
            output_manifest=dict(path=str(h/'dispatch/artifact-manifest.json'), sha256=b.sha(h/'dispatch/artifact-manifest.json'), files=3))
        audit_doc.update(self.audit_extra)
        (h/'parent-terminal-audit.json').write_text(json.dumps(audit_doc))
        release = dict(status='exact_lease_cleared_after_durable_parent_audit', audit_sha256=b.sha(h/'parent-terminal-audit.json'))
        release.update(self.release_extra); (h/'lease-release.json').write_text(json.dumps(release))
        (h/'parent-execution.json').write_text('{}'); (h/'execution-exit.json').write_text('{}')
        return self

    def layout(self):
        h = self.home; ckpt = h/'worker-output/checkpoint-global-060-integrity.pt'
        return dict(policy_id=f'replica-{self.replica}-{self.arm}', run_id=self.reg['run_id'], replica=self.replica, arm=self.arm,
            home=str(h), registration_path=str(h/'registration-final.json'), audit_path=str(h/'parent-terminal-audit.json'),
            parent_execution_path=str(h/'parent-execution.json'), execution_exit_path=str(h/'execution-exit.json'),
            lease_release_path=str(h/'lease-release.json'), artifact_manifest_path=str(h/'dispatch/artifact-manifest.json'),
            worker_result_path=str(h/'worker-output/worker-result.json'), checkpoint_path=str(ckpt), sidecar_path=str(ckpt)+'.json')

    def policy(self):
        with mock.patch.object(builder.b, 'predeclared_layouts', lambda: [self.layout()]):
            return builder.policy_entry(self.layout(), self.c)[0]


class Producers(unittest.TestCase):
    def check(self, world):
        policy = world.policy()
        b.producer_policy(policy, world.c, verify_runtime_files=False, layout=world.layout())
        return policy

    def test_builder_entry_passes_validator(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = ProducerWorld(tmp).write(); policy = self.check(world)
            self.assertEqual(policy['id'], 'replica-1-uniform'); self.assertEqual(len(policy['producer']['pins']), 10)

    def test_every_hash_and_state_flag_is_checked(self):
        cases = {
            'audit status': lambda w: w.audit_extra.update(status='failed_partial'),
            'audit observer exit': lambda w: w.audit_extra.update(observer_observed_worker_raw_exit=1),
            'audit promoted': lambda w: w.audit_extra.update(promoted=True),
            'audit registration': lambda w: w.audit_extra.update(registration_sha256='0'*64),
            'worker incomplete': lambda w: w.worker_extra.update(status='failed'),
            'worker updates': lambda w: w.worker_extra.update(updates=48),
            'sidecar promoted': lambda w: w.sidecar_extra.update(promoted=True),
            'sidecar update': lambda w: w.sidecar_extra.update(global_update=48),
            'release audit': lambda w: w.release_extra.update(audit_sha256='1'*64),
            'release status': lambda w: w.release_extra.update(status='held'),
            'manifest ckpt': lambda w: w.manifest_extra.update({'checkpoint-global-060-integrity.pt': '2'*64}),
        }
        for name, mutate in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                world = ProducerWorld(tmp); mutate(world); world.write()
                with self.assertRaises((ValueError, KeyError)):
                    self.check(world)

    def test_checkpoint_bytes_and_pin_drift_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = ProducerWorld(tmp).write(); policy = world.policy()
            b.producer_policy(policy, world.c, verify_runtime_files=False, layout=world.layout())
            Path(policy['checkpoint_path']).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'pin drift|bytes drift'):
                b.producer_policy(policy, world.c, verify_runtime_files=False, layout=world.layout())
            policy['producer']['pins'].pop(policy['checkpoint_path'], None)
            with self.assertRaisesRegex(ValueError, 'bytes drift'):
                b.producer_policy(policy, world.c, verify_runtime_files=False, layout=world.layout())

    def test_identity_and_path_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = ProducerWorld(tmp).write(); policy = world.policy()
            bad = copy.deepcopy(policy); bad['producer']['expected_identity']['replica'] = 9
            with self.assertRaises(ValueError):
                b.producer_policy(bad, world.c, verify_runtime_files=False, layout=world.layout())
            other = dict(world.layout(), checkpoint_path='/elsewhere/checkpoint-global-060-integrity.pt')
            with self.assertRaisesRegex(ValueError, 'predeclared'):
                b.producer_policy(policy, world.c, verify_runtime_files=False, layout=other)

    def test_exclusion_must_cover_d4_and_d5(self):
        for union in ([list(b.D4)], [list(b.D5)]):
            with tempfile.TemporaryDirectory() as tmp:
                world = ProducerWorld(tmp); world.reg['exclusion_union'] = union; world.write()
                with self.assertRaisesRegex(ValueError, 'exclude'):
                    self.check(world)

    def test_inference_members_must_match_clean_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = ProducerWorld(tmp); world.runtime['dodge_rl/models/teacher.py'] = 'a'*64; world.write()
            with self.assertRaisesRegex(ValueError, 'inference member'):
                self.check(world)
        with tempfile.TemporaryDirectory() as tmp:
            world = ProducerWorld(tmp); world.runtime['dodge_rl/curriculum.py'] = 'a'*64; world.write()
            with self.assertRaisesRegex(ValueError, 'unexpected producer runtime'):
                self.check(world)

    def test_unsorted_producer_union_normalized_for_clean_validator(self):
        layout = b.producer_layout(1, 'uniform')
        if not Path(layout['registration_path']).is_file():
            self.skipTest('completed uniform replica 1 registration absent')
        raw = b.read(layout['registration_path'])['exclusion_union']
        self.assertNotEqual(raw, sorted(raw))
        normal = b.normalize_union([raw, list(reversed(raw))])
        self.assertEqual(normal, sorted(normal)); b.contracts().validate_union(normal)
        with self.assertRaises(ValueError):
            b.normalize_union([raw, raw[:-1]])

    def test_real_producer_runtime_membership(self):
        clean = b.read(b.SOURCE/'runtime-manifest.json')['files']
        actual = b.read(b.V2/'fullgame-seed-priority-experiment-luna-20261027-r3/runtime-manifest.json')['files']
        self.assertEqual(set(b.check_runtime_members(actual, clean)), b.PRODUCER_ONLY_MEMBERS)

    def test_identity_reproduces_completed_uniform_sidecar(self):
        layout = b.producer_layout(1, 'uniform')
        if not (Path(layout['registration_path']).is_file() and Path(layout['sidecar_path']).is_file()):
            self.skipTest('completed uniform replica 1 receipts absent')
        reg = b.read(layout['registration_path']); sidecar = b.read(layout['sidecar_path'])
        identity = b.learner_identity(reg, b.sha(layout['registration_path']), b.contracts())
        self.assertEqual(identity, sidecar['identity']); self.assertEqual(b.identity_hash(identity), sidecar['identity_sha256'])
        self.assertEqual(sidecar['sha256'], b.sha(layout['checkpoint_path']))


class Builder(unittest.TestCase):
    def test_refuses_without_all_six_accepted_audits(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = ProducerWorld(tmp).write()
            layouts = [world.layout()]+[dict(world.layout(), policy_id=f'replica-{r}-{a}', run_id=f'r{r}{a}',
                audit_path=f'{tmp}/missing-{r}{a}.json') for r in (1, 2, 3) for a in b.ARMS][1:]
            with mock.patch.object(builder.b, 'predeclared_layouts', lambda: layouts):
                state = builder.readiness()
                self.assertTrue(state[0]['ready']); self.assertFalse(any(row['ready'] for row in state[1:]))
                with self.assertRaisesRegex(builder.NotReady, 'missing'):
                    builder.build()

    def test_failed_audit_is_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = ProducerWorld(tmp); world.audit_extra.update(status='failed'); world.write()
            with mock.patch.object(builder.b, 'predeclared_layouts', lambda: [world.layout()]):
                row = builder.readiness()[0]
            self.assertFalse(row['ready']); self.assertIs(row['audit_accepted'], False)

    def test_real_readiness_reports_six_without_listing_outputs(self):
        rows = builder.readiness()
        self.assertEqual([r['policy_id'] for r in rows], list(b.PRODUCER_POLICIES))
        self.assertTrue(all(set(r) == {'policy_id', 'run_id', 'checkpoint_path', 'audit_present', 'audit_accepted',
                                       'missing', 'ready'} for r in rows))

    def test_finalize_is_copy_with_status_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            draft = dict(status='source_review_pending', calibration=dict(parent_accepted=False), input_pins={}, x=1)
            d = Path(tmp)/'d.json'; a = Path(tmp)/'a.json'; d.write_text(json.dumps(draft)); a.write_text('{}')
            final = finalize_registration.finalize(d, b.sha(d), a, b.sha(a))
            self.assertEqual(final['status'], 'parent_registered'); self.assertIs(final['calibration']['parent_accepted'], True)
            self.assertEqual({k: v for k, v in final.items() if k not in ('status', 'calibration', 'input_pins')}, dict(x=1))
            self.assertEqual(list(final['input_pins'].values()), [b.sha(a)])
            with self.assertRaises(ValueError):
                finalize_registration.finalize(d, '0'*64, a, b.sha(a))
            d.write_text(json.dumps(final))
            with self.assertRaises(ValueError):
                finalize_registration.finalize(d, b.sha(d), a, b.sha(a))

    def test_draft_registration_rejected_before_inputs(self):
        with self.assertRaisesRegex(ValueError, 'field set'):
            b.validate_static(dict(status='parent_registered'))


class FullRegistrationPath(unittest.TestCase):
    """Real clean source, parent receipt, registry, pool and prior-cost pins; fake producers. Needs the sealed package."""

    def setUp(self):
        if not (b.HERE/'source-manifest.json').is_file():
            self.skipTest('package not sealed')

    def worlds(self, tmp):
        c = b.contracts(); versions = c.read(b.SOURCE/'input-manifest.json')['runtime_versions']
        interpreter = b.read(b.read(b.HERE/'dependency-binding.json')['registration_path'])['interpreter']
        worlds = {}
        for r in (1, 2, 3):
            for arm in b.ARMS:
                w = ProducerWorld(tmp, r, arm); w.reg.update(runtime_versions=versions, interpreter=interpreter); worlds[(r, arm)] = w.write()
        return worlds

    def run_path(self, tmp):
        worlds = self.worlds(tmp); layouts = [worlds[(r, a)].layout() for r in (1, 2, 3) for a in b.ARMS]
        by_key = {(l['replica'], l['arm']): l for l in layouts}
        c = b.contracts()
        stack = [mock.patch.object(b, 'predeclared_layouts', lambda: layouts),
                 mock.patch.object(b, 'producer_layout', lambda r, a: by_key[(r, a)]),
                 mock.patch.object(c, 'cache_check', lambda reg: None)]
        for m in stack:
            m.start(); self.addCleanup(m.stop)
        return builder.build(runtime_files=False), worlds

    def test_draft_final_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            draft, worlds = self.run_path(tmp)
            self.assertEqual(draft['status'], 'source_review_pending'); self.assertEqual(draft['seeds'], b.SEEDS)
            self.assertEqual([p['id'] for p in draft['policies']], list(b.POLICIES))
            self.assertEqual(draft['limits']['work_seconds'], 17141); self.assertEqual(draft['limits']['total_seconds'], 17271)
            self.assertEqual(draft['calibration']['postflight_allowance_seconds'], 120); self.assertEqual(draft['limits']['constructors'], 7168)
            self.assertEqual(draft['exclusion_union'], sorted(draft['exclusion_union']))
            with self.assertRaisesRegex(ValueError, 'not launch authority'):
                b.validate_static(draft, runtime_files=False)
            d = Path(tmp)/'draft.json'; a = Path(tmp)/'accept.json'; d.write_text(json.dumps(draft)); a.write_text('{"accepted": true}')
            final = finalize_registration.finalize(d, b.sha(d), a, b.sha(a))
            with mock.patch.object(b.contracts(), 'cache_check', lambda reg: None):
                b.validate_static(final, runtime_files=False)
                for edit, pattern in [(lambda f: f['seeds'].reverse(), 'cohort'), (lambda f: f['limits'].update(raw_frames=1), 'bounds'),
                        (lambda f: f.update(evaluation_rng_seed=1), 'sampling seed'), (lambda f: f['bootstrap'].update(draws=1), 'bootstrap'),
                        (lambda f: f['policies'].reverse(), 'seven fixed'), (lambda f: f['semantics'].update(action_mode='greedy'), 'semantics'),
                        (lambda f: f['expected_lease'].update(owner_token='x'), 'lease'), (lambda f: f['calibration'].update(parent_accepted=False), 'calibration'),
                        (lambda f: f['provenance'].update(universal_workspace_nonuse_claim=True), 'provenance'),
                        (lambda f: f['exclusion_union'].pop(), 'union|D4')]:
                    bad = copy.deepcopy(final); edit(bad)
                    with self.subTest(pattern), self.assertRaisesRegex(ValueError, pattern):
                        b.validate_static(bad, runtime_files=False)

    def test_producer_checkpoint_swap_after_registration_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            draft, worlds = self.run_path(tmp)
            Path(draft['policies'][3]['checkpoint_path']).write_bytes(b'swapped')
            with mock.patch.object(b.contracts(), 'cache_check', lambda reg: None), self.assertRaisesRegex(ValueError, 'drift'):
                b.validate_static(draft, require_registered=False, runtime_files=False)


def synthetic_world(tmp):
    """Fake complete 7x1024 output with journal consistent to rows. Alive frames are tiny except one capped episode."""
    out = Path(tmp)/'worker-output'; out.mkdir()
    reg = dict(run_id=b.EVAL_RUN_ID, output=str(out), seeds=b.SEEDS, bootstrap=b.BOOTSTRAP, runtime_manifest_sha256='r'*64,
        policies=[dict(id=name, checkpoint_sha256=f'{i:064x}') for i, name in enumerate(b.POLICIES)],
        limits=dict(work_seconds=1000, total_seconds=b.total_seconds(1000), cleanup_seconds=10, rss_bytes=b.CAP, mps_bytes=b.CAP,
                    raw_frames=b.RAW_CAP, constructors=b.EPISODES, native_steps=b.STEP_CAP, resets=0, retries=0))
    registration_sha = 'a'*64; events = []; policy_rows = {}
    for p, name in enumerate(b.POLICIES):
        rows = []
        for i in range(1024):
            r = row(i, truncated=True) if (p, i) == (0, 5) else row(i, 1+(i*7+p*3) % 9, CAUSES[(i+p) % 5])
            rows.append(r); events.append(dict(kind='evaluation_constructor', policy_id=name, episode_index=i, startup_frames=13, seed=b.SEEDS[i]))
            events += [dict(kind='evaluation_step', policy_id=name, episode_index=i, elapsed_raw_frames=f) for f in frames_split(r['gameplay_frames'])]
            events.append(dict(kind='evaluation_completed', policy_id=name, row=r))
        policy_rows[name] = rows
    (out/'evaluation-events.jsonl').write_text(''.join(json.dumps(e, sort_keys=True)+'\n' for e in events))
    raw = 0
    for p, name in enumerate(b.POLICIES):
        rows = policy_rows[name]; total = sum(r['gameplay_frames']+r['startup_frames'] for r in rows); raw += total
        b.save(out/(name+'.claim'), dict(policy_id=name, registration_sha256=registration_sha, checkpoint_sha256=reg['policies'][p]['checkpoint_sha256']))
        b.save(out/(name+'.json'), dict(schema='fullgame_priority_d4_terminal60_evaluation_v1', policy_id=name,
            registration_sha256=registration_sha, checkpoint_sha256=reg['policies'][p]['checkpoint_sha256'],
            runtime_manifest_sha256=reg['runtime_manifest_sha256'], action_mode='sampled_categorical', normal_start=True,
            cutoff_enabled=False, summary=comparison.summarize(rows, b.SEEDS), rows=rows, raw_frames_including_startup=total,
            automatic_selection=False, promoted=False))
    report = comparison.compare(policy_rows, b.SEEDS)
    report['paired_conditional_seed_intervals'] = stats.paired_intervals(policy_rows, b.BOOTSTRAP)
    b.save(out/'comparison.json', report)
    (out/'resources.jsonl').write_text(json.dumps(dict(elapsed_seconds=1.0, rss_bytes=10, mps_driver_bytes=5))+'\n')
    steps = sum(e['kind'] == 'evaluation_step' for e in events)
    worker_doc = dict(schema='fullgame_priority_d4_evaluation_worker_v1', status='completed', run_id=reg['run_id'],
        registration_sha256=registration_sha, automatic_selection=False, promoted=False, training_eligible=False,
        completed_policies=list(b.POLICIES), rows_completed=b.EPISODES, raw_frames_including_startup=raw,
        constructors=b.EPISODES, native_steps=steps, comparison_sha256=b.sha(out/'comparison.json'),
        elapsed_seconds=5.0, peak_rss_bytes=10, peak_mps_driver_bytes=5)
    return reg, worker_doc, registration_sha, policy_rows


class TerminalOutputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(); cls.reg, cls.worker, cls.sha, cls.rows = synthetic_world(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def clone(self):
        copy_dir = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, copy_dir, True)
        target = Path(copy_dir)/'worker-output'; shutil.copytree(self.reg['output'], target)
        return dict(self.reg, output=str(target)), copy.deepcopy(self.worker), target

    def test_complete_synthetic_run_accepted_with_exact_accounting(self):
        accounting = terminal.validate_outputs(self.reg, self.worker, self.sha)
        self.assertEqual((accounting['constructors'], accounting['completed_episodes']), (b.EPISODES, b.EPISODES))
        self.assertEqual(accounting['raw_frames_including_startup'], self.worker['raw_frames_including_startup'])
        self.assertEqual(accounting['native_steps'], self.worker['native_steps'])

    def test_audit_recomputes_intervals_independently(self):
        stored = b.read(Path(self.reg['output'])/'comparison.json')['paired_conditional_seed_intervals']
        self.assertEqual(stats.paired_intervals(self.rows, b.BOOTSTRAP), stored)

    def test_tampered_outputs_rejected(self):
        def edit_row(reg, worker, out):
            doc = b.read(out/'replica-2-uniform.json'); doc['rows'][3]['alive_frames'] += 0
            doc['rows'][3]['alive_frames'] -= 1; (out/'replica-2-uniform.json').unlink(); b.save(out/'replica-2-uniform.json', doc)

        def drop_event(reg, worker, out):
            lines = (out/'evaluation-events.jsonl').read_text().splitlines(True)
            idx = next(i for i, l in enumerate(lines) if '"evaluation_completed"' in l)
            (out/'evaluation-events.jsonl').write_text(''.join(lines[:idx]+lines[idx+1:]))

        def torn(reg, worker, out):
            with (out/'evaluation-events.jsonl').open('a') as f:
                f.write('{"kind":')

        def duplicate_constructor(reg, worker, out):
            lines = (out/'evaluation-events.jsonl').read_text().splitlines(True)
            (out/'evaluation-events.jsonl').write_text(''.join([lines[0]]+lines))

        def overcap(reg, worker, out):
            with (out/'evaluation-events.jsonl').open('a') as f:
                f.write(json.dumps(dict(kind='evaluation_constructor', policy_id=b.POLICIES[0], episode_index=0, startup_frames=13, seed=b.SEEDS[0]))+'\n')

        def worker_edit(**kw):
            return lambda reg, worker, out: worker.update(kw)

        def limit(reg, worker, out):
            reg['limits'] = dict(reg['limits'], raw_frames=reg['limits']['raw_frames']-b.RAW_CAP+worker['raw_frames_including_startup']-1)

        def bad_resource(reg, worker, out):
            (out/'resources.jsonl').write_text(json.dumps(dict(elapsed_seconds=1.0, rss_bytes=b.CAP+1, mps_driver_bytes=5))+'\n')

        def promoted_receipt(reg, worker, out):
            doc = b.read(out/'parent324.json'); doc['promoted'] = True; (out/'parent324.json').unlink(); b.save(out/'parent324.json', doc)

        cases = dict(edited_row=edit_row, dropped_completion=drop_event, torn_journal=torn,
            duplicate_constructor=duplicate_constructor, extra_constructor=overcap, worker_partial=worker_edit(status='failed'),
            worker_rows=worker_edit(rows_completed=b.EPISODES-1), worker_deadline=worker_edit(elapsed_seconds=1000.0),
            worker_promoted=worker_edit(promoted=True), worker_cost=worker_edit(raw_frames_including_startup=1),
            worker_steps=worker_edit(native_steps=1), over_limit=limit, resource_over=bad_resource, receipt_promoted=promoted_receipt)
        for name, mutate in cases.items():
            with self.subTest(name):
                reg, worker, out = self.clone(); mutate(reg, worker, out)
                with self.assertRaises((ValueError, KeyError)):
                    terminal.validate_outputs(reg, worker, self.sha)

    def test_accounting_prefix_tolerates_torn_tail_only_when_not_strict(self):
        reg, worker, out = self.clone()
        with (out/'evaluation-events.jsonl').open('a') as f:
            f.write('{"kind":')
        self.assertEqual(terminal.accounting(out, {})['completed_episodes'], b.EPISODES)


class Journal(unittest.TestCase):
    def accounting(self, events):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'evaluation-events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
            return terminal.accounting(tmp, {}, strict=True, include_rows=True)

    def test_single_episode_exact_cost(self):
        policy = b.POLICIES[0]
        a = self.accounting([dict(kind='evaluation_constructor', policy_id=policy, episode_index=0, startup_frames=13, seed=b.SEEDS[0]),
            dict(kind='evaluation_step', policy_id=policy, episode_index=0, elapsed_raw_frames=4),
            dict(kind='evaluation_completed', policy_id=policy, row=row())])
        self.assertEqual((a['constructors'], a['completed_episodes'], a['raw_frames_including_startup']), (1, 1, 17))

    def test_invalid_journals(self):
        policy = b.POLICIES[0]
        ctor = dict(kind='evaluation_constructor', policy_id=policy, episode_index=0, startup_frames=13, seed=b.SEEDS[0])
        step = lambda n: dict(kind='evaluation_step', policy_id=policy, episode_index=0, elapsed_raw_frames=n)
        done = dict(kind='evaluation_completed', policy_id=policy, row=row())
        cases = {'duplicate constructor': [ctor, ctor], 'frame mismatch': [ctor, step(3), done],
                 'step before constructor': [step(4)], 'step after completion': [ctor, step(4), done, step(4)],
                 'five-frame step': [ctor, step(5)], 'zero-frame step': [ctor, step(0)],
                 'unknown policy': [dict(ctor, policy_id='replica-9-uniform')], 'wrong seed': [dict(ctor, seed=1)],
                 'bad startup': [dict(ctor, startup_frames=12)], 'episode out of range': [dict(ctor, episode_index=1024)],
                 'unregistered event': [dict(kind='surprise', policy_id=policy, episode_index=0)]}
        for name, events in cases.items():
            with self.subTest(name), self.assertRaises((ValueError, KeyError)):
                self.accounting(events)

    def test_episode_cap(self):
        policy = b.POLICIES[0]; events = [dict(kind='evaluation_constructor', policy_id=policy, episode_index=0, startup_frames=13, seed=b.SEEDS[0])]
        events += [dict(kind='evaluation_step', policy_id=policy, episode_index=0, elapsed_raw_frames=4)]*4501
        with self.assertRaisesRegex(ValueError, 'cap'):
            self.accounting(events)

    def test_torn_journal_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'evaluation-events.jsonl'; p.write_text('{"unfinished":')
            self.assertEqual(list(terminal.rows(p)), [])
            with self.assertRaisesRegex(ValueError, 'torn'):
                list(terminal.rows(p, strict=True))
            self.assertEqual(p.read_text(), '{"unfinished":')


class Supervision(unittest.TestCase):
    def test_supervisor_copies_unchanged(self):
        original = b.V2/'progressive1000-opening-maintenance-supervisor-parent-20261027-r1'
        for name in ('observe.py', 'execute_once.py'):
            self.assertEqual(b.sha(b.HERE/name), b.sha(original/name))

    def test_binding_surface_used_by_supervisor_exists(self):
        text = (b.HERE/'observe.py').read_text()
        for name in set(re.findall(r'\bb\.([A-Za-z_]+)', text)):
            self.assertTrue(hasattr(b, name), name)
        for name in set(re.findall(r'\bterminal\.([A-Za-z_]+)', text)):
            self.assertTrue(hasattr(terminal, name), name)

    def test_observer_receipt_validation(self):
        ex = dict(registration_sha256='r', envelope_sha256='e', observer_pgid=4)
        ex_exit = dict(registration_sha256='r', raw_observer_exit_code=0, observer_directly_reaped=True)
        obs = dict(observed_worker_raw_exit=0, directly_reaped=True, first_event=None,
                   status='completed_pending_parent_audit', owned_group_absent=True)
        audit.check_observer_receipts(ex, ex_exit, obs, 'r', 'e')
        for edit in (dict(observed_worker_raw_exit=1), dict(first_event='x'), dict(owned_group_absent=False),
                     dict(status='failed'), dict(directly_reaped=False)):
            with self.subTest(edit), self.assertRaises(ValueError):
                audit.check_observer_receipts(ex, ex_exit, dict(obs, **edit), 'r', 'e')
        with self.assertRaises(ValueError):
            audit.check_observer_receipts(ex, ex_exit, obs, 'other', 'e')
        with self.assertRaises(ValueError):
            audit.group_absent(os.getpgrp(), 'self')

    def test_manifest_member_set_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'out'; control = Path(tmp)/'control'; out.mkdir(); control.mkdir()
            (out/'a').write_text('x'); (control/'artifact-manifest.json').write_text(json.dumps({'a': b.sha(out/'a')}))
            audit.check_manifest(control, out)
            (out/'extra').write_text('y')
            with self.assertRaises(ValueError):
                audit.check_manifest(control, out)

    def test_state_replace_is_atomic_and_leaves_no_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)/'state.json'; state.write_text('{"a":1}')
            launch.replace_state(state, {'a': 2})
            self.assertEqual(json.loads(state.read_text()), {'a': 2})
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ['state.json'])

    def test_gate_document_requires_every_gate(self):
        for gate in ('d5_unopened', 'provenance_scope', 'registered_rng', 'resource_calibration', 'producer_identity'):
            self.assertIn(gate, b.GATES)
        doc = b.approval_document('r', 's', {})
        self.assertEqual(doc['gates'], dict.fromkeys(b.GATES, 'passed'))

    def test_exclusive_durable_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'receipt.json'; b.save(p, dict(first=True))
            with self.assertRaises(FileExistsError):
                b.save(p, dict(first=False))
            self.assertEqual(b.read(p), dict(first=True))
            p.write_text('{"a":1,"a":2}')
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                b.read(p)

    def test_monitor_progress_counts_only(self):
        import monitor
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'worker-output'; out.mkdir()
            events = [dict(kind='evaluation_constructor', policy_id=b.POLICIES[0], episode_index=0, startup_frames=13, seed=1),
                      dict(kind='evaluation_step', policy_id=b.POLICIES[0], episode_index=0, elapsed_raw_frames=4),
                      dict(kind='evaluation_completed', policy_id=b.POLICIES[0], row=row())]
            (out/'evaluation-events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events)+'{"torn":')
            with mock.patch.object(b, 'HERE', Path(tmp)):
                value = monitor.progress()
            self.assertEqual((value['constructors'], value['steps'], value['completed'], value['raw_frames']), (1, 1, 1, 17))
            self.assertNotIn('alive_frames', json.dumps(value))


def fake_fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=repr).encode()).hexdigest()


class WorkerWorld:
    """Real worker.run, Guard, comparison, paired_statistics, binding.validate_checkpoint and terminal validation around
    fake evaluator (_production_rows), model, checkpoint, numpy/torch facades. Nothing here loads native code."""
    FIRST = b.POLICIES[0]
    EXCLUDED = [(0xD3000000, 0xD3FFFFFF), (0xD4000400, 0xD50007FF)]

    def __init__(self, tmp, **limits):
        self.home = Path(tmp)/'home'; self.home.mkdir()
        self.log = []; self.seeds_seen = dict(np=[], torch=[], mps=[]); self.production_calls = []
        self.script = {}; self.hooks = {}; self.mps_bytes = 1024
        self.lease = dict(kind='fake_lease', run_id=b.EVAL_RUN_ID)
        (self.home/'state.json').write_text(json.dumps(dict(active_long_campaign=self.lease)))
        policies, self.states = [], {}
        for name in b.POLICIES:
            path = self.home/(name+'.pt'); path.write_bytes(name.encode())
            identity = {'who': name}
            policies.append(dict(id=name, checkpoint_path=str(path), checkpoint_sha256=b.sha(path),
                                 producer=None if name == b.PARENT_ID else dict(expected_identity=identity)))
            self.states[str(path)] = dict(model=dict(w=name), phase_update=324) if name == b.PARENT_ID else dict(
                schema='progressive1000_integrity_checkpoint_v1', global_update=60, phase_update=384, cumulative_update=432,
                identity=identity, identity_sha256=b.identity_hash(identity), promoted=False, automatic_selection=False,
                training_eligible=False, formal_comparison_endpoint=True, model=dict(w=name))
        self.reg = dict(run_id=b.EVAL_RUN_ID, runtime_manifest_sha256='r'*64, policies=policies, seeds=b.SEEDS,
            exclusion_union=[[0xD3000000, 0xD50007FF]], evaluation_rng_seed=b.EVAL_RNG_SEED, bootstrap=b.BOOTSTRAP,
            limits=dict(dict(work_seconds=1000, total_seconds=b.total_seconds(1000), cleanup_seconds=10, rss_bytes=b.CAP,
                mps_bytes=b.CAP, raw_frames=b.RAW_CAP, constructors=b.EPISODES, native_steps=b.STEP_CAP, resets=0, retries=0), **limits),
            state_path=str(self.home/'state.json'), expected_lease=self.lease, output=str(Path(tmp)/'worker-output'),
            attempt_claim_path=str(Path(tmp)/'attempt.claimed'))
        self.out = Path(self.reg['output'])

    # fake facades
    def load_checkpoint(self, path, expected_sha256):
        b.need(b.sha(path) == expected_sha256, 'fake loader: checkpoint bytes differ')
        self.log.append('load:'+Path(path).stem); return copy.deepcopy(self.states[str(path)])

    def authenticate(self, reg, c):
        self.log.append('authenticate')
        world = self
        class Model:
            def to(s, device): world.log.append('to:'+device); return s
            def load_state_dict(s, sd, strict): world.log.append('strict' if strict else 'lenient'); s.sd = copy.deepcopy(sd)
            def eval(s): return s
            def state_dict(s): return s.sd
        rng = types.SimpleNamespace(seed=lambda v: self.seeds_seen['np'].append(v))
        mps = types.SimpleNamespace(manual_seed=lambda v: self.seeds_seen['mps'].append(v), empty_cache=lambda: None,
                                    driver_allocated_memory=lambda: self.mps_bytes)
        torch = types.SimpleNamespace(manual_seed=lambda v: self.seeds_seen['torch'].append(v), mps=mps, is_grad_enabled=lambda: True)
        ckpt = types.SimpleNamespace(load_checkpoint=self.load_checkpoint, require_complete_update=lambda s: None,
            capture_rng=lambda device: dict(rng=1), restore_rng=lambda value, device: self.log.append('restore_rng'))
        teacher = types.SimpleNamespace(OmniscientEntityTeacher=Model)
        return types.SimpleNamespace(random=rng), torch, types.SimpleNamespace(VecDodgeEnv=object), ckpt, teacher

    def production_rows(self, model, env_class, neural_inputs, death_fields, seeds, excluded, check, *, batch_size, event_sink):
        name = model.sd['w']; p = b.POLICIES.index(name)
        self.production_calls.append(dict(policy=name, seeds=seeds, excluded=excluded, batch_size=batch_size,
                                          neural_inputs=neural_inputs, env_class=env_class))
        self.log.append('eval:'+name); rows = []
        for i, seed in enumerate(seeds):
            if i % 64 == 0:
                check()
            r = row(i, truncated=True) if (p, i) == (0, 5) else row(i, 1+(i*7+p*3) % 9, CAUSES[(i+p) % 5])
            event_sink(dict(kind='evaluation_constructor', episode_index=i, info=dict(startup_frames=13, seed=dict(actual_seed=seed))))
            for frames in self.script.get((name, i), frames_split(r['gameplay_frames'])):
                event_sink(dict(kind='evaluation_step', episode_index=i, elapsed_raw_frames=frames))
            event_sink(dict(kind='evaluation_completed', row=r)); rows.append(r)
        if name in self.hooks:
            self.hooks[name](model)
        return rows

    def run(self):
        e = dict(started=time.monotonic(), registration_sha256='a'*64)
        real, world = b.analysis(), self       # real clean-source row validation; only the native-env loop is faked
        class Analysis:
            _production_rows = staticmethod(world.production_rows)
            def __getattr__(self, name):
                return getattr(real, name)
        self.analysis = Analysis()
        c = types.SimpleNamespace(transition=types.SimpleNamespace(EXPECTED_PARENT=dict(model=fake_fingerprint(dict(w=b.PARENT_ID)))))
        modules = {name: types.ModuleType(name) for name in ('fingerprints', 'death_telemetry', 'successor_identity')}
        modules['fingerprints'].fingerprint = fake_fingerprint
        modules['death_telemetry'].death_fields = 'death_fields'
        modules['successor_identity'].NEURAL_INPUTS = b.NEURAL_INPUTS
        verify = lambda envelope, reg, preflight: self.log.append(f'verify_bound:preflight={preflight}')
        with mock.patch.object(b, 'HERE', self.home), mock.patch.object(b, 'load_envelope', return_value=(e, self.reg)), \
                mock.patch.object(b, 'verify_bound', side_effect=verify), mock.patch.object(b, 'contracts', return_value=c), \
                mock.patch.object(b, 'analysis', return_value=self.analysis), \
                mock.patch.object(worker, 'authenticate_runtime', side_effect=self.authenticate), mock.patch.dict(sys.modules, modules):
            try:
                self.status = worker.run('envelope.json', 'sha'); error = None
            except BaseException as caught:
                error = caught
        return error

    def result(self):
        return b.read(self.out/'worker-result.json')

    def journal(self):
        return [json.loads(line) for line in (self.out/'evaluation-events.jsonl').read_text().splitlines()]


class WorkerRun(unittest.TestCase):
    """worker.run end to end over fake evaluator/model/dependency facades (the real native env is NOT exercised)."""
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(); cls.world = WorkerWorld(cls.tmp); cls.error = cls.world.run()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def fresh(self, **limits):
        tmp = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, tmp, True)
        return WorkerWorld(tmp, **limits)

    def test_positive_flow_wires_seven_registered_policies_in_order(self):
        w = self.world; self.assertIsNone(self.error); self.assertEqual(w.status, 0)
        self.assertEqual(w.log[:3], ['verify_bound:preflight=True', 'authenticate', 'load:'+b.POLICIES[0]])
        self.assertEqual([x[5:] for x in w.log if x.startswith('load:')], list(b.POLICIES))
        self.assertEqual([x[5:] for x in w.log if x.startswith('eval:')], list(b.POLICIES))
        self.assertEqual(w.log.count('strict'), 7); self.assertEqual(w.log.count('lenient'), 0)
        self.assertEqual(w.log.count('authenticate'), 1); self.assertEqual(w.log.count('restore_rng'), 1)
        for key, expected in (('np', b.EVAL_RNG_SEED % 2**32), ('torch', b.EVAL_RNG_SEED), ('mps', b.EVAL_RNG_SEED)):
            self.assertEqual(w.seeds_seen[key], [expected]*7)
        for call in w.production_calls:
            self.assertEqual((call['seeds'], call['excluded'], call['batch_size'], call['neural_inputs']),
                             (b.SEEDS, w.EXCLUDED, 64, b.NEURAL_INPUTS))

    def test_positive_flow_accounting_and_terminal_conservation(self):
        w = self.world; result = w.result()
        self.assertEqual((result['status'], result['completed_policies'], result['rows_completed']),
                         ('completed', list(b.POLICIES), b.EPISODES))
        self.assertEqual((result['constructors'], result['automatic_selection'], result['promoted'], result['training_eligible']),
                         (b.EPISODES, False, False, False))
        journal = w.journal()
        steps = [x for x in journal if x['kind'] == 'evaluation_step']
        self.assertEqual(result['native_steps'], len(steps))
        self.assertEqual(result['raw_frames_including_startup'], 13*b.EPISODES+sum(x['elapsed_raw_frames'] for x in steps))
        self.assertIn(18000, [sum(x['elapsed_raw_frames'] for x in steps if x['policy_id'] == w.FIRST and x['episode_index'] == 5)])
        accounting = terminal.validate_outputs(w.reg, result, 'a'*64)     # real terminal validator over real worker output
        self.assertEqual((accounting['constructors'], accounting['native_steps'], accounting['raw_frames_including_startup']),
                         (result['constructors'], result['native_steps'], result['raw_frames_including_startup']))
        self.assertEqual(b.read(w.reg['attempt_claim_path'])['run_id'], b.EVAL_RUN_ID)
        self.assertFalse(any(n == 'torch' or n == 'numpy' or n.startswith('dodge_rl') for n in sys.modules))

    def test_attempt_is_spent_exactly_once(self):
        w = self.world; loads = w.log.count('authenticate')
        self.assertIsInstance(w.run(), FileExistsError)
        self.assertEqual(w.log.count('authenticate'), loads)       # failed before runtime import/checkpoint load

    def test_per_episode_cap_fails_before_episode_result_with_journal_conserved(self):
        w = self.fresh(); w.script[(w.FIRST, 7)] = [4]*4500+[3]
        error = w.run(); self.assertRegex(str(error), 'per-episode')
        result = w.result(); self.assertEqual((result['status'], result['completed_policies'], result['rows_completed']), ('failed', [], 0))
        journal = w.journal()
        self.assertFalse(any(x['kind'] == 'evaluation_completed' and x['row']['episode_index'] == 7 for x in journal))
        self.assertEqual(sum(x['elapsed_raw_frames'] for x in journal if x['kind'] == 'evaluation_step' and x['episode_index'] == 7), 18003)
        self.assertEqual(result['raw_frames_including_startup'], sum(
            x.get('startup_frames', 0)+x.get('elapsed_raw_frames', 0) for x in journal))     # nothing spent unjournaled
        self.assertFalse((w.out/(w.FIRST+'.json')).exists()); self.assertTrue((w.out/(w.FIRST+'.claim')).exists())
        self.assertEqual(w.log.count('restore_rng'), 1)

    def test_constructor_and_step_ceilings_keep_the_exceeding_event_journaled(self):
        for key, kind, limit in (('constructors', 'evaluation_constructor', 1030), ('native_steps', 'evaluation_step', 100)):
            with self.subTest(key=key):
                w = self.fresh(**{key: limit}); error = w.run(); self.assertRegex(str(error), 'constructor/step ceiling')
                journal = w.journal(); self.assertEqual(sum(x['kind'] == kind for x in journal), limit+1)
                self.assertEqual(w.result()['raw_frames_including_startup'], sum(
                    x.get('startup_frames', 0)+x.get('elapsed_raw_frames', 0) for x in journal))
                self.assertEqual(w.result()['completed_policies'], [w.FIRST] if key == 'constructors' else [])
                self.assertEqual(w.result()['status'], 'failed')

    def test_work_deadline_and_resource_ceiling_stop_before_any_checkpoint_load(self):
        w = self.fresh(work_seconds=0); self.assertRegex(str(w.run()), 'work deadline')
        self.assertEqual([x for x in w.log if x.startswith('load:')], []); self.assertTrue(Path(w.reg['attempt_claim_path']).exists())
        self.assertEqual(w.result()['status'], 'failed')
        w = self.fresh(); w.mps_bytes = b.CAP+1; self.assertRegex(str(w.run()), 'RSS/MPS')
        self.assertEqual([x for x in w.log if x.startswith('load:')], [])

    def test_weight_or_checkpoint_mutation_publishes_no_receipt(self):
        w = self.fresh(); w.hooks[w.FIRST] = lambda model: model.sd.update(w='tampered')
        self.assertRegex(str(w.run()), 'changed weights')
        self.assertFalse((w.out/(w.FIRST+'.json')).exists()); self.assertEqual(w.result()['completed_policies'], [])
        w = self.fresh(); path = Path(w.reg['policies'][0]['checkpoint_path'])
        w.hooks[w.FIRST] = lambda model: path.write_bytes(b'changed')
        self.assertRegex(str(w.run()), 'checkpoint bytes changed')
        self.assertFalse((w.out/(w.FIRST+'.json')).exists())

    def test_lease_loss_after_first_policy_keeps_only_that_receipt(self):
        w = self.fresh()
        w.hooks[w.FIRST] = lambda model: (w.home/'state.json').write_text(json.dumps(dict(active_long_campaign=None)))
        self.assertRegex(str(w.run()), 'lease')
        result = w.result(); self.assertEqual((result['status'], result['completed_policies']), ('failed', [w.FIRST]))
        self.assertTrue((w.out/(w.FIRST+'.json')).exists())
        second = b.POLICIES[1]; self.assertFalse((w.out/(second+'.claim')).exists()); self.assertNotIn('load:'+second, w.log)
        self.assertFalse((w.out/'comparison.json').exists())

    def test_parent_model_mismatch_stops_before_model_build(self):
        w = self.fresh(); w.states[w.reg['policies'][-1]['checkpoint_path']]['model'] = dict(w='other')
        self.assertRegex(str(w.run()), 'accepted parent model differs')
        self.assertEqual(w.result()['completed_policies'], list(b.PRODUCER_POLICIES))
        self.assertFalse((w.out/(b.PARENT_ID+'.json')).exists())


class FakeClock:
    """Injected observer clock/sleep: coarse steps far from the deadline, 1 s steps near the work deadline."""
    def __init__(self, start, fine_after, step=50.0):
        self.t, self.fine_after, self.step = start, fine_after, step

    def __call__(self):
        return self.t

    def sleep(self, _requested):
        time.sleep(.02)            # a real child must make progress between observer polls
        self.t += 1.0 if self.t >= self.fine_after else self.step


@unittest.skipUnless(sys.platform == 'darwin' and platform.machine() == 'arm64', 'observer ABI is Darwin arm64 only')
class ObserverRun(unittest.TestCase):
    """observe.main with its injected popen/clock/sleep driving a real tiny stub child (no worker, native, torch)."""
    START = 100000.0
    WORK = 1000

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(); cls.reg, cls.worker, cls.sha, _ = synthetic_world(cls.tmp)
        b.save(Path(cls.reg['output'])/'worker-result.json', cls.worker)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_observer(self, name, *, child, total, postflight=0.0, begin, output=None, step=50.0):
        root = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, root, True)
        state = root/'state.json'; lease = dict(kind='fake', run_id='x'); state.write_text(json.dumps(dict(active_long_campaign=lease)))
        limits = dict(self.reg['limits'], work_seconds=self.WORK, total_seconds=total)
        reg = dict(self.reg, limits=limits, output=output or self.reg['output'], state_path=str(state), expected_lease=lease,
                   interpreter=sys.executable, runtime_root=str(root), import_policy=dict(pycache_prefix=str(root/'pyc')))
        envelope_path = root/'envelope.json'; envelope_path.write_text('{}'); digest = b.sha(envelope_path)
        envelope = dict(control=str(root/'dispatch'), cancel_path=str(root/'cancel'), started=self.START,
                        registration_sha256='a'*64, self_path=str(envelope_path), self_sha256=digest)
        clock = FakeClock(self.START+begin, self.START+self.WORK-3, step); procs = []
        def popen(command, **kwargs):
            self.assertEqual(command, b.worker_command(envelope, reg))            # the registered worker command is what is launched
            self.assertTrue(kwargs['start_new_session'])
            procs.append(subprocess.Popen([sys.executable, '-I', '-c', child], **kwargs)); return procs[-1]
        def timed_validate(*args):
            result = real_validate(*args); clock.t += postflight; return result
        real_validate = terminal.validate_outputs
        self.addCleanup(lambda: [p.kill() for p in procs if p.poll() is None])
        with mock.patch.object(b, 'load_envelope', return_value=(envelope, reg)), mock.patch.object(b, 'verify_bound'), \
                mock.patch.dict(b.LIMITS, limits), mock.patch.object(terminal, 'validate_outputs', side_effect=timed_validate):
            code = observe.main(str(envelope_path), digest, popen=popen, clock=clock, sleep=clock.sleep)
        return code, b.read(root/'dispatch'/'observation.json'), root, procs

    def test_success_with_postflight_inside_registered_headroom(self):
        total = b.total_seconds(self.WORK)
        code, record, root, procs = self.run_observer('ok', child='raise SystemExit(0)', total=total, postflight=100.0, begin=self.WORK-30)
        self.assertEqual(code, 0, record.get('error') or record)
        self.assertEqual((record['status'], record['first_event'], record['deadline_consumed']), ('completed_pending_parent_audit', None, False))
        self.assertGreater(record['elapsed_seconds'], self.WORK+10)      # postflight ran past work+cleanup, inside total
        self.assertLess(record['elapsed_seconds'], total)
        self.assertTrue((root/'dispatch'/'artifact-manifest.json').is_file())
        self.assertEqual(record['evidence_checks']['constructors'], b.EPISODES)

    def test_same_postflight_would_exhaust_a_work_plus_cleanup_only_budget(self):
        code, record, _, _ = self.run_observer('legacy', child='raise SystemExit(0)', total=self.WORK+10, postflight=100.0, begin=self.WORK-30)
        self.assertEqual(code, 1); self.assertEqual(record['status'], 'failed'); self.assertTrue(record['deadline_consumed'])

    def test_postflight_beyond_registered_headroom_fails_closed(self):
        code, record, root, _ = self.run_observer('over', child='raise SystemExit(0)', total=b.total_seconds(self.WORK), postflight=170.0, begin=self.WORK-30)
        self.assertEqual(code, 1); self.assertEqual(record['status'], 'failed'); self.assertTrue(record['deadline_consumed'])
        self.assertFalse((root/'dispatch'/'artifact-manifest.json').exists())

    def test_work_deadline_cleanup_stays_within_ten_seconds_and_leaves_headroom_unused(self):
        empty = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, empty, True)
        code, record, _, procs = self.run_observer('timeout', child='import time; time.sleep(120)', total=b.total_seconds(self.WORK),
                                                   begin=0.0, output=empty)
        self.assertEqual(code, 1); self.assertEqual(record['status'], 'failed')
        self.assertEqual(record['first_event']['kind'], 'external_work_deadline')
        self.assertEqual([s['signal'] for s in record['cleanup_signals']][:1], ['SIGTERM'])
        self.assertTrue(record['directly_reaped']); self.assertTrue(record['owned_group_absent'])
        self.assertIsNotNone(procs[0].returncode); self.assertFalse(record['deadline_consumed'])
        self.assertGreaterEqual(record['elapsed_seconds'], self.WORK)
        self.assertLessEqual(record['elapsed_seconds'], self.WORK+b.CLEANUP_SECONDS)       # cleanup bound unchanged, headroom not used



class ZZEnvironment(unittest.TestCase):
    def test_no_runtime_imports(self):
        self.assertFalse(any(n == 'torch' or n.startswith('torch.') or n == 'numpy' or n == 'dodge_rl'
                             or n.startswith('dodge_rl.') for n in sys.modules))

    def test_caches_empty_and_bytecode_disabled(self):
        self.assertTrue(sys.dont_write_bytecode)
        for name in ('empty-pycache', 'tests-pycache'):
            self.assertEqual(list((b.HERE/name).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
