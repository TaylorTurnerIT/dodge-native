"""Run only synthetic CPU teacher/ray tests without importing dodge_rl._native.

Usage: python -B python/tests/run_ray_source_checks.py
Requires torch and pytest in an isolated development environment, not a native
wheel or campaign runtime. Package namespaces bypass the native-only __init__;
an import blocker rejects any attempt to import the extension. No game runner,
checkpoint, weights, notebook, or parent worktree is opened.
"""

import importlib.abc
from pathlib import Path
import signal
import sys
from types import ModuleType


class NoNative(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "dodge_rl._native" or fullname.startswith("dodge_rl._native."):
            raise RuntimeError("Native import forbidden in ray source checks")
        return None


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    for name, path in (("dodge_rl", root / "dodge_rl"),
                       ("dodge_rl.models", root / "dodge_rl/models")):
        package = ModuleType(name)
        package.__path__ = [str(path)]
        sys.modules[name] = package
    sys.meta_path.insert(0, NoNative())
    import torch
    import pytest

    # Existing teacher tests call global manual_seed. Keep their CPU semantics
    # without seeding accelerator generators, including Apple's default MPS RNG.
    def cpu_seed(seed):
        return torch.random.default_generator.manual_seed(seed)
    torch.manual_seed = cpu_seed

    def no_accelerator(*args, **kwargs):
        raise RuntimeError("Accelerator API forbidden in ray source checks")

    def unique_tripwire():
        def tripwire(*args, **kwargs):
            return no_accelerator(*args, **kwargs)
        return tripwire

    for name in ("manual_seed", "seed", "get_rng_state", "set_rng_state",
                 "synchronize", "empty_cache", "current_allocated_memory",
                 "driver_allocated_memory", "set_per_process_memory_fraction"):
        if hasattr(torch.mps, name):
            setattr(torch.mps, name, unique_tripwire())
    torch.cuda.manual_seed_all = unique_tripwire()
    torch.set_num_threads(1)
    signal.alarm(90)
    raise SystemExit(pytest.main([
        "-q", "-p", "no:cacheprovider",
        str(root / "tests/test_clearance_rays_source.py"),
        str(root / "tests/test_ray_teacher_source.py"),
        str(root / "tests/test_ray_migration_source.py"),
        str(root / "tests/test_teacher.py"),
    ]))
