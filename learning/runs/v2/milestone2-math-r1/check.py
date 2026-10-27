#!/usr/bin/env python3
"""Run only owned-file primitive checks; retain every attempt and source hash."""

import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCES = [
    ROOT / "crates/dodge-rl-env/src/geometry.rs",
    ROOT / "crates/dodge-rl-env/src/raster.rs",
    HERE / "fixtures.rs",
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(label, command):
    attempts = HERE / "commands.jsonl"
    number = len(attempts.read_text().splitlines()) + 1 if attempts.exists() else 1
    log = HERE / f"{number:02d}-{label}.log"
    record = {
        "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "cwd": str(ROOT),
        "argv": [str(arg) for arg in command],
        "sources_sha256": {str(p.relative_to(ROOT)): digest(p) for p in SOURCES},
        "log": str(log.relative_to(HERE)),
    }
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    log.write_text(result.stdout + result.stderr)
    record["exit_code"] = result.returncode
    record["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with attempts.open("a") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
    print(f"{label}: exit={result.returncode}; log={log.name}")
    print(log.read_text(), end="")
    if result.returncode:
        sys.exit(result.returncode)


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else "test"
    if phase == "format":
        run("rustfmt", ["rustfmt", "--edition", "2024", *map(str, SOURCES)])
    elif phase == "test":
        run("rustfmt-check", ["rustfmt", "--check", "--edition", "2024", *map(str, SOURCES)])
        run("rustc-test-build", ["rustc", "--edition", "2024", "--test", "--deny", "warnings", str(HERE / "fixtures.rs"), "-o", str(HERE / "fixtures-bin")])
        run("fixtures", [str(HERE / "fixtures-bin"), "--test-threads=1", "--nocapture"])
    elif phase == "clippy":
        run("clippy-driver", ["clippy-driver", "--edition", "2024", "--test", "-W", "clippy::all", "-D", "warnings", str(HERE / "fixtures.rs"), "-o", str(HERE / "fixtures-clippy-bin")])
    else:
        raise SystemExit(f"Unknown check phase: {phase}")


if __name__ == "__main__":
    main()
