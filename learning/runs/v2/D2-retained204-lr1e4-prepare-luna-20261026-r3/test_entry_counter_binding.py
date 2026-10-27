from __future__ import annotations
import importlib.util
from pathlib import Path
import sys

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))
spec = importlib.util.spec_from_file_location("execute_once_under_test", OUT / "execute_once.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

metrics = [
    {"phase_update": update, "counters": {"updates": update - 204, "optimizer_steps": 3 * (update - 204),
      "environment_decisions": 16384 * (update - 204), "raw_frames": 1000 * (update - 204)}}
    for update in range(205, 277)
]
expected = [module.r.PHASE_START, *module.r.EVALUATION_UPDATES[1:]]
assert expected == [204, 216, 228, 240, 252, 264, 276]
for update in expected:
    counters = module.expected_checkpoint_counters(update, metrics)
    assert counters == ({"updates": 0, "optimizer_steps": 0, "environment_decisions": 0, "raw_frames": 0}
                        if update == 204 else metrics[update - 205]["counters"])
try:
    module.expected_checkpoint_counters(204, [])
except Exception as exc:
    raise AssertionError("entry candidate must not require a journal row") from exc
for bad in [203, 277]:
    try:
        module.expected_checkpoint_counters(bad, metrics)
    except (StopIteration, KeyError):
        pass
    else:
        raise AssertionError(f"unexpected update {bad} accepted")
print("production checkpoint-counter helper: entry zero counters and six journal-bound candidates passed; out-of-range candidates rejected")
