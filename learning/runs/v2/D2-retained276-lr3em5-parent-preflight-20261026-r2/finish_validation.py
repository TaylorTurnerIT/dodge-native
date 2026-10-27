"""Finish parent CPU replay after correcting parent-only tempfile redirection."""
import json,os,subprocess,time
from pathlib import Path
from validate_cpu import SOURCE,HERE,ROOT,REG_SHA,verify,sha
report=json.loads((HERE/'validation.json').read_text());report['preserved_parent_replay_failure']=report.pop('error',None)
reg=json.loads((SOURCE/'registration.json').read_text())
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=reg['import_policy']['pycache_prefix'],OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4');env.pop('PYTHONPATH',None)
boundary_script="""import runpy,sys,tempfile
from pathlib import Path
from unittest.mock import patch
source=Path(sys.argv[1]);scratch=Path(sys.argv[2])/'scratch';original=tempfile.mkdtemp
def parent_temp(suffix=None,prefix=None,dir=None):
    return original(suffix=suffix,prefix=prefix,dir=scratch)
sys.path.insert(0,str(source))
with patch.object(tempfile,'mkdtemp',parent_temp):
    runpy.run_path(str(source/'test_execute_registration_boundary.py'),run_name='__main__')
import execute_once
reg=execute_once.r.read(source/'registration.json');output=Path(reg['output']);assert not output.exists()
class Reached(Exception):pass
def sentinel(path,*args,**kwargs):
    assert path.resolve()==output.resolve();raise Reached()
with patch.object(Path,'mkdir',sentinel):
    try:execute_once.execute(source/'registration.json',sys.argv[3])
    except Reached:pass
    else:raise AssertionError('real registration did not reach mutation boundary')
assert not output.exists()
print('Unmocked read of real frozen registration reached actual execute output boundary; no output mutation')
"""
commands=[[reg['interpreter'],'-B','-c',boundary_script,str(SOURCE),str(HERE),REG_SHA],[reg['interpreter'],'-B',str(SOURCE/'preflight_prepare.py'),str(SOURCE/'registration.json'),REG_SHA]]
started=time.monotonic();verify()
for index,command in enumerate(commands,start=6):
    log=HERE/f'check-{index}-parent-corrected.log'
    with log.open('x') as f:r=subprocess.run(command,cwd=SOURCE,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=120)
    report['commands'].append({'argv':command,'exit':r.returncode,'log':log.name,'log_sha256':sha(log)})
    assert r.returncode==0,f'Failed check {index}; preserve log'
report['after']=verify();report['extra_Adam_mutations']=json.loads((HERE/'extra-adam-controls.json').read_text())
report['status']='passed_7_CPU_checks_and3_extra_Adam_controls_pending_exact_lease_and_unmocked_preflight'
report['corrected_parent_replay_seconds']=time.monotonic()-started
report['preparation_metadata_note']='Copied validation.json retains R1 registration SHA and13800 pin label; current independently replayed R2 registration and13801 pins are authoritative preparation evidence.'
(HERE/'validation-corrected.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'status':report['status'],'after':report['after'],'seconds':report['corrected_parent_replay_seconds']}))
