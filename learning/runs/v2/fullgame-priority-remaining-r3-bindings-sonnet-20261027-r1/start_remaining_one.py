"""Parent dispatch for exactly one of the remaining seed-priority r3 runs; no retries.

PROSPECTIVE: refuses to run until the parent promotes registration-index.json and
parent-gates.json and writes a fresh user-authorization document. None exist in
the preparation packet. `gate_check` is read-only; `launch` is the only mutator.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import remaining_plan as p

HERE = p.HERE
SOURCE = p.R3
sys.path.insert(0, str(SOURCE))
import binding as b


def replace_state(path, state):
    pending = Path(path).with_name("state.seed-priority-remaining.pending.json")
    b.save(pending, state)
    os.replace(pending, path)
    descriptor = os.open(Path(path).parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def gate_check(base, run_id, index_sha256, gates_sha256, *, state_path=None):
    """Read-only. Returns (row, reg, gates, auth) or raises ValueError; touches nothing."""
    base = Path(base)
    index_path, gates_path = base / "registration-index.json", base / "parent-gates.json"
    b.need(index_path.is_file() and gates_path.is_file(),
           "prospective packet: parent has not promoted index and gates; NO launch authority")
    b.check_pins({str(index_path): index_sha256, str(gates_path): gates_sha256})
    index, gates = b.read(index_path), b.read(gates_path)
    proposal_index = b.read(base / "registration-index-proposal.json")
    b.need(index.get("status") == p.INDEX_PROMOTED_STATUS and index.get("launch_authority") is False
           and index["runs"] == proposal_index["runs"], "index is not the reviewed promoted proposal rows")
    selected = [row for row in index["runs"] if row["run_id"] == run_id]
    b.need(len(selected) == 1 and run_id != p.FIRST_RUN_ID, "run is not in the exact remaining index")
    row = selected[0]
    home = base / run_id
    b.need(Path(row["registration"]) == home / "registration-final.json"
           and Path(row["registration_candidate"]) == home / "registration-final-candidate.json",
           "registration must live in its own run directory")
    b.need(gates.get("schema") == p.GATES_SCHEMA and gates.get("status") == p.GATES_APPROVED_STATUS,
           "parent gates absent or only a proposal")
    b.need(gates["source_manifest_sha256"] == row["source_manifest_sha256"] == p.SOURCE_MANIFEST_SHA256
           and gates["runtime_manifest_sha256"] == row["runtime_manifest_sha256"] == p.RUNTIME_MANIFEST_SHA256,
           "source/runtime gate differs")
    proposal_path = base / "parent-gates-proposal.json"
    proposal = b.read(proposal_path)
    b.need(gates.get("proposal_sha256") == b.sha(proposal_path)
           and all(gates["pins"].get(path) == digest for path, digest in proposal["pins"].items()),
           "approved gates must carry every reviewed proposal pin")
    b.check_pins(gates["pins"])
    b.need(not any(Path(path).name == "state.json" for path in gates["pins"]),
           "mutable ledger must not be pinned as immutable history")
    b.need(gates["pins"].get(str(p.SOURCE_ACCEPTANCE)) == p.SOURCE_ACCEPTANCE_SHA256,
           "independent exact-source acceptance pin missing")
    b.need(gates["pins"].get(str(p.FIRST_HOME / "parent-terminal-audit.json")) == p.FIRST_AUDIT_SHA256,
           "first uniform terminal audit pin missing")
    auth_path = Path(gates["authorization_path"])
    b.need(auth_path.parent == base and gates["pins"].get(str(auth_path)) == gates["authorization_sha256"],
           "parent authorization document must be pinned in gates")
    auth = b.read(auth_path)
    b.need(auth.get("schema") == p.AUTH_SCHEMA and auth.get("retries") == 0
           and isinstance(auth.get("user_message"), str) and auth["user_message"].strip()
           and auth.get("source_manifest_sha256") == p.SOURCE_MANIFEST_SHA256
           and {"run_id": run_id, "registration_sha256": row["registration_sha256"]} in auth.get("runs", []),
           "fresh user authorization does not name this exact run and registration")
    b.check_pins({row["registration_candidate"]: row["registration_sha256"]})
    final = Path(row["registration"])
    if final.exists():
        b.need(b.sha(final) == row["registration_sha256"], "registration-final differs from candidate")
    reg = b.read(row["registration_candidate"])
    b.need(reg["run_id"] == run_id and reg["launch_authority"] is True and reg["status"] == "parent_registered",
           "candidate is not the parent-registered form")
    for key, name in (("output", "worker-output"), ("attempt_claim_path", "attempt.claimed"),
                      ("launch_marker_path", "launch.claimed")):
        b.need(Path(reg[key]) == home / name, "registration path escapes its run directory: " + key)
    b.need(Path(reg["import_policy"]["pycache_prefix"]) == home / "empty-pycache", "cache path differs")
    b._contracts().validate_static(reg, startup=False)
    dependency_inventory = b.read(gates["dependency_inventory_path"])
    b.need(b.sha(gates["dependency_inventory_path"]) == gates["dependency_inventory_sha256"],
           "dependency inventory differs")
    for key in ("output", "attempt_claim_path", "launch_marker_path"):
        b.need(not os.path.lexists(reg[key]), "one-use path already spent: " + key)
    for name in ("dispatch", "launch-envelope.json", "launch-approval.json", "parent-preflight.json",
                 "parent-execution.json", "execution-exit.json", "observer.log"):
        b.need(not os.path.lexists(home / name), "parent execution path already spent: " + name)
    state = b.read(state_path or reg["state_path"])
    b.need(state.get("active_long_campaign") is None and state.get("active_inference_diagnostic") is None,
           "conflicting campaign")
    b.need(not state.get("training_hold", {}).get("active", False), "user training hold is active")
    return row, reg, gates, dependency_inventory


def materialize(row):
    """Byte-exact exclusive copy of the reviewed candidate; idempotent only for equal bytes."""
    final, candidate = Path(row["registration"]), Path(row["registration_candidate"])
    if not final.exists():
        descriptor = os.open(final, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(candidate.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
    b.need(b.sha(final) == row["registration_sha256"], "materialized registration differs")


def launch(args):
    row, reg, gates, dependency_inventory = gate_check(HERE, args.run_id, args.index_sha256, args.gates_sha256)
    home = HERE / args.run_id
    contracts = b._contracts()
    contracts.cache_check(reg)
    dependency_pins = {path: item["sha256"] for path, item in dependency_inventory["pins"].items()}
    b.check_pins(dependency_pins)
    materialize(row)
    control = home / "dispatch"
    state = b.read(reg["state_path"])
    b.save(home / "launch-approval.json", contracts.launch_approval_document(row["registration_sha256"], reg))
    b.save(home / "parent-preflight.json", dict(registration_sha256=row["registration_sha256"],
           static_inputs="passed", dependency_pins_checked=len(dependency_pins), cache="passed",
           parent_gates_sha256=args.gates_sha256, claim_consumed=False))
    started = time.monotonic()
    state["active_long_campaign"] = reg["expected_lease"]
    state["last_update_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    state["rl_followup_experiments"].update(status="registered_seed_priority_trial_running",
           active_run_id=reg["run_id"], current_launch_authorized=True)
    replace_state(reg["state_path"], state)
    contracts.validate_static(reg, startup=True)
    pins = {str(SOURCE / name): digest for name, digest in b.read(SOURCE / "source-manifest.json")["files"].items()}
    pins.update(gates["pins"])
    pins.update(dependency_pins)
    envelope = dict(schema="dodge_seed_priority_worker_envelope_v1", status="parent_bound_exactly_one_run",
        registration=row["registration"], registration_sha256=row["registration_sha256"],
        launch_approval=str(home / "launch-approval.json"), launch_approval_sha256=b.sha(home / "launch-approval.json"),
        source_acceptance=str(p.SOURCE_ACCEPTANCE), source_acceptance_sha256=b.sha(p.SOURCE_ACCEPTANCE),
        control=str(control), cancel_path=str(home / "cancel"), started=started, pins=pins,
        interpreter_resolved=str(Path(reg["interpreter"]).resolve()),
        interpreter_sha256=b.sha(Path(reg["interpreter"]).resolve()))
    envelope_path = home / "launch-envelope.json"
    b.save(envelope_path, envelope)
    envelope_sha = b.sha(envelope_path)
    b.save(reg["launch_marker_path"], dict(schema="dodge_seed_priority_parent_spent_launch_marker_v1",
           registration_sha256=row["registration_sha256"], run_id=reg["run_id"], started=started))
    loaded, _ = b.load_envelope(envelope_path, envelope_sha)
    b.verify_bound(loaded, reg, preflight=True)
    command = [reg["interpreter"], "-B", str(SOURCE / "launch.py"),
               "--envelope", str(envelope_path), "--envelope-sha256", envelope_sha]
    environment = os.environ.copy()
    environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHONPYCACHEPREFIX=reg["import_policy"]["pycache_prefix"])
    with (home / "observer.log").open("x") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   env=environment, cwd=p.ROOT, start_new_session=True)
        b.save(home / "parent-execution.json", dict(observer_pid=process.pid, observer_pgid=process.pid,
               command=command, registration_sha256=row["registration_sha256"],
               envelope_sha256=envelope_sha, started=started))
        print(json.dumps(dict(status="seed_priority_training_launched_exactly_once",
                              run_id=reg["run_id"], observer_pid=process.pid)), flush=True)
        position, last_update = 0, -1
        with (home / "progress-reports.jsonl").open("x") as reports:
            while process.poll() is None:
                worker_log = control / "worker.log"
                if worker_log.exists():
                    with worker_log.open() as stream:
                        stream.seek(position)
                        while True:
                            offset = stream.tell()
                            line = stream.readline()
                            if not line or not line.endswith("\n"):
                                position = offset
                                break
                            position = stream.tell()
                            try:
                                progress = json.loads(line)
                            except ValueError:
                                continue
                            if progress.get("schema") != "progressive1000_progress_v1":
                                continue
                            reports.write(line)
                            reports.flush()
                            if progress["completed_updates"] != last_update:
                                print(json.dumps(progress, sort_keys=True), flush=True)
                                last_update = progress["completed_updates"]
                time.sleep(.5)
            code = process.wait()
    b.save(home / "execution-exit.json", dict(raw_observer_exit_code=code,
           observer_directly_reaped=True, registration_sha256=row["registration_sha256"],
           elapsed_seconds=time.monotonic() - started, parent_terminal_audit_pending=True))
    print(json.dumps(dict(status="seed_priority_terminal_parent_audit_pending", raw_exit=code)), flush=True)
    return int(code != 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--gates-sha256", required=True)
    return launch(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
