"""Parent dispatch for one reviewed seed-priority registration; no retries."""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT / "learning/runs/v2/fullgame-seed-priority-experiment-luna-20261027-r3"
sys.path.insert(0, str(SOURCE))
import binding as b


def replace_state(path, state):
    pending = Path(path).with_name("state.seed-priority-parent.pending.json")
    b.save(pending, state)
    os.replace(pending, path)
    descriptor = os.open(Path(path).parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--gates-sha256", required=True)
    args = parser.parse_args()
    index_path = HERE / "registration-index.json"
    gates_path = HERE / "parent-gates.json"
    b.check_pins({str(index_path): args.index_sha256, str(gates_path): args.gates_sha256})
    index, gates = b.read(index_path), b.read(gates_path)
    selected = [row for row in index["runs"] if row["run_id"] == args.run_id]
    b.need(len(selected) == 1, "run is not in the exact parent index")
    row = selected[0]
    home = Path(row["registration"]).parent
    b.need(home.parent == HERE, "run output must be parent-owned")
    b.check_pins(gates["pins"])
    b.need(gates["status"] == "approved_exactly_once_per_registered_run", "parent gates absent")
    b.need(gates["source_manifest_sha256"] == row["source_manifest_sha256"], "source gate differs")
    b.check_pins({row["registration"]: row["registration_sha256"]})
    reg = b.read(row["registration"])
    contracts = b._contracts()
    contracts.validate_static(reg, startup=False)
    contracts.cache_check(reg)
    dependency_inventory = b.read(gates["dependency_inventory_path"])
    dependency_pins = {path: item["sha256"] for path, item in dependency_inventory["pins"].items()}
    b.check_pins(dependency_pins)
    for key in ("output", "attempt_claim_path", "launch_marker_path"):
        b.need(not os.path.lexists(reg[key]), "one-use path already spent: " + key)
    control = home / "dispatch"
    b.need(not control.exists(), "observer dispatch already spent")
    for name in ("launch-envelope.json", "parent-execution.json", "execution-exit.json", "observer.log"):
        b.need(not os.path.lexists(home / name), "parent execution path already spent: " + name)
    state = b.read(reg["state_path"])
    b.need(state.get("active_long_campaign") is None and state.get("active_inference_diagnostic") is None,
           "conflicting campaign")
    b.need(not state.get("training_hold", {}).get("active", False), "user training hold is active")
    acceptance = HERE / "source-acceptance.json"
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
        source_acceptance=str(acceptance), source_acceptance_sha256=b.sha(acceptance),
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
                                   env=environment, cwd=ROOT, start_new_session=True)
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


if __name__ == "__main__":
    raise SystemExit(main())
