"""Standard-library fake API tests; no torch, NumPy, checkpoint, or native imports."""
import copy
import json
import unittest
from types import SimpleNamespace
from pathlib import Path

import transition as t


class FakePython:
    def seed(self, value): self.value = value


class FakeNumpy:
    def seed(self, value): self.value = value


class FakeMPS:
    def __init__(self, owner): self.owner = owner
    def manual_seed(self, value): self.owner.mps_seed = value
    def initial_seed(self): return self.owner.mps_seed


class FakeTorch:
    def __init__(self): self.cpu_seed = None; self.mps_seed = None; self.mps = FakeMPS(self)
    def manual_seed(self, value):
        self.cpu_seed = value
        self.mps_seed = value  # pinned behavior: CPU call also seeds MPS
    def initial_seed(self): return self.cpu_seed


class TransitionTests(unittest.TestCase):
    def setUp(self):
        self.seeds = dict(constructor_init_seed=123, python_random_seed=456,
                          numpy_global_seed=0, torch_cpu_global_seed=789,
                          action_sampler_torch_mps_seed=987, env_master_seed=654)
        self.py, self.np, self.torch = FakePython(), FakeNumpy(), FakeTorch()
        self.optimizer = SimpleNamespace(param_groups=[{"lr": 2.2e-5, "params": ["p"],
                                                         "exp_avg": [1, 2], "step": 42}])
        self.moments = copy.deepcopy(self.optimizer.param_groups[0])
        self.restored = []
        self.fingerprints = dict(t.EXPECTED_PARENT)

    def run_transition(self, **kwargs):
        return t.transition(
            backend=kwargs.pop("backend", "mps"), seeds=kwargs.pop("seeds", self.seeds),
            current_fingerprints=lambda: dict(self.fingerprints),
            restore_trusted=lambda: self.restored.append("accepted348"),
            fingerprint=lambda: None, python_api=self.py, numpy_api=self.np,
            torch_api=self.torch, model=object(), optimizer=self.optimizer,
            pair_id="pair-1", arm="A_constant_3e-5", **kwargs)

    def test_order_readback_and_model_adam_invariance(self):
        out = self.run_transition()
        self.assertEqual(self.restored, ["accepted348"])
        self.assertEqual(out["seed_evidence"]["torch_mps_initial_seed"], 987)
        self.assertEqual(self.torch.mps_seed, 987)
        self.assertEqual(self.optimizer.param_groups[0]["lr"], 3e-5)
        group = self.optimizer.param_groups[0]
        for key in ("params", "exp_avg", "step"):
            self.assertEqual(group[key], self.moments[key])

    def test_reverse_order_is_detected(self):
        self.torch.manual_seed(self.seeds["torch_cpu_global_seed"])
        self.torch.mps.manual_seed(self.seeds["action_sampler_torch_mps_seed"])
        self.torch.manual_seed(self.seeds["torch_cpu_global_seed"])
        self.assertNotEqual(self.torch.mps.initial_seed(), self.seeds["action_sampler_torch_mps_seed"])
        with self.assertRaisesRegex(ValueError, "seeding order"):
            self.torch.mps.manual_seed(self.seeds["action_sampler_torch_mps_seed"])
            self.torch.manual_seed(self.seeds["torch_cpu_global_seed"])
            if self.torch.mps.initial_seed() != self.seeds["action_sampler_torch_mps_seed"]:
                raise ValueError("MPS RNG read-back mismatch; check seeding order")

    def test_bad_parent_backend_and_missing_seed_rejected_before_restore(self):
        self.fingerprints["model"] = "wrong"
        with self.assertRaisesRegex(ValueError, "fingerprints"):
            self.run_transition()
        self.assertEqual(self.restored, [])
        self.fingerprints = dict(t.EXPECTED_PARENT)
        with self.assertRaisesRegex(ValueError, "backend"):
            self.run_transition(backend="cpu")
        missing = dict(self.seeds); del missing["constructor_init_seed"]
        with self.assertRaisesRegex(ValueError, "missing explicit"):
            self.run_transition(seeds=missing)
        for value in (-1, 1 << 32):
            bad = dict(self.seeds); bad["constructor_init_seed"] = value
            with self.assertRaisesRegex(ValueError, "constructor_init_seed"):
                t.validate_seeds(bad)

    def test_restore_postcondition_and_reseed_state_guard(self):
        def bad_restore(): self.fingerprints["Adam"] = "wrong"
        with self.assertRaisesRegex(ValueError, "trusted restore"):
            t.transition(backend="mps", seeds=self.seeds,
                         current_fingerprints=lambda: dict(self.fingerprints),
                         restore_trusted=bad_restore,
                         fingerprint=lambda: None, python_api=self.py,
                         numpy_api=self.np, torch_api=self.torch,
                         model=object(), optimizer=self.optimizer,
                         pair_id="pair-1", arm="A_constant_3e-5")

    def test_pairing_and_controller_endpoints(self):
        t.validate_pair({"pair_id": "p", "A": self.seeds, "B": dict(self.seeds)})
        changed = dict(self.seeds); changed["env_master_seed"] += 1
        with self.assertRaisesRegex(ValueError, "identical"):
            t.validate_pair({"pair_id": "p", "A": self.seeds, "B": changed})
        arm = "B_linear_3e-5_to_1e-5_over_60"
        self.assertEqual(t.controller_lr(arm, 397), 3e-5)
        self.assertAlmostEqual(t.controller_lr(arm, 456), 1e-5)
        self.assertEqual(t.controller_lr("A_constant_3e-5", 456), 3e-5)
        self.assertEqual(t.OLD_CONTROLLER_PROVENANCE["origin"], 372)

    def test_exact_proposed_exclusion_union_and_64_counter_rows(self):
        artifact = json.loads((Path(__file__).parent / "seed-vectors-successor-metadata.json").read_text())
        first = artifact["vectors"][0]["env_control"]
        ranges = first["exclusion_union_ranges"]
        t.validate_exclusion_controls(ranges, first["episode_controls"])
        self.assertEqual([row["episode_index"] for row in first["episode_controls"]],
                         artifact["vectors"][0]["env_control"]["episode_indices"])
        bad = list(ranges); bad.pop()
        with self.assertRaisesRegex(ValueError, "exact five-range"):
            t.validate_exclusion_controls(bad, first["episode_controls"])


if __name__ == "__main__":
    unittest.main()
