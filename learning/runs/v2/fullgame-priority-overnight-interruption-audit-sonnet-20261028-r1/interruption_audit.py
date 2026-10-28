"""Read-only forensic audit of the interrupted run-3 attempt; `release` phase clears only its exact lease."""
from __future__ import annotations
import datetime, hashlib, importlib.util, json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
FROZEN = ROOT / "learning/runs/v2/fullgame-seed-priority-experiment-luna-20261027-r3"
H = ROOT / "learning/runs/v2/fullgame-priority-remaining-r3-bindings-sonnet-20261027-r1/fullgame-seed-priority-luna-20261027-r1-replica-2-opening_priority"
REG_SHA = "db2da67332b51c3cb3839bc8cc08afd1bcca105f64023a47cb8d8da2a0006658"
ENV_SHA = "0e9f2b9a02a139a5e752c96254b0876d88e15ca3c21015d848a2c4fc195ce25a"
RUN_ID = "fullgame-seed-priority-luna-20261027-r1-replica-2-opening_priority"
OPERATOR_SUMMARY = ROOT / "learning/runs/v2/fullgame-priority-overnight-operator-haiku-20261028-r1/operator-summary.json"
TASK_OUTPUT = Path("/private/tmp/claude-501/-Users-taylor--t3-worktrees-dodge-native-t3-c8044e79/a0315727-1bdb-4133-9c9c-57baebaa8985/tasks/b7u6rvz1o.output")
PRIOR_AUDITS = {
    "priority1": ("learning/runs/v2/fullgame-priority-remaining-r3-bindings-sonnet-20261027-r1/fullgame-seed-priority-luna-20261027-r1-replica-1-opening_priority/parent-terminal-audit.json",
                  "809b21f1928366c8f1246a47689e42345baed22079ce2c3ce7e1e234bc4f5fa9"),
    "uniform2": ("learning/runs/v2/fullgame-priority-remaining-r3-bindings-sonnet-20261027-r1/fullgame-seed-priority-luna-20261027-r1-replica-2-uniform/parent-terminal-audit.json",
                 "2a9f1125a4567048e7b332fce481582cd0b8ee86fdfc5bce6a8611a4471cca47"),
}
ABSENT_REQUIRED = ["execution-exit.json", "dispatch/observation.json", "execution-result.json",
                   "observer-finalization.json", "worker-output/worker-result.json"]


def load_binding():
    spec = importlib.util.spec_from_file_location("binding", FROZEN / "binding.py")
    sys.path.insert(0, str(FROZEN))
    module = importlib.util.module_from_spec(spec)
    sys.modules["binding"] = module
    spec.loader.exec_module(module)
    assert Path(module.__file__).resolve() == FROZEN / "binding.py"
    return module


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def snapshot(root):
    files = {}
    for p in sorted(root.rglob("*")):
        if p.is_symlink():
            files[str(p.relative_to(root))] = {"symlink": os.readlink(p)}
        elif p.is_file():
            st = p.stat()
            files[str(p.relative_to(root))] = {"sha256": sha_file(p), "bytes": st.st_size, "mtime_ns": st.st_mtime_ns}
        else:
            files[str(p.relative_to(root))] = {"dir": True}
    return files


def jsonl_info(path):
    rows, torn, last = 0, False, None
    with open(path, "rb") as f:
        data = f.read()
    for line in data.split(b"\n")[:-1]:
        last = json.loads(line)
        rows += 1
    torn = bool(data) and not data.endswith(b"\n")
    return rows, torn, last


def ps_scoped(pgids, patterns):
    out = subprocess.run(["/bin/ps", "-axo", "pid=,ppid=,pgid=,command="], capture_output=True, text=True, check=True).stdout
    me = {os.getpid(), os.getppid()}
    group_members, pattern_matches = [], []
    for line in out.splitlines():
        f = line.split(None, 3)
        if len(f) < 3 or int(f[0]) in me:
            continue
        if int(f[2]) in pgids:
            group_members.append(line.strip())
        if len(f) == 4 and any(p in f[3] for p in patterns):
            pattern_matches.append(line.strip()[:300])
    return {"command": "/bin/ps -axo pid=,ppid=,pgid=,command=", "line_count": len(out.splitlines()),
            "excluded_own_pids": sorted(me), "group_members": group_members, "pattern_matches": pattern_matches}


def pmset_evidence():
    log = subprocess.run(["pmset", "-g", "log"], capture_output=True, text=True, check=True).stdout.splitlines()
    keep = []
    for line in log:
        if line[:10] == "2026-10-28" and "00:54:00" <= line[11:19] <= "01:26:00" and line[26:].lstrip().startswith(("Sleep", "DarkWake", "Wake  ")):
            keep.append(" ".join(line.split())[:210])
    assertions = subprocess.run(["pmset", "-g", "assertions"], capture_output=True, text=True).stdout
    keys = ("PreventSystemSleep", "PreventUserIdleSystemSleep", "PreventUserIdleDisplaySleep")
    summary = {l.split()[0]: int(l.split()[1]) for l in assertions.splitlines() if l.split()[:1] and l.split()[0] in keys}
    batt = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True).stdout.splitlines()[:1]
    return {"window_local": "2026-10-28 00:54:00..01:26:00 -0500", "sleep_wake_lines": keep,
            "assertions_now": summary, "power_source_now": batt}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_exclusive(path, doc):
    data = (json.dumps(doc, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    dfd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def audit():
    b = load_binding()
    audit_path = OUT / "audit.json"
    assert not audit_path.exists()
    snap1 = snapshot(H)
    ledger_before = b.read(ROOT / "learning/runs/v2-orchestration/state.json")
    env, reg = b.load_envelope(H / "launch-envelope.json", ENV_SHA)
    assert env["registration_sha256"] == REG_SHA and b.sha(H / "registration-final.json") == REG_SHA
    assert reg["run_id"] == RUN_ID
    lease = reg["expected_lease"]
    assert ledger_before["active_long_campaign"] == lease
    assert set(lease) == {"MPS_driver_bytes", "RSS_bytes", "arm", "kind", "owner_token", "replica", "run_id", "study_id"}
    b.verify_bound(env, reg, preflight=False)
    cache = Path(reg["import_policy"]["pycache_prefix"])
    assert cache.is_dir() and not any(cache.iterdir())
    contracts = sys.modules["contracts"]
    parent_receipt = ROOT / contracts.PARENT_RECEIPT
    assert reg["parent_checkpoint_sha256"] == contracts.references.ACCEPTED_CHECKPOINT_SHA256
    assert sha_file(parent_receipt) == reg["parent_receipt_sha256"]
    candidate_equal = sha_file(H / "registration-final-candidate.json") == REG_SHA

    pe = b.read(H / "parent-execution.json")
    wl = b.read(H / "dispatch/worker-launch.json")
    assert pe["registration_sha256"] == REG_SHA and pe["envelope_sha256"] == ENV_SHA
    assert wl["registration_sha256"] == REG_SHA and wl["launcher_pid"] == pe["observer_pid"]
    pgids = {"observer": pe["observer_pgid"], "worker": wl["owned_pgid"]}
    absence = {}
    for role, pg in pgids.items():
        assert type(pg) is int and pg > 1 and pg != os.getpgrp()
        try:
            os.killpg(pg, 0)
            raise SystemExit(role + " process group still exists")
        except ProcessLookupError:
            absence[role] = {"pgid": pg, "killpg_signal0": "ProcessLookupError"}
    ps = ps_scoped(set(pgids.values()), [RUN_ID, str(H), "launch-envelope.json", "worker_cli.py", ENV_SHA, REG_SHA])
    assert not ps["group_members"] and not ps["pattern_matches"]

    missing = {rel: not (H / rel).exists() for rel in ABSENT_REQUIRED}
    assert all(missing.values())
    assert (H / "dispatch/worker.log").exists() and (H / "observer.log").stat().st_size == 0

    obs_rows, obs_torn, obs_last = jsonl_info(H / "dispatch/observer-resources.jsonl")
    obs_max = 0
    with open(H / "dispatch/observer-resources.jsonl") as f:
        for line in f:
            if line.endswith("\n"):
                obs_max = max(obs_max, json.loads(line)["aggregate_rss_bytes"])
    wres = b.worker_resources(H / "worker-output", strict=False)
    wr_rows, wr_torn, wr_last = jsonl_info(H / "worker-output/resources.jsonl")
    prog_rows, prog_torn, prog_last = jsonl_info(H / "progress-reports.jsonl")
    met_rows, met_torn, met_last = jsonl_info(H / "worker-output/training-metrics.jsonl")
    ev_rows, ev_torn, _ = jsonl_info(H / "worker-output/training-events.jsonl")
    limits = reg["limits"]
    alert = b.read(H / "progress-alert.json")
    ck_updates = [r["global_update"] for r in map(json.loads, open(H / "worker-output/training-metrics.jsonl"))]
    task_bytes = TASK_OUTPUT.read_bytes()

    op = b.read(OPERATOR_SUMMARY)
    run3 = [r for r in op["runs"] if r.get("run_id") == RUN_ID]
    priors = {}
    for name, (rel, digest) in PRIOR_AUDITS.items():
        priors[name] = {"path": rel, "sha256": digest, "actual_sha256": b.sha(ROOT / rel), "unchanged": b.sha(ROOT / rel) == digest}
        assert priors[name]["unchanged"]

    snap2 = snapshot(H)
    assert snap1 == snap2, "partial evidence changed during audit"
    assert not any(cache.iterdir())

    doc = {
        "schema": "dodge_seed_priority_interrupted_attempt_audit_v1",
        "status": "failed_interrupted_spent_incomplete_attempt",
        "classification": {"comparison_eligible": False, "training_eligible": False, "promotion_authorized": False,
                           "retry_authorized": False, "seed_replacement_authorized": False,
                           "further_attempts_under_aborted_sequence_authorized": False,
                           "terminal_conservation_claimed": False, "parent_terminal_audit_py_called": False},
        "audited_at_utc": now(),
        "run_id": RUN_ID, "registration_sha256": REG_SHA, "envelope_sha256": ENV_SHA,
        "registration_final_equals_candidate": candidate_equal,
        "expected_lease": lease,
        "ledger_active_lease_equals_expected_lease": True,
        "bound_verification": {"module_origin": str(FROZEN / "binding.py"), "load_envelope": True,
                               "verify_bound_preflight_false": True, "pins_checked": len(env["pins"]),
                               "pin_keys_sha256": hashlib.sha256("\n".join(sorted(env["pins"])).encode()).hexdigest(),
                               "parent_checkpoint_sha256": reg["parent_checkpoint_sha256"],
                               "parent_receipt_path": str(parent_receipt), "parent_receipt_sha256": reg["parent_receipt_sha256"],
                               "checkpoint_equals_accepted_constant_via_validate_static": True, "parent324_unchanged": True,
                               "interpreter_resolved": env["interpreter_resolved"], "interpreter_sha256": env["interpreter_sha256"]},
        "bytecode_cache": {"path": str(cache), "empty": True},
        "process_groups": {"recorded": {"observer_pid": pe["observer_pid"], "observer_pgid": pe["observer_pgid"],
                                        "worker_pid": wl["worker_pid"], "worker_pgid": wl["owned_pgid"],
                                        "worker_start_new_session": wl["start_new_session"]},
                           "absence": absence, "ps_scoped": ps,
                           "note": "Absence proven at audit time only; says nothing about how or when processes ended."},
        "missing_receipts": {"absent_files": missing,
                             "raw_observer_exit_code": "unknown", "observer_directly_reaped": "unknown",
                             "worker_raw_exit": "unknown", "worker_directly_reaped": "unknown",
                             "terminating_signal": "unknown", "postflight_inputs_unchanged": "unknown",
                             "terminal_update_60": False, "final_integrity_checkpoint": "absent (first checkpoint at update 12)"},
        "observed_progress": {"progress_report_rows": prog_rows, "last_progress_completed_updates": prog_last["completed_updates"],
                              "last_progress_elapsed_seconds": prog_last["elapsed_seconds"], "last_progress_phase": prog_last["phase"],
                              "total_updates": prog_last["total_updates"],
                              "training_metrics_rows": met_rows, "training_metrics_global_updates": ck_updates,
                              "training_events_rows": ev_rows,
                              "torn_tails": {"progress": prog_torn, "metrics": met_torn, "events": ev_torn,
                                             "observer_resources": obs_torn, "worker_resources": wr_torn},
                              "progress_alert": {"reason": alert["reason"], "status": alert["status"],
                                                 "elapsed_seconds": alert["elapsed_seconds"], "training_signalled": alert["training_signalled"]},
                              "reward_or_performance_inspected": False},
        "resource_samples": {"observer_rows": obs_rows, "observer_last_elapsed_seconds": obs_last["elapsed_seconds"],
                             "observer_last_monotonic": obs_last["monotonic"],
                             "observer_aggregate_rss_max_bytes": obs_max,
                             "worker_resource_rows": wres["samples"], "worker_peak_rss_bytes": wres["peak_rss_bytes"],
                             "worker_peak_mps_driver_bytes": wres["peak_mps_driver_bytes"],
                             "worker_last_sample": wr_last,
                             "limits": {"rss_bytes": limits["rss_bytes"], "mps_bytes": limits["mps_bytes"],
                                        "total_seconds": limits["total_seconds"], "work_seconds": limits["work_seconds"]},
                             "rss_limit_breached": max(obs_max, wres["peak_rss_bytes"] or 0) > limits["rss_bytes"],
                             "mps_limit_breached": (wres["peak_mps_driver_bytes"] or 0) > limits["mps_bytes"]},
        "cause_evidence": {
            "launch_wrapper": {"native_background_task_id": "b7u6rvz1o", "output_file": str(TASK_OUTPUT),
                               "output_sha256": hashlib.sha256(task_bytes).hexdigest(), "output_ends_with": task_bytes.rstrip().splitlines()[-1].decode(errors="replace"),
                               "reported_by_root": {"tool_launch_utc": "2026-10-28T05:54:57.695Z",
                                                    "t3_stopped_notification_utc": "2026-10-28T06:25:23.809Z",
                                                    "elapsed_wall_seconds": 1825.8, "operator_omitted_long_timeout_default_30min": True}},
            "timing": {"parent_started_monotonic": pe["started"], "observer_last_monotonic": obs_last["monotonic"],
                       "active_monotonic_seconds_to_last_observer_row": round(obs_last["monotonic"] - pe["started"], 3),
                       "progress_last_mtime_local": "2026-10-28 01:08", "observer_resources_last_mtime_local": "2026-10-28 01:08",
                       "launch_local": "2026-10-28 00:54:59 -0500"},
            "pmset": pmset_evidence(),
            "findings": [
                "Wrapper output ends '[killed]'; wrapper stop at wall 1825.8 s is consistent with the 30 min default timeout.",
                "Monitored active time stopped near 110 s while wall time ran ~30 min; pmset shows repeated Idle/Maintenance Sleep with AC attached during the window.",
                "Launcher/observer were start_new_session children of the wrapper; whether the stop signalled or reaped them, and which signal, is not recorded.",
            ],
            "limits": [
                "No raw exit code, signal, or reap record exists for observer or worker.",
                "pmset sleep/wake log is correlation, not proof that sleep alone terminated the workers.",
                "Resource limits were not breached per recorded samples; no other fault evidence found.",
            ]},
        "operator_summary_reconciliation": {
            "path": str(OPERATOR_SUMMARY), "sha256": b.sha(OPERATOR_SUMMARY),
            "run3_entries": len(run3), "entries_duplicate": len(run3) > 1,
            "stale_claim": "summary notes say ledger rl_followup_experiments active_run_id remains run1",
            "actual_live_ledger_before_closure": {"active_run_id": ledger_before["rl_followup_experiments"]["active_run_id"],
                                                  "current_launch_authorized": ledger_before["rl_followup_experiments"]["current_launch_authorized"],
                                                  "active_long_campaign_run_id": ledger_before["active_long_campaign"]["run_id"]},
            "original_summary_preserved": True},
        "prior_successful_audits_unchanged": priors,
        "planned_training_endpoints_complete": "3/6 (original uniform1, priority1, uniform2)",
        "unstarted_paths_untouched": ["replica-3-uniform", "replica-3-opening_priority"],
        "evidence_snapshot": {"file_count": len(snap1), "stable_across_two_snapshots": True, "files": snap1},
        "script": {"path": str(Path(__file__)), "sha256": sha_file(__file__)},
    }
    write_exclusive(audit_path, doc)
    print("audit written", sha_file(audit_path))


def release():
    b = load_binding()
    audit_path, rel_path = OUT / "audit.json", OUT / "lease-release.json"
    assert audit_path.exists() and not rel_path.exists()
    a = b.read(audit_path)
    assert a["status"] == "failed_interrupted_spent_incomplete_attempt"
    env, reg = b.load_envelope(H / "launch-envelope.json", ENV_SHA)
    lease = reg["expected_lease"]
    assert lease == a["expected_lease"]
    # re-prove absence at release time
    for role in ("observer", "worker"):
        pg = a["process_groups"]["recorded"][role + "_pgid"]
        try:
            os.killpg(pg, 0)
            raise SystemExit(role + " group exists; refusing release")
        except ProcessLookupError:
            pass
    ps = ps_scoped({a["process_groups"]["recorded"]["observer_pgid"], a["process_groups"]["recorded"]["worker_pgid"]}, [RUN_ID, "worker_cli.py", ENV_SHA])
    assert not ps["group_members"] and not ps["pattern_matches"]
    sp = ROOT / "learning/runs/v2-orchestration/state.json"
    state = b.read(sp)
    if state["active_long_campaign"] != lease:
        raise SystemExit("ledger lease differs from expected; refusing release")
    before = json.loads(json.dumps(state))
    audit_sha = b.sha(audit_path)
    state["active_long_campaign"] = None
    rl = state["rl_followup_experiments"]
    rl["current_launch_authorized"] = False
    rl["active_run_id"] = None
    rl["status"] = "sequence_stopped_on_fault"
    rl["sequence_stopped_on_fault"] = {
        "run_id": RUN_ID, "classification": a["status"], "audit": str(audit_path), "audit_sha256": audit_sha,
        "further_attempts_authorized_by_aborted_sequence": False, "comparison_eligible": False,
        "unstarted_runs": ["replica-3-uniform", "replica-3-opening_priority"]}
    state["status"] = "sequence_stopped_on_fault"
    state["next_actions"] = [
        "Overnight five-run sequence aborted on fault at run 3 (interrupted wrapper); no further launches, retries, or seed replacement under it.",
        "Any continuation needs fresh user approval and a new registered plan with idle-sleep prevention and a wrapper timeout above total+cleanup.",
        "Keep D4/D5 unopened and parent324 unpromoted."]
    state["last_update_at_utc"] = now()
    expected_changed = {"active_long_campaign", "rl_followup_experiments", "status", "next_actions", "last_update_at_utc"}
    changed = {k for k in set(before) | set(state) if before.get(k) != state.get(k)}
    assert changed <= expected_changed, changed
    import tempfile
    fd, tmp = tempfile.mkstemp(prefix=".interrupted-state-pending-", dir=sp.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, sort_keys=True, indent=2, allow_nan=False); f.write("\n"); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, sp)
        dfd = os.open(sp.parent, os.O_RDONLY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    after = b.read(sp)
    assert after["active_long_campaign"] is None
    write_exclusive(rel_path, {"status": "exact_failed_lease_cleared_after_durable_interruption_audit",
                               "audit_path": str(audit_path), "audit_sha256": audit_sha,
                               "released_lease": lease, "state_top_level_keys_changed": sorted(changed),
                               "state_sha256_after": b.sha(sp), "released_at_utc": now()})
    print("released", b.sha(rel_path))


if __name__ == "__main__":
    {"audit": audit, "release": release}[sys.argv[1]]()
