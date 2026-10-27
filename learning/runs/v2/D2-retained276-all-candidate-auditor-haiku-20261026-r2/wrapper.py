"""Terminal wrapper for the frozen retained-276 continuation all-candidate auditor.

Bootstraps under exact interpreter, bytecode, registration, auditor, and dependency gates,
then runs the frozen auditor with a stricter runtime import. Writes one exclusive record into
this directory. Grants no selection, continuation, replacement, lease clear, receipt, or
terminal acceptance authority. Full mode is parent-only and not exposed on the CLI here.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
PREP = ROOT / "learning/runs/v2/D2-retained276-continuation-prepare-luna-20261026-r2"
RUN = ROOT / "learning/runs/v2/D2-retained276-continuation-20261026-r2"
VENV = ROOT / "python/.venv"
VENV_SITE = VENV / "lib/python3.12/site-packages"
INTERPRETER = VENV / "bin/python"
PYCACHE_PREFIX = PREP / "empty-pycache"
REG_PATH = PREP / "registration.json"
REG_SHA = "477217f3c7617ccbe01c651db8932eab01f54ea3924f213e67b413e640cf866c"
AUD_PATH = OUT / "audit_candidates.py"
AUD_SHA = "726318b75981293eafd6dcdd0cf73c951747d4beb8826506072c0563bc6d1dd6"
DEP_ORIGINS = {"torch": VENV_SITE / "torch/__init__.py", "numpy": VENV_SITE / "numpy/__init__.py"}
AUTHORITY = {"selection": False, "best_replacement": False, "continuation": False,
             "terminal_acceptance": False, "lease_clear": False, "new_receipt": False, "retained_publication": False}
SCOPE = ("Read-only audit of the frozen 276->348 continuation auditor. Full mode is parent-only and needs the "
         "parent-owned observer record. Observer, worker, resource, wall, process-absence, and pin gates cover only "
         "what the observer and launcher records show; final publication absence and lease release stay with the parent.")


class WrapperError(RuntimeError):
    pass


def need(condition, message):
    if not condition:
        raise WrapperError(message)


def sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_pins(pins):
    need(isinstance(pins, dict) and bool(pins), "Missing input pins")
    for name, digest in pins.items():
        path = Path(name)
        need(path.is_absolute() and path.is_file() and len(digest) == 64, f"Invalid pinned file: {name}")
        need(sha_file(path) == digest, f"Pinned input changed: {name}")
    return len(pins)


def bind_interpreter(reg):
    need(sys.executable == str(INTERPRETER) and reg["interpreter"] == str(INTERPRETER),
         f"Lexical interpreter differs: {sys.executable}")
    need(Path(sys.executable).resolve() == Path(reg["interpreter"]).resolve(), "Interpreter origin differs")
    need(Path(sys.prefix).resolve() == VENV.resolve(), "Virtualenv prefix differs")
    need(sys.version.split()[0] == reg["runtime_versions"]["python"], "Python version differs")


def bind_bytecode():
    """-B in this process and the inherited env flag for every nested subprocess; prefix stays empty."""
    need(sys.dont_write_bytecode and sys.flags.dont_write_bytecode, "Bytecode writing must be disabled (-B)")
    need(os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "PYTHONDONTWRITEBYTECODE=1 must be inherited")
    need(sys.pycache_prefix == str(PYCACHE_PREFIX) and os.environ.get("PYTHONPYCACHEPREFIX") == str(PYCACHE_PREFIX),
         "Bytecode prefix differs from registration")
    need(PYCACHE_PREFIX.is_dir() and not any(PYCACHE_PREFIX.iterdir()), "Registered bytecode prefix is not empty")
    need("PYTHONPATH" not in os.environ, "PYTHONPATH must be unset")


def reject_preloaded_dodge():
    loaded = sorted(name for name in sys.modules if name == "dodge_rl" or name.startswith("dodge_rl."))
    need(not loaded, f"Preloaded Dodge modules rejected: {loaded}")


def load_registration():
    need(sha_file(REG_PATH) == REG_SHA, "Registration digest differs")
    return json.loads(REG_PATH.read_bytes())


def load_auditor():
    """Exec the exact pinned auditor bytes; no import-path lookup."""
    source = AUD_PATH.read_bytes()
    need(hashlib.sha256(source).hexdigest() == AUD_SHA, "Auditor source digest differs")
    module = types.ModuleType("audit_candidates")
    module.__file__ = str(AUD_PATH)
    exec(compile(source, str(AUD_PATH), "exec", dont_inherit=True), module.__dict__)
    return module


def dependency_origin(name):
    """Origin without importing: sys.modules if already loaded, else the path finder only."""
    module = sys.modules.get(name)
    if module is not None:
        return Path(module.__file__).resolve()
    spec = importlib.util.find_spec(name)
    need(spec is not None and spec.origin, f"{name} origin not found")
    return Path(spec.origin).resolve()


def bind_dependency_origins(reg):
    origins = {}
    for name, expected in DEP_ORIGINS.items():
        origin = dependency_origin(name)
        need(origin == expected.resolve(), f"{name} origin differs: {origin}")
        need(origin.is_relative_to(VENV_SITE.resolve()) and reg["pins"].get(str(origin)) == sha_file(origin),
             f"{name} origin is not a registered dependency pin")
        origins[name] = {"path": str(origin), "sha256": reg["pins"][str(origin)]}
    return origins


def make_strict_import_runtime(original, reg):
    """Reject preloaded Dodge modules before the frozen import; check exact origins after it."""
    runtime = Path(reg["runtime_root"]).resolve()
    members = reg["runtime_continuity"]["member_sha256"]

    def strict_import_runtime(reg_arg):
        need(reg_arg == reg, "Runtime registration differs from wrapper registration")
        reject_preloaded_dodge()
        result = original(reg_arg)
        check_loaded_dodge(reg, runtime, members)
        return result

    return strict_import_runtime


def check_loaded_dodge(reg, runtime, members):
    origins = {}
    for name, module in sorted(sys.modules.items()):
        if not (name == "dodge_rl" or name.startswith("dodge_rl.")):
            continue
        path = Path(getattr(module, "__file__", "") or "").resolve()
        relative = path.relative_to(runtime).as_posix() if path.is_relative_to(runtime) else None
        need(relative in members and sha_file(path) == members[relative] == reg["pins"].get(str(path)),
             f"Dodge module origin not a pinned runtime member: {name} {path}")
        origins[name] = {"path": str(path), "sha256": members[relative]}
    exact = {"dodge_rl": "dodge_rl/__init__.py", "dodge_rl.checkpoints": "dodge_rl/checkpoints.py",
             "dodge_rl.survival_gate": "dodge_rl/survival_gate.py", "dodge_rl.identity": "dodge_rl/identity.py",
             "dodge_rl._native": "dodge_rl/_native.cpython-312-darwin.so"}
    for name, relative in exact.items():
        need(name in origins and origins[name]["path"] == str((runtime / relative).resolve()),
             f"Exact Dodge origin differs or is missing: {name}")
    need(origins["dodge_rl._native"]["sha256"] == reg["native"]["sha256"], "Current native digest differs")
    need(sys.path[0] == str(runtime), "Runtime root is not the first import path entry")
    return origins


def check_versions(reg):
    versions = reg["runtime_versions"]
    need(str(sys.modules["torch"].__version__) == versions["torch"], "Torch version differs")
    need(str(sys.modules["numpy"].__version__) == versions["numpy"], "NumPy version differs")
    need(sys.version.split()[0] == versions["python"], "Python version differs")


def terminal_gates(observation, execution, worker):
    """Observer and launcher records, read after writers are reaped. Final publication is parent-gated."""
    need(observation["outer_raw_exit"] == 0 and observation["worker_raw_exit"] == 0
         and observation["first_event"] is None and observation["launch_count"] == 1
         and execution["actual_worker_launch_count"] == 1 and execution["observed_worker_raw_exit"] == 0,
         "Observer raw exits or launch count differ")
    need(execution["status"] == "passed" and worker["status"] == "completed" and worker["first_failure"] is None,
         "Terminal status differs")
    need(0 < observation["outer_inclusive_wall_seconds"] <= observation["outer_limit_seconds"],
         "Outer wall outside registered limit")
    need(observation["max_aggregate_rss_bytes"] <= observation["aggregate_rss_limit_bytes"],
         "Aggregate RSS over cap")
    need(worker["peak_rss_bytes"] <= observation["aggregate_rss_limit_bytes"]
         and worker["peak_mps_driver_bytes"] <= observation["mps_limit_bytes"], "Worker memory over cap")
    need(observation["postflight"]["pins"]["failures"] == [] and observation["postflight"]["cache_empty_after"] is True,
         "Source postflight differs")
    need(all(observation[key] is True for key in ("outer_process_absent", "worker_process_absent", "worker_group_absent")),
         "Owned process absence differs in observer record")
    return {"outer_raw_exit": 0, "worker_raw_exit": 0, "outer_inclusive_wall_seconds": observation["outer_inclusive_wall_seconds"],
            "max_aggregate_rss_bytes": observation["max_aggregate_rss_bytes"],
            "peak_worker_rss_bytes": worker["peak_rss_bytes"], "peak_mps_driver_bytes": worker["peak_mps_driver_bytes"]}


def owned_processes_absent(observation, execution):
    """Live process check after the run: the owned pids and process groups must be gone."""
    for pid in (observation["observer_pid"], observation["outer_pid"], execution["worker_pid"]):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        raise WrapperError(f"Owned process still exists: {pid}")
    for pgid in (observation["outer_process_group"], execution["owned_pgid"]):
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            continue
        raise WrapperError(f"Owned process group still exists: {pgid}")
    return True


def run_audit(*, provisional, name, observer_dir=None):
    need(Path(name).name == name and name.endswith(".json"), "Output must be a plain .json name")
    reg = load_registration()
    bind_interpreter(reg)
    reject_preloaded_dodge()
    bind_bytecode()
    pins_before = verify_pins(reg["pins"])
    aud = load_auditor()
    origins = bind_dependency_origins(reg)

    aud.import_runtime = make_strict_import_runtime(aud.import_runtime, reg)
    if not provisional:
        need(observer_dir is not None, "Full mode requires the parent-owned observer directory")
        aud.check_observer_dir(observer_dir)
    audit = aud.audit(provisional=provisional, observer_dir=observer_dir)
    check_versions(reg)
    dodge_origins = check_loaded_dodge(reg, Path(reg["runtime_root"]).resolve(), reg["runtime_continuity"]["member_sha256"])

    gates = None
    if not provisional:
        need(observer_dir is not None, "Full mode requires the parent-owned observer directory")
        execution = json.loads((RUN / "execution-result.json").read_bytes())
        worker = json.loads((RUN / "worker-result.json").read_bytes())
        observation = json.loads((Path(observer_dir) / "observation.json").read_bytes())
        gates = terminal_gates(observation, execution, worker)
        gates["owned_processes_absent"] = owned_processes_absent(observation, execution)

    pins_after = verify_pins(reg["pins"])
    need(pins_before == pins_after and sha_file(REG_PATH) == REG_SHA and sha_file(AUD_PATH) == AUD_SHA,
         "Registration, auditor, or pins changed during audit")
    need(not any(PYCACHE_PREFIX.iterdir()), "Bytecode prefix gained files")
    bind_interpreter(reg)

    record = {
        "schema": "d2_retained276_continuation_terminal_wrapper_audit_v1",
        "mode": "provisional_readonly" if provisional else "full_parent_only",
        "authority": dict(AUTHORITY),
        "scope": SCOPE,
        "wrapper_sha256": sha_file(Path(__file__).resolve()),
        "auditor": {"path": str(AUD_PATH), "sha256": AUD_SHA},
        "registration": {"path": str(REG_PATH), "sha256": REG_SHA, "pins_checked_before_and_after": pins_after},
        "interpreter": {"lexical": sys.executable, "resolved": str(Path(sys.executable).resolve()),
                        "prefix": sys.prefix, "version": sys.version.split()[0]},
        "bytecode": {"dont_write_bytecode": True, "inherited_env_PYTHONDONTWRITEBYTECODE": "1",
                     "pycache_prefix": str(PYCACHE_PREFIX), "empty_after": True},
        "dependency_origins": origins,
        "dodge_origins": dodge_origins,
        "terminal_gates": gates,
        "audit": audit,
    }
    path = OUT / name
    with path.open("x") as stream:
        json.dump(record, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only provisional audit; full mode is parent-only.")
    parser.add_argument("--provisional", action="store_true", help="required; read-only published-prefix audit")
    parser.add_argument("--name", default="wrapper-provisional-audit.json")
    args = parser.parse_args(argv)
    if not args.provisional:
        parser.error("only --provisional is available here; full mode is parent-only")
    record = run_audit(provisional=True, name=args.name)
    print(json.dumps({"status": "passed", "output": args.name, "mode": record["mode"],
                      "updates_audited": record["audit"]["updates_audited"],
                      "proposed_best_update": record["audit"]["proposed_best_update"]}, sort_keys=True))


if __name__ == "__main__":
    main()
