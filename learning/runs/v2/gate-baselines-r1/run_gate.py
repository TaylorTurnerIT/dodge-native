"""One bounded sequential D3/D1 campaign. Native failures never retry."""
from __future__ import annotations
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
sys.dont_write_bytecode = True
EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[3]
WORKTREE = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-5d7162c0')
HEAD = 'd7ad95127ad7529c5217a51ae9dc5cfedd3f2365'
EXE_SHA = '922485d26128dbdc4df0868a5df7d7e72bc8f4135addfd691a1e11484d785d39'
HELPER_SHA = '8d0871bdd3fcbee22e59091baaece3611bc6b8088cae450bca0caa4ec0c42e4e'
PLAN_SHA = '964779af4134e366dcbdcaaaf2f005da94c7c1622dddcfc5c476f02b7c8adb61'
START = dt.datetime.fromisoformat('2026-10-24T06:36:26+00:00')
CUTOFF = dt.datetime.fromisoformat('2026-10-24T13:00:00+00:00')
HELPER = ROOT / 'learning/scripts/v2_run_m0_campaign.py'
PLAN = ROOT / 'docs/v2-gate-baseline-campaign.md'
STATE = ROOT / 'learning/runs/v2-orchestration/state.json'
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def load_module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
def write(path, value):
    with path.open('w') as handle:
        json.dump(value,handle,indent=2,sort_keys=True,allow_nan=False); handle.write('\n')
def utc():
    return dt.datetime.now(dt.timezone.utc)
def need(test, message):
    if not test: raise RuntimeError(message)
need(sha(HELPER)==HELPER_SHA,'immutable helper identity mismatch')
helper=load_module('frozen_runner_helper',HELPER)
audit=load_module('registered_gate_checker',EVIDENCE/'audit_gate.py')
SCRIPT_SHA=sha(Path(__file__))
CHECKER_SHA=sha(EVIDENCE/'audit_gate.py')
COPIES=[]
def preflight(label, remaining_native_seconds):
    need(sha(Path(__file__))==SCRIPT_SHA,'owned runner changed after launch')
    need(sha(EVIDENCE/'audit_gate.py')==CHECKER_SHA,'checker changed after launch')
    need(sha(HELPER)==HELPER_SHA,'immutable helper changed')
    need(sha(PLAN)==PLAN_SHA,'registered plan changed')
    need((utc()-START).total_seconds()+remaining_native_seconds <1500,'full task budget does not fit remaining stages')
    need((CUTOFF-utc()).total_seconds()>=1500+600,'full registered budget plus ten-minute cutoff reserve does not fit')
    state_bytes=STATE.read_bytes()
    state=audit.m0.parse(state_bytes.decode())
    (EVIDENCE/f'{label}-state-at-read.json').write_bytes(state_bytes)
    need(state['tasks']['milestone0_r2']['worktree']==str(WORKTREE),'state fixture path mismatch')
    need(state['tasks']['gate_baselines_r1']['plan_sha256']==PLAN_SHA,'state plan identity mismatch')
    # Dynamic state is a launch observation, never treated as static proof.
    _, worktree, executable, frozen=helper.preflight()
    need(worktree==WORKTREE,'helper fixture path mismatch')
    need(frozen['head']==HEAD,'registered HEAD mismatch')
    need(frozen['executable_sha256']==EXE_SHA and sha(executable)==EXE_SHA,'registered executable mismatch')
    need(executable==WORKTREE/'target/release/examples/m0_baseline','registered executable path mismatch')
    capsule=audit.m0.parse((audit.m0.FROZEN/'manifest.json').read_text())
    need(sha(audit.m0.FROZEN/'manifest.json')==audit.m0.FROZEN_SHA,'review capsule identity mismatch')
    manifest=WORKTREE/'target/v2-m0-review-r2/final-manifest.json'
    need(sha(manifest)==capsule['files']['evidence/final-manifest.json'],'frozen final manifest identity mismatch')
    for rel,expected in capsule['files'].items():
        need(sha(audit.m0.FROZEN/rel)==expected,'capsule bytes changed: '+rel)
    need(len(frozen['new_source_and_docs_sha256'])==5,'five frozen harness/document inputs required')
    tracked=list(filter(None,subprocess.check_output(['git','ls-files','-z'],cwd=WORKTREE).decode().split('\0')))
    need(len(tracked)==33,'all 33 tracked original paths required')
    hashes={}
    for rel in tracked:
        original=subprocess.check_output(['git','show',f'{HEAD}:{rel}'],cwd=WORKTREE)
        need((WORKTREE/rel).read_bytes()==original,'tracked HEAD bytes changed: '+rel)
        hashes[rel]=sha(WORKTREE/rel)
    need(subprocess.check_output(['git','rev-parse','HEAD'],cwd=WORKTREE,text=True).strip()==HEAD,'original HEAD mismatch')
    processes=subprocess.check_output(['ps','-axo','pid=,pgid=,comm='],text=True)
    need(not any(line.split()[-1].endswith('/m0_baseline') for line in processes.splitlines() if line.split()),'another native baseline is active')
    receipt={'status':'all_frozen_identities_verified','utc':utc().isoformat(),'head':HEAD,
        'worktree':str(WORKTREE),'tracked_count':len(tracked),'all_tracked_head_sha256':hashes,
        'harness_doc_sha256':frozen['new_source_and_docs_sha256'],'executable':str(executable),'executable_sha256':EXE_SHA,
        'final_manifest_sha256':sha(manifest),'helper_sha256':HELPER_SHA,'runner_sha256':SCRIPT_SHA,'checker_sha256':CHECKER_SHA,
        'plan_sha256':PLAN_SHA,'frozen_D2_auditor_sha256':sha(audit.ORIGINAL),
        'state_sha256_at_read':hashlib.sha256(state_bytes).hexdigest(),'state_is_dynamic_observation':True,
        'task_elapsed_seconds':(utc()-START).total_seconds(),'task_budget_seconds':1500,
        'cutoff_utc':CUTOFF.isoformat(),'cutoff_reserve_seconds':600}
    write(EVIDENCE/f'{label}-identity.json',receipt)
    return receipt
def mirror(name):
    source=WORKTREE/audit.RUNS[name]['output']
    if not source.exists(): return
    destination=EVIDENCE/'native-results'/name
    destination.mkdir(parents=True,exist_ok=False)
    for path in sorted(source.rglob('*')):
        if not path.is_file(): continue
        target=destination/path.relative_to(source); target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,target)
        need(path.read_bytes()==target.read_bytes(),'mirror byte mismatch')
        COPIES.append({'source':str(path),'copy':str(target),'bytes':path.stat().st_size,'sha256':sha(path),'copy_sha256':sha(target)})
    write(EVIDENCE/'native-results/copy-manifest.json',{'status':'unmodified_native_receipts_mirrored','files':COPIES})
def main():
    need(not (EVIDENCE/'supervisor.json').exists(),'campaign already invoked; retries forbidden')
    for settings in audit.RUNS.values():
        need(not (WORKTREE/settings['output']).exists(),'native destination exists; no overwrite or retry')
    receipt={'status':'running','started_at_utc':utc().isoformat(),'full_task_started_at_utc':START.isoformat(),
        'full_task_budget_seconds':1500,'runner_sha256':SCRIPT_SHA,'helper_sha256':HELPER_SHA,
        'checker_sha256':CHECKER_SHA,'plan_sha256':PLAN_SHA,'head':HEAD,'executable_sha256':EXE_SHA,
        'phases':[],'audits':[],'launch_command':[sys.executable,str(Path(__file__))]}
    write(EVIDENCE/'supervisor.json',receipt)
    try:
        for name,remaining in [('d3',1050),('d1',135)]:
            receipt['last_preflight']=preflight('pre-'+name,remaining)
            receipt.setdefault('state_sha256_at_launch',receipt['last_preflight']['state_sha256_at_read'])
            write(EVIDENCE/'supervisor.json',receipt)
            print(f'{utc().isoformat()} launch {name}: {audit.command(name)}',flush=True)
            try:
                result=helper.phase(name,audit.command(name),WORKTREE,EVIDENCE,audit.RUNS[name]['seconds'])
                receipt['phases'].append(result)
            finally:
                mirror(name)
            write(EVIDENCE/'supervisor.json',receipt)
            output=EVIDENCE/f'{name}-audit-r1.json'
            cmd=[sys.executable,str(EVIDENCE/'audit_gate.py'),'--run',name,'--output',str(output)]
            with (EVIDENCE/f'{name}-audit-r1.log').open('xb') as log:
                checked=subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=60,check=False)
            receipt['audits'].append({'run':name,'command':cmd,'exit_code':checked.returncode,'output':str(output)})
            write(EVIDENCE/'supervisor.json',receipt)
            need(checked.returncode==0,f'{name} checker failed; retain attempt and stop before next stage')
            print(f'{utc().isoformat()} {name} native complete and independent audit passed',flush=True)
        receipt['final_identity']=preflight('post-campaign',0)
        need((utc()-START).total_seconds()<=1500,'full task exceeded 1500 seconds')
        for item in COPIES:
            need(sha(Path(item['source']))==item['sha256']==sha(Path(item['copy'])),'native/copy hash changed')
        receipt['status']='D3_gate_baselines_and_D1_sanity_receipts_independently_verified'
    except BaseException as error:
        receipt.update(status='failed_stop_no_future_stage',error=f'{type(error).__name__}: {error}')
        raise
    finally:
        receipt['finished_at_utc']=utc().isoformat()
        receipt['full_task_elapsed_seconds']=(utc()-START).total_seconds()
        write(EVIDENCE/'supervisor.json',receipt)
if __name__=='__main__':
    main()
