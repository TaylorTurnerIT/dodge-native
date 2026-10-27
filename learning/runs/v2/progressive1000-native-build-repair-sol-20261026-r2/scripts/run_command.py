"""Capture one unique command with a 300-second process-group deadline."""
from pathlib import Path
import json
import os
import signal
import subprocess
import sys
import time

OUT = Path(__file__).absolute().parents[1]
ROOT = OUT.parents[3]
TOOLCHAIN = Path("/Users/taylor/.rustup/toolchains/1.97.1-aarch64-apple-darwin/bin")
name, *argv = sys.argv[1:]
assert name and all(c.isalnum() or c in "-_" for c in name)
assert argv
env = os.environ.copy()
for key in ["RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS",
            "PYTHONPATH", "PYTHONHOME", "PYO3_CONFIG_FILE", "PYO3_CROSS", "PYO3_NO_PYTHON"]:
    env.pop(key, None)
overrides = {
    "CARGO_HOME": str(OUT / "cargo-home"), "CARGO_TARGET_DIR": str(OUT / "target"),
    "CARGO_NET_OFFLINE": "true", "CARGO_BUILD_JOBS": "2",
    "RUSTC": str(TOOLCHAIN / "rustc"), "RUSTDOC": str(TOOLCHAIN / "rustdoc"),
    "RUSTFMT": str(TOOLCHAIN / "rustfmt"),
    "PYO3_PYTHON": str(ROOT / "python/.venv/bin/python3.12"),
    "TMPDIR": str(OUT / "tmp"), "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONPYCACHEPREFIX": str(OUT / "tmp/pycache"),
}
env.update(overrides)
log = OUT / "logs" / f"{name}.log"
record = OUT / "logs" / f"{name}.json"
assert not record.exists()
metadata = {"name": name, "argv": argv, "cwd": str(OUT / "source"),
            "wall_limit_seconds": 300, "environment_overrides": overrides}
start = time.monotonic()
with log.open("xb") as stream:
    stream.write((json.dumps(metadata) + "\n").encode())
    stream.flush()
    proc = subprocess.Popen(argv, cwd=OUT / "source", env=env, stdout=stream,
                            stderr=subprocess.STDOUT, start_new_session=True)
    timed_out = False
    try:
        code = proc.wait(timeout=300)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(proc.pid, signal.SIGKILL)
        code = proc.wait()
        stream.write(b"\nSTOP: 300-second deadline; process group killed.\n")
metadata.update(exit_code=code, timed_out=timed_out,
                wall_seconds=round(time.monotonic() - start, 3), log=str(log.relative_to(OUT)))
record.write_text(json.dumps(metadata, indent=2) + "\n")
print(json.dumps(metadata), flush=True)
print(log.read_text()[-14000:], flush=True)
sys.exit(code if code >= 0 else 1)
