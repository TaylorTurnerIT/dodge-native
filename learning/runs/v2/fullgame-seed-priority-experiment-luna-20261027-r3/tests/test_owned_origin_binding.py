"""Bind unchanged checkpoint code from the owned runtime before any restore call."""
import importlib
import sys
import types
import unittest
from pathlib import Path

import torch

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(HERE/"tests"))
from fakes import TinyNet
import contracts
import driver_binding
import runtime_adapter


class OwnedOriginBindingTests(unittest.TestCase):
    def setUp(self):
        self.saved={name:sys.modules.get(name) for name in
            ("dodge_rl","dodge_rl.checkpoints","dodge_rl.identity")}
        for name in self.saved:sys.modules.pop(name,None)
        package=types.ModuleType("dodge_rl")
        package.__path__=[str(HERE/"runtime"/"dodge_rl")]
        sys.modules["dodge_rl"]=package
        self.checkpoints=importlib.import_module("dodge_rl.checkpoints")

    def tearDown(self):
        for name,value in self.saved.items():
            if value is None:sys.modules.pop(name,None)
            else:sys.modules[name]=value

    def test_owned_checkpoint_identity_and_r5_runner_bind_before_callbacks(self):
        self.assertEqual(Path(self.checkpoints.__file__).resolve(),
            HERE/"runtime"/"dodge_rl"/"checkpoints.py")
        self.assertEqual(Path(sys.modules["dodge_rl.identity"].__file__).resolve(),
            HERE/"runtime"/"dodge_rl"/"identity.py")
        model=TinyNet()
        optimizer=torch.optim.Adam(model.parameters(),lr=3e-5,eps=1e-5)
        runner=runtime_adapter.runner_namespace()
        callbacks=driver_binding.build_callbacks(project_root=contracts.ROOT,
            checkpoint_module=self.checkpoints,runner_namespace=runner,parent_state={},
            model=model,optimizer=optimizer)
        self.assertEqual(callbacks["api_names"],{"restore":"restore_learner","capture":"capture_rng"})
        self.assertTrue(callable(callbacks["restore_trusted"]))
        self.assertTrue(callable(callbacks["rng_capture"]))
        self.assertEqual(callbacks["verified_sources"][str(driver_binding.CHECKPOINTS_RELATIVE)]["path"],
            str((HERE/"runtime"/"dodge_rl"/"checkpoints.py").resolve()))
        wrong=types.ModuleType("dodge_rl.checkpoints")
        wrong.__file__=str(contracts.ROOT/
            "learning/runs/v2/progressive1000-opening-maintenance-runtime-parent-20261027-r1/runtime/dodge_rl/checkpoints.py")
        with self.assertRaisesRegex(ValueError,"checkpoint module origin mismatch"):
            driver_binding.build_callbacks(project_root=contracts.ROOT,
                checkpoint_module=wrong,runner_namespace=runner,parent_state={},model=model,optimizer=optimizer)


if __name__=="__main__":unittest.main()
