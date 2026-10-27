"""No-MPS, no-game calibration gate run by launcher before probe subprocess."""
from __future__ import annotations
import sys
sys.dont_write_bytecode = True
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
PREPARE = ROOT / "learning/runs/v2/latest-best-paired-eval-prepare-luna-20261026-r6"

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def run(output_dir: Path) -> dict:
    started = time.monotonic()
    sys.path.insert(0, str(PREPARE))
    spec = importlib.util.spec_from_file_location("worker", PREPARE / "worker.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load exact frozen R6 worker")
    worker = importlib.util.module_from_spec(spec)
    sys.modules["worker"] = worker
    spec.loader.exec_module(worker)
    manifest = worker.verify_inputs()
    anchors = {}
    for label in worker.CHECKPOINTS:
        receipt, audit = worker._receipt_anchor(label, ROOT)
        anchors[label] = {"receipt_sha256": worker.EXPECTED_INPUTS[f"{label}_receipt"][1],
                          "audit_sha256": worker.EXPECTED_INPUTS[f"{label}_audit"][1],
                          "audit_status": audit["status"],
                          "raw_exits": audit["raw_exits"],
                          "owned_processes_and_groups_absent": audit["owned_processes_and_groups_absent"],
                          "pins_checked_before_and_after": audit["pins_checked_before_and_after"],
                          "observer_wrapper_error_disposition": audit["observer_wrapper_error_disposition"]}
    loads = {}
    for label in worker.CHECKPOINTS:
        model, receipt = worker.load_inference_model(label, device="cpu", manifest=manifest)
        loads[label] = {"checkpoint_sha256": receipt["checkpoint_sha256"],
                        "receipt_sha256": receipt["receipt_sha256"],
                        "audit_sha256": receipt["audit_sha256"],
                        "training": model.training,
                        "requires_grad_any": any(parameter.requires_grad for parameter in model.parameters()),
                        "parameter_count": sum(parameter.numel() for parameter in model.parameters())}
        del model
    origins = worker.verify_module_origins()
    result = {"schema": "current_pair_resource_calibration_cpu_preflight_v2",
              "status": "passed", "verify_inputs": True,
              "strict_cpu_loads": loads, "receipt_anchors": anchors,
              "module_origins": origins, "mps_operations": 0,
              "game_episodes": 0, "training": False, "checkpoint_writes": 0,
              "elapsed_seconds": time.monotonic() - started}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "cpu-preflight.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = run(args.output)
    print(json.dumps({"status": result["status"], "output": str(args.output / "cpu-preflight.json")},
                     sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
