"""Deferred real runtime adapter. Importing this file executes stdlib only.

Only worker_cli creates this adapter, after external registration/source/lease/
marker validation. No runtime call in this preparation has been executed.
"""
from __future__ import annotations
import copy
import importlib
import inspect
import math
from pathlib import Path
import random
import sys
import time
import types

import contracts as c
import driver_binding as binding
from fingerprints import fingerprint


def runner_namespace():
    """Authenticate and compile definitions, never run the historical worker."""
    path, source = binding._read_pinned(c.ROOT, binding.RUNNER_RELATIVE, binding.RUNNER_SHA256)
    names = ('worker','need','finite_tree','validate_gradient_alignment',
             'ordered_episode_events','continuation_cumulative_counters')
    codes = binding._definitions(source, path, names)
    namespace = dict(__file__=str(path), __name__='_paired_pinned_runner', math=math, PPO=c.PPO)
    for name, code in codes.items():
        namespace[name] = types.FunctionType(code, namespace, name,
                                             ('',) if name == 'finite_tree' else None)
    binding._bind_functions(namespace, codes, names, path)
    return namespace


def authenticate_module(module, relative, names):
    path = Path(module.__file__).resolve()
    c.need(path == Path(c.read(c.HERE / 'input-manifest.json')['runtime_root']) / relative,
           'loaded runtime module origin differs: ' + relative)
    codes = binding._definitions(path.read_bytes(), path, names)
    binding._bind_functions(module.__dict__, codes, names, path)


def authenticate_class(module, name):
    path = Path(module.__file__).resolve()
    code = binding._definitions(path.read_bytes(), path, (name,))[name]
    expected = {item.co_name:item for item in code.co_consts if isinstance(item,types.CodeType)}
    loaded = getattr(module,name)
    c.need(inspect.isclass(loaded) and inspect.getsourcefile(loaded) == str(path), 'runtime class origin differs')
    for method, body in expected.items():
        function = getattr(loaded,method)
        c.need(inspect.isfunction(function) and function.__globals__ is module.__dict__
               and binding._code_signature(function.__code__) == binding._code_signature(body),
               'runtime class method differs: '+name+'.'+method)


def seed_constructor(seed,numpy_api,torch_api):
    # Bind the frozen helper body without importing train_teacher or its runtime.
    path = Path(c.read(c.HERE/'input-manifest.json')['runtime_root'])/'dodge_rl/train_teacher.py'
    body = binding._definitions(path.read_bytes(),path,('seed_initialization',))['seed_initialization']
    namespace = dict(random=random,np=numpy_api,torch=torch_api)
    types.FunctionType(body,namespace,'seed_initialization')(seed)


class RuntimeAdapter:
    """Concrete runtime, no caller-supplied restore/capture/transition callbacks."""
    def __init__(self, reg, context):
        self.reg, self.context = reg, context
        runtime = reg['runtime_root']
        c.need(not any(name == 'dodge_rl' or name.startswith('dodge_rl.') for name in sys.modules),
               'runtime must start unloaded')
        sys.path.insert(0, runtime)
        # Deferred imports are unreachable through validation-only and fake tests.
        self.np = importlib.import_module('numpy')
        self.torch = importlib.import_module('torch')
        self.game = importlib.import_module('dodge_rl')
        self.ckpt = importlib.import_module('dodge_rl.checkpoints')
        self.ppo_module = importlib.import_module('dodge_rl.ppo')
        self.teacher = importlib.import_module('dodge_rl.models.teacher')
        self.identity_module = importlib.import_module('dodge_rl.identity')
        c.need(Path(self.game.__file__).resolve() == Path(runtime) / 'dodge_rl/__init__.py', 'native package origin differs')
        c.need(dict(python=sys.version.split()[0], torch=str(self.torch.__version__), numpy=str(self.np.__version__)) == reg['runtime_versions'], 'loaded runtime versions differ')
        c.need(self.torch.backends.mps.is_available(), 'MPS unavailable')
        authenticate_module(self.ckpt, 'dodge_rl/checkpoints.py', binding.CHECKPOINT_FUNCTIONS + ('load_checkpoint','save_checkpoint','episode_resume_state','_cpu_copy'))
        authenticate_module(self.ppo_module, 'dodge_rl/ppo.py', ('collect_rollout','ppo_update'))
        authenticate_class(self.teacher,'OmniscientEntityTeacher')
        self.runner = runner_namespace()
        self.torch.set_num_threads(4)
        self.parent = self.ckpt.load_checkpoint(Path(context['parent']['checkpoint_path']), expected_sha256=c.references.ACCEPTED_CHECKPOINT_SHA256)
        self.ckpt.require_complete_update(self.parent)
        self.validate_parent()
        self.env = None
        self.callbacks = None

    def validate_parent(self):
        parent, receipt = self.parent, self.context['parent']
        c.need(parent['schema'] == 'd2_training_v3_checkpoint_v1' and parent['tag'] == 'candidate' and parent['phase'] == 'D2'
               and parent['phase_update'] == 324 and parent['local_update'] == 24, 'accepted candidate checkpoint schema differs')
        c.need(parent['identity_sha256'] == receipt['identity_sha256'] and self.identity_module.identity_hash(parent['identity']) == parent['identity_sha256'], 'accepted model identity differs')
        for key in ('config_sha256','policy_sha256','native_sha256','runtime_sha256'):
            c.need(parent[key] == receipt[key], 'parent checkpoint lineage differs: ' + key)
        c.need(parent['registration_sha256'] == receipt['registration_sha256'] and parent['parent_checkpoint_sha256'] == receipt['candidate_parent_checkpoint_sha256'], 'parent producing lineage differs')
        c.need(parent['next_episode_indices'] == self.reg['initial_episode_indices'] and parent['cumulative_counters'] == receipt['candidate_cumulative_counters'] and parent['counters'] == receipt['candidate_counters'], 'accepted parent counters/indices differ')
        c.need(fingerprint(parent['model']) == c.transition.EXPECTED_PARENT['model']
               and fingerprint(parent['optimizer']) == c.transition.EXPECTED_PARENT['Adam']
               and fingerprint(parent['rng']) == c.transition.EXPECTED_PARENT['RNG'], 'deserialized parent fingerprints differ')
        c.need(set(parent['rng']) == binding.RAW_RNG_KEYS and parent['rng']['sampling_backend'] == 'torch_global_mps', 'parent raw RNG backend differs')
        c.need(parent['identity']['config'] == c.read(self.context['manifest']['config_path']), 'parent config contents differ')

    def bootstrap(self):
        # R5 requires bound instances before its claim. This initialization is
        # disposable, not a restore of accepted state. All immutable gates ran.
        seeds = self.reg['vector']['seeds']
        seed_constructor(seeds['constructor_init_seed'],self.np,self.torch)
        self.model = self.teacher.OmniscientEntityTeacher().to(device='mps', dtype=self.torch.float32)
        c.need(self.model.architecture_description() == self.parent['identity']['architecture'], 'architecture differs')
        self.optimizer = self.torch.optim.Adam(self.model.parameters(), lr=3e-5, eps=c.PPO['adam_eps'])
        self.callbacks = binding.build_callbacks(project_root=c.ROOT, checkpoint_module=self.ckpt,
            runner_namespace=self.runner, parent_state=self.parent, model=self.model, optimizer=self.optimizer)
        c.need(not inspect.signature(self.callbacks['restore_trusted']).parameters, 'restore callback must take zero arguments')

    def source(self):
        # R5 consumes normalized labels; the raw receipt uses optimizer/rng.
        receipt = self.context['parent']
        self.validate_parent()
        return dict(receipt_sha256=c.references.PARENT_RECEIPT_SHA256,
                    checkpoint_sha256=c.references.ACCEPTED_CHECKPOINT_SHA256,
                    checkpoint_path=receipt['checkpoint_path'], receipt_path=str(c.ROOT / c.PARENT_RECEIPT),
                    checkpoint_fingerprints=dict(c.transition.EXPECTED_PARENT),
                    learner_fingerprints=dict(c.transition.EXPECTED_PARENT))

    def make_env(self):
        # Seed/exclusion controls are computed before any environment constructor.
        controls = c.episode_controls(self.reg['vector'])
        c.need(controls == self.context['controls'], 'environment seed controls changed')
        self.env = self.game.VecDodgeEnv(batch_size=64, action_repeat=4, difficulty=2,
            patterns_enabled=True, powerups_enabled=True, raw_frame_cap=18000,
            num_threads=4, chunk_size=8, render_pixels=False, auxiliary_targets=False,
            run_seed=self.reg['vector']['seeds']['env_master_seed'],
            initial_episode_indices=self.reg['initial_episode_indices'],
            excluded_seed_ranges=[tuple(row) for row in self.reg['exclusion_union']])
        actual = self.env.episode_info()
        c.need(len(actual) == 64, 'native initial slot count differs')
        for row, expected in zip(actual, controls, strict=True):
            seed = row['seed']
            c.need(seed['slot'] == expected['slot'] and seed['episode'] == expected['episode_index']
                   and seed['actual_seed'] == expected['first_actual_seed'] and seed['counter'] == expected['rejection_counter'], 'native initial seed differs')
        c.need(self.env.batch_info()['next_episode_indices'] == [v+1 for v in self.reg['initial_episode_indices']], 'native next indices differ')
        self.observation = self.env.observations()
        self.ppo = self.ppo_module.PPOConfig(**c.PPO)

    def update(self, guard, progress):
        collection = self.ppo_module.collect_rollout(self.model, self.env, 256, 'mps',
            observation=self.observation, config=self.ppo, check_guard=guard)
        self.observation = collection.observations
        value = self.ppo_module.ppo_update(self.model, self.optimizer, collection.batch, self.ppo,
            check_guard=guard, critic_diagnostics=True, gradient_alignment_diagnostics=True, progress=progress)
        self.runner['finite_tree'](value)
        self.runner['validate_gradient_alignment'](value['gradient_alignment_diagnostics'])
        diag = value['critic_diagnostics']
        c.need(diag['version'] == 'same_batch_critic_diagnostics_v1', 'critic diagnostics schema differs')
        old, direct = value['explained_variance'], diag['pre_update']['explained_variance']
        c.need((old is None and direct is None) or (old is not None and direct is not None and math.isclose(old,direct,rel_tol=1e-6,abs_tol=1e-6)), 'direct/legacy EV differs')
        c.need(progress.get('complete') is True and progress.get('in_update') is False, 'incomplete PPO update')
        return value, collection

    def candidate(self, out, local, counters, progress, registration_sha, started):
        c.need(progress['complete'] is True and progress['in_update'] is False, 'cannot save incomplete update')
        before = dict(model=fingerprint(self.model.state_dict()), Adam=fingerprint(self.optimizer.state_dict()),
                      RNG=fingerprint(self.callbacks['rng_capture']()), env=fingerprint([self.env.episode_info(), self.env.batch_info()]))
        next_indices, abandoned = self.ckpt.episode_resume_state(self.env,64)
        parent = self.context['parent']
        identity = copy.deepcopy(self.parent['identity'])
        identity.update(version='teacher_identity_v3',run_id=self.reg['run_id'],study_id=c.STUDY,
                        arm=self.reg['arm'],replica=self.reg['replica'],phase_update_start=324,phase_update_end=384,
                        run_seed=self.reg['vector']['seeds']['env_master_seed'],parent_checkpoint_sha256=c.references.ACCEPTED_CHECKPOINT_SHA256,
                        parent_terminal_receipt_sha256=c.references.PARENT_RECEIPT_SHA256,registration_sha256=registration_sha)
        # PPO controls are unchanged; schedule/seeds/exclusions are explicit study identity.
        identity['paired_study'] = dict(seed_vector=self.reg['vector']['seeds'],vector_sha256=self.reg['vector']['vector_sha256'],
                                       schedule=c.SCHEDULE,exclusion_union=self.reg['exclusion_union'],controller=c.transition.controller_lr(self.reg['arm'],372+local))
        wall = time.monotonic()-started
        state = dict(version='teacher_checkpoint_v1',schema='d2_training_v3_checkpoint_v1',resume_mode='fresh_env',tag='candidate',phase='D2',
            eligibility_status='provisional_pending_parent_terminal_receipt',training_eligible=False,promoted=False,
            identity=identity,identity_sha256=self.identity_module.identity_hash(identity),config_sha256=parent['config_sha256'],policy_sha256=parent['policy_sha256'],
            native_sha256=parent['native_sha256'],runtime_sha256=parent['runtime_sha256'],run_seed=self.reg['vector']['seeds']['env_master_seed'],
            registration_sha256=registration_sha,model=self.ckpt._cpu_copy(self.model.state_dict()),optimizer=self.ckpt._cpu_copy(self.optimizer.state_dict()),
            rng=self.callbacks['rng_capture'](),counters=dict(counters),inherited_counters=dict(parent['candidate_cumulative_counters']),
            cumulative_counters=self.runner['continuation_cumulative_counters'](parent['candidate_cumulative_counters'],counters),
            phase_update=324+local,local_update=local,update_progress=dict(progress),next_episode_indices=next_indices,
            abandoned_current_episodes=abandoned,parent_abandoned_current_episodes=self.parent['abandoned_current_episodes'],
            parent_sha256=c.references.ACCEPTED_CHECKPOINT_SHA256,parent_checkpoint_sha256=c.references.ACCEPTED_CHECKPOINT_SHA256,
            parent_run_id=parent['run_id'],parent_registration_sha256=parent['registration_sha256'],
            selected_parent_checkpoint_trajectory_baseline_seconds=parent['wall_accounting']['future_checkpoint_trajectory_baseline_seconds'],
            parent_completed_campaign_cost_baseline_seconds=parent['wall_accounting']['successful_ancestor_and_completed_campaign_cost_seconds'],
            current_iteration_observed_outer_seconds=wall,
            cumulative_selected_checkpoint_trajectory_wall_seconds=parent['wall_accounting']['future_checkpoint_trajectory_baseline_seconds']+wall,
            cumulative_successful_ancestor_and_completed_campaign_cost_seconds=parent['wall_accounting']['successful_ancestor_and_completed_campaign_cost_seconds']+wall)
        expected_lr = c.transition.controller_lr(self.reg['arm'],372+local)
        c.need(all(group['lr']==expected_lr for group in state['optimizer']['param_groups']), 'saved optimizer LR differs')
        path = out / f'checkpoint-{324+local:06d}-candidate.pt'
        digest = self.ckpt.save_checkpoint(path,state)
        after = dict(model=fingerprint(self.model.state_dict()), Adam=fingerprint(self.optimizer.state_dict()),
                     RNG=fingerprint(self.callbacks['rng_capture']()), env=fingerprint([self.env.episode_info(),self.env.batch_info()]))
        c.need(before == after, 'candidate save changed live learner/RNG/environment')
        return dict(checkpoint=path.name,checkpoint_sha256=digest,phase_update=324+local,local_update=local,
                    cumulative_update=372+local,training_eligible=False,promoted=False,automatic_selection=False,
                    update_progress=dict(progress),cumulative_counters=state['cumulative_counters'])

    def close(self):
        if self.env is not None:
            self.env = None  # VecDodgeEnv has no close().
