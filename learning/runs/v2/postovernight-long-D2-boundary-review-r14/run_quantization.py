import os,pathlib,subprocess,time,json,datetime,hashlib
p=pathlib.Path(__file__).resolve().parent;root=pathlib.Path.cwd();cache=p/'quantization-pycache';cache.mkdir()
command=[str(root/'learning/.venv/bin/python'),'-B',str(p/'registered_quantization.py')]
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=str(cache));start=time.monotonic()
registration=dict(command=command,script_sha256=hashlib.sha256((p/'registered_quantization.py').read_bytes()).hexdigest(),at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),timeout_seconds=30,environment={k:env[k] for k in ['PYTHONDONTWRITEBYTECODE','PYTHONPYCACHEPREFIX']})
(p/'registered-quantization-command.json').write_text(json.dumps(registration,indent=2)+'\n')
with (p/'registered-quantization.stdout.log').open('xb') as out,(p/'registered-quantization.stderr.log').open('xb') as err:r=subprocess.run(command,stdout=out,stderr=err,env=env,timeout=30)
result=dict(raw_exit=r.returncode,wall_seconds=time.monotonic()-start,invocations=1,cache_empty=not any(cache.iterdir()))
(p/'registered-quantization-raw.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));raise SystemExit(r.returncode)
