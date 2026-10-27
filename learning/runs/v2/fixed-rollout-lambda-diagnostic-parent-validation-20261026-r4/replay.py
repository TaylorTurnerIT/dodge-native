import hashlib,json,os,subprocess,time
from pathlib import Path
ROOT=Path.cwd();OWN=Path(__file__).resolve().parent;SOURCE=ROOT/'learning/runs/v2/fixed-rollout-lambda-diagnostic-luna-20261026-r4'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
receipt=json.loads((SOURCE/'receipt.json').read_text())
for p,h in receipt['input_sha256'].items():assert sha(ROOT/p)==h,p
for p,h in receipt['output_sha256'].items():assert sha(SOURCE/p)==h,p
before={str(p.relative_to(SOURCE)):sha(p) for p in SOURCE.rglob('*') if p.is_file()}
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=str(OWN/'empty-cache'),OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2');env.pop('PYTHONPATH',None)
script="""import runpy,sys,tempfile
from pathlib import Path
from unittest.mock import patch
source=Path(sys.argv[1]);scratch=Path(sys.argv[2]);name=sys.argv[3];original=tempfile.mkdtemp
def owned_temp(suffix=None,prefix=None,dir=None):
    if dir is None or Path(dir).resolve()==source.resolve():dir=scratch
    return original(suffix=suffix,prefix=prefix,dir=dir)
with patch.object(tempfile,'mkdtemp',owned_temp):runpy.run_path(str(source/name),run_name='__main__')
"""
started=time.monotonic();commands=[]
for name in ['controls.py','controls_r4.py']:
 log=OWN/(name+'.log');command=[str(ROOT/'python/.venv/bin/python'),'-B','-c',script,str(SOURCE),str(OWN/'scratch'),name]
 with log.open('x') as f:r=subprocess.run(command,cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=60)
 commands.append({'name':name,'raw_exit':r.returncode,'log_sha256':sha(log)});assert r.returncode==0,name
assert before=={str(p.relative_to(SOURCE)):sha(p) for p in SOURCE.rglob('*') if p.is_file()};assert not any((OWN/'empty-cache').iterdir())
report={'status':'passed_two_synthetic_CPU_control_scripts_pending_R4_source_review','commands':commands,'elapsed_seconds':time.monotonic()-started,'source_unchanged':True,'source_files':len(before),'actual_rollout_or_capture':False,'MPS':False,'training':False,'source_receipt_sha256':sha(SOURCE/'receipt.json')}
(OWN/'validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
