"""Real checkpoint420 read-only CPU compatibility; no native games or MPS."""

import hashlib
import io
import importlib.util
import os
from pathlib import Path
import random
import sys

import pytest
import torch

from dodge_rl.clearance_rays import clearance_ray_features
from dodge_rl.ray_frontend import batched_clearance_rays
from dodge_rl.ray_migration import migrate_adam
from dodge_rl.models.ray_teacher import RayGeometryTeacher
from dodge_rl.models.teacher import OmniscientEntityTeacher
from test_clearance_rays_source import scene

CHECKPOINT = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/uniform2-recovery240-luna-20261028-r1/worker-output/checkpoint-global-420.pt')
DIGEST = '7e0de8640f1337261412d91cde6bc692772ff212fbd360f5aad415dc6bc7ed4b'


def tensors(data):
    return tuple(torch.tensor(x, dtype=dtype) for x, dtype in zip(
        data, (torch.float32, torch.float32, torch.int64, torch.bool), strict=True))


def test_batched_double_geometry_exact_float32_reference_and_padding():
    rng = random.Random(9821)
    examples = []
    for _ in range(100):
        boxes = [(k, rng.randrange(-4, 130), rng.randrange(-4, 130),
                  rng.randrange(-4, 130), rng.randrange(-4, 130), k != 4)
                 for k in (1, 4, 7, 8)]
        examples.append(scene(p=(rng.choice([2, 23, 64, 125]), rng.choice([2, 63.5, 125])),
                              size=rng.choice([2, 3, 4]), boxes=boxes))
    batch = [[data[i][0] for data in examples] for i in range(4)]
    values = tensors(batch)
    expected = torch.tensor(clearance_ray_features(*(v.tolist() for v in values)), dtype=torch.float32)
    assert torch.equal(batched_clearance_rays(*values), expected)
    changed = list(values)
    changed[1] = changed[1].clone(); changed[2] = changed[2].clone()
    changed[1][~changed[3]] = float('nan'); changed[2][~changed[3]] = 999
    assert torch.equal(batched_clearance_rays(*changed), expected)


def test_screen_ppo_cpu_geometry_route_and_valid_partial_macro_batch():
    source=Path(__file__).resolve().parents[1]/'ppo_runtime.py'
    spec=importlib.util.spec_from_file_location('dodge_rl.ppo_screen_fixture',source)
    ppo=importlib.util.module_from_spec(spec);sys.modules[spec.name]=ppo
    try:
        spec.loader.exec_module(ppo)
        model=RayGeometryTeacher(OmniscientEntityTeacher())
        data=tensors(scene())
        # Requested learner device is MPS; CPU model/arrays prove the route does
        # not attempt a forward/reverse MPS transfer before geometry derivation.
        result=ppo._model_output(model,dict(zip(ppo._OBSERVATIONS,data)),torch.device('mps'))
        assert result.logits.device.type=='cpu'
        arrays=[v.unsqueeze(0).repeat(3,2,*([1]*(v.ndim-1))) for v in data]
        shape=(3,2);actions=torch.zeros(shape,dtype=torch.int64)
        with torch.no_grad():
            flat=[v.flatten(0,1) for v in arrays]
            output=model(*flat)
            values=output.values.reshape(shape).clone()
            old=output.logits.log_softmax(-1)[:,0].reshape(shape).clone()
        batch=ppo.RolloutBatch(*arrays,actions,old,values,torch.ones(shape)*.25,
            values+.01,torch.zeros(shape,dtype=torch.bool),torch.zeros(shape,dtype=torch.bool))
        optimizer=torch.optim.Adam(model.parameters(),lr=3e-5,eps=1e-5)
        metrics=ppo.ppo_update(model,optimizer,batch,ppo.PPOConfig(update_epochs=1,minibatch_size=2),
            microbatch_size=2,effective_minibatch_size=4)
        assert metrics['transitions']==6 and metrics['optimizer_steps']==2
        assert model.gate.item()!=0
    finally:
        del sys.modules[spec.name]


@pytest.mark.skipif(os.environ.get('RAY_CHECKPOINT420_CPU_FIXTURE') != '1', reason='Explicit read-only checkpoint CPU fixture')
def test_real_420_warm_start_and_name_mapped_adam_first_cpu_step():
    raw = CHECKPOINT.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == DIGEST
    state = torch.load(io.BytesIO(raw), weights_only=False, map_location='cpu')
    assert state['version'] == 'teacher_checkpoint_v1' and state['resume_mode'] == 'fresh_env'
    assert not state.get('update_progress', {}).get('in_update', False)
    control = OmniscientEntityTeacher()
    control.load_state_dict(state['model'], strict=True)
    legacy = OmniscientEntityTeacher()
    legacy.load_state_dict(state['model'], strict=True)
    rays = RayGeometryTeacher(legacy, branch_seed=123)
    control_optim, control_map = migrate_adam(state['optimizer'], control, control, learning_rate=3e-5, adam_eps=1e-5)
    ray_optim, ray_map = migrate_adam(state['optimizer'], legacy, rays, learning_rate=3e-5, adam_eps=1e-5)
    assert control_map['preserved_legacy_parameters'] == ray_map['preserved_legacy_parameters']
    assert len(ray_map['new_parameters_without_state']) == 5
    assert not any(p in ray_optim.state for p in [rays.gate, *rays.branch.parameters()])
    for name, p in control.named_parameters():
        q = dict(rays.named_parameters())['legacy.'+name]
        for field in ('step', 'exp_avg', 'exp_avg_sq'):
            assert torch.equal(control_optim.state[p][field], ray_optim.state[q][field])
    data = tensors(scene(boxes=[(1, 70, 60, 75, 68, True), (7, 60, 70, 68, 75, False)]))
    left, right = control(*data), rays(*data)
    for field in ('logits', 'values', 'latent'):
        assert torch.equal(getattr(left, field), getattr(right, field))
    for output, optimizer in ((left, control_optim), (right, ray_optim)):
        # One synthetic CPU fixture step, never native/MPS training.
        loss = output.logits[:, 0].sum() + output.values.sum()
        loss.backward(); optimizer.step()
    for name, p in control.named_parameters():
        q = dict(rays.named_parameters())['legacy.'+name]
        assert torch.equal(p, q), name
        for field in ('step', 'exp_avg', 'exp_avg_sq'):
            assert torch.equal(control_optim.state[p][field], ray_optim.state[q][field])
    assert rays.gate.item() != 0
    assert hashlib.sha256(CHECKPOINT.read_bytes()).hexdigest() == DIGEST
