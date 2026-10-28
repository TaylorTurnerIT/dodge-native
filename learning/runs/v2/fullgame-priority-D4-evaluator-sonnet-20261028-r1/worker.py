"""Seven predetermined D4 terminal60 evaluations under one existing supervisor lease."""
from __future__ import annotations
import argparse
import gc
import importlib
import json
import os
from pathlib import Path
import random
import resource
import sys
import time

import binding as b
import comparison
from paired_statistics import paired_intervals


def emit(stream,value):
    stream.write(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n')


class Guard:
    def __init__(self,reg,started,torch,resources,events):
        self.reg,self.started,self.torch=reg,started,torch
        self.resources,self.events=resources,events
        self.raw=0;self.constructors=0;self.steps=0;self.last=float('-inf');self.peak_rss=self.peak_mps=0

    def check(self,force=False):
        now=time.monotonic();limits=self.reg['limits']
        b.need(now-self.started<limits['work_seconds'],'evaluation work deadline')
        b.need(self.raw<=limits['raw_frames'],'evaluation total raw-frame ceiling')
        b.need(self.constructors<=limits['constructors'] and self.steps<=limits['native_steps'],
               'evaluation constructor/native-step ceiling')
        b.need(not os.path.lexists(b.HERE/'cancel'),'parent cancellation')
        if force or now-self.last>=.2:
            b.check_lease(self.reg)
            rss=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*(1 if sys.platform=='darwin' else 1024)
            mps=int(self.torch.mps.driver_allocated_memory())
            b.need(rss<=limits['rss_bytes'] and mps<=limits['mps_bytes'],'evaluation RSS/MPS ceiling')
            self.peak_rss=max(self.peak_rss,rss);self.peak_mps=max(self.peak_mps,mps)
            emit(self.resources,dict(elapsed_seconds=now-self.started,rss_bytes=rss,mps_driver_bytes=mps))
            self.resources.flush();self.events.flush();self.last=now

    def journal(self,policy_id,event):
        kind=event['kind'];row=dict(kind=kind,policy_id=policy_id)
        if kind=='evaluation_constructor':
            self.raw+=event['info']['startup_frames'];self.constructors+=1
            row.update(episode_index=event['episode_index'],startup_frames=event['info']['startup_frames'],
                seed=event['info']['seed']['actual_seed'])
        elif kind=='evaluation_step':
            self.raw+=event['elapsed_raw_frames'];self.steps+=1
            row.update(episode_index=event['episode_index'],elapsed_raw_frames=event['elapsed_raw_frames'])
        elif kind=='evaluation_completed':row['row']=event['row']
        else:raise ValueError('unexpected collector event')
        emit(self.events,row)
        b.need(self.raw<=self.reg['limits']['raw_frames'] and self.constructors<=self.reg['limits']['constructors']
               and self.steps<=self.reg['limits']['native_steps'],'returned raw-frame/constructor/step ceiling')


def authenticate_runtime(reg,c):
    b.need(not any(name=='dodge_rl' or name.startswith('dodge_rl.') for name in sys.modules),
        'runtime must start unloaded')
    sys.path.insert(0,reg['runtime_root'])
    np=importlib.import_module('numpy');torch=importlib.import_module('torch')
    game=importlib.import_module('dodge_rl');ckpt=importlib.import_module('dodge_rl.checkpoints')
    teacher=importlib.import_module('dodge_rl.models.teacher')
    from runtime_adapter import authenticate_module,authenticate_class
    import driver_binding
    authenticate_module(ckpt,'dodge_rl/checkpoints.py',driver_binding.CHECKPOINT_FUNCTIONS+
        ('load_checkpoint','save_checkpoint','episode_resume_state','_cpu_copy'))
    authenticate_class(teacher,'OmniscientEntityTeacher');authenticate_class(teacher,'CustomTransformerLayer')
    b.need(dict(python=sys.version.split()[0],numpy=str(np.__version__),torch=str(torch.__version__))==reg['runtime_versions'],
        'loaded dependency versions differ')
    b.need(torch.backends.mps.is_available(),'registered MPS unavailable')
    manifest=b.read(b.SOURCE/'runtime-manifest.json')['files'];root=Path(reg['runtime_root'])
    for name,module in tuple(sys.modules.items()):
        if name=='dodge_rl' or name.startswith('dodge_rl.'):
            path=Path(module.__file__).resolve()
            b.need(path.is_relative_to(root) and b.sha(path)==manifest.get(str(path.relative_to(root))),
                'loaded clean runtime member/origin differs')
    return np,torch,game,ckpt,teacher


def run(envelope_path,envelope_sha):
    e,reg=b.load_envelope(envelope_path,envelope_sha);b.verify_bound(e,reg,preflight=True)
    # Spend the campaign before imports, checkpoint deserialization, seeds or games.
    b.save(reg['attempt_claim_path'],dict(schema='fullgame_priority_d4_evaluation_attempt_v1',
        run_id=reg['run_id'],registration_sha256=e['registration_sha256'],pid=os.getpid()))
    out=Path(reg['output']);out.mkdir(exist_ok=False)
    c=b.contracts();analysis=b.analysis()
    result=dict(schema='fullgame_priority_d4_evaluation_worker_v1',status='failed',run_id=reg['run_id'],
        registration_sha256=e['registration_sha256'],automatic_selection=False,promoted=False,
        training_eligible=False,completed_policies=[],rows_completed=0)
    with (out/'evaluation-events.jsonl').open('x') as events,(out/'resources.jsonl').open('x') as resources:
        guard=None
        try:
            np,torch,game,ckpt,teacher=authenticate_runtime(reg,c)
            from fingerprints import fingerprint
            from death_telemetry import death_fields
            from successor_identity import NEURAL_INPUTS
            b.need(tuple(NEURAL_INPUTS)==b.NEURAL_INPUTS,'clean neural input contract differs')
            guard=Guard(reg,e['started'],torch,resources,events);guard.check(force=True)
            all_rows={};caller_rng=ckpt.capture_rng('mps');grad_enabled=torch.is_grad_enabled()
            try:
                for policy in reg['policies']:
                    guard.check(force=True);policy_started=time.monotonic();raw_before=guard.raw
                    b.save(out/(policy['id']+'.claim'),dict(policy_id=policy['id'],
                        registration_sha256=e['registration_sha256'],checkpoint_sha256=policy['checkpoint_sha256']))
                    state=ckpt.load_checkpoint(Path(policy['checkpoint_path']),expected_sha256=policy['checkpoint_sha256'])
                    ckpt.require_complete_update(state);b.validate_checkpoint(state,policy)
                    if policy['id']==b.PARENT_ID:
                        b.need(fingerprint(state['model'])==c.transition.EXPECTED_PARENT['model'],'accepted parent model differs')
                    model=teacher.OmniscientEntityTeacher().to('mps')
                    model.load_state_dict(state['model'],strict=True);model.eval();model._expanded_eval_device='mps'
                    before=fingerprint(model.state_dict());del state
                    random.seed(reg['evaluation_rng_seed']);np.random.seed(reg['evaluation_rng_seed']%(2**32))
                    torch.manual_seed(reg['evaluation_rng_seed']);torch.mps.manual_seed(reg['evaluation_rng_seed'])
                    scratch_before=fingerprint(ckpt.capture_rng('mps'))
                    excluded=[]
                    for low,high in reg['exclusion_union']:
                        if low<b.SEEDS[0]:excluded.append((low,min(high,b.SEEDS[0]-1)))
                        if high>b.SEEDS[-1]:excluded.append((max(low,b.SEEDS[-1]+1),high))
                    rows=analysis._production_rows(model,game.VecDodgeEnv,NEURAL_INPUTS,death_fields,
                        reg['seeds'],excluded,guard.check,batch_size=64,
                        event_sink=lambda event,p=policy['id']:guard.journal(p,event))
                    summary=comparison.summarize(rows,reg['seeds'])
                    b.need(fingerprint(model.state_dict())==before,'evaluation changed weights')
                    b.need(b.sha(policy['checkpoint_path'])==policy['checkpoint_sha256'],'checkpoint bytes changed')
                    value=dict(schema='fullgame_priority_d4_terminal60_evaluation_v1',policy_id=policy['id'],
                        registration_sha256=e['registration_sha256'],checkpoint_sha256=policy['checkpoint_sha256'],
                        runtime_manifest_sha256=reg['runtime_manifest_sha256'],action_mode='sampled_categorical',
                        normal_start=True,cutoff_enabled=False,summary=summary,rows=rows,
                        raw_frames_including_startup=guard.raw-raw_before,elapsed_seconds=time.monotonic()-policy_started,
                        scratch_rng_before_sha256=scratch_before,scratch_rng_after_sha256=fingerprint(ckpt.capture_rng('mps')),
                        automatic_selection=False,promoted=False)
                    b.save(out/(policy['id']+'.json'),value);all_rows[policy['id']]=rows
                    result['completed_policies'].append(policy['id']);result['rows_completed']+=len(rows)
                    print(json.dumps(dict(status='fixed_policy_complete',policy_id=policy['id'],
                        completed_policies=len(all_rows),episodes=result['rows_completed'],elapsed_seconds=time.monotonic()-e['started'])),flush=True)
                    del model;gc.collect();torch.mps.empty_cache();guard.check(force=True)
                report=comparison.compare(all_rows,reg['seeds'])
                report['paired_conditional_seed_intervals']=paired_intervals(all_rows,reg['bootstrap'])
                guard.check(force=True)
                b.save(out/'comparison.json',report)
                result.update(status='completed',raw_frames_including_startup=guard.raw,constructors=guard.constructors,
                    native_steps=guard.steps,comparison_sha256=b.sha(out/'comparison.json'),peak_rss_bytes=guard.peak_rss,
                    peak_mps_driver_bytes=guard.peak_mps)
            finally:
                ckpt.restore_rng(caller_rng,'mps')
                b.need(fingerprint(ckpt.capture_rng('mps'))==fingerprint(caller_rng),'caller RNG restore differs')
                b.need(torch.is_grad_enabled()==grad_enabled,'global gradient mode changed')
        except BaseException as error:
            result['first_failure']=repr(error)
            if guard is not None:result['raw_frames_including_startup']=guard.raw
            raise
        finally:
            events.flush();os.fsync(events.fileno());resources.flush();os.fsync(resources.fileno())
            result['elapsed_seconds']=time.monotonic()-e['started']
            b.save(out/'worker-result.json',result)
    return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--envelope',required=True)
    parser.add_argument('--envelope-sha256',required=True);args=parser.parse_args()
    raise SystemExit(run(args.envelope,args.envelope_sha256))
