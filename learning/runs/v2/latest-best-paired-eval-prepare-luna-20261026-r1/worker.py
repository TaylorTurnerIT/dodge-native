"""One-shot inference worker. Importable tests use fake environments only."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import resource
import sys
import threading
import time

import numpy as np

from paired_eval import (CANONICAL_ROW_KEYS, CHECKPOINTS, REPLICATES, SEEDS,
                         UniformStream, compare_control, episode_schedule,
                         require, sample_logits_cpu, sha256)


ROOT = Path(__file__).resolve().parents[4]
PREPARE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / "learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime"
STATE_PATH = ROOT / "learning/runs/v2-orchestration/state.json"
PROTOCOL_PATH = PREPARE_DIR / "protocol-proposed.json"
INPUT_MANIFEST_PATH = PREPARE_DIR / "input-manifest.json"
EXPECTED_INPUTS = {
    "best180_checkpoint": ("learning/runs/v2/D2-gradient-alignment-20261025-r2/checkpoint-000180-candidate.pt",
                            "105e0f7a83e154116bd9f0d5eaaf573a896886468c9038f548f5ce7e6377c7ea"),
    "latest252_checkpoint": ("learning/runs/v2/D2-continuation-20261025-r2/checkpoint-000252-candidate.pt",
                             "cbdc65d0f3b2e32644ba64ada80093f20c7a6bceb8730f2eecac7a188504254b"),
    "best180_receipt": ("learning/runs/v2/d2-gradient-parent-terminal-audit-20261025-r2/parent-terminal-receipt.json",
                        "7968a62b6e601fab971e4145dbaebfa1995c8f696e6df442ab70fc0435b74903"),
    "best180_audit": ("learning/runs/v2/d2-gradient-parent-terminal-audit-20261025-r2/audit.json",
                      "a93fe6abd35e715c538522dff1bf381a52b8c60f79e30914aa7b953b4f2864af"),
    "latest252_receipt": ("learning/runs/v2/d2-continuation252-parent-terminal-audit-20261026-r1/parent-terminal-receipt.json",
                          "25f2744d39e2c48e48333088c78855af1ad3b65f1053f576d70f9ac38b5d4096"),
    "latest252_audit": ("learning/runs/v2/d2-continuation252-parent-terminal-audit-20261026-r1/audit.json",
                        "08eb63b4c6d199bfb44e3abdafd1d773ab921de3687c04641c6df596ad7313b2"),
    "best180_development": ("learning/runs/v2/D2-gradient-alignment-20261025-r2/development-000180.jsonl",
                            "33e7859274c65cbefb627e595006e4c64650a653ccace1e059bc9e46a8df76f1"),
    "latest252_development": ("learning/runs/v2/D2-continuation-20261025-r2/development-000252.jsonl",
                              "dd02551520977ceb26cddec7a7d9437265d3fbfd58917a79bbc52cc1f5929d36"),
}
EXPECTED_RECEIPT_DETAILS = {
    "best180": {"phase_update": 180, "run_id": "D2-gradient-alignment-20261025-r2",
                "checkpoint_sha256": EXPECTED_INPUTS["best180_checkpoint"][1]},
    "latest252": {"phase_update": 252, "run_id": "D2-continuation-20261025-r2",
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
    manifest = load_json(INPUT_MANIFEST_PATH)
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
    detail = EXPECTED_RECEIPT_DETAILS[label]
    require(receipt["schema"] == "d2_normal_training_parent_terminal_receipt_v1"
            and receipt["status"] == "accepted_completed_normal_training_iteration"
            and receipt["phase"] == "D2"
            and receipt["run_id"] == detail["run_id"]
            and receipt["checkpoint_sha256"] == detail["checkpoint_sha256"]
            and receipt["checkpoint_path"] == str(root / EXPECTED_INPUTS[f"{label}_checkpoint"][0]),
            f"Terminal receipt identity differs: {label}")
    require(receipt["raw_outer_exit"] == 0 and receipt["raw_worker_exit"] == 0
            and receipt["all_owned_processes_absent"] is True
            and receipt["publication_failure_present"] is False
            and receipt["cancellation_lineage"] == []
            and receipt["source_pins_verified"] > 0,
            f"Terminal receipt execution boundary differs: {label}")
    require(receipt["performance"]["checkpoint_sha256"] == detail["checkpoint_sha256"]
            and receipt["performance"]["episodes"] == 64 and receipt["performance"]["caps"] == 0,
            f"Terminal performance binding differs: {label}")
    return receipt, audit


def load_inference_model(label: str, root: Path = ROOT, device: str = "cpu"):
    """Use frozen current ckpt loader, then require current v3 and terminal bindings."""
    import torch
    sys.path.insert(0, str(RUNTIME_DIR))
    from dodge_rl import checkpoints as ckpt
    from dodge_rl.models.teacher import OmniscientEntityTeacher

    require(label in CHECKPOINTS, "Unknown checkpoint label")
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
    paths = {"dodge_rl": Path(dodge_rl.__file__).resolve(),
             "checkpoints": Path(checkpoints.__file__).resolve(),
             "dev_eval": Path(dev_eval.__file__).resolve(),
             "identity": Path(identity.__file__).resolve(),
             "teacher": Path(teacher.__file__).resolve(),
             "native": Path(dodge_rl.VecDodgeEnv.__module__ and
                            __import__("dodge_rl._native", fromlist=["__file__"]).__file__).resolve()}
    for name, path in paths.items():
        require(path.is_relative_to(RUNTIME_DIR.resolve()), f"Module origin escaped frozen runtime: {name}")
    return {name: str(path) for name, path in paths.items()}


def _canonical_row(index: int, seed: int, info: dict, terminated: bool, truncated: bool,
                   death_fields) -> dict:
    require(not (terminated and truncated), "Episode terminated and truncated together")
    require(info["seed"]["actual_seed"] == seed and info["bootstrap"] == (not terminated),
            "Development episode boundary or seed differs")
    require(info["score_raw_fixed"] == info["score_delta_sum_raw_fixed"], "Score identity differs")
    objective = info["score_raw_fixed"] / 65536 + info["alive_frames"] / 100 - 5 * terminated
    require(math.isclose(info["objective_return"], objective, rel_tol=0.0, abs_tol=1e-9),
            "Development objective differs")
    row = {"episode_index": index, "seed": seed, "score_raw_fixed": info["score_raw_fixed"],
           "score": info["score_raw_fixed"] / 65536, "alive_frames": info["alive_frames"],
           "gameplay_frames": info["gameplay_frames"], "terminated": terminated,
           "truncated": truncated, "objective_return": info["objective_return"],
           **death_fields(info, terminated, truncated)}
    require(set(row) == set(CANONICAL_ROW_KEYS), "Canonical episode schema changed")
    return row


def evaluate(model, *, checkpoint: str, mode: str, replicate_seed: int | None,
             env_factory, config_factory, seeds: tuple[int, ...] = SEEDS,
             expected_control_path: Path | None = None, check_guard=None,
             episode_sink=None) -> list[dict]:
    """Run one 64-seed evaluation. Tests inject deterministic fake B1 environments."""
    import torch

    require(checkpoint in CHECKPOINTS and mode in {"argmax", "sampled"}, "Unknown evaluation arm")
    require((mode == "argmax" and replicate_seed is None)
            or (mode == "sampled" and replicate_seed in REPLICATES), "Replicate provenance differs")
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
                for index, action in zip(active, actions, strict=True):
                    if check_guard:
                        check_guard()
                    result = envs[index].step(np.array([action], dtype=np.int64))
                    info = result["info"][0]
                    terminated, truncated = bool(result["terminated"][0]), bool(result["truncated"][0])
                    row = _canonical_row(index, seeds[index], info, terminated, truncated, death_fields)
                    if terminated or truncated:
                        row.update(checkpoint=checkpoint, mode=mode, replicate_seed=replicate_seed)
                        rows[index] = row
                        if episode_sink:
                            episode_sink(row)
                        envs[index].close()
                        del envs[index], observations[index]
                    else:
                        observations[index] = result["observations"]
                del logits
                if check_guard:
                    check_guard()
    finally:
        for env in envs.values():
            env.close()
    completed = [rows[index] for index in range(64)]
    require(len(completed) == 64 and [row["seed"] for row in completed] == list(SEEDS),
            "Development evaluation incomplete or reordered")
    if mode == "argmax" and expected_control_path is not None:
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
            and lease.get("haiku_review_status") == "reviewed"
            and lease.get("no_concurrent_long_mps_training") is True
            and all(isinstance(lease.get(key), str) and len(lease[key]) == 64
                    and all(char in "0123456789abcdef" for char in lease[key]) for key in review),
            "Parent review/reconciliation gate is missing from the inference lease")
    return lease


class ResourceSampler:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.stop_event = threading.Event()
        self.thread = None
        self.error = None

    def _sample(self):
        try:
            import torch
            with self.path.open("x", buffering=1) as stream:
                while not self.stop_event.is_set():
                    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                    rss = int(peak if sys.platform == "darwin" else peak * 1024)
                    mps = int(torch.mps.driver_allocated_memory())
                    stream.write(json.dumps({"monotonic": time.monotonic(), "rss_bytes": rss,
                                             "mps_driver_bytes": mps}, sort_keys=True) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                    self.stop_event.wait(0.25)
        except BaseException as error:
            self.error = f"{type(error).__name__}: {error}"

    def start(self):
        self.thread = threading.Thread(target=self._sample, name="owned-resource-sampler", daemon=True)
        self.thread.start()

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
                     "actual_episode_count": 0, "episodes_expected": 512,
                     "load_receipts": load_receipts, "cancellation_lineage": [],
                     "publication_failure": None, "module_origins": {}}
    streams = []
    try:
        require(torch.backends.mps.is_available(), "Registered MPS inference device unavailable")
        torch.set_num_threads(4)
        device = torch.device("mps")
        for label in CHECKPOINTS:
            models[label], load_receipts[label] = load_inference_model(label, device="mps")
        from dodge_rl import VecDodgeEnv
        from dodge_rl.dev_eval import development_environment_config
        from paired_eval import summarize_all
        worker_result["module_origins"] = verify_module_origins()
        episode_path = output_dir / "episodes.jsonl"
        with episode_path.open("x", buffering=1) as episodes:
            def sink(row):
                episodes.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
                episodes.flush()
                os.fsync(episodes.fileno())

            def guard():
                _lease_check(protocol, protocol_hash, harness_hash, manifest_hash, state_path)
                require(time.monotonic() - started <= 590.0, "590-second inference work limit exceeded")

            for item in episode_schedule():
                guard()
                label, mode, rep = item["checkpoint"], item["mode"], item["replicate_seed"]
                control_path = None
                if mode == "argmax":
                    control_key = "best180_development" if label == "best180" else "latest252_development"
                    control_path = ROOT / EXPECTED_INPUTS[control_key][0]
                arm_rows = evaluate(models[label], checkpoint=label, mode=mode, replicate_seed=rep,
                                    env_factory=VecDodgeEnv,
                                    config_factory=development_environment_config,
                                    expected_control_path=control_path, check_guard=guard,
                                    episode_sink=sink)
                worker_result["actual_episode_count"] += len(arm_rows)
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
