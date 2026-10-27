"""Index and optionally stage source and compact evidence from ignored runs."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
BLOCKED = {
    "target", "cargo-home", ".cargo-home", "registry", "test-tmp",
    "__pycache__", ".venv", ".git", "empty-pycache", "empty-pycache-prefix",
    "empty-prefix", "node_modules", "attempts", "fixtures", "tmp", "temp", ".cache",
}
SOURCE = {".py", ".rs", ".toml", ".lock", ".md", ".diff", ".patch", ".sh", ".p8", ".html"}
EVIDENCE = {".json", ".jsonl", ".txt", ".log", ".csv", ".sha256"}
PROVENANCE = (
    "source-manifest", "source-hashes", "registration", "receipt",
    "parent-terminal-audit", "parent-acceptance",
)
SENSITIVE = re.compile(
    rb"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|"
    rb"\b(?:sk-[A-Za-z0-9]{24,}|gh[pousr]_[A-Za-z0-9]{30,})\b"
)


def inventory(excluded_runs):
    files = []
    for directory, children, names in os.walk(ROOT / "learning/runs"):
        children[:] = sorted(
            name for name in children
            if name not in BLOCKED and name not in excluded_runs
            and not name.startswith("test-tmp")
        )
        for name in sorted(names):
            path = Path(directory) / name
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(ROOT)
            size = path.stat().st_size
            depth = len(relative.parts) - 3
            keep = (
                path.suffix in SOURCE
                or (path.suffix in EVIDENCE and depth <= 3 and size <= 1024**2)
                or (path.suffix == ".json" and depth <= 3 and size <= 10 * 1024**2
                    and any(word in name for word in PROVENANCE))
                or (name in {"SHA256SUMS", "one-shot.claimed"} and size <= 1024**2)
            )
            if not keep:
                continue
            raw = path.read_bytes()
            if SENSITIVE.search(raw):
                raise ValueError(f"Review possible credential before staging: {relative}")
            files.append({
                "path": str(relative), "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            })
    return sorted(files, key=lambda item: item["path"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exclude-run", action="append", default=[])
    parser.add_argument("--stage", action="store_true")
    args = parser.parse_args()
    files = inventory(set(args.exclude_run))
    index_path = ROOT / "learning/experiment-evidence-index.json"
    index = {
        "schema": "dodge_experiment_source_evidence_index_v1",
        "scope": "Source/config/tests and compact evidence; checkpoints and build outputs stay local.",
        "source_extensions": sorted(SOURCE),
        "compact_evidence_policy": (
            "Evidence up to1MiB at run root/one nested level; named provenance, "
            "registrations and receipts up to10MiB. Source and seals retain original paths."
        ),
        "blocked_directory_names": sorted(BLOCKED),
        "pending_active_output": sorted(set(args.exclude_run)),
        "included_files": len(files),
        "included_bytes": sum(item["bytes"] for item in files),
        "files": files,
    }
    index_path.write_text(json.dumps(index, indent=2) + "\n")
    if args.stage:
        paths = [item["path"] for item in files]
        subprocess.run(
            ["git", "add", "-f", "--pathspec-from-file=-", "--pathspec-file-nul"],
            input=b"\0".join(os.fsencode(path) for path in paths) + b"\0",
            cwd=ROOT, check=True,
        )
        subprocess.run(
            ["git", "add", "--", str(index_path.relative_to(ROOT))],
            cwd=ROOT, check=True,
        )
    print(json.dumps({key: index[key] for key in (
        "included_files", "included_bytes", "pending_active_output",
    )}))


if __name__ == "__main__":
    main()
