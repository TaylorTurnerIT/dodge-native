"""One local learner at a time; live continuation, measured play, immutable best."""
import argparse
import gc
import importlib
import importlib.util
import json
import math
import os
import random
import resource
import signal
import sys
import time
import traceback
import common as c
from policy import advance,summarize
from evaluation import evaluate
from warmstart import load_control,verify_only_lr_changed
from analysis import compare


def main():
    p=argparse.ArgumentParser();p.add_argument('--registration',required=True);p.add_argument('--sha256',required=True);a=p.parse_args()
    reg=c.load_registration(a.registration,a.sha256);c.review_gate(reg,a.sha256);c.check_lease(reg)
    out=c.RUN/'output/worker';c.save(out/'worker.claimed',dict(pid=os.getpid(),parent_pid=os.getppid(),registration_sha256=a.sha256))
    started=time.monotonic();last=-1.;cancelled=False;torch=None;peaks=dict(peak_rss_bytes=0,peak_mps_driver_bytes=0)
    journals=[];completed=[]
    def cancel(*_):
        nonlocal cancelled
        cancelled=True
    signal.signal(signal.SIGTERM,cancel);signal.signal(signal.SIGINT,cancel)
    def guard():
        nonlocal last
        c.need(not cancelled,'User cancelled loop')
        now=time.monotonic()
        if now-last>=.25:
            c.check_lease(reg)
            peaks['peak_rss_bytes']=max(peaks['peak_rss_bytes'],int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss))
            peaks['peak_mps_driver_bytes']=max(peaks['peak_mps_driver_bytes'],int(torch.mps.driver_allocated_memory()) if torch else 0)
            c.check_worker_resources(reg,peaks['peak_rss_bytes'],peaks['peak_mps_driver_bytes']);last=now
    try:
        guard();sys.path.insert(0,reg['runtime_root']);sys.path.append(reg['training_components'])
        torch=importlib.import_module('torch');np=importlib.import_module('numpy');native=importlib.import_module('dodge_rl')
        teacher=importlib.import_module('dodge_rl.models.teacher');ray=importlib.import_module('dodge_rl.models.ray_teacher')
        migration=importlib.import_module('dodge_rl.ray_migration');ppo=importlib.import_module('dodge_rl.ppo')
        checkpoint=importlib.import_module('dodge_rl.checkpoints');adapter_module=importlib.import_module('dodge_rl.seeded_training')
        from fingerprints import fingerprint
        from update_telemetry import Recorder,instrument_update,JsonlSink
        spec=importlib.util.spec_from_file_location('accepted_training_component',c.Path(reg['training_components'])/'worker.py')
        training=importlib.util.module_from_spec(spec);spec.loader.exec_module(training)
        c.need(torch.backends.mps.is_available(),'MPS required')
        torch.set_num_threads(reg['threads']);torch.set_num_interop_threads(1)
        torch.mps.set_per_process_memory_fraction(min(1.,reg['allocator_bytes']/torch.mps.recommended_max_memory()))
        def runtime_check():
            for name,module in list(sys.modules.items()):
                if name=='dodge_rl' or name.startswith('dodge_rl.'):
                    path=str(c.Path(module.__file__).resolve());c.need(path in reg['input_pins'] and c.sha(path)==reg['input_pins'][path],'Unpinned runtime '+name)
        runtime_check();guard()
        c.save(out/'device.json',dict(device='mps',torch_version=torch.__version__,numpy_version=np.__version__,interpreter=sys.executable,elapsed_time_cancellation=False))
        c.verify_environment(reg)
        # Both baselines run on this machine; no M4 floating-point rows are reused.
        baseline_metrics={}
        for label in ['420','control12']:
            baseline_out=out/('baseline-'+label);baseline_out.mkdir()
            torch.manual_seed(reg['replicas']['1']['constructor_seed'])
            state=(checkpoint.load_checkpoint(c.Path(reg['checkpoint_path']),expected_sha256=reg['checkpoint_sha256'])
                if label=='420' else load_control(reg,torch,fingerprint))
            model=teacher.OmniscientEntityTeacher();model.load_state_dict(state['model'],strict=True);del state
            model.to('mps');model.eval()
            measured=evaluate(model,reg['evaluation_seeds'],reg,baseline_out,guard,torch,np,native,checkpoint,fingerprint)
            baseline_metrics[label]=measured['metrics']
            del model;gc.collect();torch.mps.empty_cache();guard()
        control12_rows=[json.loads(x) for x in (out/'baseline-control12/episodes.jsonl').read_text().splitlines()]
        baseline420_rows=[json.loads(x) for x in (out/'baseline-420/episodes.jsonl').read_text().splitlines()]
        c.save(out/'baseline-paired-uncertainty.json',compare(control12_rows,baseline420_rows,np))
        baseline=baseline_metrics['control12'];reference=baseline
        c.save(out/'baseline.json',dict(metrics=baseline,context420=baseline_metrics['420'],cached_games=0,
            new_games=1024,paired_uncertainty_sha256=c.sha(out/'baseline-paired-uncertainty.json'),source_control12_sha256=reg['warmstart']['sha256'],source420_sha256=reg['checkpoint_sha256'],
            baseline_results={label:c.sha(out/('baseline-'+label)/'result.json') for label in ['420','control12']}))
        for arm in reg['job_order']:
            directory=out/arm;directory.mkdir();(directory/'evaluations').mkdir();(directory/'checkpoints').mkdir()
            seed=reg['replicas']['1'];torch.manual_seed(seed['constructor_seed'])
            original=load_control(reg,torch,fingerprint)
            legacy=teacher.OmniscientEntityTeacher();legacy.load_state_dict(original['model'],strict=True)
            model=legacy;model.to('mps')
            optimizer,manifest=migration.migrate_adam(original['optimizer'],legacy,model,
                learning_rate=reg['ppo']['learning_rate'],adam_eps=reg['ppo']['adam_eps'])
            verify_only_lr_changed(original['optimizer'],optimizer.state_dict(),fingerprint)
            checkpoint.restore_rng(original['rng'],'mps')
            c.need(fingerprint(checkpoint.capture_rng('mps'))==fingerprint(original['rng']),'Source RNG restore differs')
            c.save(directory/'migration.json',dict(manifest,source_model_fingerprint=reg['warmstart']['model_fingerprint'],
                source_adam_fingerprint=reg['warmstart']['adam_fingerprint'],content_except_LR_preserved=True,
                actual_LR_before=3e-5,actual_LR_after=1e-5,source_rng_restored=True,full_simulator_restore=False))
            del original
            initial_branch=None if arm=='control' else fingerprint(model.branch.state_dict())
            telemetry=JsonlSink(directory/'updates.jsonl');journals.append(telemetry)
            events=c.Journal(directory/'native-events.jsonl');journals.append(events)
            activity=c.Journal(directory/'activity.jsonl');journals.append(activity)
            decisions=c.Journal(directory/'decisions.jsonl');journals.append(decisions)
            recorder=Recorder(arm,1);update=0;adam_steps=0;segment=0;segments=[];adapter=None;prepared=None;env=None
            current_rng=checkpoint.capture_rng('mps');config=ppo.PPOConfig(**dict(reg['ppo'],**reg['arms'][arm]))
            def new_games(reason):
                nonlocal segment,adapter,prepared,env
                # Only planned stream-capacity rollover starts fresh games. Learner
                # and Adam remain live; no checkpoint/simulator restore is claimed.
                if adapter is not None:
                    events.emit(dict(kind='explicit_new_games_boundary',reason=reason,after_update=recorder.completed_updates,abandoned_active_episodes=64))
                    del prepared,adapter,env;prepared=adapter=env=None;gc.collect()
                segment+=1;stream_reg=dict(reg,frame_target=reg['initial_updates']*65536)
                stream_reg['replicas']={'1':dict(seed,environment_seed=seed['environment_seed']+segment-1)}
                pool,strata,streams,digest=c.build_streams(stream_reg,'1')
                env=native.VecDodgeEnv(batch_size=64,action_repeat=1,difficulty=2,patterns_enabled=True,powerups_enabled=True,
                    raw_frame_cap=18000,num_threads=reg['threads'],chunk_size=8,render_pixels=False,auxiliary_targets=False,
                    seeds_by_slot=streams,initial_episode_indices=[0]*64,excluded_seed_ranges=[tuple(x) for x in reg['exclusions']])
                adapter=adapter_module.SeededTrainingAdapter(env,seeds_by_slot=streams,components_by_slot=[['uniform']*len(x) for x in streams],
                    strata_by_seed=strata,training_pool_values=pool,exclusions=reg['exclusions'],rollout_steps=1024,gameplay_frame_target=None)
                adapter.completed_updates=recorder.completed_updates;adapter.event_sink=events.emit
                prepared=training.PreparedUpdates(model,optimizer,adapter,config,ppo,reg,'mps')
                row=dict(kind='initial_assignments',simulator_segment=segment,after_update=recorder.completed_updates,reason=reason,stream_sha256=digest,assignments=adapter.assignment_events,exact_simulator_resume=False)
                events.emit(row);segments.append(row);del streams
            new_games('fresh_control12_learner_Adam_new_simulator_segment')
            def save_learner(u,measured):
                path=directory/'checkpoints'/f'checkpoint-{u:06d}.pt'
                state=dict(schema='performance_loop_learner_v1',arm=arm,completed_updates=u,actual_gameplay_frames=u*65536,
                    parent_checkpoint_sha256=reg['warmstart']['sha256'],inherited_parent_updates=12,learner_updates_since420=12+u,
                    actual_Adam_steps=adam_steps,model=checkpoint._cpu_copy(model.state_dict()),optimizer=checkpoint._cpu_copy(optimizer.state_dict()),rng=checkpoint.capture_rng('mps'),
                    adapter=adapter.snapshot(),simulator_segment=segment,full_environment_state_captured=False,automatic_resume_authorized=False,passive_reset_history='Full history in native-events.jsonl; in-memory reset copies bounded after each completed update.',
                    measured_performance=measured,registration_sha256=a.sha256,model_fingerprint=fingerprint(model.state_dict()),adam_fingerprint=fingerprint(optimizer.state_dict()),promoted=False)
                digest=c.publish(path,lambda f:torch.save(state,f));path.chmod(0o444)
                meta=dict(path=str(path),sha256=digest,update=u,actual_gameplay_frames=u*65536,actual_Adam_steps=adam_steps,model_fingerprint=state['model_fingerprint'],adam_fingerprint=state['adam_fingerprint'],performance=measured,simulator_segment=segment,full_simulator_restore=False)
                c.save(path.with_suffix('.json'),meta);del state;return meta
            prefix_passive_checks=[];update_times=[]
            checkpoints=[save_learner(0,baseline)];policy_state={'best':dict(update=0,**baseline)};stop=None
            for update in range(1,reg['max_updates']+1):
                guard()
                remaining=min(len(adapter.seeds_by_slot[i])-info['seed']['episode']-1 for i,info in enumerate(env.episode_info()))
                if remaining<=1024:new_games('registered_seed_stream_capacity_rollover')
                checkpoint.restore_rng(current_rng,'mps')
                begin=time.monotonic();captured=[];original_gae=ppo.compute_gae
                def probe(*a,**kw):
                    result=original_gae(*a,**kw);captured.append((result,tuple(x.clone() for x in result)));return result
                if update<=reg['prefix_updates']:ppo.compute_gae=probe
                try:
                    collection,metrics,boundary=instrument_update(prepared,ppo,recorder,telemetry,resource_snapshot=lambda:dict(peaks),check_guard=guard)
                    c.need(all(a is b for a,b in zip((collection,metrics,boundary),prepared.last_result)),'Telemetry changed return identity')
                    if update<=reg['prefix_updates']:
                        c.need(ppo.compute_gae is probe and len(captured)==1,'Counted GAE hook identity differs')
                        c.need(all(torch.equal(a,b) for a,b in zip(*captured[0])),'Passive GAE tensors changed')
                        prefix_passive_checks.append(True)
                finally:ppo.compute_gae=original_gae
                torch.mps.synchronize();guard();update_times.append(time.monotonic()-begin)
                current_rng=checkpoint.capture_rng('mps')
                if update==reg['prefix_updates']:
                    c.save(directory/'prefix-qualification.json',dict(status='accepted_counted_M1_training_prefix',
                        counted_updates=update,counted_frames=recorder.frames,actual_K1_frames_per_full_vector=64,
                        passive_GAE_and_return_identity_checks=prefix_passive_checks,resources=dict(peaks),
                        measured_update_seconds=update_times,elapsed_full_path_seconds=time.monotonic()-started,
                        initial72_training_estimate_seconds=1.2*max(update_times)*reg['initial_updates'],
                        estimate_is_not_admission_or_stopping_rule=True,full_simulator_restore=False,
                        migration_sha256=c.sha(directory/'migration.json')))
                    print(c.canonical(dict(kind='counted_prefix',updates=update,frames=recorder.frames,resources=peaks)).decode(),flush=True)
                c.need(recorder.frames==update*65536 and metrics['optimizer_steps']==metrics['epochs_completed']*32,'Actual training exposure differs')
                adam_steps+=metrics['optimizer_steps']
                row=dict(update=update,simulator_segment=segment,policy_loss=float(metrics['policy_loss']),actor_grad_norm=float(metrics['actor_grad_norm']),critic_grad_norm=float(metrics['critic_grad_norm']),trunk_grad_norm=float(metrics['trunk_grad_norm']),grad_norm=float(metrics['grad_norm']))
                if arm=='rays':
                    row.update(ray_gate=float(model.gate.detach().cpu()),branch_parameter_norm=math.sqrt(sum(float(x.detach().cpu().double().square().sum()) for x in model.branch.parameters())),
                        branch_changed_from_initial=fingerprint(model.branch.state_dict())!=initial_branch,
                        last_step_gate_gradient=None if model.gate.grad is None else float(model.gate.grad.detach().cpu()),
                        branch_Adam_step_min=min(float(optimizer.state[x]['step'].item()) for x in model.branch.parameters() if 'step' in optimizer.state[x]))
                c.need(all(math.isfinite(v) for v in row.values() if isinstance(v,float)),'Nonfinite branch/learning diagnostic')
                activity.emit(row);events.sync();activity.sync()
                adapter.returned_resets.clear()  # Passive copies are already durable in native-events.
                prepared.last_result=None
                del collection,metrics,boundary;gc.collect();torch.mps.empty_cache();guard()
                if update%reg['segment_updates']:continue
                events.sync();activity.sync()
                evaluation_out=directory/'evaluations'/f'{update:06d}';evaluation_out.mkdir()
                before_env=fingerprint(env.episode_info());before_adam=fingerprint(optimizer.state_dict())
                checked=evaluate(model,reg['evaluation_seeds'],reg,evaluation_out,guard,torch,np,native,checkpoint,fingerprint)
                c.need(fingerprint(env.episode_info())==before_env and fingerprint(optimizer.state_dict())==before_adam,'Play check changed live training state')
                c.need(fingerprint(checkpoint.capture_rng('mps'))==fingerprint(current_rng),'Training RNG drift across play check')
                c.save(evaluation_out/'paired-vs-control12.json',compare([json.loads(x) for x in (evaluation_out/'episodes.jsonl').read_text().splitlines()],control12_rows,np))
                meta=save_learner(update,checked['metrics']);checkpoints.append(meta)
                policy_state,decision=advance(policy_state,checked['metrics'],update,reference,reg['policy'])
                decision.update(arm=arm,paired_uncertainty_sha256=c.sha(evaluation_out/'paired-vs-control12.json'),evaluation_result_sha256=c.sha(evaluation_out/'result.json'),checkpoint_sha256=meta['sha256'],metrics=checked['metrics'])
                decisions.emit(decision);decisions.sync()
                c.save(directory/f'decision-{update:06d}.json',decision)
                print(c.canonical(dict(kind='measured_play',**decision)).decode(),flush=True)
                if not decision['continue_training']:stop=decision['stop_reason'];break
            c.need(stop is not None,'Prospective bounded-progress policy missing terminal disposition')
            for j in [telemetry,events,activity,decisions]:j.close();journals.remove(j)
            best_update=policy_state['best']['update'];best=next(x for x in checkpoints if x['update']==best_update)
            terminal=dict(arm=arm,updates=update,actual_gameplay_frames=update*65536,Adam_steps=adam_steps,stop_reason=stop,best=best,
                checkpoints=checkpoints,simulator_segments=[{k:v for k,v in x.items() if k!='assignments'} for x in segments],
                artifacts={n:c.sha(directory/n) for n in ['updates.jsonl','native-events.jsonl','activity.jsonl','decisions.jsonl','migration.json','prefix-qualification.json']})
            c.save(directory/'result.json',terminal);completed.append(terminal)
            del prepared,adapter,env,model,legacy,optimizer,current_rng;gc.collect();torch.mps.empty_cache();guard()
        runtime_check();c.verify_pins(reg);c.verify_runtime_members(reg)
        c.save(out/'result.json',dict(status='complete_performance_loop',registration_sha256=a.sha256,arms=completed,
            baseline_sha256=c.sha(out/'baseline.json'),resources=peaks,elapsed_seconds=time.monotonic()-started,promoted=False,held_confirmation_opened=False))
        return 0
    except BaseException as error:
        for journal in journals:journal.close()
        c.save(out/'first-failure.json',dict(status='first_failure_preserved_exact_lease_held_no_retry',error=repr(error),traceback=traceback.format_exc(),completed_arms=[r['arm'] for r in completed],resources=peaks,elapsed_seconds=time.monotonic()-started,
            partial_observations=(training.failure_observations(prepared) if 'training' in locals() and 'prepared' in locals() else None)))
        raise


if __name__=='__main__':raise SystemExit(main())
