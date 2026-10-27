"""One-shot inference worker. Importable tests use fake environments only."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import resource
import sys
import threading
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
PREPARE_DIR = Path(__file__).resolve().parent
_PAIRED_EVAL_NAME = "_latest_best_paired_eval_r6_paired_eval"
_PAIRED_EVAL_SPEC = importlib.util.spec_from_file_location(
    _PAIRED_EVAL_NAME, PREPARE_DIR / "paired_eval.py")
if _PAIRED_EVAL_SPEC is None or _PAIRED_EVAL_SPEC.loader is None:
    raise RuntimeError("Cannot load paired_eval.py from exact R6 preparation directory")
_PAIRED_EVAL = importlib.util.module_from_spec(_PAIRED_EVAL_SPEC)
sys.modules[_PAIRED_EVAL_NAME] = _PAIRED_EVAL
_PAIRED_EVAL_SPEC.loader.exec_module(_PAIRED_EVAL)
if Path(_PAIRED_EVAL.__file__).resolve() != (PREPARE_DIR / "paired_eval.py").resolve():
    raise RuntimeError("R6 paired_eval module origin differs")
CANONICAL_ROW_KEYS = _PAIRED_EVAL.CANONICAL_ROW_KEYS
CHECKPOINTS = _PAIRED_EVAL.CHECKPOINTS
REPLICATES = _PAIRED_EVAL.REPLICATES
SEEDS = _PAIRED_EVAL.SEEDS
UniformStream = _PAIRED_EVAL.UniformStream
compare_control = _PAIRED_EVAL.compare_control
episode_schedule = _PAIRED_EVAL.episode_schedule
require = _PAIRED_EVAL.require
sample_logits_cpu = _PAIRED_EVAL.sample_logits_cpu
sha256 = _PAIRED_EVAL.sha256
RUNTIME_DIR = ROOT / "learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime"
STATE_PATH = ROOT / "learning/runs/v2-orchestration/state.json"
PROTOCOL_PATH = PREPARE_DIR / "protocol-proposed.json"
INPUT_MANIFEST_PATH = PREPARE_DIR / "input-manifest.json"
DEPENDENCY_INVENTORY_PATH = ROOT / "learning/runs/v2/critic-diagnostic-parent-prepare-20261025-r1/dependency-inventory.json"
DEPENDENCY_INVENTORY_SHA256 = "2957832457c39751998012f4aeb4440f5d7570250ae9ab072ee10d86dd970ed6"
EXPECTED_INPUTS = {
    "best204_checkpoint": ("learning/runs/v2/D2-best180-branch-luna-20261026-r1/checkpoint-000204-candidate.pt",
                            "f1300e4e86ec89ed9cfba446c8e7f66cf29caad6a1130864edd4d6ee7859d442"),
    "latest252_checkpoint": ("learning/runs/v2/D2-best180-branch-luna-20261026-r1/checkpoint-000252-candidate.pt",
                             "4714133c0254bbdc48f36208b105026b234987e14d902a3754883a15a3b0796d"),
    "best204_receipt": ("learning/runs/v2/D2-best180-parent-terminal-audit-20261026-r1/retained-best-candidate-receipt.json",
                        "7fd26ae3f50ec7517a6f0a79334735bbfe48733b86639d83f7bafc122df110cf"),
    "best204_audit": ("learning/runs/v2/D2-best180-parent-terminal-audit-20261026-r1/audit.json",
                      "b93cfd247aa3cfaa83236faa8b9087d5b950d0573cebe5018f06a2d76125b9d1"),
    "best204_completed_iteration_receipt": ("learning/runs/v2/D2-best180-parent-terminal-audit-20261026-r1/parent-terminal-receipt.json",
                                             "059f927d5b2d23d0ad1c1083db64bd723dc91f2a6171100566ee5212350642dc"),
    "latest252_receipt": ("learning/runs/v2/D2-best180-parent-terminal-audit-20261026-r1/parent-terminal-receipt.json",
                          "059f927d5b2d23d0ad1c1083db64bd723dc91f2a6171100566ee5212350642dc"),
    "latest252_audit": ("learning/runs/v2/D2-best180-parent-terminal-audit-20261026-r1/audit.json",
                        "b93cfd247aa3cfaa83236faa8b9087d5b950d0573cebe5018f06a2d76125b9d1"),
    "best204_development": ("learning/runs/v2/D2-best180-branch-luna-20261026-r1/development-000204.jsonl",
                            "3ca81171ab7130ee337a4504e957695e7132e7e9f1243b0e8c48db87032fd55a"),
    "latest252_development": ("learning/runs/v2/D2-best180-branch-luna-20261026-r1/development-000252.jsonl",
                              "3538cf944f0726c31c24f13d3a8d72517818b8322b96cef57b3b730ab057c785"),
}
EXPECTED_RECEIPT_DETAILS = {
    "best204": {"phase_update": 204, "run_id": "D2-best180-branch-luna-20261026-r1",
                "checkpoint_sha256": EXPECTED_INPUTS["best204_checkpoint"][1]},
    "latest252": {"phase_update": 252, "run_id": "D2-best180-branch-luna-20261026-r1",
                  "checkpoint_sha256": EXPECTED_INPUTS["latest252_checkpoint"][1]},
}


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def sha256_bytes(value: bytes) -> str:
    import hashlib
    return hashlib.sha256(value).hexdigest()


def verify_inputs(root: Path = ROOT) -> dict:
    for label, (relative, expected_hash) in EXPECTED_INPUTS.items():
        path = root / relative
        require(path.is_file() and sha256(path) == expected_hash, f"Input pin mismatch: {relative}")
    require(sha256(DEPENDENCY_INVENTORY_PATH) == DEPENDENCY_INVENTORY_SHA256,
            "Dependency inventory anchor changed")
    inventory = load_json(DEPENDENCY_INVENTORY_PATH)
    require(inventory.get("scope") == "Python interpreter and installed Torch/NumPy package files excluding bytecode caches; OS frameworks and driver binaries not fully inventoried.",
            "Dependency inventory scope changed")
    pins = inventory.get("pins")
    require(isinstance(pins, dict) and len(pins) == 13513, "Dependency inventory structure differs")
    package_roots = {Path(path_text).parent for path_text in pins
                     if Path(path_text).parent.name in {"torch", "numpy"}}
    require({path.name for path in package_roots} == {"torch", "numpy"},
            "Dependency inventory package roots differ")
    actual_package_files = {str(path) for package_root in package_roots
                            for path in package_root.rglob("*") if path.is_file()
                            and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}}
    pinned_package_files = {path_text for path_text in pins
                            if any(path_text.startswith(str(package_root) + "/") for package_root in package_roots)}
    require(actual_package_files == pinned_package_files,
            "Installed Torch/NumPy package membership differs from dependency inventory")
    for path_text, expected in pins.items():
        path = Path(path_text)
        require(path.is_file() and path.stat().st_size == expected["size"]
                and sha256(path) == expected["sha256"], f"Dependency pin mismatch: {path_text}")
    manifest = load_json(INPUT_MANIFEST_PATH)
    require(manifest["dependency_inventory_sha256"] == DEPENDENCY_INVENTORY_SHA256
            and manifest["dependency_inventory_path"] == str(DEPENDENCY_INVENTORY_PATH.relative_to(root))
            and manifest["dependency_inventory_scope"] == inventory["scope"],
            "Manifest dependency inventory anchor or scope differs")
    require(manifest["schema"] == "latest_best_paired_eval_input_manifest_v1", "Unknown input manifest")
    protocol_hash = sha256(PROTOCOL_PATH)
    require(manifest["protocol_sha256"] == protocol_hash, "Protocol hash differs from input manifest")
    source_hashes = {}
    for name, digest in manifest["harness_source_files"].items():
        path = PREPARE_DIR / name
        require(path.is_file() and sha256(path) == digest, f"Harness source pin mismatch: {name}")
        source_hashes[name] = digest
    harness_hash = sha256_bytes(json.dumps(source_hashes, sort_keys=True, separators=(",", ":")).encode())
    require(manifest["harness_sha256"] == harness_hash
            and load_json(PROTOCOL_PATH)["harness_sha256"] == harness_hash,
            "Harness source set hash differs")
    for relative, digest in manifest["input_files"].items():
        path = root / relative
        require(path.is_file() and sha256(path) == digest, f"Pinned input file changed: {relative}")
    for name, digest in manifest["support_files"].items():
        path = PREPARE_DIR / name
        require(path.is_file() and sha256(path) == digest, f"Pinned support file changed: {name}")
    for name, digest in manifest["frozen_runtime_files"].items():
        path = root / name
        require(path.is_file() and sha256(path) == digest, f"Frozen runtime pin mismatch: {name}")
    runtime_digest = sha256_bytes(json.dumps(manifest["frozen_runtime_files"], sort_keys=True,
                                             separators=(",", ":")).encode())
    require(manifest["runtime_tree_sha256"] == runtime_digest, "Frozen runtime tree digest differs")
    interpreter = manifest["interpreter"]
    link = root / interpreter["lexical_venv_path"]
    target = Path(interpreter["resolved_target"])
    require(link.is_symlink() and str(link.resolve()) == str(target)
            and sha256(link) == interpreter["target_sha256"]
            and sha256(target) == interpreter["target_sha256"],
            "Pinned lexical interpreter link or resolved target differs")
    native = root / "learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime/dodge_rl/_native.cpython-312-darwin.so"
    require(sha256(native) == "022d41dde9bace0b4f4c4c06b9b4ed007bc2c60013cd98734086e587d7bb997e",
            "Frozen native extension hash differs")
    return manifest


def _receipt_anchor(label: str, root: Path) -> tuple[dict, dict]:
    receipt_key = f"{label}_receipt"
    relative, expected_hash = EXPECTED_INPUTS[receipt_key]
    receipt_path = root / relative
    require(sha256(receipt_path) == expected_hash, f"Accepted receipt hash mismatch: {label}")
    receipt = load_json(receipt_path)
    audit_rel, audit_hash = EXPECTED_INPUTS[f"{label}_audit"]
    audit_path = root / audit_rel
    require(sha256(audit_path) == audit_hash == receipt["audit_sha256"], f"Parent audit pin mismatch: {label}")
    audit = load_json(audit_path)
    require(audit.get("status") == "passed", f"Parent audit not passed: {label}")
    validate_execution_boundary(audit)
    detail = EXPECTED_RECEIPT_DETAILS[label]
    if label == "best204":
        completed_rel, completed_hash = EXPECTED_INPUTS["best204_completed_iteration_receipt"]
        completed_path = root / completed_rel
        require(sha256(completed_path) == completed_hash == receipt["completed_iteration_receipt_sha256"],
                "Selected candidate whole-iteration receipt pin mismatch")
        completed = load_json(completed_path)
        validate_training_counter_boundary(receipt, completed, audit)
        require(receipt["schema"] == "d2_retained_best_candidate_parent_receipt_v1"
                and receipt["status"] == "accepted_complete_candidate_from_completed_normal_training_iteration"
                and receipt["checkpoint_sha256"] == detail["checkpoint_sha256"]
                and receipt["checkpoint_path"] == str(root / EXPECTED_INPUTS["best204_checkpoint"][0])
                and receipt["candidate_phase_update"] == 204
                and receipt["candidate_local_update"] == 24
                and receipt["candidate_cumulative_counters"] == {
                    key: receipt["inherited_counters"][key] + receipt["candidate_counters"][key]
                    for key in receipt["candidate_counters"]}
                and receipt["completed_iteration_phase_update_end"] == completed["completed_phase_updates"] == 252
                and receipt["completed_iteration_local_updates"] == completed["completed_local_updates"] == 72
                and completed["schema"] == "d2_normal_training_parent_terminal_receipt_v1"
                and completed["status"] == "accepted_completed_normal_training_iteration"
                and completed["phase"] == "D2" and completed["run_id"] == receipt["run_id"]
                and completed["inherited_counters"] == receipt["inherited_counters"]
                and completed["cumulative_counters"] == {
                    key: completed["inherited_counters"][key] + completed["new_counters"][key]
                    for key in completed["new_counters"]}
                and completed["audit_sha256"] == receipt["audit_sha256"]
                and completed["registration_sha256"] == receipt["registration_sha256"]
                and completed["policy_sha256"] == receipt["policy_sha256"]
                and completed["native_sha256"] == receipt["native_sha256"]
                and completed["runtime_sha256"] == receipt["runtime_sha256"]
                and completed["config_sha256"] == receipt["config_sha256"]
                and completed["checkpoint_sha256"] == EXPECTED_INPUTS["latest252_checkpoint"][1]
                and completed["checkpoint_path"] == str(root / EXPECTED_INPUTS["latest252_checkpoint"][0]),
                "Selected candidate and completed-iteration authority differ")
        require(receipt["audit_sha256"] == audit_hash and receipt["candidate_parent_checkpoint_sha256"]
                == "105e0f7a83e154116bd9f0d5eaaf573a896886468c9038f548f5ce7e6377c7ea"
                and receipt["competence_passed"] is False and receipt["stage_promotion_eligible"] is False,
                "Selected-candidate authority boundary differs")
    else:
        require(receipt.get("cumulative_counters", {}).get("updates") == 300
                and audit.get("cumulative_counters") == receipt.get("cumulative_counters"),
                "Latest endpoint whole-run counters differ from parent audit")
        require(receipt["schema"] == "d2_normal_training_parent_terminal_receipt_v1"
                and receipt["status"] == "accepted_completed_normal_training_iteration"
                and receipt["phase"] == "D2"
                and receipt["run_id"] == detail["run_id"]
                and receipt["checkpoint_sha256"] == detail["checkpoint_sha256"]
                and receipt["checkpoint_path"] == str(root / EXPECTED_INPUTS[f"{label}_checkpoint"][0]),
                f"Terminal receipt identity differs: {label}")
        require(receipt["performance"]["checkpoint_sha256"] == detail["checkpoint_sha256"]
                and receipt["performance"]["episodes"] == 64 and receipt["performance"]["caps"] == 0,
                f"Terminal performance binding differs: {label}")
    return receipt, audit


def validate_execution_boundary(audit: dict) -> None:
    """Restore R4 boundary intent against the pinned parent audit's actual schema."""
    raw_exits = audit.get("raw_exits")
    require(isinstance(raw_exits, dict) and raw_exits.get("outer") == 0
            and raw_exits.get("worker") == 0, "Parent audit raw exits are not both zero")
    require(audit.get("owned_processes_and_groups_absent") is True,
            "Parent audit does not prove owned process and group absence")
    require(type(audit.get("pins_checked_before_and_after")) is int
            and audit["pins_checked_before_and_after"] > 0,
            "Parent audit lacks positive before-and-after pin checks")
    require(audit.get("observer_wrapper_error_disposition") ==
            "Wrapper caught its own successful SystemExit(0); observed exits and all independent gates pass. Original error artifact preserved.",
            "Parent audit observer SystemExit(0) wrapper disposition is unaccounted")
    require(audit.get("actual_evaluations_checked") == 7
            and audit.get("status") == "passed",
            "Parent audit does not report all seven source audit evaluations passing")


def validate_training_counter_boundary(selected: dict, whole: dict, audit: dict) -> None:
    """Keep selected local candidate update 252 distinct from whole-run update 300."""
    selected_cumulative = selected.get("candidate_cumulative_counters")
    whole_cumulative = whole.get("cumulative_counters")
    audit_cumulative = audit.get("cumulative_counters")
    require(isinstance(selected_cumulative, dict) and selected_cumulative.get("updates") == 252,
            "Selected best candidate cumulative updates must equal 252")
    require(isinstance(whole_cumulative, dict) and whole_cumulative.get("updates") == 300,
            "Completed whole-run cumulative updates must equal 300")
    require(audit_cumulative == whole_cumulative,
            "Parent audit and whole-run cumulative counters differ")


def load_inference_model(label: str, root: Path = ROOT, device: str = "cpu",
                         manifest: dict | None = None):
    """Use preflight-verified inputs, frozen current loader, and current v3 bindings."""
    import torch
    sys.path.insert(0, str(RUNTIME_DIR))
    from dodge_rl import checkpoints as ckpt
    from dodge_rl.models.teacher import OmniscientEntityTeacher

    require(label in CHECKPOINTS, "Unknown checkpoint label")
    if manifest is None:
        manifest = verify_inputs(root)
    receipt, _audit = _receipt_anchor(label, root)
    path = root / EXPECTED_INPUTS[f"{label}_checkpoint"][0]
    expected_hash = EXPECTED_INPUTS[f"{label}_checkpoint"][1]
    state = ckpt.load_checkpoint(path, expected_sha256=expected_hash)
    ckpt.require_complete_update(state)
    validate_checkpoint_receipt_binding(state, receipt, label, ckpt.identity_hash)
    before_rng = torch.get_rng_state().clone()
    with torch.random.fork_rng(devices=[]):
        model = OmniscientEntityTeacher()
    after_rng = torch.get_rng_state()
    require(torch.equal(before_rng, after_rng), "Model architecture validation changed global CPU RNG")
    model.load_state_dict(state["model"], strict=True)
    model.to(torch.device(device))
    model.requires_grad_(False)
    model.eval()
    require(not any(parameter.requires_grad for parameter in model.parameters()),
            "Inference model unexpectedly enables gradients")
    del state
    return model, {"checkpoint_sha256": expected_hash, "receipt_sha256": EXPECTED_INPUTS[f"{label}_receipt"][1],
                   "audit_sha256": EXPECTED_INPUTS[f"{label}_audit"][1],
                   "terminal_receipt_status": receipt["status"], "device": device,
                   "architecture": manifest["architecture"]}


def validate_checkpoint_receipt_binding(state: dict, receipt: dict, label: str, identity_hash) -> None:
    detail = EXPECTED_RECEIPT_DETAILS[label]
    if label == "best204":
        require(receipt["schema"] == "d2_retained_best_candidate_parent_receipt_v1"
                and receipt["status"] == "accepted_complete_candidate_from_completed_normal_training_iteration"
                and receipt["checkpoint_sha256"] == detail["checkpoint_sha256"]
                and receipt["candidate_phase_update"] == 204
                and receipt["candidate_local_update"] == 24
                and receipt["audit_sha256"] == EXPECTED_INPUTS["best204_audit"][1],
                f"Checkpoint/terminal receipt binding differs: {label}")
    else:
        require(receipt["schema"] == "d2_normal_training_parent_terminal_receipt_v1"
                and receipt["status"] == "accepted_completed_normal_training_iteration"
                and receipt["phase"] == "D2" and receipt["run_id"] == detail["run_id"]
                and receipt["checkpoint_sha256"] == detail["checkpoint_sha256"]
                and receipt["audit_sha256"] == EXPECTED_INPUTS[f"{label}_audit"][1],
                f"Checkpoint/terminal receipt binding differs: {label}")
    require(state["schema"] == "d2_training_v3_checkpoint_v1"
            and state["version"] == "teacher_checkpoint_v1"
            and state["resume_mode"] == "fresh_env"
            and state["phase"] == "D2" and state["tag"] == "candidate"
            and state["eligibility_status"] == "provisional_pending_parent_terminal_receipt"
            and state["training_eligible"] is False and state["promoted"] is False
            and state["phase_update"] == detail["phase_update"]
            and state["identity"]["run_id"] == detail["run_id"],
            f"Current v3 checkpoint fields differ: {label}")
    require(state["identity_sha256"] == identity_hash(state["identity"])
            and state["identity"]["config"]["phase"] == "D2",
            "Checkpoint identity hash/config binding differs")
    require(state["identity"]["config"]["action_repeat"] == 4
            and state["identity"]["config"]["powerups_enabled"] is True
            and state["identity"]["config"]["phase_settings"]["difficulty"] == 2
            and state["identity"]["config"]["phase_settings"]["patterns_enabled"] is True,
            "Checkpoint D2 environment binding differs")
    if label == "best204":
        candidate_counters = receipt["candidate_counters"]
        cumulative_counters = receipt["candidate_cumulative_counters"]
        local_update = receipt["candidate_local_update"]
        parent_checkpoint = receipt["candidate_parent_checkpoint_sha256"]
        require(state["identity"]["config"] is not None
                and state["config_sha256"] == receipt["config_sha256"]
                and state["identity"]["registration_sha256"] == receipt["registration_sha256"]
                and state["registration_sha256"] == receipt["registration_sha256"]
                and state["policy_sha256"] == receipt["policy_sha256"]
                and state["native_sha256"] == receipt["native_sha256"]
                and state["runtime_sha256"] == receipt["runtime_sha256"]
                and state["counters"] == candidate_counters
                and state["cumulative_counters"] == cumulative_counters
                and state["local_update"] == local_update
                and state["phase_update"] == receipt["candidate_phase_update"]
                and state["update_progress"]["completed_updates"] == local_update
                and state["parent_checkpoint_sha256"] == parent_checkpoint,
                f"Selected candidate counters or configuration differ: {label}")
        require(receipt["candidate_phase_update"] == detail["phase_update"]
                and receipt["run_id"] == detail["run_id"]
                and receipt["completed_iteration_local_updates"] == 72
                and receipt["completed_iteration_phase_update_end"] == 252
                and receipt["candidate_parent_checkpoint_sha256"] == state["parent_checkpoint_sha256"]
                and receipt["candidate_cumulative_counters"] == {
                    key: receipt["inherited_counters"][key] + receipt["candidate_counters"][key]
                    for key in receipt["candidate_counters"]}
                and receipt["stage_promotion_eligible"] is False
                and receipt["competence_passed"] is False
                and state["config_sha256"] == "2d8eb5626d0debdf5416d0b89610d78ddd56011c3238a82fec72efabe1bd7fe3",
                f"Selected candidate phase/config pin differs: {label}")
        return
    require(state["config_sha256"] == receipt["config_sha256"]
            and state["identity"]["registration_sha256"] == receipt["registration_sha256"]
            and state["policy_sha256"] == receipt["policy_sha256"]
            and state["native_sha256"] == receipt["native_sha256"]
            and state["runtime_sha256"] == receipt["runtime_sha256"]
            and state["cumulative_counters"] == receipt["cumulative_counters"]
            and state["phase_update"] == receipt["completed_phase_updates"]
            and state["phase_update"] == receipt["performance"]["update"]
            and state["local_update"] == receipt["completed_local_updates"]
            and state["counters"] == receipt["new_counters"]
            and state["update_progress"]["complete"] is True
            and state["update_progress"]["in_update"] is False
            and state["update_progress"]["completed_updates"] == receipt["completed_local_updates"]
            and state["parent_checkpoint_sha256"] == receipt["parent_checkpoint_sha256"]
            and state["registration_sha256"] == receipt["registration_sha256"],
            f"Checkpoint/terminal receipt binding differs: {label}")
    require(receipt["training_continuation_eligible"] is True
            and receipt["stage_promotion_eligible"] is False
            and receipt["competence_passed"] is False,
            f"Receipt eligibility boundary differs: {label}")


def verify_module_origins() -> dict:
    sys.path.insert(0, str(RUNTIME_DIR))
    import dodge_rl
    from dodge_rl import checkpoints, dev_eval, identity
    from dodge_rl.models import teacher
    from dodge_rl import _native
    import numpy
    import torch
    paths = {"numpy": Path(numpy.__file__).resolve(), "torch": Path(torch.__file__).resolve(),
             "dodge_rl": Path(dodge_rl.__file__).resolve(),
             "checkpoints": Path(checkpoints.__file__).resolve(),
             "dev_eval": Path(dev_eval.__file__).resolve(),
             "identity": Path(identity.__file__).resolve(),
             "teacher": Path(teacher.__file__).resolve(),
             "native": Path(_native.__file__).resolve()}
    site_packages = Path(numpy.__file__).resolve().parents[1]
    require(paths["numpy"].is_relative_to(site_packages) and paths["torch"].is_relative_to(site_packages),
            "Torch or NumPy module origin escaped registered site-packages")
    for name in ("dodge_rl", "checkpoints", "dev_eval", "identity", "teacher", "native"):
        require(paths[name].is_relative_to(RUNTIME_DIR.resolve()),
                f"Module origin escaped frozen runtime: {name}")
    return {"paths": {name: str(path) for name, path in paths.items()},
            "versions": {"torch": torch.__version__, "numpy": numpy.__version__}}


def _validate_step(index: int, seed: int, info: dict, terminated: bool, truncated: bool) -> None:
    require(not (terminated and truncated), "Episode terminated and truncated together")
    require(info["seed"]["actual_seed"] == seed and info["bootstrap"] == (not terminated),
            "Development episode boundary or seed differs")
    require(info["score_raw_fixed"] == info["score_delta_sum_raw_fixed"], "Score identity differs")
    objective = info["score_raw_fixed"] / 65536 + info["alive_frames"] / 100 - 5 * terminated
    require(math.isclose(info["objective_return"], objective, rel_tol=0.0, abs_tol=1e-9),
            "Development objective differs")


def _canonical_row(index: int, seed: int, info: dict, terminated: bool, truncated: bool,
                   death_fields) -> dict:
    _validate_step(index, seed, info, terminated, truncated)
    row = {"episode_index": index, "seed": seed, "score_raw_fixed": info["score_raw_fixed"],
           "score": info["score_raw_fixed"] / 65536, "alive_frames": info["alive_frames"],
           "gameplay_frames": info["gameplay_frames"], "terminated": terminated,
           "truncated": truncated, "objective_return": info["objective_return"],
           **death_fields(info, terminated, truncated)}
    require(set(row) == set(CANONICAL_ROW_KEYS), "Canonical episode schema changed")
    return row


def read_latest_resource_sample(path: Path, *, now: float | None = None,
                                max_age: float = 1.0) -> dict:
    """Read newest complete sample; partial tail is ignored and bad complete lines fail closed."""
    path = Path(path)
    require(path.is_file(), "Resource sample log is missing")
    raw = path.read_bytes()
    complete = raw.split(b"\n")
    if raw.endswith(b"\n"):
        lines = complete[:-1]
    else:
        lines = complete[:-1]
    require(bool(lines), "Resource sample log has no complete sample")
    records = []
    for line in lines:
        require(bool(line), "Resource sample log has an empty complete line")
        try:
            item = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"Malformed complete resource sample: {error}") from error
        require(isinstance(item, dict) and type(item.get("monotonic")) in {int, float}
                and math.isfinite(item["monotonic"])
                and type(item.get("rss_bytes")) is int and item["rss_bytes"] >= 0
                and type(item.get("mps_driver_bytes")) is int and item["mps_driver_bytes"] >= 0,
                "Malformed complete resource sample fields")
        records.append(item)
    latest = records[-1]
    observed_now = time.monotonic() if now is None else now
    age = observed_now - latest["monotonic"]
    require(age >= 0.0, "Resource sample timestamp is in the future")
    require(age <= max_age, "Resource sample is stale")
    return {"sample": latest, "age_seconds": age, "complete_records": len(records)}


def evaluate(model, *, checkpoint: str, mode: str, replicate_seed: int | None,
             env_factory, config_factory, seeds: tuple[int, ...] = SEEDS,
             expected_control_path: Path | None = None, check_guard=None,
             episode_sink=None, on_episode_row=None, fixture: bool = False) -> list[dict]:
    """Run one registered campaign arm or one explicitly bounded native fixture."""
    import torch

    require(checkpoint in CHECKPOINTS and mode in {"argmax", "sampled"}, "Unknown evaluation arm")
    require((mode == "argmax" and replicate_seed is None)
            or (mode == "sampled" and replicate_seed in REPLICATES), "Replicate provenance differs")
    if fixture:
        require(len(seeds) == 1 and seeds[0] in SEEDS and expected_control_path is None,
                "Native fixture must use one existing D development seed without control substitution")
        fixture_config = config_factory(seeds[0], "D2")
        require(type(fixture_config.get("raw_frame_cap")) is int
                and 0 < fixture_config["raw_frame_cap"] <= 128,
                "Native fixture frame cap exceeds 32 K=4 decisions")
    else:
        require(tuple(seeds) == SEEDS, "Only current 64 D development seeds are authorized")
    if mode == "sampled":
        streams = {seed: UniformStream(replicate_seed, seed) for seed in seeds}
    else:
        streams = {}
    envs, observations = {}, {}
    rows = {}
    from dodge_rl.dev_eval import OBSERVATION_KEYS, death_fields, development_seeds
    require(tuple(development_seeds()) == SEEDS, "Frozen development seed helper differs")
    try:
        for index, seed in enumerate(seeds):
            if check_guard:
                check_guard()
            env = env_factory(**config_factory(seed, "D2"))
            info = env.episode_info()[0]
            require(info["seed"]["evaluation"] and info["seed"]["actual_seed"] == seed
                    and info["startup_frames"] == 13, "Development constructor contract differs")
            envs[index], observations[index] = env, env.observations()
        with torch.inference_mode():
            while envs:
                if check_guard:
                    check_guard()
                active = sorted(envs)
                tensors = {name: torch.from_numpy(np.concatenate(
                    [observations[index][name] for index in active], axis=0)).to(next(model.parameters()).device)
                    for name in OBSERVATION_KEYS}
                output = model(*(tensors[name] for name in OBSERVATION_KEYS))
                logits = output.logits
                require(tuple(logits.shape) == (len(active), 9) and bool(torch.isfinite(logits).all()),
                        "Nonfinite or wrong-shaped inference output")
                if mode == "argmax":
                    actions = logits.argmax(dim=-1).to("cpu").tolist()
                else:
                    actions = [sample_logits_cpu(logits[position], streams[seeds[index]].next())
                               for position, index in enumerate(active)]
                del output, tensors
                for action_offset, (index, action) in enumerate(zip(active, actions, strict=True)):
                    if check_guard and action_offset > 0 and action_offset % GUARD_ACTION_CHUNK == 0:
                        check_guard()
                    result = envs[index].step(np.array([action], dtype=np.int64))
                    info = result["info"][0]
                    terminated, truncated = bool(result["terminated"][0]), bool(result["truncated"][0])
                    _validate_step(index, seeds[index], info, terminated, truncated)
                    if terminated or truncated:
                        row = _canonical_row(index, seeds[index], info, terminated, truncated, death_fields)
                        row.update(checkpoint=checkpoint, mode=mode, replicate_seed=replicate_seed)
                        rows[index] = row
                        if episode_sink:
                            episode_sink(row)
                        if on_episode_row:
                            on_episode_row(row)
                        del envs[index], observations[index]
                    else:
                        observations[index] = result["observations"]
                del logits
                if check_guard:
                    check_guard()
    finally:
        # PyO3 releases NativeVecDodgeEnv on reference drop; it has no close() API.
        # Clearing both maps is non-raising, so cleanup cannot replace a step error.
        envs.clear()
        observations.clear()
    completed = [rows[index] for index in range(len(seeds)) if index in rows]
    if fixture:
        require(len(completed) == 1, "Native fixture did not finish within its frame cap")
    else:
        require(len(completed) == 64 and [row["seed"] for row in completed] == list(SEEDS),
                "Development evaluation incomplete or reordered")
    if not fixture and mode == "argmax" and expected_control_path is not None:
        compare_control([{key: row[key] for key in CANONICAL_ROW_KEYS} for row in completed], expected_control_path)
    return completed


def _lease_check(protocol: dict, protocol_hash: str, harness_hash: str, manifest_hash: str,
                 state_path: Path = STATE_PATH) -> dict:
    state = load_json(state_path)
    require(state.get("active_long_campaign") is None, "Long campaign lease must be null")
    lease = state.get("active_inference_diagnostic")
    required = {"kind": "M3_latest_best_paired_eval", "authorization": "inference_only_paired_diagnostic",
                "run_id": protocol["run_id"], "protocol_sha256": protocol_hash,
                "harness_sha256": harness_hash, "input_manifest_sha256": manifest_hash}
    require(isinstance(lease, dict) and all(lease.get(key) == value for key, value in required.items()),
            "Exact parent-owned active inference lease missing or changed")
    require(lease.get("cancel_requested", False) is False, "Parent requested cancellation")
    review = protocol["lease_contract"]["required_review_fields"]
    require(lease.get("campaign_launch_authorized") is True
            and lease.get("review_status") == "reviewed"
            and isinstance(lease.get("review_provider"), str) and bool(lease["review_provider"].strip())
            and lease.get("no_concurrent_long_mps_training") is True
            and all(isinstance(lease.get(key), str) and len(lease[key]) == 64
                    and all(char in "0123456789abcdef" for char in lease[key]) for key in review),
            "Parent review/reconciliation gate is missing from the inference lease")
    return lease


STARTUP_SAMPLE_SECONDS = 10.0
GUARD_ACTION_CHUNK = 8


def _default_probe() -> tuple[int, int]:
    import torch
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss = int(peak if sys.platform == "darwin" else peak * 1024)
    return rss, int(torch.mps.driver_allocated_memory())


class ResourceSampler:
    def __init__(self, path: Path, *, probe=_default_probe, period: float = 0.25):
        self.path = Path(path)
        self.probe = probe
        self.period = period
        self.stop_event = threading.Event()
        self.first_sample = threading.Event()
        self.thread = None
        self.error = None

    def _sample(self):
        try:
            with self.path.open("x", buffering=1) as stream:
                while not self.stop_event.is_set():
                    rss, mps = self.probe()
                    stream.write(json.dumps({"monotonic": time.monotonic(), "rss_bytes": rss,
                                             "mps_driver_bytes": mps}, sort_keys=True) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                    self.first_sample.set()
                    self.stop_event.wait(self.period)
        except BaseException as error:
            self.error = f"{type(error).__name__}: {error}"
        finally:
            # Wake startup waiters; they re-check self.error before trusting any sample.
            self.first_sample.set()

    def start(self):
        self.thread = threading.Thread(target=self._sample, name="owned-resource-sampler", daemon=True)
        self.thread.start()

    def require_live(self):
        """Fail before further work if the sampler errored or stopped. Missing samples are not zero."""
        require(self.error is None, f"Resource sampler failed: {self.error}")
        require(self.thread is not None and self.thread.is_alive(), "Resource sampler is not running")

    def wait_first_sample(self, timeout: float = STARTUP_SAMPLE_SECONDS):
        """Bounded startup gate: no MPS model load until a complete sample has been written."""
        require(self.first_sample.wait(timeout), "No complete resource sample within startup bound")
        self.require_live()
        read_latest_resource_sample(self.path, max_age=1.0)

    def close(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=2.0)
        require(self.thread is None or not self.thread.is_alive(), "Resource sampler did not stop")
        require(self.error is None, f"Resource sampler failed: {self.error}")


def run_worker(output_dir: Path, *, protocol_path: Path = PROTOCOL_PATH,
               state_path: Path = STATE_PATH, resource_path: Path | None = None) -> int:
    """Child worker entrypoint, requires parent-installed lease. Never used in preparation."""
    import torch

    protocol = load_json(protocol_path)
    require(protocol["schema"] == "latest_best_paired_eval_protocol_v1",
            "Unknown paired evaluation protocol")
    manifest = verify_inputs()
    manifest_hash = sha256(INPUT_MANIFEST_PATH)
    protocol_hash = sha256(protocol_path)
    harness_hash = protocol["harness_sha256"]
    _lease_check(protocol, protocol_hash, harness_hash, manifest_hash, state_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    sampler = ResourceSampler(resource_path or output_dir.parent / "resources.jsonl")
    sampler.start()
    models = {}
    load_receipts = {}
    worker_result = {"schema": "latest_best_paired_eval_worker_result_v1", "status": "failed",
                     "actual_episode_count": 0, "completed_arms": 0, "episodes_expected": 512,
                     "load_receipts": load_receipts, "cancellation_lineage": [],
                     "publication_failure": None, "module_origins": {}}
    streams = []
    try:
        # MPS work starts only after a complete owned sample exists and the sampler is still live.
        sampler.wait_first_sample(STARTUP_SAMPLE_SECONDS)
        read_latest_resource_sample(sampler.path, max_age=1.0)
        require(torch.backends.mps.is_available(), "Registered MPS inference device unavailable")
        torch.set_num_threads(4)
        device = torch.device("mps")
        for label in CHECKPOINTS:
            sampler.require_live()
            models[label], load_receipts[label] = load_inference_model(label, device="mps", manifest=manifest)
            sampler.require_live()
        from dodge_rl import VecDodgeEnv
        from dodge_rl.dev_eval import development_environment_config
        summarize_all = _PAIRED_EVAL.summarize_all
        worker_result["module_origins"] = verify_module_origins()
        episode_path = output_dir / "episodes.jsonl"
        with episode_path.open("x", buffering=1) as episodes:
            def sink(row):
                episodes.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
                episodes.flush()
                os.fsync(episodes.fileno())

            def row_persisted(_row):
                worker_result["actual_episode_count"] += 1

            def guard():
                sampler.require_live()
                fresh = read_latest_resource_sample(sampler.path, max_age=1.0)
                worker_result["max_resource_sample_age_seconds"] = max(
                    worker_result.get("max_resource_sample_age_seconds", 0.0), fresh["age_seconds"])
                guard_start = time.perf_counter()
                _lease_check(protocol, protocol_hash, harness_hash, manifest_hash, state_path)
                guard_elapsed = time.perf_counter() - guard_start
                worker_result["guard_check_count"] = worker_result.get("guard_check_count", 0) + 1
                worker_result["lease_check_total_seconds"] = worker_result.get(
                    "lease_check_total_seconds", 0.0) + guard_elapsed
                worker_result["lease_check_max_seconds"] = max(
                    worker_result.get("lease_check_max_seconds", 0.0), guard_elapsed)
                require(time.monotonic() - started <= 590.0, "590-second inference work limit exceeded")

            for item in episode_schedule():
                guard()
                label, mode, rep = item["checkpoint"], item["mode"], item["replicate_seed"]
                control_path = None
                if mode == "argmax":
                    control_key = "best204_development" if label == "best204" else "latest252_development"
                    control_path = ROOT / EXPECTED_INPUTS[control_key][0]
                arm_rows = evaluate(models[label], checkpoint=label, mode=mode, replicate_seed=rep,
                                    env_factory=VecDodgeEnv,
                                    config_factory=development_environment_config,
                                    expected_control_path=control_path, check_guard=guard,
                                    episode_sink=sink, on_episode_row=row_persisted)
                worker_result["completed_arms"] += 1
                streams.extend(arm_rows)
                del arm_rows
                guard()
        require(worker_result["actual_episode_count"] == 512, "Worker episode count differs")
        worker_result["summary"] = summarize_all(streams)
        worker_result["status"] = "complete"
        worker_result["elapsed_work_seconds"] = time.monotonic() - started
    except BaseException as error:
        worker_result["error"] = f"{type(error).__name__}: {error}"
        worker_result["elapsed_work_seconds"] = time.monotonic() - started
    finally:
        try:
            sampler.close()
        except BaseException as error:
            worker_result["status"] = "failed"
            worker_result["resource_sampler_error"] = f"{type(error).__name__}: {error}"
        for model in models.values():
            del model
    with (output_dir / "worker-result.json").open("x") as stream:
        json.dump(worker_result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return 0 if worker_result["status"] == "complete" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resource-log", type=Path)
    args = parser.parse_args()
    require(os.environ.get("T3_PAIRED_EVAL_SUPERVISED") == "1",
            "Worker can only start through the registered supervisor")
    require(args.worker and args.output is not None and args.resource_log is not None,
            "Worker requires explicit supervised launch flags")
    return run_worker(args.output, resource_path=args.resource_log)


if __name__ == "__main__":
    raise SystemExit(main())
