"""Actual-native synthetic CPU collector units; no optimizer, checkpoint or study.

The split fixture divides one pending synthetic update into two owned buffers.
It does not simulate successful PPO or advance the scheduler.
"""
from pathlib import Path
import copy
from dataclasses import asdict, fields
import json
import sys
from types import SimpleNamespace

sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parent / 'tests')]
from common import OUT, canonical, digest, load_native, write
from fixed_policy import avoidance_actions
import numpy as np
import torch
from torch import nn
from successor import ppo
from successor.curriculum import CurriculumAdapter, HISTORICAL_RANGES, PINNED_PPO, equal, validate_seed_union
from test_collector import scalar_gae

torch.set_num_threads(1)
torch.set_num_interop_threads(1)
native = load_native('new')
EXCLUSIONS = validate_seed_union(HISTORICAL_RANGES)
SYNTHETIC_DIGEST = digest({'fixture': 'CPU-unit-only-not-study', 'run_seed': 777})
OPTIONS = dict(batch_size=8, action_repeat=4, difficulty=1, patterns_enabled=False,
    powerups_enabled=False, raw_frame_cap=18000, num_threads=2, chunk_size=2,
    render_pixels=False, auxiliary_targets=False, run_seed=777,
    excluded_seed_ranges=list(EXCLUSIONS))
OBS_KEYS = ('global_feats', 'entity_feats', 'entity_types', 'entity_mask')


def value_tensor(model, observation):
    return model.value_head(torch.as_tensor(observation['global_feats'])[:, 0]).squeeze(-1)


class FixedTinyPolicy(nn.Module):
    """Fixed fixture actions and a tiny, nonconstant CPU linear value function."""
    def __init__(self, trace):
        super().__init__()
        self.trace = trace
        self.value_head = nn.Linear(14, 1)
        with torch.no_grad():
            self.value_head.weight.copy_(torch.arange(1, 15, dtype=torch.float32).reshape(1, 14) / 64)
            self.value_head.bias.fill_(0.25)

    def forward(self, global_feats, entity_feats, entity_types, entity_mask):
        tensors = dict(zip(OBS_KEYS, (global_feats, entity_feats, entity_types, entity_mask), strict=True))
        assert all(x.device.type == 'cpu' for x in tensors.values())
        observation = {k: v.detach().numpy() for k, v in tensors.items()}
        actions = avoidance_actions(observation)
        logits = torch.full((len(actions), 9), -1000.0)
        logits[torch.arange(len(actions)), actions] = 0.0
        values = self.value_head(global_feats[:, 0]).squeeze(-1)
        if self.trace.audit_pending:
            assert digest(observation) == digest({k: self.trace.last['observations'][k] for k in OBS_KEYS})
            self.trace.rows[-1]['final_values'] = values.detach().tolist()
            self.trace.rows[-1]['final_observation_valued_before_reset'] = True
            self.trace.valued_step = self.trace.steps - 1
            self.trace.audit_pending = False
        return SimpleNamespace(logits=logits, values=values)


class TraceEnv:
    """Read-only instrumentation around exact native API calls and owned results."""
    def __init__(self, inner, failure=False):
        self.inner = inner
        self.failure = failure
        self.reset_returned = False
        self.steps = 0
        self.rows, self.cutoffs, self.resets = [], [], []
        self.last = None
        self.raw = None
        self.audit_pending = False
        self.valued_step = -1

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def step(self, actions):
        result = self.inner.step(actions)
        self.steps += 1
        self.last = result
        self.raw = copy.deepcopy(result)
        self.rows.append({'global_decision': self.steps - 1, 'actions': np.asarray(actions).tolist(),
            'raw_final_digest': digest(result), 'raw_truncated': result['truncated'].tolist()})
        return result

    def truncate_practice(self, indices, horizons):
        infos_before = self.inner.episode_info()
        observations_before = self.inner.observations()
        result_before = digest(self.last)
        returned = self.inner.truncate_practice(indices, horizons)
        assert all(infos_before[s]['gameplay_frames'] == h == 1000 for s, h in zip(indices, horizons, strict=True))
        assert all(not infos_before[s]['terminated'] and not infos_before[s]['truncated'] for s in indices)
        assert digest(self.last) == result_before
        assert equal(self.inner.observations(), observations_before)
        self.cutoffs.append({'global_decision': self.steps - 1, 'indices': list(indices),
            'horizons': list(horizons), 'before': infos_before, 'returned': copy.deepcopy(returned),
            'native_info_after': self.inner.episode_info(), 'final_observations_unchanged': True,
            'owned_step_unchanged': True})
        return returned

    def reset_done(self, indices):
        before = self.inner.episode_info()
        expected = [s for s, r in enumerate(before) if r['terminated'] or r['truncated']]
        assert indices == expected == sorted(set(indices))
        assert self.valued_step == self.steps - 1, 'reset preceded actual final observation value'
        saved = digest(self.last)
        returned = self.inner.reset_done(indices)
        assert digest(self.last) == saved, 'native reset mutated owned final result'
        after = self.inner.episode_info()
        for slot in range(len(before)):
            if slot in indices:
                assert after[slot]['seed']['episode'] == before[slot]['seed']['episode'] + 1
                assert after[slot]['gameplay_frames'] == after[slot]['alive_frames'] == 0
            else:
                assert equal(before[slot], after[slot])
        self.resets.append({'global_decision': self.steps - 1, 'indices': list(indices),
            'before': before, 'returned': copy.deepcopy(returned['info']),
            'post_reset_observations_digest': digest(self.inner.observations()),
            'one_episode_increment': True, 'one_combined_subset_call': True,
            'final_value_before_reset': True})
        self.reset_returned = True
        return returned

    def guard(self):
        if self.failure and self.reset_returned:
            raise RuntimeError('intentional_unit_guard_after_actual_native_reset')


class OffsetAdapter:
    """Unit instrumentation only: second half keeps global decision order."""
    def __init__(self, boundary, offset):
        self.boundary, self.offset = boundary, offset

    def __getattr__(self, name):
        return getattr(self.boundary, name)

    def before_step(self, previous, decision):
        return self.boundary.before_step(previous, decision + self.offset)

    def reconcile(self, result, previous, decision):
        return self.boundary.reconcile(result, previous, decision + self.offset)

    def record_step(self, result, previous, decision):
        return self.boundary.record_step(result, previous, decision + self.offset)

    def record_reset(self, indices, infos, decision):
        return self.boundary.record_reset(indices, infos, decision + self.offset)


def batch_digest(batch):
    return digest({f.name: None if getattr(batch, f.name) is None else getattr(batch, f.name).numpy()
                   for f in fields(batch)})


def verify_gae(batch):
    names = ('rewards', 'values', 'next_values', 'terminated', 'truncated')
    args = [getattr(batch, n) if n in ('terminated', 'truncated') else getattr(batch, n).double() for n in names]
    actual, returns = ppo.compute_gae(*args, PINNED_PPO.gamma, PINNED_PPO.gae_lambda)
    expected = torch.tensor(scalar_gae(*[x.tolist() for x in args], PINNED_PPO.gamma,
                                     PINNED_PPO.gae_lambda), dtype=torch.float64)
    torch.testing.assert_close(actual, expected, rtol=0, atol=1e-12)
    torch.testing.assert_close(returns, expected + args[1], rtol=0, atol=1e-12)
    # Perturb every next-episode reward after each actual boundary. That later
    # episode must not affect the advantage on or before the boundary.
    checked = 0
    for slot in range(batch.shape[1]):
        ends = torch.nonzero(batch.terminated[:, slot] | batch.truncated[:, slot]).flatten().tolist()
        for t in ends:
            if t + 1 == batch.shape[0]:
                continue
            changed = args[0].clone()
            changed[t+1:, slot] += 123.0
            perturbed, _ = ppo.compute_gae(changed, *args[1:], PINNED_PPO.gamma, PINNED_PPO.gae_lambda)
            torch.testing.assert_close(perturbed[:t+1, slot], actual[:t+1, slot], rtol=0, atol=0)
            checked += 1
    return {'scalar_oracle_max_abs_error': float((actual-expected).abs().max()),
        'no_next_episode_reward_leak_checks': checked,
        'death_boundaries': int(batch.terminated.sum()), 'alive_cutoffs': int(batch.truncated.sum()),
        'continuations': int((~(batch.terminated | batch.truncated)).sum())}


def scenario(name, enabled, pieces, failure=False):
    torch.manual_seed(777)
    env = TraceEnv(native.VecDodgeEnv(**OPTIONS), failure)
    initial_info = env.episode_info()
    assert env.batch_info()['seed_mode'] == {'mode': 'training', 'run_seed': 777}
    assert all(r['seed']['evaluation'] is False for r in initial_info)
    boundary = CurriculumAdapter(env, enabled=enabled, digest=SYNTHETIC_DIGEST, replica=1,
                                 exclusion_ranges=EXCLUSIONS)
    initial_assignments = copy.deepcopy(boundary.assignment_events)
    model = FixedTinyPolicy(env)
    parameters_before = digest({k: v.detach().numpy() for k, v in model.state_dict().items()})
    original_audit = ppo._audit_step
    def audit(result, size, cap):
        assert equal(result['info'], env.inner.episode_info())
        for slot, info in enumerate(result['info']):
            assert bool(result['terminated'][slot]) == info['terminated']
            assert bool(result['truncated'][slot]) == info['truncated']
        # Native operation and adapter may synchronize only masks and EpisodeInfo.
        for key in result.keys() - {'truncated', 'info'}:
            assert equal(result[key], env.raw[key]), key
        audited = original_audit(result, size, cap)
        env.rows[-1].update(synchronized_before_audit_and_storage=True,
            terminated=result['terminated'].tolist(), truncated=result['truncated'].tolist(),
            raw_rewards=result['rewards'].tolist(), score_delta_raw_fixed=result['score_delta_raw_fixed'].tolist(),
            alive_raw_frames=result['alive_raw_frames'].tolist(), elapsed_raw_frames=result['elapsed_raw_frames'].tolist(),
            episode_info=copy.deepcopy(result['info']), final_observations_digest=digest(result['observations']))
        env.audit_pending = True
        return audited
    ppo._audit_step = audit
    boundary.begin_update(1)
    collections, offset, current = [], 0, None
    expected_failure = None
    row = {'name': name, 'enabled': enabled, 'pieces': pieces, 'initial_info': initial_info,
        'initial_batch_info': env.batch_info(), 'initial_assignments': initial_assignments, 'complete': False}
    try:
        for count in pieces:
            adapter = boundary if offset == 0 else OffsetAdapter(boundary, offset)
            collection = ppo.collect_rollout(model, env, count, 'cpu', observation=current,
                config=PINNED_PPO, check_guard=env.guard, boundary_adapter=adapter)
            collections.append(collection)
            current, offset = collection.observations, offset + count
        assert not failure, 'expected post-reset guard did not occur'
        # Concatenate unit buffers for a single scalar oracle; recurrence crosses
        # the artificial 128 boundary but stops at actual death/cutoff masks.
        batch = ppo.RolloutBatch(**{f.name: torch.cat([getattr(c.batch, f.name) for c in collections])
            for f in fields(ppo.RolloutBatch)})
        assert batch.shape == (256, 8)
        for t, record in enumerate(env.rows):
            assert batch.actions[t].tolist() == record['actions']
            assert batch.terminated[t].tolist() == record['terminated']
            assert batch.truncated[t].tolist() == record['truncated']
            for key in ('raw_rewards', 'score_delta_raw_fixed', 'alive_raw_frames', 'elapsed_raw_frames'):
                torch.testing.assert_close(getattr(batch, key)[t], torch.tensor(record[key], dtype=getattr(batch, key).dtype), rtol=0, atol=0)
            expected = torch.tensor(record['final_values'])
            expected[batch.terminated[t]] = 0
            torch.testing.assert_close(batch.next_values[t], expected, rtol=0, atol=0)
        assert torch.count_nonzero(batch.next_values[batch.terminated]) == 0
        assert all(not getattr(batch, f.name).requires_grad and getattr(batch, f.name).device.type == 'cpu' for f in fields(batch))
        row['gae'] = verify_gae(batch)
        saved = batch_digest(batch)
        if enabled:
            assert sum(len(r['indices']) for r in env.cutoffs) >= 1, 'fixed normal-start training fixture has no actual H1000 survivor; stop, no replacement'
        else:
            assert not env.cutoffs and not bool(batch.truncated.any())
        # Caller mutation of owned native return buffers must not alter storage
        # or native observations; production state remains untouched.
        native_observation_digest = digest(env.inner.observations())
        for array in env.last['observations'].values():
            if isinstance(array, np.ndarray):
                array.fill(0)
        assert digest(env.inner.observations()) == native_observation_digest
        assert batch_digest(batch) == saved
        row.update(batch_digest=saved, final_storage_owned=True, full256_decisions=True,
            decision255=env.rows[255], completed_episodes=[r for c in collections for r in c.completed_episodes],
            buffer_end_digests=[batch_digest(c.batch) for c in collections])
        if len(pieces) == 2:
            # Each half's continuation is actual native state, with no intervening
            # reset, scheduler call, or constructor at the buffer seam.
            for key in OBS_KEYS:
                torch.testing.assert_close(collections[1].batch.__dict__[key][0],
                    torch.as_tensor(collections[0].observations[key]), rtol=0, atol=0)
            row['cross_buffer_observations_exact'] = True
        row['complete'] = True
    except RuntimeError as exc:
        if not failure or str(exc) != 'intentional_unit_guard_after_actual_native_reset':
            raise
        expected_failure = str(exc)
        snapshot = boundary.snapshot()
        reset_slots = env.resets[-1]['indices']
        rows = {r['slot']: r for r in snapshot['in_flight']}
        for slot in reset_slots:
            assert rows[slot]['assignment_status'] == 'unassigned_unaudited'
            assert rows[slot]['generation'] is rows[slot]['horizon'] is rows[slot]['ordinal'] is None
        assert snapshot['normal_reset_count'] == 0
        assert snapshot['returned_reset_startup_frames_unaudited'] == 13 * len(reset_slots)
        assert snapshot['returned_work_not_accepted_by_audit'] == 0
        row.update(complete=True, expected_failure=expected_failure,
            unassigned_reset_slots=reset_slots, no_reassignment_or_retry=True)
    finally:
        ppo._audit_step = original_audit
        snapshot = boundary.snapshot()
        assert snapshot['completed_updates'] == 0 and snapshot['pending_update'] == 1
        assert snapshot['boundaries'] == []
        if enabled:
            assert snapshot['scheduler']['generation'] == snapshot['scheduler']['update'] == 0
        assert len(boundary.assignment_events) == 8 + snapshot['normal_reset_count']
        assert [r['ordinal'] for r in boundary.assignment_events] == (list(range(len(boundary.assignment_events))) if enabled else [None]*len(boundary.assignment_events))
        assert snapshot['gameplay_frames_including_fatal'] == sum(sum(r.get('elapsed_raw_frames', [])) for r in env.rows)
        assert snapshot['reset_startup_frames'] == 13*snapshot['normal_reset_count']
        assert sum(r['executed_gameplay_frames'] for r in snapshot['interval_exposure']) == snapshot['gameplay_frames_including_fatal']
        assert parameters_before == digest({k: v.detach().numpy() for k, v in model.state_dict().items()})
        row.update(snapshot=snapshot, native_steps=env.steps, native_cutoffs=env.cutoffs,
            combined_resets=env.resets, step_evidence=env.rows, optimizer_steps=0,
            fixed_model_parameters_unchanged=True, actual_native_training_metadata=True,
            expected_failure=expected_failure, scheduler_unpromoted_without_PPO=True)
        write('results/' + name + '.json', row)
    print(json.dumps({'scenario': name, 'complete': row['complete'], 'steps': env.steps,
        'cutoff_survivors': sum(len(r['indices']) for r in env.cutoffs),
        'true_deaths': sum(sum(r.get('terminated', [])) for r in env.rows),
        'resets': len(env.resets), 'expected_failure': expected_failure}), flush=True)
    return row


report = {'scope': 'actual native, synthetic CPU units only; no runtime qualification',
          'options': OPTIONS, 'validated_historical_floor_union': EXCLUSIONS,
          'synthetic_assignment_digest': SYNTHETIC_DIGEST, 'scenarios': [], 'complete': False}
try:
    for args in [('enabled_full256', True, [256]), ('disabled_full256', False, [256]),
                 ('enabled_split128_128', True, [128, 128]),
                 ('enabled_post_reset_guard_failure', True, [256], True)]:
        row = scenario(*args)
        report['scenarios'].append({k: row[k] for k in ('name', 'complete', 'native_steps', 'optimizer_steps', 'scheduler_unpromoted_without_PPO')})
    full = json.loads((OUT / 'results/enabled_full256.json').read_text())
    split = json.loads((OUT / 'results/enabled_split128_128.json').read_text())
    assert full['batch_digest'] == split['batch_digest'], 'split buffer altered actions/storage/trajectory'
    control = json.loads((OUT / 'results/disabled_full256.json').read_text())
    assert full['initial_info'] == control['initial_info']
    first_cutoff = full['native_cutoffs'][0]['global_decision']
    assert full['step_evidence'][:first_cutoff] == control['step_evidence'][:first_cutoff]
    # At the cutoff decision the raw native result is identical before enabled
    # reconciliation. Later paths intentionally diverge after actual resets.
    assert full['step_evidence'][first_cutoff]['raw_final_digest'] == control['step_evidence'][first_cutoff]['raw_final_digest']
    report.update(complete=True, enabled_disabled_initial_and_raw_prefix_exact=True,
        split_full_batch_exact=True, torch_version=torch.__version__, numpy_version=np.__version__,
        python=sys.version, cuda_initialized=torch.cuda.is_initialized(), mps_used=False,
        optimizer_steps=0, no_checkpoint_or_accepted_model_import=True)
finally:
    write('results/integration-summary.json', report)
