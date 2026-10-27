from __future__ import annotations
import sys
sys.dont_write_bytecode = True
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> int:
    pins = json.loads((HERE / "source-pins.json").read_text())
    for name, expected in pins["files"].items():
        path = Path(name)
        if not path.is_file() or sha(path) != expected:
            raise RuntimeError(f"Pinned file changed: {name}")
    for name, expected in pins["directories"].items():
        path = Path(name)
        entries = {str(item): sha(item) for item in path.rglob("*")
                   if item.is_file() and "__pycache__" not in item.parts
                   and item.suffix not in {".pyc", ".pyo"}}
        actual = hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"Pinned source directory changed: {name}")
    if list((HERE / "bytecode-cache-empty").rglob("*.pyc")):
        raise RuntimeError("Owned bytecode prefix is not empty")
    state_path = ROOT / "learning/runs/v2-orchestration/state.json"
    state = json.loads(state_path.read_text())
    result = {
        "status": "passed", "pinned_files_checked": len(pins["files"]),
        "pinned_directories_checked": len(pins["directories"]),
        "bytecode_prefix_empty": True,
        "active_long_campaign": state.get("active_long_campaign"),
        "active_inference_diagnostic": state.get("active_inference_diagnostic"),
        "state_sha256_provenance_only": sha(state_path),
        "launch_marker_exists": (HERE / "launch-once.marker").exists(),
        "reservation_exists": (HERE / "parent-reservation.json").exists(),
        "probe_output_exists": (HERE / "probe-output").exists(),
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
