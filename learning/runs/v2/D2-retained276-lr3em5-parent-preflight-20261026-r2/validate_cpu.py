"""Replay frozen LR-arm CPU controls without modifying preparation artifacts."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT / "learning/runs/v2/D2-retained276-lr3em5-prepare-luna-20261026-r2"
REG_SHA = "8e17e1188253f091b62a8b60397663a530c4a865166f9568978dd009148308e7"

def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()

def verify():
    assert sha(SOURCE / "registration.json") == REG_SHA
    assert sha(SOURCE / "source-manifest.json") == "043155540dc0c403df463929a2a6cffbb7855697b623e7739b266cc823eb5886"
    reg = json.loads((SOURCE / "registration.json").read_text())
    for name, digest in reg["pins"].items():
        assert sha(name) == digest, name
    frozen = json.loads((SOURCE / "freeze-hashes.json").read_text())
    for name, digest in frozen["files_sha256"].items():
        assert sha(SOURCE / name) == digest, name
    assert not any(Path(reg["import_policy"]["pycache_prefix"]).iterdir())
    return {"pins": len(reg["pins"]), "frozen_files": len(frozen["files_sha256"])}

def main():
    started = time.monotonic()
    report = {"commands": [], "game_weight_optimizer_steps": 0, "MPS_used": False,
              "environment_constructed": False, "campaign_launched": False,
              "synthetic_progress_test_optimizer_steps": 3}
    try:
        report["before"] = verify()
        reg = json.loads((SOURCE / "registration.json").read_text())
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPYCACHEPREFIX=reg["import_policy"]["pycache_prefix"],
                   OMP_NUM_THREADS="4", MKL_NUM_THREADS="4", OPENBLAS_NUM_THREADS="4")
        env.pop("PYTHONPATH", None)
        commands = [[reg["interpreter"], "-B", str(SOURCE / name)] for name in
                    ("test_source_contract.py", "test_entry_evaluation.py", "test_entry_counter_binding.py",
                     "test_worker_progress_binding.py")]
        # Only the test's two evidence paths are redirected. Production modules remain untouched.
        script = """import copy,json,runpy,sys
from pathlib import Path
from unittest.mock import patch
source=Path(sys.argv[1]);owned=Path(sys.argv[2]);original=Path.open
mapping={source/'cpu-restore-and-controls.json':owned/'cpu-restore-and-controls.json',
         source/'attempts/mutated-resource-cost-anchor.json':owned/'mutated-resource-cost-anchor.json'}
def owned_open(path,mode='r',*args,**kwargs):
    target=mapping.get(path)
    if target is not None and (any(c in mode for c in 'wax+') or target.exists()):
        return original(target,mode,*args,**kwargs)
    return original(path,mode,*args,**kwargs)
with patch.object(Path,'open',owned_open):
    result=runpy.run_path(str(source/'cpu_restore_and_controls.py'),run_name='__main__')
helper=result['helper'];parent=result['parent']['optimizer'];controls={}
before=helper.begin_transition_record(parent,{})
for name in ['moment','step','epsilon']:
    effective=copy.deepcopy(parent);effective['param_groups'][0]['lr']=0.00003
    first=next(iter(effective['state']))
    if name=='moment':effective['state'][first]['exp_avg'].add_(1)
    elif name=='step':effective['state'][first]['step'].add_(1)
    else:effective['param_groups'][0]['eps']+=0.000001
    try:helper.transition_record(before,effective,result['delta'])
    except ValueError as error:
        assert 'outside declared' in str(error);controls[name]=True
    else:raise AssertionError('Mutation passed transition validator: '+name)
(owned/'extra-adam-controls.json').write_text(json.dumps({'status':'passed','controls':controls,'optimizer_steps':0},indent=2)+'\\n')
print(json.dumps({'extra_Adam_mutation_controls':controls}))
"""
        commands.append([reg["interpreter"], "-B", "-c", script, str(SOURCE), str(HERE)])
        for index, command in enumerate(commands):
            log = HERE / f"check-{index + 1}.log"
            with log.open("x") as stream:
                result = subprocess.run(command, cwd=SOURCE, env=env, stdout=stream,
                                        stderr=subprocess.STDOUT, timeout=120)
            report["commands"].append({"argv": command, "exit": result.returncode,
                                       "log": log.name, "log_sha256": sha(log)})
            assert result.returncode == 0, f"Check {index + 1} failed; inspect retained log"
        
        boundary_script = """import runpy,sys,tempfile
from pathlib import Path
from unittest.mock import patch
source=Path(sys.argv[1]);owned=Path(sys.argv[2]);scratch=owned/'scratch';scratch.mkdir()
original=tempfile.mkdtemp
def parent_temp(*args,**kwargs):
    kwargs['dir']=scratch
    return original(*args,**kwargs)
sys.path.insert(0,str(source))
with patch.object(tempfile,'mkdtemp',parent_temp):
    runpy.run_path(str(source/'test_execute_registration_boundary.py'),run_name='__main__')
"""
        extra_commands = [
            [reg["interpreter"], "-B", "-c", boundary_script, str(SOURCE), str(HERE)],
            [reg["interpreter"], "-B", str(SOURCE / "preflight_prepare.py"), str(SOURCE / "registration.json"), REG_SHA]]
        for index, command in enumerate(extra_commands, start=6):
            log=HERE/f"check-{index}.log"
            with log.open("x") as stream:
                result=subprocess.run(command,cwd=SOURCE,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=120)
            report["commands"].append({"argv":command,"exit":result.returncode,"log":log.name,"log_sha256":sha(log)})
            assert result.returncode==0,f"Check {index} failed; inspect retained log"
        report["after"] = verify()
        report["extra_Adam_mutations"] = json.loads((HERE / "extra-adam-controls.json").read_text())
        report["status"] = "passed_7_CPU_checks_and3_extra_Adam_controls_pending_exact_lease_and_unmocked_preflight"
    except BaseException as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        (HERE / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"status": report["status"], "elapsed_seconds": report["elapsed_seconds"]}))

if __name__ == "__main__":
    main()
