"""Stage a local extension copy, never install it into the project runtime."""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import sysconfig

OUT = Path(__file__).absolute().parents[1]
label, = sys.argv[1:]
assert label in ["initial", "final"]
destination = OUT / "extension" / label
destination.mkdir()
binary = OUT / "target/debug/libdodge_rl_env.dylib"
extension = destination / ("_native" + sysconfig.get_config_var("EXT_SUFFIX"))
shutil.copyfile(binary, extension)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
configs = {}
for p in sorted((OUT / "target/debug/build").glob("pyo3-build-config-*/out/pyo3-build-config.txt")):
    configs[str(p.relative_to(OUT))] = {"sha256": sha(p), "text": p.read_text()}
source = {str(p.relative_to(OUT / "source")): sha(p)
          for p in sorted((OUT / "source").rglob("*")) if p.is_file()}
if label == "initial":
    source = json.loads((OUT / "input-baseline.json").read_text())["source"]
assert sha(binary) == sha(extension)
metadata = {"sha256": sha(extension), "path": str(extension.relative_to(OUT)),
            "profile": "dev, unoptimized + debuginfo", "python_executable": sys.executable,
            "python_version": sys.version, "prefix": sys.prefix,
            "extension_suffix": sysconfig.get_config_var("EXT_SUFFIX"),
            "pyo3_build_configuration": configs, "source": source,
            "installed": False, "accepted_runtime_identity_proven": False}
(destination / "manifest.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
print(json.dumps({k: v for k, v in metadata.items() if k not in ["source", "pyo3_build_configuration"]}))
