"""Parent-only exact-once subprocess supervisor; inert until explicitly invoked."""
from __future__ import annotations
import hashlib, json, os, signal, subprocess, sys, time
from pathlib import Path

WORKER_MAX_RSS = 6 * 1024**3
WORKER_MAX_MPS = 6 * 1024**3
CLEANUP_SECONDS = 10


def digest(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def exclusive_marker(path: Path):
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as f: json.dump({'pid':os.getpid(),'time_ns':time.time_ns()},f)

def execute_once(*, registration: Path, worker: Path, evaluator: Path, stage: str, candidate_update: int, cohort: str, output: Path, marker: Path, preflight, observe, wall_seconds: float):
    """Callbacks are parent-owned. preflight must fully validate state without mutation."""
    preflight()  # one-shot remains untouched on ANY preflight failure
    reg=json.loads(registration.read_text())
    pins=reg.get('source',{})
    if reg.get('schema')!='expanded_D2_evaluation_registration_v1': raise RuntimeError('registration schema mismatch')
    if not reg.get('expected_lease') or not reg.get('state_path'): raise RuntimeError('parent lease/ledger binding absent')
    if digest(worker)!=pins.get('worker_sha256'): raise RuntimeError('worker source pin mismatch')
    if digest(evaluator)!=pins.get('evaluator_sha256'): raise RuntimeError('evaluator source pin mismatch')
    if wall_seconds <= CLEANUP_SECONDS: raise RuntimeError('wall budget lacks cleanup reserve')
    if wall_seconds != reg.get('limits',{}).get('outer_seconds'): raise RuntimeError('requested wall budget differs from registration')
    exclusive_marker(marker)
    start=time.monotonic(); deadline=start+wall_seconds-CLEANUP_SECONDS
    cmd=[sys.executable,str(worker),'--registration',str(registration),'--evaluator',str(evaluator),'--output',str(output),'--stage',stage,'--candidate-update',str(candidate_update),'--cohort',cohort,'--guard',str(registration),'--deadline',str(deadline)]
    proc=subprocess.Popen(cmd,start_new_session=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    reason=None; stdout=''; stderr=''; last_sample=0.0
    try:
        while proc.poll() is None:
            now=time.monotonic()
            if now >= deadline: reason='wall_limit'; break
            if now-last_sample >= .2:
                status=observe(proc.pid,proc.create_time if hasattr(proc,'create_time') else None)
                last_sample=now
                if status.get('cancelled'): reason='cancelled'; break
                if not status.get('lease_valid'): reason='lease_invalid'; break
                if status.get('rss_bytes',0)>WORKER_MAX_RSS: reason='rss_limit'; break
                if status.get('mps_bytes',0)>WORKER_MAX_MPS: reason='mps_limit'; break
            time.sleep(.02)
        if reason:
            try: os.killpg(proc.pid,signal.SIGTERM)
            except ProcessLookupError: pass
            try: stdout,stderr=proc.communicate(timeout=CLEANUP_SECONDS/2)
            except subprocess.TimeoutExpired:
                try: os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                stdout,stderr=proc.communicate(timeout=CLEANUP_SECONDS/2)
        else: stdout,stderr=proc.communicate(timeout=max(.01,deadline-time.monotonic()))
    finally:
        if proc.poll() is None:
            try: os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            proc.communicate(timeout=CLEANUP_SECONDS)
    receipt={'schema':'layerA_worker_exit_v1','stage':stage,'candidate_update':candidate_update,'cohort':cohort,'exit_code':proc.returncode,'stop_reason':reason,'elapsed_seconds':time.monotonic()-start,'stdout':stdout,'stderr':stderr,'output_exists':output.exists(),'worker_sha256':pins['worker_sha256'],'evaluator_sha256':reg['source']['evaluator_sha256']}
    output.with_suffix(output.suffix+'.outer-receipt.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
    if reason or proc.returncode != 0: raise RuntimeError(f'worker stopped: {reason or proc.returncode}; partial evidence preserved')
    return receipt
