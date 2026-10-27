"""Run the reviewed original-engine M0 experiments once, retaining failures."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time


ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "learning/runs/v2-orchestration/state.json"
RSS_LIMIT = 6 * 1024**3


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def preflight() -> tuple[dict, Path, Path, dict]:
    state = json.loads(STATE.read_text())
    worktree = Path(state["tasks"]["milestone0_r2"]["worktree"])
    manifest = json.loads((worktree / "target/v2-m0-review-r2/final-manifest.json").read_text())
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=worktree, text=True).strip() != manifest["head"]:
        raise RuntimeError("original-engine HEAD changed")
    if subprocess.check_output(["git", "diff", "HEAD", "--"], cwd=worktree):
        raise RuntimeError("original tracked source changed")
    for relative, expected in manifest["new_source_and_docs_sha256"].items():
        if digest(worktree / relative) != expected:
            raise RuntimeError(f"frozen harness changed: {relative}")
    executable = Path(manifest["executable"])
    if digest(executable) != manifest["executable_sha256"]:
        raise RuntimeError("frozen executable changed")
    return state, worktree, executable, manifest


def stop_owned(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def phase(name: str, command: list[str], worktree: Path, evidence: Path, seconds: int) -> dict:
    result = {"name": name, "command": command, "cwd": str(worktree), "started_at_utc": utc(),
              "native_wall_limit_seconds": seconds, "watchdog_grace_seconds": 15,
              "rss_limit_bytes": RSS_LIMIT, "peak_observed_rss_bytes": 0}
    write_json(evidence / f"{name}-receipt.json", result)
    started = time.monotonic()
    with (evidence / f"{name}.log").open("xb") as log, (evidence / f"{name}-resources.jsonl").open("x") as samples:
        process = subprocess.Popen(command, cwd=worktree, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        result["owned_pid"] = process.pid
        write_json(evidence / f"{name}-receipt.json", result)
        try:
            while process.poll() is None:
                rss = subprocess.run(["ps", "-o", "rss=", "-p", str(process.pid)], capture_output=True, text=True, check=False)
                if rss.returncode == 0 and rss.stdout.strip():
                    observed = int(rss.stdout.strip()) * 1024
                    result["peak_observed_rss_bytes"] = max(result["peak_observed_rss_bytes"], observed)
                    samples.write(json.dumps({"utc": utc(), "elapsed_seconds": time.monotonic() - started, "rss_bytes": observed}) + "\n")
                    samples.flush()
                    if observed > RSS_LIMIT:
                        result["supervisor_failure"] = "observed RSS threshold exceeded"
                        stop_owned(process)
                        break
                if time.monotonic() - started > seconds + 15:
                    result["supervisor_failure"] = "native wall limit plus watchdog grace exceeded"
                    stop_owned(process)
                    break
                time.sleep(1)
        except BaseException as error:
            result["supervisor_failure"] = f"{type(error).__name__}: {error}"
            stop_owned(process)
            raise
        finally:
            result.update(exit_code=process.wait(), elapsed_seconds=time.monotonic() - started, finished_at_utc=utc())
            write_json(evidence / f"{name}-receipt.json", result)
    if result["exit_code"] != 0 or "supervisor_failure" in result:
        raise RuntimeError(f"{name} failed; retained receipt and native partial records")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    options = parser.parse_args()
    state, worktree, executable, manifest = preflight()
    if options.check_only:
        print(json.dumps({"status": "identity_verified", "worktree": str(worktree), "executable_sha256": manifest["executable_sha256"]}))
        return
    if state["baseline_campaign_plan"]["status"] != "ready_to_launch":
        raise RuntimeError("parent review gate has not authorized campaign launch")
    cutoff = dt.datetime.fromisoformat(state["overnight_cutoff_utc"])
    # Native benchmark and campaign budgets, both watchdog graces, plus ten
    # minutes for receipts must fit before the user's overnight cutoff.
    if (cutoff - dt.datetime.now(dt.timezone.utc)).total_seconds() < 60 + 3600 + 30 + 600:
        raise RuntimeError("full experiment budget and receipt reserve do not fit before cutoff")
    evidence = ROOT / "learning/runs/v2/milestone0-campaign-r2"
    outputs = [worktree / "target/v2-m0-profile-r2", worktree / "target/v2-m0-baselines-r2"]
    if any(path.exists() for path in outputs):
        raise RuntimeError("experiment destination already exists; no retry or overwrite")
    evidence.mkdir(parents=True, exist_ok=False)
    receipt = {"status": "running", "started_at_utc": utc(), "script_sha256": digest(Path(__file__)),
               "plan_sha256": digest(ROOT / "docs/v2-baseline-campaign.md"),
               "state_sha256_at_launch": digest(STATE), "head": manifest["head"],
               "executable_sha256": manifest["executable_sha256"], "phases": []}
    write_json(evidence / "supervisor.json", receipt)
    common = [str(executable), "--action-repeat", "4", "--difficulty", "2", "--patterns", "true", "--powerups", "true"]
    try:
        receipt["phases"].append(phase("profile", common + ["--benchmark-seconds", "10", "--threads", "4", "--max-seconds", "60", "--output-dir", str(outputs[0])], worktree, evidence, 60))
        write_json(evidence / "supervisor.json", receipt)
        preflight()
        receipt["phases"].append(phase("baselines", common + ["--episodes", "1000", "--max-frames", "18000", "--max-seconds", "3600", "--output-dir", str(outputs[1])], worktree, evidence, 3600))
        preflight()
        receipt["status"] = "native_experiments_complete_parent_audit_pending"
    except BaseException as error:
        receipt.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        receipt["finished_at_utc"] = utc()
        write_json(evidence / "supervisor.json", receipt)


if __name__ == "__main__":
    main()
