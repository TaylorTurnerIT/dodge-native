"""Terminal wrapper for the frozen retained324 linear-LR all-candidate auditor.

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
PREP = ROOT / "learning/runs/v2/D2-retained324-linear-integrated-luna-20261026-r4"
RUN = ROOT / "learning/runs/v2/D2-retained324-linear-lr-20261026-r1"
BINDING_PATH = OUT / "audit-binding.json"
OBSERVER_DIR = None
OBSERVER_SOURCE = None
OBSERVER_SHA = None
VENV = ROOT / "python/.venv"
VENV_SITE = VENV / "lib/python3.12/site-packages"
INTERPRETER = VENV / "bin/python"
PYCACHE_PREFIX = OUT / "empty-pycache"
REG_PATH = PREP / "registration.json"
REG_SHA = None
AUD_PATH = OUT / "audit_candidates.py"
SCHEMA_PATH = PREP / "registration_schema.py"
AUD_SHA = None
BINDING = None
DEP_ORIGINS = {"torch": VENV_SITE / "torch/__init__.py", "numpy": VENV_SITE / "numpy/__init__.py"}
AUTHORITY = {"selection": False, "best_replacement": False, "continuation": False,
             "terminal_acceptance": False, "lease_clear": False, "new_receipt": False, "retained_publication": False}
SCOPE = ("Read-only audit of frozen selected324 linear-LR run 324->384. Full mode is parent-only and requires "
         "all terminal artifacts plus the exact parent-owned observer record. All candidates remain provisional; "
         "parent controls retained-best acceptance, lease, and publication.")


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


def load_binding():
    global BINDING, REG_SHA, AUD_SHA, OBSERVER_DIR, OBSERVER_SOURCE, OBSERVER_SHA
    need(BINDING_PATH.is_file(), "Parent-generated exact audit binding is required")
    BINDING = json.loads(BINDING_PATH.read_bytes())
    need(BINDING.get("schema") == "d2_retained324_linear_auditor_binding_v1"
         and BINDING.get("run_id") == RUN.name, "Audit binding identity differs")
    required_sources = {str((OUT / name).resolve()) for name in
                        ("audit_candidates.py", "wrapper.py", "binding_builder.py",
                         "schedule_contract.py", "lr_schedule.py")}
    need(set(BINDING.get("auditor_sources", {})) == required_sources,
         "OWN auditor source binding inventory differs")
    for name, digest in BINDING["auditor_sources"].items():
        need(Path(name).is_absolute() and sha_file(name) == digest, "OWN auditor source binding differs")
    REG_SHA = BINDING["registration"]["sha256"]
    need(Path(BINDING["registration"]["path"]).resolve() == REG_PATH.resolve(), "Bound registration path differs")
    need(sha_file(BINDING["reviewed_manifest"]["path"]) == BINDING["reviewed_manifest"]["sha256"],
         "Reviewed manifest digest differs")
    AUD_SHA = BINDING["auditor_sources"][str(AUD_PATH.resolve())]
    OBSERVER_SOURCE = Path(BINDING["observer_source"]["path"])
    OBSERVER_SHA = BINDING["observer_source"]["sha256"]
    OBSERVER_DIR = OBSERVER_SOURCE.parent
    return BINDING


def bind_observer_directory(observer_dir):
    need(observer_dir is not None and Path(observer_dir).resolve() == OBSERVER_DIR.resolve(),
         "Full mode requires the exact registered parent-owned observer directory")
    need(sha_file(OBSERVER_SOURCE) == OBSERVER_SHA, "Registered observer source digest differs")
    return str(OBSERVER_DIR)


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
    need(BINDING is not None and sha_file(REG_PATH) == REG_SHA, "Registration digest differs")
    return json.loads(REG_PATH.read_bytes())


def load_auditor():
    """Exec exact current successor auditor bytes; wrapper hash pins it after freeze."""
    source = AUD_PATH.read_bytes()
    need(len(AUD_SHA) == 64 and hashlib.sha256(source).hexdigest() == AUD_SHA, "Auditor source digest differs")
    if str(OUT) not in sys.path:
        sys.path.insert(0, str(OUT))
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


def terminal_gates(observation, execution, worker, reg):
    """Observer and launcher records, read after writers are reaped. Final publication is parent-gated."""
    need(observation["outer_raw_exit"] == 0 and observation["worker_raw_exit"] == 0
         and observation["first_event"] is None and observation["launch_count"] == 1
         and execution["actual_worker_launch_count"] == 1 and execution["observed_worker_raw_exit"] == 0
         and observation.get("success_authoritative") is True,
         "Observer raw exits, launch count, or authoritative status differ")
    need(execution["status"] == "passed" and worker["status"] == "completed" and worker["first_failure"] is None,
         "Terminal status differs")
    need(0 < observation["outer_inclusive_wall_seconds"] <= observation["outer_limit_seconds"],
         "Outer wall outside registered limit")
    need(observation["max_aggregate_rss_bytes"] <= observation["aggregate_rss_limit_bytes"],
         "Aggregate RSS over cap")
    need(worker["peak_rss_bytes"] <= observation["aggregate_rss_limit_bytes"]
         and worker["peak_mps_driver_bytes"] <= observation["mps_limit_bytes"], "Worker memory over cap")
    postflight = observation["postflight"]
    lease = postflight["lease"]
    need(postflight["pins"]["checked"] == len(reg["pins"]) and postflight["pins"]["failures"] == []
         and postflight["cache_empty_after"] is True and postflight["publication_failure_absent"] is True,
         "Source, cache, or publication postflight differs")
    need(lease["active_long_campaign_exact"] is True and lease["active_inference_campaign"] is None
         and lease["active_inference_lease"] is None and lease["active_inference_diagnostic"] is None,
         "Observer lease postflight differs")
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
    for pgid in (observation.get("outer_process_group"), execution["owned_pgid"]):
        if pgid is None:
            continue
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            continue
        raise WrapperError(f"Owned process group still exists: {pgid}")
    return True


def run_audit(*, provisional, name, observer_dir=None):
    need(Path(name).name == name and name.endswith(".json"), "Output must be a plain .json name")
    load_binding()
    if not provisional:
        bind_observer_directory(observer_dir)
    reg = load_registration()
    need(SCHEMA_PATH.resolve() == Path(reg["registration_schema_path"]).resolve()
         and sha_file(SCHEMA_PATH) == reg["registration_schema_sha256"]
         and reg["pins"].get(str(SCHEMA_PATH.resolve())) == reg["registration_schema_sha256"],
         "Registration schema origin or digest differs")
    bind_interpreter(reg)
    reject_preloaded_dodge()
    bind_bytecode()
    pins_before = verify_pins(reg["pins"])
    aud = load_auditor()
    origins = bind_dependency_origins(reg)

    aud.import_runtime = make_strict_import_runtime(aud.import_runtime, reg)
    audit = aud.audit(provisional=provisional, observer_dir=observer_dir)
    check_versions(reg)
    dodge_origins = check_loaded_dodge(reg, Path(reg["runtime_root"]).resolve(), reg["runtime_continuity"]["member_sha256"])

    gates = None
    if not provisional:
        need(observer_dir is not None, "Full mode requires the parent-owned observer directory")
        execution = json.loads((RUN / "execution-result.json").read_bytes())
        worker = json.loads((RUN / "worker-result.json").read_bytes())
        observation = json.loads((Path(observer_dir) / "observation.json").read_bytes())
        gates = terminal_gates(observation, execution, worker, reg)
        gates["owned_processes_absent"] = owned_processes_absent(observation, execution)
        need(sha_file(OBSERVER_SOURCE) == OBSERVER_SHA, "Registered observer source changed during audit")

    pins_after = verify_pins(reg["pins"])
    need(pins_before == pins_after and sha_file(REG_PATH) == REG_SHA and sha_file(AUD_PATH) == AUD_SHA,
         "Registration, auditor, or pins changed during audit")
    need(not any(PYCACHE_PREFIX.iterdir()), "Bytecode prefix gained files")
    bind_interpreter(reg)

    record = {
        "schema": "d2_retained324_linear_lr_terminal_wrapper_audit_v1",
        "mode": "provisional_readonly" if provisional else "full_parent_only",
        "authority": dict(AUTHORITY),
        "scope": "Read-only full candidate audit; parent owns acceptance, lease clear, and publication.",
        "wrapper_sha256": sha_file(Path(__file__).resolve()),
        "auditor": {"path": str(AUD_PATH), "sha256": AUD_SHA},
        "registration": {"path": str(REG_PATH), "sha256": REG_SHA, "pins_checked_before_and_after": pins_after},
        "reviewed_manifest": BINDING["reviewed_manifest"],
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


def full_mode(*, observer_dir, name="full-audit.json"):
    """Parent-only entry point. Requires all six candidates and successful closed terminal receipts."""
    return run_audit(provisional=False, name=name, observer_dir=observer_dir)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only provisional audit; full mode is parent-only.")
    parser.add_argument("--provisional", action="store_true", help="required; read-only published-prefix audit")
    parser.add_argument("--name", default="wrapper-provisional-audit.json")
    args = parser.parse_args(argv)
    if not args.provisional:
        parser.error("full mode is parent-only; call wrapper.full_mode(observer_dir=..., name=...)")
    record = run_audit(provisional=True, name=args.name)
    print(json.dumps({"status": "passed", "output": args.name, "mode": record["mode"],
                      "updates_audited": record["audit"]["updates_audited"],
                      "proposed_best_update": record["audit"]["proposed_best_update"]}, sort_keys=True))


if __name__ == "__main__":
    main()
