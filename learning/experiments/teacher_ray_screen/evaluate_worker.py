"""D13 terminal evaluation. Native/MPS work requires coordinator stage dispatch."""

import argparse
from collections import deque
import gc
import hashlib
import importlib
import math
import os
import random
import resource
import signal
import sys
import time
import traceback

import common as c

CONDITIONS = ('clean','epsilon0.01','epsilon0.05','delay1','delay4')


def domain_seed(kind, seed, condition):
    return int.from_bytes(hashlib.sha256(f'ray055_eval_v1/{kind}/{seed}/{condition}'.encode()).digest()[:8],'big')


class Executor:
    def __init__(self, seed, condition):
        c.need(condition in CONDITIONS, 'Unknown executor condition')
        self.condition = condition
        self.rng = random.Random(domain_seed('executor',seed,condition))
        self.queue = deque()
        self.applied = 0
        self.frame = 0
        self.realized_changes = 0

    def apply(self, requested):
        c.need(type(requested) is int and 0 <= requested < 9, 'Invalid requested action')
        selected = requested
        if self.condition.startswith('epsilon') and self.rng.random() < float(self.condition[7:]):
            selected = self.rng.randrange(9)
        self.realized_changes += selected != requested
        delay = int(self.condition[5:]) if self.condition.startswith('delay') else 0
        self.queue.append((self.frame+delay,selected))
        while self.queue and self.queue[0][0] <= self.frame:
            _,self.applied = self.queue.popleft()
        self.frame += 1
        return self.applied


def summary(values):
    values = sorted(values)
    n = len(values); c.need(n > 0 and n%4 == 0,'Whole quartiles required')
    return dict(Worst=values[0],Q1=sum(values[:n//4])/(n//4),Mean=sum(values)/n,
                Q4=sum(values[-n//4:])/(n//4),Best=values[-1])


def training_binding(reg, dispatch):
    path = dispatch['training_acceptance_path']
    c.need(c.sha(path) == dispatch['training_acceptance_sha256'],'Training acceptance hash differs')
    accepted = c.read(path)
    c.need(accepted['status'] == 'accepted_training_screen'
           and accepted['registration_sha256'] == dispatch['registration_sha256']
           and accepted['D13_evaluation_authorized'] and not accepted['promoted'], 'Strict training acceptance absent')
    audit_path = c.HERE/'parent-terminal-audit.json'
    c.need(c.sha(audit_path) == accepted['parent_terminal_audit_sha256'],'Training terminal audit differs')
    audit = c.read(audit_path)
    c.need(audit['status'] == 'training_complete_pending_coordinator_acceptance'
           and audit['registration_sha256'] == dispatch['registration_sha256']
           and len(audit['trajectories']) == 4 and not audit['cohort_D13_opened'], 'Training evidence differs')
    return audit


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--registration',required=True)
    parser.add_argument('--sha256',required=True);parser.add_argument('--dispatch',required=True)
    parser.add_argument('--dispatch-sha256',required=True);args=parser.parse_args()
    reg=c.load_registration(args.registration,args.sha256)
    c.need(c.sha(args.dispatch)==args.dispatch_sha256,'Evaluation dispatch hash differs')
    dispatch=c.read(args.dispatch)
    c.need(dispatch['stage']=='evaluation' and dispatch['registration_sha256']==args.sha256
           and dispatch['expected_lease']==reg['evaluation_expected_lease'],'Evaluation dispatch differs')
    audit=training_binding(reg,dispatch)
    reg=dict(reg,expected_lease=reg['evaluation_expected_lease'])
    c.check_lease(reg)
    out=c.HERE/'evaluation-output'
    c.save(out/'worker.claimed',dict(pid=os.getpid(),parent_pid=os.getppid(),registration_sha256=args.sha256,
        dispatch_sha256=args.dispatch_sha256))
    started=time.monotonic();cancelled=False;last_check=last_power=float('-inf')
    torch=None;peaks=dict(peak_rss_bytes=0,peak_mps_driver_bytes=0)
    journal=None

    def cancel(*_):
        nonlocal cancelled
        cancelled=True
    signal.signal(signal.SIGTERM,cancel);signal.signal(signal.SIGINT,cancel)

    def guard():
        nonlocal last_check,last_power
        now=time.monotonic()
        c.need(not cancelled and now-started<reg['evaluation']['worker_work_seconds'],'Evaluation deadline/cancellation')
        if now-last_check>=.25:
            c.check_lease(reg)
            peaks['peak_rss_bytes']=max(peaks['peak_rss_bytes'],int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss))
            peaks['peak_mps_driver_bytes']=max(peaks['peak_mps_driver_bytes'],0 if torch is None else int(torch.mps.driver_allocated_memory()))
            c.need(peaks['peak_rss_bytes']<reg['rss_bytes'] and peaks['peak_mps_driver_bytes']<reg['mps_bytes'],'Separate evaluation resource ceiling')
            last_check=now
        if now-last_power>=5:
            c.ac_power();last_power=now

    try:
        guard();sys.path.insert(0,reg['runtime_root'])
        torch=importlib.import_module('torch');np=importlib.import_module('numpy')
        native=importlib.import_module('dodge_rl')
        teacher=importlib.import_module('dodge_rl.models.teacher')
        ray=importlib.import_module('dodge_rl.models.ray_teacher')
        importlib.import_module('dodge_rl.ray_frontend')
        checkpoint=importlib.import_module('dodge_rl.checkpoints')
        torch.set_num_threads(reg['threads']);torch.set_num_interop_threads(1)
        torch.mps.set_per_process_memory_fraction(min(1.,reg['allocator_bytes']/torch.mps.recommended_max_memory()))
        for name,module in list(sys.modules.items()):
            if name=='dodge_rl' or name.startswith('dodge_rl.'):
                p=str(c.Path(module.__file__).resolve())
                c.need(p in reg['input_pins'] and c.sha(p)==reg['input_pins'][p],'Unpinned evaluation runtime '+name)
        journal=c.Journal(out/'episodes.jsonl');rows=[];frames=0;prefix=None
        artifacts={x['job']:x['final_checkpoint'] for x in audit['trajectories']}
        keys=('global_feats','entity_feats','entity_types','entity_mask')
        evaluation=reg['evaluation'];lo,hi=evaluation['range_inclusive']
        for model_name in evaluation['models']:
            guard()
            artifact=(dict(path=reg['checkpoint_path'],sha256=reg['checkpoint_sha256'])
                      if model_name=='420' else artifacts[model_name])
            c.need(c.sha(artifact['path'])==artifact['sha256'],'Endpoint hash differs')
            state=torch.load(artifact['path'],map_location='cpu',weights_only=False)
            with torch.random.fork_rng(devices=[]):
                torch.random.default_generator.manual_seed(202610305001)
                legacy=teacher.OmniscientEntityTeacher()
                model=ray.RayGeometryTeacher(legacy) if model_name.endswith('rays') else legacy
            model.load_state_dict(state['model'],strict=True);del state
            model.to('mps');model.eval()
            for condition in evaluation['conditions']:
                seeds=list(range(lo,hi+1)) if condition=='clean' else list(range(lo,lo+256))
                for offset in range(0,len(seeds),64):
                    guard();environments={};observations={};episode={}
                    for seed in seeds[offset:offset+64]:
                        env=native.VecDodgeEnv(batch_size=1,action_repeat=1,difficulty=2,
                            patterns_enabled=True,powerups_enabled=True,raw_frame_cap=18000,num_threads=1,chunk_size=1,
                            render_pixels=False,auxiliary_targets=False,seeds_by_slot=[[seed]],
                            excluded_seed_ranges=[tuple(x) for x in reg['exclusions'] if not (x[0]==lo and x[1]==hi)])
                        info=env.episode_info()[0]
                        c.need(info['seed']['actual_seed']==seed and info['startup_frames']==13,'D13 reset/seed differs')
                        environments[seed]=env;observations[seed]=env.observations()
                        episode[seed]=dict(executor=Executor(seed,condition),generator=torch.Generator(device='cpu').manual_seed(domain_seed('policy',seed,condition)),
                            previous=None,switches=[0,0,0],comparisons=0,entropy=0.,max_probability=0.,top_two_gap=0.,effective_support=0.,decisions=0)
                    while environments:
                        guard();active=sorted(environments)
                        arrays=[torch.from_numpy(np.concatenate([observations[s][k] for s in active],axis=0)) for k in keys]
                        if not getattr(model,'cpu_geometry_inputs',False): arrays=[x.to('mps') for x in arrays]
                        with torch.no_grad(): probabilities=model(*arrays).logits.softmax(-1).cpu()
                        c.need(bool(torch.isfinite(probabilities).all()),'Nonfinite evaluation probabilities')
                        for i,seed in enumerate(active):
                            row=episode[seed];p=probabilities[i]
                            request=int(torch.multinomial(p,1,generator=row['generator']).item())
                            executed=row['executor'].apply(request);actions=(request,request,executed)
                            if row['previous'] is not None:
                                row['comparisons']+=1
                                row['switches']=[n+int(a!=b) for n,a,b in zip(row['switches'],actions,row['previous'])]
                            row['previous']=actions;row['decisions']+=1
                            entropy=float(-(p*p.clamp_min(1e-30).log()).sum());top=p.topk(2).values
                            row['entropy']+=entropy;row['max_probability']+=float(top[0]);row['top_two_gap']+=float(top[0]-top[1]);row['effective_support']+=math.exp(entropy)
                            result=environments[seed].step(np.array([executed],dtype=np.int64));info=result['info'][0]
                            c.need(info['seed']['actual_seed']==seed,'D13 seed drift')
                            elapsed=int(result['elapsed_raw_frames'][0])
                            c.need(elapsed==1,'K1 executor must advance exactly one raw frame')
                            term,trunc=bool(result['terminated'][0]),bool(result['truncated'][0]);frames+=elapsed
                            if term or trunc:
                                c.need(term!=trunc and info['gameplay_frames']==row['decisions']
                                    and info['alive_frames']==row['decisions']-int(term),'K1 evaluation frame identity differs')
                                n=row['decisions'];record=dict(model=model_name,condition=condition,seed=seed,
                                    alive_frames=info['alive_frames'],gameplay_frames=info['gameplay_frames'],terminated=term,truncated=trunc,
                                    score_raw_fixed=info['score_raw_fixed'],decisions=n,eligible_action_comparisons=row['comparisons'],
                                    intended_selected_executed_switches=row['switches'],
                                    switch_rates=[x/row['comparisons'] if row['comparisons'] else None for x in row['switches']],
                                    switches_per_1000_frames=[1000*x/n for x in row['switches']],
                                    realized_epsilon_changes=row['executor'].realized_changes,
                                    entropy=row['entropy']/n,normalized_entropy=row['entropy']/n/math.log(9),
                                    max_probability=row['max_probability']/n,top_two_gap=row['top_two_gap']/n,effective_support=row['effective_support']/n)
                                journal.emit(record);rows.append(record)
                                del environments[seed],observations[seed]
                            else:observations[seed]=result['observations']
                    journal.sync()
                    if prefix is None:
                        elapsed=time.monotonic()-started
                        remaining=10240-len(rows)
                        forecast=elapsed+1.2*(elapsed/frames)*remaining*18000+evaluation['IO_analysis_reserve_seconds']
                        c.need(forecast<evaluation['worker_work_seconds'],'Counted D13 prefix full-cap forecast exceeds work ceiling')
                        prefix=dict(counted_games=len(rows),actual_frames=frames,forecast_seconds=forecast,
                            method='Elapsed/actual raw frames × remaining games ×18000cap ×1.2 + IO/analysis reserve')
                        c.save(out/'prefix-qualification.json',prefix)
            del model,legacy;gc.collect();torch.mps.empty_cache();guard()
        journal.close();journal=None
        c.need(len(rows)==10240,'D13 count differs')
        from evaluation_analysis import analyze
        analysis=analyze(rows,evaluation,guard)
        c.save(out/'analysis.json',analysis);guard();c.verify_pins(reg)
        c.save(out/'result.json',dict(status='complete_D13_evaluation_no_promotion',registration_sha256=args.sha256,
            games=len(rows),actual_frames=frames,resources=peaks,elapsed_seconds=time.monotonic()-started,
            episodes_sha256=c.sha(out/'episodes.jsonl'),analysis_sha256=c.sha(out/'analysis.json'),
            prefix_sha256=c.sha(out/'prefix-qualification.json'),promoted=False))
        return 0
    except BaseException as error:
        if journal is not None:journal.close()
        c.save(out/'first-failure.json',dict(status='first_failure_preserved_lease_held',error=repr(error),
            traceback=traceback.format_exc(),resources=peaks,elapsed_seconds=time.monotonic()-started))
        raise


if __name__=='__main__':
    raise SystemExit(main())
