"""Exactly one fail-fast stdlib stage; preserves raw output and terminal status."""
from pathlib import Path
import datetime
import ast
import shutil
import sys
import hashlib
import json
import os
import subprocess
import time
H=Path(__file__).resolve().parent
ROOT=H.parents[3]

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')
def main():
    out=H/'unit-stage';out.mkdir()  # No reuse or retry.
    cache=out/'fresh-pycache';cache.mkdir();fixtures=out/'fixtures';fixtures.mkdir()
    alias='learning/.venv/bin/python'
    argv=[alias,'-B',str(H/'run_unit_suite.py')]
    env=dict(os.environ,VALIDATION_DIR=str(fixtures),PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=str(cache))
    relevant={'VALIDATION_DIR','PYTHONDONTWRITEBYTECODE','PYTHONPYCACHEPREFIX','PYTHONPATH','PYTHONHOME','PYTHONSAFEPATH','PATH','PYTORCH_ENABLE_MPS_FALLBACK'}
    save(out/'command.json',dict(argv=argv,cwd=str(ROOT),timeout_seconds=300,started_at_utc=now(),
        env_values={k:v for k,v in env.items() if k in relevant},
        other_env_value_sha256={k:hashlib.sha256(v.encode()).hexdigest() for k,v in env.items() if k not in relevant},
        interpreter_alias_preserved=True,ordered_modules=['test_r10','test_r7','test_repairs','test_boundary'],
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in H.glob('*.py')}))
    source=out/'sources';source.mkdir()
    for p in list(H.glob('*.py'))+[H/'protocol-r7-proposal.json',H/'PARENT-NEXT.md']:shutil.copyfile(p,source/p.name)
    shutil.copytree(H/'original-source',source/'original-source')
    shutil.copytree(H/'r6-source',source/'r6-source')
    shutil.copytree(H/'r9-source',source/'r9-source')
    shutil.copyfile(H/'retained-r9-injection.json',source/'retained-r9-injection.json')
    shutil.copyfile(H/'preparation-copy.json',source/'preparation-copy.json')
    required=[H/name for name in ('test_r10.py','fixture_preconditions.py','test_r7.py','test_repairs.py','test_boundary.py','run_unit_suite.py','long_d2.py','long_d2_executor.py','lifecycle.py','processes.py','boundary_integrity.py','source_equality.py')]
    required += [H/'original-source'/p.name for p in (H/'r6-source').glob('*.py') if (H/'original-source'/p.name).exists()]
    required += [H/'original-source'/name for name in ('long_d2.py','boundary_integrity.py')]
    required += [H.parent/name/'long_d2.py' for name in ('postovernight-long-D2-guard-prepare-r1','postovernight-long-D2-prepare-r4','postovernight-long-D2-boundary-prepare-r3')]
    required += [ROOT/'learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r4.json',ROOT/alias]
    expected_original=json.loads((H/'preparation-copy.json').read_text())['original_fixture_files']
    fixture_exact={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (H/'original-source').iterdir() if p.is_file()}==expected_original
    precheck=dict(original_fixture_exact=fixture_exact,required_files={str(p):p.is_file() for p in required},argv=argv,
                  alias_preserved=argv[0]==alias,validation_dir=str(fixtures),
                  validation_dir_empty=not any(fixtures.iterdir()),cache_empty=not any(cache.iterdir()),
                  no_old_envelopes=not any((H/name).exists() for name in ('capsule-final','long-identity.json','registration.json','classification.json')))
    # Read only fixture registration: evaluate only literal dict/list construction.
    namespace={'__builtins__':{},'dict':dict}
    tree=ast.parse((H/'fixture_preconditions.py').read_text())
    node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PHASES' for t in n.targets))
    exec(compile(ast.Module(body=[node],type_ignores=[]),'phase-registration','exec'),namespace)
    phases=namespace['PHASES']
    tree=ast.parse((H/'os_checks.py').read_text())
    node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CASES' for t in n.targets))
    exec(compile(ast.Module(body=[node],type_ignores=[]),'case-registration','exec'),namespace)
    cases=namespace['CASES']
    precheck['scenario_count']=len(cases)
    precheck['phase_registration']={phase:dict(expected_latch_phase=value[0],positive_prerequisites=list(value[1])) for phase,value in phases.items()}
    precheck['positive_metadata_valid']=(len(cases)==15 and all(value[0] in ('NORMAL','DEFER') and value[1] and len(set(value[1]))==len(value[1]) for value in phases.values())
        and all(not options.get('phase') or options['phase'] in phases for _,options,_ in cases))
    precheck['fresh_helper_output_policy']='tempfile.mkdtemp per test and repeated helper; exclusive outputs never reused'
    precheck['required_registrations']={str(H/name):(H/name).is_file() for name in ('retained-r9-injection.json','protocol-r7-proposal.json','preparation-copy.json','PARENT-NEXT.md')}
    precheck['positive_metadata_valid'] &= all(precheck['required_registrations'].values())
    save(out/'setup-precheck.json',precheck)
    if not (precheck['positive_metadata_valid'] and precheck['original_fixture_exact'] and all(precheck['required_files'].values()) and precheck['alias_preserved'] and precheck['validation_dir_empty'] and precheck['cache_empty'] and precheck['no_old_envelopes']):
        save(out/'raw-result.json',dict(raw_exit=None,validation_attempts=0,precheck_failed=True,no_retry=True))
        raise SystemExit(1)
    start=time.monotonic();result={}
    try:
        with (out/'stdout.log').open('xb') as stdout,(out/'stderr.log').open('xb') as stderr:
            process=subprocess.Popen(argv,cwd=ROOT,env=env,stdout=stdout,stderr=stderr)
            try:
                raw=process.wait(timeout=300)
                result=dict(raw_exit=raw,timed_out=False)
            except subprocess.TimeoutExpired:
                process.kill();raw=process.wait()
                result=dict(raw_exit=raw,timed_out=True,termination='unit stage timeout; no retry')
    finally:
        result.update(finished_at_utc=now(),elapsed_seconds=time.monotonic()-start,validation_attempts=1,
                      no_retry=True,cache_empty=not any(cache.iterdir()))
        save(out/'raw-result.json',result)
    print(json.dumps(result,sort_keys=True))
    raise SystemExit(result['raw_exit'] if not result.get('timed_out') else 124)
if __name__=='__main__':main()
