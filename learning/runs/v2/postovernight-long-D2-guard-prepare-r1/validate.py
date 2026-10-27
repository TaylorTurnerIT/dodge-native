"""Exclusive, fail-fast stdlib runner. Every run retains all executed root sources."""
from pathlib import Path
import json,os,shutil,subprocess,sys,time
H=Path(__file__).resolve().parent

def command(name,argv,timeout):
    out=H/'attempts'/name;out.mkdir(parents=True,exist_ok=False)
    (out/'sources').mkdir()
    for p in H.glob('*.py'):shutil.copyfile(p,out/'sources'/p.name)
    start=time.monotonic();value=dict(argv=argv,cwd=str(H),timeout_seconds=timeout,start_monotonic=start)
    (out/'command-start.json').write_text(json.dumps(value,indent=2)+'\n')
    try:
        with (out/'raw.log').open('x') as f:
            r=subprocess.run(argv,stdout=f,stderr=subprocess.STDOUT,timeout=timeout,cwd=H,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',LONG_D2_TEST_EVIDENCE=str(out),TMPDIR=str(out/'tmp')))
        value['raw_exit']=r.returncode
    except BaseException as error:value.update(raw_exit=None,error=repr(error));raise
    finally:
        value['elapsed_seconds']=time.monotonic()-start
        (out/'command-result.json').write_text(json.dumps(value,indent=2)+'\n')
    if r.returncode:raise SystemExit('Failed '+name+'; retained raw.log; no retry')

if __name__=='__main__':
    phase=sys.argv[1];name=sys.argv[2]
    if phase=='unit':
        out=H/'attempts'/name;(out/'tmp').mkdir(parents=True)
        # command() owns creation, so undo only the empty setup directories.
        (out/'tmp').rmdir();out.rmdir()
        command(name,[sys.executable,'-B',str(H/'unit_suite.py')],120)
    elif phase=='freeze':command(name,[sys.executable,'-B',str(H/'freeze.py')],120)
    elif phase=='matrix':command(name,[sys.executable,'-B',str(H/'run_focused_checks.py'),str(H/'attempts'/(name+'-cases'))],420)
    elif phase=='stress':command(name,[sys.executable,'-B',str(H/'stress.py')],180)
    elif phase=='preflight':
        import long_d2 as c
        r=c.read_json(H/'registration.json');command(name,[sys.executable,'-B',r['executor'],'preflight','--registration',str(H/'registration.json')],90)
