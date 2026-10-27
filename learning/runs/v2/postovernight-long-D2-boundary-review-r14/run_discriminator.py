import pathlib,subprocess,time,json,datetime,sys
p=pathlib.Path(__file__).resolve().parent
command=[sys.executable,'-B',str(p/'discriminate.py')]
start=time.monotonic();at=datetime.datetime.now(datetime.timezone.utc).isoformat()
with (p/'discriminator.stdout.log').open('xb') as out,(p/'discriminator.stderr.log').open('xb') as err:
 r=subprocess.run(command,stdout=out,stderr=err,timeout=60)
value=dict(command=command,at_utc=at,raw_exit=r.returncode,wall_seconds=time.monotonic()-start,timeout_seconds=60,invocations=1)
(p/'discriminator-command.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value));raise SystemExit(r.returncode)
