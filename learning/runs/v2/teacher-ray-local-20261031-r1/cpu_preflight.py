"""One CPU readiness attestation for a frozen packet; no launch/lease mutation.

Run this copied script using the registration's lexical interpreter. Native
imports are inspected, but both constructor aliases are replaced by tripwires.
MPS APIs and global accelerator seeding are blocked before model construction.
"""

import argparse
import importlib
import importlib.metadata
from pathlib import Path
import sys
import traceback

import common as c
from fingerprints import fingerprint


def tripwire_factory():
    def forbidden(*args, **kwargs):
        raise RuntimeError('Native games/accelerator work forbidden in CPU preflight')
    return forbidden


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--registration',required=True)
    parser.add_argument('--sha256',required=True)
    args=parser.parse_args()
    reg=c.load_registration(args.registration,args.sha256)
    result_path=c.HERE/'CPU-runtime-preflight.json'
    failure_path=c.HERE/'CPU-preflight-first-failure.json'
    c.need(not result_path.exists() and not failure_path.exists(),'CPU preflight already consumed')
    c.need(not (c.HERE/'launch.claimed').exists()
           and not list((c.HERE/'outputs').rglob('*.claimed')),'Claimed packet refused')
    c.need(sys.executable==reg['interpreter'],'Use the registered lexical interpreter')
    try:
        sys.path.insert(0,reg['runtime_root'])
        import torch
        for name in ('manual_seed','seed','get_rng_state','set_rng_state','synchronize',
                     'empty_cache','current_allocated_memory','driver_allocated_memory',
                     'set_per_process_memory_fraction'):
            if hasattr(torch.mps,name):setattr(torch.mps,name,tripwire_factory())
        def cpu_seed(seed):return torch.random.default_generator.manual_seed(seed)
        torch.manual_seed=cpu_seed
        torch.cuda.manual_seed_all=tripwire_factory()
        torch.set_num_threads(1)
        native=importlib.import_module('dodge_rl')
        extension=importlib.import_module('dodge_rl._native')
        native.VecDodgeEnv=tripwire_factory()
        extension.VecDodgeEnv=tripwire_factory()
        for name in ('ppo','seeded_training','checkpoints','models.teacher',
                     'models.ray_teacher','ray_frontend','ray_migration'):
            importlib.import_module('dodge_rl.'+name)
        from dodge_rl.models.teacher import OmniscientEntityTeacher
        from dodge_rl.models.ray_teacher import RayGeometryTeacher
        from dodge_rl.ray_migration import migrate_adam
        from dodge_rl.checkpoints import load_checkpoint,require_complete_update
        state=load_checkpoint(Path(reg['checkpoint_path']),expected_sha256=reg['checkpoint_sha256'])
        require_complete_update(state)
        c.need(fingerprint(state['model'])==reg['model_fingerprint'] and
               fingerprint(state['optimizer'])==reg['adam_fingerprint'],'Checkpoint420 contents differ')
        cpu_seed(reg['replicas']['1']['constructor_seed'])
        legacy=OmniscientEntityTeacher()
        legacy.load_state_dict(state['model'],strict=True)
        rng=torch.get_rng_state().clone()
        model=RayGeometryTeacher(legacy,branch_seed=reg['replicas']['1']['branch_seed'])
        c.need(torch.equal(rng,torch.get_rng_state()),'Branch constructor changed CPU RNG')
        optimizer,manifest=migrate_adam(state['optimizer'],legacy,model,
            learning_rate=reg['ppo']['learning_rate'],adam_eps=reg['ppo']['adam_eps'])
        g=torch.zeros(1,1,14);g[:,:,4]=1
        e=torch.zeros(1,80,16);types=torch.zeros(1,80,dtype=torch.int64)
        mask=torch.zeros(1,80,dtype=torch.bool)
        with torch.no_grad():
            left,right=legacy(g,e,types,mask),model(g,e,types,mask)
        c.need(all(torch.equal(getattr(left,k),getattr(right,k)) for k in ('logits','values','latent')),
               'CPU warm-start outputs differ')
        c.need(all(torch.equal(a,b) for a,b in zip(left.attentions,right.attentions,strict=True)),
               'CPU warm-start attention differs')
        c.need(all(p.device.type=='cpu' for p in model.parameters()),'Non-CPU parameter')
        from dodge_rl.player_geometry import MAX_PLAYER_SIZE
        for player_size in (2.,4.,275249/65536,MAX_PLAYER_SIZE):
            g[0,0,0]=(2-64)/64;g[0,0,1]=(125-64)/64;g[0,0,4]=player_size/4
            with torch.no_grad():
                left,right=legacy(g,e,types,mask),model(g,e,types,mask)
            c.need(all(torch.equal(getattr(left,k),getattr(right,k)) for k in ('logits','values','latent')),
                   'Legal Q16 player size CPU warm-start differs')
        origins={}
        for name,module in list(sys.modules.items()):
            if name=='dodge_rl' or name.startswith('dodge_rl.'):
                path=str(Path(module.__file__).resolve())
                c.need(path in reg['input_pins'] and c.sha(path)==reg['input_pins'][path],
                       'Unpinned loaded module: '+name)
                origins[name]=dict(path=path,sha256=c.sha(path))
        members={name:reg['input_pins'][str(Path(reg['runtime_root'])/name)] for name in reg['runtime_members']}
        import hashlib
        runtime_digest=hashlib.sha256(c.canonical(members)).hexdigest()
        c.verify_pins(reg)
        c.need(not list((c.HERE/'empty-pycache').iterdir()),'Frozen cache changed')
        c.save(result_path,dict(status='CPU_runtime_import_and_420_migration_passed',
            registration_sha256=args.sha256,interpreter=sys.executable,
            interpreter_sha256=c.sha(sys.executable),runtime_manifest_sha256=runtime_digest,
            native_binary=origins['dodge_rl._native'],loaded_origins=origins,
            packages={p:importlib.metadata.version(p) for p in ('torch','numpy','pytest')},
            CPU_zero_gate_logits_values_latent_attention_exact=True,Adam_name_mapping=manifest,
            branch_constructor_CPU_RNG_unchanged=True,native_games=0,MPS_work=False,optimizer_steps=0,
            checkpoint_unchanged=c.sha(reg['checkpoint_path'])==reg['checkpoint_sha256'],
            limits='CPU/source evidence only; no independent acceptance, MPS/resource or full-path qualification.'))
        print(c.canonical(dict(status='CPU_preflight_passed',sha256=c.sha(result_path),
            runtime_manifest_sha256=runtime_digest,native_games=0,MPS_work=False)).decode())
        return 0
    except BaseException as error:
        c.save(failure_path,dict(status='CPU_preflight_failed_no_execution',error=repr(error),
            traceback=traceback.format_exc(),registration_sha256=args.sha256))
        raise


if __name__=='__main__':raise SystemExit(main())
