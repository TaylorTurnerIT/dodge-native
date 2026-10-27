"""Read-only parent leases and cooperative wall/RSS/MPS guards."""
from __future__ import annotations

from contextlib import contextmanager
import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import threading
import time

from .identity import ROOT, require

STATE_PATH = ROOT / "learning/runs/v2-orchestration/state.json"
CUTOFF = datetime(2026, 10, 24, 13, tzinfo=timezone.utc)
RSS_LIMIT = 6 * 1024**3
_UNSET = object()


class GuardStop(RuntimeError):
    pass


class SignalCancellation(BaseException):
    """A handled cancellation signal, retained by the caller's failure receipt."""

    def __init__(self, signal_number: int):
        self.signal_number = signal_number
        super().__init__(f"Cancellation requested by {signal.Signals(signal_number).name}")


class _CancellationSignals:
    def __init__(self):
        self.deferred = False
        self.signal_number = None
        self.pending_signal = None

    def defer(self) -> None:
        """Keep repeated cancellation from interrupting bounded cleanup."""
        self.deferred = True

    def resume(self) -> None:
        """Deliver a signal deferred across assignment of an owned worker PID."""
        if self.pending_signal is not None:
            number = self.pending_signal
            self.pending_signal = None
            self.defer()
            raise SignalCancellation(number)
        self.deferred = False

    def handle(self, signal_number, _frame) -> None:
        if self.signal_number is None:
            self.signal_number = signal_number
        if self.deferred:
            if self.pending_signal is None:
                self.pending_signal = signal_number
            return
        self.defer()
        raise SignalCancellation(signal_number)


@contextmanager
def cancellation_signals():
    """Temporarily handle SIGTERM/SIGINT on the foreground main thread.

    The first signal raises through ordinary work; further signals are deferred
    until the caller finishes bounded cleanup and exits this context. Existing
    handlers are restored even when setup or the protected call fails.
    """
    require(threading.current_thread() is threading.main_thread(),
            "Teacher signal supervision requires the main thread")
    cancellation = _CancellationSignals()
    previous = {}
    try:
        for number in (signal.SIGTERM, signal.SIGINT):
            previous[number] = signal.getsignal(number)
            signal.signal(number, cancellation.handle)
        yield cancellation
    finally:
        for number, handler in reversed(tuple(previous.items())):
            signal.signal(number, handler)


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
                 state_path: Path = STATE_PATH, *, phase=None,
                 expected_parent_receipt=_UNSET) -> dict:
    lease = json.loads(state_path.read_text()).get("active_long_campaign")
    require(isinstance(lease, dict) and lease.get("run_id") == run_id,
            "Parent-owned teacher lease missing or changed")
    require(lease.get("kind") == "M3_teacher" and lease.get("authorization") == "frozen_reviewed_M3_teacher",
            "Teacher work was not authorized after frozen review")
    require(lease.get("identity_sha256") == identity_sha256 and lease.get("config_sha256") == config_sha256,
            "Parent lease identity/config mismatch")
    phase = lease.get("phase") if phase is None else phase
    require(phase in {"probe", "pilot", "D1", "D2", "D3"}, "Parent lease phase missing or invalid")
    require(lease.get("phase") == phase, "Parent lease phase changed")
    receipt = lease.get("parent_terminal_receipt")
    if expected_parent_receipt is not _UNSET and receipt != expected_parent_receipt:
        raise GuardStop("Parent terminal receipt changed during run")
    if phase in {"D1", "D2", "D3"}:
        require(isinstance(receipt, dict), "Parent terminal receipt missing for curriculum phase")
        require(receipt.get("phase") == {"D1": "pilot", "D2": "D1", "D3": "D2"}[phase],
                "Parent terminal receipt source phase differs")
    else:
        require("parent_terminal_receipt" not in lease, "Unexpected parent terminal receipt for fresh phase")
    return lease


def emit(stream, record: dict) -> None:
    stream.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
    stream.flush()


class Guard:
    def __init__(self, *, deadline: float, run_id: str, identity_sha256: str,
                 config_sha256: str, stream, identity_check=None, mps=False,
                 state_path: Path = STATE_PATH, sample_seconds=0.5, phase=None,
                 expected_parent_receipt=_UNSET):
        self.deadline, self.run_id = deadline, run_id
        self.identity_sha256, self.config_sha256 = identity_sha256, config_sha256
        self.stream, self.identity_check, self.mps = stream, identity_check, mps
        self.state_path, self.sample_seconds = state_path, sample_seconds
        self.last_sample = float("-inf")
        self.maximum_rss = self.maximum_mps = 0
        self.phase = phase
        self.expected_parent_receipt = (_UNSET if expected_parent_receipt is _UNSET
                                        else copy.deepcopy(expected_parent_receipt))

    def check(self, force=False) -> None:
        now = time.monotonic()
        if now >= self.deadline:
            raise GuardStop("Experiment wall guard expired")
        if utc_now() >= CUTOFF:
            raise GuardStop("Overnight cutoff reached")
        lease = assert_lease(self.run_id, self.identity_sha256, self.config_sha256, self.state_path,
                             phase=self.phase, expected_parent_receipt=self.expected_parent_receipt)
        if self.expected_parent_receipt is _UNSET:
            self.expected_parent_receipt = copy.deepcopy(lease.get("parent_terminal_receipt"))
        if force or now - self.last_sample >= self.sample_seconds:
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
    """Terminate the new-session worker's exact process group and reap its leader.

    A leader can exit while children remain in its group, so leader exit never
    suppresses group termination. SIGTERM allows five seconds for a diagnostic
    checkpoint; SIGKILL bounds an uncooperative worker's final reap.
    """
    require(type(process.pid) is int and process.pid > 1 and process.pid != os.getpgrp(),
            "Refusing unsafe owned process group")
    result = {"owned_pid": process.pid, "owned_pgid": process.pid, "errors": []}
    def poll():
        try:
            return process.poll()
        except BaseException as error:
            result["errors"].append({"operation": "poll", "error": repr(error)})
            return None
    def group_exists():
        try:
            os.killpg(process.pid, 0)
            return True
        except ProcessLookupError:
            return False
        except BaseException as error:
            result["errors"].append({"operation": "group_probe", "error": repr(error)})
            return True

    for sig, wait_seconds in ((signal.SIGTERM, 5), (signal.SIGKILL, 5)):
        signal_started = time.monotonic()
        group_gone = False
        try:
            os.killpg(process.pid, sig)
            result[signal.Signals(sig).name] = True
        except ProcessLookupError:
            result["exit_signal_race"] = True
            group_gone = True
        except BaseException as error:
            result["errors"].append(repr(error))
        try:
            process.wait(timeout=wait_seconds)
        except subprocess.TimeoutExpired:
            continue
        except BaseException as error:
            result["errors"].append({"operation": "wait", "error": repr(error)})
        if sig == signal.SIGTERM and poll() is not None:
            # wait() can return immediately after leader exit. Preserve the
            # same bounded cooperative opportunity for any remaining children.
            for _ in range(50):
                if group_gone or not group_exists():
                    group_gone = True
                    break
                if time.monotonic() - signal_started >= wait_seconds:
                    break
                try:
                    time.sleep(0.1)
                except BaseException as error:
                    result["errors"].append({"operation": "group_grace", "error": repr(error)})
                    break
            if group_gone:
                break
    code = poll()
    result.update(exit_code=code, reaped=code is not None)
    return result
