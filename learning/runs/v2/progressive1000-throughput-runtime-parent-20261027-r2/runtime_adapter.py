"""Deferred real runtime adapter. Importing this file executes stdlib only.

Only worker_cli creates this adapter, after external registration/source/lease/
marker validation. No runtime call in this preparation has been executed.
"""
from __future__ import annotations
import ast
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
    c.need(path == c.HERE / 'runtime' / relative,
           'loaded runtime module origin differs: ' + relative)
    codes = binding._definitions(path.read_bytes(), path, names)
    binding._bind_functions(module.__dict__, codes, names, path)


def authenticate_class(module, name):
    path = Path(module.__file__).resolve()
    source = path.read_bytes()
    code = binding._definitions(source, path, (name,))[name]
    expected = {item.co_name:item for item in code.co_consts if isinstance(item,types.CodeType)}
    definition = next(node for node in ast.parse(source, filename=str(path)).body
                      if isinstance(node,ast.ClassDef) and node.name == name)
    kinds = {}
    for node in definition.body:
        if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            continue
        decorators = node.decorator_list
        c.need(not decorators or (len(decorators) == 1 and isinstance(decorators[0],ast.Name)
               and decorators[0].id in {'staticmethod','property'}),
               'unsupported runtime class descriptor: '+name+'.'+node.name)
        kinds[node.name] = (types.FunctionType if not decorators else
                            {'staticmethod':staticmethod,'property':property}[decorators[0].id])
    c.need(set(kinds) == set(expected),'runtime class definitions differ: '+name)
    loaded = getattr(module,name)
    c.need(inspect.isclass(loaded) and inspect.getsourcefile(loaded) == str(path), 'runtime class origin differs')
    for method, body in expected.items():
        function = inspect.getattr_static(loaded,method)
        c.need(type(function) is kinds[method], 'runtime class descriptor differs: '+name+'.'+method)
        if type(function) is staticmethod:
            function = function.__func__
        elif type(function) is property:
            c.need(function.fset is None and function.fdel is None,
                   'runtime class property differs: '+name+'.'+method)
            function = function.fget
        c.need(inspect.isfunction(function) and function.__globals__ is module.__dict__
               and binding._code_signature(function.__code__) == binding._code_signature(body),
               'runtime class method differs: '+name+'.'+method)


def seed_constructor(seed,numpy_api,torch_api):
    # Bind the frozen helper body without importing train_teacher or its runtime.
    path = c.HERE/'runtime'/'dodge_rl/train_teacher.py'
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
        self.curriculum_module = importlib.import_module('dodge_rl.curriculum')
        self.teacher = importlib.import_module('dodge_rl.models.teacher')
        self.identity_module = importlib.import_module('dodge_rl.identity')
        c.need(Path(self.game.__file__).resolve() == Path(runtime) / 'dodge_rl/__init__.py', 'native package origin differs')
        c.need(dict(python=sys.version.split()[0], torch=str(self.torch.__version__), numpy=str(self.np.__version__)) == reg['runtime_versions'], 'loaded runtime versions differ')
        c.need(self.torch.backends.mps.is_available(), 'MPS unavailable')
        authenticate_module(self.ckpt, 'dodge_rl/checkpoints.py', binding.CHECKPOINT_FUNCTIONS + ('load_checkpoint','save_checkpoint','episode_resume_state','_cpu_copy'))
        authenticate_module(self.ppo_module, 'dodge_rl/ppo.py', ('collect_rollout','ppo_update'))
        authenticate_class(self.teacher,'OmniscientEntityTeacher')
        authenticate_class(self.teacher,'CustomTransformerLayer')
        authenticate_class(self.curriculum_module,'CurriculumAdapter')
        authenticate_class(self.curriculum_module,'PreparedUpdates')
        for name, module in tuple(sys.modules.items()):
            if name == 'dodge_rl' or name.startswith('dodge_rl.'):
                path = Path(module.__file__).resolve()
                c.need(path.is_relative_to(Path(runtime)),'loaded module escaped shared runtime: '+name)
                relative = str(path.relative_to(runtime))
                c.need(c.sha(path) == context['runtime_manifest']['files'].get(relative),
                       'loaded module/native pin differs: '+name)
        self.runner = runner_namespace()
        self.torch.set_num_threads(4)
        self.parent = self.ckpt.load_checkpoint(Path(context['parent']['checkpoint_path']), expected_sha256=c.references.ACCEPTED_CHECKPOINT_SHA256)
        self.ckpt.require_complete_update(self.parent)
        self.validate_parent()
        self.env = None
        self.callbacks = None
        self.boundary = self.prepared = None

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
        controls = c.episode_controls(self.reg['vector'],self.reg['initial_episode_indices'],self.reg['exclusion_union'])
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
        self.boundary = self.curriculum_module.CurriculumAdapter(self.env,
            enabled=self.reg['curriculum_enabled'],digest=self.reg['vector']['vector_sha256'],
            replica=self.reg['replica'],exclusion_ranges=self.reg['exclusion_union'])
        self.pending_reset_seeds = {}
        self.boundary.reset_preflight = self.preflight_reset
        self.boundary.reset_verifier = self.verify_reset
        self.prepared = self.curriculum_module.PreparedUpdates(self.model,self.optimizer,self.boundary,
            config=self.ppo,device=self.reg['backend'])

    def preflight_reset(self, indices, ended_info):
        """Predict the whole next seed batch before any reset constructor mutates."""
        ranges=c.validate_union(self.reg['exclusion_union'])
        predicted={}
        seen=set(self.boundary.consumed_actual_seeds)
        for slot in indices:
            episode=ended_info[slot]['seed']['episode']+1
            value=c.seed_metadata(self.reg['vector']['seeds']['env_master_seed'],slot,episode,ranges)
            seed=value['first_actual_seed']
            c.need(seed not in seen,'future actual episode seed collision; no replacement')
            seen.add(seed)
            predicted[slot]=dict(slot=slot,episode=episode,counter=value['rejection_counter'],
                                 actual_seed=seed,evaluation=False)
        self.pending_reset_seeds=predicted

    def verify_reset(self,indices,infos):
        c.need(len(indices)==len(infos),'returned reset seed metadata missing')
        for slot,info in zip(indices,infos,strict=True):
            c.need(info['seed']==self.pending_reset_seeds.get(slot),'returned reset seed differs from preconstruction prediction')
        self.pending_reset_seeds={}

    def update(self, guard, progress, journal_collection_events):
        """Journal once before PPO; propagate callback failures without retry.

        The worker owns durable writes. The synchronous callback receives detached
        event lists, so payload mutations cannot alter the collection. Its return
        value is ignored; an exception aborts before PPO and candidate eligibility.
        """
        collection, value, boundary = self.prepared.update_once(check_guard=guard,
            journal_collection_events=journal_collection_events,validate_metrics=self.runner['finite_tree'])
        progress.clear()
        progress.update(self.prepared.progress)
        c.need(progress.get('complete') is True and progress.get('in_update') is False,
               'incomplete PPO update')
        return value, collection, boundary

    def snapshot(self):
        return None if self.prepared is None else self.prepared.snapshot()

    def integrity_checkpoint(self, out, local, counters, registration_sha):
        from successor_identity import learner_identity
        c.need(self.prepared.state == 'ready' and self.boundary.completed_updates == local,
               'integrity checkpoint requires a completed global boundary')
        before = dict(model=fingerprint(self.model.state_dict()), Adam=fingerprint(self.optimizer.state_dict()),
                      RNG=fingerprint(self.callbacks['rng_capture']()), env=fingerprint([self.env.episode_info(),self.env.batch_info()]))
        next_indices, abandoned = self.ckpt.episode_resume_state(self.env,64)
        identity = learner_identity(self.reg,registration_sha)
        state = dict(version='teacher_checkpoint_v1',schema='progressive1000_integrity_checkpoint_v1',
            resume_mode='fresh_env',tag='integrity',training_eligible=False,promoted=False,
            formal_comparison_endpoint=(local==60),identity=identity,
            identity_sha256=self.identity_module.identity_hash(identity),
            parent_lineage=dict(checkpoint_sha256=c.references.ACCEPTED_CHECKPOINT_SHA256,
                receipt_sha256=c.references.PARENT_RECEIPT_SHA256,
                native_sha256=self.parent['native_sha256'],runtime_sha256=self.parent['runtime_sha256'],
                model_Adam_RNG_fingerprints=dict(c.transition.EXPECTED_PARENT)),
            successor_runtime_manifest_sha256=self.reg['runtime_manifest_sha256'],
            model=self.ckpt._cpu_copy(self.model.state_dict()),optimizer=self.ckpt._cpu_copy(self.optimizer.state_dict()),
            rng=self.callbacks['rng_capture'](),next_episode_indices=next_indices,
            abandoned_current_episodes=abandoned,counters=copy.deepcopy(counters),
            phase_update=324+local,cumulative_update=372+local,global_update=local,
            update_progress=copy.deepcopy(self.prepared.progress),
            curriculum_state=self.boundary.snapshot(),automatic_selection=False,
            parent_checkpoint_sha256=c.references.ACCEPTED_CHECKPOINT_SHA256)
        c.need(all(g['lr']==3e-5 for g in state['optimizer']['param_groups']), 'saved LR is not constant')
        path=out/f'checkpoint-global-{local:03d}-integrity.pt'
        digest=self.ckpt.save_checkpoint(path,state)
        after=dict(model=fingerprint(self.model.state_dict()),Adam=fingerprint(self.optimizer.state_dict()),
                   RNG=fingerprint(self.callbacks['rng_capture']()),env=fingerprint([self.env.episode_info(),self.env.batch_info()]))
        c.need(before==after,'integrity save changed live state')
        return dict(path=str(path),sha256=digest,global_update=local,phase_update=324+local,
                    cumulative_update=372+local,formal_comparison_endpoint=(local==60),
                    training_eligible=False,promoted=False,automatic_selection=False)

    def close(self):
        if self.env is not None:
            self.prepared = self.boundary = self.env = None  # Native ownership ends here; supervisor verifies cleanup.
