"""Independent read-only auditor for the retained-204 lr1e-4 continuation (r2).

Loads the frozen r3 runner through its own registration preflight, so the frozen
launcher's validator sees the verified LR helper bound in the runner module.
Prefix mode audits published candidates only. Full mode also needs terminal outputs.
Nothing here grants selection, continuation, or terminal acceptance.
"""
from __future__ import annotations

import argparse
import copy
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
PREP = ROOT / "learning/runs/v2/D2-retained204-lr1e4-prepare-luna-20261026-r3"
RUN = ROOT / "learning/runs/v2/D2-retained204-lr1e4-20261026-r1"
OBS = ROOT / "learning/runs/v2/D2-retained204-lr1e4-execution-observer-luna-20261026-r1"
BASE = ROOT / "learning/runs/v2/D2-best180-branch-luna-20261026-r1"
RECEIPT = ROOT / "learning/runs/v2/D2-best180-parent-terminal-audit-20261026-r1/retained-best-candidate-receipt.json"

REG_PATH = PREP / "registration.json"
REG_SHA = "68063348dede3050c4a8852c6314f4c95fd3a623e89c9499413f2325f4edad44"
RUNNER_SHA = "7543ba23a65c03e19b05015894b74a9c68e23e56e49daf1ba3ee3808b368f89d"
LAUNCHER_SHA = "58bc5cb35ab531455d5218dd3a77dde84d441a12d361a99c9c8a0c83b33e4206"
HELPER_SHA = "b3cd23ccf14f9703dfd86ef3c24bfed41ab81f166c28205d90222bc12488ed8a"
CONFIG_SHA = "f858a63c324fc312f794c0423aa56db2daf60793b62990cd51fa400afe3af628"
PARENT_CONFIG_SHA = "2d8eb5626d0debdf5416d0b89610d78ddd56011c3238a82fec72efabe1bd7fe3"
PARENT_SHA = "f1300e4e86ec89ed9cfba446c8e7f66cf29caad6a1130864edd4d6ee7859d442"
PARENT_RECEIPT_SHA = "7fd26ae3f50ec7517a6f0a79334735bbfe48733b86639d83f7bafc122df110cf"
PARENT_REGISTRATION_SHA = "d6a5aa8cbdd889728b79486f09673215847b6d8e27f93f1ce80eb1cf3e8cc7ba"
PARENT_RUN_ID = "D2-best180-branch-luna-20261026-r1"
BASE_JSON_SHA = "4a6ff2e4615b4fe6ded781decc29858935fcdbc01f0c216f631abe02c10f5d48"
BASE_JSONL_SHA = "3ca81171ab7130ee337a4504e957695e7132e7e9f1243b0e8c48db87032fd55a"
BASELINE_MEAN_ALIVE = 1921.171875
PHASE_START, PHASE_END = 204, 276
UPDATES = tuple(range(PHASE_START, PHASE_END + 1, 12))
PARENT_UPDATES = 252
PARENT_LOCAL_UPDATES = 24
LR_PARENT, LR_ARM = 0.0003, 0.0001
SELECTED_BASE_WALL = 3352.0462366251204
CAMPAIGN_BASE_WALL = 4129.756859292152
DECISIONS_PER_UPDATE = 16384
COMPETENCE_ALIVE = 3060
SEED_COHORT = tuple(range(0xD0000000, 0xD0000040))
U64 = 2**64
ENTRY_ZERO = {"updates": 0, "optimizer_steps": 0, "environment_decisions": 0, "raw_frames": 0}
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
    prefix = str(PREP / "empty-pycache-prefix")
    check(sys.pycache_prefix == prefix and os.environ.get("PYTHONPYCACHEPREFIX") == prefix,
          "Bytecode prefix differs from registration")
    check(Path(prefix).is_dir() and not any(Path(prefix).iterdir()), "Registered bytecode prefix is not empty")
    for name in ("runner", "execute_once_frozen", "dodge_rl"):
        check(name not in sys.modules, f"Module cache already contains {name}")


def load_frozen():
    """Frozen runner by exact bytes, then the live registration through its own preflight.

    load_registration() sets runner._VERIFIED_TRANSITION, which the frozen launcher's
    validate_outputs() dereferences. Only the live lease is checked; nothing is mocked.
    """
    bind_environment()
    check(sha_file(REG_PATH) == REG_SHA, "Registration digest differs")
    runner = load_pinned_module("runner", PREP / "runner.py", RUNNER_SHA)
    check(Path(runner.__file__).resolve() == (PREP / "runner.py").resolve(), "Runner origin differs")
    reg, config = runner.load_registration(str(REG_PATH), REG_SHA)
    check(runner._VERIFIED_TRANSITION is not None, "Verified LR transition helper not bound")
    check(Path(reg["runner_path"]).resolve() == (PREP / "runner.py").resolve(), "Frozen runner origin differs")
    check(reg["run_id"] == runner.RUN_ID == RUN.name, "Run identity differs")
    check(sha_file(PREP / "execute_once.py") == LAUNCHER_SHA and sha_file(reg["lr_transition_helper_path"]) == HELPER_SHA
          and reg["config_sha256"] == CONFIG_SHA and reg["parent"]["sha256"] == PARENT_SHA
          and sha_file(RECEIPT) == PARENT_RECEIPT_SHA, "Critical pin differs")
    return runner, reg, config


def import_runtime(reg):
    runtime = Path(reg["runtime_root"]).resolve()
    sys.path.insert(0, str(runtime))
    import dodge_rl
    from dodge_rl import checkpoints, survival_gate
    from dodge_rl.identity import identity_hash
    check(Path(dodge_rl.__file__).resolve().is_relative_to(runtime), "dodge_rl origin differs")
    return checkpoints, survival_gate, identity_hash


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
        if not all(p.is_file() and not p.name.endswith(".partial") for p in expected_candidate_paths(update).values()):
            break
        done.append(update)
    return done


def strip_lr(optimizer_state):
    return {**optimizer_state, "param_groups": [{k: v for k, v in g.items() if k != "lr"} for g in optimizer_state["param_groups"]]}


def validate_metric_rows(runner, metrics, max_local):
    """Per-update rows in the consumed prefix: contiguous phases, exact counter chain, finite values."""
    check([row.get("phase_update") for row in metrics] == list(range(PHASE_START + 1, PHASE_START + 1 + len(metrics))),
          "Metric rows are not a contiguous update prefix")
    steps = 0
    for local, row in enumerate(metrics[:max_local], 1):
        value = row["metrics"]
        runner.finite_tree(value)
        check(0 < value["optimizer_steps"] <= 128 and value["transitions"] == DECISIONS_PER_UPDATE, "Optimizer or rollout counts differ")
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
          and state.get("policy_sha256") == runner.POLICY_SHA and state.get("native_sha256") == reg["native"]["sha256"]
          and state.get("runtime_sha256") == reg["runtime_sha256"] and type(state.get("run_seed")) is int
          and state["run_seed"] == reg["run_seed"], "Candidate registration/config/policy/native/runtime/seed differs")
    check(state.get("parent_sha256") == PARENT_SHA and state.get("parent_checkpoint_sha256") == PARENT_SHA
          and state.get("parent_registration_sha256") == PARENT_REGISTRATION_SHA and state.get("parent_run_id") == PARENT_RUN_ID,
          "Candidate parent identity differs")
    ident = state.get("identity")
    check(isinstance(ident, dict) and state.get("identity_sha256") == ctx["identity_hash"](ident), "Identity hash differs")
    check(ident.get("version") == "teacher_identity_v3" and ident.get("run_id") == runner.RUN_ID
          and ident.get("phase") == "D2" and ident.get("phase_update_start") == PHASE_START
          and ident.get("phase_update_end") == PHASE_END and ident.get("run_seed") == reg["run_seed"]
          and ident.get("registration_sha256") == REG_SHA and ident.get("parent_checkpoint_sha256") == PARENT_SHA
          and ident.get("parent_candidate_receipt_sha256") == PARENT_RECEIPT_SHA
          and ident.get("parent_config_sha256") == PARENT_CONFIG_SHA and ident.get("policy_sha256") == runner.POLICY_SHA
          and ident.get("config") == ctx["config"] and ident.get("architecture") == parent["identity"]["architecture"],
          "Embedded identity, config, or architecture differs")
    progress = state.get("update_progress")
    check(type(progress) is dict and progress.get("complete") is True and progress.get("in_update") is False
          and progress.get("completed_updates") == local, "Update progress differs")
    check(state.get("inherited_counters") == parent["cumulative_counters"]
          and state.get("parent_abandoned_current_episodes") == parent["abandoned_current_episodes"],
          "Inherited counters or parent abandoned records differ")
    counters = state.get("counters")
    if update == PHASE_START:
        check(counters == ENTRY_ZERO and all(type(v) is int for v in counters.values()) and local == 0,
              "Entry candidate must carry zero local counters")
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
    check(state.get("cumulative_counters") == cumulative and cumulative["updates"] == PARENT_UPDATES + local,
          "Cumulative counter base differs from accepted 252-update parent")
    validate_wall(state, local)


def validate_wall(state, local):
    cur = state.get("current_iteration_observed_outer_seconds")
    check(isinstance(cur, (int, float)) and math.isfinite(cur) and 0 < cur < 1800, "Current-iteration wall out of range")
    traj = state.get("cumulative_selected_checkpoint_trajectory_wall_seconds")
    cost = state.get("cumulative_successful_ancestor_and_completed_campaign_cost_seconds")
    check(all(isinstance(v, (int, float)) and math.isfinite(v) for v in (traj, cost)), "Wall fields not finite")
    check(math.isclose(traj, SELECTED_BASE_WALL + cur, rel_tol=0, abs_tol=1e-6)
          and math.isclose(cost, CAMPAIGN_BASE_WALL + cur, rel_tol=0, abs_tol=1e-6), "Wall formula differs")
    check(state.get("selected_parent_checkpoint_trajectory_baseline_seconds") == SELECTED_BASE_WALL
          and state.get("parent_completed_campaign_cost_baseline_seconds") == CAMPAIGN_BASE_WALL, "Wall baselines differ")


def validate_resume(ctx, update, state):
    """Next indices, abandoned records, journal prefix, and raw-frame conservation."""
    runner, parent, records = ctx["runner"], ctx["parent"], ctx["journal"]
    nxt = state.get("next_episode_indices")
    check(type(nxt) is list and len(nxt) == 64 and all(type(x) is int and 0 <= x < U64 for x in nxt),
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


def validate_certificate(ctx, update, cert, side, rows_list, cp_name, cp_hash, state):
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
    competence = cert.get("competence_passed")
    check(type(competence) is bool and competence == (mean_alive >= COMPETENCE_ALIVE), "Competence differs from 3060 survival floor")
    check(survival_gate.progress_passed("D2", {"D2": ev}) == competence, "Competence differs from survival gate")
    return {"mean_alive_frames": ev["mean_alive_frames"], "mean_score": ev["mean_score"],
            "performance": cert["performance"], "competence_passed": competence, "deaths": deaths, "caps": caps}


def validate_entry_against_base(ctx, cert, rows_list):
    base, base_sha = stable_json(BASE / "development-000204.json")
    check(base_sha == BASE_JSON_SHA, "Accepted 204 JSON digest differs")
    check(sha_file(BASE / "development-000204.jsonl") == BASE_JSONL_SHA, "Accepted 204 JSONL digest differs")
    check(sha_file(RECEIPT) == PARENT_RECEIPT_SHA and json.loads(read_stable(RECEIPT))["evaluation_sha256"] == BASE_JSON_SHA,
          "Parent receipt does not bind accepted 204 JSON")
    base_rows = base["evaluation"]["rows"]
    check(sorted(cert["evaluation"]["rows"], key=lambda r: r["seed"]) == sorted(base_rows, key=lambda r: r["seed"]),
          "Entry 204 certificate rows differ from accepted JSON")
    base_jsonl, _ = parse_journal(read_stable(BASE / "development-000204.jsonl"), strict=True)
    check(sorted(rows_list, key=lambda r: r["seed"]) == sorted(base_jsonl, key=lambda r: r["seed"]),
          "Entry 204 JSONL rows differ from accepted JSONL")
    mean = sum(r["alive_frames"] for r in base_rows) / 64
    check(mean == BASELINE_MEAN_ALIVE, "Accepted 204 baseline mean differs")


def lr_transition_recomputed(ctx, entry_state):
    """Recompute before/after fingerprints on the real CPU parent and entry optimizers."""
    L, reg, parent = ctx["lr_helper"], ctx["reg"], ctx["parent"]
    identities = {"parent_checkpoint_sha256": PARENT_SHA, "candidate_receipt_sha256": PARENT_RECEIPT_SHA,
                  "parent_config_sha256": PARENT_CONFIG_SHA, "arm_config_sha256": CONFIG_SHA,
                  "helper_sha256": reg["lr_transition_helper_sha256"]}
    before = L.begin_transition_record(parent["optimizer"], identities)
    delta = {"parent_lr": LR_PARENT, "effective_lr": LR_ARM, "changed_fields": ["optimizer.param_groups[*].lr"],
             "per_group_lr": [{"index": i, "before": LR_PARENT, "after": LR_ARM}
                              for i, _ in enumerate(parent["optimizer"]["param_groups"])]}
    return L.transition_record(before, entry_state["optimizer"], delta)


def audit_lr_record(ctx, entry_state, lr_record):
    recomputed = lr_transition_recomputed(ctx, entry_state)
    check(recomputed == lr_record, "LR transition record differs from recomputed CPU fingerprints")
    return recomputed


def audit_entry_restoration(ctx, entry_restoration):
    runner, parent = ctx["runner"], ctx["parent"]
    check(entry_restoration["matched"] == {"model": True, "Adam": True, "RNG": True}
          and entry_restoration["parent_sha256"] == PARENT_SHA, "Entry restoration did not match parent")
    expected = {"model": runner.fingerprint(parent["model"]), "Adam": runner.fingerprint(parent["optimizer"]),
                "RNG": runner.fingerprint(parent["rng"])}
    for name, digest in expected.items():
        check(entry_restoration["components"][name]["expected_sha256"] == digest
              and entry_restoration["components"][name]["restored_sha256"] == digest
              and entry_restoration["components"][name]["matched"] is True, f"Entry restoration {name} digest differs")


def build_context(runner, reg, config, ckpt, survival_gate, identity_hash, journal, metrics):
    parent = ckpt.load_checkpoint(Path(reg["parent"]["path"]), expected_sha256=PARENT_SHA)
    ckpt.require_complete_update(parent)
    runner.validate_parent_checkpoint_for_restore(parent, PARENT_SHA, json.loads(read_stable(reg["parent"]["terminal_receipt_path"])))
    rows_by_phase = {}
    for row in metrics:
        rows_by_phase.setdefault(row["phase_update"], []).append(row)
    return {"runner": runner, "reg": reg, "config": config, "parent": parent, "ckpt": ckpt,
            "survival_gate": survival_gate, "identity_hash": identity_hash, "lr_helper": runner._VERIFIED_TRANSITION,
            "journal": journal, "metrics": metrics, "rows_by_phase": rows_by_phase}


def audit(*, provisional):
    runner, reg, config = load_frozen()
    ckpt, survival_gate, identity_hash = import_runtime(reg)
    tracked = {}
    lr_path = RUN / "lr-transition.json"
    lr_raw = read_stable(lr_path)
    lr_record = json.loads(lr_raw)
    tracked[str(lr_path)] = sha_bytes(lr_raw)

    journal_raw = Path(RUN / "training-episodes.jsonl").read_bytes()
    metrics_raw = Path(RUN / "training-metrics.jsonl").read_bytes()
    journal, journal_consumed = parse_journal(journal_raw, strict=not provisional)
    metrics, metrics_consumed = parse_journal(metrics_raw, strict=not provisional)

    published = published_updates()
    check(published and published[0] == PHASE_START, "Entry 204 certificate is not published")
    if provisional:
        targets = tuple(published)
    else:
        check(tuple(published) == UPDATES, "Full mode requires all seven published certificates")
        targets = UPDATES

    ctx = build_context(runner, reg, config, ckpt, survival_gate, identity_hash, journal, metrics)
    entry_restoration, _ = stable_json(RUN / "entry-restoration.json")
    audit_entry_restoration(ctx, entry_restoration)
    validate_metric_rows(runner, metrics, max(targets) - PHASE_START)

    results, means, states = {}, {}, {}
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
        summary = validate_certificate(ctx, update, cert, side, rows_list, cp.name, cp_hash, state)
        if update == PHASE_START:
            check(runner.fingerprint(state["model"]) == runner.fingerprint(ctx["parent"]["model"])
                  and runner.fingerprint(state["rng"]) == runner.fingerprint(ctx["parent"]["rng"]),
                  "Entry model or RNG differs from accepted parent")
            check(runner.fingerprint(strip_lr(state["optimizer"])) == runner.fingerprint(strip_lr(ctx["parent"]["optimizer"])),
                  "Entry Adam state differs beyond group LR")
            check(all(g["lr"] == LR_ARM and type(g["lr"]) is float for g in state["optimizer"]["param_groups"]),
                  "Entry optimizer LR is not exactly 1e-4")
            ctx["lr_helper"].assert_saved_optimizer_lr(state, LR_ARM)
            validate_entry_against_base(ctx, cert, rows_list)
            audit_lr_record(ctx, state, lr_record)
        else:
            ctx["lr_helper"].assert_saved_optimizer_lr(state, LR_ARM)
        means[update] = summary["mean_alive_frames"]
        states[update] = state
        results[str(update)] = {**summary, "checkpoint_sha256": cp_hash, "certificate_sha256": cert_hash,
                                "sidecar_sha256": side_hash, "rows_sha256": sha_bytes(rows_raw)}
        for path, digest in ((cp, cp_hash), (cert_p, cert_hash), (side_p, side_hash), (rows_p, sha_bytes(rows_raw))):
            tracked[str(path)] = digest
        del state

    proposed = choose_best(means)
    result = {"schema": "retained204_lr1e4_all_candidate_audit_v2",
              "status": "readonly_published_prefix_provisional" if provisional else "all_candidates_audited_pending_parent_terminal_acceptance",
              "run_id": runner.RUN_ID, "registration_sha256": REG_SHA, "updates_audited": list(targets),
              "baseline_mean_alive_frames": BASELINE_MEAN_ALIVE, "proposed_best_update": proposed,
              "candidates": results, "lr_transition_recomputed": True,
              "journal_prefix_policy": "initial+parent_abandoned+phase<=update",
              "journal_consumed_sha256": sha_bytes(journal_consumed), "metrics_consumed_sha256": sha_bytes(metrics_consumed),
              "authority": dict(AUTHORITY)}
    if not provisional:
        execution, _ = stable_json(RUN / "execution-result.json")
        worker, _ = stable_json(RUN / "worker-result.json")
        check(execution.get("status") == "passed" and worker.get("status") == "completed", "Terminal status not successful")
        launcher = load_pinned_module("execute_once_frozen", PREP / "execute_once.py", LAUNCHER_SHA)
        check(launcher.r is runner, "Frozen launcher did not bind the audited runner")
        result["frozen_launcher_terminal_checks"] = launcher.validate_outputs(reg, worker, REG_SHA)
        observation, _ = stable_json(OBS / "observation.json")
        check(observation["outer_raw_exit"] == 0 and observation["worker_raw_exit"] == 0, "Observer raw exits differ")

    # Append-only journals: the consumed prefix must remain byte-identical, and published files must be unchanged.
    check(Path(RUN / "training-episodes.jsonl").read_bytes()[: len(journal_consumed)] == journal_consumed,
          "Consumed training-episode journal prefix changed during audit")
    check(Path(RUN / "training-metrics.jsonl").read_bytes()[: len(metrics_consumed)] == metrics_consumed,
          "Consumed training-metrics prefix changed during audit")
    check(sha_file(lr_path) == tracked[str(lr_path)], "LR transition changed during audit")
    for path, digest in tracked.items():
        check(sha_file(path) == digest, f"Audited file changed during audit: {Path(path).name}")
    check(sha_file(REG_PATH) == REG_SHA, "Registration changed during audit")
    runner.verify_pins(reg["pins"])
    check(not any((PREP / "empty-pycache-prefix").iterdir()), "Bytecode prefix gained files during audit")
    result["pins_checked_before_and_after"] = len(reg["pins"])
    result["parent_gated_checks"] = ["observer raw exits and resources", "wall accounting postflight",
                                     "source postflight", "final publication absence", "lease release"]
    result["tracked_file_sha256"] = dict(sorted(tracked.items()))
    return result


def choose_best(means, baseline=BASELINE_MEAN_ALIVE):
    """Strict improvement over the retained 204 baseline; ties keep the earlier update."""
    eligible = {u: m for u, m in means.items() if m > baseline}
    if not eligible:
        return None
    return max(eligible, key=lambda u: (eligible[u], -u))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--provisional", action="store_true")
    args = parser.parse_args(argv)
    output = Path(args.output)
    check(output.parent.resolve() == OUT.resolve(), "Output must be in the auditor directory")
    result = audit(provisional=args.provisional)
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
