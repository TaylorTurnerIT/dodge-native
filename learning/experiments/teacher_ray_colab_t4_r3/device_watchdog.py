"""Linux direct-child supervisor for ONE synthetic subprocess, not a launcher.

Local CLI assignment/time/cost ownership belongs to the coordinator. This second
guard bounds the remote subprocess even if the CLI connection disappears.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def write_once(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False)
        stream.write("\n"); stream.flush(); os.fsync(stream.fileno())


def group_RSS(group):
    """Linux resident set summed over the owned process group, in bytes."""
    members = {}
    for directory in Path("/proc").iterdir():
        if not directory.name.isdigit():
            continue
        try:
            stat = (directory / "stat").read_text().rsplit(")", 1)[1].split()
            if int(stat[2]) == group:
                pages = int((directory / "statm").read_text().split()[1])
                members[int(directory.name)] = pages * os.sysconf("SC_PAGE_SIZE")
        except FileNotFoundError:
            continue  # Process exited between enumeration and read.
    return members


def CUDA_process_bytes(members):
    """Driver-reported resident GPU memory; distinct from Torch's allocator."""
    result = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=pid,used_gpu_memory", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True, timeout=3)
    total = 0
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 2 or not all(field.isdigit() for field in fields):
            raise ValueError("Unavailable CUDA driver memory observation")
        if int(fields[0]) in members:
            total += int(fields[1]) * 1024**2
    return total


def supervise(command, output, *, work_seconds, rss_bytes, cuda_bytes,
              require_cuda, cancel_path, sample_seconds=.1,
              resource_probe=group_RSS, cuda_probe=CUDA_process_bytes):
    if sys.platform != "linux":
        raise ValueError("Linux process ownership required")
    output = Path(output)
    identity = {"record": "DODGE-060", "job_nonce": os.environ.get("DODGE060_JOB_NONCE", "local_CPU_fixture"),
                "payload_sha256": os.environ.get("DODGE060_PAYLOAD_SHA256")}
    write_once(str(output) + ".claimed", {**identity, "pid": os.getpid(), "command": command})
    started = time.monotonic()
    cancelled = False
    def cancel(*_):
        nonlocal cancelled
        cancelled = True
    handlers = {sig: signal.signal(sig, cancel) for sig in (signal.SIGTERM, signal.SIGINT)}
    child = None
    peak_rss = peak_cuda = 0
    failure = None
    group_absent = False
    try:
        # The child's group is never inherited from the persistent notebook.
        with Path(str(output) + ".stdout").open("xb") as stdout, \
             Path(str(output) + ".stderr").open("xb") as stderr:
            child = subprocess.Popen(command, start_new_session=True, stdout=stdout, stderr=stderr)
            while child.poll() is None:
                if cancelled or Path(cancel_path).exists():
                    raise RuntimeError("Synthetic child cancelled")
                if time.monotonic() - started >= work_seconds:
                    raise TimeoutError("Synthetic child work deadline")
                members = resource_probe(child.pid)
                rss = sum(members.values())
                memory = cuda_probe(members) if require_cuda else 0
                peak_rss = max(peak_rss, rss); peak_cuda = max(peak_cuda, memory)
                if rss >= rss_bytes or memory >= cuda_bytes:
                    raise MemoryError("Separate RSS/CUDA device process memory ceiling")
                time.sleep(sample_seconds)
            if child.returncode != 0:
                raise RuntimeError("Synthetic child exit " + str(child.returncode))
    except BaseException as error:
        failure = repr(error)
    finally:
        if child is not None:
            # Polling/reaping the leader does not prove its group is empty.
            # Always terminate the owned group, including leaked descendants.
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL); child.wait(timeout=2)
            remaining = resource_probe(child.pid)
            group_absent = not remaining
            if remaining:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                failure = failure or "Owned process group leaked descendants"
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
    result = dict(identity, schema="dodge_colab_synthetic_watchdog_result_v1",
        status="complete" if failure is None else "failed", error=failure,
        device="cuda" if require_cuda else "cpu", native_games=0, training_frames=0,
        trained_weights_saved=False, owned_group_absent=group_absent,
        child_pid=None if child is None else child.pid,
        child_returncode=None if child is None else child.returncode,
        peak_group_RSS_bytes=peak_rss, peak_sampled_CUDA_driver_process_bytes=peak_cuda,
        CUDA_memory_source="nvidia-smi compute-apps used_gpu_memory MiB" if require_cuda else "not_used",
        sampling_seconds=sample_seconds, elapsed_seconds=time.monotonic() - started,
        limits="Sampled physical memory; allocator peaks are recorded separately by the child.")
    write_once(output if failure is None else str(output) + ".first-failure.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cancel-path", type=Path, required=True)
    parser.add_argument("--work-seconds", type=float, default=300)
    parser.add_argument("--require-cuda", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    result = supervise(command, args.output, work_seconds=args.work_seconds,
        rss_bytes=6*1024**3, cuda_bytes=6*1024**3, require_cuda=args.require_cuda,
        cancel_path=args.cancel_path)
    raise SystemExit(0 if result["status"] == "complete" else 1)
