"""Real lifetime signal controls, always run as an owned subprocess."""
from pathlib import Path
import json
import os
import signal
import sys
import time
import lifecycle as life
mode=sys.argv[1];out=Path(sys.argv[2]);t0=time.monotonic()
life.POOL=life.FailurePool(t0)
latch=life.ProcessLatch();arms=[];dispositions=[]
real_timer=signal.setitimer;real_signal=signal.signal

def timer(which,seconds,*args):
    arms.append(seconds);return real_timer(which,seconds,*args)

def disposition(number,handler):
    dispositions.append(str(handler))
    assert handler!=signal.SIG_DFL
    return real_signal(number,handler)
signal.setitimer=timer;signal.signal=disposition
raised=0
if mode=='expired':
    try:latch.install(t0-1)
    except life.Stop:raised+=1
elif mode in ('normal','defer','failure'):
    latch.install(t0+.04)
    if mode!='normal':latch.phase=mode.upper()
    try:time.sleep(.07)
    except life.Stop:raised+=1
    latch.phase='FAILURE'
    for number in (signal.SIGINT,signal.SIGTERM,signal.SIGINT):os.kill(os.getpid(),number)
else:
    latch.install(t0+2)
    if mode=='pending-alarm':signal.pthread_sigmask(signal.SIG_BLOCK,life.OWNED);os.kill(os.getpid(),signal.SIGALRM)
value=dict(mode=mode,arms=arms,nonzero_arms=sum(x>0 for x in arms),raised=raised,
           cancellation_requests=latch.cancellation_requests,alarm_seen=latch.alarm_seen,
           no_default_restore=all(x!='0' for x in dispositions))
out.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')
life.final_exit(2,latch,t0+2)
