"""Independent validation of frozen R2; no lease or actual campaign."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT / "learning/runs/v2/D2-retained276-continuation-prepare-luna-20261026-r2"
R1 = SOURCE.with_name("D2-retained276-continuation-prepare-luna-20261026-r1")
REG_SHA = "477217f3c7617ccbe01c651db8932eab01f54ea3924f213e67b413e640cf866c"
MANIFEST_SHA = "0c11fd8338d85f5c55d76583c7909d62e45101ec66ef4ce00dab7bcab803b37d"

def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def verify():
    assert sha(SOURCE / "registration.json") == REG_SHA
    assert sha(SOURCE / "source-manifest.json") == MANIFEST_SHA
    reg = json.loads((SOURCE / "registration.json").read_text())
    manifest = json.loads((SOURCE / "source-manifest.json").read_text())
    for path, expected in reg["pins"].items():
        assert sha(path) == expected, path
    for path, expected in manifest["files"].items():
        assert sha(SOURCE / path) == expected, path
    assert not list(Path(reg["import_policy"]["pycache_prefix"]).rglob("*"))
    expected = (R1 / "runner.py").read_text().replace(
        'RUN_ID = "D2-retained276-continuation-20261026-r1"',
        'RUN_ID = "D2-retained276-continuation-20261026-r2"').replace(
        "gradient_alignment_diagnostics=True)", "gradient_alignment_diagnostics=True, progress=progress)")
    assert (SOURCE / "runner.py").read_text() == expected
    assert (SOURCE / "execute_once.py").read_bytes() == (R1 / "execute_once.py").read_bytes()
    assert sha(SOURCE / "continuation-config.json") == "f858a63c324fc312f794c0423aa56db2daf60793b62990cd51fa400afe3af628"
    return {"pins": len(reg["pins"]), "manifest_files": len(manifest["files"]),
            "production_delta": "RUN_ID plus progress keyword only; launcher unchanged"}

def main():
    started = time.monotonic()
    reg = json.loads((SOURCE / "registration.json").read_text())
    report = {"before": verify(), "commands": [], "actual_campaigns": 0, "mps_operations": 0,
              "real_environment_constructions": 0, "game_weight_optimizer_steps": 0,
              "progress_regression_synthetic_optimizer_steps": 3}
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
               PYTHONPYCACHEPREFIX=reg["import_policy"]["pycache_prefix"])
    env.pop("PYTHONPATH", None)
    commands = [[reg["interpreter"], "-B", str(SOURCE / name)] for name in
                ("test_source_contract.py", "test_entry_counter_binding.py", "test_entry_evaluation.py",
                 "test_worker_progress_binding.py")]
    script = """import runpy,sys
from pathlib import Path
from unittest.mock import patch
source=Path(sys.argv[1]); target=Path(sys.argv[2]); original=Path.write_text
expected=source.parent/'cpu-restore-and-controls.json'
def owned_write(path,*args,**kwargs):
    if path == expected:
        return original(target,*args,**kwargs)
    raise AssertionError('Unexpected write: '+str(path))
with patch.object(Path,'write_text',owned_write):
    runpy.run_path(str(source),run_name='__main__')
"""
    commands.append([reg["interpreter"], "-B", "-c", script,
                     str(SOURCE / "cpu_restore_and_controls.py"), str(HERE / "cpu-restore-and-controls.json")])
    try:
        for index, command in enumerate(commands):
            log = HERE / f"check-{index + 1}.log"
            with log.open("w") as stream:
                result = subprocess.run(command, cwd=SOURCE, env=env, stdout=stream,
                                        stderr=subprocess.STDOUT, timeout=120)
            report["commands"].append({"argv": command, "exit": result.returncode,
                                       "log": log.name, "log_sha256": sha(log)})
            assert result.returncode == 0, f"Check {index + 1} failed; inspect preserved log"
        report["after"] = verify()
        report["status"] = "passed_preparation_pending_frozen_review_exact_lease_and_unmocked_preflight"
    except BaseException as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        (HERE / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({key: report[key] for key in ("status", "elapsed_seconds")}))

if __name__ == "__main__":
    main()
