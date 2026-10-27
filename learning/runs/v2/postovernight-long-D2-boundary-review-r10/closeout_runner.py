from pathlib import Path
import datetime,hashlib,json,os,subprocess,sys,time
H=Path(__file__).resolve().parent
name,script=sys.argv[1:]
command=[sys.executable,'-B',str(H/script)]
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
record=dict(argv=command,cwd=str(Path.cwd()),started_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),environment={k:env.get(k) for k in ('PYTHONDONTWRITEBYTECODE','PYTHONPYCACHEPREFIX','PYTHONPATH','VALIDATION_DIR')},environment_sha256=hashlib.sha256(json.dumps(env,sort_keys=True).encode()).hexdigest())
(H/(name+'-command.json')).write_text(json.dumps(record,indent=2)+'\n')
start=time.monotonic()
with (H/(name+'.stdout.log')).open('xb') as out,(H/(name+'.stderr.log')).open('xb') as err:
 p=subprocess.run(command,env=env,stdout=out,stderr=err,timeout=60)
record.update(raw_exit=p.returncode,elapsed_seconds=time.monotonic()-start)
(H/(name+'-command.json')).write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
print((H/(name+'.stdout.log')).read_text())
print((H/(name+'.stderr.log')).read_text())

if p.returncode==0:
 files={str(f.relative_to(H)):dict(bytes=f.stat().st_size,sha256=hashlib.sha256(f.read_bytes()).hexdigest()) for f in H.rglob('*') if f.is_file() and f.name!='output-manifest.json'}
 (H/'output-manifest.json').write_text(json.dumps(dict(schema='review_output_manifest_v1',excludes_itself=True,files=files),indent=2)+'\n')
