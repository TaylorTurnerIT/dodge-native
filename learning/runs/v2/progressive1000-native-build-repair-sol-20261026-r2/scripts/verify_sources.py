"""Produce exact source diffs, verify reconstruction, and pin build inputs."""
from pathlib import Path
import difflib
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tomllib

OUT = Path(__file__).absolute().parents[1]
ROOT = OUT.parents[3]
PREVIOUS = OUT.parent / "progressive1000-native-cutoff-prepare-sol-20261026-r1"
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def inventory(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob("*"))
            if p.is_file() and ".git" not in p.relative_to(root).parts}

def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")

baseline = json.loads((OUT / "input-baseline.json").read_text())
current = inventory(OUT / "source")
assert current == json.loads((OUT / "extension/final/manifest.json").read_text())["source"]
assert inventory(OUT / "originals") == baseline["originals"]
assert inventory(OUT / "cargo-home/registry") == baseline["cargo-home/registry"]
assert current["Cargo.lock"] == baseline["source"]["Cargo.lock"]
changed = [p for p in current if current[p] != baseline["source"].get(p)]
assert changed == ["crates/dodge-rl-env/src/env.rs", "crates/dodge-rl-env/src/features.rs",
                   "crates/dodge-rl-env/src/practice_tests.rs"]
for name in ["source", "originals", "cargo-home/registry"]:
    assert inventory(PREVIOUS / name) == baseline[name]
for name, expected in baseline["protected"].items():
    assert sha(Path(name)) == expected, name
for name in ["README.md", "receipt.json", "freeze-manifest.json", "exact.diff", "check-results.json"]:
    assert sha(PREVIOUS / name) == baseline[name]
frozen = json.loads((PREVIOUS / "freeze-manifest.json").read_text())["files"]
for name, expected in frozen.items():
    p = PREVIOUS / name
    assert p.stat().st_size == expected["bytes"] and sha(p) == expected["sha256"], name

reconstructions = {}
for old, output, scratch in [(PREVIOUS / "source", "r1-to-r2.diff", "r1-reconstruction"),
                              (OUT / "originals", "original-to-r2.diff", "original-reconstruction")]:
    old_hashes = inventory(old)
    diff = []
    for name in sorted(set(old_hashes) | set(current)):
        if old_hashes.get(name) == current.get(name):
            continue
        before = (old / name).read_text().splitlines(keepends=True) if name in old_hashes else []
        after = (OUT / "source" / name).read_text().splitlines(keepends=True) if name in current else []
        diff.extend(difflib.unified_diff(before, after,
                    fromfile="a/"+name if name in old_hashes else "/dev/null",
                    tofile="b/"+name if name in current else "/dev/null"))
    patch = OUT / output
    patch.write_text("".join(diff))
    target = OUT / "tmp" / scratch
    shutil.copytree(old, target, copy_function=shutil.copyfile)
    for p in [target, *target.rglob("*")]:
        p.chmod(p.stat().st_mode | 0o200 | (0o100 if p.is_dir() else 0))
    env = os.environ.copy()
    env.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
    for key in ["GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"]:
        env.pop(key, None)
    commands = [["git", "init", "--quiet"], ["git", "apply", "--check", str(patch)],
                ["git", "apply", str(patch)]]
    for argv in commands:
        result = subprocess.run(argv, cwd=target, env=env, timeout=300, capture_output=True, text=True)
        print(json.dumps({"argv": argv, "cwd": str(target), "exit_code": result.returncode,
                          "stdout": result.stdout, "stderr": result.stderr}), flush=True)
        result.check_returncode()
    assert inventory(target) == current
    reconstructions[output] = {"sha256": sha(patch), "reconstructs_exact_source": True}

lock = tomllib.loads((OUT / "source/Cargo.lock").read_text())
deps = {"cargo_lock_sha256": current["Cargo.lock"], "packages": lock["package"],
        "offline_cache_files": len(baseline["cargo-home/registry"]),
        "offline_cache_manifest": "input-baseline.json: cargo-home/registry",
        "python": {"invocation": sys.executable, "version": sys.version, "prefix": sys.prefix,
                   "executable_sha256": sha(Path(sys.executable)),
                   "pyvenv_cfg_sha256": sha(ROOT / "python/.venv/pyvenv.cfg")}}
numpy_dist = importlib.metadata.distribution("numpy")
numpy_hashes = {}
for name in numpy_dist.files:
    p = Path(numpy_dist.locate_file(name))
    if p.is_file() and p.suffix != ".pyc":
        numpy_hashes[str(name)] = sha(p)
deps["numpy"] = {"version": numpy_dist.version, "files": numpy_hashes}
toolchain = Path("/Users/taylor/.rustup/toolchains/1.97.1-aarch64-apple-darwin/bin")
deps["tools"] = {}
for name in ["cargo", "rustc", "rustfmt"]:
    p = toolchain / name
    argv = [str(p), "-Vv" if name == "rustc" else "--version"]
    result = subprocess.run(argv, timeout=300, capture_output=True, text=True, check=True)
    deps["tools"][name] = {"path": str(p), "sha256": sha(p), "version": result.stdout.strip()}
save("dependency-manifest.json", deps)
design = OUT.parent / "progressive1000-curriculum-replica-parent-20261026-r3"
assert sha(design / "scheduler_reference.py") == "a467b7219a9cd801fa3b403a6af112fc693ec3d14c9d311e8845632ef61d844b"
save("source-manifest.json", {"files": current, "changed_from_r1": changed,
     "diffs": reconstructions, "core_unchanged_from_r1_and_original": all(
         current[p] == baseline["source"][p] == baseline["originals"][p]
         for p in current if p.startswith("crates/dodge-core/")),
     "dependency_manifest_sha256": sha(OUT / "dependency-manifest.json"),
     "predecessor_frozen_files_verified": len(frozen),
     "listed_protected_inputs_unchanged": True,
     "scope_limit": "Listed hashes and predecessor freeze only; no concurrent whole-workspace attribution.",
     "design_scheduler_sha256": sha(design / "scheduler_reference.py")})
print(json.dumps({"changed": changed, "diffs": reconstructions,
                  "predecessor_files_verified": len(frozen),
                  "source_manifest_sha256": sha(OUT / "source-manifest.json")}))
