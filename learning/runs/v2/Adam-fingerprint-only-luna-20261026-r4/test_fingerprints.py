"""CPU-only content fingerprint tests with a tiny real Torch Adam optimizer."""
import hashlib
import sys
import unittest
from pathlib import Path

import torch
from torch import nn

import fingerprints as f

ROOT = Path(__file__).resolve().parents[4]
TRUSTED_RUNNER = ROOT / "learning/runs/v2/D2-retained324-linear-integrated-luna-20261026-r4/runner.py"


def extract_trusted_fingerprint():
    source = TRUSTED_RUNNER.read_text()
    start = source.index("def fingerprint(value):")
    end = source.index("\n\ndef mismatch_paths", start)
    block = source[start:end]
    namespace = {"hashlib": hashlib, "Mapping": __import__("collections.abc", fromlist=["Mapping"]).Mapping}
    exec(compile(block, str(TRUSTED_RUNNER), "exec"), namespace)
    return namespace["fingerprint"]


class FingerprintTests(unittest.TestCase):
    def setUp(self):
        self.model = nn.Linear(3, 2, device="cpu")
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=1e-3)
        # One permitted CPU toy step creates real tensor-valued Adam moments.
        loss = self.model(torch.ones(2, 3, device="cpu")).square().mean()
        loss.backward()
        self.optimizer.step()

    def test_full_adam_digest_changes_with_learning_rate(self):
        before = f.fingerprint(self.optimizer.state_dict())
        self.optimizer.param_groups[0]["lr"] *= 2
        after = f.fingerprint(self.optimizer.state_dict())
        self.assertNotEqual(before, after)

    def test_normalized_adam_digest_ignores_only_learning_rate(self):
        before = f.optimizer_content_fingerprint(self.optimizer.state_dict())
        self.optimizer.param_groups[0]["lr"] *= 2
        self.assertEqual(before, f.optimizer_content_fingerprint(self.optimizer.state_dict()))
        self.optimizer.param_groups[0]["weight_decay"] = 0.125
        self.assertNotEqual(before, f.optimizer_content_fingerprint(self.optimizer.state_dict()))

    def test_in_place_exp_avg_mutation_changes_normalized_digest(self):
        state = self.optimizer.state_dict()
        old_shallow_copy = self.optimizer.state.copy()
        before = f.optimizer_content_fingerprint(state)
        moment = next(iter(self.optimizer.state.values()))["exp_avg"]
        moment.add_(1)
        self.assertIs(old_shallow_copy[next(iter(old_shallow_copy))]["exp_avg"], moment)
        self.assertNotEqual(before, f.optimizer_content_fingerprint(self.optimizer.state_dict()))

    def test_model_tensor_mutation_changes_digest(self):
        before = f.fingerprint(self.model.state_dict())
        with torch.no_grad():
            self.model.weight[0, 0].add_(1)
        self.assertNotEqual(before, f.fingerprint(self.model.state_dict()))

    def test_matches_exact_extracted_trusted_function_on_cpu_values(self):
        trusted = extract_trusted_fingerprint()
        values = {
            "model": self.model.state_dict(),
            "optimizer": self.optimizer.state_dict(),
            "nested": [torch.tensor([1, 2], dtype=torch.int64), ("x", 3.5)],
        }
        self.assertEqual(f.fingerprint(values), trusted(values))


if __name__ == "__main__":
    unittest.main(verbosity=2)
