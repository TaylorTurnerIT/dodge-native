"""Exercise actual launcher entry before any registered-output mutation."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile

import execute_once
import registration_schema

ROOT = Path(__file__).resolve().parents[4]
PREP = Path(__file__).resolve().parent
REG_PATH = PREP / "registration.json"
REG = json.loads(REG_PATH.read_text())
REG_SHA = hashlib.sha256(REG_PATH.read_bytes()).hexdigest()

class ReachedOutputMkdir(Exception):
    pass


def invoke(reg, expected):
    original_read = execute_once.r.read
    original_mkdir = Path.mkdir
    with tempfile.TemporaryDirectory() as tmp:
        fixture = Path(tmp) / "registration.json"
        fixture.write_text(json.dumps(reg))
        def read(path):
            if Path(path) == fixture:
                return json.loads(fixture.read_text())
            return original_read(path)
        def mkdir(path, *args, **kwargs):
            if Path(path).resolve() == Path(reg["output"]).resolve():
                raise ReachedOutputMkdir
            raise AssertionError(f"unexpected mkdir: {path}")
        execute_once.r.read = read
        Path.mkdir = mkdir
        try:
            try:
                execute_once.execute(fixture, "0" * 64)
            except ReachedOutputMkdir:
                assert expected == "reached"
            except (ValueError, KeyError):
                assert expected == "rejected"
            else:
                raise AssertionError("entry returned without boundary result")
        finally:
            Path.mkdir = original_mkdir
            execute_once.r.read = original_read

invoke(copy.deepcopy(REG), "reached")
for mutate in (
    lambda r: r.update(schema="d2_retained276_continuation_registration_v1"),
    lambda r: r.update(output=str(PREP / "wrong-output")),
    lambda r: r.update(run_id="D2-retained276-lr3em5-20261026-r1"),
):
    bad = copy.deepcopy(REG)
    mutate(bad)
    invoke(bad, "rejected")
print("actual execute entry: valid registration reached pre-mutation mkdir; wrong schema/output/run identity rejected before mkdir")
