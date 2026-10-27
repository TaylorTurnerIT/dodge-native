"""Synthetic CPU checks for the fixed full-attention teacher; no game rollouts."""

import io
import json

import pytest
import torch

from dodge_rl.models.teacher import CustomTransformerLayer, OmniscientEntityTeacher, TeacherOutput


@pytest.fixture(scope="module", autouse=True)
def bounded_cpu_threads():
    previous = torch.get_num_threads()
    torch.set_num_threads(4)
    yield
    torch.set_num_threads(previous)


def inputs(valid_counts=(4, 7)):
    generator = torch.Generator().manual_seed(382)
    batch = len(valid_counts)
    global_feats = torch.randn(batch, 1, 14, generator=generator) * 0.2
    entity_feats = torch.randn(batch, 80, 16, generator=generator) * 0.2
    entity_types = torch.randint(1, 9, (batch, 80), generator=generator)
    mask = torch.arange(80).unsqueeze(0) < torch.tensor(valid_counts).unsqueeze(1)
    entity_feats[~mask] = 0
    entity_types[~mask] = 0
    return global_feats, entity_feats, entity_types, mask


def make_model(seed=831):
    torch.manual_seed(seed)
    return OmniscientEntityTeacher()


def assert_same_policy(left, right):
    torch.testing.assert_close(left.logits, right.logits, rtol=1e-5, atol=1e-6)
    torch.testing.assert_close(left.values, right.values, rtol=1e-5, atol=1e-6)
    torch.testing.assert_close(left.latent, right.latent, rtol=1e-5, atol=2e-6)


def test_fixed_default_architecture_and_json_identity():
    model = make_model()
    description = model.architecture_description()
    assert json.loads(json.dumps(description)) == description
    assert description["token_count"] == 81
    assert description["model_dim"] == 128
    assert description["num_layers"] == 2
    assert description["num_heads"] == 4
    assert description["ffn_dim"] == 256
    assert description["entity_position_embeddings"] is False
    assert len(model.layers) == 2
    assert all(isinstance(layer, CustomTransformerLayer) for layer in model.layers)
    assert all(layer.mha.embed_dim == 128 and layer.mha.num_heads == 4 for layer in model.layers)
    assert all(layer.mha.dropout == 0.0 for layer in model.layers)
    assert all(layer.norm1.eps == layer.norm2.eps == 1e-5 for layer in model.layers)
    assert model.final_norm.eps == 1e-5
    description["entity_shape"][0] = 1
    assert model.architecture_description()["entity_shape"] == [80, 16]


@pytest.mark.parametrize("training", [True, False])
def test_outputs_and_full_attention_are_available_in_both_modes(training):
    model = make_model().train(training)
    with torch.no_grad():
        result = model(*inputs())
    assert isinstance(result, TeacherOutput)
    assert result.logits.shape == (2, 9)
    assert result.values.shape == (2,)
    assert result.latent.shape == (2, 128)
    assert len(result.attentions) == 2
    for tensor in (result.logits, result.values, result.latent, *result.attentions):
        assert torch.isfinite(tensor).all()
    for weights in result.attentions:
        assert weights.shape == (2, 81, 81)
        torch.testing.assert_close(weights.sum(dim=-1), torch.ones(2, 81))


def test_zero_entities_keep_global_key_valid_and_outputs_finite():
    model = make_model().eval()
    with torch.no_grad():
        result = model(*inputs((0, 0)))
    assert torch.isfinite(result.logits).all()
    assert torch.isfinite(result.values).all()
    assert torch.isfinite(result.latent).all()
    for weights in result.attentions:
        assert torch.isfinite(weights).all()
        assert torch.equal(weights[:, :, 0], torch.ones(2, 81))
        assert torch.count_nonzero(weights[:, :, 1:]) == 0


def test_masked_rows_are_invariant_even_for_nonfinite_padding_and_bad_padding_ids():
    model = make_model().eval()
    data = inputs()
    changed = [tensor.clone() for tensor in data]
    changed[1][~changed[3]] = float("nan")
    changed[2][~changed[3]] = 999
    with torch.no_grad():
        baseline, sentinel = model(*data), model(*changed)
    assert_same_policy(baseline, sentinel)
    for before, after in zip(baseline.attentions, sentinel.attentions, strict=True):
        assert torch.equal(before, after)


def test_entity_permutation_preserves_policy_and_permutes_attention_axes():
    model = make_model().eval()
    global_feats, entity_feats, types, mask = inputs()
    permutation = torch.randperm(80, generator=torch.Generator().manual_seed(71))
    full_permutation = torch.cat((torch.tensor([0]), permutation + 1))
    with torch.no_grad():
        original = model(global_feats, entity_feats, types, mask)
        permuted = model(global_feats, entity_feats[:, permutation], types[:, permutation], mask[:, permutation])
    assert_same_policy(original, permuted)
    for before, after in zip(original.attentions, permuted.attentions, strict=True):
        expected = before[:, full_permutation][:, :, full_permutation]
        torch.testing.assert_close(after, expected, rtol=1e-5, atol=1e-6)


def test_padding_key_weights_are_zero_in_every_layer():
    data = inputs()
    model = make_model()
    result = model(*data)
    padded_keys = torch.cat((torch.zeros(2, 1, dtype=torch.bool), ~data[3]), dim=1)
    for weights in result.attentions:
        assert torch.count_nonzero(weights.masked_select(padded_keys.unsqueeze(1))) == 0
        assert (weights[:, 0, 0] > 0).all()


def test_entity_queries_receive_other_entity_information_in_first_layer():
    model = make_model().eval()
    data = inputs((3,))
    changed = [tensor.clone() for tensor in data]
    changed[1][0, 1, 0] += 1.0
    changed[1][0, 1, 10] -= 0.75
    captured = []
    handle = model.layers[0].register_forward_hook(
        lambda _module, _args, output: captured.append(output[0].detach().clone())
    )
    try:
        with torch.no_grad():
            baseline, altered = model(*data), model(*changed)
    finally:
        handle.remove()
    # Query 1's own input is unchanged; entity 2 is a different valid key.
    assert torch.equal(data[1][0, 0], changed[1][0, 0])
    assert baseline.attentions[0][0, 1, 2] > 0
    assert altered.attentions[0][0, 1, 2] > 0
    assert torch.linalg.vector_norm(captured[0][0, 1] - captured[1][0, 1]) > 1e-4


def test_valid_threat_geometry_changes_policy_but_same_masked_intervention_does_not():
    model = make_model().eval()
    near = list(inputs((1,)))
    near[1].zero_()
    near[2][0, 0] = 1
    # Center, half-extents, relative position, signed gaps, time-to-overlap,
    # and lethal-now flag represent a nearby normal enemy.
    near[1][0, 0, [0, 2, 3, 4, 10, 11, 12, 15]] = torch.tensor(
        [0.02, 0.05, 0.05, 0.02, -0.01, -0.01, 0.0, 1.0]
    )
    far = [tensor.clone() for tensor in near]
    far[1][0, 0, [0, 4, 10, 12]] = torch.tensor([0.75, 0.75, 0.75, 1.0])
    with torch.no_grad():
        before, after = model(*near), model(*far)
    assert torch.linalg.vector_norm(before.latent - after.latent) > 0.01
    assert (before.logits - after.logits).abs().max() > 1e-6
    near[3].zero_()
    far[3].zero_()
    with torch.no_grad():
        assert_same_policy(model(*near), model(*far))


def gradient_mass(module):
    gradients = [parameter.grad for parameter in module.parameters() if parameter.grad is not None]
    assert all(torch.isfinite(gradient).all() for gradient in gradients)
    return sum(float(gradient.abs().sum()) for gradient in gradients)


def test_actor_and_critic_losses_route_to_their_head_and_shared_trunk():
    model = make_model()
    model(*inputs()).logits[:, 0].sum().backward()
    assert gradient_mass(model.actor_head) > 0
    assert all(parameter.grad is None for parameter in model.critic_head.parameters())
    for part in (model.global_projection, model.entity_projection, model.type_embedding, *model.layers, model.final_norm):
        assert gradient_mass(part) > 0
    model.zero_grad(set_to_none=True)
    model(*inputs()).values.sum().backward()
    assert gradient_mass(model.critic_head) > 0
    assert all(parameter.grad is None for parameter in model.actor_head.parameters())
    for part in (model.global_projection, model.entity_projection, model.type_embedding, *model.layers, model.final_norm):
        assert gradient_mass(part) > 0


def assert_orthogonal_weight(weight, gain_squared):
    # Normalize gains so the small actor head cannot hide errors under a fixed
    # absolute tolerance. Use float64 for the check, allowing eight float32
    # epsilons for the stored QR-initialized weights rather than dot roundoff.
    normalized_gram = weight.double() @ weight.double().T / gain_squared
    torch.testing.assert_close(
        normalized_gram,
        torch.eye(weight.shape[0], dtype=torch.float64),
        rtol=0,
        atol=8 * torch.finfo(weight.dtype).eps,
    )


def test_registered_head_initialization_and_biases():
    model = make_model()
    for head, final_gain in ((model.actor_head, 0.01), (model.critic_head, 1.0)):
        for index, gain_squared in ((0, 2.0), (2, final_gain**2)):
            weight = head[index].weight.detach()
            assert_orthogonal_weight(weight, gain_squared)
            assert torch.count_nonzero(head[index].bias) == 0


def test_orthogonality_check_rejects_perturbed_registered_head_weights():
    model = make_model()
    for head, final_gain in ((model.actor_head, 0.01), (model.critic_head, 1.0)):
        for index, gain_squared in ((0, 2.0), (2, final_gain**2)):
            changed = head[index].weight.detach().clone()
            changed[0, 0] += 0.1
            with pytest.raises(AssertionError):
                assert_orthogonal_weight(changed, gain_squared)


def test_fixed_input_state_dict_round_trip_is_exact():
    original = make_model().eval()
    data = inputs()
    buffer = io.BytesIO()
    torch.save(original.state_dict(), buffer)
    buffer.seek(0)
    restored = make_model(seed=12).eval()
    restored.load_state_dict(torch.load(buffer, weights_only=True))
    with torch.no_grad():
        before, after = original(*data), restored(*data)
    for left, right in zip(
        (before.logits, before.values, before.latent, *before.attentions),
        (after.logits, after.values, after.latent, *after.attentions),
        strict=True,
    ):
        assert torch.equal(left, right)


@pytest.mark.parametrize(
    "position,replacement,error",
    [
        (0, lambda value: value.squeeze(1), ValueError),
        (0, lambda value: value.double(), TypeError),
        (1, lambda value: value[:, :79], ValueError),
        (1, lambda value: value.half(), TypeError),
        (2, lambda value: value.int(), TypeError),
        (3, lambda value: value.to(torch.uint8), TypeError),
    ],
)
def test_layout_mismatches_fail_before_attention(position, replacement, error):
    model = make_model()
    data = list(inputs())
    data[position] = replacement(data[position])
    with pytest.raises(error):
        model(*data)


def test_empty_batch_is_rejected():
    model = make_model()
    with pytest.raises(ValueError, match="at least one"):
        model(*(tensor[:0] for tensor in inputs()))
