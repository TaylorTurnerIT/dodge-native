"""Check the three loss bridges, geometry, and frozen-teacher boundary."""

from __future__ import annotations

import importlib.util
import math
import unittest

HAS_TORCH = importlib.util.find_spec("torch") is not None
if HAS_TORCH:
    import torch

    from dodge_learning.distillation import (
        DistillationConfig, distillation_losses, teacher_attention_to_grid,
    )
    from dodge_learning.vit import ViTConfig, ViTPolicy


@unittest.skipUnless(HAS_TORCH, "install the optional PyTorch models extra")
class SpatialTargetTests(unittest.TestCase):
    def test_area_mapping_uses_row_major_grid_and_excludes_hidden_mass(self) -> None:
        attention = torch.tensor([[0.2, 0.4, 0.3, 0.1]], requires_grad=True)
        bounds = torch.tensor([[[32., 16., 48., 32.], [0., 0., 32., 16.],
                                [200., 200., 220., 220.], [96., 96., 112., 112.]]])
        target, valid = teacher_attention_to_grid(
            attention, bounds, torch.tensor([[True, True, True, False]]),
            torch.ones(1, 4, dtype=torch.bool), torch.tensor([[0., 0., 128., 128.]]), 8,
        )
        expected = torch.zeros(1, 64)
        expected[0, 0] = 1 / 3
        expected[0, 1] = 1 / 3
        expected[0, 10] = 1 / 3
        torch.testing.assert_close(target, expected)
        self.assertEqual(valid.tolist(), [True])
        self.assertFalse(target.requires_grad)

    def test_capture_clipping_preserves_game_image_coordinates(self) -> None:
        target, valid = teacher_attention_to_grid(
            torch.ones(1, 1), torch.tensor([[[0., 0., 32., 16.]]]),
            torch.ones(1, 1, dtype=torch.bool), torch.ones(1, 1, dtype=torch.bool),
            torch.tensor([[8., 0., 128., 128.]]), 8,
        )
        self.assertTrue(valid.item())
        self.assertAlmostEqual(target[0, 0].item(), 1 / 3, places=6)
        self.assertAlmostEqual(target[0, 1].item(), 2 / 3, places=6)
        self.assertEqual(target[0, 2:].count_nonzero().item(), 0)

    def test_point_and_line_footprints_and_right_boundary(self) -> None:
        target, valid = teacher_attention_to_grid(
            torch.ones(3, 1),
            torch.tensor([[[127., 127., 127., 127.]], [[0., 16., 32., 16.]],
                          [[128., 0., 128., 0.]]]),
            torch.ones(3, 1, dtype=torch.bool), torch.ones(3, 1, dtype=torch.bool),
            torch.tensor([[0., 0., 128., 128.]]).expand(3, -1), 8,
        )
        self.assertEqual(valid.tolist(), [True, True, False])
        self.assertEqual(target[0, -1].item(), 1)
        self.assertEqual(target[1, 8].item(), 0.5)
        self.assertEqual(target[1, 9].item(), 0.5)
        self.assertEqual(target[2].count_nonzero().item(), 0)

    def test_padding_and_no_visible_hazards_produce_no_targets(self) -> None:
        target, valid = teacher_attention_to_grid(
            torch.tensor([[1., math.nan], [1., math.nan]]),
            torch.tensor([[[0., 0., 16., 16.], [math.nan] * 4],
                          [[200., 0., 220., 16.], [math.nan] * 4]]),
            torch.tensor([[False, True], [True, True]]),
            torch.tensor([[True, False], [True, False]]),
            torch.tensor([[0., 0., 128., 128.]]).expand(2, -1), 8,
        )
        self.assertEqual(valid.tolist(), [False, False])
        self.assertTrue(bool(torch.isfinite(target).all()))
        self.assertEqual(target.count_nonzero().item(), 0)

    def test_invalid_active_geometry_or_attention_is_rejected(self) -> None:
        args = [torch.ones(1, 1), torch.tensor([[[0., 0., 16., 16.]]]),
                torch.ones(1, 1, dtype=torch.bool), torch.ones(1, 1, dtype=torch.bool),
                torch.tensor([[0., 0., 128., 128.]])]
        for index, invalid in (
            (0, torch.tensor([[-1.]])), (0, torch.tensor([[math.nan]])),
            (1, torch.tensor([[[0., 0., -1., 16.]]])),
            (1, torch.tensor([[[0., 0., math.inf, 16.]]])),
            (4, torch.tensor([[128., 0., 0., 128.]])),
        ):
            actual = list(args)
            actual[index] = invalid
            with self.subTest(index=index, invalid=invalid), self.assertRaises(ValueError):
                teacher_attention_to_grid(*actual, 8)
        for grid in (0, True, 8.0, 129):
            with self.subTest(grid=grid), self.assertRaises(ValueError):
                teacher_attention_to_grid(*args, grid)


@unittest.skipUnless(HAS_TORCH, "install the optional PyTorch models extra")
class LossBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.previous_threads = torch.get_num_threads()
        torch.set_num_threads(1)

    @classmethod
    def tearDownClass(cls) -> None:
        torch.set_num_threads(cls.previous_threads)

    @staticmethod
    def teacher():
        return (
            torch.randn(2, 9, requires_grad=True), torch.randn(2, 32, requires_grad=True),
            torch.tensor([[0.2, 0.8], [0.4, 0.6]], requires_grad=True),
            torch.tensor([[[64., 64., 68., 68.], [0., 0., 16., 16.]],
                          [[64., 64., 68., 68.], [112., 112., 128., 128.]]], requires_grad=True),
            torch.tensor([[False, True], [False, True]]), torch.ones(2, 2, dtype=torch.bool),
            torch.tensor([[0., 0., 128., 128.]]).expand(2, -1),
        )

    def test_all_bridges_backpropagate_only_into_student(self) -> None:
        model = ViTPolicy(ViTConfig(embed_dim=32, depth=1))
        output = model.distillation_outputs(torch.rand(2, 4, 128, 128))
        teacher = self.teacher()
        losses = distillation_losses(output.logits, output.latent, output.attention, *teacher, grid_size=8)
        self.assertEqual(losses.attention_rows, 2)
        for value in (losses.total, losses.action, losses.latent, losses.attention):
            self.assertTrue(bool(torch.isfinite(value)))
        torch.testing.assert_close(losses.total, losses.action + losses.latent + losses.attention)
        losses.total.backward()
        for value in teacher:
            if isinstance(value, torch.Tensor) and value.requires_grad:
                self.assertIsNone(value.grad)
        for parameter in model.parameters():
            self.assertIsNotNone(parameter.grad)
            self.assertTrue(bool(torch.isfinite(parameter.grad).all()))
        self.assertGreater(model.patch_embed.weight.grad.abs().sum().item(), 0)
        self.assertGreater(model.attention_score.weight.grad.abs().sum().item(), 0)
        self.assertGreater(model.head.weight.grad.abs().sum().item(), 0)

    def test_each_bridge_has_student_gradient(self) -> None:
        for term in ("action", "latent", "attention"):
            with self.subTest(term=term):
                student_logits = torch.randn(2, 9, requires_grad=True)
                student_latent = torch.randn(2, 32, requires_grad=True)
                raw_attention = torch.randn(2, 64, requires_grad=True)
                losses = distillation_losses(
                    student_logits, student_latent, raw_attention.softmax(-1), *self.teacher(), grid_size=8
                )
                getattr(losses, term).backward()
                target = {"action": student_logits, "latent": student_latent, "attention": raw_attention}[term]
                self.assertIsNotNone(target.grad)
                self.assertGreater(target.grad.abs().sum().item(), 0)

    def test_unmapped_attention_is_differentiable_zero(self) -> None:
        student = torch.randn(2, 64, requires_grad=True)
        teacher = list(self.teacher())
        teacher[4] = torch.zeros(2, 2, dtype=torch.bool)
        losses = distillation_losses(
            torch.randn(2, 9, requires_grad=True), torch.randn(2, 32, requires_grad=True),
            student.softmax(-1), *teacher, grid_size=8,
        )
        self.assertEqual(losses.attention_rows, 0)
        self.assertEqual(losses.attention.item(), 0)
        losses.attention.backward()
        torch.testing.assert_close(student.grad, torch.zeros_like(student))

    def test_matching_targets_yield_zero_losses(self) -> None:
        logits = torch.randn(2, 9)
        latent = torch.randn(2, 32)
        teacher = self.teacher()
        target, _ = teacher_attention_to_grid(*teacher[2:], 8)
        losses = distillation_losses(logits, latent, target, logits, latent, *teacher[2:], grid_size=8)
        self.assertLess(abs(losses.action.item()), 1e-6)
        self.assertEqual(losses.latent.item(), 0)
        self.assertLess(abs(losses.attention.item()), 1e-6)

    def test_config_and_malformed_losses_are_rejected(self) -> None:
        for invalid in (
            {"action_weight": -1}, {"latent_weight": math.nan}, {"attention_weight": True},
            {"action_weight": 0, "latent_weight": 0, "attention_weight": 0},
            {"temperature": 0}, {"temperature": math.inf}, {"temperature": 10**1000},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                DistillationConfig(**invalid)
        common = (torch.randn(2, 9), torch.randn(2, 32))
        for attention in (torch.ones(2, 64), torch.ones(2, 63) / 63, torch.full((2, 64), math.nan)):
            with self.subTest(shape=attention.shape), self.assertRaises(ValueError):
                distillation_losses(*common, attention, *self.teacher(), grid_size=8)


if __name__ == "__main__":
    unittest.main()
