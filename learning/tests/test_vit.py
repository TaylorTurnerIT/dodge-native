"""Optional compact ViT checks without gameplay or trained-policy claims."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import importlib.util
import inspect
import json
import math
import unittest

from dodge_learning.smoke import run_smoke

HAS_TORCH = importlib.util.find_spec("torch") is not None
if HAS_TORCH:
    import torch

    from dodge_learning.models import distillation_loss
    from dodge_learning.vit import ViTConfig, ViTPolicy
    from dodge_learning.pixels import PixelHistory, PICO8_PALETTE


class ArchitectureBudgetTests(unittest.TestCase):
    def test_smoke_rejects_invalid_architecture_and_patch_size(self) -> None:
        with self.assertRaises(ValueError):
            run_smoke(architecture="unknown")
        for patch_size in (0, 32, 4.0, True):
            with self.subTest(patch_size=patch_size), self.assertRaises(ValueError):
                run_smoke(patch_size=patch_size)


@unittest.skipUnless(HAS_TORCH, "install the optional PyTorch models extra")
class ViTPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.previous_threads = torch.get_num_threads()
        torch.set_num_threads(1)

    @classmethod
    def tearDownClass(cls) -> None:
        torch.set_num_threads(cls.previous_threads)

    def test_default_config_and_patch_tokens_match_spatial_resolution(self) -> None:
        config = ViTConfig()
        self.assertEqual(config, ViTConfig(16, 128, 4, 4, 2.0, 0.0))
        with self.assertRaises(FrozenInstanceError):
            config.depth = 3
        for patch_size, expected_tokens in ((16, 64), (8, 256), (4, 1024)):
            with self.subTest(patch_size=patch_size):
                config = ViTConfig(patch_size=patch_size, embed_dim=32, depth=1)
                model = ViTPolicy(config)
                self.assertIs(model.config, config)
                self.assertEqual(config.num_tokens, expected_tokens)
                self.assertEqual(tuple(model.position_embedding.shape), (1, expected_tokens, 32))
                tokens = model.patch_embed(torch.zeros(1, 4, 128, 128)).flatten(2)
                self.assertEqual(tuple(tokens.shape), (1, 32, expected_tokens))
                self.assertEqual(tuple(model(torch.zeros(1, 4, 128, 128)).shape), (1, 9))

    def test_only_image_input_drives_action_logits_and_gradients(self) -> None:
        model = ViTPolicy(ViTConfig(embed_dim=32, depth=1))
        self.assertEqual(tuple(inspect.signature(model.forward).parameters), ("images",))
        images = torch.rand(2, 4, 128, 128)
        teacher_logits = torch.randn(2, 9, requires_grad=True)
        logits = model(images)
        self.assertEqual(tuple(logits.shape), (2, 9))
        self.assertTrue(bool(torch.isfinite(logits).all()))
        loss = distillation_loss(logits, teacher_logits)
        loss.backward()
        self.assertIsNone(teacher_logits.grad)
        for parameter in model.parameters():
            self.assertIsNotNone(parameter.grad)
            self.assertTrue(bool(torch.isfinite(parameter.grad).all()))
        self.assertGreater(float(model.position_embedding.grad.abs().sum()), 0)
        self.assertGreater(float(model.patch_embed.weight.grad.abs().sum()), 0)
        with self.assertRaises(TypeError):
            model(images, train_only_state={"seed": 42})
        with self.assertRaises(TypeError):
            model({"pixels": images, "info": {"seed": 42}})

    def test_distillation_attention_pools_the_policy_latent(self) -> None:
        model = ViTPolicy(ViTConfig(embed_dim=32, depth=1)).eval()
        images = torch.rand(2, 4, 128, 128)
        result = model.distillation_outputs(images)
        self.assertEqual(tuple(result.latent.shape), (2, 32))
        self.assertEqual(tuple(result.attention.shape), (2, 64))
        torch.testing.assert_close(result.attention.sum(dim=-1), torch.ones(2))
        torch.testing.assert_close(model(images), result.logits)
        torch.testing.assert_close(model.head(result.latent), result.logits)
        result.attention.retain_grad()
        result.logits.square().mean().backward()
        self.assertGreater(float(result.attention.grad.abs().sum()), 0)
        self.assertGreater(float(model.attention_score.weight.grad.abs().sum()), 0)

    def test_gray_history_uses_palette_luminance_and_preserves_rgb(self) -> None:
        history = PixelHistory()
        frame = bytes(range(16)) * 1024
        history.reset(frame, frame_id=13)
        rgb_before = history.rgb_chw()
        gray = history.gray_chw()
        self.assertEqual(len(gray), 4 * 128 * 128)
        for index, (red, green, blue) in enumerate(PICO8_PALETTE):
            self.assertAlmostEqual(
                gray[index], (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255, places=6
            )
        self.assertEqual(history.rgb_chw(), rgb_before)
        self.assertEqual(gray[:16384], gray[-16384:])

    def test_learned_positions_make_patch_location_matter(self) -> None:
        generator = torch.Generator(device="cpu").manual_seed(1234)
        model = ViTPolicy(ViTConfig(embed_dim=32, depth=1)).eval()
        first = torch.zeros(1, 4, 128, 128)
        second = first.clone()
        first[:, :, :16, :16] = 1.0
        second[:, :, :16, 16:32] = 1.0
        with torch.no_grad():
            model.position_embedding.zero_()
            torch.testing.assert_close(model(first), model(second), atol=1e-6, rtol=1e-5)
            model.position_embedding.copy_(
                torch.randn(model.position_embedding.shape, generator=generator) * 0.2
            )
            location_difference = (model(first) - model(second)).abs().max()
        self.assertGreater(float(location_difference), 1e-6)

    def test_policy_rejects_nonimage_shapes_and_integer_pixels(self) -> None:
        model = ViTPolicy(ViTConfig(embed_dim=32, depth=1))
        for shape in ((1, 3, 128, 128), (1, 4, 64, 64), (4, 128, 128), (0, 4, 128, 128), (1, 12, 128, 128)):
            with self.subTest(shape=shape), self.assertRaises(ValueError):
                model(torch.zeros(shape))
        with self.assertRaises(TypeError):
            model(torch.zeros(1, 4, 128, 128, dtype=torch.uint8))
        for invalid in (math.nan, math.inf, -0.1, 1.1):
            images = torch.zeros(1, 4, 128, 128)
            images[0, 0, 0, 0] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                model(images)

    def test_config_rejects_invalid_or_unbounded_architectures(self) -> None:
        invalid = (
            {"patch_size": 32},
            {"patch_size": 8.0},
            {"embed_dim": 0},
            {"embed_dim": 1024},
            {"embed_dim": True},
            {"embed_dim": 30, "num_heads": 4},
            {"depth": 0},
            {"depth": 13},
            {"num_heads": 0},
            {"num_heads": 32},
            {"mlp_ratio": 0},
            {"mlp_ratio": math.inf},
            {"mlp_ratio": 10**1000},
            {"dropout": 10**1000},
            {"mlp_ratio": math.nan},
            {"mlp_ratio": True},
            {"dropout": -0.1},
            {"dropout": 1.0},
            {"dropout": math.nan},
        )
        for parameters in invalid:
            with self.subTest(parameters=parameters), self.assertRaises(ValueError):
                ViTConfig(**parameters)
        with self.assertRaises(TypeError):
            ViTPolicy(config={"patch_size": 8})

    def test_smoke_reports_vit_primary_and_cnn_comparison(self) -> None:
        primary = run_smoke("cpu", steps=1, batch_size=1)
        self.assertEqual(primary["architecture"], "vit")
        self.assertEqual(primary["config"]["patch_size"], 16)
        self.assertEqual(primary["config"]["num_tokens"], 64)
        comparison = run_smoke("cpu", steps=1, batch_size=1, architecture="cnn")
        self.assertEqual(comparison["architecture"], "cnn")
        self.assertNotIn("patch_size", comparison["config"])
        for result in (primary, comparison):
            self.assertFalse(result["trained_policy"])
            self.assertFalse(result["game_evaluation"])
            self.assertTrue(result["parameters_finite"])
            self.assertGreater(result["max_abs_gradient"], 0)
            json.dumps(result, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
