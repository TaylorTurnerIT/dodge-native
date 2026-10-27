"""Read-only parent leases and cooperative wall/RSS/MPS guards."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

from .identity import ROOT, require

STATE_PATH = ROOT / "learning/runs/v2-orchestration/state.json"
CUTOFF = datetime(2026, 10, 24, 13, tzinfo=timezone.utc)
RSS_LIMIT = 6 * 1024**3


class GuardStop(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def check_budget(now: datetime, seconds: int) -> None:
    require(type(seconds) is int and 0 < seconds <= 1800, "Invalid experiment budget")
    require(now + timedelta(seconds=seconds + 600) <= CUTOFF,
            "Full experiment budget plus receipt reserve does not fit cutoff")


def current_rss_bytes(pid: int) -> int:
    result = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], text=True,
                            capture_output=True, timeout=5)
    require(result.returncode == 0 and result.stdout.strip().isdigit(), "Cannot observe owned-process RSS")
    return int(result.stdout.strip()) * 1024


def peak_rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def assert_lease(run_id: str, identity_sha256: str, config_sha256: str,
                 state_path: Path = STATE_PATH) -> dict:
    lease = json.loads(state_path.read_text()).get("active_long_campaign")
    require(isinstance(lease, dict) and lease.get("run_id") == run_id,
            "Parent-owned teacher lease missing or changed")
    require(lease.get("kind") == "M3_teacher" and lease.get("authorization") == "frozen_reviewed_M3_teacher",
            "Teacher work was not authorized after frozen review")
    require(lease.get("identity_sha256") == identity_sha256 and lease.get("config_sha256") == config_sha256,
            "Parent lease identity/config mismatch")
    return lease


def emit(stream, record: dict) -> None:
    stream.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
    stream.flush()


class Guard:
    def __init__(self, *, deadline: float, run_id: str, identity_sha256: str,
                 config_sha256: str, stream, identity_check=None, mps=False,
                 state_path: Path = STATE_PATH, sample_seconds=0.5):
        self.deadline, self.run_id = deadline, run_id
        self.identity_sha256, self.config_sha256 = identity_sha256, config_sha256
        self.stream, self.identity_check, self.mps = stream, identity_check, mps
        self.state_path, self.sample_seconds = state_path, sample_seconds
        self.last_sample = float("-inf")
        self.maximum_rss = self.maximum_mps = 0

    def check(self, force=False) -> None:
        now = time.monotonic()
        if now >= self.deadline:
            raise GuardStop("Experiment wall guard expired")
        if utc_now() >= CUTOFF:
            raise GuardStop("Overnight cutoff reached")
        if force or now - self.last_sample >= self.sample_seconds:
            assert_lease(self.run_id, self.identity_sha256, self.config_sha256, self.state_path)
            if self.identity_check is not None:
                self.identity_check()
            rss = current_rss_bytes(os.getpid())
            peak = peak_rss_bytes()
            mps_bytes = 0
            if self.mps:
                import torch
                mps_bytes = int(torch.mps.driver_allocated_memory())
            self.maximum_rss = max(self.maximum_rss, rss, peak)
            self.maximum_mps = max(self.maximum_mps, mps_bytes)
            emit(self.stream, {"at_utc": utc_now().isoformat(), "monotonic": now,
                               "pid": os.getpid(), "rss_bytes": rss,
                               "self_peak_rss_bytes": peak, "mps_driver_bytes": mps_bytes})
            self.last_sample = now
            if max(rss, peak) > RSS_LIMIT:
                raise GuardStop("Observed RSS guard exceeded")
            if mps_bytes > RSS_LIMIT:
                raise GuardStop("MPS driver allocation guard exceeded")
            if time.monotonic() >= self.deadline or utc_now() >= CUTOFF:
                raise GuardStop("Guard verification finished after deadline/cutoff")


def stop_owned(process: subprocess.Popen) -> dict:
    result = {"owned_pid": process.pid, "owned_pgid": process.pid, "errors": []}
    for sig, wait_seconds in ((signal.SIGTERM, 2), (signal.SIGKILL, 5)):
        if process.poll() is not None:
            break
        try:
            os.killpg(process.pid, sig)
            result[signal.Signals(sig).name] = True
        except ProcessLookupError:
            result["exit_signal_race"] = True
        except OSError as error:
            result["errors"].append(repr(error))
        try:
            process.wait(timeout=wait_seconds)
        except subprocess.TimeoutExpired:
            continue
    result.update(exit_code=process.poll(), reaped=process.poll() is not None)
    return result
