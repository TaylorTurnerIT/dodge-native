"""Record non-secret build environment and host tools after the scoped build."""
from pathlib import Path
import hashlib
import json
import os
import platform
import subprocess

OUT = Path(__file__).absolute().parents[1]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
result = {"recorded_after_build": True, "platform": platform.platform(),
          "machine": platform.machine(), "environment": {k: os.environ.get(k) for k in [
              "PATH", "SDKROOT", "MACOSX_DEPLOYMENT_TARGET", "CC", "CXX", "AR",
              "CFLAGS", "CXXFLAGS", "LDFLAGS", "RUSTUP_TOOLCHAIN", "DYLD_LIBRARY_PATH",
              "DYLD_FALLBACK_LIBRARY_PATH", "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS"]},
          "cargo_ancestor_configs": {}, "commands": []}
for root in [OUT / "source", *(OUT / "source").parents]:
    for name in [".cargo/config.toml", ".cargo/config"]:
        p = root / name
        if p.is_file():
            result["cargo_ancestor_configs"][str(p)] = {"sha256": sha(p), "text": p.read_text()}
for argv in [["/usr/bin/xcrun", "--show-sdk-path"], ["/usr/bin/clang", "--version"],
             ["/usr/bin/sw_vers"], ["/usr/bin/file", str(OUT / "extension/final/_native.cpython-312-darwin.so")]]:
    command = subprocess.run(argv, timeout=300, capture_output=True, text=True)
    result["commands"].append({"argv": argv, "exit_code": command.returncode,
                               "stdout": command.stdout, "stderr": command.stderr})
    command.check_returncode()
(OUT / "host-manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps(result))
