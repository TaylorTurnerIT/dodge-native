"""Prospective D2 training-v3 contracts; no state or lease writes."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from collections.abc import Mapping

PARENT_SHA = "ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f"
ANCHOR_SHA = "4e9f12884712916e9eb957628b89b357784c79d0f1f6f8ab18e6047935197413"
VALIDATOR_SHA = "72c34ea7a3208f8ce1cba1cd144b3ba58bac7b246ce57610b70970355ac60c55"
ARCHIVE_SHA = "3b4b1e4f3337323de9938c0c86f158036d8dacc77acba645b3e150d9d2e765bd"
OLD_NATIVE_SHA = "967c7249acd52339d1818dcbe94e63ee734aea914c3497eb59a7e945a6e95583"
CONFIG_SHA = "2d8eb5626d0debdf5416d0b89610d78ddd56011c3238a82fec72efabe1bd7fe3"
POLICY_SHA = "bfcbee1609cec0180495c957cf4b5e0b31356f395e2a706217cc9225647d23ae"
SURVIVAL_GATE_SHA = "11257111602f26e49fbc71afc6a51acb79434a3717bd8d6d36d1bbf87dfb8841"
DEV_EVAL_SHA = "eecf71936f10938169c0283ed1bb0717b87e46da7ee4ac8636a20d366df3753b"
NEW_NATIVE_SHA = "022d41dde9bace0b4f4c4c06b9b4ed007bc2c60013cd98734086e587d7bb997e"
RECEIPT_SHA = "3616bd5ab6ee00c372a793f98b0559bec87d6b2c781513b98725a0274a0091b5"
RUN_ID = "D2-training-v3-20261025-r1"
LIMITS = {"max_updates": 72, "eval_updates": [0, 72],
          "work_seconds": 1600, "total_seconds": 1800,
          "RSS_bytes": 6442450944, "MPS_bytes": 6442450944, "retries": 0}
EVAL_UPDATES = tuple(LIMITS["eval_updates"])
SEED_EXCLUSIONS = [[2952790016, 2952791015], [3489660928, 3489661055], [3758096384, 3758097383]]


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def v3_progress_passed(summary):
    """Use documented v3 survival predicate only; score is never a gate."""
    need(isinstance(summary, Mapping), "Evaluation summary must be a mapping")
    value = summary.get("mean_alive_frames")
    need(type(value) in (int, float) and math.isfinite(value), "Evaluation mean must be finite")
    return summary.get("complete") is True and value >= 3060


def validate_registration(reg, root):
    root = Path(root).resolve()
    here = Path(__file__).resolve().parent
    need(reg.get("schema") == "d2_training_v3_registration_v1", "Wrong v3 registration schema")
    required = {"root", "run_id", "phase", "limits", "parent", "output", "policy",
                "legacy_validator", "pins", "import_policy", "runtime_root", "native",
                "runtime_sha256", "expected_lease", "state_path",
                "interpreter", "runner_path", "launcher_path", "config_path", "run_seed",
                "helper_path", "adapter_path", "source_manifest_path", "source_manifest_sha256",
                "seed_draws", "seed_excluded_ranges", "timing_policy",
                "cancel_path", "one_use_marker_path", "terminal_receipt_path"}
    need(required <= reg.keys(), "Parent registration fields missing")
    need(Path(reg["root"]).resolve() == root, "Registration root differs")
    need(reg.get("run_id") == RUN_ID and reg.get("limits") == LIMITS, "Registration identity or limits differ")
    need(reg.get("phase") == "D2" and reg.get("training_eligible") is False,
         "Prospective candidate flags differ")
    need(reg.get("parent", {}).get("sha256") == PARENT_SHA, "Only accepted initial D1 is permitted")
    need(reg["parent"].get("anchor_sha256") == ANCHOR_SHA, "Accepted D1 anchor hash differs")
    need(Path(reg["parent"]["path"]).resolve() == root / "learning/runs/v2/milestone3-D1-curriculum-r1/checkpoint-000009-candidate.pt",
         "Accepted D1 path substitution")
    out = Path(reg["output"]).resolve()
    need(out.name == RUN_ID and out.parent == (root / "learning/runs/v2").resolve(), "Output path substitution")
    need(Path(reg["one_use_marker_path"]).resolve() == out / "launch-marker.json"
         and Path(reg["terminal_receipt_path"]).is_absolute()
         and Path(reg["cancel_path"]).is_absolute() and Path(reg["state_path"]).is_absolute(),
         "Parent output or control path differs")
    need(Path(reg["terminal_receipt_path"]).resolve().is_relative_to(out),
         "Parent terminal receipt must stay inside the new run output")
    need(reg["timing_policy"] == {"work_seconds": 1600, "total_seconds": 1800},
         "Frozen timing policy differs")
    policy = root / "docs/teacher-qualification-v3.json"
    need(reg["policy"]["path"] == str(policy) and sha(policy) == POLICY_SHA
         and reg["policy"]["sha256"] == POLICY_SHA and reg["pins"].get(str(policy)) == POLICY_SHA,
         "V3 policy pin differs")
    need(reg["legacy_validator"]["path"] == str(root / "learning/runs/v2/critic-diagnostic-parent-prepare-20261025-r1/runtime/dodge_rl/survival_gate.py"),
         "Legacy validator source path differs")
    need(reg["legacy_validator"]["sha256"] == SURVIVAL_GATE_SHA
         and reg["pins"].get(reg["legacy_validator"]["path"]) == SURVIVAL_GATE_SHA,
         "Legacy validator hash not pinned")
    need(Path(reg["legacy_validator"]["path"]).read_bytes() ==
         (root / "python/dodge_rl/survival_gate.py").read_bytes(), "Survival gate changed")
    proof_path = Path(reg["parent"]["validation_receipt_path"])
    need(reg["parent"]["validation_receipt_sha256"] == RECEIPT_SHA
         and reg["parent"]["validation_receipt_sha256"] == reg["pins"].get(str(proof_path)),
         "Original transition receipt not pinned")
    proof = json.loads(proof_path.read_text())
    validator_path = reg["legacy_validator"]["path"]
    expected = {"status": "passed", "parent_phase": "D1", "target_phase": "D2",
                "exact_parent_sha256": PARENT_SHA, "certificate_passed": True,
                "parent_optimizer_steps": 6144, "no_learner_restore_or_environment": True}
    need(proof.get("raw_exit") == 0 and proof.get("matches_stored_transition_result") is True
         and proof.get("parent_sha256") == PARENT_SHA
         and proof.get("validator_sha256") == VALIDATOR_SHA
         and proof.get("archive_sha256") == ARCHIVE_SHA
         and proof.get("old_extension_sha256") == OLD_NATIVE_SHA
         and json.loads(proof.get("stdout", "{}")) == expected,
         "Original accepted D1 transition validation failed")
    for key, expected_hash in (("anchor_path", ANCHOR_SHA), ("validator_path", VALIDATOR_SHA),
                               ("archive_path", ARCHIVE_SHA)):
        path = reg["parent"][key]
        need(reg["pins"].get(path) == expected_hash and sha(path) == expected_hash,
             "Original accepted D1 lineage pin differs: " + key)
    need(Path(reg["parent"]["validator_path"]).resolve() == root / "learning/runs/v2/milestone3-D2-freeze-r1/validate-transition.py",
         "Original transition validator path differs")
    anchor = json.loads(Path(reg["parent"]["anchor_path"]).read_text())
    need(anchor.get("checkpoint_sha256") == PARENT_SHA and anchor.get("supervisor_exit_code") == 0
         and anchor.get("phase") == "D1", "Original accepted D1 terminal anchor differs")
    need(reg["pins"].get(reg["config_path"]) == CONFIG_SHA, "Frozen learner config hash differs")
    need(Path(validator_path).resolve() == root / "learning/runs/v2/critic-diagnostic-parent-prepare-20261025-r1/runtime/dodge_rl/survival_gate.py",
         "Legacy survival gate path differs")
    need(reg["import_policy"].get("python_flag") == "-B" and Path(reg["import_policy"].get("PYTHONPYCACHEPREFIX", "")).is_absolute(), "Import cache policy differs")
    need(reg["runtime_root"] == str(root / "learning/runs/v2/critic-diagnostic-parent-prepare-20261025-r1/runtime"),
         "Runtime root differs")
    package = Path(reg["runtime_root"]) / "dodge_rl"
    runtime_files = sorted(str(p.resolve()) for p in package.rglob("*") if p.is_file())
    need(bool(runtime_files) and set(runtime_files) <= reg["pins"].keys(),
         "Immutable runtime contains an unpinned member")
    runtime_identity = hashlib.sha256(json.dumps(
        {name: reg["pins"][name] for name in runtime_files}, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()
    need(reg["runtime_sha256"] == runtime_identity, "Immutable runtime manifest hash differs")
    need(Path(reg["native"]["path"]).resolve() == Path(reg["runtime_root"]) / "dodge_rl/_native.cpython-312-darwin.so"
         and reg["native"]["sha256"] == reg["pins"].get(reg["native"]["path"])
         and reg["native"]["sha256"] == NEW_NATIVE_SHA
         and reg["native"]["old_sha256"] == OLD_NATIVE_SHA
         and reg["native"]["old_sha256"] == reg["pins"].get(reg["native"]["old_path"]),
         "Native runtime or original native safety pin differs")
    need(reg["pins"].get(str(Path(reg["runtime_root"]) / "dodge_rl/dev_eval.py")) == DEV_EVAL_SHA,
         "Immutable dev_eval source hash differs")
    validate_seed_policy(reg["run_seed"], reg["seed_draws"], reg["seed_excluded_ranges"])
    lease = reg["expected_lease"]
    need(isinstance(lease, dict) and lease.get("run_id") == RUN_ID
         and lease.get("kind") in {"D2_training", "D2_training_v3"}
         and lease.get("parent_checkpoint_sha256") == PARENT_SHA
         and isinstance(lease.get("authorization"), str) and bool(lease["authorization"])
         and "critic" not in lease["authorization"].lower()
         and "diagnostic" not in lease["authorization"].lower(), "Parent lease identity differs")
    need(Path(reg["runner_path"]).is_absolute() and Path(reg["launcher_path"]).is_absolute()
         and Path(reg["interpreter"]).is_absolute() and Path(reg["config_path"]).is_absolute()
         and Path(reg["runner_path"]).resolve() == here / "worker.py"
         and Path(reg["launcher_path"]).resolve() == here / "launcher.py"
         and Path(reg["adapter_path"]).resolve() == Path(__file__).resolve()
         and Path(reg["helper_path"]).resolve() == Path(__file__).with_name("helper.py").resolve(),
         "Registered source roots or executable paths differ")
    need(Path(reg["config_path"]).resolve() == root / "learning/runs/v2/milestone3-D2-freeze-r1/D2-config.json"
         and Path(reg["interpreter"]).resolve() == (root / "python/.venv/bin/python").resolve()
         and Path(reg["native"]["old_path"]).resolve() == root / "python/dodge_rl/_native.cpython-312-darwin.so"
         and Path(reg["state_path"]).resolve() == root / "learning/runs/v2-orchestration/state.json"
         and Path(reg["source_manifest_path"]).resolve().parent == here,
         "Registered config, interpreter, original native, or manifest root differs")
    need(reg["runtime_versions"] == {"python": "3.12.15", "torch": "2.14.1", "numpy": "2.5.4"},
         "Registered interpreter package versions differ")
    for path, digest in reg["pins"].items():
        need(Path(path).is_absolute() and Path(path).is_file() and sha(path) == digest, "Pinned input differs: " + path)
    for key in ("runner_path", "launcher_path", "helper_path", "adapter_path", "config_path", "interpreter", "native"):
        path = reg["native"]["path"] if key == "native" else reg[key]
        need(reg["pins"].get(path) == sha(path), "Critical registration source is not pinned: " + path)
    need(reg["pins"].get(reg["parent"]["validation_receipt_path"]) == sha(reg["parent"]["validation_receipt_path"]),
         "Original transition receipt is not pinned")
    manifest_path = reg["source_manifest_path"]
    need(reg["pins"].get(manifest_path) == reg["source_manifest_sha256"]
         and sha(manifest_path) == reg["source_manifest_sha256"], "Source manifest pin differs")
    manifest = json.loads(Path(manifest_path).read_text())
    manifest_files = manifest.get("files")
    required_sources = {reg[k] for k in ("runner_path", "launcher_path", "helper_path", "adapter_path",
        "config_path", "interpreter", "policy") if isinstance(reg[k], str)}
    required_sources.update((reg["policy"]["path"], reg["legacy_validator"]["path"], reg["native"]["path"],
                             reg["native"]["old_path"], reg["parent"]["path"],
                             reg["parent"]["anchor_path"], reg["parent"]["validator_path"],
                             reg["parent"]["archive_path"], reg["parent"]["validation_receipt_path"]))
    need(isinstance(manifest_files, dict) and required_sources <= manifest_files.keys(),
         "Source manifest critical member set incomplete")
    need(set(reg["pins"]) == set(manifest_files) | {manifest_path},
         "Registration pin set differs from the frozen source manifest")
    allowed_roots = (here, Path(reg["runtime_root"]) / "dodge_rl")
    allowed_files = {Path(reg[k]).resolve() for k in ("config_path", "interpreter")}
    allowed_files.update(Path(value).resolve() for value in (
        reg["policy"]["path"], reg["legacy_validator"]["path"], reg["native"]["path"],
        reg["native"]["old_path"], reg["parent"]["path"], reg["parent"]["anchor_path"],
        reg["parent"]["validator_path"], reg["parent"]["archive_path"],
        reg["parent"]["validation_receipt_path"],
        str(root / "python/dodge_rl/survival_gate.py")))
    for path, digest in manifest_files.items():
        resolved = Path(path).resolve()
        need(any(resolved == allowed or resolved.is_relative_to(allowed) for allowed in allowed_roots)
             or resolved in allowed_files, "Source manifest path is outside registered roots: " + path)
        need(reg["pins"].get(path) == digest and sha(path) == digest, "Source manifest file differs: " + path)
    return reg


def check_import_cache(reg, environ=None):
    env = os.environ if environ is None else environ
    prefix = env.get("PYTHONPYCACHEPREFIX")
    expected = reg["import_policy"]["PYTHONPYCACHEPREFIX"]
    need(Path(expected).is_absolute() and Path(expected).is_dir() and not any(Path(expected).iterdir()),
         "Dedicated bytecode prefix must exist and be empty")
    need(prefix == expected, "PYTHONPYCACHEPREFIX differs from dedicated prefix")
    import sys
    need(sys.pycache_prefix == expected, "Interpreter bytecode prefix differs")
    need(reg["import_policy"]["python_flag"] == "-B", "Python bytecode flag differs")


def check_lease(reg):
    state = json.loads(Path(reg["state_path"]).read_text())
    need(state.get("active_long_campaign") == reg["expected_lease"], "Parent-owned D2 training lease changed")


def validate_seed_policy(run_seed, seed_draws, excluded_ranges):
    need(run_seed == 810631976 and seed_draws == 1 and excluded_ranges == SEED_EXCLUSIONS,
         "Fresh D2 seed policy differs")


def checkpoint_payload(*, model, optimizer, rng, registration, counters, run_seed,
                       registration_sha256, identity, identity_sha256, next_episode_indices,
                       abandoned_current_episodes, update_progress, cumulative_wall_seconds):
    need(type(counters.get("updates")) is int and counters["updates"] in range(0, 73)
         and update_progress.get("complete") is True and update_progress.get("in_update") is False,
         "Checkpoint is not at complete update boundary")
    validate_seed_policy(run_seed, 1, SEED_EXCLUSIONS)
    need(isinstance(model, Mapping) and bool(model) and isinstance(optimizer, Mapping)
         and bool(optimizer) and isinstance(rng, Mapping)
         and {"python", "numpy_global", "numpy_generator", "torch_cpu", "torch_mps",
              "sampling_backend"} <= rng.keys(),
         "Checkpoint learner or complete RNG state missing")
    identity_digest = hashlib.sha256(json.dumps(identity, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    need(identity_sha256 == identity_digest and identity.get("version") == "teacher_identity_v3"
         and identity.get("phase") == "D2", "Checkpoint v3 identity digest differs")
    need(len(next_episode_indices) == 64 and all(type(i) is int and i >= 0 for i in next_episode_indices),
         "Checkpoint episode indices differ")
    need(registration.get("pins", {}).get(registration.get("config_path")) is not None, "Config pin missing")
    need(counters.get("updates") == 72, "Checkpoint must preserve D2 update count")
    return {"version": "teacher_checkpoint_v1", "resume_mode": "fresh_env", "tag": "candidate",
            "identity": identity, "identity_sha256": identity_sha256,
            "schema": "d2_training_v3_checkpoint_v1", "phase": "D2",
            "eligibility_status": "provisional_pending_parent_terminal_receipt",
            "registration_sha256": registration_sha256,
            "policy_sha256": registration["policy"]["sha256"],
            "runtime_sha256": registration["runtime_sha256"],
            "config_sha256": registration["pins"][registration["config_path"]],
            "inherited_counters": {"D1_updates": 32, "pilot_updates": 16, "updates": 48},
            "cumulative_counters": {"updates": 120},
            "native_sha256": registration["native"]["sha256"],
            "parent_sha256": PARENT_SHA, "model": model, "optimizer": optimizer, "rng": rng,
            "counters": counters, "run_seed": run_seed,
            "next_episode_indices": next_episode_indices,
            "abandoned_current_episodes": abandoned_current_episodes,
            "update_progress": update_progress, "complete_update_boundary": True,
            "cumulative_wall_seconds": cumulative_wall_seconds}


def validate_synthetic_iteration(metrics, evaluations, worker):
    need(worker.get("status") == "completed" and worker.get("updates") == 72, "Iteration incomplete")
    need(type(worker.get("elapsed_seconds")) in (int, float)
         and 0 <= worker["elapsed_seconds"] <= LIMITS["work_seconds"]
         and type(worker.get("peak_rss_bytes")) is int
         and worker["peak_rss_bytes"] <= LIMITS["RSS_bytes"]
         and type(worker.get("peak_mps_driver_bytes")) is int
         and worker["peak_mps_driver_bytes"] <= LIMITS["MPS_bytes"]
         and worker.get("first_failure") is None and worker.get("first_signal") is None,
         "Worker resource, time, or failure receipt differs")
    need([r.get("phase_update") for r in metrics] == list(range(1, 73)), "Update journal incomplete")
    need([r.get("phase_update") for r in evaluations] == list(EVAL_UPDATES), "Evaluation schedule incomplete")
    optimizer_steps = 0
    raw_frames = 0
    for update, row in enumerate(metrics, 1):
        value = row.get("metrics")
        counters = row.get("counters")
        progress = row.get("update_progress")
        need(isinstance(value, Mapping) and isinstance(counters, Mapping) and isinstance(progress, Mapping),
             "Update record fields missing")
        need(value.get("transitions") == 16384 and type(value.get("optimizer_steps")) is int
             and 0 < value["optimizer_steps"] <= 128, "Update rollout/optimizer counts differ")
        need(counters.get("updates") == update and counters.get("environment_decisions") == update * 16384
             and counters.get("optimizer_steps") == optimizer_steps + value["optimizer_steps"]
             and type(counters.get("raw_frames")) is int and counters["raw_frames"] >= raw_frames,
             "Cumulative counters or seed carry differ")
        need(progress.get("complete") is True and progress.get("in_update") is False,
             "Update boundary is incomplete")
        optimizer_steps = counters["optimizer_steps"]
        raw_frames = counters["raw_frames"]
    progress = []
    for record in evaluations:
        summary = record["summary"]
        rows = summary.get("rows")
        need(summary.get("stage") == "D2" and summary.get("episodes") == 64
             and summary.get("complete") is True and isinstance(rows, list) and len(rows) == 64,
             "Evaluation summary is incomplete")
        need([row.get("seed") for row in rows] == list(range(0xD0000000, 0xD0000040)),
             "Evaluation seed cohort differs")
        need(summary.get("mean_alive_frames") == sum(r["alive_frames"] for r in rows) / 64
             and summary.get("mean_score") == sum(r["score"] for r in rows) / 64,
             "Evaluation mean differs from rows")
        expected_performance = {}
        for metric, field in (("alive_frames", "alive_frames"), ("score", "score")):
            values = sorted(r[field] for r in rows)
            expected_performance[metric] = {"Q1": sum(values[:16]) / 16,
                "Q4": sum(values[-16:]) / 16, "mean": sum(values) / 64}
        need(record.get("performance") == expected_performance, "Independent Q1/Q4 performance summary differs")
        need(record.get("checkpoint") == f"checkpoint-{record['phase_update']:06d}-candidate.pt"
             and isinstance(record.get("checkpoint_sha256"), str)
             and len(record["checkpoint_sha256"]) == 64,
             "Evaluation checkpoint identity or eligibility differs")
        passed = v3_progress_passed(summary)
        progress.append({"phase_update": record["phase_update"], "progress_passed": passed,
                         "competence_passed": summary["mean_alive_frames"] >= 3060})
    need(worker.get("raw_exit") == 0 and worker.get("cancelled") is False, "Terminal worker evidence failed")
    need(worker.get("counters") == metrics[-1]["counters"], "Final worker counters differ from update journal")
    return {"completed_training_iteration": True,
            "competence_passed": progress[-1]["competence_passed"],
            "progress_passed": progress[-1]["progress_passed"], "evaluations": progress}


def validate_episode_journal(records):
    need(isinstance(records, list) and records and records[0].get("kind") == "initial",
         "Episode journal initial record missing")
    current = {}
    for info in records[0]["info"]:
        seed = info["seed"]
        need(seed["episode"] == 0 and type(seed["slot"]) is int and seed["slot"] not in current,
             "Initial episode index or slot differs")
        current[seed["slot"]] = 0
    need(sorted(current) == list(range(64)) and
         records[0].get("batch_info", {}).get("initial_episode_indices") == [0] * 64 and
         records[0].get("batch_info", {}).get("next_episode_indices") == [1] * 64,
         "Initial 64-slot episode seed state differs")
    last_update = 0
    for record in records[1:]:
        update = record.get("phase_update")
        need(type(update) is int and last_update <= update <= 72, "Episode telemetry phase_update differs")
        last_update = update
        kind = record["kind"]
        if kind == "completed":
            info = record["info"]
            seed = info["seed"]
            need(seed["episode"] == current.get(seed["slot"]), "Completed episode seed index skipped or replayed")
            current[seed["slot"]] += 1
        elif kind == "reset":
            infos = record["info"]
            need(len(infos) == len(record["indices"]), "Reset episode telemetry count differs")
            for slot, info in zip(record["indices"], infos, strict=True):
                seed = info["seed"]
                need(seed["slot"] == slot and seed["episode"] == current.get(slot, -2),
                     "Episode seed carry skipped or replayed")
        else:
            need(False, "Unknown episode journal record kind")
    return {"records": len(records), "slots": len(current), "final_episode_indices": current}
