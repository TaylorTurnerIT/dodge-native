import hashlib,json,os,subprocess,time
from pathlib import Path
ROOT=Path.cwd();OWN=Path(__file__).resolve().parent
assert not (OWN/'execution-started.json').exists()
env=os.environ.copy();env.pop('PYTHONPATH',None);env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=str(OWN/'empty-cache'),OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4')
command=[str(ROOT/'python/.venv/bin/python'),'-B',str(OWN/'capture_once.py')];start=time.monotonic()
with (OWN/'capture.log').open('x') as log:
    try:r=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180);code=r.returncode;error=None
    except subprocess.TimeoutExpired:code=None;error='Parent180secondouterdeadline;owned direct child killed and reaped by subprocess.run'
(OWN/'capture-execution.json').write_text(json.dumps({'command':command,'actual_launch_count':1,'raw_exit':code,'error':error,'observed_wall_seconds':time.monotonic()-start,'training':False},indent=2)+'\n')
print(json.dumps({'raw_exit':code,'error':error,'wall_seconds':time.monotonic()-start}));raise SystemExit(0 if code==0 else 1)
