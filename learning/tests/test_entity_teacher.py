"""Privileged input preservation and entity-transformer decision-path checks."""

from __future__ import annotations

import copy
import importlib.util
import unittest
import warnings
from dataclasses import asdict, replace

HAS_MODELS = importlib.util.find_spec("torch") is not None and importlib.util.find_spec("numpy") is not None
if HAS_MODELS:
    import numpy as np
    import torch

    from dodge_learning.entity_teacher import (
        ENTITY_DIM,
        ENTITY_TEACHER_SCHEMA_VERSION,
        LEGACY_ENTITY_TEACHER_SCHEMA_VERSION,
        GLOBAL_DIM,
        MAX_ENTITY_COUNT,
        REQUIRED_PRIVILEGED_SCHEMA_VERSION,
        EncodedEntities,
        EntityActorCritic,
        EntityTeacherConfig,
        batch_entities,
        encode_entities,
    )


def sample_privileged_state(count: int = 4) -> dict:
    rows = []
    for index in range(count):
        features = [0.0] * 32
        features[:5] = [0.5 - index, 0.25 + index, index / 4, -index / 8, 0.5]
        features[9] = index / 10
        rows.append({
            "features": features, "kind": index if index < 4 else 5,
            "bounds": [64.0 - index * 128, 32.0, 68.0 - index * 128, 36.0],
            "spatial": index > 0,
        })
    return {"schema_version": 1, "globals": [0.0] * 64, "entities": rows, "capture_bounds": [0.0, 0.0, 128.0, 128.0]}


def archived_legacy_teacher(config):
    """Version-1 architecture kept independent of the new forward branches."""
    nn = torch.nn
    width, hidden = config.embed_dim, int(config.embed_dim * config.mlp_ratio)

    class LegacyBlock(nn.Module):
        def __init__(self):
            super().__init__()
            self.token_norm, self.query_norm = nn.LayerNorm(width), nn.LayerNorm(width)
            self.attention = nn.MultiheadAttention(width, config.num_heads, dropout=config.dropout, batch_first=True)
            self.query_mlp_norm, self.token_mlp_norm = nn.LayerNorm(width), nn.LayerNorm(width)

            def mlp():
                return nn.Sequential(nn.Linear(width, hidden), nn.GELU(), nn.Dropout(config.dropout),
                                     nn.Linear(hidden, width), nn.Dropout(config.dropout))

            self.query_mlp, self.token_mlp = mlp(), mlp()
            self.dropout = nn.Dropout(config.dropout)

        def forward(self, query, tokens, mask):
            tokens = tokens + self.token_mlp(self.token_mlp_norm(tokens))
            normalized = self.token_norm(tokens)
            attended, weights = self.attention(self.query_norm(query), normalized, normalized,
                                              key_padding_mask=~mask, need_weights=True,
                                              average_attn_weights=True)
            query = query + self.dropout(attended)
            return query + self.query_mlp(self.query_mlp_norm(query)), tokens, weights[:, 0]

    class LegacyTeacher(nn.Module):
        def __init__(self):
            super().__init__()
            self.entity_projection = nn.Linear(32, width)
            self.kind_embedding = nn.Embedding(16, width)
            self.global_projection = nn.Sequential(nn.Linear(64, width), nn.GELU(), nn.Linear(width, width))
            self.blocks = nn.ModuleList(LegacyBlock() for _ in range(config.depth))
            self.output_norm = nn.LayerNorm(width)
            self.actor, self.value = nn.Linear(width, 9), nn.Linear(width, 1)
            nn.init.orthogonal_(self.actor.weight, gain=.01)
            nn.init.zeros_(self.actor.bias)
            nn.init.orthogonal_(self.value.weight, gain=1.)
            nn.init.zeros_(self.value.bias)

        def forward(self, batch):
            features = batch.features.masked_fill(~batch.mask.unsqueeze(-1), 0.)
            kinds = batch.kinds.masked_fill(~batch.mask, 0)
            tokens = self.entity_projection(features) + self.kind_embedding(kinds)
            query = tokens[:, :1] + self.global_projection(batch.globals).unsqueeze(1)
            for block in self.blocks:
                query, tokens, attention = block(query, tokens, batch.mask)
            latent = self.output_norm(query[:, 0])
            return self.actor(latent), self.value(latent).squeeze(-1), latent, attention

    return LegacyTeacher()


@unittest.skipUnless(HAS_MODELS, "install the optional PyTorch model extra")
class EntityEncodingTests(unittest.TestCase):
    def test_schema_retains_offscreen_and_nonspatial_entities_without_normalizing_twice(self) -> None:
        raw = sample_privileged_state()
        raw["entities"][3]["spatial"] = False
        encoded = encode_entities(raw)
        self.assertEqual((ENTITY_TEACHER_SCHEMA_VERSION, REQUIRED_PRIVILEGED_SCHEMA_VERSION), (2, 1))
        self.assertEqual(LEGACY_ENTITY_TEACHER_SCHEMA_VERSION, 1)
        self.assertEqual(encoded.features.shape, (4, ENTITY_DIM))
        self.assertEqual(encoded.globals.shape, (GLOBAL_DIM,))
        self.assertEqual(encoded.features[3, 0], -2.5)
        self.assertEqual(encoded.kinds.tolist(), [0, 1, 2, 3])
        np.testing.assert_array_equal(encoded.bounds[3], raw["entities"][3]["bounds"])

    def test_arrays_are_owned_immutable_and_preserve_native_values(self) -> None:
        raw = sample_privileged_state()
        state = encode_entities(raw)
        raw["entities"][0]["features"][0] = 99
        raw["globals"][0] = 99
        self.assertEqual(state.features[0, 0], 0.5)
        self.assertEqual(state.globals[0], 0)
        for values in (state.globals, state.features, state.kinds, state.bounds, state.spatial, state.capture_bounds):
            with self.assertRaises(ValueError):
                values.setflags(write=True)

    def test_schema_rejects_missing_extra_and_bad_versions(self) -> None:
        for record_path, key in (((), "seed"), (("entities", 0), "visible")):
            raw = sample_privileged_state()
            record = raw
            for item in record_path:
                record = record[item]
            record[key] = 1
            with self.subTest(key=key), self.assertRaises(ValueError):
                encode_entities(raw)
        for version in (True, 1.0, 0, 2):
            raw = sample_privileged_state()
            raw["schema_version"] = version
            with self.subTest(version=version), self.assertRaises(ValueError):
                encode_entities(raw)

    def test_rejects_boolean_or_nonfinite_numeric_inputs_and_bad_kinds(self) -> None:
        for value in (True, float("nan"), float("inf"), 1e100, "1"):
            for target in ("globals", "features", "bounds", "capture_bounds"):
                raw = sample_privileged_state()
                if target in ("features", "bounds"):
                    raw["entities"][1][target][0] = value
                else:
                    raw[target][0] = value
                with self.subTest(value=value, target=target), self.assertRaises(ValueError):
                    encode_entities(raw)
        for kind in (True, 1.0, -1, 16):
            raw = sample_privileged_state()
            raw["entities"][1]["kind"] = kind
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                encode_entities(raw)
        raw = sample_privileged_state()
        raw["entities"][1]["spatial"] = 1
        with self.assertRaises(ValueError):
            encode_entities(raw)

    def test_player_is_required_once_and_capacity_does_not_truncate(self) -> None:
        for change in ("empty", "missing_player", "second_player", "capacity"):
            raw = sample_privileged_state()
            if change == "empty":
                raw["entities"] = []
            elif change == "missing_player":
                raw["entities"][0]["kind"] = 1
            elif change == "second_player":
                raw["entities"][1]["kind"] = 0
            else:
                raw["entities"] = [raw["entities"][0]] * (MAX_ENTITY_COUNT + 1)
            with self.subTest(change=change), self.assertRaises(ValueError):
                encode_entities(raw)

    def test_half_open_geometry_has_ordered_corners_and_allows_empty_capture(self) -> None:
        raw = sample_privileged_state()
        raw["capture_bounds"] = [0, 0, 0, 0]
        state = encode_entities(raw)
        np.testing.assert_array_equal(state.capture_bounds, [0, 0, 0, 0])
        raw["entities"][1]["bounds"] = [2, 0, 1, 4]
        with self.assertRaises(ValueError):
            encode_entities(raw)

    def test_batch_padding_keeps_every_entity_and_geometry(self) -> None:
        sparse, dense = encode_entities(sample_privileged_state(1)), encode_entities(sample_privileged_state(6))
        batch = batch_entities([sparse, dense])
        self.assertEqual(tuple(batch.features.shape), (2, 6, ENTITY_DIM))
        self.assertEqual(batch.mask.sum(dim=1).tolist(), [1, 6])
        np.testing.assert_array_equal(batch.features[1].numpy(), dense.features)
        np.testing.assert_array_equal(batch.bounds[1].numpy(), dense.bounds)
        for invalid in ([], [object()], "state"):
            with self.assertRaises(ValueError):
                batch_entities(invalid)


@unittest.skipUnless(HAS_MODELS, "install the optional PyTorch model extra")
class EntityTransformerTests(unittest.TestCase):
    def test_default_matches_archived_schema_one_weights_rng_and_outputs_exactly(self) -> None:
        config = EntityTeacherConfig(embed_dim=32, depth=2)
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(102)
            legacy = archived_legacy_teacher(config).eval()
            expected_rng = torch.random.get_rng_state().clone()
            torch.manual_seed(102)
            current = EntityActorCritic(config).eval()
            self.assertTrue(torch.equal(expected_rng, torch.random.get_rng_state()))
        self.assertEqual(set(legacy.state_dict()), set(current.state_dict()))
        for name, value in legacy.state_dict().items():
            torch.testing.assert_close(current.state_dict()[name], value, rtol=0, atol=0)
        current.load_state_dict(legacy.state_dict(), strict=True)
        batch = batch_entities([encode_entities(sample_privileged_state(1)), encode_entities(sample_privileged_state(6))])
        with torch.no_grad():
            expected = legacy(batch)
            output = current.distillation_outputs(batch)
        for actual, old in zip((output.logits, output.value, output.latent, output.attention), expected):
            torch.testing.assert_close(actual, old, rtol=0, atol=0)

    def test_fresh_policy_does_not_start_with_a_strong_direction_preference(self) -> None:
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(7)
            model = EntityActorCritic().eval()
        with torch.no_grad():
            logits, _ = model(batch_entities([encode_entities(sample_privileged_state())]))
        probabilities = logits.softmax(dim=-1)
        entropy = -(probabilities * probabilities.log()).sum(dim=-1)
        self.assertLess(float(probabilities.max() - probabilities.min()), 0.01)
        self.assertGreater(float(entropy.item()), 2.19)

    @classmethod
    def setUpClass(cls) -> None:
        cls.previous_threads = torch.get_num_threads()
        torch.set_num_threads(1)

    @classmethod
    def tearDownClass(cls) -> None:
        torch.set_num_threads(cls.previous_threads)

    def model(self) -> EntityActorCritic:
        with torch.random.fork_rng(devices=[]):
            torch.random.default_generator.manual_seed(17)
            return EntityActorCritic(EntityTeacherConfig(embed_dim=32, depth=2, num_heads=4))

    def test_config_validation_and_default_width(self) -> None:
        config = EntityTeacherConfig()
        self.assertEqual(config.embed_dim, 128)
        self.assertEqual(EntityTeacherConfig(**asdict(config)), config)
        for key, value in (("embed_dim", True), ("depth", 0), ("num_heads", 3), ("dropout", 1), ("mlp_ratio", float("nan"))):
            with self.subTest(key=key), self.assertRaises(ValueError):
                EntityTeacherConfig(**{key: value})
        with self.assertRaises(TypeError):
            EntityActorCritic({})

    def test_representation_controls_are_opt_in_and_strictly_bounded(self) -> None:
        config = EntityTeacherConfig()
        self.assertEqual((config.attention_prior, config.relative_geometry, config.kind_embedding_scale), (1., False, 1.))
        for key, values in (
            ("attention_prior", (0, .5, 4097, True, "512", float("inf"), float("nan"), 10**1000)),
            ("kind_embedding_scale", (0, .0001, 1.01, True, float("inf"), float("nan"), 10**1000)),
            ("relative_geometry", (0, 1, "true", np.bool_(True))),
        ):
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    EntityTeacherConfig(**{key: value})

    def test_kind_scaling_keeps_all_other_initial_weights_and_rng_draws(self) -> None:
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(91)
            baseline = EntityActorCritic(EntityTeacherConfig(embed_dim=32))
            baseline_rng = torch.random.get_rng_state().clone()
            torch.manual_seed(91)
            scaled = EntityActorCritic(EntityTeacherConfig(embed_dim=32, kind_embedding_scale=.02))
            self.assertTrue(torch.equal(baseline_rng, torch.random.get_rng_state()))
        self.assertEqual(set(baseline.state_dict()), set(scaled.state_dict()))
        for name, value in baseline.state_dict().items():
            expected = value * .02 if name == "kind_embedding.weight" else value
            torch.testing.assert_close(scaled.state_dict()[name], expected, rtol=0, atol=0)

    def test_relative_geometry_preserves_player_metadata_and_recoverable_coordinates(self) -> None:
        raw = sample_privileged_state(5)
        prefixes = [[.5, .25, .5, -.25], [1., .75, -.5, .25], [-.5, 1., 1.5, -.5], [.2, .4, .9, .8], [9., 8., 7., 6.]]
        for row, prefix in zip(raw["entities"], prefixes):
            row["features"][:4] = prefix
        batch = batch_entities([encode_entities(raw)])
        model = EntityActorCritic(EntityTeacherConfig(embed_dim=32, relative_geometry=True))
        actual = model._policy_features(batch)
        expected = batch.features.clone()
        player = expected[0, 0, :4].clone()
        expected[0, 1:3, :4] -= player
        endpoint_origin = torch.cat((player[:2], player[:2]))
        expected[0, 3, :4] -= endpoint_origin
        torch.testing.assert_close(actual, expected, rtol=0, atol=0)
        torch.testing.assert_close(actual[0, 1:3, :4] + player, batch.features[0, 1:3, :4])
        torch.testing.assert_close(actual[0, 3, :4] + endpoint_origin, batch.features[0, 3, :4])
        torch.testing.assert_close(actual[0, (0, 4)], batch.features[0, (0, 4)], rtol=0, atol=0)
        torch.testing.assert_close(actual[:, :, 4:], batch.features[:, :, 4:], rtol=0, atol=0)

        translated = copy.deepcopy(raw)
        delta = torch.tensor([.125, -.125, .25, -.5])
        for index in (0, 1, 2):
            translated["entities"][index]["features"][:4] = (torch.tensor(prefixes[index]) + delta).tolist()
        translated["entities"][3]["features"][:4] = (torch.tensor(prefixes[3]) + torch.cat((delta[:2], delta[:2]))).tolist()
        shifted = model._policy_features(batch_entities([encode_entities(translated)]))
        torch.testing.assert_close(shifted[0, 1:4, :4], actual[0, 1:4, :4])

    def test_finite_physical_prior_retains_offscreen_objects_and_all_catalog_keys(self) -> None:
        raw = sample_privileged_state(9)
        kinds = [0, 1, 2, 2, 3, 3, 3, 5, 8]
        for row, kind in zip(raw["entities"], kinds):
            row["kind"] = kind
            row["features"] = [0.] * 32
            row["spatial"] = False
        raw["entities"][1]["features"][:2] = [-2., -2.]
        raw["entities"][1]["bounds"] = [-256., -256., -252., -252.]
        raw["entities"][2]["features"][16] = 1.
        for index, parent, phase in ((4, .25, 1.), (5, .5, 1.), (6, .25, 0.)):
            raw["entities"][index]["features"][4] = parent
            raw["entities"][index]["features"][7] = phase
        raw["globals"][20:22] = [1., .25]
        batch = batch_entities([encode_entities(raw)])
        model = EntityActorCritic(EntityTeacherConfig(embed_dim=32, attention_prior=512.)).eval()
        with torch.no_grad():
            for block in model.blocks:
                block.attention.in_proj_weight[:64].zero_()
                block.attention.in_proj_bias[:64].zero_()
        with warnings.catch_warnings(record=True) as caught, torch.no_grad():
            warnings.simplefilter("always")
            output = model.distillation_outputs(batch)
        self.assertFalse(caught)
        expected = torch.ones(1, 9)
        expected[0, (1, 2, 4)] = 512.
        expected /= expected.sum(dim=1, keepdim=True)
        torch.testing.assert_close(output.attention, expected, atol=1e-7, rtol=1e-6)
        self.assertEqual(tuple(output.attention.shape), (1, 9))
        self.assertTrue(bool((output.attention > 0).all()))
        self.assertTrue(bool(torch.isfinite(output.logits).all()))
        changed = replace(batch, spatial=~batch.spatial)
        torch.testing.assert_close(model.distillation_outputs(changed).attention, output.attention, rtol=0, atol=0)

    def test_representation_controls_keep_permutation_padding_and_gradients_valid(self) -> None:
        raw = sample_privileged_state(6)
        permutation = [0, 5, 3, 1, 4, 2]
        changed = copy.deepcopy(raw)
        changed["entities"] = [changed["entities"][index] for index in permutation]
        config = EntityTeacherConfig(embed_dim=32, attention_prior=512., relative_geometry=True, kind_embedding_scale=.02)
        model = EntityActorCritic(config).eval()
        batch = batch_entities([encode_entities(raw), encode_entities(changed)])
        output = model.distillation_outputs(batch)
        torch.testing.assert_close(output.logits[0], output.logits[1], atol=1e-6, rtol=1e-5)
        torch.testing.assert_close(output.attention[0, permutation], output.attention[1], atol=1e-7, rtol=1e-5)
        loss = torch.nn.functional.cross_entropy(output.logits, torch.tensor([1, 3])) + output.value.square().mean()
        loss.backward()
        for block in model.blocks:
            gradient = block.attention.in_proj_weight.grad
            self.assertTrue(bool(torch.isfinite(gradient).all()))
            self.assertGreater(float(gradient[:64].abs().sum()), 0)

        sparse = batch_entities([encode_entities(sample_privileged_state(1)), encode_entities(raw)])
        expected = model.distillation_outputs(sparse)
        features, kinds, bounds = sparse.features.clone(), sparse.kinds.clone(), sparse.bounds.clone()
        features[~sparse.mask] = float("nan")
        kinds[~sparse.mask] = 123456
        bounds[~sparse.mask] = float("nan")
        padded = replace(sparse, features=features, kinds=kinds, bounds=bounds, spatial=~sparse.spatial)
        actual = model.distillation_outputs(padded)
        torch.testing.assert_close(actual.logits, expected.logits, rtol=0, atol=0)
        self.assertEqual(float(actual.attention[0, 1:].detach().sum()), 0.)
        torch.testing.assert_close(actual.attention.sum(dim=1), torch.ones(2))

    def test_player_only_attention_and_ppo_outputs_are_finite(self) -> None:
        model = self.model().eval()
        batch = batch_entities([encode_entities(sample_privileged_state(1))])
        output = model.distillation_outputs(batch)
        logits, values = model(batch)
        self.assertEqual(tuple(output.latent.shape), (1, 32))
        self.assertEqual(tuple(logits.shape), (1, 9))
        self.assertEqual(tuple(values.shape), (1,))
        torch.testing.assert_close(output.attention, torch.ones(1, 1))
        torch.testing.assert_close(output.logits, logits)
        torch.testing.assert_close(output.value, values)
        self.assertTrue(bool(torch.isfinite(output.latent).all()))

    def test_permuting_nonplayer_rows_preserves_policy_and_permutes_attention(self) -> None:
        raw = sample_privileged_state(6)
        permutation = [0, 5, 3, 1, 4, 2]
        changed = copy.deepcopy(raw)
        changed["entities"] = [changed["entities"][index] for index in permutation]
        model = self.model().eval()
        output = model.distillation_outputs(batch_entities([encode_entities(raw), encode_entities(changed)]))
        torch.testing.assert_close(output.logits[0], output.logits[1], atol=1e-6, rtol=1e-5)
        torch.testing.assert_close(output.latent[0], output.latent[1], atol=1e-6, rtol=1e-5)
        torch.testing.assert_close(output.attention[0, permutation], output.attention[1], atol=1e-7, rtol=1e-5)

    def test_arbitrary_padding_and_spatial_flags_do_not_change_policy(self) -> None:
        states = [encode_entities(sample_privileged_state(1)), encode_entities(sample_privileged_state(6))]
        model = self.model().eval()
        batch = batch_entities(states)
        expected = model.distillation_outputs(batch)
        features, kinds, bounds = batch.features.clone(), batch.kinds.clone(), batch.bounds.clone()
        features[~batch.mask] = float("nan")
        kinds[~batch.mask] = 123456
        bounds[~batch.mask] = float("nan")
        changed = replace(batch, features=features, kinds=kinds, bounds=bounds, spatial=~batch.spatial)
        actual = model.distillation_outputs(changed)
        torch.testing.assert_close(expected.logits, actual.logits)
        torch.testing.assert_close(expected.latent, actual.latent)
        self.assertEqual(float(actual.attention[0, 1:].detach().abs().sum()), 0.0)
        torch.testing.assert_close(actual.attention.sum(dim=1), torch.ones(2))
        solo = model.distillation_outputs(batch_entities(states[:1]))
        torch.testing.assert_close(solo.logits[0], actual.logits[0], atol=1e-6, rtol=1e-5)

    def test_ppo_loss_trains_threat_attention_and_nonvisual_state_changes_decision(self) -> None:
        model = self.model()
        raw = sample_privileged_state(6)
        changed = copy.deepcopy(raw)
        changed["entities"][5]["features"][9] += 10
        changed["globals"][18] += 1
        output = model.distillation_outputs(batch_entities([encode_entities(raw), encode_entities(changed)]))
        self.assertFalse(torch.allclose(output.logits[0], output.logits[1]))
        loss = torch.nn.functional.cross_entropy(output.logits, torch.tensor([1, 3])) + output.value.square().mean()
        loss.backward()
        for block in model.blocks:
            gradient = block.attention.in_proj_weight.grad
            self.assertIsNotNone(gradient)
            self.assertTrue(bool(torch.isfinite(gradient).all()))
            # Query/key projection gradients prove learned attention weighting
            # participates in PPO, rather than exposing decorative saliency.
            self.assertGreater(float(gradient[: 2 * model.config.embed_dim].abs().sum()), 0)

    def test_invalid_valid_rows_fail_before_attention(self) -> None:
        batch = batch_entities([encode_entities(sample_privileged_state())])
        model = self.model()
        bad_features = batch.features.clone()
        bad_features[0, 2, 0] = float("nan")
        bad_mask = batch.mask.clone()
        bad_mask[0, 0] = False
        for invalid in (
            replace(batch, features=bad_features), replace(batch, mask=bad_mask),
            replace(batch, kinds=batch.kinds.float()),
            replace(batch, globals=batch.globals.double()),
        ):
            with self.assertRaises(ValueError):
                model(invalid)


if __name__ == "__main__":
    unittest.main()
