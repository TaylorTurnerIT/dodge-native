"""Retain one explicit pure check, its source, command, log and exit status."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

here = Path(__file__).resolve().parent
root = here.parents[3]
label, *command = sys.argv[1:]
checks = here / "checks"
checks.mkdir(exist_ok=True)
log = checks / (label + ".log")
receipt = checks / (label + ".json")
source = root / "learning/scripts/v2_validate_environment.py"
raw = source.read_bytes()
(checks / (label + "-source.py")).write_bytes(raw)
record = {"label": label, "command": command, "cwd": str(root), "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
          "source_sha256": hashlib.sha256(raw).hexdigest(), "pure_only": True, "campaign_executed": False,
          "test_sources_sha256": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (here / "test_supervisor.py", here / "run_pure_tests.py")}}
start = time.monotonic()
with log.open("xb") as stream:
    try:
        result = subprocess.run(command, cwd=root, stdout=stream, stderr=subprocess.STDOUT, timeout=120,
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        record["exit_code"] = result.returncode
    except subprocess.TimeoutExpired as error:
        record.update(exit_code=124, error=repr(error))
record.update(elapsed_seconds=time.monotonic() - start, log=str(log.relative_to(root)), log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
with receipt.open("x") as stream:
    json.dump(record, stream, indent=2, sort_keys=True)
    stream.write("\n")
with (here / "commands.jsonl").open("a") as stream:
    stream.write(json.dumps(record, sort_keys=True) + "\n")
print(json.dumps(record, sort_keys=True))
print(log.read_text()[-14000:])
sys.exit(record["exit_code"])
