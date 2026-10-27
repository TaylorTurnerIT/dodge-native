"""Run evidence closeout, close logs, validate JSON, then hash final outputs."""
from pathlib import Path
import datetime,hashlib,json,os,subprocess,sys,time
H=Path(__file__).resolve().parent
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):h.update(block)
    return h.hexdigest()
def save(name,value):(H/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
argv=[sys.executable,'-B',str(H/'finalize_review.py')]
row=dict(argv=argv,cwd=str(Path.cwd()),started_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
         environment={k:os.environ.get(k) for k in ('PYTHONDONTWRITEBYTECODE','PYTHONPYCACHEPREFIX','PYTHONPATH')})
save('closeout-command.json',row);start=time.monotonic()
with (H/'closeout.stdout.log').open('xb') as out,(H/'closeout.stderr.log').open('xb') as err:
    result=subprocess.run(argv,stdout=out,stderr=err,timeout=60)
row.update(raw_exit=result.returncode,elapsed_seconds=time.monotonic()-start)
save('closeout-command.json',row)
assert result.returncode==0,(H/'closeout.stderr.log').read_text()
validations=[]
for path in sorted(H.rglob('*.json')):
    cmd=[sys.executable,'-B','-m','json.tool',str(path)]
    r=subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    validations.append(dict(argv=cmd,raw_exit=r.returncode,stderr=r.stderr))
    assert r.returncode==0
save('json-validation.json',dict(all_passed=True,commands=validations,excludes_itself=True))
files={str(p.relative_to(H)):dict(sha256=sha(p),bytes=p.stat().st_size)
       for p in sorted(H.rglob('*')) if p.is_file() and p.name!='output-manifest.json'}
save('output-manifest.json',dict(schema='frozen_r11_review_output_manifest_v1',files=files,
    excludes_itself=True,logs_closed_before_hashing=True,receipt_is_one_way_leaf=True))
subprocess.run([sys.executable,'-B','-m','json.tool',str(H/'output-manifest.json')],stdout=subprocess.DEVNULL,check=True)
print((H/'closeout.stdout.log').read_text())
print(json.dumps(dict(files=len(files),output_manifest_sha256=sha(H/'output-manifest.json'),JSON_validated=len(validations))))
