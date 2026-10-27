from pathlib import Path
import unittest

ROOT = Path(__file__).parent


class SourceContractTests(unittest.TestCase):
    def test_adapter_is_inert_and_narrow(self):
        source = (ROOT / "adapter.py").read_text()
        forbidden = ("torch", "dodge_rl", "gymnasium", "VecDodgeEnv", "pickle.load", "torch.load", "open(", "Path(")
        for token in forbidden:
            self.assertNotIn(token, source)
        self.assertIn("def analyze(registration: dict, selection: dict, terminal_audit: dict, winner_result: dict, incumbent_result: dict)", source)
        self.assertIn("np.random.PCG64(BOOTSTRAP_SEED)", source)
        self.assertIn("np.quantile(means, 0.05, method=\"linear\")", source)
        self.assertIn("difference[indices].mean(axis=1)", source)
        self.assertIn("CHUNK_RESAMPLES = 128", source)


if __name__ == "__main__":
    unittest.main()
