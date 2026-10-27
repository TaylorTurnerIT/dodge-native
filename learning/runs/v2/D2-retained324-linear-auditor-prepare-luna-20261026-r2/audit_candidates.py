"""Independent read-only auditor for the frozen retained324 linear-LR run (324 -> 384, local 0..60).

Loads the frozen runner through its own registration preflight, so the frozen launcher's
validate_outputs() sees the same runner module. Prefix mode audits published candidates only.
Full mode needs all six certificates, terminal outputs, and a parent-owned observer record.
The run restores selected324 model, Adam, and RNG exactly at entry LR 3e-5, then verifies every scheduled LR.
Nothing grants selection, continuation, or terminal acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import types
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
PREP = ROOT / "learning/runs/v2/D2-retained324-linear-integrated-luna-20261026-r4"
RUN = ROOT / "learning/runs/v2/D2-retained324-linear-lr-20261026-r1"
PARENT_RUN = ROOT / "learning/runs/v2/D2-retained300-continuation-20261026-r1"
PARENT_AUDIT = ROOT / "learning/runs/v2/D2-retained300-parent-terminal-audit-20261026-r1"
OBSERVER_DIR = None
OBSERVER_SOURCE = None
OBSERVER_SHA = None
OBSERVER_INSTANTIATION_SHA = "56d547b6ccd96df759740d1573fc1de44319094fe0d3ff8296ae75aa3dbbf166"
OBSERVER_INSTANTIATION_PATH = ROOT / "learning/runs/v2/D2-retained324-linear-execution-observer-parent-20261026-r1/instantiation.json"
VENV_SITE = ROOT / "python/.venv/lib/python3.12/site-packages"

REG_PATH = PREP / "registration-final-r2.json"
REGISTRATION_SHA256 = "0a6bf98221689ffcf62a28289dae7bb98eb89bc8d3c02b93127f4a04df75cb4e"
REG_SHA = REGISTRATION_SHA256
RUNNER_SHA = "e80fba02fbef45564d9937cc9eb59bfe1a988040233a41f5bb417e26ed70019f"
REGISTRATION_SCHEMA_SHA = "ed21c10e4c148b995e62784d0bc2c8a1af33d7ab404bcd6b7d8dbf68c02e782f"
PARENT_ADAPTER_SHA = "8091c8e90d86404ff96c7272d403e9ad8d3c3a8f9d767b42acfce13a8ccb692d"
LAUNCHER_SHA = "6b27b5702e050ba1899078a80c4909ff89cd12a72abcff0ff5dcc7006d679728"
LAUNCHER_PATH = PREP / "execute_once.py"
CONFIG_SHA = "1c24df3eea150160451ada08e9f6844cd67645abf5fb8b712afd14abca930ce8"
POLICY_SHA = "bfcbee1609cec0180495c957cf4b5e0b31356f395e2a706217cc9225647d23ae"
NEW_NATIVE_SHA = "022d41dde9bace0b4f4c4c06b9b4ed007bc2c60013cd98734086e587d7bb997e"
PARENT_SHA = "c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc"
PARENT_RECEIPT_SHA = "76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08"
PARENT_REGISTRATION_SHA = "8a60dc80f1ebe03c43bf18eebf75199e14f207b677570ac2d6d4368ddfcb0f79"
PARENT_CONFIG_SHA = "1c24df3eea150160451ada08e9f6844cd67645abf5fb8b712afd14abca930ce8"
PARENT_RUN_ID = "D2-retained300-continuation-20261026-r1"
PARENT_EVAL_JSON_SHA = "73f9ee722b445ae8e2baf2b16fcb40744338323ec17efe35a56e703947a35e64"
PARENT_EVAL_JSONL_SHA = "8777375952d4c656ff805f8c08da30d62e8185cdea5f63e3f0e98f542ff23215"
RUN_ID = "D2-retained324-linear-lr-20261026-r1"
RUN_SEED = 4200000001
PHASE_START, PHASE_END = 324, 384
UPDATES = tuple(range(PHASE_START, PHASE_END + 1, 12))
NEW_UPDATES = 60
PARENT_TOTAL_UPDATES = 372
MAX_OPTIMIZER_STEPS = 7680
MAX_ENVIRONMENT_DECISIONS = 983040
DECISIONS_PER_UPDATE = 16384
SELECTED_TRAJECTORY_BASELINE = 5678.9823631240915
ORIGINAL_PRODUCING_CAMPAIGN_COST = 9758.365427209174
CAMPAIGN_COST_BASELINE = 10824.835578584221
CAMPAIGN_COST_BASELINE_SHA = "d3ddc427f18c8a88c45439452c9efcd966daefe423222e0fa03e97ff4f4fc7d3"
ORIGINAL_PRODUCING_CAMPAIGN_COST_SHA = "7c6f250b5c5aa9e4098603cc8772c532a713e65f478cbda6ebfdd3941692fc9b"
BASELINE_MEAN_ALIVE = 2939.40625
BASELINE_PERFORMANCE = {'alive_frames': {'Q1': 767.5, 'Q4': 5468.6875, 'mean': 2939.40625}, 'score': {'Q1': 4.09375, 'Q4': 61.53125, 'mean': 29.53125}}
BASELINE_DEATH_CAUSES = {'kamikaze_enemy': 9, 'kamikaze_explosion': 3, 'moving_pattern_rect': 3, 'normal_enemy': 35, 'static_pattern_rect': 14}
SEED_COHORT = tuple(range(0xD0000000, 0xD0000040))
ENTRY_ZERO = {"updates": 0, "optimizer_steps": 0, "environment_decisions": 0, "raw_frames": 0}
EXACT_DODGE = {"dodge_rl": "dodge_rl/__init__.py", "dodge_rl.checkpoints": "dodge_rl/checkpoints.py",
               "dodge_rl.survival_gate": "dodge_rl/survival_gate.py", "dodge_rl.identity": "dodge_rl/identity.py",
               "dodge_rl._native": "dodge_rl/_native.cpython-312-darwin.so"}
AUTHORITY = {"selection": False, "best_replacement": False, "continuation": False, "terminal_acceptance": False}
schedule_contract = None
lr_schedule = None
BINDING_SHA = None


class AuditError(ValueError):
    pass


def check(condition, message):
    if not condition:
        raise AuditError(message)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def read_stable(path):
    """Immutable file: two reads must match before the bytes are trusted."""
    first = Path(path).read_bytes()
    check(first == Path(path).read_bytes(), f"Input changed while reading: {Path(path).name}")
    return first


def sha_file(path):
    return sha_bytes(read_stable(path))


def stable_json(path):
    raw = read_stable(path)
    return json.loads(raw), sha_bytes(raw)


def validate_actual_package(registration, registration_sha256):
    """Check source-manifest contracts for the exact frozen integrated package."""
    check(registration_sha256 == REGISTRATION_SHA256, "Actual registration digest differs")
    manifest, _ = stable_json(PREP / "source-manifest.json")
    check(manifest.get("schema") == "d2_retained324_linear_integrated_source_manifest_v1"
          and manifest.get("run_id") == RUN_ID
          and manifest.get("controls", {}).get("final_registration") == REG_PATH.name
          and manifest.get("artifacts", {}).get(REG_PATH.name) == REGISTRATION_SHA256,
          "Actual source-manifest registration contract differs")
    checks = {
        "runner.py": "e80fba02fbef45564d9937cc9eb59bfe1a988040233a41f5bb417e26ed70019f",
        "execute_once.py": "6b27b5702e050ba1899078a80c4909ff89cd12a72abcff0ff5dcc7006d679728",
        "lr_schedule.py": "ef81e87580c39e6f733098a5c228e4660af03e7fccddcc06044e9d3612bce079",
        "registration_schema.py": "ed21c10e4c148b995e62784d0bc2c8a1af33d7ab404bcd6b7d8dbf68c02e782f",
        "parent_adapter.py": "8091c8e90d86404ff96c7272d403e9ad8d3c3a8f9d767b42acfce13a8ccb692d",
    }
    for name, digest in checks.items():
        path = PREP / name
        check(sha_file(path) == digest and registration.get("pins", {}).get(str(path.resolve())) == digest,
              f"Actual package source pin differs: {name}")
    check(registration.get("run_id") == RUN_ID
          and registration.get("schema") == "d2_retained324_linear_lr_registration_v1"
          and Path(registration.get("root", "")).resolve() == ROOT.resolve()
          and Path(registration.get("runner_path", "")).resolve() == (PREP / "runner.py").resolve()
          and Path(registration.get("launcher_path", "")).resolve() == (PREP / "execute_once.py").resolve()
          and Path(registration.get("registration_schema_path", "")).resolve()
          == (PREP / "registration_schema.py").resolve()
          and registration.get("runtime_sha256") == "2cf10e9f056f41b39dc17845192e9adf553a5f699546d4f5dcea764a23e36b31"
          and Path(registration.get("runtime_root", "")).resolve()
          == (ROOT / "learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime").resolve(),
          "Actual package root, runtime, paths, or schema differ")
    check(isinstance(registration.get("pins"), dict) and len(registration["pins"]) == 13857
          and registration.get("parent", {}).get("registration_sha256") == PARENT_REGISTRATION_SHA,
          "Actual registration pin inventory or parent registration differs")
    check(registration.get("config_sha256") == CONFIG_SHA
          and registration.get("parent", {}).get("sha256") == PARENT_SHA
          and registration.get("parent", {}).get("terminal_receipt_sha256") == PARENT_RECEIPT_SHA
          and registration.get("native", {}).get("sha256") == NEW_NATIVE_SHA,
          "Actual config, selected parent, terminal receipt, or native differs from independent pins")
    anchor = registration.get("latest_resource_cost_anchor", {})
    check(anchor.get("sha256") == CAMPAIGN_COST_BASELINE_SHA
          and registration.get("parent", {}).get("completed_cost_receipt_sha256")
          == ORIGINAL_PRODUCING_CAMPAIGN_COST_SHA,
          "Actual resource-cost provenance differs")


def parse_journal(raw, *, strict):
    """Parse one already-read buffer. Prefix mode drops an incomplete tail; full mode rejects it."""
    if raw and not raw.endswith(b"\n"):
        check(not strict, "Journal tail incomplete in full mode")
        raw = raw[: raw.rfind(b"\n") + 1]
    return [json.loads(line) for line in raw.splitlines() if line], raw


def load_pinned_module(name, path, expected_sha):
    """Exec exact bytes already checked against the pinned digest; no import-path lookup."""
    path = Path(path).resolve(strict=True)
    source = path.read_bytes()
    check(sha_bytes(source) == expected_sha, f"Pinned source digest differs: {path.name}")
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(source, str(path), "exec", dont_inherit=True), module.__dict__)
    return module


def binding_digest(raw: bytes, expected: str) -> str:
    check(isinstance(expected, str) and len(expected) == 64
          and all(ch in "0123456789abcdef" for ch in expected),
          "Parent-supplied expected binding SHA-256 is required")
    actual = sha_bytes(raw)
    check(actual == expected, "Audit binding digest differs from parent-supplied digest")
    return actual


def load_bound_schedule_modules(source_pins):
    """Load both schedule modules by explicit OWN path and digest, never sys.path lookup."""
    global schedule_contract, lr_schedule
    lr_path = (OUT / "lr_schedule.py").resolve()
    contract_path = (OUT / "schedule_contract.py").resolve()
    check(source_pins.get(str(lr_path)) and source_pins.get(str(contract_path)),
          "Binding omits pinned schedule module sources")
    lr_schedule = load_pinned_module("lr_schedule", lr_path, source_pins[str(lr_path)])
    schedule_contract = load_pinned_module("schedule_contract", contract_path, source_pins[str(contract_path)])
    check(Path(lr_schedule.__file__).resolve() == lr_path
          and schedule_contract.lr_schedule is lr_schedule
          and Path(schedule_contract.__file__).resolve() == contract_path,
          "Pinned schedule module origins differ")
    return schedule_contract, lr_schedule


def bind_environment():
    """Interpreter, bytecode policy, and empty bytecode prefix before frozen imports."""
    check(sys.dont_write_bytecode and sys.flags.dont_write_bytecode, "Bytecode writing must be disabled (-B)")
    check(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 must be inherited")
    prefix = str(OUT / "empty-pycache")
    check(sys.pycache_prefix == prefix and os.environ.get("PYTHONPYCACHEPREFIX") == prefix,
          "Bytecode prefix differs from registration")
    check("PYTHONPATH" not in os.environ, "PYTHONPATH must be unset")
    check(Path(prefix).is_dir() and not any(Path(prefix).iterdir()), "Registered bytecode prefix is not empty")
    for name in ("runner", "execute_once_frozen", "dodge_rl"):
        check(name not in sys.modules, f"Module cache already contains {name}")


def load_frozen(*, expected_binding_sha256):
    """Frozen runner by exact bytes, then the live registration through its own preflight.
    """
    global REGISTRATION_SCHEMA_SHA, PARENT_ADAPTER_SHA, LAUNCHER_PATH
    global CONFIG_SHA, PARENT_SHA, PARENT_RECEIPT_SHA, NEW_NATIVE_SHA
    global OBSERVER_SHA, OBSERVER_SOURCE, OBSERVER_DIR, schedule_contract, lr_schedule, BINDING_SHA
    bind_environment()
    binding_path = OUT / "audit-binding.json"
    check(binding_path.is_file(), "Parent-generated exact audit binding is required")
    check(binding_path.resolve() == (OUT / "audit-binding.json").resolve(), "Binding path differs")
    binding_raw = read_stable(binding_path)
    binding_sha = binding_digest(binding_raw, expected_binding_sha256)
    binding = json.loads(binding_raw)
    BINDING_SHA = binding_sha
    check(binding.get("schema") == "d2_retained324_linear_auditor_binding_v1"
          and binding.get("run_id") == RUN_ID, "Audit binding identity differs")
    required_sources = {str((OUT / name).resolve()) for name in
                        ("audit_candidates.py", "wrapper.py", "binding_builder.py",
                         "schedule_contract.py", "lr_schedule.py")}
    check(set(binding.get("auditor_sources", {})) == required_sources,
          "OWN auditor source binding inventory differs")
    for path_text, digest in binding["auditor_sources"].items():
        check(Path(path_text).is_absolute() and sha_file(path_text) == digest,
              "OWN auditor source binding differs")
    schedule_contract, lr_schedule = load_bound_schedule_modules(binding["auditor_sources"])
    check(sha_file(binding["reviewed_manifest"]["path"]) == binding["reviewed_manifest"]["sha256"],
          "Reviewed manifest digest differs")
    OBSERVER_SOURCE = Path(binding["observer_source"]["path"])
    check(OBSERVER_SOURCE.is_absolute(), "Observer source path must be absolute")
    OBSERVER_SHA = binding["observer_source"]["sha256"]
    OBSERVER_DIR = OBSERVER_SOURCE.parent
    check(binding.get("observer_instantiation") == {
        "path": str(OBSERVER_INSTANTIATION_PATH.resolve()), "sha256": OBSERVER_INSTANTIATION_SHA},
        "Observer instantiation binding differs from immutable parent record")
    reg_raw = read_stable(REG_PATH)
    actual_registration_sha = sha_bytes(reg_raw)
    check(actual_registration_sha == REG_SHA, "Actual registration digest differs from independent auditor pin")
    check(actual_registration_sha == binding["registration"]["sha256"]
          and Path(binding["registration"]["path"]).resolve() == REG_PATH.resolve(),
          "Final registration binding differs")
    reg_preview = json.loads(reg_raw)
    validate_actual_package(reg_preview, REG_SHA)
    check(reg_preview.get("run_id") == RUN_ID
          and Path(reg_preview.get("runner_path", "")).resolve() == (PREP / "runner.py").resolve(),
          "Final registration runner path or run identity differs")
    pins = reg_preview.get("pins", {})
    def registered_sha(path):
        resolved = str(Path(path).resolve())
        digest = pins.get(resolved)
        check(isinstance(digest, str) and len(digest) == 64, f"Final registration omits source pin: {Path(path).name}")
        return digest
    schema_path = Path(reg_preview["registration_schema_path"]).resolve()
    check(schema_path == (PREP / "registration_schema.py").resolve(), "Registration schema path differs")
    check(reg_preview.get("registration_schema_sha256") == REGISTRATION_SCHEMA_SHA,
          "Registration schema digest differs from independent auditor pin")
    check(registered_sha(PREP / "runner.py") == RUNNER_SHA,
          "Registered runner differs from independent auditor pin")
    check(Path(reg_preview["parent_adapter_path"]).resolve() == (PREP / "parent_adapter.py").resolve()
          and registered_sha(PREP / "parent_adapter.py") == PARENT_ADAPTER_SHA,
          "Registered parent adapter differs from independent auditor pin")
    check(Path(reg_preview["launcher_path"]).resolve() == LAUNCHER_PATH.resolve()
          and registered_sha(LAUNCHER_PATH) == LAUNCHER_SHA,
          "Registered launcher differs from independent auditor pin")
    check(reg_preview.get("config_sha256") == CONFIG_SHA
          and reg_preview.get("parent", {}).get("sha256") == PARENT_SHA
          and reg_preview.get("parent", {}).get("terminal_receipt_sha256") == PARENT_RECEIPT_SHA
          and reg_preview.get("native", {}).get("sha256") == NEW_NATIVE_SHA
          and registered_sha(reg_preview["parent"]["terminal_receipt_path"]) == PARENT_RECEIPT_SHA,
          "Registration config, parent, receipt, or native differs from independent auditor pin")
    schema = load_pinned_module("registration_schema", schema_path, REGISTRATION_SCHEMA_SHA)
    check(Path(schema.__file__).resolve() == schema_path.resolve(), "Registration schema origin differs")
    check(schema.RUN_ID == RUN_ID, "Registration schema run identity differs")
    adapter = load_pinned_module("parent_adapter", PREP / "parent_adapter.py", PARENT_ADAPTER_SHA)
    check(Path(adapter.__file__).resolve() == (PREP / "parent_adapter.py").resolve(), "Parent adapter origin differs")
    runner = load_pinned_module("runner", PREP / "runner.py", RUNNER_SHA)
    check(Path(runner.__file__).resolve() == (PREP / "runner.py").resolve(), "Runner origin differs")
    runner.check_import_cache = lambda reg: check(
        os.environ.get("PYTHONPYCACHEPREFIX") == str(OUT / "empty-pycache")
        and sys.pycache_prefix == str(OUT / "empty-pycache")
        and sys.dont_write_bytecode and (OUT / "empty-pycache").is_dir()
        and not any((OUT / "empty-pycache").iterdir()),
        "Auditor-owned bytecode prefix differs or is not empty")
    reg, config = runner.load_registration(str(REG_PATH), REG_SHA)
    check(reg["run_id"] == runner.RUN_ID == RUN_ID == RUN.name, "Run identity differs")
    check(Path(reg["runner_path"]).resolve() == (PREP / "runner.py").resolve(), "Frozen runner origin differs")
    check(sha_file(LAUNCHER_PATH) == LAUNCHER_SHA and reg["config_sha256"] == CONFIG_SHA
          and reg["parent"]["sha256"] == PARENT_SHA and reg["native"]["sha256"] == NEW_NATIVE_SHA
          and sha_file(reg["parent"]["terminal_receipt_path"]) == PARENT_RECEIPT_SHA, "Critical pin differs")
    return runner, reg, config


def import_runtime(reg):
    runtime = Path(reg["runtime_root"]).resolve()
    sys.path.insert(0, str(runtime))
    import dodge_rl
    from dodge_rl import checkpoints, survival_gate
    from dodge_rl.identity import identity_hash
    import dodge_rl._native  # noqa: F401  binds the current native origin for the origin check
    runtime_origins(reg, runtime, sys.modules)
    return checkpoints, survival_gate, identity_hash


def runtime_origins(reg, runtime, modules):
    """Every loaded dodge_rl module is a pinned runtime member; exact origins and current native."""
    members = reg["runtime_continuity"]["member_sha256"]
    origins = {}
    for name, module in sorted(modules.items()):
        if not (name == "dodge_rl" or name.startswith("dodge_rl.")):
            continue
        path = Path(getattr(module, "__file__", "") or "").resolve()
        check(path.is_relative_to(runtime), f"Dodge module outside runtime root: {name}")
        relative = path.relative_to(runtime).as_posix()
        check(relative in members and sha_file(path) == members[relative] == reg["pins"].get(str(path)),
              f"Dodge module not a pinned runtime member: {name}")
        origins[name] = {"path": str(path), "sha256": members[relative]}
    for name, relative in EXACT_DODGE.items():
        check(name in origins and origins[name]["path"] == str((runtime / relative).resolve()),
              f"Exact Dodge origin differs or is missing: {name}")
    check(origins["dodge_rl._native"]["sha256"] == NEW_NATIVE_SHA, "Current native digest differs")
    check(sys.path[0] == str(runtime), "Runtime root is not the first import path entry")
    return origins


def expected_outputs():
    names = ["entry-restoration.json", "launch-marker.json", "worker-launch.json",
             "worker-result.json", "worker.log", "resources.jsonl", "training-episodes.jsonl", "training-metrics.jsonl"]
    for update in UPDATES:
        names += [f"checkpoint-{update:06d}-candidate.pt", f"checkpoint-{update:06d}-candidate.pt.json",
                  f"development-{update:06d}.json", f"development-{update:06d}.jsonl"]
    return names


def finite_tensors(value):
    """Every floating tensor in a nested state tree is finite."""
    if isinstance(value, dict):
        for item in value.values():
            finite_tensors(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            finite_tensors(item)
    elif hasattr(value, "is_floating_point") and value.is_floating_point():
        check(bool(value.isfinite().all()), "Nonfinite tensor in checkpoint state")


def expected_candidate_paths(update):
    cp = RUN / f"checkpoint-{update:06d}-candidate.pt"
    return {"checkpoint": cp, "sidecar": Path(str(cp) + ".json"),
            "certificate": RUN / f"development-{update:06d}.json", "rows": RUN / f"development-{update:06d}.jsonl"}


def published_updates():
    done = []
    for update in UPDATES:
        if not all(p.is_file() for p in expected_candidate_paths(update).values()):
            break
        done.append(update)
    return done


def check_saved_lr(state, local_update):
    """Bind every candidate optimizer LR to exact inherited + local schedule progress."""
    inherited_counters = state.get("inherited_counters")
    cumulative_counters = state.get("cumulative_counters")
    check(isinstance(inherited_counters, dict) and isinstance(cumulative_counters, dict),
          "Checkpoint inherited or cumulative counters missing or invalid")
    inherited = inherited_counters.get("updates")
    cumulative = cumulative_counters.get("updates")
    try:
        schedule_contract.validate_checkpoint_schedule(
            state, inherited_updates=inherited, local_updates=local_update,
            cumulative_updates=cumulative)
    except (KeyError, TypeError, ValueError) as exc:
        raise AuditError(str(exc)) from exc


def validate_metric_rows(runner, metrics, max_local, group_count):
    check(len(metrics) >= max_local, "Metric/gradient coverage shorter than candidate prefix")
    """Per-update rows in the consumed prefix: contiguous phases, exact counter chain, finite values."""
    check([row.get("phase_update") for row in metrics] == list(range(PHASE_START + 1, PHASE_START + 1 + len(metrics))),
          "Metric rows are not a contiguous update prefix")
    check(len(metrics) >= max_local, "Metric/gradient coverage shorter than candidate prefix")
    steps = 0
    for local, row in enumerate(metrics[:max_local], 1):
        value = row["metrics"]
        runner.finite_tree(value)
        check(0 < value["optimizer_steps"] <= 128 and value["transitions"] == DECISIONS_PER_UPDATE,
              "Optimizer or rollout counts differ")
        steps += value["optimizer_steps"]
        progress = row["update_progress"]
        check(row["local_update"] == local and row["counters"]["updates"] == local
              and row["counters"]["optimizer_steps"] == steps
              and row["counters"]["environment_decisions"] == local * DECISIONS_PER_UPDATE
              and progress["completed_updates"] == local and progress["complete"] is True
              and progress["in_update"] is False, f"Metric counter chain differs at local {local}")
        runner.validate_gradient_alignment(value.get("gradient_alignment_diagnostics"))
        try:
            schedule_contract.validate_metric_schedule(
                row, inherited_updates=PARENT_TOTAL_UPDATES, local_update=local,
                group_count=group_count)
        except (KeyError, TypeError, ValueError) as exc:
            raise AuditError(str(exc)) from exc
    if max_local == schedule_contract.HORIZON:
        check(len(metrics) == schedule_contract.HORIZON,
              "Full schedule audit requires exactly 60 metric rows")
        try:
            schedule_contract.validate_progression(metrics, group_count=group_count)
        except (KeyError, TypeError, ValueError) as exc:
            raise AuditError(str(exc)) from exc
    return steps


def prefix_steps_through(metrics, local):
    return sum(row["metrics"]["optimizer_steps"] for row in metrics[:local])


def validate_state_identity(ctx, update, state):
    runner, reg, parent = ctx["runner"], ctx["reg"], ctx["parent"]
    local = update - PHASE_START
    check(state.get("schema") == "d2_training_v3_checkpoint_v1" and state.get("tag") == "candidate"
          and state.get("version") == "teacher_checkpoint_v1" and state.get("resume_mode") == "fresh_env",
          "Candidate schema, tag, or resume mode differs")
    check(state.get("eligibility_status") == "provisional_pending_parent_terminal_receipt"
          and state.get("training_eligible") is False and state.get("promoted") is False,
          "Candidate eligibility differs")
    check(state.get("phase") == "D2" and state.get("phase_update") == update and state.get("local_update") == local,
          "Candidate phase/local update differs")
    check(state.get("registration_sha256") == REG_SHA and state.get("config_sha256") == CONFIG_SHA
          and state.get("policy_sha256") == POLICY_SHA and state.get("native_sha256") == NEW_NATIVE_SHA
          and state.get("runtime_sha256") == reg["runtime_sha256"] and type(state.get("run_seed")) is int
          and state["run_seed"] == RUN_SEED, "Candidate registration/config/policy/native/runtime/seed differs")
    check(state.get("parent_sha256") == PARENT_SHA and state.get("parent_checkpoint_sha256") == PARENT_SHA
          and state.get("parent_registration_sha256") == PARENT_REGISTRATION_SHA
          and state.get("parent_run_id") == PARENT_RUN_ID, "Candidate parent identity differs")
    ident = state.get("identity")
    check(isinstance(ident, dict) and state.get("identity_sha256") == ctx["identity_hash"](ident), "Identity hash differs")
    check(ident.get("version") == "teacher_identity_v3" and ident.get("run_id") == RUN_ID
          and ident.get("phase") == "D2" and ident.get("phase_update_start") == PHASE_START
          and ident.get("phase_update_end") == PHASE_END and ident.get("run_seed") == RUN_SEED
          and ident.get("registration_sha256") == REG_SHA and ident.get("parent_checkpoint_sha256") == PARENT_SHA
          and ident.get("parent_terminal_receipt_sha256") == PARENT_RECEIPT_SHA
          and ident.get("parent_config_sha256") == PARENT_CONFIG_SHA
          and ident.get("policy_sha256") == POLICY_SHA
          and ident.get("lr_schedule") == schedule_contract.lr_schedule.SCHEDULE_SPEC
          and ident.get("lr_schedule_spec_sha256") == schedule_contract.lr_schedule.SCHEDULE_SPEC_SHA256
          and ident.get("config") == ctx["config"] and ident.get("architecture") == parent["identity"]["architecture"],
          "Embedded identity, config, or architecture differs")
    progress = state.get("update_progress")
    check(type(progress) is dict and progress.get("complete") is True and progress.get("in_update") is False
          and progress.get("completed_updates") == local, "Update progress differs")
    check(state.get("inherited_counters") == parent["cumulative_counters"]
          and state.get("parent_abandoned_current_episodes") == parent["abandoned_current_episodes"],
          "Inherited counters or parent abandoned records differ")
    counters = state.get("counters")
    check(type(counters) is dict and all(type(v) is int for v in counters.values()), "Counter types differ")
    if update == PHASE_START:
        check(counters == ENTRY_ZERO and local == 0, "Entry candidate must carry zero local counters")
        check(PHASE_START not in ctx["rows_by_phase"], "Entry candidate has a metric row")
    else:
        rows = ctx["rows_by_phase"].get(update, [])
        check(len(rows) == 1, f"Candidate metric row count differs at {update}")
        row = rows[0]
        check(row["local_update"] == local and row["counters"] == counters and row["update_progress"] == progress,
              "Candidate counters or progress do not match its metric row")
        check(counters["updates"] == local and counters["environment_decisions"] == local * DECISIONS_PER_UPDATE
              and counters["optimizer_steps"] == prefix_steps_through(ctx["metrics"], local),
              "Local counters differ from metric chain")
    cumulative = runner.continuation_cumulative_counters(parent["cumulative_counters"], counters)
    check(state.get("cumulative_counters") == cumulative and cumulative["updates"] == PARENT_TOTAL_UPDATES + local,
          "Cumulative counter base differs from selected324 parent cumulative counters")
    validate_wall(state, local)


def validate_wall(state, local):
    cur = state.get("current_iteration_observed_outer_seconds")
    check(isinstance(cur, (int, float)) and math.isfinite(cur) and 0 < cur < 1800, "Current-iteration wall out of range")
    traj = state.get("cumulative_selected_checkpoint_trajectory_wall_seconds")
    cost = state.get("cumulative_successful_ancestor_and_completed_campaign_cost_seconds")
    check(all(isinstance(v, (int, float)) and math.isfinite(v) for v in (traj, cost)), "Wall fields not finite")
    check(math.isclose(traj, SELECTED_TRAJECTORY_BASELINE + cur, rel_tol=0, abs_tol=1e-6)
          and math.isclose(cost, CAMPAIGN_COST_BASELINE + cur, rel_tol=0, abs_tol=1e-6), "Wall formula differs")
    check(state.get("selected_parent_checkpoint_trajectory_baseline_seconds") == SELECTED_TRAJECTORY_BASELINE
          and state.get("parent_completed_campaign_cost_baseline_seconds") == CAMPAIGN_COST_BASELINE,
          "Wall baselines differ")


def validate_resume(ctx, update, state):
    """Next indices, abandoned records, journal prefix, and raw-frame conservation."""
    runner, parent, records = ctx["runner"], ctx["parent"], ctx["journal"]
    nxt = state.get("next_episode_indices")
    check(type(nxt) is list and len(nxt) == 64 and all(type(x) is int and 0 <= x < 2 ** 64 for x in nxt),
          "Resume next indices must be 64 typed u64 values")
    abandoned = state.get("abandoned_current_episodes")
    check(type(abandoned) is list and len(abandoned) == 64 and all(type(item) is dict for item in abandoned)
          and sorted(item["slot"] for item in abandoned) == list(range(64)), "Resume abandoned records must cover 64 slots once")
    for item in abandoned:
        seed = item["seed"]
        check(type(seed) is dict and type(seed["slot"]) is int and type(seed["episode"]) is int
              and seed["slot"] == item["slot"] and seed["episode"] + 1 == nxt[item["slot"]],
              "Abandoned seed lineage differs from next indices")
        check(type(item["gameplay_frames"]) is int and 0 <= item["gameplay_frames"] < 18000, "Abandoned frames outside cap")
    prefix = [row for row in records if row["kind"] in ("initial", "abandoned_parent_episode")
              or (row["kind"] in ("completed", "reset") and row["phase_update"] <= update)]
    episode = runner.validate_episode_journal(prefix, parent["next_episode_indices"])
    check(episode["next_episode_indices"] == nxt, "Resume next indices differ from validated journal prefix")
    check(episode["current_episode_indices"] == {item["slot"]: item["seed"]["episode"] for item in abandoned},
          "Abandoned current episode indices differ from validated journal prefix")
    inherited = [row for row in prefix if row["kind"] == "abandoned_parent_episode"]
    check(len(inherited) == 64 and sorted(row["info"]["slot"] for row in inherited) == list(range(64))
          and sorted((row["info"] for row in inherited), key=lambda x: x["slot"])
          == sorted(parent["abandoned_current_episodes"], key=lambda x: x["slot"])
          and all(row["reason"] == "fresh_environment_at_saved_next_episode_index"
                  and row["parent_checkpoint_sha256"] == PARENT_SHA for row in inherited),
          "Accepted parent abandoned records not preserved exactly")
    completed = sum(row["info"]["gameplay_frames"] for row in prefix if row["kind"] == "completed")
    check(completed + sum(item["gameplay_frames"] for item in abandoned) == state["counters"]["raw_frames"],
          "Raw-frame conservation differs (excluding parent abandoned)")


def validate_observer_instantiation(record):
    check(record.get("schema") == "retained324_linear_lr_observer_instantiation_v1"
          and record.get("observer_sha256") == OBSERVER_SHA
          and record.get("registration_sha256") == REG_SHA
          and record.get("run_id") == RUN_ID
          and record.get("actual_launches") == 0 and record.get("one_shot_marker_absent") is True,
          "Observer instantiation identity or no-launch declaration differs")
    return True


def validate_certificate(ctx, update, cert, side, rows_list, cp_name, cp_hash):
    runner, survival_gate = ctx["runner"], ctx["survival_gate"]
    local = update - PHASE_START
    check(cert.get("checkpoint") == cp_name and cert.get("checkpoint_sha256") == cp_hash
          and side.get("checkpoint_sha256") == cp_hash, "Certificate or sidecar checkpoint binding differs")
    check(cert.get("phase_update") == update and cert.get("local_update") == local
          and cert.get("normal_training_iteration") is True and cert.get("training_eligible") is False
          and cert.get("promoted") is False and cert.get("training_state_unchanged") is True,
          "Certificate phase, local, or eligibility flags differ")
    check(side.get("eligibility_status") == "provisional_pending_parent_terminal_receipt"
          and side.get("training_eligible") is False and side.get("promoted") is False, "Sidecar flags differ")
    ev = cert["evaluation"]
    check(type(ev) is dict and ev.get("complete") is True, "Evaluation incomplete")
    rows = ev["rows"]
    check(type(rows) is list and len(rows) == 64 and sorted(r["seed"] for r in rows) == list(SEED_COHORT),
          "Development cohort differs from the registered 64 seeds")
    check(sorted(rows, key=lambda r: r["seed"]) == sorted(rows_list, key=lambda r: r["seed"]),
          "JSONL rows differ from certificate rows")
    causes = Counter()
    for item in rows:
        check(type(item["terminated"]) is bool and type(item["truncated"]) is bool
              and item["terminated"] != item["truncated"], "Episode boundary flags differ")
        for key in ("alive_frames", "score", "objective_return"):
            check(type(item[key]) in (int, float) and math.isfinite(item[key]), f"Evaluation {key} not finite")
        check(math.isclose(item["objective_return"], item["score"] + .01 * item["alive_frames"]
                           - (5 if item["terminated"] else 0), rel_tol=0, abs_tol=1e-9), "Objective formula differs")
        if item["terminated"]:
            causes[item["death_cause"]] += 1
    deaths = sum(item["terminated"] for item in rows)
    caps = sum(item["truncated"] for item in rows)
    check(type(ev["deaths"]) is int and ev["deaths"] == deaths and type(ev["caps"]) is int and ev["caps"] == caps
          and deaths + caps == 64, "Boundary counts differ")
    check({k: v for k, v in ev["death_causes"].items() if v} == dict(causes), "Death-cause aggregate differs")
    mean_alive = sum(item["alive_frames"] for item in rows) / 64
    mean_score = sum(item["score"] for item in rows) / 64
    check(math.isclose(ev["mean_alive_frames"], mean_alive, rel_tol=0, abs_tol=1e-9)
          and math.isclose(ev["mean_score"], mean_score, rel_tol=0, abs_tol=1e-9), "Certificate means differ")
    check(cert.get("performance") == runner.performance(ev), "Certificate performance differs")
    # Informational survival-gate flag: recorded by the frozen runner, never a selection gate.
    competence = cert.get("competence_passed")
    check(type(competence) is bool and competence == survival_gate.progress_passed("D2", {"D2": ev}),
          "Recorded competence flag differs from the pinned survival gate")
    return {"mean_alive_frames": ev["mean_alive_frames"], "mean_score": ev["mean_score"],
            "performance": cert["performance"], "competence_passed": competence, "deaths": deaths, "caps": caps}


def validate_entry_against_parent(cert, rows_list):
    """Entry 324 rows and means equal the selected parent 324 evaluation (JSON and JSONL)."""
    base_path = PARENT_RUN / "development-000324.json"
    base, base_sha = stable_json(base_path)
    check(base_sha == PARENT_EVAL_JSON_SHA, "Selected324 JSON digest differs")
    check(sha_file(PARENT_RUN / "development-000324.jsonl") == PARENT_EVAL_JSONL_SHA, "Selected324 JSONL digest differs")
    base_rows = base["evaluation"]["rows"]
    check(sorted(cert["evaluation"]["rows"], key=lambda r: r["seed"]) == sorted(base_rows, key=lambda r: r["seed"]),
          "Entry324 certificate rows differ from selected parent JSON")
    base_jsonl, _ = parse_journal(read_stable(PARENT_RUN / "development-000324.jsonl"), strict=True)
    check(sorted(rows_list, key=lambda r: r["seed"]) == sorted(base_jsonl, key=lambda r: r["seed"]),
          "Entry324 JSONL rows differ from selected parent JSONL")
    mean = sum(r["alive_frames"] for r in base_rows) / 64
    check(mean == BASELINE_MEAN_ALIVE and base["performance"] == BASELINE_PERFORMANCE,
          "Selected324 baseline performance differs")
    check(base["evaluation"]["deaths"] == 64 and base["evaluation"]["caps"] == 0
          and {k: v for k, v in base["evaluation"]["death_causes"].items() if v} == BASELINE_DEATH_CAUSES,
          "Selected324 death accounting differs")


def validate_entry_state(ctx, state):
    """Entry preserves selected parent model, Adam, and RNG exactly."""
    runner, parent = ctx["runner"], ctx["parent"]
    check(runner.fingerprint(state["model"]) == runner.fingerprint(parent["model"])
          and runner.fingerprint(state["rng"]) == runner.fingerprint(parent["rng"]),
          "Entry model or RNG differs from selected324 parent")
    check(state.get("phase_update") == PHASE_START and state.get("local_update") == 0,
          "Entry candidate is not selected324")
    check(runner.fingerprint(state["optimizer"]) == runner.fingerprint(parent["optimizer"]),
          "Entry Adam state differs from selected324 parent")
    check_saved_lr(state, 0)


def audit_entry_restoration(ctx, entry_restoration):
    runner, parent = ctx["runner"], ctx["parent"]
    check(entry_restoration["matched"] == {"model": True, "Adam": True, "RNG": True}
          and entry_restoration["parent_sha256"] == PARENT_SHA, "Entry restoration did not match parent")
    expected = {"model": runner.fingerprint(parent["model"]), "Adam": runner.fingerprint(parent["optimizer"]),
                "RNG": runner.fingerprint(parent["rng"])}
    for name, digest in expected.items():
        component = entry_restoration["components"][name]
        check(component["expected_sha256"] == digest and component["restored_sha256"] == digest
              and component["matched"] is True, f"Entry restoration {name} digest differs")


def build_context(runner, reg, config, ckpt, survival_gate, identity_hash, journal, metrics):
    parent = ckpt.load_checkpoint(Path(reg["parent"]["path"]), expected_sha256=PARENT_SHA)
    ckpt.require_complete_update(parent)
    runner.validate_parent_checkpoint_for_restore(parent, PARENT_SHA, json.loads(read_stable(reg["parent"]["terminal_receipt_path"])))
    rows_by_phase = {}
    for row in metrics:
        rows_by_phase.setdefault(row["phase_update"], []).append(row)
    return {"runner": runner, "reg": reg, "config": config, "parent": parent, "ckpt": ckpt,
            "survival_gate": survival_gate, "identity_hash": identity_hash,
            "journal": journal, "metrics": metrics, "rows_by_phase": rows_by_phase}


def retained_best(means_in_order):
    """Chronological mean-survival best across entry324 and all continuation candidates."""
    best_update, best_mean = PHASE_START, BASELINE_MEAN_ALIVE
    for update, mean in means_in_order:
        if mean > best_mean:
            best_update, best_mean = update, mean
    return best_update


def choose_best(means):
    """Select maximum mean survival, including entry324; ties keep earlier update."""
    check(PHASE_START in means, "Selected324 entry mean missing")
    return max(means, key=lambda update: (means[update], -update))


def audit(*, provisional, expected_binding_sha256, observer_dir=None):
    runner, reg, config = load_frozen(expected_binding_sha256=expected_binding_sha256)
    ckpt, survival_gate, identity_hash = import_runtime(reg)
    tracked = {}
    journal_raw = read_stable(RUN / "training-episodes.jsonl")
    metrics_raw = read_stable(RUN / "training-metrics.jsonl")
    journal, journal_consumed = parse_journal(journal_raw, strict=not provisional)
    metrics, metrics_consumed = parse_journal(metrics_raw, strict=not provisional)

    published = published_updates()
    check(published and published[0] == PHASE_START, "Entry324 certificate is not published")
    if provisional:
        targets = tuple(published)
    else:
        check(tuple(published) == UPDATES, "Full mode requires all six published certificates")
        check(observer_dir is not None and Path(observer_dir).resolve() == OBSERVER_DIR.resolve(),
              "Full mode requires the exact registered parent-owned observer directory")
        check(sha_file(OBSERVER_SOURCE) == OBSERVER_SHA, "Registered observer source digest differs")
        observer = load_pinned_module("retained324_observer_source", OBSERVER_SOURCE, OBSERVER_SHA)
        check(observer.REG_SHA == REG_SHA, "Pinned observer source registration binding differs")
        instantiation_path = OBSERVER_INSTANTIATION_PATH
        instantiation, instantiation_sha = stable_json(instantiation_path)
        check(instantiation_sha == OBSERVER_INSTANTIATION_SHA
              and instantiation_path.resolve() == OBSERVER_INSTANTIATION_PATH.resolve(),
              "Observer instantiation digest or path differs")
        validate_observer_instantiation(instantiation)
        tracked[str(instantiation_path)] = instantiation_sha
        targets = UPDATES

    ctx = build_context(runner, reg, config, ckpt, survival_gate, identity_hash, journal, metrics)
    entry_path = RUN / "entry-restoration.json"
    entry_restoration, entry_sha = stable_json(entry_path)
    audit_entry_restoration(ctx, entry_restoration)
    tracked[str(entry_path)] = entry_sha
    parent_group_count = len(ctx["parent"]["optimizer"]["param_groups"])
    validate_metric_rows(runner, metrics, max(targets) - PHASE_START, parent_group_count)

    results, means = {}, {}
    for update in targets:
        paths = expected_candidate_paths(update)
        cp, cert_p, side_p, rows_p = paths["checkpoint"], paths["certificate"], paths["sidecar"], paths["rows"]
        cp_hash = sha_file(cp)
        cert, cert_hash = stable_json(cert_p)
        side, side_hash = stable_json(side_p)
        rows_list, rows_raw = parse_journal(read_stable(rows_p), strict=True)
        state = ckpt.load_checkpoint(cp, expected_sha256=cp_hash)
        ckpt.require_complete_update(state)
        check(sha_file(cp) == cp_hash, f"Checkpoint changed during audit: {cp.name}")
        validate_state_identity(ctx, update, state)
        validate_resume(ctx, update, state)
        finite_tensors(state["model"])
        finite_tensors(state["optimizer"])
        finite_tensors(state["rng"])
        component_fingerprints = {"model": runner.fingerprint(state["model"]),
                                  "Adam": runner.fingerprint(state["optimizer"]),
                                  "RNG": runner.fingerprint(state["rng"])}
        summary = validate_certificate(ctx, update, cert, side, rows_list, cp.name, cp_hash)
        check_saved_lr(state, update - PHASE_START)
        if update == PHASE_START:
            validate_entry_against_parent(cert, rows_list)
            validate_entry_state(ctx, state)
        means[update] = summary["mean_alive_frames"]
        results[str(update)] = {**summary, "checkpoint_sha256": cp_hash, "certificate_sha256": cert_hash,
                                "sidecar_sha256": side_hash, "rows_sha256": sha_bytes(rows_raw),
                                "component_fingerprints": component_fingerprints}
        for path, digest in ((cp, cp_hash), (cert_p, cert_hash), (side_p, side_hash), (rows_p, sha_bytes(rows_raw))):
            tracked[str(path)] = digest
        del state

    proposed = choose_best(means)
    retained = retained_best(sorted(means.items()))
    check(retained == proposed, "Chronological retained best differs from strict-max selection")
    result = {"schema": "retained324_linear_lr_all_candidate_audit_v1",
              "status": "readonly_published_prefix_provisional" if provisional else "all_candidates_audited_pending_parent_terminal_acceptance",
              "run_id": RUN_ID, "registration_sha256": REG_SHA, "binding_sha256": BINDING_SHA,
              "updates_audited": list(targets),
              "baseline_mean_alive_frames": BASELINE_MEAN_ALIVE, "proposed_best_update": proposed, "selection_basis": "mean_alive_frames_including_entry324_no_score_gate",
              "candidates": results, "schedule_spec": schedule_contract.lr_schedule.SCHEDULE_SPEC,
              "schedule_spec_sha256": schedule_contract.lr_schedule.SCHEDULE_SPEC_SHA256,
              "schedule_origin_cumulative_update": schedule_contract.ORIGIN,
              "schedule_horizon_updates": schedule_contract.HORIZON,
              "wall_anchors": {"selected_trajectory_seconds": SELECTED_TRAJECTORY_BASELINE,
                               "original_producing_campaign_cost_seconds": ORIGINAL_PRODUCING_CAMPAIGN_COST,
                               "latest_completed_campaign_cost_seconds": CAMPAIGN_COST_BASELINE,
                               "latest_completed_campaign_cost_receipt_sha256": CAMPAIGN_COST_BASELINE_SHA},
              "journal_prefix_policy": "initial+parent_abandoned+phase<=update",
              "journal_consumed_sha256": sha_bytes(journal_consumed), "metrics_consumed_sha256": sha_bytes(metrics_consumed),
              "authority": dict(AUTHORITY)}
    if not provisional:
        expected = expected_outputs()
        check(expected == reg["expected_outputs"], "Expected output inventory differs from registration")
        check("lr-transition.json" in reg["forbidden_outputs"] and not (RUN / "lr-transition.json").exists(), "Forbidden LR-transition output exists")
        check(tuple(published) == UPDATES, "Full mode requires all six published certificates")
        missing = [name for name in expected if not (RUN / name).is_file()]
        check(not missing, f"Terminal outputs missing: {missing[:3]}")
        execution_path = RUN / "execution-result.json"
        worker_path = RUN / "worker-result.json"
        execution, execution_sha = stable_json(execution_path)
        worker, worker_sha = stable_json(worker_path)
        tracked[str(execution_path)] = execution_sha
        tracked[str(worker_path)] = worker_sha
        check(execution.get("status") == "passed" and worker.get("status") == "completed", "Terminal status not successful")
        launcher = load_pinned_module("execute_once_frozen", LAUNCHER_PATH, LAUNCHER_SHA)
        check(launcher.r is runner, "Frozen launcher did not bind the audited runner")
        result["frozen_launcher_terminal_checks"] = launcher.validate_outputs(reg, worker, REG_SHA)
        observation_path = Path(observer_dir) / "observation.json"
        observation, observation_sha = stable_json(observation_path)
        tracked[str(observation_path)] = observation_sha
        check(observation["outer_raw_exit"] == 0 and observation["worker_raw_exit"] == 0, "Observer raw exits differ")
        check(observation.get("launch_count") == 1 and observation.get("first_event") is None
              and observation.get("outer_process_absent") is True and observation.get("worker_process_absent") is True
              and observation.get("worker_group_absent") is True, "Observer lifecycle/cleanup differs")
        check(type(observation.get("outer_process_group")) is int,
              "Observer outer process group is unknown or not typed")
        check(0 < observation.get("outer_inclusive_wall_seconds", 0) <= 1800
              and observation.get("max_aggregate_rss_bytes", 2**63) <= 6442450944, "Observer wall/resource cap differs")
        postflight = observation.get("postflight", {})
        lease = postflight.get("lease", {})
        check(observation.get("success_authoritative") is True
              and postflight.get("pins", {}).get("checked") == len(reg["pins"])
              and postflight.get("pins", {}).get("failures") == []
              and postflight.get("cache_empty_after") is True
              and postflight.get("publication_failure_absent") is True, "Observer pin/cache/publication postflight differs")
        check(lease.get("active_long_campaign_exact") is True
              and lease.get("active_inference_campaign") is None and lease.get("active_inference_lease") is None
              and lease.get("active_inference_diagnostic") is None, "Observer lease postflight differs")
        check(sha_file(OBSERVER_SOURCE) == OBSERVER_SHA, "Registered observer source changed during audit")
        result["terminal_record_sha256"] = {
            str(execution_path): execution_sha,
            str(worker_path): worker_sha,
            str(observation_path): observation_sha,
        }
        result["_terminal_records"] = {"execution": execution, "worker": worker,
                                       "observation": observation}

    # Append-only journals and published files must be unchanged after the audit.
    check(Path(RUN / "training-episodes.jsonl").read_bytes()[: len(journal_consumed)] == journal_consumed,
          "Consumed training-episode journal prefix changed during audit")
    check(Path(RUN / "training-metrics.jsonl").read_bytes()[: len(metrics_consumed)] == metrics_consumed,
          "Consumed training-metrics prefix changed during audit")
    for path, digest in tracked.items():
        check(sha_file(path) == digest, f"Audited file changed during audit: {Path(path).name}")
    check(sha_file(REG_PATH) == REG_SHA, "Registration changed during audit")
    runner.verify_pins(reg["pins"])
    check(not any((OUT / "empty-pycache").iterdir()), "Auditor-owned bytecode prefix gained files during audit")
    result["pins_checked_before_and_after"] = len(reg["pins"])
    result["parent_gated_checks"] = ["final publication absence", "lease release"]
    result["auditor_checked_terminal"] = ["frozen launcher outputs", "all candidate checkpoints and identity",
        "model/Adam/RNG entry restore", "candidate counters and episode resume", "schedule metadata and exact saved/metric per-group LR progression", "metric gradient coverage",
        "evaluation cohort rows/death causes/survival statistics", "observer exits/resources/cleanup/process absence",
        "source pins and cache"]
    result["tracked_file_sha256"] = dict(sorted(tracked.items()))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--provisional", action="store_true")
    parser.add_argument("--binding-sha256", required=True,
                        help="exact audit-binding.json digest supplied by the parent")
    args = parser.parse_args(argv)
    if not args.provisional:
        parser.error("full mode is parent-only; use the wrapper's explicit full_mode function")
    output = Path(args.output)
    check(output.parent.resolve() == OUT.resolve(), "Output must be in the auditor directory")
    result = audit(provisional=True, expected_binding_sha256=args.binding_sha256)
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
