"""Retained CPU test runner with explicit module overrides and source receipts."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("tests", nargs="+")
    args = parser.parse_args()
    root = Path.cwd()
    directory = Path(__file__).resolve().parent / args.label
    directory.mkdir(exist_ok=False)
    selected = [f"python/dodge_rl/{name}.py" for name in ("supervision", "checkpoints", "train_teacher")]
    actual = {name: str(args.source_root.resolve() / name) for name in selected}
    for name in ("python/dodge_rl/identity.py", "python/dodge_rl/dev_eval.py", "python/dodge_rl/ppo.py",
                 "python/dodge_rl/models/teacher.py", "python/dodge_rl/_native.cpython-312-darwin.so"):
        actual[name] = str(root / name)
    for name in ("python/tests/test_teacher_runner.py", "python/tests/test_checkpoints.py",
                 "python/tests/test_runtime_repair.py", "python/tests/test_runtime_repair_signals.py"):
        actual[name] = str(root / name)
    sources = {}
    for name, path in actual.items():
        sources[name] = {"executed_path": path, "sha256": digest(Path(path))}
        if name.endswith(".py"):
            target = directory / "source" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    (directory / "executed-source.json").write_text(json.dumps(sources, indent=2, sort_keys=True) + "\n")
    bootstrap = """
import hashlib, importlib.util, pathlib, sys
import dodge_rl
source_root=pathlib.Path(sys.argv[1])
for name in ('supervision','checkpoints','train_teacher'):
    path=source_root/'python/dodge_rl'/(name+'.py')
    spec=importlib.util.spec_from_file_location('dodge_rl.'+name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    setattr(dodge_rl,name,module)
    spec.loader.exec_module(module)
    print('EXECUTED_SOURCE',name,str(path),hashlib.sha256(path.read_bytes()).hexdigest(),flush=True)
import pytest
raise SystemExit(pytest.main(sys.argv[2:]))
"""
    command = [sys.executable, "-B", "-c", bootstrap, str(args.source_root.resolve()), "-q",
               "-p", "no:cacheprovider", "--basetemp", str(directory / "fixtures"), "--tb=short", *args.tests]
    environment = dict(os.environ, PYTHONPATH="python", PYTHONDONTWRITEBYTECODE="1")
    started_utc = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    status = None
    with (directory / "stdout-stderr.log").open("xb") as stream:
        try:
            completed = subprocess.run(command, env=environment, stdout=stream, stderr=subprocess.STDOUT, timeout=120)
            status = completed.returncode
        except subprocess.TimeoutExpired as error:
            stream.write(("\nHARNESS_TIMEOUT " + repr(error) + "\n").encode())
            status = 124
    record = {"argv": command, "cwd": str(root), "environment": {"PYTHONPATH": "python",
              "PYTHONDONTWRITEBYTECODE": "1"}, "started_at_utc": started_utc,
              "duration_seconds": time.monotonic() - started, "exit_status": status,
              "source_sha256_after": {name: digest(Path(path)) for name, path in actual.items()},
              "source_unchanged_during_test": all(digest(Path(path)) == sources[name]["sha256"]
                                                  for name, path in actual.items())}
    (directory / "command-result.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"directory": str(directory), "exit_status": status,
                      "duration_seconds": record["duration_seconds"],
                      "source_unchanged_during_test": record["source_unchanged_during_test"]}))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
