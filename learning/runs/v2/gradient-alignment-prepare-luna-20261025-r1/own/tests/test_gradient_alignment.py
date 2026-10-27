import torch
from dodge_rl.gradient_alignment import summarize


def measure(a, c):
    p = torch.nn.Parameter(torch.zeros(len(a)))
    return summarize((torch.tensor(a, dtype=torch.float32),), (torch.tensor(c, dtype=torch.float32),), [('x', p)], metadata={})


def test_aligned_orthogonal_opposing_scaled_zero_and_coverage():
    assert measure([1, 0], [2, 0])['cosine'] == 1.0
    assert measure([1, 0], [0, 2])['cosine'] == 0.0
    assert measure([1, 0], [-2, 0])['cosine'] == -1.0
    assert measure([3, 4], [6, 8])['norm_ratio_critic_over_actor'] == 2.0
    z = measure([0, 0], [1, 0])
    assert z['cosine'] is None and z['zero_norm_reason'] == 'actor_gradient_zero'
    p1, p2 = torch.nn.Parameter(torch.zeros(1)), torch.nn.Parameter(torch.zeros(2))
    r = summarize((torch.ones(1), None), (None, torch.ones(2)), [('layers.0.w', p1), ('layers.1.w', p2)], metadata={})
    assert r['coverage'] == {'actor_used': 1, 'critic_used': 1, 'parameters': 2, 'elements': 3}
    assert set(r['groups']) == {'layers.0', 'layers.1'}
