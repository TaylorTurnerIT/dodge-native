"""Bounded parent integration checks; no full M2 campaign or retries."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import tarfile
import time

ROOT = Path(__file__).resolve().parents[4]
assert (ROOT / "Cargo.toml").is_file(), "Integration runner has the wrong root"
OUT = Path(__file__).resolve().parent
START = time.monotonic()
ENV = os.environ.copy()
OVERRIDES = {
    "CARGO_TARGET_DIR": str(ROOT / "learning/.cache/v2-m2-integration-build-r2"),
    "PYO3_PYTHON": str(ROOT / "python/.venv/bin/python"),
    "VIRTUAL_ENV": str(ROOT / "python/.venv"),
}
ENV.update(OVERRIDES)
RECORDS = []


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def run(name, command, cwd=ROOT, seconds=180):
    assert time.monotonic() - START + seconds <= 900, "Integration budget exhausted"
    log = OUT / (name + ".log")
    began = time.monotonic()
    print(json.dumps({"phase": name, "at_utc": datetime.now(timezone.utc).isoformat()}), flush=True)
    record = {"name": name, "command": [str(x) for x in command], "cwd": str(cwd),
              "timeout_seconds": seconds, "environment_overrides": OVERRIDES}
    with log.open("xb") as stream:
        process = subprocess.Popen(record["command"], cwd=cwd, env=ENV,
                                   stdout=stream, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        record.update(owned_pid=process.pid, owned_pgid=process.pid)
        try:
            process.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            record["timeout"] = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        record.update(exit_code=process.returncode, elapsed_seconds=time.monotonic()-began)
    record.update(log=str(log.relative_to(ROOT)), log_sha256=sha(log))
    RECORDS.append(record)
    with (OUT / "commands.jsonl").open("a") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
    if process.returncode or record.get("timeout"):
        write_new(OUT / (name + "-failure.json"), record)
        raise RuntimeError(f"{name} failed; retained log {log}")
    return log


spec = importlib.util.spec_from_file_location("validation_harness", ROOT / "learning/scripts/v2_validate_environment.py")
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)
run("format-integrated-module", ["cargo", "+1.97.1", "fmt", "-p", "dodge-rl-env"])
SOURCES = harness.source_inventory()
write_new(OUT / "prebuild-source-manifest.json", SOURCES)
SOURCE_HASH = sha(OUT / "prebuild-source-manifest.json")
with tarfile.open(OUT / "prebuild-source.tar.gz", "w:gz") as archive:
    for name in SOURCES:
        archive.add(ROOT / name, arcname=name)

run("default-crate-tests", ["cargo", "+1.97.1", "test", "--locked", "-p", "dodge-rl-env", "--", "--nocapture", "--test-threads=1"])
run("workspace-fmt", ["cargo", "+1.97.1", "fmt", "--all", "--", "--check"])
run("workspace-clippy", ["cargo", "+1.97.1", "clippy", "--locked", "--workspace", "--all-targets", "--all-features", "--", "-D", "warnings"])
compile_log = run("release-test-compile", ["cargo", "+1.97.1", "test", "--release", "--locked", "-p", "dodge-rl-env", "--no-default-features", "--lib", "--no-run", "--message-format=json"])
artifacts = []
for line in compile_log.read_text().splitlines():
    try:
        item = json.loads(line)
    except json.JSONDecodeError:
        continue
    if item.get("reason") == "compiler-artifact" and item.get("executable") and item.get("profile", {}).get("test") and item.get("target", {}).get("name") == "dodge_rl_env":
        artifacts.append(item)
assert len(artifacts) == 1, artifacts
binary = Path(artifacts[0]["executable"]).resolve()
write_new(OUT / "native-test-binary.json", {"path": str(binary), "sha256": sha(binary), "compiler_artifact": artifacts[0], "full_campaign_executed": False})
run("small-d2-replay", [binary, "tests::frozen_m0_ten_paired_episodes_per_policy", "--ignored", "--exact", "--nocapture", "--test-threads=1"], seconds=120)
run("pinned-extension-develop", [ROOT / "python/.venv/bin/maturin", "develop", "--release", "--uv", "--locked"], cwd=ROOT / "python")
extension = ROOT / "python/dodge_rl/_native.cpython-312-darwin.so"
shutil.copyfile(extension, OUT / "native.cpython-312-darwin.so")
run("real-extension-pytest", [ROOT / "python/.venv/bin/python", "-m", "pytest", "-q", "tests/test_env.py"], cwd=ROOT / "python")
run("matching-wheel", [ROOT / "python/.venv/bin/maturin", "build", "--release", "--locked", "--out", OUT / "wheels"], cwd=ROOT / "python")
assert harness.source_inventory() == SOURCES, "Build inputs changed during checks"
write_new(OUT / "build-receipt.json", {
    "at_utc": datetime.now(timezone.utc).isoformat(), "status": "passed",
    "source_manifest": str(OUT / "prebuild-source-manifest.json"),
    "source_manifest_sha256": SOURCE_HASH, "source_archive_sha256": sha(OUT / "prebuild-source.tar.gz"),
    "source_files": len(SOURCES), "source_unchanged_through_checks": True,
    "native_test_binary": str(binary), "native_test_binary_sha256": sha(binary),
    "installed_extension": str(extension), "installed_extension_sha256": sha(extension),
    "archived_extension_sha256": sha(OUT / "native.cpython-312-darwin.so"),
    "commands": RECORDS, "full_campaign_executed": False,
    "prior_build_input_manifest_gap_resolved_by_new_prebuild_pin": True,
    "prior_intermediate_binary_limit_unchanged": True,
})
print(json.dumps({"status": "passed", "build_receipt": str(OUT / "build-receipt.json"),
                  "native_test_binary": str(binary), "extension_sha256": sha(extension),
                  "elapsed_seconds": time.monotonic()-START}), flush=True)
