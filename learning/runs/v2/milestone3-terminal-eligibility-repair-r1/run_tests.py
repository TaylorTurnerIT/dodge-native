"""Retain exact commands, source archives, timing and all synthetic test outcomes."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,os,subprocess,sys,time,shutil
root=Path.cwd(); out=root/'learning/runs/v2/milestone3-terminal-eligibility-repair-r1'
label,source_name,*selection=sys.argv[1:];dest=out/label;dest.mkdir(exist_ok=False)
(dest/'executed-source').mkdir()
source=root if source_name=='live' else root/'learning/.cache/v2-m3-runtime-review-r2'
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
paths=sorted((root/'python/dodge_rl').rglob('*.py'))+sorted((root/'python/tests').glob('*.py'))+sorted((root/'python/dodge_rl').glob('*.so'))
actual={str(p.relative_to(root)):h(p) for p in paths}
for name in ('supervision','checkpoints','train_teacher'):
 p=source/'python/dodge_rl'/f'{name}.py';actual[f'executed:{p}']=h(p)
 for q in [p]:
  target=dest/'executed-source'/q.name;shutil.copy2(q,target)
(dest/'executed-source.json').write_text(json.dumps(actual,indent=2,sort_keys=True)+'\n')
bootstrap='''
import hashlib, importlib.util, pathlib, sys
import dodge_rl
source_root=pathlib.Path(sys.argv[1])
for name in ('supervision','checkpoints','train_teacher'):
    path=source_root/'python/dodge_rl'/(name+'.py')
    spec=importlib.util.spec_from_file_location('dodge_rl.'+name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    setattr(dodge_rl,name,module)
    spec.loader.exec_module(module)
    print('EXECUTED_SOURCE',name,str(path),hashlib.sha256(path.read_bytes()).hexdigest(),flush=True)
import pytest
raise SystemExit(pytest.main(sys.argv[2:]))
'''
argv=[str(root/'python/.venv/bin/python'),'-B','-c',bootstrap,str(source),'-q','-p','no:cacheprovider','--basetemp',str(dest/'fixtures'),'--tb=short','--junitxml',str(dest/'junit.xml'),*selection]
started=datetime.now(timezone.utc).isoformat();begin=time.monotonic()
with (dest/'stdout-stderr.log').open('x') as log:
 try:status=subprocess.run(argv,cwd=root,env=dict(os.environ,PYTHONPATH='python',PYTHONDONTWRITEBYTECODE='1'),stdout=log,stderr=subprocess.STDOUT,timeout=120).returncode
 except subprocess.TimeoutExpired:status=124
receipt={'argv':argv,'cwd':str(root),'environment':{'PYTHONPATH':'python','PYTHONDONTWRITEBYTECODE':'1'},'exit_status':status,'started_at_utc':started,'duration_seconds':time.monotonic()-begin,'source_unchanged_during_test':all(h(root/p)==d for p,d in actual.items() if not p.startswith('executed:')),'executed_source':{p:d for p,d in actual.items() if p.startswith('executed:')}}
(dest/'command-result.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
print(json.dumps(receipt,indent=2));print((dest/'stdout-stderr.log').read_text()[-12000:])
raise SystemExit(status)
