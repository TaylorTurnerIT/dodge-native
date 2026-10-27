"""Bounded, offline, successor-owned build/test driver. Stop on first failure."""
from pathlib import Path
import json
import os
import signal
import subprocess
import sys
import time

OUT = Path(__file__).resolve().parents[1]
SOURCE = OUT / "source"
TOOLCHAIN = Path("/Users/taylor/.rustup/toolchains/1.97.1-aarch64-apple-darwin/bin")
env = os.environ.copy()
env.update({
    "CARGO_HOME": str(OUT / "cargo-home"),
    "CARGO_TARGET_DIR": str(OUT / "target"),
    "CARGO_NET_OFFLINE": "true",
    "CARGO_BUILD_JOBS": "2",
    "RUSTC": str(TOOLCHAIN / "rustc"),
    "RUSTDOC": str(TOOLCHAIN / "rustdoc"),
    "RUSTFMT": str(TOOLCHAIN / "rustfmt"),
    "PYO3_PYTHON": "/Users/taylor/.local/bin/python3.11",
    "TMPDIR": str(OUT / "tmp"),
})
for key in ["RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS"]:
    env.pop(key, None)
changed = ["src/lib.rs", "src/env.rs", "src/python.rs", "src/practice_tests.rs",
           "tests/support/wire_fixture.rs"]
commands = [
    ("format", [str(TOOLCHAIN / "rustfmt"), "--edition", "2024", "--config", "skip_children=true"]
     + [str(SOURCE / "crates/dodge-rl-env" / p) for p in changed]),
    ("binding-build", [str(TOOLCHAIN / "cargo"), "build", "--offline", "-p", "dodge-rl-env",
                       "--lib", "--features", "extension-module"]),
    ("native-unit", [str(TOOLCHAIN / "cargo"), "test", "--offline", "-p", "dodge-rl-env",
                     "--lib", "practice_tests::", "--", "--test-threads=1", "--nocapture"]),
]
results = []
receipt = OUT / "check-results.json"
assert not receipt.exists(), "Single execution only; do not retry this driver."
receipt.write_text(json.dumps({"status": "started", "commands": []}, indent=2) + "\n")
for name, argv in commands:
    log = OUT / "logs" / (name + ".log")
    start = time.monotonic()
    with log.open("xb") as stream:
        stream.write((json.dumps({"argv": argv, "cwd": str(SOURCE), "wall_limit_seconds": 300,
                                 "environment_overrides": {k: env[k] for k in [
                                     "CARGO_HOME", "CARGO_TARGET_DIR", "CARGO_NET_OFFLINE",
                                     "CARGO_BUILD_JOBS", "RUSTC", "RUSTDOC", "RUSTFMT",
                                     "PYO3_PYTHON", "TMPDIR"]}}) + "\n").encode())
        stream.flush()
        proc = subprocess.Popen(argv, cwd=SOURCE, env=env, stdout=stream,
                                stderr=subprocess.STDOUT, start_new_session=True)
        timed_out = False
        try:
            code = proc.wait(timeout=300)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            code = proc.wait()
            stream.write(b"\nSTOP: 300-second wall limit exceeded; process group killed.\n")
    result = {"name": name, "argv": argv, "exit_code": code, "timed_out": timed_out,
              "wall_seconds": round(time.monotonic() - start, 3),
              "log": str(log.relative_to(OUT))}
    results.append(result)
    receipt.write_text(json.dumps({"status": "failed" if code else "in_progress", "commands": results}, indent=2) + "\n")
    print(json.dumps(result), flush=True)
    if code:
        print(log.read_text()[-12000:], flush=True)
        sys.exit(1)
receipt.write_text(json.dumps({"status": "passed", "commands": results}, indent=2) + "\n")
