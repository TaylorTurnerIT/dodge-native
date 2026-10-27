import sys,subprocess,json,time,hashlib,pathlib,datetime
root=pathlib.Path(__file__).resolve().parent
cmd=sys.argv[1]
n=len(list(root.glob('command-*.json')))+1
start=time.monotonic(); p=subprocess.run(cmd,shell=True,executable='/bin/zsh',stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
(root/f'command-{n:03d}.log').write_bytes(p.stdout)
(root/f'command-{n:03d}.json').write_text(json.dumps({'command':cmd,'cwd':str(pathlib.Path.cwd()),'exit_code':p.returncode,'elapsed_seconds':time.monotonic()-start,'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'log':f'command-{n:03d}.log'},indent=2)+'\n')
sys.stdout.buffer.write(p.stdout);sys.exit(p.returncode)
