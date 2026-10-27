"""Finish independent preparation checks with the registered bytecode prefix."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PREVIOUS = ROOT / "learning/runs/v2/D2-retained276-continuation-parent-preflight-20261026-r1"
spec = importlib.util.spec_from_file_location("_parent_cpu_validation", PREVIOUS / "validate_cpu.py")
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)

def main():
    previous = json.loads((PREVIOUS / "validation.json").read_text())
    assert [item["exit"] for item in previous["commands"]] == [0, 0, 0, 1]
    source = validation.SOURCE
    reg = json.loads((source / "registration.json").read_text())
    started = time.monotonic()
    report = {"before": validation.verify(), "prior_checks_reused": previous["commands"][:3],
              "prior_invocation_failure": "Parent used its own empty cache prefix instead of the registered prefix; production rejected it before checkpoint restore.",
              "prior_evidence": str(PREVIOUS / "validation.json"),
              "production_source_changed": False, "campaign_launched": False}
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
               PYTHONPYCACHEPREFIX=reg["import_policy"]["pycache_prefix"])
    env.pop("PYTHONPATH", None)
    script = """import runpy,sys
from pathlib import Path
from unittest.mock import patch
source=Path(sys.argv[1]); target=Path(sys.argv[2]); original=Path.write_text
expected=source.parent/'cpu-restore-and-controls.json'
def owned_write(path,*args,**kwargs):
    if path == expected:
        return original(target,*args,**kwargs)
    raise AssertionError('Unexpected test write: '+str(path))
with patch.object(Path,'write_text',owned_write):
    runpy.run_path(str(source),run_name='__main__')
"""
    command = [reg["interpreter"], "-B", "-c", script, str(source / "cpu_restore_and_controls.py"),
               str(HERE / "cpu-restore-and-controls.json")]
    try:
        with (HERE / "cpu-restore.log").open("w") as stream:
            result = subprocess.run(command, cwd=source, env=env, stdout=stream,
                                    stderr=subprocess.STDOUT, timeout=120)
        report["restore_command"] = command
        report["restore_exit"] = result.returncode
        assert result.returncode == 0, "CPU restore failed; inspect retained log"
        report["after"] = validation.verify()
        restore = json.loads((HERE / "cpu-restore-and-controls.json").read_text())
        assert restore["status"] == "passed" and all(restore["negative_controls"].values())
        report["restore"] = restore
        report["status"] = "passed_preparation_only_pending_source_review_exact_lease_and_unmocked_preflight"
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = repr(error)
        raise
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        report["cpu_restore_log_sha256"] = hashlib.sha256((HERE / "cpu-restore.log").read_bytes()).hexdigest()
        (HERE / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({key: report[key] for key in ("status", "elapsed_seconds")}))

if __name__ == "__main__":
    main()
