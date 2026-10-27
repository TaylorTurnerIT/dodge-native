"""Copy source and immutable offline cache inputs into this successor only."""
from pathlib import Path
import hashlib
import json
import shutil
import stat
import sys

OUT = Path(__file__).absolute().parent
ROOT = OUT.parents[3]
PREVIOUS = OUT.parent / "progressive1000-native-cutoff-prepare-sol-20261026-r1"
assert sys.version_info[:3] == (3, 12, 15)
assert sys.prefix == str(ROOT / "python/.venv")

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def inventory(path):
    result = {}
    for item in sorted(path.rglob("*")):
        assert not item.is_symlink(), f"Refuse symlink input: {item}"
        if item.is_file():
            result[str(item.relative_to(path))] = digest(item)
    return result

def copy_tree(source, destination):
    hashes = inventory(source)
    shutil.copytree(source, destination, copy_function=shutil.copyfile)
    for item in [destination, *destination.rglob("*")]:
        item.chmod(item.stat().st_mode | stat.S_IWUSR | (stat.S_IXUSR if item.is_dir() else 0))
    assert inventory(destination) == hashes
    return hashes

baseline = {}
for name in ["source", "originals", "cargo-home/registry"]:
    baseline[name] = inventory(PREVIOUS / name)
for name in ["README.md", "receipt.json", "freeze-manifest.json", "exact.diff", "check-results.json"]:
    baseline[name] = digest(PREVIOUS / name)
protected = [ROOT / "README.md", ROOT / "python/pyproject.toml",
             OUT.parent / "progressive1000-design-parent-acceptance-20261026-r1/implementation-contract.json",
             OUT.parent / "progressive1000-curriculum-replica-parent-20261026-r3/experiment.json"]
protected += [ROOT / "crates/dodge-rl-env/src" / name for name in ["env.rs", "python.rs", "lib.rs"]]
baseline["protected"] = {str(p): digest(p) for p in protected}
assert baseline["protected"][str(protected[3])] == "c20bd35188c4b4dd36687bc10c7998e6410c70d37300be92db9a42b3d01c43c0"
if sys.argv[1:] == ["--finish-existing"]:
    for name in ["source", "originals", "cargo-home/registry"]:
        assert inventory(OUT / name) == baseline[name]
else:
    assert not sys.argv[1:]
    copy_tree(PREVIOUS / "source", OUT / "source")
    copy_tree(PREVIOUS / "originals", OUT / "originals")
    (OUT / "cargo-home").mkdir()
    copy_tree(PREVIOUS / "cargo-home/registry", OUT / "cargo-home/registry")
for name in ["logs", "target", "tmp", "extension", "scripts"]:
    (OUT / name).mkdir(exist_ok=True)
(OUT / "input-baseline.json").write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n")
print(json.dumps({"python": sys.version, "executable": sys.executable, "prefix": sys.prefix,
                  "source_files": len(baseline["source"]),
                  "cache_files": len(baseline["cargo-home/registry"])}))
