"""Non-learning actual probe of power_guard.check(). Read-only: prints one JSON line, writes nothing.

Run from the ROOT native session under the same prefix as a dispatch:
/usr/bin/caffeinate -ims /usr/bin/env PYTHONDONTWRITEBYTECODE=1 <interpreter> -B probe_power_guard.py
"""
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import power_guard

try:
    print(json.dumps(dict(status="passed", receipt=power_guard.check(), training_launched=False), sort_keys=True))
except Exception as error:
    print(json.dumps(dict(status="failed", error=repr(error), training_launched=False), sort_keys=True))
    raise SystemExit(1)
