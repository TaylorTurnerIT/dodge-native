"""Independent read-only auditor for the retained-276 continuation (276 -> 348, local 0..72).

Loads the frozen runner through its own registration preflight, so the frozen launcher's
validate_outputs() sees the same runner module. Prefix mode audits published candidates only.
Full mode needs all seven certificates, terminal outputs, and a parent-owned observer record.
No LR transition: the arm keeps LR 1e-4 from the parent. Nothing here grants selection,
continuation, or terminal acceptance.
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
PREP = ROOT / "learning/runs/v2/D2-retained276-continuation-prepare-luna-20261026-r2"
RUN = ROOT / "learning/runs/v2/D2-retained276-continuation-20261026-r2"
OBSERVER_DIR = ROOT / "learning/runs/v2/D2-retained276-continuation-execution-observer-luna-20261026-r2"
PARENT_RUN = ROOT / "learning/runs/v2/D2-retained204-lr1e4-20261026-r1"
PARENT_AUDIT = ROOT / "learning/runs/v2/D2-retained204-lr1e4-parent-terminal-audit-20261026-r1"
VENV_SITE = ROOT / "python/.venv/lib/python3.12/site-packages"

REG_PATH = PREP / "registration.json"
REG_SHA = "477217f3c7617ccbe01c651db8932eab01f54ea3924f213e67b413e640cf866c"
OBSERVER_SHA = "e3782f1c28c05548e995f3cb8c1a41b2a66f77b69d9455cada0be465f950ad95"
RUNNER_SHA = "db0bb3389ee5562bbb9cc1c550cdf64a077c7a1bf84a4f233df861867113a37b"
LAUNCHER_SHA = "6c1ed02b8b29e88491d6f5b7656bed43bfb40bfbb1c327c3ee1d57783e3c3554"
CONFIG_SHA = "f858a63c324fc312f794c0423aa56db2daf60793b62990cd51fa400afe3af628"
POLICY_SHA = "bfcbee1609cec0180495c957cf4b5e0b31356f395e2a706217cc9225647d23ae"
NEW_NATIVE_SHA = "022d41dde9bace0b4f4c4c06b9b4ed007bc2c60013cd98734086e587d7bb997e"
PARENT_SHA = "0b5cf72b4eb9629fa4f10ce2cecb3625b56f8787c0eca6395b9fe17161e6b292"
PARENT_RECEIPT_SHA = "d64d0f803d02a8d2c33da9fa0ba862f06ba7d9c56dcf4f0494e559a49e48fcc4"
PARENT_REGISTRATION_SHA = "68063348dede3050c4a8852c6314f4c95fd3a623e89c9499413f2325f4edad44"
PARENT_RUN_ID = "D2-retained204-lr1e4-20261026-r1"
PARENT_EVAL_JSON_SHA = "89454dba1753d5cb89eadc4339865780daadecdf78d7d040873e69e2c6d6e974"
PARENT_EVAL_JSONL_SHA = "2a3994d5503944318621695081e6482769ae69004d90f22f196ce57c6792eff0"
RUN_ID = "D2-retained276-continuation-20261026-r2"
RUN_SEED = 3791628419
PHASE_START, PHASE_END = 276, 348
UPDATES = tuple(range(PHASE_START, PHASE_END + 1, 12))
NEW_UPDATES = 72
PARENT_TOTAL_UPDATES = 324
LR_ARM = 0.0001
DECISIONS_PER_UPDATE = 16384
SELECTED_TRAJECTORY_BASELINE = 4760.062404125177
CAMPAIGN_COST_BASELINE = 5537.773026792208
BASELINE_MEAN_ALIVE = 2483.65625
BASELINE_PERFORMANCE = {"alive_frames": {"Q1": 566.75, "Q4": 5171.8125, "mean": 2483.65625},
                        "score": {"Q1": 2.6875, "Q4": 57.21875, "mean": 24.046875}}
BASELINE_DEATH_CAUSES = {"normal_enemy": 26, "static_pattern_rect": 14, "kamikaze_enemy": 13,
                         "moving_pattern_rect": 10, "kamikaze_explosion": 1}
SEED_COHORT = tuple(range(0xD0000000, 0xD0000040))
ENTRY_ZERO = {"updates": 0, "optimizer_steps": 0, "environment_decisions": 0, "raw_frames": 0}
EXACT_DODGE = {"dodge_rl": "dodge_rl/__init__.py", "dodge_rl.checkpoints": "dodge_rl/checkpoints.py",
               "dodge_rl.survival_gate": "dodge_rl/survival_gate.py", "dodge_rl.identity": "dodge_rl/identity.py",
               "dodge_rl._native": "dodge_rl/_native.cpython-312-darwin.so"}
AUTHORITY = {"selection": False, "best_replacement": False, "continuation": False, "terminal_acceptance": False}


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


def bind_environment():
    """Interpreter, bytecode policy, and empty bytecode prefix before frozen imports."""
    check(sys.dont_write_bytecode and sys.flags.dont_write_bytecode, "Bytecode writing must be disabled (-B)")
    check(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 must be inherited")
    prefix = str(PREP / "empty-pycache")
    check(sys.pycache_prefix == prefix and os.environ.get("PYTHONPYCACHEPREFIX") == prefix,
          "Bytecode prefix differs from registration")
    check(Path(prefix).is_dir() and not any(Path(prefix).iterdir()), "Registered bytecode prefix is not empty")
    for name in ("runner", "execute_once_frozen", "dodge_rl"):
        check(name not in sys.modules, f"Module cache already contains {name}")


def load_frozen(*, enforce_lease=True):
    """Frozen runner by exact bytes, then the live registration through its own preflight.

    enforce_lease=False exists only for CPU unit tests before the parent installs the lease.
    The audit and wrapper always call with the default, so the live lease is checked.
    """
    bind_environment()
    check(sha_file(REG_PATH) == REG_SHA, "Registration digest differs")
    runner = load_pinned_module("runner", PREP / "runner.py", RUNNER_SHA)
    check(Path(runner.__file__).resolve() == (PREP / "runner.py").resolve(), "Runner origin differs")
    if not enforce_lease:
        runner.check_lease = lambda reg: None
    reg, config = runner.load_registration(str(REG_PATH), REG_SHA)
    check(reg["run_id"] == runner.RUN_ID == RUN_ID == RUN.name, "Run identity differs")
    check(Path(reg["runner_path"]).resolve() == (PREP / "runner.py").resolve(), "Frozen runner origin differs")
    check(sha_file(PREP / "execute_once.py") == LAUNCHER_SHA and reg["config_sha256"] == CONFIG_SHA
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
    names = ["entry-restoration.json", "effective-learning-rate.json", "launch-marker.json", "worker-launch.json",
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


def check_saved_lr(state, expected=LR_ARM):
    """Real saved copied optimizer groups carry exactly the arm LR as floats."""
    groups = state["optimizer"]["param_groups"]
    check(groups and all(type(g.get("lr")) is float and g["lr"] == expected for g in groups),
          "Saved optimizer LR differs from arm LR 1e-4")


def validate_metric_rows(runner, metrics, max_local):
    """Per-update rows in the consumed prefix: contiguous phases, exact counter chain, finite values."""
    check([row.get("phase_update") for row in metrics] == list(range(PHASE_START + 1, PHASE_START + 1 + len(metrics))),
          "Metric rows are not a contiguous update prefix")
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
          and ident.get("parent_config_sha256") == CONFIG_SHA and ident.get("policy_sha256") == POLICY_SHA
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
          "Cumulative counter base differs from accepted 324-update parent")
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
    """Entry 276 rows and means equal the accepted parent 276 evaluation (JSON and JSONL)."""
    base_path = PARENT_RUN / "development-000276.json"
    base, base_sha = stable_json(base_path)
    check(base_sha == PARENT_EVAL_JSON_SHA, "Accepted 276 JSON digest differs")
    check(sha_file(PARENT_RUN / "development-000276.jsonl") == PARENT_EVAL_JSONL_SHA, "Accepted 276 JSONL digest differs")
    base_rows = base["evaluation"]["rows"]
    check(sorted(cert["evaluation"]["rows"], key=lambda r: r["seed"]) == sorted(base_rows, key=lambda r: r["seed"]),
          "Entry 276 certificate rows differ from accepted parent JSON")
    base_jsonl, _ = parse_journal(read_stable(PARENT_RUN / "development-000276.jsonl"), strict=True)
    check(sorted(rows_list, key=lambda r: r["seed"]) == sorted(base_jsonl, key=lambda r: r["seed"]),
          "Entry 276 JSONL rows differ from accepted parent JSONL")
    mean = sum(r["alive_frames"] for r in base_rows) / 64
    check(mean == BASELINE_MEAN_ALIVE and base["performance"] == BASELINE_PERFORMANCE,
          "Accepted parent 276 baseline performance differs")
    check(base["evaluation"]["deaths"] == 64 and base["evaluation"]["caps"] == 0
          and {k: v for k, v in base["evaluation"]["death_causes"].items() if v} == BASELINE_DEATH_CAUSES,
          "Accepted parent 276 death accounting differs")


def validate_entry_state(ctx, state):
    """Entry candidate is the restored parent before any gradient: model, RNG, Adam, and LR exact."""
    runner, parent = ctx["runner"], ctx["parent"]
    check(runner.fingerprint(state["model"]) == runner.fingerprint(parent["model"])
          and runner.fingerprint(state["rng"]) == runner.fingerprint(parent["rng"]),
          "Entry model or RNG differs from accepted parent")
    check(runner.fingerprint(state["optimizer"]) == runner.fingerprint(parent["optimizer"]),
          "Entry Adam state differs from accepted parent")
    check_saved_lr(state)


def validate_effective_lr_record(runner, record, parent):
    n = len(parent["optimizer"]["param_groups"])
    check(record.get("expected_learning_rate") == LR_ARM and record.get("mutation_applied") is False
          and record.get("parent_group_lrs") == [LR_ARM] * n and record.get("restored_group_lrs") == [LR_ARM] * n,
          "Effective learning-rate record differs from arm LR 1e-4 without mutation")
    fp = runner.fingerprint(parent["optimizer"])
    check(record.get("parent_optimizer_fingerprint") == fp and record.get("restored_optimizer_fingerprint") == fp,
          "Effective learning-rate optimizer fingerprints differ from accepted parent")


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


def retained_best(means_in_order, baseline=BASELINE_MEAN_ALIVE):
    """Chronological monotone best: a candidate replaces the retained one only if strictly greater."""
    best_update, best_mean = None, baseline
    for update, mean in means_in_order:
        if mean > best_mean:
            best_update, best_mean = update, mean
    return best_update


def choose_best(means, baseline=BASELINE_MEAN_ALIVE):
    """Strict improvement over the accepted 276 baseline; ties keep the earlier update."""
    eligible = {u: m for u, m in means.items() if m > baseline}
    if not eligible:
        return None
    return max(eligible, key=lambda u: (eligible[u], -u))


def check_observer_dir(observer_dir):
    """Full mode binds the one registered parent-owned observer directory and its accepted source."""
    check(Path(observer_dir).resolve() == OBSERVER_DIR.resolve(),
          "Observer directory differs from the registered parent-owned directory")
    check(sha_file(OBSERVER_DIR / "observe.py") == OBSERVER_SHA, "Observer source digest differs")
    instantiation, _ = stable_json(OBSERVER_DIR / "instantiation.json")
    check(instantiation.get("observer_sha256") == OBSERVER_SHA, "Observer instantiation digest differs")


def audit(*, provisional, observer_dir=None):
    runner, reg, config = load_frozen()
    ckpt, survival_gate, identity_hash = import_runtime(reg)
    tracked = {}
    journal_raw = read_stable(RUN / "training-episodes.jsonl")
    metrics_raw = read_stable(RUN / "training-metrics.jsonl")
    journal, journal_consumed = parse_journal(journal_raw, strict=not provisional)
    metrics, metrics_consumed = parse_journal(metrics_raw, strict=not provisional)

    published = published_updates()
    check(published and published[0] == PHASE_START, "Entry 276 certificate is not published")
    if provisional:
        targets = tuple(published)
    else:
        check(tuple(published) == UPDATES, "Full mode requires all seven published certificates")
        check(observer_dir is not None, "Full mode requires the parent-owned observer directory")
        check_observer_dir(observer_dir)
        targets = UPDATES

    ctx = build_context(runner, reg, config, ckpt, survival_gate, identity_hash, journal, metrics)
    entry_path = RUN / "entry-restoration.json"
    lr_path = RUN / "effective-learning-rate.json"
    entry_restoration, entry_sha = stable_json(entry_path)
    audit_entry_restoration(ctx, entry_restoration)
    effective, effective_sha = stable_json(lr_path)
    validate_effective_lr_record(runner, effective, ctx["parent"])
    tracked[str(entry_path)] = entry_sha
    tracked[str(lr_path)] = effective_sha
    validate_metric_rows(runner, metrics, max(targets) - PHASE_START)

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
        summary = validate_certificate(ctx, update, cert, side, rows_list, cp.name, cp_hash)
        check_saved_lr(state)
        if update == PHASE_START:
            validate_entry_against_parent(cert, rows_list)
            validate_entry_state(ctx, state)
        means[update] = summary["mean_alive_frames"]
        results[str(update)] = {**summary, "checkpoint_sha256": cp_hash, "certificate_sha256": cert_hash,
                                "sidecar_sha256": side_hash, "rows_sha256": sha_bytes(rows_raw)}
        for path, digest in ((cp, cp_hash), (cert_p, cert_hash), (side_p, side_hash), (rows_p, sha_bytes(rows_raw))):
            tracked[str(path)] = digest
        del state

    proposed = choose_best(means)
    retained = retained_best(sorted(means.items()))
    check(retained == proposed, "Chronological retained best differs from strict-max selection")
    result = {"schema": "retained276_continuation_all_candidate_audit_v1",
              "status": "readonly_published_prefix_provisional" if provisional else "all_candidates_audited_pending_parent_terminal_acceptance",
              "run_id": RUN_ID, "registration_sha256": REG_SHA, "updates_audited": list(targets),
              "baseline_mean_alive_frames": BASELINE_MEAN_ALIVE, "proposed_best_update": proposed,
              "candidates": results, "lr_transition": None, "effective_lr": LR_ARM,
              "journal_prefix_policy": "initial+parent_abandoned+phase<=update",
              "journal_consumed_sha256": sha_bytes(journal_consumed), "metrics_consumed_sha256": sha_bytes(metrics_consumed),
              "authority": dict(AUTHORITY)}
    if not provisional:
        expected = expected_outputs()
        check(expected == reg["expected_outputs"], "Expected output inventory differs from registration")
        missing = [name for name in expected if not (RUN / name).is_file()]
        check(not missing, f"Terminal outputs missing: {missing[:3]}")
        execution, _ = stable_json(RUN / "execution-result.json")
        worker, _ = stable_json(RUN / "worker-result.json")
        check(execution.get("status") == "passed" and worker.get("status") == "completed", "Terminal status not successful")
        launcher = load_pinned_module("execute_once_frozen", PREP / "execute_once.py", LAUNCHER_SHA)
        check(launcher.r is runner, "Frozen launcher did not bind the audited runner")
        result["frozen_launcher_terminal_checks"] = launcher.validate_outputs(reg, worker, REG_SHA)
        observation, _ = stable_json(Path(observer_dir) / "observation.json")
        check(observation["outer_raw_exit"] == 0 and observation["worker_raw_exit"] == 0, "Observer raw exits differ")

    # Append-only journals and published files must be unchanged after the audit.
    check(Path(RUN / "training-episodes.jsonl").read_bytes()[: len(journal_consumed)] == journal_consumed,
          "Consumed training-episode journal prefix changed during audit")
    check(Path(RUN / "training-metrics.jsonl").read_bytes()[: len(metrics_consumed)] == metrics_consumed,
          "Consumed training-metrics prefix changed during audit")
    for path, digest in tracked.items():
        check(sha_file(path) == digest, f"Audited file changed during audit: {Path(path).name}")
    check(sha_file(REG_PATH) == REG_SHA, "Registration changed during audit")
    runner.verify_pins(reg["pins"])
    check(not any((PREP / "empty-pycache").iterdir()), "Bytecode prefix gained files during audit")
    result["pins_checked_before_and_after"] = len(reg["pins"])
    result["parent_gated_checks"] = ["observer raw exits and resources", "wall accounting postflight",
                                     "source postflight", "final publication absence", "lease release"]
    result["tracked_file_sha256"] = dict(sorted(tracked.items()))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--provisional", action="store_true")
    parser.add_argument("--observer-dir")
    args = parser.parse_args(argv)
    output = Path(args.output)
    check(output.parent.resolve() == OUT.resolve(), "Output must be in the auditor directory")
    result = audit(provisional=args.provisional, observer_dir=args.observer_dir)
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
