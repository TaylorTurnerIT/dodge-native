"""Real SIGTERM in the terminal publication window, with a mocked worker."""
from pathlib import Path
import inspect
import os
import signal
import sys
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "learning/runs/v2/critic-diagnostic-runner-prepare-20261025-r2"))
import runner as r
import execute_once as e
from test_contract import FakeProcess, completed, registration

fixture = HERE / "late-publication-OS-fixture"
fixture.mkdir(exist_ok=False)
reg = registration(fixture)
regpath = fixture / "registration.json"
r.save(regpath, reg)
out = Path(reg["output"])
out.mkdir(parents=True)
r.save(out / "worker-result.json", completed())
fired = False


def clock():
    global fired
    caller = inspect.currentframe().f_back
    if (not fired and caller.f_code.co_name == "execute"
            and caller.f_locals.get("result", {}).get("status") == "passed"):
        fired = True
        os.kill(os.getpid(), signal.SIGTERM)
    return 0.


with patch.object(r, "load_registration", return_value=(reg, {})), \
     patch.object(r, "check_lease"), patch.object(e, "group_exists", return_value=False), \
     patch.object(e, "validate_outputs", return_value={"updates_checked": 48}):
    code = e.execute(regpath, "synthetic_fixture_only", clock=clock,
                     popen=Mock(return_value=FakeProcess()))
failure = r.read(out / "publication-failure.json")
assert fired and code == 1 and failure["status"] == "failed"
assert failure["parent_signal"]["signal"] == signal.SIGTERM
print("Expected nonzero cancellation result preserved after real SIGTERM", flush=True)
raise SystemExit(code)
