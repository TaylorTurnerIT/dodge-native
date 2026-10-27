"""Verify the exact R5 proposal and its pinned inputs. Read-only."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def main() -> int:
    freeze_path = HERE / "freeze-manifest.json"
    freeze = json.loads(freeze_path.read_text())
    errors = []
    for relative, expected in freeze["files"].items():
        path = HERE / relative
        if not path.is_file() or sha(path) != expected:
            errors.append(f"frozen file mismatch: {relative}")
    pins_path = HERE / "source-pins.json"
    pins = json.loads(pins_path.read_text())
    for name, expected in pins["files"].items():
        path = Path(name)
        if not path.is_file() or sha(path) != expected:
            errors.append(f"source pin mismatch: {name}")
    plan = json.loads((HERE / "calibration-plan.json").read_text())
    pins_sha = sha(pins_path)
    if plan["source_pins_sha256"] != pins_sha:
        errors.append("plan source pinset anchor mismatch")
    if freeze["plan_sha256"] != sha(HERE / "calibration-plan.json"):
        errors.append("freeze plan hash mismatch")
    if freeze["source_pins_sha256"] != pins_sha:
        errors.append("freeze source pinset hash mismatch")
    lexical = Path(plan["interpreter"]["lexical_path"])
    target = Path(plan["interpreter"]["resolved_target"])
    if not lexical.is_file() or lexical.resolve() != target.resolve():
        errors.append("lexical interpreter target mismatch")
    elif sha(target) != plan["interpreter"]["sha256"]:
        errors.append("resolved interpreter hash mismatch")
    result = {"status": "failed" if errors else "passed",
              "frozen_file_count": len(freeze["files"]),
              "source_pin_count": len(pins["files"]),
              "plan_sha256": sha(HERE / "calibration-plan.json"),
              "source_pins_sha256": pins_sha,
              "errors": errors}
    print(json.dumps(result, sort_keys=True))
    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
