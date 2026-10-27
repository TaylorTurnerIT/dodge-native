"""Parent-only unmocked package-loader check; never audits candidates or loads checkpoints."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import wrapper


def bootstrap(*, expected_binding_sha256: str) -> dict:
    if Path(wrapper.__file__).resolve() != (wrapper.OUT / "wrapper.py").resolve():
        raise wrapper.WrapperError("Bootstrap wrapper origin differs from OWN source")
    wrapper.load_binding(expected_binding_sha256)
    reg = wrapper.load_registration()
    wrapper.bind_interpreter(reg)
    wrapper.reject_preloaded_dodge()
    wrapper.bind_bytecode()
    pins_before = wrapper.verify_pins(reg["pins"])
    auditor = wrapper.load_auditor()
    dependency_origins_before = wrapper.bind_dependency_origins(reg)
    runner, loaded_reg, config = auditor.load_frozen(
        expected_binding_sha256=expected_binding_sha256)
    launcher = auditor.load_pinned_module(
        "execute_once_frozen", auditor.LAUNCHER_PATH, auditor.LAUNCHER_SHA)
    if launcher.r is not runner:
        raise wrapper.WrapperError("Frozen launcher did not bind the actual loaded runner")
    dependency_origins_after = wrapper.bind_dependency_origins(loaded_reg)
    if dependency_origins_before != dependency_origins_after:
        raise wrapper.WrapperError("Dependency origins changed during bootstrap")
    if pins_before != len(reg["pins"]) or wrapper.verify_pins(reg["pins"]) != pins_before:
        raise wrapper.WrapperError("Registration pins changed during bootstrap")
    if any(wrapper.PYCACHE_PREFIX.iterdir()):
        raise wrapper.WrapperError("Bytecode prefix gained files during bootstrap")
    return {
        "status": "bootstrap_ready_only",
        "registration_sha256": auditor.REG_SHA,
        "binding_sha256": wrapper.BINDING_SHA,
        "runner_sha256": auditor.RUNNER_SHA,
        "launcher_sha256": auditor.LAUNCHER_SHA,
        "registration_schema_sha256": auditor.REGISTRATION_SCHEMA_SHA,
        "parent_adapter_sha256": auditor.PARENT_ADAPTER_SHA,
        "schedule_module_origins": {
            "schedule_contract": str(Path(auditor.schedule_contract.__file__).resolve()),
            "lr_schedule": str(Path(auditor.lr_schedule.__file__).resolve()),
        },
        "dependency_origins": dependency_origins_after,
        "pins_checked": pins_before,
        "checkpoint_deserialization": False,
        "candidate_audit": False,
        "training_launch": False,
        "authority": dict(wrapper.AUTHORITY),
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding-sha256", required=True,
                        help="exact audit-binding.json digest supplied by the parent")
    args = parser.parse_args(argv)
    print(json.dumps(bootstrap(expected_binding_sha256=args.binding_sha256),
                     sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
