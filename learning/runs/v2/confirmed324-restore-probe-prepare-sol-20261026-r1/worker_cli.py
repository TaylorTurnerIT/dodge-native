"""One independent process; accepted restore/reseed only, then cleanup and exit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import sys
import threading
import time
import types


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--registration',required=True); ap.add_argument('--registration-sha256',required=True)
    ap.add_argument('--heartbeat',required=True); ap.add_argument('--deadline',required=True,type=float)
    a=ap.parse_args(); rp=Path(a.registration)
    raw=rp.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=a.registration_sha256: raise ValueError('registration hash drift')
    reg=json.loads(raw); path=Path(reg['source']['probe_path']); raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=reg['source']['probe_sha256']: raise ValueError('probe source buffer pin mismatch')
    p=types.ModuleType('_verified_restore_probe'); p.__file__=str(path); exec(compile(raw,str(path),'exec'),p.__dict__)
    p.preflight(rp,a.registration_sha256,reg,Path(__file__),worker_phase=True)
    modules,context=p.verify_immutable(reg)
    out=Path(reg['output_dir']); events=[]; resources=[]; start=time.monotonic()
    stop=threading.Event(); errors=[]; lock=threading.RLock(); adapter=None; t=None; outcome=None; failure=None; cleanup={}; runtime_ready=False
    def save(path,value):
        with Path(path).open('x') as f:
            json.dump(value,f,sort_keys=True,allow_nan=False); f.write('\n'); f.flush(); os.fsync(f.fileno())
    def guard():
        p.need(time.monotonic()<a.deadline,'worker deadline elapsed')
        p.need(not Path(reg['cancel_path']).exists(),'cancel present')
        p.need(not errors,'heartbeat thread failed')
        p.need(not received,'worker signal observed')
    def memory():
        peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss=int(peak if sys.platform=='darwin' else peak*1024)
        torch=getattr(adapter,'torch',None)
        mps=int(torch.mps.driver_allocated_memory()) if runtime_ready else 0
        p.need(0<=rss<=reg['limits']['RSS_bytes'] and 0<=mps<=reg['limits']['MPS_driver_bytes'],'heartbeat resource cap exceeded')
        return rss,mps,runtime_ready
    def sample(phase):
        rss,mps,available=memory(); p.need(available,'MPS memory sample unavailable')
        row=dict(phase=phase,elapsed_seconds=time.monotonic()-start,rss_high_water_bytes=rss,mps_driver_bytes=mps)
        with lock:
            resources.append(row); rf.write(json.dumps(row,sort_keys=True)+'\n'); rf.flush(); os.fsync(rf.fileno())
    def event(name):
        guard()
        row=dict(event=name,sequence=len(events),monotonic_ns=time.monotonic_ns())
        events.append(row); ef.write(json.dumps(row,sort_keys=True)+'\n'); ef.flush(); os.fsync(ef.fileno())
        sample(name)
    def publish_heartbeat():
        rss,mps,available=memory()
        row=dict(run_id=reg['run_id'],registration_sha256=a.registration_sha256,pid=os.getpid(),timestamp_ns=time.time_ns(),sequence=time.monotonic_ns(),rss_bytes=rss,mps_driver_bytes=mps,rss_semantics='process lifetime high-water bytes',mps_sample_status='measured' if available else 'unavailable_until_adapter_validation')
        temp=Path(a.heartbeat+'.tmp.'+str(os.getpid()))
        with temp.open('x') as f: json.dump(row,f); f.flush(); os.fsync(f.fileno())
        os.replace(temp,a.heartbeat)
    def heartbeat():
        while not stop.is_set():
            try: publish_heartbeat()
            except BaseException as exc: errors.append(type(exc).__name__+':'+str(exc)); stop.set(); return
            stop.wait(.2)
    received=[]; handling_cleanup=False; outcome_frozen=False
    def handled_signal(sig,frame):
        nonlocal handling_cleanup
        if outcome_frozen: return
        received.append(signal.Signals(sig).name)
        if handling_cleanup: return
        handling_cleanup=True
        raise KeyboardInterrupt('worker signal: '+signal.Signals(sig).name)
    for sig in (signal.SIGTERM,signal.SIGHUP,signal.SIGINT): signal.signal(sig,handled_signal)
    with (out/'events.jsonl').open('x') as ef,(out/'resources.jsonl').open('x') as rf:
        try:
            # Retain even a partially initialized instance for cleanup on failure.
            cls=modules['runtime_adapter'].RuntimeAdapter
            adapter=cls.__new__(cls)
            t=threading.Thread(target=heartbeat,daemon=True); t.start()
            cls.__init__(adapter,p.adapter_subset(reg,context),context)
            runtime_ready=True
            guard(); event('runtime_authenticated_checkpoint_validated')
            result=p.run_claimed(reg,context,modules,adapter,event)
            identity=p.runtime_identity(adapter,modules)
            outcome=dict(schema=p.RESULT_SCHEMA,status='verified_pending_parent_audit',run_id=reg['run_id'],registration_sha256=a.registration_sha256,study_id=p.STUDY,replica=1,arm=p.ARM,vector_sha256=reg['vector']['vector_sha256'],reference=reg['reference'],parent_fingerprints=p.EXPECTED,events=events,runtime=identity,scope=p.SCOPE,resources=resources,**result)
        except BaseException as exc:
            failure=type(exc).__name__+':'+str(exc)
        finally:
            handling_cleanup=True
            # Stop the sampler before releasing model, parent tensors and callbacks.
            stop.set()
            if t is not None: t.join(1)
            if t is not None and t.is_alive(): failure=failure or 'heartbeat thread did not stop'
            if received: failure=failure or 'worker signals:'+repr(received)
            if errors: failure=failure or 'heartbeat:'+repr(errors)
            if adapter is not None: cleanup=p.release(adapter)
            if any(v['status']!='pass' for v in cleanup.values()): failure=failure or 'cleanup failed'
            if failure is None:
                try:
                    guard(); event('cleanup_complete'); publish_heartbeat()
                    p.preflight(rp,a.registration_sha256,reg,Path(__file__),worker_phase=True)
                    guard(); outcome['cleanup']=cleanup
                    p.validate_result(reg,outcome,a.registration_sha256)
                    guard()
                    outcome_frozen=True
                    p.need(not received,'worker signal before outcome freeze')
                    save(out/'result.json',outcome)
                    save(out/'COMMITTED.json',dict(schema='confirmed324_restore_probe_commit_v1',result_sha256=p.sha(out/'result.json'),registration_sha256=a.registration_sha256))
                except BaseException as exc: failure=type(exc).__name__+':'+str(exc)
            if failure is not None:
                save(out/'worker-failure.json',dict(schema='confirmed324_restore_probe_failure_v1',run_id=reg['run_id'],registration_sha256=a.registration_sha256,error=failure,events=events,resources=resources,cleanup=cleanup,subclaim_exists=Path(reg['attempt_claim_path']).exists(),partial_result=outcome,partial_probe=getattr(adapter,'_probe_partial',None),handled_signals=received))
                raise RuntimeError('restore probe failed; partial evidence preserved: '+failure)
if __name__=='__main__': main()
