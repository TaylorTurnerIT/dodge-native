"""Deterministic, explicit allowlist for the synthetic-only cloud payload.

The checkpoint is a separate, hash-checked upload. No native source/binary,
seed pool, notebook, credentials, trained outputs or old packet is uploaded.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile


ROOT = Path(__file__).resolve().parent
MEMBERS = (
    "compatibility.py", "fingerprints.py", "device_watchdog.py",
    "runtime_overlay/dodge_rl/models/teacher.py",
    "runtime_overlay/dodge_rl/models/ray_teacher.py",
    "runtime_overlay/dodge_rl/clearance_rays.py",
    "runtime_overlay/dodge_rl/ray_frontend.py",
    "runtime_overlay/dodge_rl/player_geometry.py",
    "runtime_overlay/dodge_rl/ray_migration.py",
    "runtime_overlay/dodge_rl/checkpoints.py",
    "runtime_overlay/dodge_rl/identity.py",
    "runtime_overlay/dodge_rl/device_runtime.py",
)


def build(root=ROOT):
    payload = {}
    for name in MEMBERS:
        source = root / name
        if source.is_symlink() or not source.is_file():
            raise ValueError("Missing or symlink payload member: " + name)
        payload[name] = source.read_bytes()
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()}
    payload["manifest.json"] = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, data in sorted(payload.items()):
            entry = tarfile.TarInfo(name); entry.size = len(data); entry.mode = 0o444
            archive.addfile(entry, io.BytesIO(data))
    data = buffer.getvalue()
    return data, manifest, hashlib.sha256(data).hexdigest()


def extract_verified(archive_path, destination, expected_sha):
    data = Path(archive_path).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_sha:
        raise ValueError("Payload archive hash differs")
    destination = Path(destination)
    destination.mkdir(exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        names = [entry.name for entry in archive.getmembers()]
        if len(names) != len(set(names)) or set(names) != {*MEMBERS, "manifest.json"}:
            raise ValueError("Payload member set differs")
        if any(not entry.isfile() for entry in archive.getmembers()):
            raise ValueError("Payload non-file member")
        manifest = json.loads(archive.extractfile("manifest.json").read())
        if set(manifest) != set(MEMBERS):
            raise ValueError("Payload manifest member set differs")
        for name in MEMBERS:
            contents = archive.extractfile(name).read()
            if hashlib.sha256(contents).hexdigest() != manifest[name]:
                raise ValueError("Payload member hash differs: " + name)
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(contents)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data, manifest, digest = build()
    with args.output.open("xb") as stream:
        stream.write(data)
    print(json.dumps({"path": str(args.output), "sha256": digest, "members": manifest}, sort_keys=True))
