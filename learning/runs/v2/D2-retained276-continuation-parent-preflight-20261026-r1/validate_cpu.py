"""Independent CPU preparation replay; does not reserve or launch training."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT / "learning/runs/v2/D2-retained276-continuation-prepare-luna-20261026-r1"
REG_SHA = "30a290809c52190313ac723ebe44dd7ab43f4bf6da6fc0b841f83f979b1e17a7"

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def verify():
    assert sha(SOURCE / "registration.json") == REG_SHA
    reg = json.loads((SOURCE / "registration.json").read_text())
    manifest = json.loads((SOURCE / "source-manifest.json").read_text())
    assert sha(SOURCE / "source-manifest.json") == "08fa53152689701920f175d1bf3e40b217c40fa97d4faa806deffdf99d76e640"
    for path, expected in reg["pins"].items():
        assert sha(Path(path)) == expected, path
    for path, expected in manifest["files"].items():
        assert sha(SOURCE / path) == expected, path
    assert not list((SOURCE / "empty-pycache").rglob("*"))
    return {"pins": len(reg["pins"]), "manifest_files": len(manifest["files"])}

def main():
    started = time.monotonic()
    report = {"scope": "CPU preparation only; no lease, environment, MPS, optimizer steps or campaign", "commands": []}
    report["before"] = verify()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPYCACHEPREFIX=str(HERE / "empty-cache"))
    env.pop("PYTHONPATH", None)
    (HERE / "empty-cache").mkdir(exist_ok=True)
    python = str(ROOT / "python/.venv/bin/python")
    commands = [[python, "-B", str(SOURCE / name)] for name in
                ("test_source_contract.py", "test_entry_counter_binding.py", "test_entry_evaluation.py")]
    # Redirect only this test's evidence write. Production source/imports stay unchanged.
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
    commands.append([python, "-B", "-c", script, str(SOURCE / "cpu_restore_and_controls.py"),
                     str(HERE / "cpu-restore-and-controls.json")])
    try:
        for index, command in enumerate(commands):
            log = HERE / f"check-{index + 1}.log"
            with log.open("w") as stream:
                result = subprocess.run(command, cwd=SOURCE, env=env, stdout=stream,
                                        stderr=subprocess.STDOUT, timeout=120)
            report["commands"].append({"argv": command, "exit": result.returncode,
                                       "log": log.name, "log_sha256": sha(log)})
            assert result.returncode == 0, f"CPU check {index + 1} failed; see {log}"
        report["after"] = verify()
        assert not list((HERE / "empty-cache").rglob("*"))
        report["status"] = "passed_preparation_only_pending_source_review_exact_lease_and_unmocked_preflight"
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = repr(error)
        raise
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        (HERE / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({key: value for key, value in report.items() if key != "commands"}))

if __name__ == "__main__":
    main()
