"""Exercise the production evaluator API with an isolated, strict fake runtime.

Static identity validation is replaced by a fixture. This test establishes API
wiring and publication behavior, not native acceptance or launch authority.
"""
import hashlib
import importlib.util
import inspect
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch

from test_expanded_eval import FakeEnv, OWN_DIRECTORY, expanded_eval


class SuccessPathTests(unittest.TestCase):
    def exercise(self, module, expect_name_error=False):
        with tempfile.TemporaryDirectory(dir=OWN_DIRECTORY) as directory:
            root = Path(directory)
            checkpoint = root / "fake-checkpoint.bin"
            checkpoint.write_bytes(b"synthetic; never deserialized")
            native_path = root / module.NATIVE_RELATIVE_PATH
            native_path.parent.mkdir(parents=True)
            native_path.write_bytes(b"synthetic; never imported as an extension")
            protocol = root / "protocol.json"
            protocol.write_text('{"training_excluded_ranges":[[1,2],[5,8]]}')
            out = root / "result.json"
            seeds = list(range(0xD1001000, 0xD1001008))
            cohort_sha = "b" * 64
            runtime = dict(root=str(root), backend="cpu", torch_version=torch.__version__,
                           numpy_version=np.__version__, pycache_prefix=sys.pycache_prefix,
                           member_sha256={})
            candidate = dict(checkpoint_path=str(checkpoint),
                             checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest())
            reg = dict(runtime=runtime, cohorts={"ranking": {"manifest_sha256": cohort_sha}})
            tracker = {"constructed": [], "boundaries": []}

            class Teacher(torch.nn.Module):
                def __init__(self):
                    super().__init__()
                    self.register_buffer("weights", torch.arange(9, dtype=torch.float32))

                def forward(self, features):
                    return types.SimpleNamespace(logits=self.weights.expand(features.shape[0], -1))

            def strict_env(**kwargs):
                ranges = kwargs["excluded_seed_ranges"]
                if ranges != [(1, 2), (5, 8)] or any(type(pair) is not tuple for pair in ranges):
                    raise TypeError("native boundary requires tuple pairs")
                tracker["boundaries"].append(ranges)
                return FakeEnv(kwargs["seeds_by_slot"][0][0], tracker)

            modules = {}
            for name, relative in (("dodge_rl", "dodge_rl/__init__.py"),
                                   ("dodge_rl.models", "dodge_rl/models/__init__.py"),
                                   ("dodge_rl.dev_eval", "dodge_rl/dev_eval.py"),
                                   ("dodge_rl.identity", "dodge_rl/identity.py"),
                                   ("dodge_rl.checkpoints", "dodge_rl/checkpoints.py"),
                                   ("dodge_rl._native", module.NATIVE_RELATIVE_PATH)):
                modules[name] = types.ModuleType(name)
                modules[name].__file__ = str(root / relative)
            package = modules["dodge_rl"]
            package.__path__ = [str(root / "dodge_rl")]
            for name in ("models", "dev_eval", "identity", "checkpoints", "_native"):
                setattr(package, name, modules["dodge_rl." + name])
            package.VecDodgeEnv = strict_env
            modules["dodge_rl.models"].OmniscientEntityTeacher = Teacher
            modules["dodge_rl.identity"].OBSERVATION_KEYS = ("global_feats",)
            modules["dodge_rl.dev_eval"].death_fields = lambda info, *args: {
                key: info[key] for key in ("death_cause", "fatal_gameplay_frame", "death_observed_lethal_contacts")}
            modules["dodge_rl.checkpoints"].load_checkpoint = lambda *args, **kwargs: {
                "model": Teacher().state_dict()}
            guards = []
            original_getfile = inspect.getfile
            getfile = lambda obj: str(root / "dodge_rl/models/teacher.py") if obj is Teacher else original_getfile(obj)
            old_path = list(sys.path)
            try:
                with patch.dict(sys.modules, modules), patch.object(inspect, "getfile", side_effect=getfile), \
                     patch.object(module, "_validate_static", return_value=(reg, {}, seeds, candidate, root, out)), \
                     patch.object(module, "_trusted_module_cache"), patch.object(module, "_BACKEND_IDENTITY", None), \
                     patch.object(module, "PROTOCOL_PATH", protocol), \
                     patch.object(module, "NATIVE_SHA256", hashlib.sha256(native_path.read_bytes()).hexdigest()):
                    arguments = dict(registration_path=str(root / "fixture.json"), registration_sha256="c" * 64,
                                     candidate_update=348, cohort_name="ranking", output_path=str(out),
                                     check_guard=lambda: guards.append(True))
                    if expect_name_error:
                        with self.assertRaisesRegex(NameError, "chosen"):
                            module.evaluate_registered(**arguments)
                        self.assertFalse(out.exists())
                    else:
                        result = module.evaluate_registered(**arguments)
                        self.assertEqual(json.loads(out.read_text()), result)
                        self.assertEqual(result["cohort_sha256"], cohort_sha)
                        self.assertTrue(result["complete"])
                        self.assertEqual(result["episodes"], len(seeds))
                        self.assertEqual([row["seed"] for row in result["rows"]], seeds)
                        self.assertGreater(len(guards), 4)
                self.assertEqual(len(tracker["boundaries"]), len(seeds))
            finally:
                sys.path[:] = old_path

    def test_successful_publication_and_strict_native_boundary_wiring(self):
        self.exercise(expanded_eval)

    def test_predecessor_fails_after_inference_without_publishing(self):
        predecessor = OWN_DIRECTORY.parent / "expanded-evaluator-native-boundary-repair-luna-20261026-r3/expanded_eval.py"
        spec = importlib.util.spec_from_file_location("predecessor_publication_regression", predecessor)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.exercise(module, expect_name_error=True)
