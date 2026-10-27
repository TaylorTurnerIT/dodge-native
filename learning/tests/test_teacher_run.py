import argparse
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

HAS_MODELS = importlib.util.find_spec("torch") is not None
HAS_NATIVE = importlib.util.find_spec("dodge_learning._native") is not None


@unittest.skipUnless(HAS_MODELS and HAS_NATIVE, "requires model extra and native bridge")
class TeacherCommandTests(unittest.TestCase):
    def test_tiny_training_writes_checkpoint_and_reproducibility_receipts(self):
        from dodge_learning.checkpoints import load_teacher_checkpoint
        from dodge_learning.teacher_run import main

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            with redirect_stdout(io.StringIO()):
                code = main(["train", "--output-dir", str(output), "--frames", "8",
                             "--rollout-steps", "4", "--epochs", "1", "--minibatch-size", "4"])
            self.assertEqual(code, 0)
            receipt = json.loads((output / "run.json").read_text())
            self.assertEqual(receipt["metrics"]["frames_collected"], 8)
            self.assertGreater(receipt["metrics"]["optimizer_steps"], 0)
            self.assertFalse(receipt["student_collection_allowed"])
            loaded = load_teacher_checkpoint(output / "teacher.pt")
            self.assertEqual(loaded.sha256, receipt["checkpoint"]["sha256"])
            self.assertEqual(loaded.metadata["metrics"]["frames_collected"], 8)
            self.assertTrue((output / "source.json").is_file())
            self.assertTrue((output / "seeds.json").is_file())

    def test_invalid_smoke_budget_is_rejected_before_creating_run(self):
        from dodge_learning.teacher_run import run_training

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            arguments = argparse.Namespace(
                frames=8, max_seconds=30, rollout_steps=4, epochs=1,
                minibatch_size=4, learning_rate=3e-4, episode_frames=18_000,
                seed=7, output_dir=output, evaluate_smoke=True,
                smoke_frames=100_000, evaluation_seconds=30,
            )
            with self.assertRaises(ValueError):
                run_training(arguments)
            self.assertFalse(output.exists())
