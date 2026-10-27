"""Single registration identity guard shared by launcher and runner."""
from pathlib import Path

SCHEMA = "d2_retained300_continuation_registration_v1"
RUN_ID = "D2-retained300-continuation-20261026-r2"

def validate_identity(reg):
    if not isinstance(reg, dict) or reg.get("schema") != SCHEMA:
        raise ValueError("Wrong registration schema")
    if reg.get("run_id") != RUN_ID:
        raise ValueError("Wrong registration run identity")
    root = Path(reg.get("root", "")).resolve()
    output = Path(reg.get("output", "")).resolve()
    if output != root / "learning/runs/v2" / RUN_ID:
        raise ValueError("Unsafe registration output identity")
    return reg
