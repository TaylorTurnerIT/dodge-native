"""Assemble deterministic registration only after immutable sources are frozen."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
import sys
sys.dont_write_bytecode = True

import parent_adapter
import registration_schema
import runner as integrated_runner

ROOT = Path("/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79")
OWN = ROOT / "learning/runs/v2/D2-retained324-linear-integrated-luna-20261026-r4"
BASE = ROOT / "learning/runs/v2/D2-retained324-continuation-prepare-luna-20261026-r2"
SCHEDULE = OWN
RUNNER_DIR = OWN
BASE_REGISTRATION_SHA256 = "44ac8185b24de2d98cc1c870191f18be47734b5cc11c7c6ff91b9feacb34cd5a"
BASE_MANIFEST_SHA256 = "9032b3ee00ed30c72364acfc8e865730625d244edfb8662147300970cec52741"
LATEST_COST_PATH = ROOT / "learning/runs/v2/D2-retained324-parent-terminal-audit-20261026-r1/completed-iteration-receipt.json"
SELECTED_RECEIPT_PATH = ROOT / "learning/runs/v2/D2-retained300-parent-terminal-audit-20261026-r1/retained-best-candidate-receipt.json"
PRODUCING_COST_PATH = ROOT / "learning/runs/v2/D2-retained300-parent-terminal-audit-20261026-r1/completed-iteration-receipt.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def require_manifest(path: Path, digest: str, kind: str) -> dict[str, Any]:
    if not path.is_file() or sha256(path) != digest:
        raise ValueError(f"{kind} manifest missing or digest drifted")
    manifest = read_json(path)
    source_key = f"{kind}_path"
    digest_key = f"{kind}_sha256"
    source = Path(manifest.get(source_key, ""))
    source_digest = manifest.get(digest_key)
    if not source.is_absolute() or not source.is_file() or source_digest is None:
        raise ValueError(f"{kind} manifest lacks an absolute source path and digest")
    if sha256(source) != source_digest:
        raise ValueError(f"{kind} source digest differs from immutable manifest")
    return manifest


def _source_pin(pins: dict[str, str], path: Path, digest: str) -> None:
    key = str(path.resolve())
    old = pins.get(key)
    if old is not None and old != digest:
        raise ValueError(f"Historical source pin rewrite refused: {key}")
    pins[key] = digest


def build_registration(runner_manifest_path: Path, runner_manifest_sha256: str,
                       helper_manifest_path: Path, helper_manifest_sha256: str,
                       launcher_manifest_path: Path, launcher_manifest_sha256: str) -> dict[str, Any]:
    """Build in memory; caller may publish only after all immutable input checks pass."""
    own_manifest = read_json(OWN / "source-manifest.json")
    if own_manifest.get("schema") != "d2_retained324_linear_integrated_source_manifest_v1":
        raise ValueError("Integrated source manifest schema differs")
    for name, digest in own_manifest.get("files", {}).items():
        if not (OWN / name).is_file() or sha256(OWN / name) != digest:
            raise ValueError("Integrated owned source digest differs: " + name)
    for name, digest in own_manifest.get("manifests", {}).items():
        if not (OWN / name).is_file() or sha256(OWN / name) != digest:
            raise ValueError("Integrated owned manifest digest differs: " + name)
    runner_manifest = require_manifest(runner_manifest_path, runner_manifest_sha256, "runner")
    helper_manifest = require_manifest(helper_manifest_path, helper_manifest_sha256, "helper")
    launcher_manifest = require_manifest(launcher_manifest_path, launcher_manifest_sha256, "launcher")
    runner_path = Path(runner_manifest["runner_path"]).resolve()
    helper_path = Path(helper_manifest["helper_path"]).resolve()
    if runner_path.parent != RUNNER_DIR.resolve():
        raise ValueError("Final runner must come from the named frozen runner successor")
    if helper_path.name != "lr_schedule.py" or helper_path.parent != RUNNER_DIR.resolve():
        raise ValueError("Linear schedule helper must be imported from frozen runner successor")
    launcher_path = Path(launcher_manifest["launcher_path"]).resolve()
    if launcher_path.parent != OWN.resolve() or launcher_path.name != "execute_once.py":
        raise ValueError("Successor launcher must reside in this own-output directory")
    if launcher_manifest.get("runner_module_plumbing") != "explicit_immutable_path":
        raise ValueError("Successor launcher lacks reviewed explicit runner-module plumbing")
    if Path(launcher_manifest.get("runner_module_path", "")).resolve() != runner_path:
        raise ValueError("Successor launcher runner-module binding differs")
    helper_digest = helper_manifest["helper_sha256"]
    if helper_digest != registration_schema.HELPER_SHA256:
        raise ValueError("Schedule helper digest differs from accepted helper")
    spec_digest = helper_manifest.get("schedule_spec_sha256")
    if not isinstance(spec_digest, str) or len(spec_digest) != 64:
        raise ValueError("Helper manifest lacks exact schedule specification digest")
    if helper_manifest.get("origin_cumulative_update") != 372 or helper_manifest.get("horizon_updates") != 60:
        raise ValueError("Schedule helper manifest origin or horizon differs")

    if Path(parent_adapter.__file__).resolve() != (OWN / "parent_adapter.py").resolve() or Path(registration_schema.__file__).resolve() != (OWN / "registration_schema.py").resolve():
        raise ValueError("Loaded adapter/schema origins differ from owned sources")
    if sha256(BASE / "registration.json") != BASE_REGISTRATION_SHA256 or sha256(BASE / "source-manifest.json") != BASE_MANIFEST_SHA256:
        raise ValueError("Pinned base registration or source manifest drifted")
    base = read_json(BASE / "registration.json")
    prior_manifest = read_json(BASE / "source-manifest.json")
    prior_pins = base.get("pins")
    if not isinstance(prior_pins, dict) or len(prior_pins) != 13846:
        raise ValueError("Frozen historical pin set does not contain exactly 13846 entries")
    if prior_manifest.get("pins") != len(prior_pins):
        raise ValueError("Frozen source manifest pin count differs")
    r1 = read_json(ROOT / "learning/runs/v2/D2-retained300-continuation-freeze-20261026-r5/registration.json").get("pins", {})
    actual_overlap = sum(1 for k, v in r1.items() if k in prior_pins and prior_pins[k] == v)
    if len(r1) != 13827 or actual_overlap != 13827:
        raise ValueError("Historical R1 pin bytes differ from the frozen R2 pin set")
    if prior_manifest.get("historical_R1_pin_coverage") != {
        "R1_pin_count": 13827, "R2_pin_count": 13846,
        "removed_R1_pins": 0, "shared_hash_rewrites": 0,
    }:
        raise ValueError("Historical pin preservation evidence differs")

    selected = read_json(SELECTED_RECEIPT_PATH)
    producing_cost = read_json(PRODUCING_COST_PATH)
    latest_cost = read_json(LATEST_COST_PATH)
    parent_adapter.validate_producing_cost_receipt(
        producing_cost, parent_adapter.PRODUCING_COST_RECEIPT_SHA256)
    parent_adapter.validate_latest_cost_receipt(
        latest_cost, parent_adapter.LATEST_COST_RECEIPT_SHA256)
    if sha256(SELECTED_RECEIPT_PATH) != parent_adapter.SELECTED_RECEIPT_SHA256:
        raise ValueError("Original selected candidate receipt drifted")
    if sha256(PRODUCING_COST_PATH) != parent_adapter.PRODUCING_COST_RECEIPT_SHA256:
        raise ValueError("Original producing cost receipt drifted")
    if sha256(LATEST_COST_PATH) != parent_adapter.LATEST_COST_RECEIPT_SHA256:
        raise ValueError("Latest completed cost receipt drifted")
    if latest_cost["wall_accounting"]["completed_campaign_resource_cost_before_seconds"] != producing_cost["wall_accounting"]["completed_campaign_resource_cost_after_seconds"]:
        raise ValueError("Latest cost chain does not begin at original producing cost")
    if selected.get("checkpoint_sha256") != parent_adapter.CHECKPOINT_SHA256:
        raise ValueError("Selected original checkpoint authority differs")
    metadata_path = Path(selected["checkpoint_path"] + ".json")
    metadata = read_json(metadata_path)
    if metadata != {"checkpoint_sha256": parent_adapter.CHECKPOINT_SHA256,
                    "eligibility_status": "provisional_pending_parent_terminal_receipt",
                    "promoted": False, "training_eligible": False}:
        raise ValueError("Selected checkpoint metadata differs")
    if (selected.get("candidate_phase_update"), selected.get("candidate_local_update"),
        selected.get("candidate_cumulative_counters", {}).get("updates"),
        selected.get("candidate_counters", {}).get("updates")) != (324, 24, 372, 24):
        raise ValueError("Selected parent counter contract differs")
    if selected.get("config_sha256") != parent_adapter.CONFIG_SHA256 or selected.get("checkpoint_path") is None:
        raise ValueError("Selected parent config or checkpoint path differs")
    parent = base.get("parent", {})
    if (Path(parent.get("path", "")).resolve() != Path(selected["checkpoint_path"]).resolve()
        or parent.get("sha256") != parent_adapter.CHECKPOINT_SHA256
        or parent.get("terminal_receipt_sha256") != parent_adapter.SELECTED_RECEIPT_SHA256
        or parent.get("metadata_sha256") != parent_adapter.CHECKPOINT_METADATA_SHA256
        or base.get("config_sha256") != parent_adapter.CONFIG_SHA256
        or base.get("runtime_sha256") != selected.get("runtime_sha256")) :
        raise ValueError("Copied parent path, byte pin, metadata, config, or runtime differs")
    if selected.get("next_episode_indices") != selected.get("candidate_counters", {}).get("next_episode_indices") and "next_episode_indices" in selected.get("candidate_counters", {}):
        raise ValueError("Selected episode-index contract differs")


    registration = json.loads(json.dumps(base))
    if (ROOT / "learning/runs/v2" / registration_schema.RUN_ID).exists():
        raise ValueError("Run output collision; registration assembly refused")
    registration.update({
        "root": str(ROOT),
        "ppo": integrated_runner.PPO,
        "registration_schema_path": str((OWN / "registration_schema.py").resolve()),
        "registration_schema_sha256": sha256(OWN / "registration_schema.py"),
        "lr_schedule_path": str((OWN / "lr_schedule.py").resolve()),
        "lr_schedule_sha256": helper_digest,
        "schema": registration_schema.SCHEMA,
        "run_id": registration_schema.RUN_ID,
        "output": str(registration_schema.OUTPUT),
        "phase_start": 324,
        "phase_end": 384,
        "parent_total_updates": 372,
        "expected_total_updates": 432,
        "new_updates": 60,
        "run_seed": registration_schema.RUN_SEED,
        "evaluation_updates": [324, 336, 348, 360, 372, 384],
        "runner_path": str(runner_path),
        "runner_sha256": runner_manifest["runner_sha256"],
        "launcher_path": str(launcher_path),
        "launcher_sha256": launcher_manifest["launcher_sha256"],
        "parent_adapter_path": str((OWN / "parent_adapter.py").resolve()),
        "parent_adapter_sha256": sha256(OWN / "parent_adapter.py"),
        "registration_schema_module_path": str((OWN / "registration_schema.py").resolve()),
        "registration_schema_module_sha256": sha256(OWN / "registration_schema.py"),
        "checkpoint_contract": {
            "authority": "original selected324 receipt only",
            "phase": "D2", "phase_update": 324, "local_update": 24,
            "checkpoint_sha256": parent_adapter.CHECKPOINT_SHA256,
            "selected_receipt_sha256": parent_adapter.SELECTED_RECEIPT_SHA256,
            "checkpoint_metadata_sha256": parent_adapter.CHECKPOINT_METADATA_SHA256,
            "cumulative_updates": 372,
            "selected_trajectory_baseline_seconds": parent_adapter.SELECTED_TRAJECTORY_BASELINE_SECONDS,
            "entry_optimizer_lr": 3e-5,
            "training_eligible": False, "promoted": False,
        },
        "latest_resource_cost_anchor": {
            "authority": "accounting_only; no checkpoint, learner ancestry, continuation, or promotion authority",
            "path": str(LATEST_COST_PATH),
            "sha256": parent_adapter.LATEST_COST_RECEIPT_SHA256,
        },
        "lr_schedule": {
            "name": "linear_3e-5_to_1e-5_then_hold",
            "origin_cumulative_update": 372,
            "horizon_updates": 60,
            "start_lr": 3e-5,
            "end_lr": 1e-5,
            "formula": "start_lr - (start_lr - end_lr) * (u - 1) / (horizon_updates - 1)",
            "u_definition": "cumulative_update - origin_cumulative_update",
            "application": "after_rollout_before_ppo_update",
            "after_horizon": "hold_end_lr",
            "spec_sha256": spec_digest,
            "helper_path": str(helper_path),
            "helper_sha256": helper_digest,
            "group_lr_log": "per_optimizer_group_per_update",
        },
        "authority_limits": {
            "selected_receipt_sha256": parent_adapter.SELECTED_RECEIPT_SHA256,
            "selected_checkpoint_sha256": parent_adapter.CHECKPOINT_SHA256,
            "producing_cost_receipt_sha256": parent_adapter.PRODUCING_COST_RECEIPT_SHA256,
            "latest_cost_receipt_sha256": parent_adapter.LATEST_COST_RECEIPT_SHA256,
            "latest_receipt_accounting_only": True,
            "new_receipt_competence_passed_key_absent": "competence_passed" not in latest_cost,
            "learner_ancestry_updates_from_discarded_iteration": 0,
            "checkpoint_replacement_authorized": False,
            "promotion_authorized": False,
        },
        "expected_lease": {
            "authorization": "user_continue_D2_training_v3",
            "kind": "D2_gradient_alignment",
            "parent_checkpoint_sha256": parent_adapter.CHECKPOINT_SHA256,
            "run_id": registration_schema.RUN_ID,
        },
        "launcher_module_contract": {
            "runner_module": "runner",
            "runner_module_plumbing": "explicit_immutable_path",
            "required_runner_module_path": str(runner_path),
            "status": "immutable_successor_launcher_manifest_verified",
        },
    })
    registration["parent"]["completed_cost_receipt_path"] = str(PRODUCING_COST_PATH)
    registration["parent"]["completed_cost_receipt_sha256"] = parent_adapter.PRODUCING_COST_RECEIPT_SHA256
    registration["parent"]["completed_iteration_receipt_path"] = str(PRODUCING_COST_PATH)
    registration["parent"]["completed_iteration_receipt_sha256"] = parent_adapter.PRODUCING_COST_RECEIPT_SHA256
    registration["parent"]["latest_resource_cost_anchor"] = {"path":str(LATEST_COST_PATH),"sha256":parent_adapter.LATEST_COST_RECEIPT_SHA256}
    registration["parent"]["completed_iteration_receipt_path"] = str(PRODUCING_COST_PATH)
    registration["parent"]["completed_iteration_receipt_sha256"] = parent_adapter.PRODUCING_COST_RECEIPT_SHA256
    registration["resource_cost_anchor"] = {
        "authority": "accounting_only; no model or continuation authority",
        "path": str(LATEST_COST_PATH),
        "sha256": parent_adapter.LATEST_COST_RECEIPT_SHA256,
    }
    registration["pins"] = dict(prior_pins)
    for path, digest in (
        ((OWN / "parent_adapter.py"), sha256(OWN / "parent_adapter.py")),
        ((OWN / "registration_schema.py"), sha256(OWN / "registration_schema.py")),
        ((OWN / "build_registration.py"), sha256(OWN / "build_registration.py")),
        (runner_path, runner_manifest["runner_sha256"]),
        (helper_path, helper_digest),
        (OWN / "frozen-manifest.json", sha256(OWN / "frozen-manifest.json")),
        (launcher_path, launcher_manifest["launcher_sha256"]),
        (SELECTED_RECEIPT_PATH, parent_adapter.SELECTED_RECEIPT_SHA256),
        (PRODUCING_COST_PATH, parent_adapter.PRODUCING_COST_RECEIPT_SHA256),
        (LATEST_COST_PATH, parent_adapter.LATEST_COST_RECEIPT_SHA256),
        (runner_manifest_path.resolve(), runner_manifest_sha256),
        (helper_manifest_path.resolve(), helper_manifest_sha256),
        (launcher_manifest_path.resolve(), launcher_manifest_sha256),
    ):
        _source_pin(registration["pins"], path, digest)
    registration_schema.validate_identity(registration)
    return registration


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-manifest", type=Path, required=True)
    parser.add_argument("--runner-manifest-sha256", required=True)
    parser.add_argument("--helper-manifest", type=Path, required=True)
    parser.add_argument("--helper-manifest-sha256", required=True)
    parser.add_argument("--launcher-manifest", type=Path, required=True)
    parser.add_argument("--launcher-manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, default=OWN / "registration.json")
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing registration collision")
    reg = build_registration(args.runner_manifest, args.runner_manifest_sha256,
                             args.helper_manifest, args.helper_manifest_sha256,
                             args.launcher_manifest, args.launcher_manifest_sha256)
    registration_schema.validate_identity(reg)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(reg, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
