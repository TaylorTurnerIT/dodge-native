"""Run one named, explicitly registered validation command and retain evidence."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("argv", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    argv = args.argv[1:] if args.argv and args.argv[0] == "--" else args.argv
    output = HERE / "attempts" / args.name
    output.mkdir(parents=True, exist_ok=False)
    source = output / "sources"
    source.mkdir()
    hashes = {}
    for path in HERE.glob("*.py"):
        raw = path.read_bytes()
        (source / path.name).write_bytes(raw)
        hashes[path.name] = hashlib.sha256(raw).hexdigest()
    env = dict(os.environ, VALIDATION_DIR=str(output),
               PYTHONDONTWRITEBYTECODE="1",
               PYTHONPYCACHEPREFIX=str(output / "empty-cache"))
    env.pop("PYTORCH_ENABLE_MPS_FALLBACK", None)
    registration = dict(argv=argv, cwd=str(HERE), timeout_seconds=args.timeout,
                        registered_at_utc=datetime.now(timezone.utc).isoformat(),
                        environment={key: env[key] for key in
                                     ("VALIDATION_DIR", "PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX")},
                        sources_sha256=hashes, rerun_policy="No automatic retry")
    (output / "command.json").write_text(json.dumps(registration, indent=2, sort_keys=True) + "\n")
    started = time.monotonic()
    result = {}
    with (output / "stdout.log").open("x") as stdout, (output / "stderr.log").open("x") as stderr:
        try:
            child = subprocess.run(argv, cwd=HERE, env=env, stdout=stdout,
                                   stderr=stderr, timeout=args.timeout, check=False)
            result["raw_exit"] = child.returncode
        except subprocess.TimeoutExpired:
            result.update(raw_exit=None, timeout=True)
    result.update(elapsed_seconds=time.monotonic() - started,
                  completed_at_utc=datetime.now(timezone.utc).isoformat())
    (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(dict(name=args.name, **result)), flush=True)
    raise SystemExit(0 if result.get("raw_exit") == 0 else 1)


if __name__ == "__main__":
    main()
