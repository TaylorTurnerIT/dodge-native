from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent
ENV = ROOT / "python/.venv"
LEGACY = ROOT / "learning/.venv"
START = time.monotonic()
COMMANDS = []


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write(name, value):
    (EVIDENCE / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def run(name, args):
    remaining = 580 - (time.monotonic() - START)
    if remaining <= 0:
        raise RuntimeError("setup budget exhausted before next command")
    record = {"name": name, "args": list(map(str, args)), "started_at_utc": now()}
    COMMANDS.append(record)
    write("commands.json", COMMANDS)
    try:
        with (EVIDENCE / (name + ".log")).open("x") as log:
            result = subprocess.run(record["args"], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=remaining, check=False)
        record["exit_code"] = result.returncode
        if result.returncode:
            raise RuntimeError(f"{name} exited {result.returncode}; log retained")
    finally:
        record["finished_at_utc"] = now()
        write("commands.json", COMMANDS)
    return (EVIDENCE / (name + ".log")).read_text()


receipt = {"status": "running", "started_at_utc": now(), "root": str(ROOT), "venv": str(ENV)}
write("receipt.json", receipt)
try:
    if ENV.exists():
        raise RuntimeError("new environment unexpectedly exists; refusing replacement")
    legacy_cfg = hashlib.sha256((LEGACY / "pyvenv.cfg").read_bytes()).hexdigest()
    receipt["legacy_pyvenv_cfg_sha256_before"] = legacy_cfg
    receipt["uv_version"] = run("uv-version", ["uv", "--version"]).strip()
    base = run("base-python", [str(LEGACY / "bin/python"), "-c", "import sys;print(sys._base_executable)"]).strip()
    receipt["base_python"] = base
    run("create-venv", ["uv", "venv", "--python", base, str(ENV)])
    run("install", ["uv", "pip", "install", "--python", str(ENV / "bin/python"), "torch==2.14.1", "numpy==2.5.4", "pytest", "maturin", "--no-progress"])
    verify = '''import importlib.metadata as m,json,platform,sys,torch,numpy,pytest
torch.set_num_threads(1)
cpu=float((torch.tensor([1.,2.])*2).sum().item())
assert cpu==6.0
built=torch.backends.mps.is_built()
available=torch.backends.mps.is_available()
mps=None
if available:
    mps=float((torch.tensor([1.,2.],device="mps")*2).sum().cpu().item())
    torch.mps.synchronize()
    assert mps==6.0
assert m.version("torch")=="2.14.1"
assert m.version("numpy")=="2.5.4"
print(json.dumps({"python":sys.version,"executable":sys.executable,"base_prefix":sys.base_prefix,"platform":platform.platform(),"machine":platform.machine(),"versions":{name:m.version(name) for name in ["torch","numpy","pytest","maturin"]},"imports":{"torch":torch.__file__,"numpy":numpy.__file__,"pytest":pytest.__file__},"cpu_tensor_sum":cpu,"mps_built":built,"mps_available":available,"mps_tensor_sum":mps},indent=2))'''
    verification = json.loads(run("verify-imports-and-tensors", [str(ENV / "bin/python"), "-c", verify]))
    write("verification.json", verification)
    run("pytest-version", [str(ENV / "bin/pytest"), "--version"])
    run("maturin-version", [str(ENV / "bin/maturin"), "--version"])
    freeze = run("freeze", ["uv", "pip", "freeze", "--python", str(ENV / "bin/python")])
    (EVIDENCE / "requirements-freeze.txt").write_text(freeze)
    versions = verification["versions"]
    req = ROOT / "python/requirements-local-mac.txt"
    req.write_text("# Local Mac v2 environment, verified on CPython 3.12.15 (arm64).\n" + "".join(f"{name}=={versions[name]}\n" for name in ["torch", "numpy", "pytest", "maturin"]))
    receipt["verification"] = verification
    receipt["requirements_sha256"] = hashlib.sha256(req.read_bytes()).hexdigest()
    receipt["legacy_pyvenv_cfg_sha256_after"] = hashlib.sha256((LEGACY / "pyvenv.cfg").read_bytes()).hexdigest()
    if receipt["legacy_pyvenv_cfg_sha256_after"] != legacy_cfg:
        raise RuntimeError("legacy environment config changed during setup")
    receipt["status"] = "complete"
except BaseException as error:
    receipt.update(status="failed", error=f"{type(error).__name__}: {error}")
    raise
finally:
    receipt.update(finished_at_utc=now(), elapsed_seconds=time.monotonic() - START)
    write("receipt.json", receipt)
    hashes = {str(p.relative_to(EVIDENCE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in EVIDENCE.rglob("*") if p.is_file() and p.name != "artifact-sha256.json"}
    write("artifact-sha256.json", hashes)
