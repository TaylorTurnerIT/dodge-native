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
REGISTRATION = PREP / "registration-final-r2.json"
OBSERVER = HERE.parent / "D2-retained324-linear-execution-observer-parent-20261026-r1" / "observe.py"
OBSERVER_SHA256 = "f271b2641b995fc34a90cebe420657953cb16ce9038886edc2fd74c184ccacad"
OBSERVER_INSTANTIATION = HERE.parent / "D2-retained324-linear-execution-observer-parent-20261026-r1" / "instantiation.json"
OBSERVER_INSTANTIATION_SHA256 = "56d547b6ccd96df759740d1573fc1de44319094fe0d3ff8296ae75aa3dbbf166"
REGISTRATION_SHA256 = "0a6bf98221689ffcf62a28289dae7bb98eb89bc8d3c02b93127f4a04df75cb4e"
FROZEN_MANIFEST = HERE / "frozen-manifest.json"
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


def _manifest_matches_reviewed_inputs(value: dict, registration: Path, registration_sha256: str,
                                      frozen_manifest: Path, frozen_manifest_sha256: str,
                                      auditor_sources: dict[str, str]) -> bool:
    return (value.get("schema") == "d2_retained324_linear_auditor_review_assembly_v1"
            and value.get("run_id") == RUN_ID
            and value.get("registration") == {"path": str(registration), "sha256": registration_sha256}
            and value.get("frozen_manifest") == {"path": str(frozen_manifest), "sha256": frozen_manifest_sha256}
            and value.get("auditor_sources") == auditor_sources)


def build_binding(*, registration: Path, registration_sha256: str,
                  reviewed_manifest: Path, reviewed_manifest_sha256: str,
                  observer_source: Path, observer_sha256: str,
                  frozen_manifest: Path, frozen_manifest_sha256: str) -> dict:
    if not registration.is_absolute():
        raise ValueError("Registration path must be absolute")
    registration = registration.resolve()
    if registration != REGISTRATION.resolve():
        raise ValueError("Registration path is not registration-final-r2.json")
    if registration_sha256 != REGISTRATION_SHA256:
        raise ValueError("Registration digest is not the frozen actual package digest")
    reg_bytes = checked_bytes(registration, registration_sha256, "Registration")
    reviewed_bytes = checked_bytes(reviewed_manifest, reviewed_manifest_sha256, "Reviewed manifest")
    if not observer_source.is_absolute():
        raise ValueError("Observer source path must be absolute")
    observer_source = observer_source.resolve()
    if observer_source != OBSERVER.resolve() or observer_sha256 != OBSERVER_SHA256:
        raise ValueError("Observer source is not the exact registered parent observer")
    checked_bytes(observer_source, observer_sha256, "Parent observer source")
    if not frozen_manifest.is_absolute():
        raise ValueError("Frozen manifest path must be absolute")
    frozen_manifest = frozen_manifest.resolve()
    if frozen_manifest != FROZEN_MANIFEST.resolve():
        raise ValueError("Frozen manifest path is not this successor's immutable manifest")
    frozen_bytes = checked_bytes(frozen_manifest, frozen_manifest_sha256, "Frozen manifest")
    reg = json.loads(reg_bytes)
    if reg.get("run_id") != RUN_ID:
        raise ValueError("Registration run_id differs from requested successor")
    if reg.get("schema") != "d2_retained324_linear_lr_registration_v1":
        raise ValueError("Registration schema differs from actual package")
    source_manifest_path = PREP / "source-manifest.json"
    source_manifest_raw = source_manifest_path.read_bytes()
    source_manifest = json.loads(source_manifest_raw)
    if (source_manifest.get("schema") != "d2_retained324_linear_integrated_source_manifest_v1"
            or source_manifest.get("run_id") != RUN_ID
            or source_manifest.get("controls", {}).get("final_registration") != REGISTRATION.name
            or source_manifest.get("artifacts", {}).get(REGISTRATION.name) != REGISTRATION_SHA256):
        raise ValueError("Actual source manifest does not bind registration-final-r2.json")
    observer_instantiation_raw = checked_bytes(
        OBSERVER_INSTANTIATION, OBSERVER_INSTANTIATION_SHA256, "Parent observer instantiation")
    observer_instantiation = json.loads(observer_instantiation_raw)
    if (observer_instantiation.get("schema") != "retained324_linear_lr_observer_instantiation_v1"
            or observer_instantiation.get("registration_path") != str(REGISTRATION.resolve())
            or observer_instantiation.get("registration_sha256") != REGISTRATION_SHA256
            or observer_instantiation.get("observer_sha256") != OBSERVER_SHA256
            or observer_instantiation.get("actual_launches") != 0
            or observer_instantiation.get("one_shot_marker_absent") is not True):
        raise ValueError("Parent observer instantiation does not bind exact registration and no-launch state")
    frozen = json.loads(frozen_bytes)
    if frozen.get("inputs", {}).get("source_manifest_sha256") != hashlib.sha256(source_manifest_raw).hexdigest():
        raise ValueError("Actual source-manifest digest differs from frozen input pin")
    frozen_sources = frozen.get("auditor_sources")
    if frozen.get("schema") != "d2_retained324_linear_auditor_frozen_manifest_v2" or not isinstance(frozen_sources, dict):
        raise ValueError("Frozen manifest schema or source pins differ")
    source_pins = {str((HERE / name).resolve()): frozen_sources.get(name) for name in SOURCE_NAMES}
    if any(not isinstance(digest, str) or len(digest) != 64 or sha256(HERE / name) != digest
           for name, digest in zip(SOURCE_NAMES, source_pins.values())):
        raise ValueError("Current auditor sources do not match explicit frozen-manifest pins")
    review = json.loads(reviewed_bytes)
    if not _manifest_matches_reviewed_inputs(review, registration, registration_sha256,
                                             frozen_manifest, frozen_manifest_sha256, source_pins):
        raise ValueError("Reviewed manifest does not bind exact registration, frozen manifest, and auditor sources")
    return {
        "schema": "d2_retained324_linear_auditor_binding_v1",
        "run_id": RUN_ID,
        "registration": {"path": str(registration), "sha256": registration_sha256},
        "reviewed_manifest": {"path": str(reviewed_manifest.resolve()), "sha256": reviewed_manifest_sha256},
        "observer_source": {"path": str(observer_source), "sha256": observer_sha256},
        "observer_instantiation": {"path": str(OBSERVER_INSTANTIATION.resolve()),
                                   "sha256": OBSERVER_INSTANTIATION_SHA256},
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
    parser.add_argument("--frozen-manifest", type=Path, required=True)
    parser.add_argument("--frozen-manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.resolve() != (HERE / "audit-binding.json").resolve():
        parser.error("Output must be OWN audit-binding.json")
    binding = build_binding(registration=args.registration,
                            registration_sha256=args.registration_sha256,
                            reviewed_manifest=args.reviewed_manifest,
                            reviewed_manifest_sha256=args.reviewed_manifest_sha256,
                            observer_source=args.observer_source,
                            observer_sha256=args.observer_sha256,
                            frozen_manifest=args.frozen_manifest,
                            frozen_manifest_sha256=args.frozen_manifest_sha256)
    with args.output.open("x") as stream:
        json.dump(binding, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
