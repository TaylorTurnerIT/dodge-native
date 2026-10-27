from __future__ import annotations
import json, sys
from pathlib import Path
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))
import runner
reg = json.loads((OUT / "registration.json").read_text())
accepted = json.loads(Path(reg["parent"]["source_evaluation_path"]).read_text())["evaluation"]
runner.validate_entry_evaluation(accepted, accepted)
mutated = json.loads(json.dumps(accepted))
mutated["rows"][0]["alive_frames"] += 1
try:
    runner.validate_entry_evaluation(mutated, accepted)
except ValueError as exc:
    assert "Entry evaluation differs" in str(exc)
else:
    raise AssertionError("changed entry row passed production validator")
print("production phase-204 entry evaluation validator: accepted rows pass; changed row rejected")
