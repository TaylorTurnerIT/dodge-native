import datetime,hashlib,json,subprocess,sys,time
from pathlib import Path
root=Path(__file__).resolve().parent
label=sys.argv[1]; command=sys.argv[2:]
if (root/(label+'.json')).exists(): raise SystemExit('Refuse overwrite: '+label)
def sources():
 paths=[p for p in Path('crates').rglob('*') if p.is_file() and 'dodge-rl-env' not in p.parts]+[Path(p) for p in ['Cargo.toml','Cargo.lock','.cargo/config.toml','rust-toolchain.toml']]
 return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.exists()}
before=sources(); start=datetime.datetime.now(datetime.timezone.utc).isoformat(); t=time.monotonic()
with (root/(label+'.log')).open('wb') as out:
 result=subprocess.run(command,stdout=out,stderr=subprocess.STDOUT)
after=sources()
receipt={'command':command,'utc_start':start,'elapsed_seconds':time.monotonic()-t,'exit_code':result.returncode,'raw_log':label+'.log','raw_log_sha256':hashlib.sha256((root/(label+'.log')).read_bytes()).hexdigest(),'source_sha256':before,'source_changed_during_check':before!=after}
(root/(label+'.json')).write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({k:v for k,v in receipt.items() if k!='source_sha256'}))
print((root/(label+'.log')).read_text()[-16000:])
sys.exit(result.returncode)
