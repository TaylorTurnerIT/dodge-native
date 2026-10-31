"""Immutable chunk exports and durable off-VM copies, without loading model files.

An acknowledgment certifies exact bytes already fsynced and read back by the
parent. It is never a training, retry, resume, billing or lease permission.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import time
import uuid

CHUNK_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_EXPORT_BYTES = 2 * 1024**3
MAX_MEMBERS = 512
HEX = re.compile(r"[0-9a-f]{64}")
TOKEN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,95}")
IDENTITY = ("record", "job_nonce", "registration_sha256", "expected_lease_sha256")


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK_BYTES), b""):
            value.update(block)
    return value.hexdigest()


def fsync_dir(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def real_directory(path):
    path = Path(path).absolute()
    need(not path.is_symlink() and path.resolve() == path, "Redirected result directory")
    missing, parent = [], path
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for directory in reversed(missing):
        directory.mkdir()
        fsync_dir(directory.parent)
    need(path.is_dir(), "Result directory absent")
    return path


def durable_new(path, data):
    """Exclusive publication; failures preserve the partial, never overwrite it."""
    path = Path(path)
    real_directory(path.parent)
    need(not path.exists() and not path.is_symlink(), "Result already exists")
    temporary = path.with_name(path.name + ".partial-" + str(uuid.uuid4()))
    with temporary.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.link(temporary, path)
    fsync_dir(path.parent)
    temporary.unlink()
    fsync_dir(path.parent)


def identity(value):
    result = {key: value[key] for key in IDENTITY}
    need(isinstance(result["record"], str) and TOKEN.fullmatch(result["record"]), "Invalid record")
    need(str(uuid.UUID(result["job_nonce"])) == result["job_nonce"], "Noncanonical job nonce")
    for key in IDENTITY[2:]:
        need(isinstance(result[key], str) and HEX.fullmatch(result[key]), "Invalid identity digest")
    return result


def relative_name(name):
    need(isinstance(name, str) and len(name) <= 240 and "\\" not in name, "Invalid artifact name")
    path = PurePosixPath(name)
    need(not path.is_absolute() and path.as_posix() == name and ".." not in path.parts,
         "Unsafe artifact name")
    need(path.parts and all(TOKEN.fullmatch(part) for part in path.parts), "Unsafe artifact component")
    return name


def validate_manifest(body, expected):
    need(body.get("schema") == "dodge_result_export_v1" and identity(body) == identity(expected),
         "Export identity differs")
    need(type(body.get("sequence")) is int and body["sequence"] >= 1, "Invalid export sequence")
    need(body.get("kind") in ("preflight", "checkpoint", "job", "terminal"), "Invalid export kind")
    need(body.get("job") is None or TOKEN.fullmatch(body["job"]), "Invalid export job")
    need(type(body.get("update")) is int and body["update"] >= 0, "Invalid export boundary")
    members = body.get("members")
    need(isinstance(members, dict) and 0 < len(members) <= MAX_MEMBERS, "Invalid export inventory")
    total = 0
    for name, item in members.items():
        relative_name(name)
        need(type(item.get("bytes")) is int and 0 <= item["bytes"] <= MAX_EXPORT_BYTES,
             "Invalid member length")
        need(isinstance(item.get("sha256"), str) and HEX.fullmatch(item["sha256"]), "Invalid member digest")
        chunks = item.get("chunks")
        need(isinstance(chunks, list) and len(chunks) == (item["bytes"] + CHUNK_BYTES - 1) // CHUNK_BYTES,
             "Invalid chunk count")
        for part in chunks:
            need(isinstance(part, str) and HEX.fullmatch(part), "Invalid chunk digest")
        total += item["bytes"]
    need(total <= MAX_EXPORT_BYTES, "Export size cap")
    if body["kind"] == "checkpoint":
        need(body["job"] is not None and body["update"] > 0
             and any(name.endswith(".pt") for name in members), "Checkpoint export has no weights")
    return body


class Publisher:
    """Remote producer. Publish only stable files at a stopped writer boundary."""
    def __init__(self, root, expected):
        self.root, self.expected = real_directory(root), identity(expected)
        self.chunks = real_directory(self.root / "chunks")
        self.manifests = real_directory(self.root / "manifests")
        self.acks = real_directory(self.root / "acks")
        self.ready = real_directory(self.root / "ready")
        self.claims = real_directory(self.root / "claims")

    def publish(self, sequence, kind, files, *, job=None, update=0):
        need(type(sequence) is int and sequence >= 1, "Invalid export sequence")
        target = self.manifests / ("%06d.json" % sequence)
        need(not target.exists(), "Export sequence already consumed")
        durable_new(self.claims / target.name, canonical(dict(self.expected, sequence=sequence)))
        need(isinstance(files, dict) and 0 < len(files) <= MAX_MEMBERS, "Invalid export files")
        body = dict(self.expected, schema="dodge_result_export_v1", sequence=sequence,
                    kind=kind, job=job, update=update, members={})
        total = 0
        for name, path in sorted(files.items()):
            relative_name(name)
            path = Path(path)
            need(path.is_file() and not path.is_symlink() and path.absolute() == path.resolve(),
                 "Artifact absent or redirected")
            before = path.stat()
            total += before.st_size
            need(total <= MAX_EXPORT_BYTES, "Export size cap")
            chunks, value, size = [], hashlib.sha256(), 0
            with path.open("rb") as stream:
                for data in iter(lambda: stream.read(CHUNK_BYTES), b""):
                    value.update(data)
                    size += len(data)
                    part = digest(data)
                    chunk_path = self.chunks / (part + ".bin")
                    if chunk_path.exists():
                        need(not chunk_path.is_symlink() and file_digest(chunk_path) == part,
                             "Existing export chunk differs")
                    else:
                        durable_new(chunk_path, data)
                    chunks.append(part)
            after = path.stat()
            need((before.st_ino, before.st_size, before.st_mtime_ns) ==
                 (after.st_ino, after.st_size, after.st_mtime_ns) and size == before.st_size,
                 "Artifact changed during export")
            body["members"][name] = dict(bytes=size, sha256=value.hexdigest(), chunks=chunks)
        validate_manifest(body, self.expected)
        data = canonical(body)
        need(len(data) <= MAX_MANIFEST_BYTES, "Export manifest size cap")
        durable_new(target, data)
        durable_new(self.ready / target.name, canonical(dict(sequence=sequence, sha256=digest(data))))
        return dict(path="manifests/" + target.name, sha256=digest(data), manifest=body)

    def wait_for_ack(self, export, *, guard, seconds, clock=time.monotonic, pause=time.sleep):
        """Wait with the existing control/budget guard; never authorize more work."""
        need(0 < seconds <= 180, "Acknowledgment wait outside cap")
        deadline = clock() + seconds
        target = self.acks / ("%06d.json" % export["manifest"]["sequence"])
        while True:
            guard()
            need(clock() < deadline, "Off-VM checkpoint acknowledgment deadline")
            if target.exists():
                need(not target.is_symlink() and target.stat().st_size <= 4096, "Invalid backup acknowledgment")
                ack = json.loads(target.read_bytes())
                need(ack.get("schema") == "dodge_result_backup_ack_v1"
                     and identity(ack) == self.expected
                     and ack.get("manifest_sha256") == export["sha256"]
                     and ack.get("sequence") == export["manifest"]["sequence"]
                     and ack.get("status") == "durable_copy_readback_verified",
                     "Backup acknowledgment differs")
                return ack
            pause(.1)


class Receiver:
    """Parent-owned storage. Fetch callbacks must enforce endpoint and deadlines."""
    def __init__(self, root, expected, *, get_json, get_chunk, put_ack, guard):
        self.root, self.expected = real_directory(root), identity(expected)
        self.get_json, self.get_chunk, self.put_ack, self.guard = get_json, get_chunk, put_ack, guard
        self.objects = real_directory(self.root / "objects")
        self.exports = real_directory(self.root / "exports")

    def mirror(self, pointer, *, before_ack=lambda body, files: None):
        self.guard()
        sequence = pointer["sequence"]
        need(type(sequence) is int and sequence >= 1, "Invalid pointer sequence")
        expected_sha = pointer["sha256"]
        need(isinstance(expected_sha, str) and HEX.fullmatch(expected_sha), "Invalid pointer digest")
        raw = self.get_json("manifests/%06d.json" % sequence)
        need(len(raw) <= MAX_MANIFEST_BYTES and digest(raw) == expected_sha, "Export manifest differs")
        body = validate_manifest(json.loads(raw), self.expected)
        need(body["sequence"] == sequence, "Export sequence differs")
        target = self.exports / ("%06d" % sequence)
        # Each export is single-attempt. An existing partial/claim never resets.
        target.mkdir()
        fsync_dir(target.parent)
        durable_new(target / "manifest.json", raw)
        try:
            for name, item in body["members"].items():
                self.guard()
                path = target / "files" / name
                real_directory(path.parent)
                partial = path.with_name(path.name + ".partial")
                with partial.open("xb") as stream:
                    for index, part in enumerate(item["chunks"]):
                        self.guard()
                        object_path = self.objects / (part + ".bin")
                        expected_bytes = min(CHUNK_BYTES, item["bytes"] - index * CHUNK_BYTES)
                        if object_path.exists():
                            need(not object_path.is_symlink(), "Redirected stored chunk")
                            data = object_path.read_bytes()
                        else:
                            data = self.get_chunk("chunks/" + part + ".bin")
                            need(len(data) == expected_bytes and digest(data) == part, "Downloaded chunk differs")
                            durable_new(object_path, data)
                        need(len(data) == expected_bytes and digest(data) == part, "Stored chunk differs")
                        stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                need(partial.stat().st_size == item["bytes"] and file_digest(partial) == item["sha256"],
                     "Reassembled artifact differs")
                os.link(partial, path)
                fsync_dir(path.parent)
                partial.unlink()
                fsync_dir(path.parent)
            self.guard()
            receipt = dict(self.expected, schema="dodge_result_backup_receipt_v1",
                           status="durable_copy_readback_verified", sequence=sequence,
                           manifest_sha256=expected_sha, kind=body["kind"], job=body["job"], update=body["update"])
            # Read every committed file back before certifying backup.
            for name, item in body["members"].items():
                need(file_digest(target / "files" / name) == item["sha256"], "Backup readback differs")
            before_ack(body, target / "files")
            durable_new(target / "backup-receipt.json", canonical(receipt))
            self.guard()
            ack = dict(self.expected, schema="dodge_result_backup_ack_v1",
                       status=receipt["status"], sequence=sequence, manifest_sha256=expected_sha)
            self.put_ack("acks/%06d.json" % sequence, canonical(ack))
            return receipt
        except BaseException as error:
            failure = dict(self.expected, schema="dodge_result_backup_failure_v1", sequence=sequence,
                           manifest_sha256=expected_sha, exception_type=type(error).__name__,
                           status="copy_failed_previous_exports_preserved")
            if not (target / "first-failure.json").exists():
                durable_new(target / "first-failure.json", canonical(failure))
            raise

    def verify(self, sequence):
        target = self.exports / ("%06d" % sequence)
        need(not target.is_symlink() and target.resolve() == target.absolute(), "Redirected backup")
        raw = (target / "manifest.json").read_bytes()
        body = validate_manifest(json.loads(raw), self.expected)
        receipt = json.loads((target / "backup-receipt.json").read_bytes())
        need(identity(receipt) == self.expected and receipt["manifest_sha256"] == digest(raw)
             and receipt["status"] == "durable_copy_readback_verified" and body["sequence"] == sequence
             and receipt["sequence"] == sequence and not (target / "first-failure.json").exists(),
             "Backup receipt differs")
        for name, item in body["members"].items():
            path = target / "files" / name
            need(path.is_file() and not path.is_symlink() and path.resolve() == path.absolute()
                 and path.stat().st_size == item["bytes"] and file_digest(path) == item["sha256"],
                 "Durable backup absent or changed")
        return body, target / "files"
