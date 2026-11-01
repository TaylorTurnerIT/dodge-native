"""Exactly one fixed-weight, clean, consumed-development evaluation."""
import argparse
import gc
import hashlib
import importlib
import os
import resource
import signal
import sys
import time
import traceback
import common as c
from analysis import analyze,forecast


def policy_seed(seed):
    return int.from_bytes(hashlib.sha256(f'dodge068/paired-policy-v1/{seed}/clean'.encode()).digest()[:8],'big')


def main():
    p=argparse.ArgumentParser();p.add_argument('--registration',required=True);p.add_argument('--sha256',required=True)
    args=p.parse_args();reg=c.load_registration(args.registration,args.sha256)
    review=c.review_gate(reg,args.sha256);c.check_lease(reg)
    dispatch=c.read(c.HERE/'output/dispatch.json')
    c.need(dispatch['registration_sha256']==args.sha256 and dispatch['review_sha256']==review
           and dispatch['expected_lease']==reg['expected_lease'],'Dispatch binding differs')
    out=c.HERE/'output/worker';c.save(out/'worker.claimed',dict(pid=os.getpid(),parent_pid=os.getppid(),registration_sha256=args.sha256))
    started=dispatch['started_monotonic'];last=-1.;cancelled=False;torch=None;journal=None;telemetry=None
    peaks=dict(peak_rss_bytes=0,peak_mps_driver_bytes=0);rows=[];batches=[];frames=0
    def cancel(*_):
        nonlocal cancelled
        cancelled=True
    signal.signal(signal.SIGTERM,cancel);signal.signal(signal.SIGINT,cancel)
    def guard():
        nonlocal last
        now=time.monotonic()
        c.need(not cancelled and now-started<reg['work_seconds'],'Evaluation work deadline/cancellation')
        if now-last>=.25:
            c.check_lease(reg)
            peaks['peak_rss_bytes']=max(peaks['peak_rss_bytes'],int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss))
            peaks['peak_mps_driver_bytes']=max(peaks['peak_mps_driver_bytes'],int(torch.mps.driver_allocated_memory()) if torch else 0)
            c.need(peaks['peak_rss_bytes']<reg['rss_bytes'] and peaks['peak_mps_driver_bytes']<reg['mps_bytes'],'Separate evaluation RSS/MPS ceiling')
            last=now
    try:
        guard();sys.path.insert(0,reg['runtime_root'])
        torch=importlib.import_module('torch');np=importlib.import_module('numpy')
        native=importlib.import_module('dodge_rl');teacher=importlib.import_module('dodge_rl.models.teacher')
        ray=importlib.import_module('dodge_rl.models.ray_teacher')
        from fingerprints import fingerprint
        c.need(torch.backends.mps.is_available(),'Native MPS required')
        torch.set_num_threads(reg['threads']);torch.set_num_interop_threads(1)
        torch.mps.set_per_process_memory_fraction(min(1.,reg['allocator_bytes']/torch.mps.recommended_max_memory()))
        torch.set_grad_enabled(False)
        c.save(out/'device.json',dict(device='mps',torch_version=torch.__version__,numpy_version=np.__version__,
            interpreter=sys.executable,runtime_root=reg['runtime_root'],native_path=native.__file__,
            gradients_enabled=torch.is_grad_enabled(),optimizer_constructed=False))
        journal=c.Journal(out/'episodes.jsonl');telemetry=c.Journal(out/'batches.jsonl')
        keys=('global_feats','entity_feats','entity_types','entity_mask')
        # Interleave all five fixed models: first 64 games/model qualify, then
        # the remaining registered 64/model. Outcomes never alter this schedule.
        for offset in (0,64):
            for artifact in reg['models']:
                guard();batch_start=time.monotonic();model_name=artifact['name']
                c.need(c.sha(artifact['path'])==artifact['sha256'],'Checkpoint changed')
                state=torch.load(artifact['path'],map_location='cpu',weights_only=False)
                with torch.random.fork_rng(devices=[]):
                    torch.random.default_generator.manual_seed(20261101068)
                    legacy=teacher.OmniscientEntityTeacher()
                    model=ray.RayGeometryTeacher(legacy) if model_name.endswith('rays') else legacy
                model.load_state_dict(state['model'],strict=True)
                initial=fingerprint(model.state_dict())
                c.need(initial==artifact['model_fingerprint'],'Accepted model fingerprint differs')
                del state
                model.requires_grad_(False);model.to('mps');model.eval()
                c.need(all(x.device.type=='mps' and not x.requires_grad for x in model.parameters()),'Fixed MPS parameters required')
                environments={};observations={};episode={};batch_frames=0;rounds=0;window_start=time.monotonic();window_rounds=0;max_window=0.
                for seed in reg['seeds'][offset:offset+64]:
                    guard()
                    env=native.VecDodgeEnv(batch_size=1,action_repeat=1,difficulty=2,patterns_enabled=True,powerups_enabled=True,
                        raw_frame_cap=18000,num_threads=1,chunk_size=1,render_pixels=False,auxiliary_targets=False,
                        seeds_by_slot=[[seed]],excluded_seed_ranges=[tuple(x) for x in reg['exclusions'] if x!=[3657433088,3657435135]])
                    info=env.episode_info()[0]
                    c.need(info['seed']['actual_seed']==seed and info['startup_frames']==13,'Normal-start seed identity differs')
                    environments[seed]=env;observations[seed]=env.observations()
                    episode[seed]=dict(generator=torch.Generator(device='cpu').manual_seed(policy_seed(seed)),decisions=0)
                del env
                while environments:
                    guard();active=sorted(environments)
                    arrays=[torch.from_numpy(np.concatenate([observations[s][k] for s in active],axis=0)) for k in keys]
                    if not getattr(model,'cpu_geometry_inputs',False):arrays=[x.to('mps') for x in arrays]
                    output=model(*arrays)
                    c.need(output.logits.device.type=='mps','Policy forward device differs')
                    probabilities=output.logits.softmax(-1).cpu()
                    c.need(bool(torch.isfinite(probabilities).all()),'Nonfinite policy')
                    for i,seed in enumerate(active):
                        row=episode[seed];requested=int(torch.multinomial(probabilities[i],1,generator=row['generator']).item())
                        result=environments[seed].step(np.array([requested],dtype=np.int64));info=result['info'][0]
                        c.need(info['seed']['actual_seed']==seed and int(result['elapsed_raw_frames'][0])==1,'Native seed/K1 drift')
                        row['decisions']+=1;frames+=1;batch_frames+=1
                        term,trunc=bool(result['terminated'][0]),bool(result['truncated'][0])
                        if term or trunc:
                            n=row['decisions']
                            c.need(term!=trunc and info['gameplay_frames']==n and info['alive_frames']==n-int(term),'Native terminal frame identity differs')
                            record=dict(model=model_name,checkpoint_sha256=artifact['sha256'],condition='clean',seed=seed,
                                action_repeat=1,startup_frames=13,alive_frames=int(info['alive_frames']),gameplay_frames=n,
                                terminated=term,truncated=trunc,score_raw_fixed=int(info['score_raw_fixed']),decisions=n)
                            journal.emit(record);rows.append(record)
                            del environments[seed],observations[seed]
                        else:observations[seed]=result['observations']
                    rounds+=1;window_rounds+=1
                    if window_rounds==256 or not environments:
                        max_window=max(max_window,(time.monotonic()-window_start)/window_rounds)
                        window_start=time.monotonic();window_rounds=0
                journal.sync()
                torch.mps.synchronize()
                c.need(fingerprint(model.state_dict())==initial,'Fixed weights changed')
                for name,module in list(sys.modules.items()):
                    if name=='dodge_rl' or name.startswith('dodge_rl.'):
                        path=str(c.Path(module.__file__).resolve())
                        c.need(path in reg['input_pins'] and c.sha(path)==reg['input_pins'][path],'Unpinned runtime import '+name)
                del model,legacy,arrays,output,probabilities,observations,environments,episode,result
                gc.collect();torch.mps.empty_cache();guard()
                batch=dict(model=model_name,offset=offset,games=64,frames=batch_frames,rounds=rounds,
                    wall_seconds=time.monotonic()-batch_start,max_window_seconds_per_round=max_window,
                    cumulative_games=len(rows),actual_frames=frames,elapsed_seconds=time.monotonic()-started,resources=dict(peaks))
                batches.append(batch);telemetry.emit(batch);telemetry.sync()
                print(c.canonical(dict(kind='completed_batch',**batch)).decode(),flush=True)
            elapsed=time.monotonic()-started
            projected=forecast(elapsed,batches,10-len(batches),reg['IO_analysis_reserve_seconds'])
            receipt=dict(status='accepted_counted_prefix' if projected<reg['work_seconds'] else 'failed_counted_prefix',
                elapsed_seconds=elapsed,counted_games=len(rows),actual_frames=frames,models=[m['name'] for m in reg['models']],
                batches=batches.copy(),forecast_seconds=projected,margin_factor=1.2,
                remaining_batches=10-len(batches),remaining_round_cap_per_batch=18000,
                IO_analysis_reserve_seconds=reg['IO_analysis_reserve_seconds'],device='mps',resources=dict(peaks))
            c.save(out/('prefix-qualification.json' if offset==0 else 'final-forecast.json'),receipt)
            c.need(projected<reg['work_seconds'],'Counted full-path forecast exceeds evaluation work ceiling')
        journal.close();journal=None;telemetry.close();telemetry=None
        analysis=analyze(rows,reg,guard);c.save(out/'analysis.json',analysis)
        guard();c.verify_pins(reg);c.verify_runtime_members(reg)
        c.save(out/'result.json',dict(status='complete_fixed_endpoint_development_evaluation',registration_sha256=args.sha256,
            games=len(rows),actual_frames=frames,actual_startup_frames=13*len(rows),resources=peaks,
            elapsed_seconds=time.monotonic()-started,promoted=False,training=False,
            artifacts={name:c.sha(out/name) for name in ['episodes.jsonl','batches.jsonl','analysis.json','prefix-qualification.json','final-forecast.json','device.json']}))
        return 0
    except BaseException as error:
        if journal is not None:journal.close()
        if telemetry is not None:telemetry.close()
        c.save(out/'first-failure.json',dict(status='first_failure_preserved_lease_held',error=repr(error),traceback=traceback.format_exc(),
            completed_games=len(rows),actual_partial_gameplay_frames=frames,resources=peaks,elapsed_seconds=time.monotonic()-started))
        raise


if __name__=='__main__':raise SystemExit(main())
