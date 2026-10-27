"""Shared D2 retained300 continuation identity check."""
from pathlib import Path

SCHEMA = "d2_retained300_same_lr_registration_v1"
RUN_ID = "D2-retained300-continuation-20261026-r1"


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
