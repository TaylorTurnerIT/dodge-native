"""Serial058 trajectory lifecycle; device/session work is isolated in live_session."""
import argparse
import os
from pathlib import Path
import signal
import time
import traceback

import common as c
from live_session import LiveSession, PreparedUpdates, failure_observations, geometry_failure
from receipts import write_stage


def run_trajectory(reg,job,out,session_factory=LiveSession,check_control=lambda:None):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    c.save(out/'worker.claimed',dict(record='DODGE-064',job=job['id'],job_nonce=reg['job_nonce']))
    started=time.monotonic();session=None;checkpoints=[];times=[];prefix=[];cancelled=False
    def cancel(*_):
        nonlocal cancelled
        cancelled=True
    handlers={sig:signal.signal(sig,cancel) for sig in (signal.SIGTERM,signal.SIGINT)}
    def guard():
        check_control()
        c.need(not cancelled and time.monotonic()-started<reg['work_seconds'],'Worker cancellation/work deadline')
        c.need(time.monotonic()-reg['campaign_started_monotonic']<reg['campaign_total_seconds'],'Global training work cap')
        if session is not None:session.resources()
    try:
        guard();session=session_factory(reg,job,out,guard);setup=time.monotonic()-started
        for update in range(1,reg['updates']+1):
            guard();begin=time.monotonic();row=session.step(update,guard);guard()
            times.append(time.monotonic()-begin)
            c.need(row['training_frames']==update*reg['envs']*reg['rollout'] and row['completed_updates']==update,'Actual counted K1 exposure differs')
            if update<=reg['prefix_updates']:prefix.append(row['passive_GAE_return_identity'])
            if update==reg['prefix_updates']:
                forecast=setup+1.2*max(times)*reg['updates']+reg['IO_reserve_seconds']
                remaining=len(reg['jobs'])-reg['jobs'].index(job)-1
                full_path=(time.monotonic()-reg['campaign_started_monotonic']
                    +1.2*max(times)*(reg['updates']-update)+reg['IO_reserve_seconds']
                    +reg['receipt_seconds']+remaining*(reg['work_seconds']+reg['receipt_seconds']))
                c.need(all(prefix) and len(prefix)==2,'Passive prefix GAE/return checks missing')
                c.need(forecast<reg['work_seconds'] and full_path<reg['campaign_total_seconds'],'Counted-prefix full-path20%+IO forecast failed; no retry/resize')
                c.save(out/'prefix-qualification.json',dict(status='accepted_counted_prefix',
                    updates=update,counted_frames=row['training_frames'],valid_partial_vectors=0,
                    forecast_seconds=forecast,full_path_forecast_seconds=full_path,
                    passive_GAE_return_checks=prefix,resources=session.resources(),device='cuda',device_index=0,
                    limits='Counted first2 updates only; no simulator restore or survival claim.'))
            if update in reg['checkpoint_updates']:
                checkpoints.append(session.checkpoint(out/('checkpoint-%03d.pt'%update),update))
        guard()
        session.close()
        counts=session.counts();c.need(counts['training_frames']==reg['frame_target'],'Final frame target differs')
        rows=[c.read_json_line(line) for line in (out/'updates.jsonl').read_text().splitlines()]
        c.validate_telemetry(rows,reg,job)
        return write_stage(out/'worker-result.json',reg,'worker','complete',job=job['id'],
            **counts,trained_weights_saved=bool(checkpoints),checkpoints=checkpoints,
            fixture_only=session.fixture_only,device='cuda',device_index=0,
            stream_sha256=session.stream_digest,prefix_sha256=c.sha(out/'prefix-qualification.json'),
            telemetry_sha256=c.sha(out/'updates.jsonl'),resources=session.resources(),
            elapsed_seconds=time.monotonic()-started,no_resume=True,promotion=False)
    except BaseException as error:
        if session is not None:
            try:session.close()
            except BaseException:pass
        counts=dict(training_frames=None,completed_updates=0,native_games=None) if session is None else session.counts()
        partial={} if session is None else session.failure(error)
        return write_stage(out/'worker-first-failure.json',reg,'worker','failed',job=job['id'],
            **counts,trained_weights_saved=any('.pt' in p.name for p in out.iterdir()),checkpoints=checkpoints,
            fixture_only=False if session is None else session.fixture_only,error=repr(error),
            traceback=traceback.format_exc(),partial_observations=partial,
            elapsed_seconds=time.monotonic()-started)
    finally:
        for sig,handler in handlers.items():signal.signal(sig,handler)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--registration',required=True)
    parser.add_argument('--sha256',required=True);parser.add_argument('--job',required=True);args=parser.parse_args()
    reg=c.load_registration(args.registration,args.sha256);job=next(x for x in reg['jobs'] if x['id']==args.job)
    reg['control_stage']='train';c.check_lease(reg)
    c.need(c.read(c.HERE/'control.json')['allowed_stage']=='train','Training-stage control absent')
    out=c.HERE/'artifacts/outputs'/job['id'];until=time.monotonic()+5
    while not (out/'dispatch.json').exists() and time.monotonic()<until:c.check_lease(reg);time.sleep(.01)
    dispatch=c.read(out/'dispatch.json')
    c.need(dispatch['worker_expected_job']==job['id'] and dispatch['worker_pid']==os.getpid()
           and dispatch['parent_pid']==os.getppid() and dispatch['registration_sha256']==args.sha256,'Direct parent binding differs')
    reg['campaign_started_monotonic']=dispatch['campaign_started_monotonic']
    from safety_hooks import checkpoint_factory
    result=run_trajectory(reg,job,out,session_factory=checkpoint_factory(reg,LiveSession),check_control=lambda:c.check_lease(reg))
    return 0 if result['status']=='complete' else 1


if __name__=='__main__':raise SystemExit(main())
