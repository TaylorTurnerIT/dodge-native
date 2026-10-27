"""Independent read-only auditor for the retained-204 lr1e-4 continuation.

Binds the frozen r3 registration, runner, launcher, and LR helper by exact bytes.
Never writes into the training output directory. Prefix mode is provisional and has
no selection or continuation authority. Full mode runs the frozen launcher validator
before independent checks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import types
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
PARENT_SHA = "f1300e4e86ec89ed9cfba446c8e7f66cf29caad6a1130864edd4d6ee7859d442"
PARENT_RECEIPT_SHA = "7fd26ae3f50ec7517a6f0a79334735bbfe48733b86639d83f7bafc122df110cf"
BASE_JSON_SHA = "4a6ff2e4615b4fe6ded781decc29858935fcdbc01f0c216f631abe02c10f5d48"
BASE_JSONL_SHA = "3ca81171ab7130ee337a4504e957695e7132e7e9f1243b0e8c48db87032fd55a"
BASELINE_MEAN_ALIVE = 1921.171875
PHASE_START, PHASE_END = 204, 276
UPDATES = tuple(range(204, 277, 12))
SELECTED_BASE_WALL = 3352.0462366251204
CAMPAIGN_BASE_WALL = 4129.756859292152
DECISIONS_PER_UPDATE = 16384
COMPETENCE_ALIVE = 3060
ENTRY_ZERO = {"updates": 0, "optimizer_steps": 0, "environment_decisions": 0, "raw_frames": 0}


class AuditError(ValueError):
    pass


def check(condition, message):
    if not condition:
        raise AuditError(message)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return sha_bytes(Path(path).read_bytes())


def stable_bytes(path):
    """Read twice; reject a file that changed while being read."""
    first = Path(path).read_bytes()
    check(first == Path(path).read_bytes(), f"Input changed while reading: {path}")
    return first


def stable_json(path):
    raw = stable_bytes(path)
    return json.loads(raw), sha_bytes(raw)


def complete_lines(path, *, strict):
    """Return parsed JSONL records and digest of consumed bytes. Prefix mode ignores a partial tail; full mode fails on one."""
    raw = stable_bytes(path)
    if raw and not raw.endswith(b"\n"):
        check(not strict, f"Journal tail incomplete in full mode: {path}")
        raw = raw[: raw.rfind(b"\n") + 1]
    records = [json.loads(line) for line in raw.splitlines()]
    return records, sha_bytes(raw)


def consumed_length(path, strict):
    raw = Path(path).read_bytes()
    return len(raw) if strict or raw.endswith(b"\n") or not raw else raw.rfind(b"\n") + 1


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


def bind_environment(reg):
    """Interpreter, bytecode policy, empty cache, and contamination gates before frozen imports."""
    check(Path(sys.executable).resolve() == Path(reg["interpreter"]).resolve(), "Interpreter differs from registration")
    check(sys.dont_write_bytecode and sys.flags.dont_write_bytecode, "Bytecode writing must be disabled")
    prefix = reg["import_policy"]["pycache_prefix"]
    check(sys.pycache_prefix == prefix and os.environ.get("PYTHONPYCACHEPREFIX") == prefix,
          "Bytecode prefix differs from registration")
    check(Path(prefix).is_dir() and not any(Path(prefix).iterdir()), "Registered bytecode prefix is not empty")
    for name in ("runner", "execute_once_frozen", "dodge_rl"):
        check(name not in sys.modules, f"Module cache already contains {name}")


def check_critical_pins(reg):
    for path, expected in (
        (str(PREP / "runner.py"), RUNNER_SHA),
        (str(PREP / "execute_once.py"), LAUNCHER_SHA),
        (reg["lr_transition_helper_path"], HELPER_SHA),
        (reg["config_path"], CONFIG_SHA),
        (reg["parent"]["path"], PARENT_SHA),
        (reg["parent"]["terminal_receipt_path"], PARENT_RECEIPT_SHA),
    ):
        check(reg["pins"].get(path) == expected and sha(path) == expected, f"Critical pin differs: {Path(path).name}")


def validate_candidate_metadata(state, update, *, parent_cumulative, parent_next, reg_sha, config_sha,
                                policy_sha, parent_run_id, parent_registration_sha, run_id):
    """Pure metadata gate on a loaded candidate state (no tensor access)."""
    local = update - PHASE_START
    check(state.get("schema") == "d2_training_v3_checkpoint_v1" and state.get("tag") == "candidate"
          and state.get("eligibility_status") == "provisional_pending_parent_terminal_receipt"
          and state.get("training_eligible") is False and state.get("promoted") is False,
          "Candidate schema or eligibility differs")
    check(state.get("phase") == "D2" and state.get("phase_update") == update and state.get("local_update") == local,
          "Candidate phase/local update differs")
    check(state.get("registration_sha256") == reg_sha and state.get("config_sha256") == config_sha
          and state.get("policy_sha256") == policy_sha and state.get("parent_sha256") == PARENT_SHA
          and state.get("parent_checkpoint_sha256") == PARENT_SHA
          and state.get("parent_registration_sha256") == parent_registration_sha
          and state.get("parent_run_id") == parent_run_id, "Candidate frozen identity differs")
    ident = state.get("identity", {})
    check(ident.get("run_id") == run_id and ident.get("phase_update_start") == PHASE_START
          and ident.get("phase_update_end") == PHASE_END and ident.get("registration_sha256") == reg_sha
          and ident.get("parent_checkpoint_sha256") == PARENT_SHA and ident.get("policy_sha256") == policy_sha,
          "Embedded identity differs")
    progress = state.get("update_progress", {})
    check(progress.get("complete") is True and progress.get("in_update") is False
          and progress.get("completed_updates") == local, "Update progress differs")
    counters = state.get("counters", {})
    if update == PHASE_START:
        check(counters == ENTRY_ZERO, "Entry candidate must carry zero local counters")
    else:
        check(counters.get("updates") == local and counters.get("environment_decisions") == DECISIONS_PER_UPDATE * local,
              "Local counters differ from update count")
    check(state.get("inherited_counters") == parent_cumulative, "Inherited cumulative counters differ")
    expected_cumulative = {k: parent_cumulative[k] + counters[k] for k in ENTRY_ZERO}
    check(state.get("cumulative_counters") == expected_cumulative and expected_cumulative["updates"] == PARENT_UPDATES + local,
          "Cumulative counter base differs from accepted 252-update parent")
    check(state.get("next_episode_indices") is not None and len(state["next_episode_indices"]) == 64,
          "Resume next indices must cover 64 slots")
    groups = state.get("optimizer", {}).get("param_groups", [])
    check(len(groups) == 1 and groups[0].get("lr") == 0.0001, "Candidate optimizer LR is not 1e-4")
    return validate_wall(state, local)


PARENT_UPDATES = 252


def validate_wall(state, local):
    """Trajectory and campaign wall must be finite and follow the registered formula and limits."""
    cur = state.get("current_iteration_observed_outer_seconds")
    check(isinstance(cur, (int, float)) and math.isfinite(cur) and 0 < cur < 1800, "Current-iteration wall out of range")
    traj = state.get("cumulative_selected_checkpoint_trajectory_wall_seconds")
    cost = state.get("cumulative_successful_ancestor_and_completed_campaign_cost_seconds")
    check(all(isinstance(v, (int, float)) and math.isfinite(v) for v in (traj, cost)), "Wall fields not finite")
    check(math.isclose(traj, SELECTED_BASE_WALL + cur, rel_tol=0, abs_tol=1e-6)
          and math.isclose(cost, CAMPAIGN_BASE_WALL + cur, rel_tol=0, abs_tol=1e-6),
          "Wall formula differs")
    check(state.get("selected_parent_checkpoint_trajectory_baseline_seconds") == SELECTED_BASE_WALL
          and state.get("parent_completed_campaign_cost_baseline_seconds") == CAMPAIGN_BASE_WALL,
          "Wall baselines differ")
    return cur


def validate_prefix_journal(records, update, runner, parent_next, state):
    """Journal prefix through update, plus parent abandoned records only. Future events are excluded."""
    prefix = [row for row in records if row["kind"] in ("initial", "abandoned_parent_episode")
              or row.get("phase_update", 0) <= update]
    episode = runner.validate_episode_journal(prefix, parent_next)
    check(episode["next_episode_indices"] == state["next_episode_indices"], "Resume next indices differ from journal")
    abandoned = state["abandoned_current_episodes"]
    check(len(abandoned) == 64 and sorted(item["slot"] for item in abandoned) == list(range(64)),
          "Resume abandoned records must cover 64 slots")
    for item in abandoned:
        check(0 <= item["gameplay_frames"] < 18000, "Abandoned frames outside cap")
    completed = sum(row["info"]["gameplay_frames"] for row in prefix if row["kind"] == "completed")
    check(completed + sum(item["gameplay_frames"] for item in abandoned) == state["counters"]["raw_frames"],
          "Raw-frame conservation differs")
    inherited = [r for r in prefix if r["kind"] == "abandoned_parent_episode"]
    check(len(inherited) == 64, "Parent abandoned records must be preserved")
    return episode


def validate_certificate(cert, rows, runner, survival_passed):
    """Bind certificate summary, competence, and JSONL rows; no score gate."""
    evaluation = cert["evaluation"]
    check(len(rows) == 64 and sorted(r["seed"] for r in rows) == sorted(r["seed"] for r in evaluation["rows"]),
          "JSONL seed cohort differs from certificate")
    check(sorted(rows, key=lambda r: r["seed"]) == sorted(evaluation["rows"], key=lambda r: r["seed"]),
          "JSONL rows differ from certificate rows")
    alive = [r["alive_frames"] for r in evaluation["rows"]]
    check(math.isclose(evaluation["mean_alive_frames"], sum(alive) / 64, rel_tol=0, abs_tol=1e-9),
          "Certificate mean alive differs")
    check(cert["performance"] == runner.performance(evaluation), "Certificate performance differs")
    deaths = sum(r["terminated"] for r in evaluation["rows"])
    caps = sum(r["truncated"] for r in evaluation["rows"])
    check(deaths + caps == 64 and deaths == evaluation["deaths"] and caps == evaluation["caps"], "Boundary counts differ")
    check(cert["competence_passed"] == (evaluation["mean_alive_frames"] >= COMPETENCE_ALIVE)
          and cert["competence_passed"] == survival_passed, "Competence differs from survival gate")
    return evaluation["mean_alive_frames"]


def choose_best(means, baseline=BASELINE_MEAN_ALIVE):
    """Strict improvement over the retained 204 baseline; ties keep baseline; no endpoint default."""
    eligible = {u: m for u, m in means.items() if m > baseline}
    if not eligible:
        return None
    return max(eligible, key=lambda u: (eligible[u], -u))


def audit(*, provisional, reg_path=REG_PATH):
    reg, reg_hash = stable_json(reg_path)
    check(reg_hash == REG_SHA, "Registration digest differs")
    bind_environment(reg)
    check_critical_pins(reg)
    if not provisional:
        for path, expected in reg["pins"].items():
            check(sha(path) == expected, f"Registration pin differs: {path}")

    runner = load_pinned_module("runner", PREP / "runner.py", RUNNER_SHA)
    check(Path(runner.__file__).resolve() == (PREP / "runner.py").resolve(), "Runner origin differs")
    sys.path.insert(0, reg["runtime_root"])
    from dodge_rl import checkpoints as ckpt
    from dodge_rl import survival_gate
    check(Path(sys.modules["dodge_rl"].__file__).resolve().is_relative_to(Path(reg["runtime_root"]).resolve()),
          "dodge_rl origin differs")

    base_raw = stable_bytes(BASE / "development-000204.json")
    check(sha_bytes(base_raw) == BASE_JSON_SHA, "Accepted 204 baseline JSON digest differs")
    base_rows_raw = stable_bytes(BASE / "development-000204.jsonl")
    check(sha_bytes(base_rows_raw) == BASE_JSONL_SHA, "Accepted 204 baseline JSONL digest differs")
    check(sha(RECEIPT) == PARENT_RECEIPT_SHA, "Parent receipt digest differs")
    base_eval = json.loads(base_raw)["evaluation"]
    base_mean = sum(r["alive_frames"] for r in base_eval["rows"]) / 64
    check(base_mean == BASELINE_MEAN_ALIVE, "Accepted 204 baseline mean differs")

    journal_path = RUN / "training-episodes.jsonl"
    metrics_path = RUN / "training-metrics.jsonl"
    lr_path = RUN / "lr-transition.json"
    lr_before = sha(lr_path)
    lr = json.loads(lr_path.read_text())
    check(lr["parent_checkpoint_sha256"] == PARENT_SHA and lr["helper_sha256"] == HELPER_SHA
          and lr["arm_config_sha256"] == CONFIG_SHA and lr["effective_lr"] == 0.0001
          and lr["non_lr_fields_changed"] == [] and lr["parent_lr"] == 0.0003,
          "LR transition record differs from registration")

    parent = ckpt.load_checkpoint(Path(reg["parent"]["path"]), expected_sha256=PARENT_SHA)
    ckpt.require_complete_update(parent)
    parent_cum = parent["cumulative_counters"]
    check(parent_cum["updates"] == PARENT_UPDATES, "Parent cumulative base is not 252")

    journal, journal_sha = complete_lines(journal_path, strict=not provisional)
    consumed = consumed_length(journal_path, strict=not provisional)
    metrics, metrics_sha = complete_lines(metrics_path, strict=not provisional)
    published = []
    for update in UPDATES:
        cp = RUN / f"checkpoint-{update:06d}-candidate.pt"
        cert = RUN / f"development-{update:06d}.json"
        rows = RUN / f"development-{update:06d}.jsonl"
        side = Path(str(cp) + ".json")
        if all(p.is_file() and not p.name.endswith(".partial") for p in (cp, cert, rows, side)):
            published.append(update)
        else:
            break
    check(published and published[0] == PHASE_START, "Entry 204 certificate is not published")
    targets = tuple(published) if provisional else UPDATES
    check(provisional or len(published) == len(UPDATES), "Full mode requires all seven certificates")

    means, results = {}, {}
    for update in targets:
        cp = RUN / f"checkpoint-{update:06d}-candidate.pt"
        cert_path = RUN / f"development-{update:06d}.json"
        rows_path = RUN / f"development-{update:06d}.jsonl"
        cp_hash = sha(cp)
        cert, cert_hash = stable_json(cert_path)
        side, side_hash = stable_json(Path(str(cp) + ".json"))
        check(cert["checkpoint"] == cp.name and cert["checkpoint_sha256"] == cp_hash
              and side["checkpoint_sha256"] == cp_hash, f"Certificate/sidecar binding differs at {update}")
        check(cert["phase_update"] == update and cert["local_update"] == update - PHASE_START
              and cert["normal_training_iteration"] is True and cert["training_eligible"] is False
              and cert["promoted"] is False and cert["training_state_unchanged"] is True,
              f"Certificate phase/local/eligibility differs at {update}")
        state = ckpt.load_checkpoint(cp, expected_sha256=cp_hash)
        ckpt.require_complete_update(state)
        check(sha(cp) == cp_hash, "Checkpoint changed during audit")
        validate_candidate_metadata(state, update, parent_cumulative=parent_cum, parent_next=parent["next_episode_indices"],
                                    reg_sha=REG_SHA, config_sha=CONFIG_SHA, policy_sha=runner.POLICY_SHA,
                                    parent_run_id="D2-best180-branch-luna-20261026-r1",
                                    parent_registration_sha=runner.PARENT_REGISTRATION_SHA, run_id=runner.RUN_ID)
        if update == PHASE_START:
            check(runner.fingerprint(state["model"]) == runner.fingerprint(parent["model"])
                  and runner.fingerprint(state["rng"]) == runner.fingerprint(parent["rng"]),
                  "Entry model or RNG differs from parent")
            strip = lambda opt: {**opt, "param_groups": [{k: v for k, v in g.items() if k != "lr"} for g in opt["param_groups"]]}
            check(runner.fingerprint(strip(state["optimizer"])) == runner.fingerprint(strip(parent["optimizer"])),
                  "Entry Adam state differs beyond LR")
        rows_list, _ = complete_lines(rows_path, strict=True)
        validate_prefix_journal(journal, update, runner, parent["next_episode_indices"], state)
        survival = survival_gate.progress_passed("D2", {"D2": cert["evaluation"]})
        mean = validate_certificate(cert, rows_list, runner, survival)
        means[update] = mean
        results[str(update)] = {"mean_alive_frames": mean, "checkpoint_sha256": cp_hash,
                                "certificate_sha256": cert_hash, "sidecar_sha256": side_hash,
                                "competence_passed": cert["competence_passed"]}

    check(sha(lr_path) == lr_before, "LR transition changed during audit")
    proposed = choose_best(means)
    result = {"schema": "retained204_lr1e4_all_candidate_audit_v1",
              "status": "readonly_published_prefix_provisional" if provisional else "all_candidates_audited_pending_parent_terminal_acceptance",
              "run_id": runner.RUN_ID, "registration_sha256": REG_SHA, "updates_audited": list(targets),
              "baseline_mean_alive_frames": BASELINE_MEAN_ALIVE, "proposed_best_update": proposed,
              "candidates": results, "journal_prefix_policy": "initial+parent_abandoned+phase<=update",
              "journal_sha256": journal_sha, "metrics_sha256": metrics_sha,
              "terminal_acceptance_authority": False, "best_replacement_authority": False,
              "continuation_authority": False}
    if not provisional:
        execution, _ = stable_json(RUN / "execution-result.json")
        worker, _ = stable_json(RUN / "worker-result.json")
        check(execution.get("status") == "passed" and worker.get("status") == "completed", "Terminal status not successful")
        launcher = load_pinned_module("execute_once_frozen", PREP / "execute_once.py", LAUNCHER_SHA)
        result["frozen_launcher_terminal_checks"] = launcher.validate_outputs(reg, worker, REG_SHA)
        observation, _ = stable_json(OBS / "observation.json")
        check(observation["outer_raw_exit"] == 0 and observation["worker_raw_exit"] == 0, "Observer raw exits differ")
    # Journal is append-only: the bytes consumed at start must still be a prefix of the file.
    later = Path(journal_path).read_bytes()
    check(sha_bytes(later[:consumed]) == journal_sha, "Consumed journal prefix changed during audit")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--provisional", action="store_true")
    args = parser.parse_args(argv)
    output = Path(args.output)
    check(output.parent.resolve() == OUT.resolve(), "Output must be in the auditor directory")
    result = audit(provisional=args.provisional)
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    main()
