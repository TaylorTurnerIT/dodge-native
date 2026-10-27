#!/usr/bin/env python3
"""Build a same-LR registration from assembled sources and immutable parent evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
OWN = Path(__file__).resolve().parent
CONTRACT = ROOT / "learning/runs/v2/D2-retained300-continuation-parent-integration-20261026-r5/integration-contract.json"
EVIDENCE_MAP = ROOT / "learning/runs/v2/D2-retained300-continuation-parent-integration-20261026-r5/evidence-map-reconciliation.json"
BASE_DEFAULT = ROOT / "learning/runs/v2/D2-retained276-lr3em5-prepare-luna-20261026-r2/registration.json"
REQUIRED_SOURCES = ("runner.py", "execute_once.py", "registration_schema.py", "parent_adapter.py")


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON input {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def require_file(path: Path, expected: str | None = None) -> str:
    if not path.is_file():
        raise ValueError(f"required input missing: {path}")
    actual = sha(path)
    if expected is not None and actual != expected:
        raise ValueError(f"input hash differs: {path}")
    return actual


def build_registration(
    contract_path: Path,
    base_registration_path: Path,
    final_source_dir: Path,
    output_path: Path,
    *,
    evidence_map_path: Path,
    selected_receipt_path: Path,
    completed_cost_receipt_path: Path,
    audit_path: Path,
    selection_path: Path,
    full_audit_path: Path,
    producing_registration_path: Path,
) -> dict[str, Any]:
    """Validate all inputs, build registration, then publish via exclusive create."""
    contract_path = contract_path.resolve()
    base_registration_path = base_registration_path.resolve()
    final = final_source_dir.resolve()
    out = output_path.resolve()
    evidence_map_path = evidence_map_path.resolve()
    evidence = read_json(evidence_map_path)
    contract = read_json(contract_path)
    reg = read_json(base_registration_path)
    selected_path = selected_receipt_path.resolve()
    selected = read_json(selected_path)

    # Validate every available frozen evidence-map pin before constructing output.
    evidence_pins: dict[str, str] = {}
    for relative, expected in evidence.get("verified_input_sha256", {}).items():
        path = ROOT / relative
        require_file(path, expected)
        evidence_pins[str(path)] = expected

    if selected_path != (ROOT / "learning/runs/v2/D2-retained276-lr3em5-parent-terminal-audit-20261026-r2/retained-best-candidate-receipt.json").resolve():
        raise ValueError("selected receipt path differs from frozen evidence path")
    require_file(selected_path, contract["selected_receipt_sha256"])
    require_file(base_registration_path, selected["registration_sha256"])
    if selected.get("checkpoint_sha256") != contract["parent_checkpoint_sha256"]:
        raise ValueError("selected checkpoint hash differs from contract")
    if selected.get("candidate_phase_update") != 300 or selected.get("candidate_local_update") != 24:
        raise ValueError("selected receipt counters differ from required parent state")
    if selected.get("candidate_cumulative_counters", {}).get("updates") != 348:
        raise ValueError("selected receipt cumulative update count differs")

    paths = {
        "checkpoint": Path(selected["checkpoint_path"]),
        "sidecar": Path(selected["checkpoint_path"] + ".json"),
        "evaluation": Path(selected["evaluation_path"]),
        "evaluation_jsonl": Path(selected["evaluation_jsonl_path"]),
        "selected_receipt": selected_path,
        "completed_cost_receipt": completed_cost_receipt_path.resolve(),
        "audit": audit_path.resolve(),
        "selection": selection_path.resolve(),
        "full_audit": full_audit_path.resolve(),
        "producing_registration": producing_registration_path.resolve(),
    }
    expected = {
        "checkpoint": selected["checkpoint_sha256"],
        "sidecar": selected["checkpoint_sidecar_sha256"],
        "evaluation": selected["evaluation_sha256"],
        "evaluation_jsonl": selected["evaluation_jsonl_sha256"],
        "selected_receipt": contract["selected_receipt_sha256"],
        "completed_cost_receipt": contract["completed_cost_receipt_sha256"],
        "audit": selected["audit_sha256"],
        "selection": evidence["verified_input_sha256"]["learning/runs/v2/D2-retained276-lr3em5-parent-terminal-audit-20261026-r2/retained-best-decision.json"],
        "full_audit": evidence["verified_input_sha256"]["learning/runs/v2/D2-retained276-lr3em5-auditor-luna-20261026-r2/full-audit.json"],
        "producing_registration": selected["registration_sha256"],
    }
    for key, path in paths.items():
        require_file(path, expected[key])
    if paths["completed_cost_receipt"] != Path(selected["completed_iteration_receipt_path"]).resolve():
        raise ValueError("completed cost receipt path differs from selected receipt")
    if paths["audit"] != Path(selected["audit_path"]).resolve():
        raise ValueError("parent audit path differs from selected receipt")
    if paths["selection"] != (ROOT / "learning/runs/v2/D2-retained276-lr3em5-parent-terminal-audit-20261026-r2/retained-best-decision.json").resolve():
        raise ValueError("parent selection path differs from frozen evidence path")
    if paths["full_audit"] != (ROOT / "learning/runs/v2/D2-retained276-lr3em5-auditor-luna-20261026-r2/full-audit.json").resolve():
        raise ValueError("full audit path differs from frozen evidence path")
    if paths["producing_registration"] != Path(selected["registration_path"]).resolve():
        raise ValueError("producing registration path differs from selected receipt")

    source_paths = {name: final / name for name in REQUIRED_SOURCES}
    for path in source_paths.values():
        require_file(path)
    config = Path(reg["config_path"])
    require_file(config, contract["config_sha256"])
    if reg.get("limits", {}).get("retries") != 0:
        raise ValueError("base registration retries must be zero")
    if out.exists():
        raise FileExistsError(f"refusing existing output: {out}")
    if OWN not in out.parents and final not in out.parents:
        raise ValueError("output must be in own directory or final source directory")
    if out == Path(contract["actual_output"]).resolve() or out.is_relative_to(Path(contract["actual_output"]).resolve()):
        raise ValueError("output cannot be inside actual run directory")

    # Preserve historical and runtime pins; replace only predecessor component pins.
    pins = dict(reg.get("pins", {}))
    old_component = ROOT / "learning/runs/v2/D2-retained276-lr3em5-prepare-luna-20261026-r2"
    for name in (*REQUIRED_SOURCES, "lr_transition.py"):
        pins.pop(str(old_component / name), None)
    pins.update(evidence_pins)
    pins.update({str(path): sha(path) for path in source_paths.values()})
    reg["pins"] = pins

    reg.update(
        schema=contract["schema"], transition_schema=contract["transition_schema"],
        run_id=contract["run_id"], run_seed=contract["run_seed"],
        phase_start=contract["phase_start"], phase_end=contract["phase_end"],
        expected_total_updates=contract["expected_total_updates"], new_updates=contract["new_updates"],
        parent_total_updates=contract["parent_total_updates"], output=contract["actual_output"],
        config_sha256=contract["config_sha256"], training_eligible=False, promoted=False,
        runner_path=str(source_paths["runner.py"]), runner_sha256=sha(source_paths["runner.py"]),
        launcher_path=str(source_paths["execute_once.py"]), launcher_sha256=sha(source_paths["execute_once.py"]),
        registration_schema_module_path=str(source_paths["registration_schema.py"]),
        registration_schema_module_sha256=sha(source_paths["registration_schema.py"]),
        parent_adapter_path=str(source_paths["parent_adapter.py"]),
        parent_adapter_sha256=sha(source_paths["parent_adapter.py"]),
    )
    # Parent authority points to selected complete-update state and its producing run.
    parent = reg["parent"]
    parent.update(
        path=selected["checkpoint_path"], sha256=selected["checkpoint_sha256"],
        sidecar_sha256=selected["checkpoint_sidecar_sha256"], phase=selected["phase"],
        phase_update=selected["candidate_phase_update"], local_update=selected["candidate_local_update"],
        terminal_receipt_path=str(selected_path), terminal_receipt_sha256=contract["selected_receipt_sha256"],
        source_evaluation_path=selected["evaluation_path"], source_evaluation_sha256=selected["evaluation_sha256"],
        source_evaluation_jsonl_path=selected["evaluation_jsonl_path"],
        source_evaluation_jsonl_sha256=selected["evaluation_jsonl_sha256"],
        audit_path=selected["audit_path"], audit_sha256=selected["audit_sha256"],
        full_audit_path=str(paths["full_audit"]), full_audit_sha256=expected["full_audit"],
        selection_path=str(paths["selection"]), selection_sha256=expected["selection"],
        metadata_path=selected["checkpoint_path"] + ".json",
        metadata_sha256=selected["checkpoint_sidecar_sha256"],
        registration_path=selected["registration_path"], registration_sha256=selected["registration_sha256"],
        phase_local_update=selected["candidate_local_update"],
        total_update=selected["candidate_cumulative_counters"]["updates"],
        completed_iteration_receipt_path=selected["completed_iteration_receipt_path"],
        completed_iteration_receipt_sha256=contract["completed_cost_receipt_sha256"],
        wall_accounting=selected["wall_accounting"],
    )
    reg["expected_lease"] = {
        "authorization": "user_continue_D2_training_v3", "kind": "D2_gradient_alignment",
        "parent_checkpoint_sha256": contract["parent_checkpoint_sha256"], "run_id": contract["run_id"],
    }
    reg["parent_registration_sha256"] = selected["registration_sha256"]
    reg["parent_config_sha256"] = contract["config_sha256"]
    reg["parent_config_path"] = str(config)
    reg["resource_cost_anchor"] = {
        "authority": "resource_cost_only; no model or continuation authority",
        "path": selected["completed_iteration_receipt_path"],
        "sha256": contract["completed_cost_receipt_sha256"],
    }
    reg["limits"].update(
        work_seconds=contract["work_seconds"], total_seconds=contract["outer_seconds"],
        retries=0, max_updates=contract["new_updates"], eval_updates=contract["evaluation_updates"],
    )
    reg["evaluation_updates"] = contract["evaluation_updates"]
    prior_outputs = reg.get("expected_outputs", [])
    excluded_updates = (276, 288, 300, 312, 324, 336)
    outputs = [name for name in prior_outputs if name not in ("lr-transition.json",) and not any(f"{u:06d}" in name for u in excluded_updates)]
    outputs.extend(["entry-restoration.json"])
    for update in contract["evaluation_updates"]:
        outputs.extend((f"checkpoint-{update:06d}-candidate.pt", f"checkpoint-{update:06d}-candidate.pt.json", f"development-{update:06d}.json", f"development-{update:06d}.jsonl"))
    reg["expected_outputs"] = list(dict.fromkeys(outputs))
    reg["forbidden_outputs"] = sorted(set(reg.get("forbidden_outputs", [])) | {"lr-transition.json"})
    reg["resource_estimate"].update(
        cleanup_reserve_seconds=contract["cleanup_seconds"], hard_work_cap_seconds=contract["work_seconds"],
        outer_cap_seconds=contract["outer_seconds"], preregistered_work_seconds=contract["planned_seconds"],
        observed_control_outer_seconds=1502.5562572500203, scaled_seconds=1727.9396958375232,
        observed_control_optimizer_steps=7680, extra_planning_margin_seconds=22.06030416247677,
        relaxation_permitted=False,
    )
    reg["cancel_path"] = str(Path(contract["actual_output"]).with_suffix(".cancel"))
    reg["import_policy"]["pycache_prefix"] = str(final / "empty-pycache")
    reg.pop("arm_transition", None)
    reg.pop("lr_transition_helper_path", None)
    reg.pop("lr_transition_helper_sha256", None)

    # All checks precede directory creation and exclusive file creation.
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as stream:
        json.dump(reg, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return {"output": str(out), "sha256": sha(out), "source_dir": str(final), "source_pins_added": list(REQUIRED_SOURCES)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=CONTRACT)
    parser.add_argument("--evidence-map", type=Path, default=EVIDENCE_MAP)
    parser.add_argument("--final-source-dir", type=Path)
    parser.add_argument("--base-registration", type=Path, default=BASE_DEFAULT)
    parser.add_argument("--output", type=Path, default=OWN / "registration-proposal.json")
    args = parser.parse_args()
    contract = read_json(args.contract)
    root = args.contract.resolve().parents[4]
    audit_dir = root / "learning/runs/v2/D2-retained276-lr3em5-parent-terminal-audit-20261026-r2"
    auditor_dir = root / "learning/runs/v2/D2-retained276-lr3em5-auditor-luna-20261026-r2"
    receipt = audit_dir / "retained-best-candidate-receipt.json"
    result = build_registration(
        args.contract, args.base_registration,
        args.final_source_dir or Path(contract["final_source_dir"]), args.output,
        evidence_map_path=args.evidence_map, selected_receipt_path=receipt,
        completed_cost_receipt_path=audit_dir / "completed-iteration-receipt.json",
        audit_path=audit_dir / "audit.json", selection_path=audit_dir / "retained-best-decision.json",
        full_audit_path=auditor_dir / "full-audit.json",
        producing_registration_path=ROOT / "learning/runs/v2/D2-retained276-lr3em5-prepare-luna-20261026-r2/registration.json",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
