"""Freeze R6 protocol, source, support, and input-manifest hashes."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]

def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")

def main() -> None:
    protocol_path = HERE / "protocol-proposed.json"
    manifest_path = HERE / "input-manifest.json"
    protocol = json.loads(protocol_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    source_names = sorted(manifest["harness_source_files"])
    manifest["harness_source_files"] = {
        name: sha(HERE / name) for name in source_names
    }
    harness_hash = hashlib.sha256(json.dumps(
        manifest["harness_source_files"], sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()
    protocol["harness_sha256"] = harness_hash
    write(protocol_path, protocol)
    manifest["harness_sha256"] = harness_hash
    manifest["protocol_path"] = str(protocol_path)
    manifest["protocol_sha256"] = sha(protocol_path)
    manifest["support_files"] = {
        "README.md": sha(HERE / "README.md"),
        "freeze_artifacts.py": sha(HERE / "freeze_artifacts.py"),
    }
    manifest["frozen_runtime_files"] = {
        name: digest for name, digest in manifest["frozen_runtime_files"].items()
        if "__pycache__" not in Path(name).parts and not name.endswith((".pyc", ".pyo"))
    }
    manifest["runtime_tree_sha256"] = hashlib.sha256(json.dumps(
        manifest["frozen_runtime_files"], sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()
    write(manifest_path, manifest)
    print(json.dumps({"harness_sha256": harness_hash,
                      "protocol_sha256": manifest["protocol_sha256"],
                      "manifest_sha256": sha(manifest_path)}, sort_keys=True))

if __name__ == "__main__":
    main()
