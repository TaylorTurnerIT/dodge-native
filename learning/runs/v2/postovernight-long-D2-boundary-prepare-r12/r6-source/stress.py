#!/usr/bin/env python3
"""One stdlib CPU contender; real new B/R/A bytes, no ML metadata stand-ins."""
import time
START=time.monotonic()
from pathlib import Path
import json
import os
import sys
import threading
import boundary_integrity as integrity
import long_d2 as c
import lifecycle as life
H=Path(__file__).resolve().parent


def main():
    out=Path(sys.argv[1]);out.mkdir()
    root=H/'capsule-final';ctx=c.capsule_context(root,verify_inputs=False)
    life.POOL=life.FailurePool(START,120)
    latch=life.ProcessLatch();latch.install(START+120)
    lease_path=out/'synthetic-safety-lease.json';c.save(lease_path,{'active_long_campaign':ctx[-1]})
    stop=threading.Event();burn=None;guard=None;result={};code=1
    try:
        def safety():latch.check();c.assert_lease(lease_path,ctx[-1])
        guard=c.Guard(START+120,safety,lambda:integrity.verify(ctx,root),None)
        guard.start()
        pre=integrity.verify(ctx,root,endpoint='preflight')
        def contend():
            n=1
            while not stop.is_set():
                for _ in range(12000):n=(n*1664525+1013904223)&0xffffffff
        burn=threading.Thread(target=contend,name='validation-python-CPU-contender');life.start_thread(burn)
        simulated=[]
        for update in range(12):
            n=0
            for j in range(40000):n=(n+j*j)%1000003
            guard.check(force=True)
            simulated.append(dict(update=update,kind='eval' if update%4==3 else 'update'))
        stop.set();burn.join(timeout=life.remaining(START+120,.5));c.require(not burn.is_alive(),'Contender survived')
        post=integrity.verify(ctx,root,endpoint='postflight')
        guard.close()
        result=dict(status='passed',preflight=pre,postflight=post,resource=guard.receipt(),boundaries=guard.boundaries,
            simulated_boundaries=simulated,archive_passes=2,archive_hotpath_member_reads=0,
            ML_imports=False,genuine_runtime_check_claimed=False,MPS_driver_observed=False,
            limitation='No ML equivalence, continuous immutability, fixed mutation latency, p99.9, or real legacy rebuild claim. MPS allocation is not measured in this stdlib-only process.')
        code=0
    except BaseException as error:
        result=dict(status='failed',error=repr(error),boundaries=[] if guard is None else guard.boundaries,
                    resource=None if guard is None else guard.receipt())
    finally:
        stop.set()
        if burn is not None:burn.join(timeout=.5)
        if guard is not None:
            guard.event.set()
            if guard.thread is not None:guard.thread.join(timeout=.5)
        result['elapsed_seconds']=time.monotonic()-START
        c.save(out/'stress-result.json',result)
    os._exit(code)

if __name__=='__main__':main()
