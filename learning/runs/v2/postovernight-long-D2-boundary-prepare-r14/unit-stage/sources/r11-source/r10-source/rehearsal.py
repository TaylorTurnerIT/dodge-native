#!/usr/bin/env python3
"""One startup-only real runtime reconstruction. Never launches production worker.

No checkpoint deserialization, environment, inference, PPO, gradient or optimizer.
Unchanged identity._architecture_description constructs only a teacher architecture,
with its original internal CPU RNG save/restore. No entry-control proof is claimed.
"""
import time
START=time.monotonic()
from pathlib import Path
import os
import sys
import traceback
import boundary_integrity as integrity
import long_d2 as c
import lifecycle as life
H=Path(__file__).resolve().parent


def main():
    manifest=c.read_json(Path(sys.argv[1]));out=Path(manifest['output']);out.mkdir()
    root=H/'capsule-final';sys.path[0]=str(root/c.PREPARE_REL)
    ctx=c.capsule_context(root,verify_inputs=False);p,config,base,identity,pins,lease=ctx
    policy=dict(identity['runtime_policy'],pycache_prefix=manifest['validation_only_pycache_prefix'])
    c.require(c.sha(H/'rehearsal.py')==manifest['helper_sha256'],'Frozen rehearsal helper differs')
    life.POOL=life.FailurePool(START,120)
    latch=life.ProcessLatch();latch.install(START+120)
    imported={};observations=[];guard=None;code=1;result={}
    def verify():
        observation=integrity.verify(ctx,root)
        if imported:
            actual=imported['identity'].check_frozen(c.ORIGINAL_ROOT/p['base_identity_path'],p['base_identity_sha256'],base,c.ORIGINAL_ROOT)
            c.require(actual==p['base_identity'],'Real unchanged frozen identity differs')
            origins=c.check_module_origins(identity,root)
            runtime=integrity.runtime_check(identity,c.ORIGINAL_ROOT,cache_policy=policy)
            observation.update(genuine_legacy=True,project_origins=origins,runtime=runtime)
        else:observation['runtime']=integrity.runtime_check(identity,c.ORIGINAL_ROOT,cache_policy=policy)
        observations.append(observation)
        return observation
    try:
        with (out/'resources.jsonl').open('x') as resources:
            guard=c.Guard(START+120,latch.check,verify,resources)
            guard.start()
            sys.path.insert(0,str(c.ORIGINAL_ROOT/'python'))
            import torch
            import numpy as np
            import dodge_rl
            from dodge_rl import checkpoints as ckpt, identity as old_identity, dev_eval
            from dodge_rl.models.teacher import OmniscientEntityTeacher
            from dodge_rl.ppo import PPOConfig, collect_rollout, ppo_update
            from dodge_rl.train_teacher import (seed_initialization, make_optimizer, TrainingEnvLog,require_raw_diagnostics)
            imported.update(identity=old_identity)
            c.require(not os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK'),'MPS fallback forbidden')
            c.require(torch.backends.mps.is_available(),'MPS unavailable')
            torch.set_num_threads(4);c.require(torch.get_num_threads()==4,'Torch threads differ')
            guard.mps=lambda:int(torch.mps.driver_allocated_memory())
            guard.check(force=True)
            # Final live rebuild and loaded origins are mandatory while runtime exists.
            guard.check(force=True)
            guard.close()
            result=dict(status='passed',observations=observations,resources=guard.receipt(),boundaries=guard.boundaries,
                actual_native_origins=observations[-1]['runtime']['native_origins'],genuine_unchanged_check_frozen=True,
                no_D1_checkpoint_deserialization=True,no_environment_inference_gradient_optimizer=True,
                architecture_only_constructor_with_original_CPU_RNG_save_restore=True,entry_control_proven=False,
                validation_only_cache_override=policy['pycache_prefix'],production_cache_used=False,
                MPS_observation_scope='real driver_allocated_memory after torch import; unavailable pre-import, no fabricated ML metadata',
                helper_sha256=manifest['helper_sha256'])
            code=0
    except BaseException as error:
        result=dict(status='failed',error=repr(error),traceback=traceback.format_exc(),observations=observations,
                    resources=None if guard is None else guard.receipt())
    finally:
        if guard is not None:
            guard.event.set()
            if guard.thread is not None:guard.thread.join(timeout=.5)
        result['elapsed_seconds']=time.monotonic()-START
        c.save(out/'rehearsal-result.json',result)
    os._exit(code)

if __name__=='__main__':main()
