"""R5 successor: unchanged checkpoint bytes, strictly rebound owned origins.

The parent model/Adam/RNG lineage is independent of the successor runtime identity.
Function, origin, default, module and private-global checks remain mandatory.
"""
from __future__ import annotations

import hashlib
import inspect
import dis
from pathlib import Path
import sys
import types

CHECKPOINTS_RELATIVE = Path("learning/runs/v2/progressive1000-throughput-runtime-parent-20261027-r1/runtime/dodge_rl/checkpoints.py")
CHECKPOINTS_SHA256 = "807141943a742c6e9fdd34274c191b3c318134cc7fb0c1c6256874cadee1cbc3"
IDENTITY_RELATIVE = Path("learning/runs/v2/progressive1000-throughput-runtime-parent-20261027-r1/runtime/dodge_rl/identity.py")
IDENTITY_SHA256 = "50775b2e7c30e53757dd3134d11613f716733cee8e6a96cc18b62e8ff2a4a053"
RUNNER_RELATIVE = Path("learning/runs/v2/D2-retained300-continuation-freeze-20261026-r5/runner.py")
RUNNER_SHA256 = "108ba55ad78aa26166acb14f67cc6466da6293ccee3d272e1fe6e775ebf2ac60"
RAW_RNG_KEYS = frozenset({"python", "numpy_global", "numpy_generator", "torch_cpu", "torch_mps", "sampling_backend"})
CHECKPOINT_FUNCTIONS = ("capture_rng", "restore_rng", "require_complete_update", "restore_learner")


def _read_pinned(root, relative, expected):
    path = (root / relative).resolve()
    if root not in path.parents or not path.is_file():
        raise ValueError(f"pinned trusted source mismatch: {relative}")
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != expected:
        raise ValueError(f"pinned trusted source mismatch: {relative}")
    return path, source


def verify_pinned_sources(project_root):
    root = Path(project_root).resolve()
    result = {}
    for relative, expected in ((CHECKPOINTS_RELATIVE, CHECKPOINTS_SHA256),
                               (IDENTITY_RELATIVE, IDENTITY_SHA256),
                               (RUNNER_RELATIVE, RUNNER_SHA256)):
        path, _ = _read_pinned(root, relative, expected)
        result[str(relative)] = {"path": str(path), "sha256": expected}
    return result


def _definitions(source, filename, names):
    module_code = compile(source, str(filename), "exec", flags=0, dont_inherit=True)
    found = {item.co_name: item for item in module_code.co_consts
             if isinstance(item, types.CodeType) and item.co_name in names}
    if set(found) != set(names):
        raise ValueError("pinned source function definitions missing")
    return found


def _code_signature(code):
    constants = tuple(_code_signature(value) if isinstance(value, types.CodeType) else
                      (type(value).__module__, type(value).__qualname__, value)
                      for value in code.co_consts)
    instructions = tuple((item.opname, _code_signature(item.argval)
                          if isinstance(item.argval, types.CodeType) else item.argval)
                         for item in dis.get_instructions(code))
    return (instructions, constants, code.co_names, code.co_varnames, code.co_freevars,
            code.co_cellvars, code.co_argcount, code.co_posonlyargcount,
            code.co_kwonlyargcount, code.co_nlocals, code.co_flags, code.co_exceptiontable)


def _bind_functions(namespace, pinned, names, source_path):
    for name in names:
        function = namespace.get(name)
        if not inspect.isfunction(function) or function.__globals__ is not namespace:
            raise ValueError(f"trusted function namespace mismatch: {name}")
        if Path(inspect.getsourcefile(function) or "").resolve() != source_path:
            raise ValueError(f"trusted API function origin mismatch: {name}")
        if _code_signature(function.__code__) != _code_signature(pinned[name]):
            raise ValueError(f"trusted function code mismatch: {name}")


def build_callbacks(*, project_root, checkpoint_module, runner_namespace, parent_state,
                    model, optimizer, capture_module_hash=None):
    """Return callbacks only when loaded code matches hash-pinned source definitions.

    No project module is imported or executed here. The optional legacy hash argument
    is ignored: caller-supplied hashes do not prove loaded function identity.
    """
    root = Path(project_root).resolve()
    checkpoint_path, checkpoint_bytes = _read_pinned(root, CHECKPOINTS_RELATIVE, CHECKPOINTS_SHA256)
    identity_path, identity_bytes = _read_pinned(root, IDENTITY_RELATIVE, IDENTITY_SHA256)
    runner_path, runner_bytes = _read_pinned(root, RUNNER_RELATIVE, RUNNER_SHA256)
    sources = {str(CHECKPOINTS_RELATIVE): {"path": str(checkpoint_path), "sha256": CHECKPOINTS_SHA256},
               str(IDENTITY_RELATIVE): {"path": str(identity_path), "sha256": IDENTITY_SHA256},
               str(RUNNER_RELATIVE): {"path": str(runner_path), "sha256": RUNNER_SHA256}}
    if Path(getattr(checkpoint_module, "__file__", "")).resolve() != checkpoint_path:
        raise ValueError("checkpoint module origin mismatch")
    checkpoint_ns = checkpoint_module.__dict__
    expected_checkpoint = _definitions(checkpoint_bytes, checkpoint_path, CHECKPOINT_FUNCTIONS)
    _bind_functions(checkpoint_ns, expected_checkpoint, CHECKPOINT_FUNCTIONS, checkpoint_path)
    identity_require = _definitions(identity_bytes, identity_path, ("require",))["require"]
    require_function = checkpoint_ns.get("require")
    if (not inspect.isfunction(require_function)
            or Path(inspect.getsourcefile(require_function) or "").resolve() != identity_path
            or _code_signature(require_function.__code__) != _code_signature(identity_require)):
        raise ValueError("identity require dependency mismatch")
    for name in ("copy", "random", "numpy", "torch"):
        module_name = "numpy" if name == "numpy" else name
        expected_module = sys.modules.get(module_name)
        if expected_module is None or checkpoint_ns.get(name if name != "numpy" else "np") is not expected_module:
            raise ValueError(f"driver module dependency mismatch: {module_name}")
    if checkpoint_ns["capture_rng"].__defaults__ != ("cpu", None):
        raise ValueError("capture_rng defaults mismatch")
    if checkpoint_ns["restore_learner"].__defaults__ != ("cpu",):
        raise ValueError("restore_learner defaults mismatch")
    if checkpoint_ns["restore_rng"].__defaults__ != ("cpu", None):
        raise ValueError("restore_rng defaults mismatch")

    # Build all callable dependencies from the authenticated code objects. Never
    # let callbacks resolve names through the caller's mutable module dictionary.
    private_builtins = dict(vars(__import__("builtins")))
    private_builtins["ValueError"] = ValueError
    private_ns = {"__builtins__": private_builtins, "__name__": "_pinned_checkpoint_callbacks",
                  "__file__": str(checkpoint_path), "copy": sys.modules["copy"],
                  "random": sys.modules["random"], "np": sys.modules["numpy"],
                  "torch": sys.modules["torch"]}
    private_ns["require"] = types.FunctionType(identity_require, private_ns, "require")
    private_ns["require"].__module__ = "_pinned_identity"
    private_ns["require"].__code__ = identity_require
    private_ns["require"].__globals__["__file__"] = str(identity_path)
    private_functions = {}
    for name in CHECKPOINT_FUNCTIONS:
        defaults = {"capture_rng": ("cpu", None), "restore_rng": ("cpu", None),
                    "require_complete_update": None, "restore_learner": ("cpu",)}[name]
        function = types.FunctionType(expected_checkpoint[name], private_ns, name, defaults)
        function.__module__ = "_pinned_checkpoints"
        function.__qualname__ = name
        function.__code__ = expected_checkpoint[name]
        private_functions[name] = function
    private_ns.update(private_functions)

    if not isinstance(runner_namespace, dict):
        raise ValueError("pinned runner namespace required")
    worker = runner_namespace.get("worker")
    if runner_namespace.get("__file__") is None or Path(runner_namespace["__file__"]).resolve() != runner_path:
        raise ValueError("pinned runner worker origin required")
    expected_worker = _definitions(runner_bytes, runner_path, ("worker",))
    _bind_functions(runner_namespace, expected_worker, ("worker",), runner_path)

    def restore_trusted():
        return private_functions["restore_learner"](parent_state, model, optimizer, "mps")

    def rng_capture():
        raw = private_functions["capture_rng"]("mps")
        if not isinstance(raw, dict) or set(raw) != RAW_RNG_KEYS:
            raise ValueError("capture_rng must return the pinned raw six-key RNG dictionary")
        return raw

    return {"restore_trusted": restore_trusted, "rng_capture": rng_capture,
            "verified_sources": sources, "api_names": {"restore": "restore_learner", "capture": "capture_rng"}}
