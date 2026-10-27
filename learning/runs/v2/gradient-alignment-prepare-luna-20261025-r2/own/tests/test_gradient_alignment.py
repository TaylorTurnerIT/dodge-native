import math
import pytest
import torch
from dodge_rl.gradient_alignment import summarize


def measure(a, c):
    p = torch.nn.Parameter(torch.zeros(len(a)))
    return summarize((torch.tensor(a, dtype=torch.float32),), (torch.tensor(c, dtype=torch.float32),), [('x', p)], metadata={})


def test_analytic_alignment_zero_unused_and_groups():
    assert measure([1, 0], [2, 0])['cosine'] == 1.0
    assert measure([1, 0], [0, 2])['cosine'] == 0.0
    assert measure([1, 0], [-2, 0])['cosine'] == -1.0
    assert measure([3, 4], [6, 8])['norm_ratio_critic_over_actor'] == 2.0
    z = measure([0, 0], [1, 0])
    assert z['defined'] is False and z['zero_norm_reason'] == 'actor_gradient_zero'
    assert 'cosine' not in z and 'norm_ratio_critic_over_actor' not in z
    p1, p2 = torch.nn.Parameter(torch.zeros(1)), torch.nn.Parameter(torch.zeros(2))
    r = summarize((torch.ones(1), None), (None, torch.ones(2)), [('layers.0.w', p1), ('layers.1.w', p2)], metadata={})
    assert r['coverage'] == {'actor_used': 1, 'critic_used': 1, 'parameters': 2, 'elements': 3}
    assert set(r['groups']) == {'layers.0', 'layers.1'}
    assert r['groups']['layers.0']['defined'] is False


def test_nonfinite_and_shape_mismatch_rejected_with_name():
    p = torch.nn.Parameter(torch.zeros(2))
    with pytest.raises(FloatingPointError, match=r'actor gradient for trunk.weight at \(1,\)'):
        summarize((torch.tensor([1., float('nan')]),), (torch.ones(2),), [('trunk.weight', p)], metadata={})
    with pytest.raises(ValueError, match='shape mismatch for trunk.weight'):
        summarize((torch.ones(1),), (torch.ones(2),), [('trunk.weight', p)], metadata={})


def test_all_emitted_numbers_finite_and_none_free():
    result = measure([1, 2], [2, 1])
    def walk(value):
        if isinstance(value, dict):
            for item in value.values(): walk(item)
        elif isinstance(value, (tuple, list)):
            for item in value: walk(item)
        elif value is None:
            raise AssertionError('unexpected None')
        elif isinstance(value, float):
            assert math.isfinite(value)
    walk(result)
