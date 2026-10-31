"""Pinned Colab exec cell for synthetic059, called only by reviewed parent.

Uploads arrive at fixed /content paths. The coordinator verifies live billing
admission before this cell; this cell never allocates a VM or opens a seed pool.
No package installation, native build or trained checkpoint output is performed.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import uuid


def require_single_T4(text):
    """Admit one whole T4 product, without silently selecting another GPU."""
    name = text.strip()
    if name not in {"Tesla T4", "NVIDIA T4"}:
        raise ValueError("Exact single whole T4 GPU required")
    return name


def run_fixture(root, receipts, expected_sha, nonce):
    archive = Path("/content/dodge-ray060-payload.tar")
    checkpoint = Path("/content/checkpoint-global-420.pt")
    data = archive.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_sha:
        raise ValueError("Uploaded synthetic payload hash differs")
    if hashlib.sha256(checkpoint.read_bytes()).hexdigest() != (
        "7e0de8640f1337261412d91cde6bc692772ff212fbd360f5aad415dc6bc7ed4b"
    ):
        raise ValueError("Uploaded original420 checkpoint hash differs")
    payload = root / "source"; payload.mkdir()
    with tarfile.open(archive, mode="r:") as source:
        entries = source.getmembers()
        names = [entry.name for entry in entries]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate payload member")
        for entry in entries:
            path = PurePosixPath(entry.name)
            if not entry.isfile() or path.is_absolute() or ".." in path.parts:
                raise ValueError("Unsafe synthetic payload member")
        manifest = json.loads(source.extractfile("manifest.json").read())
        if set(names) != {*manifest, "manifest.json"}:
            raise ValueError("Synthetic payload manifest member set differs")
        for name, digest in manifest.items():
            contents = source.extractfile(name).read()
            if hashlib.sha256(contents).hexdigest() != digest:
                raise ValueError("Synthetic payload member digest differs")
            target = payload / name; target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(contents)
    # Driver inspection does not create a CUDA context or run a model.
    GPU = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                         check=True, capture_output=True, text=True, timeout=15)
    # Accept NVIDIA's two T4 names, while rejecting other models, MIG instances,
    # and multiple output rows.
    require_single_T4(GPU.stdout)
    command = [sys.executable, "-B", str(payload / "device_watchdog.py"),
        "--output", str(receipts / "watchdog.json"), "--cancel-path", str(root / "cancel.requested"),
        "--work-seconds", "300", "--require-cuda", "--", sys.executable, "-B",
        str(payload / "compatibility.py"), "--device", "cuda", "--checkpoint", str(checkpoint),
        "--output", str(receipts / "CUDA-compatibility.json"), "--job-nonce", nonce]
    child = subprocess.run(command, check=False, timeout=315,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    if child.returncode:
        raise RuntimeError("Synthetic CUDA fixture failed; first evidence preserved")


def main():
    root = Path("/content/dodge-ray-060-r1")
    expected_sha = os.environ["DODGE060_PAYLOAD_SHA256"]
    nonce = os.environ["DODGE060_JOB_NONCE"]
    if str(uuid.UUID(nonce)) != nonce:
        raise ValueError("Canonical coordinator allocation UUID required")
    if os.environ.get("DODGE060_BILLING_ADMITTED") != "true":
        raise ValueError("Parent live billing admission absent")
    if sys.platform != "linux":
        raise ValueError("Synthetic cloud candidate requires Linux")
    # A new execution attempt must not reuse an old claim, even after failure.
    with Path(str(root) + ".claimed").open("x") as stream:
        json.dump({"pid": os.getpid(), "payload_sha256": expected_sha, "job_nonce": nonce}, stream)
        stream.flush(); os.fsync(stream.fileno())
    root.mkdir(exist_ok=False)
    receipts = root / "receipts"; receipts.mkdir()
    error = None
    try:
        run_fixture(root, receipts, expected_sha, nonce)
    except BaseException as failure:
        error = failure
        with (receipts / "bootstrap-first-failure.json").open("x") as stream:
            json.dump({"record": "DODGE-060", "job_nonce": nonce,
                       "error_type": type(failure).__name__, "error": str(failure)}, stream)
            stream.flush(); os.fsync(stream.fileno())
    result = {"schema": "dodge_colab_synthetic_receipt_bundle_v1", "record": "DODGE-060",
        "job_nonce": nonce, "payload_sha256": expected_sha,
        "status": "complete" if error is None else "failed", "native_games": 0,
        "training_frames": 0, "trained_weights_saved": False}
    with (receipts / "bootstrap-result.json").open("x") as stream:
        json.dump(result, stream, sort_keys=True)
        stream.flush(); os.fsync(stream.fileno())
    # Small, fixed-path receipt archive; no model/Adam tensors or checkpoint.
    destination = Path("/content/dodge-ray060-receipts.tar")
    with tarfile.open(destination, mode="x") as archive_out:
        for receipt in sorted(receipts.iterdir()):
            if not receipt.is_file() or receipt.is_symlink():
                raise ValueError("Unexpected synthetic receipt member")
            archive_out.add(receipt, arcname=receipt.name, recursive=False)
    print(json.dumps({**result,
        "receipt_path": str(destination),
        "receipt_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "receipt_bytes": destination.stat().st_size, "native_games": 0,
        "trained_weights_saved": False}, sort_keys=True))
    if error is not None:
        raise error


if __name__ == "__main__":
    main()
