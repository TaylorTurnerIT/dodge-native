"""Feature-budget, variable-entity, and gradient checks for the state teacher."""

from __future__ import annotations

import copy
import importlib.util
import unittest
from dataclasses import FrozenInstanceError, asdict, replace

HAS_MODELS = (
    importlib.util.find_spec("torch") is not None
    and importlib.util.find_spec("numpy") is not None
)
HAS_NATIVE = importlib.util.find_spec("dodge_learning._native") is not None
if HAS_MODELS:
    import numpy as np
    import torch

    from dodge_learning.teacher import (
        MAX_ENTITIES_PER_TYPE,
        REQUIRED_NATIVE_FEATURE_SCHEMA_VERSION,
        TEACHER_SCHEMA_VERSION,
        EncodedState,
        StateActorCritic,
        TeacherConfig,
        batch_states,
        encode_state,
    )


def sample_state() -> dict:
    return {
        "player": {"x": 64.0, "y": -16.0, "vx": 2.0, "vy": -4.0, "size": 4.0},
        "globals": {"speed": 2.0, "freeze_rate": 0.25, "freeze_active": True},
        "enemies": [
            {"x": 256.0, "y": -128.0, "vx": 4.0, "vy": -2.0, "size": 8.0, "kind": -1},
            {"x": 32.0, "y": 16.0, "vx": -1.0, "vy": 0.0, "size": 2.0, "kind": 4},
        ],
        "rectangles": [
            {"x": -128.0, "y": 64.0, "width": 256.0, "height": 32.0, "dx": 2.0, "dy": -4.0, "solid": False},
        ],
        "warnings": [{"x0": -128.0, "y0": 64.0, "x1": 256.0, "y1": 32.0}],
    }


@unittest.skipUnless(HAS_MODELS, "install the optional PyTorch model extra")
class TeacherFeatureTests(unittest.TestCase):
    def test_schema_and_normalization_preserve_signed_coordinates(self) -> None:
        state = encode_state(sample_state())
        self.assertEqual(TEACHER_SCHEMA_VERSION, 1)
        self.assertEqual(REQUIRED_NATIVE_FEATURE_SCHEMA_VERSION, 2)
        np.testing.assert_array_equal(state.globals, [0.5, -0.125, 0.5, -1, 0.5, 0.5, 0.25, 1])
        np.testing.assert_array_equal(state.enemies[0], [2, -1, 1, -0.5, 1, 1, 0, 0, 0, 0, 0])
        np.testing.assert_array_equal(state.enemies[1, 5:], [0, 0, 0, 0, 0, 1])
        np.testing.assert_array_equal(state.rectangles[0], [-1, 0.5, 2, 0.25, 0.5, -1, 0])
        np.testing.assert_array_equal(state.warnings[0], [-1, 0.5, 2, 0.25])
        for array in (state.globals, state.enemies, state.rectangles, state.warnings):
            self.assertEqual(array.dtype, np.float32)

    def test_encoded_arrays_are_copied_and_cannot_be_made_writable(self) -> None:
        raw = sample_state()
        encoded = encode_state(raw)
        raw["player"]["x"] = -999
        self.assertEqual(encoded.globals[0], 0.5)
        with self.assertRaises(FrozenInstanceError):
            encoded.globals = np.zeros(8)
        for array in (encoded.globals, encoded.enemies, encoded.rectangles, encoded.warnings):
            with self.assertRaises(ValueError):
                array.setflags(write=True)
        source = np.arange(8, dtype=np.float32)
        direct = EncodedState(source, np.empty((0, 11)), np.empty((0, 7)), np.empty((0, 4)))
        source[:] = -1
        np.testing.assert_array_equal(direct.globals, np.arange(8))

    def test_rejects_unknown_or_missing_fields_at_every_level(self) -> None:
        for field, record in (
            ("seed", lambda state: state),
            ("rng", lambda state: state["player"]),
            ("future_targets", lambda state: state["globals"]),
            ("future_x", lambda state: state["enemies"][0]),
            ("targets", lambda state: state["rectangles"][0]),
            ("seed", lambda state: state["warnings"][0]),
        ):
            state = sample_state()
            record(state)[field] = 42
            with self.subTest(field=field), self.assertRaises(ValueError):
                encode_state(state)
        state = sample_state()
        del state["player"]["vx"]
        with self.assertRaises(ValueError):
            encode_state(state)
        with self.assertRaises(ValueError):
            encode_state({"train_only_state": sample_state(), "info": {"seed": 42}})

    def test_numeric_fields_reject_booleans_nonfinite_and_float32_overflow(self) -> None:
        for row_name, field in (("player", "x"), ("globals", "speed"), ("enemies", "vx"), ("rectangles", "width"), ("warnings", "x0")):
            for value in (True, np.bool_(False), float("nan"), float("inf"), -float("inf"), "1", 10**1000, 1e100):
                state = sample_state()
                row = state[row_name]
                if isinstance(row, list):
                    row = row[0]
                row[field] = value
                with self.subTest(row=row_name, field=field, value=value), self.assertRaises(ValueError):
                    encode_state(state)

    def test_flags_require_booleans_and_enemy_kind_requires_known_integer(self) -> None:
        for value in (0, 1, "true", None, float("nan")):
            state = sample_state()
            state["globals"]["freeze_active"] = value
            with self.subTest(flag=value), self.assertRaises(ValueError):
                encode_state(state)
            state = sample_state()
            state["rectangles"][0]["solid"] = value
            with self.assertRaises(ValueError):
                encode_state(state)
        for kind in (-2, 5, True, 1.0, "1", float("nan")):
            state = sample_state()
            state["enemies"][0]["kind"] = kind
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                encode_state(state)
        for index, kind in enumerate((-1, 0, 1, 2, 3, 4)):
            state = sample_state()
            state["enemies"][0]["kind"] = kind
            expected = np.zeros(6)
            expected[index] = 1
            np.testing.assert_array_equal(encode_state(state).enemies[0, 5:], expected)

    def test_capacity_fails_instead_of_truncating_each_entity_type(self) -> None:
        for name in ("enemies", "rectangles", "warnings"):
            state = sample_state()
            state[name] = [state[name][0]] * (MAX_ENTITIES_PER_TYPE + 1)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "capacity"):
                encode_state(state)
        state = sample_state()
        state["warnings"] = [state["warnings"][0]] * MAX_ENTITIES_PER_TYPE
        encoded = encode_state(state)
        self.assertEqual(encoded.warnings.shape, (MAX_ENTITIES_PER_TYPE, 4))

    def test_empty_entities_and_variable_length_batch_keep_all_rows(self) -> None:
        raw = sample_state()
        empty = copy.deepcopy(raw)
        for name in ("enemies", "rectangles", "warnings"):
            empty[name] = []
        empty_encoded = encode_state(empty)
        self.assertEqual(empty_encoded.enemies.shape, (0, 11))
        self.assertEqual(empty_encoded.rectangles.shape, (0, 7))
        self.assertEqual(empty_encoded.warnings.shape, (0, 4))
        solo = batch_states([empty_encoded])
        self.assertEqual(tuple(solo.enemies.shape), (1, 1, 11))
        self.assertFalse(bool(solo.enemy_mask.any()))
        batch = batch_states([empty_encoded, encode_state(raw)])
        self.assertEqual(tuple(batch.enemies.shape), (2, 2, 11))
        self.assertEqual(batch.enemy_mask.tolist(), [[False, False], [True, True]])
        self.assertEqual(batch.rectangle_mask.tolist(), [[False], [True]])
        self.assertEqual(batch.warning_mask.tolist(), [[False], [True]])
        np.testing.assert_array_equal(batch.enemies[1].numpy(), encode_state(raw).enemies)
        with self.assertRaises(ValueError):
            batch_states([])
        with self.assertRaises(TypeError):
            batch_states([raw])

    def test_direct_encoded_state_rejects_bad_shapes_and_nonfinite(self) -> None:
        valid = encode_state(sample_state())
        for change in (
            {"globals": np.zeros(9)},
            {"enemies": np.zeros((2, 10))},
            {"warnings": np.full((1, 4), np.nan)},
            {"rectangles": np.ones((1, 7), dtype=np.bool_)},
        ):
            with self.subTest(change=tuple(change)), self.assertRaises(ValueError):
                replace(valid, **change)


@unittest.skipUnless(HAS_MODELS, "install the optional PyTorch model extra")
class TeacherModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.previous_threads = torch.get_num_threads()
        torch.set_num_threads(1)

    @classmethod
    def tearDownClass(cls) -> None:
        torch.set_num_threads(cls.previous_threads)

    def test_config_is_bounded_frozen_and_serializable(self) -> None:
        config = TeacherConfig()
        self.assertEqual(asdict(config), {"hidden_dim": 128, "entity_dim": 32})
        self.assertEqual(TeacherConfig(**asdict(config)), config)
        with self.assertRaises(FrozenInstanceError):
            config.hidden_dim = 64
        for name, maximum in (("hidden_dim", 1024), ("entity_dim", 256)):
            for value in (0, -1, maximum + 1, True, 1.5, "16"):
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    TeacherConfig(**{name: value})
        with self.assertRaises(TypeError):
            StateActorCritic({"hidden_dim": 128})

    def test_policy_and_value_have_finite_gradients(self) -> None:
        torch.manual_seed(31)
        model = StateActorCritic(TeacherConfig(hidden_dim=32, entity_dim=16))
        self.assertEqual(model.config, TeacherConfig(32, 16))
        batch = batch_states([encode_state(sample_state()), encode_state(sample_state())])
        logits, values = model(batch)
        self.assertEqual(tuple(logits.shape), (2, 9))
        self.assertEqual(tuple(values.shape), (2,))
        self.assertTrue(bool(torch.isfinite(logits).all()))
        self.assertTrue(bool(torch.isfinite(values).all()))
        loss = -torch.log_softmax(logits, dim=-1)[:, 0].mean() + (values - 2).square().mean()
        loss.backward()
        for parameter in model.parameters():
            self.assertIsNotNone(parameter.grad)
            self.assertTrue(bool(torch.isfinite(parameter.grad).all()))
        for part in (model.actor, model.value, model.enemy_encoder, model.rectangle_encoder, model.warning_encoder):
            self.assertTrue(any(bool(parameter.grad.abs().sum() > 0) for parameter in part.parameters()))

    def test_entity_order_does_not_change_policy_or_value(self) -> None:
        state = sample_state()
        state["rectangles"] *= 2
        state["rectangles"][1] = dict(state["rectangles"][1], x=17.0)
        state["warnings"] *= 2
        state["warnings"][1] = dict(state["warnings"][1], x0=17.0)
        reversed_state = copy.deepcopy(state)
        for name in ("enemies", "rectangles", "warnings"):
            reversed_state[name].reverse()
        model = StateActorCritic().eval()
        logits, values = model(batch_states([encode_state(state), encode_state(reversed_state)]))
        torch.testing.assert_close(logits[0], logits[1], rtol=1e-5, atol=1e-6)
        torch.testing.assert_close(values[0], values[1], rtol=1e-5, atol=1e-6)

    def test_batch_padding_and_empty_sets_do_not_change_outputs(self) -> None:
        empty = sample_state()
        for name in ("enemies", "rectangles", "warnings"):
            empty[name] = []
        empty_encoded = encode_state(empty)
        sparse = sample_state()
        sparse["enemies"] = sparse["enemies"][:1]
        sparse_encoded = encode_state(sparse)
        dense = sample_state()
        for name in ("enemies", "rectangles", "warnings"):
            dense[name] *= 3
        model = StateActorCritic().eval()
        expected = model(batch_states([empty_encoded, sparse_encoded]))
        mixed = batch_states([empty_encoded, sparse_encoded, encode_state(dense)])
        actual = model(mixed)
        for single, padded in zip(expected, actual):
            torch.testing.assert_close(single, padded[:2], rtol=1e-5, atol=1e-6)
        changed = replace(
            mixed,
            enemies=mixed.enemies.masked_fill(~mixed.enemy_mask.unsqueeze(-1), float("nan")),
            rectangles=mixed.rectangles.masked_fill(~mixed.rectangle_mask.unsqueeze(-1), 1e30),
            warnings=mixed.warnings.masked_fill(~mixed.warning_mask.unsqueeze(-1), -1e30),
        )
        for before, after in zip(actual, model(changed)):
            torch.testing.assert_close(before, after)
        sum(output.sum() for output in expected).backward()
        self.assertTrue(all(parameter.grad is None or bool(torch.isfinite(parameter.grad).all()) for parameter in model.parameters()))

    @unittest.skipUnless(HAS_NATIVE, "build the optional native bridge")
    def test_real_native_projection_encodes_and_backpropagates(self) -> None:
        from dodge_learning import NativeEnvironment

        env = NativeEnvironment(seed=42, max_episode_frames=32)
        samples = []
        for action in range(9):
            payload = env.step(action)
            self.assertEqual(
                payload["info"]["provenance"]["feature_schema_version"],
                REQUIRED_NATIVE_FEATURE_SCHEMA_VERSION,
            )
            samples.append(encode_state(payload["train_only_state"]))
        model = StateActorCritic()
        logits, values = model(batch_states(samples))
        self.assertEqual(tuple(logits.shape), (9, 9))
        self.assertTrue(bool(torch.isfinite(values).all()))
        (-torch.log_softmax(logits, -1)[:, 1].mean() + values.square().mean()).backward()
        self.assertTrue(any(parameter.grad is not None and bool(parameter.grad.abs().sum() > 0) for parameter in model.parameters()))


if __name__ == "__main__":
    unittest.main()
