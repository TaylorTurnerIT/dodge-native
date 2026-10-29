"""Single-use frozen-policy diagnostic worker; parent envelope is mandatory."""
from __future__ import annotations
import argparse, gc, importlib, importlib.util, json, os, random, resource, sys, time
from pathlib import Path
import binding as b
import screen


def emit(stream, value):
    stream.write(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n');stream.flush()


class Guard:
    def __init__(self, reg, started, torch, events, resources):
        self.reg,self.started,self.torch=reg,started,torch;self.events,self.resources=events,resources
        self.raw=self.constructors=self.steps=0;self.last=0.;self.peak_rss=self.peak_mps=0;self.group_counts={};self.condition_counts={};self.episode_raw={}
    def check(self, force=False):
        now=time.monotonic(); lim=self.reg['limits']
        b.need(now-self.started < lim['work_seconds'],'diagnostic work deadline')
        b.need(self.raw<=lim['raw_frames'] and self.constructors<=lim['constructors'] and self.steps<=lim['native_steps'],'diagnostic aggregate ceiling')
        b.need(not os.path.lexists(b.HERE/'cancel'),'parent cancellation')
        if force or now-self.last>=.2:
            b.check_lease(self.reg)
            rss=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*(1 if sys.platform=='darwin' else 1024)
            mps=int(self.torch.mps.driver_allocated_memory())
            b.need(rss<=lim['rss_bytes'] and mps<=lim['mps_bytes'],'worker RSS/MPS ceiling')
            self.peak_rss=max(self.peak_rss,rss);self.peak_mps=max(self.peak_mps,mps)
            emit(self.resources,dict(elapsed_seconds=now-self.started,rss_bytes=rss,mps_driver_bytes=mps));self.last=now
    def event(self, group, event):
        kind=event['kind']; rec=dict(group=group,kind=kind)
        condition=group.rsplit('-rep',1)[0];counts=self.group_counts.setdefault(group,dict(raw_frames=0,constructors=0,steps=0));condition_counts=self.condition_counts.setdefault(condition,dict(raw_frames=0,constructors=0,steps=0))
        if kind=='constructor':
            self.raw+=event['info']['startup_frames'];self.constructors+=1;counts['raw_frames']+=event['info']['startup_frames'];counts['constructors']+=1;condition_counts['raw_frames']+=event['info']['startup_frames'];condition_counts['constructors']+=1
            self.episode_raw[(group,event['episode_index'])]=event['info']['startup_frames']
            rec.update(episode_index=event['episode_index'],startup_frames=event['info']['startup_frames'],seed=event['info']['seed']['actual_seed'])
        elif kind=='step':
            self.raw+=event['elapsed_raw_frames'];self.steps+=1;counts['raw_frames']+=event['elapsed_raw_frames'];counts['steps']+=1;condition_counts['raw_frames']+=event['elapsed_raw_frames'];condition_counts['steps']+=1
            key=(group,event['episode_index']);self.episode_raw[key]+=event['elapsed_raw_frames']
            b.need(self.episode_raw[key]<=18013,'per-episode raw-frame cap exceeded')
            # Per-native-step counts stay in memory; only episode aggregates are journaled.
        elif kind=='completed': rec['row']=event['row']
        else: raise ValueError('unknown collector event')
        if kind!='step': emit(self.events,rec)
        lim=self.reg['condition_limits'][condition]
        b.need(condition_counts['raw_frames']<=lim['raw_frames'] and condition_counts['constructors']<=lim['constructors'] and condition_counts['steps']<=lim['native_steps'],'per-condition ceiling exceeded')
        b.need(self.raw<=self.reg['limits']['raw_frames'] and self.constructors<=self.reg['limits']['constructors'] and self.steps<=self.reg['limits']['native_steps'],'in-memory diagnostic ceiling exceeded')


def load_pinned_helper(path,digest,name):
    helper=Path(path).resolve();b.need(b.sha(helper)==digest,'helper pin differs: '+name)
    spec=importlib.util.spec_from_file_location('control_frequency_pinned_'+name,helper)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    b.need(Path(module.__file__).resolve()==helper,'pinned helper origin differs: '+name)
    return module

def load_fingerprint_helper(reg):
    module=load_pinned_helper(reg['fingerprint_helper_path'],reg['fingerprint_helper_sha256'],'fingerprints')
    b.need(callable(getattr(module,'fingerprint',None)), 'pinned fingerprint helper API differs')
    return module.fingerprint


def load_frozen_policy(reg,torch,ckpt,teacher,fingerprint):
    """Shared real load path for bounded startup qualification and exact run."""
    path=Path(reg['checkpoint_path']).resolve()
    b.need(b.sha(path)==reg['checkpoint_sha256'],'checkpoint bytes differ before restore')
    state=ckpt.load_checkpoint(path,expected_sha256=reg['checkpoint_sha256'])
    ckpt.require_complete_update(state)
    b.need(state.get('global_update')==420,'checkpoint update differs')
    model=teacher.OmniscientEntityTeacher().to(reg['backend'])
    model.load_state_dict(state['model'],strict=True);model.eval();model._expanded_eval_device=reg['backend']
    del state
    b.need(fingerprint(model.state_dict())==reg['model_fingerprint'],'checkpoint model fingerprint differs')
    b.need(all(parameter.dtype==torch.float32 and parameter.device.type==reg['backend'] for parameter in model.parameters()), 'model dtype/device differs')
    return model


def authenticate_runtime(reg):
    b.need(not any(name=='dodge_rl' or name.startswith('dodge_rl.') for name in sys.modules),'runtime must start unloaded')
    sys.path.insert(0,reg['runtime_root'])
    np=importlib.import_module('numpy');torch=importlib.import_module('torch')
    game=importlib.import_module('dodge_rl');ckpt=importlib.import_module('dodge_rl.checkpoints')
    teacher=importlib.import_module('dodge_rl.models.teacher')
    manifest=b.read(reg['runtime_manifest_path'])
    root=Path(reg['runtime_root']).resolve()
    for name,module in tuple(sys.modules.items()):
        if name=='dodge_rl' or name.startswith('dodge_rl.'):
            path=Path(module.__file__).resolve()
            b.need(path.is_relative_to(root) and b.sha(path)==manifest['files'].get(str(path.relative_to(root))),'loaded module origin or runtime pin differs')
    death=load_pinned_helper(reg['death_telemetry_path'],reg['death_telemetry_sha256'],'death_telemetry')
    b.need(callable(getattr(death,'death_fields',None)) and tuple(screen.NEURAL_INPUTS)==tuple(reg['neural_inputs']),'pinned inference helper contract differs')
    sys.modules['death_telemetry']=death
    versions=dict(python=sys.version.split()[0],numpy=str(np.__version__),torch=str(torch.__version__))
    b.need(versions==reg['runtime_versions'],'loaded dependency versions differ')
    b.need(torch.backends.mps.is_available(),'registered MPS unavailable')
    torch.set_num_threads(reg['torch_num_threads'])
    b.need(torch.get_num_threads()==reg['torch_num_threads'],'Torch thread count differs')
    return np,torch,game,ckpt,teacher


def run(envelope_path,envelope_sha):
    envelope,reg=b.load_envelope(envelope_path,envelope_sha);b.verify_bound(envelope,reg,preflight=True)
    b.save(reg['attempt_claim_path'],dict(schema='control_frequency_confirmation_attempt_v1',run_id=reg['run_id'],registration_sha256=envelope['registration_sha256'],pid=os.getpid()))
    out=Path(reg['output']);out.mkdir(exist_ok=False)
    result=dict(schema='control_frequency_confirmation_worker_v1',status='failed',run_id=reg['run_id'],registration_sha256=envelope['registration_sha256'],automatic_selection=False,promoted=False,training_eligible=False,completed_groups=[],rows_completed=0)
    with (out/'events.jsonl').open('x') as events,(out/'resources.jsonl').open('x') as resources:
        guard=None
        try:
            np,torch,game,ckpt,teacher=authenticate_runtime(reg)
            fingerprint=load_fingerprint_helper(reg)
            death=sys.modules['death_telemetry']
            b.need(tuple(screen.NEURAL_INPUTS)==tuple(reg['neural_inputs']),'model observation inputs differ')
            guard=Guard(reg,envelope['started'],torch,events,resources);guard.check(True)
            path=Path(reg['checkpoint_path']);caller_rng=ckpt.capture_rng('mps');grad=torch.is_grad_enabled()
            model=load_frozen_policy(reg,torch,ckpt,teacher,fingerprint);initial=fingerprint(model.state_dict());groups={};group_elapsed={};excluded=reg['evaluation_exclusions']
            try:
                for group in reg['order']:
                    guard.check(True);gid=f"{group['condition']}-rep{group['repetition']}";started=time.monotonic();before=guard.raw
                    action=reg['condition_map'][group['condition']]
                    controller_seed=group['controller_seed']
                    rng_before=fingerprint(ckpt.capture_rng('mps'))
                    if action['action_mode']=='sampled_categorical':
                        b.need(type(controller_seed)is int and controller_seed in reg['controller_seeds'],'sampled controller seed differs')
                        random.seed(controller_seed);np.random.seed(controller_seed%(2**32));torch.manual_seed(controller_seed);torch.mps.manual_seed(controller_seed)
                    rows=screen._production_rows(model,game.VecDodgeEnv,reg['neural_inputs'],death.death_fields,reg['seeds'],excluded,guard.check,
                        action_repeat=action['action_repeat'],action_mode=action['action_mode'],batch_size=reg['batch_size'],
                        event_sink=lambda event,g=gid:guard.event(g,event))
                    summary=screen.summarize(rows,reg['seeds'])
                    b.need(fingerprint(model.state_dict())==initial,'evaluation changed model weights')
                    b.need(b.sha(path)==reg['checkpoint_sha256'],'checkpoint bytes changed during evaluation')
                    value=dict(schema='control_frequency_confirmation_group_v1',group=group,condition=action,
                        checkpoint_sha256=reg['checkpoint_sha256'],runtime_manifest_sha256=reg['runtime_manifest_sha256'],
                        summary=summary,rows=rows,raw_frames_including_startup=guard.raw-before,
                        elapsed_seconds=time.monotonic()-started,rng_before_sha256=rng_before,
                        rng_after_sha256=fingerprint(ckpt.capture_rng('mps')),automatic_selection=False,promoted=False)
                    b.save(out/(gid+'.json'),value);groups[gid]=rows;group_elapsed[gid]=value['elapsed_seconds'];result['completed_groups'].append(gid);result['rows_completed']+=len(rows)
                    guard.check(True);del value
                    print(json.dumps(dict(status='fixed_policy_group_complete',group=gid,episodes=result['rows_completed'],elapsed_seconds=time.monotonic()-envelope['started'])),flush=True)
                row_conditions={k:[] for k in screen.CONDITIONS}
                for group in reg['order']:
                    key=group['condition'];gid=f"{key}-rep{group['repetition']}"
                    if key.startswith('sampled'): row_conditions[key].append(groups[gid])
                    else: row_conditions[key]=groups[gid]
                report=screen.analyze_conditions(row_conditions,reg['seeds'],bootstrap_draws=reg['bootstrap']['draws'],bootstrap_seed=reg['bootstrap']['seed'])
                report['registered_contrast_names']=reg['bootstrap']['contrasts'];report['registered_group_order']=reg['order'];report['condition_wall_seconds']={c:sum(group_elapsed[f"{g['condition']}-rep{g['repetition']}"] for g in reg['order'] if g['condition']==c) for c in screen.CONDITIONS};comparison_elapsed=time.monotonic()-envelope['started'];report['comparison_elapsed_seconds']=comparison_elapsed;b.save(out/'comparison.json',report)
                guard.check(True)
                result.update(status='completed',raw_frames_including_startup=guard.raw,constructors=guard.constructors,native_steps=guard.steps,
                    comparison_elapsed_seconds=comparison_elapsed,comparison_sha256=b.sha(out/'comparison.json'),peak_rss_bytes=guard.peak_rss,peak_mps_driver_bytes=guard.peak_mps)
            finally:
                ckpt.restore_rng(caller_rng,'mps');b.need(fingerprint(ckpt.capture_rng('mps'))==fingerprint(caller_rng),'caller RNG restore differs')
                b.need(torch.is_grad_enabled()==grad,'global gradient mode changed')
                del model;gc.collect();torch.mps.empty_cache()
        except BaseException as error:
            result['first_failure']=repr(error)
            if guard is not None: result.update(raw_frames_including_startup=guard.raw,constructors=guard.constructors,native_steps=guard.steps)
            raise
        finally:
            events.flush();os.fsync(events.fileno());resources.flush();os.fsync(resources.fileno())
            result['elapsed_seconds']=time.monotonic()-envelope['started'];b.save(out/'worker-result.json',result)
    return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--envelope',required=True);parser.add_argument('--envelope-sha256',required=True);args=parser.parse_args()
    raise SystemExit(run(args.envelope,args.envelope_sha256))
