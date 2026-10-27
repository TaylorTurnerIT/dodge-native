"""Build parent-consumed audit pins after final registration and review freeze."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN_ID = "D2-retained324-linear-lr-20261026-r1"
PREP = HERE.parent / "D2-retained324-linear-integrated-luna-20261026-r4"
RUN = HERE.parent / RUN_ID
SOURCE_NAMES = ("audit_candidates.py", "wrapper.py", "binding_builder.py",
                "schedule_contract.py", "lr_schedule.py")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_bytes(path: Path, expected: str, label: str) -> bytes:
    if not path.is_absolute() or not path.is_file():
        raise ValueError(f"{label} path must be an absolute existing file")
    if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
        raise ValueError(f"{label} SHA-256 must be supplied explicitly")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"{label} bytes do not match explicitly supplied SHA-256")
    return data


def build_binding(*, registration: Path, registration_sha256: str,
                  reviewed_manifest: Path, reviewed_manifest_sha256: str,
                  observer_source: Path, observer_sha256: str) -> dict:
    if registration.resolve() != (PREP / "registration.json").resolve():
        raise ValueError("Registration path is not the final integrated-run registration")
    reg_bytes = checked_bytes(registration, registration_sha256, "Registration")
    reviewed_bytes = checked_bytes(reviewed_manifest, reviewed_manifest_sha256, "Reviewed manifest")
    observer_bytes = checked_bytes(observer_source, observer_sha256, "Parent observer source")
    reg = json.loads(reg_bytes)
    if reg.get("run_id") != RUN_ID:
        raise ValueError("Registration run_id differs from requested successor")
    if not reviewed_bytes or not observer_bytes:
        raise ValueError("Reviewed manifest and observer source must be nonempty")
    source_pins = {str((HERE / name).resolve()): sha256(HERE / name) for name in SOURCE_NAMES}
    return {
        "schema": "d2_retained324_linear_auditor_binding_v1",
        "run_id": RUN_ID,
        "registration": {"path": str(registration), "sha256": registration_sha256},
        "reviewed_manifest": {"path": str(reviewed_manifest), "sha256": reviewed_manifest_sha256},
        "observer_source": {"path": str(observer_source), "sha256": observer_sha256},
        "auditor_sources": source_pins,
        "run_directory": str(RUN),
        "authority": {"selection": False, "best_replacement": False, "continuation": False,
                      "terminal_acceptance": False, "lease_clear": False, "new_receipt": False},
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registration", type=Path, required=True)
    parser.add_argument("--registration-sha256", required=True)
    parser.add_argument("--reviewed-manifest", type=Path, required=True)
    parser.add_argument("--reviewed-manifest-sha256", required=True)
    parser.add_argument("--observer-source", type=Path, required=True)
    parser.add_argument("--observer-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.resolve() != (HERE / "audit-binding.json").resolve():
        parser.error("Output must be OWN audit-binding.json")
    binding = build_binding(registration=args.registration,
                            registration_sha256=args.registration_sha256,
                            reviewed_manifest=args.reviewed_manifest,
                            reviewed_manifest_sha256=args.reviewed_manifest_sha256,
                            observer_source=args.observer_source,
                            observer_sha256=args.observer_sha256)
    with args.output.open("x") as stream:
        json.dump(binding, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
