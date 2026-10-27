"""Observe exact retiring/new watchdog handles without changing their behavior."""
from pathlib import Path
import json,os,signal,sys,threading,time
OUT=Path(__file__).resolve().parents[1];PREP=OUT.parent/'postovernight-long-D2-prepare-r4';sys.path.insert(0,str(PREP))
import synthetic as fixture
root=Path(sys.argv[sys.argv.index('--root')+1]).resolve();lock=threading.RLock()
def event(kind,execution,**extra):
 with lock,(root/'takeover-events.jsonl').open('a') as f:
  f.write(json.dumps(dict(kind=kind,pid=os.getpid(),thread=threading.get_ident(),monotonic=time.monotonic(),pool=id(execution.pool),first=execution.pool.first,until=execution.pool.until,**extra),sort_keys=True)+'\n')
original_monitor=fixture.e.Execution.monitor
original_fail=fixture.e.Execution.fail
original_final=fixture.life.final_exit
current=[None]
def monitor(execution):
 current[0]=execution;stop=execution.stop
 event('monitor_start',execution,stop=id(stop),stop_set=stop.is_set())
 try:return original_monitor(execution)
 finally:event('monitor_exit',execution,stop=id(stop),stop_set=stop.is_set())
def fail(execution,*a,**k):
 previous=execution.pool.until;result=original_fail(execution,*a,**k)
 event('failure',execution,previous_until=previous)
 return result
def final(code,latch,deadline,failed=lambda:False):
 execution=current[0]
 if execution is not None:event('final',execution,code=code,deadline=deadline,watchdog_alive=execution.watchdog.is_alive(),owned_threads=[dict(ident=t.ident,name=t.name,alive=t.is_alive()) for t in threading.enumerate() if t.name.startswith('long-D2-')])
 return original_final(code,latch,deadline,failed)
fixture.e.Execution.monitor=monitor;fixture.e.Execution.fail=fail;fixture.life.final_exit=final
fixture.main()
