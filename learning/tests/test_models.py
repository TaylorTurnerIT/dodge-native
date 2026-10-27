"""Optional model tests; baseline-only installations do not require PyTorch."""

from __future__ import annotations

import importlib.util
import inspect
import json
import math
import unittest
from unittest import mock

from dodge_learning.smoke import run_smoke

HAS_TORCH = importlib.util.find_spec("torch") is not None
if HAS_TORCH:
    import torch

    from dodge_learning.models import VisionPolicy, distillation_loss
    from dodge_learning.smoke import resolve_device


class SmokeBudgetTests(unittest.TestCase):
    def test_budgets_reject_unbounded_work_before_importing_torch(self) -> None:
        for steps in (0, -1, 11, True, 1.5):
            with self.subTest(steps=steps), self.assertRaises(ValueError):
                run_smoke(steps=steps)
        for batch_size in (0, -1, 65, True, 1.5):
            with self.subTest(batch_size=batch_size), self.assertRaises(ValueError):
                run_smoke(batch_size=batch_size)


@unittest.skipUnless(HAS_TORCH, "install the optional PyTorch model extra")
class VisionModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.previous_threads = torch.get_num_threads()
        torch.set_num_threads(1)

    @classmethod
    def tearDownClass(cls) -> None:
        torch.set_num_threads(cls.previous_threads)

    def test_policy_accepts_only_images_and_has_trainable_output(self) -> None:
        model = VisionPolicy()
        signature = inspect.signature(model.forward)
        self.assertEqual(tuple(signature.parameters), ("images",))
        images = torch.rand(2, 12, 128, 128)
        logits = model(images)
        self.assertEqual(tuple(logits.shape), (2, 9))
        self.assertTrue(bool(torch.isfinite(logits).all()))
        loss = distillation_loss(logits, torch.randn(2, 9))
        loss.backward()
        self.assertTrue(any(bool(p.grad.abs().sum() > 0) for p in model.parameters()))
        with self.assertRaises(TypeError):
            model(images, train_only_state={"seed": 42})

    def test_policy_rejects_wrong_history_resolution_or_dtype(self) -> None:
        model = VisionPolicy()
        for shape in ((1, 3, 128, 128), (1, 12, 64, 64), (12, 128, 128), (0, 12, 128, 128)):
            with self.subTest(shape=shape), self.assertRaises(ValueError):
                model(torch.zeros(shape))
        with self.assertRaises(TypeError):
            model(torch.zeros(1, 12, 128, 128, dtype=torch.uint8))

    def test_distillation_matches_forward_kl_and_stops_teacher_gradients(self) -> None:
        student = torch.randn(3, 9, requires_grad=True)
        teacher = torch.randn(3, 9, requires_grad=True)
        temperature = 2.0
        loss = distillation_loss(student, teacher, temperature)
        target = torch.softmax(teacher.detach() / temperature, dim=-1)
        expected = (
            target * (target.log() - torch.log_softmax(student / temperature, dim=-1))
        ).sum(dim=-1).mean() * temperature**2
        torch.testing.assert_close(loss, expected)
        loss.backward()
        self.assertIsNone(teacher.grad)
        self.assertIsNotNone(student.grad)
        self.assertTrue(bool(torch.isfinite(student.grad).all()))
        self.assertGreater(float(student.grad.abs().sum()), 0)

    def test_identical_distributions_have_zero_loss(self) -> None:
        logits = torch.randn(2, 9)
        loss = distillation_loss(logits, logits + 7.0)
        self.assertAlmostEqual(float(loss), 0, places=6)

    def test_distillation_validates_temperature_logits_and_batch(self) -> None:
        logits = torch.zeros(2, 9)
        for temperature in (0, -1, math.nan, math.inf, True, "1"):
            with self.subTest(temperature=temperature), self.assertRaises(ValueError):
                distillation_loss(logits, logits, temperature)
        for teacher in (torch.zeros(1, 9), torch.zeros(2, 8), torch.zeros(0, 9)):
            with self.subTest(shape=tuple(teacher.shape)), self.assertRaises(ValueError):
                distillation_loss(logits, teacher)
        with self.assertRaises(ValueError):
            distillation_loss(logits, torch.full((2, 9), math.nan))
        with self.assertRaises(ValueError):
            distillation_loss(logits, logits.double())
        with self.assertRaises(TypeError):
            distillation_loss(logits.long(), logits.long())

    def test_explicit_mps_request_never_silently_uses_cpu(self) -> None:
        with mock.patch("torch.backends.mps.is_available", return_value=False):
            with self.assertRaises(RuntimeError):
                resolve_device("mps")
            self.assertEqual(resolve_device("auto").type, "cpu")
        with (
            mock.patch("torch.backends.mps.is_built", return_value=True),
            mock.patch("torch.backends.mps.is_available", return_value=True),
            mock.patch.dict("os.environ", {"PYTORCH_ENABLE_MPS_FALLBACK": "1"}),
            self.assertRaises(RuntimeError),
        ):
            resolve_device("mps")

    def test_cpu_smoke_reports_diagnostic_without_gameplay_claims(self) -> None:
        result = run_smoke("cpu", steps=1, batch_size=1)
        self.assertFalse(result["trained_policy"])
        self.assertFalse(result["game_evaluation"])
        self.assertEqual(result["device"], "cpu")
        self.assertTrue(result["parameters_finite"])
        self.assertGreater(result["max_abs_gradient"], 0)
        self.assertTrue(all(math.isfinite(value) for value in result["losses"]))
        json.dumps(result, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
