"""Retain one bounded PPO component check and its exact selected source bytes."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
label, *command = sys.argv[1:]
directory = HERE / label
directory.mkdir(exist_ok=False)
sources = {}
for name in ("python/dodge_rl/ppo.py", "python/tests/test_ppo.py"):
    source = ROOT / name
    copied = directory / source.name
    copied.write_bytes(source.read_bytes())
    sources[name] = hashlib.sha256(source.read_bytes()).hexdigest()
record = {"started_at_utc": datetime.now(timezone.utc).isoformat(),
          "argv": command, "cwd": str(ROOT), "source_sha256": sources,
          "no_real_game_rollouts": True, "synthetic_CPU_only": True}
started = time.monotonic()
with (directory / "stdout-stderr.log").open("xb") as log:
    try:
        process = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                 timeout=120, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
                                                      OMP_NUM_THREADS="4", MKL_NUM_THREADS="4"))
        record["exit_code"] = process.returncode
    except subprocess.TimeoutExpired as error:
        record.update(exit_code=124, error=repr(error))
peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
record.update(elapsed_seconds=time.monotonic() - started,
              finished_at_utc=datetime.now(timezone.utc).isoformat(),
              observed_child_peak_RSS_bytes=int(peak if sys.platform == "darwin" else peak * 1024),
              log_sha256=hashlib.sha256((directory / "stdout-stderr.log").read_bytes()).hexdigest())
with (directory / "receipt.json").open("x") as output:
    json.dump(record, output, indent=2, sort_keys=True)
    output.write("\n")
print(json.dumps(record, sort_keys=True))
print((directory / "stdout-stderr.log").read_text()[-14000:])
sys.exit(record["exit_code"])
