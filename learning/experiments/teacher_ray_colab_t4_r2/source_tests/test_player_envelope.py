"""CPU Q16 arithmetic and actual PPO bootstrap path; no native games/MPS."""

import hashlib
import json
from pathlib import Path
import struct
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from dodge_rl.clearance_rays import clearance_ray_features
from dodge_rl.ray_frontend import batched_clearance_rays
from dodge_rl.player_geometry import AdmittedPlayerGeometryError,MAX_PLAYER_SIZE,MAX_PLAYER_SIZE_RAW
from dodge_rl.models.teacher import OmniscientEntityTeacher
from dodge_rl.models.ray_teacher import RayGeometryTeacher
from dodge_rl import ppo
from test_clearance_rays_source import scene


def tensors(data):
    return tuple(torch.tensor(x,dtype=d) for x,d in zip(data,
        (torch.float32,torch.float32,torch.int64,torch.bool),strict=True))


def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
def from_f32(x):return int(f32(f32(x)*f32(65536)))


def test_source_Q16_freeze_and_size_envelope_no_native_or_float_tolerance():
    rate=65536;observed=[]
    for timer in range(1,482):
        rate=from_f32(.4) if timer<=420 else rate+from_f32(f32(f32(.6)/f32(60)))
        if timer>480:rate=65536
        observed.append(rate)
    assert min(observed)==26214 and max(observed)==65536
    size=2*65536;sequence=[]
    for _ in range(11):
        assert size<4*65536
        size+=(32768*26214)>>16
        sequence.append(size)
    assert size==275249 and size/65536==4.1999664306640625
    assert sequence[-2]==262142
    # The NEXT raw frame executes the >4 branch, not a same-frame clamp.
    next_size=4*65536 if size>4*65536 else size
    assert next_size==262144
    assert (4*65536-1)+((32768*max(observed))>>16)==MAX_PLAYER_SIZE_RAW==294911
    assert MAX_PLAYER_SIZE==4.5-1/65536


@pytest.mark.parametrize('size',[2,4,275249/65536,MAX_PLAYER_SIZE])
@pytest.mark.parametrize('p',[(2,2),(125,125),(2+1/65536,125-1/65536)])
def test_legal_fixedpoint_edges_and_overshoot_match_scalar_geometry(size,p):
    values=tensors(scene(p=p,size=size,boxes=[(7,120,120,128,128,True)]))
    expected=torch.tensor(clearance_ray_features(*(v.tolist() for v in values)),dtype=torch.float32)
    assert torch.equal(batched_clearance_rays(*values),expected)
    assert 4*float(values[0][0,0,4])==size


@pytest.mark.parametrize('size,p',[(4.5,(64,64)),(MAX_PLAYER_SIZE+1/65536,(64,64)),
    (2-1/65536,(64,64)),(float('nan'),(64,64)),(float('inf'),(64,64)),
    (4,(2-1/65536,64)),(4,(125+1/65536,64))])
def test_outside_source_envelope_rejected_by_both_validators(size,p):
    values=tensors(scene(p=p,size=size))
    for call in (lambda:clearance_ray_features(*(v.tolist() for v in values)),
                 lambda:batched_clearance_rays(*values)):
        with pytest.raises(AdmittedPlayerGeometryError) as caught:call()
        row=caught.value.player_geometry_rows[0]
        assert set(row)=={'row','player_x','player_y','player_size'} and row['row']==0
        json.dumps(row,allow_nan=False)


class BootstrapEnv:
    """One synthetic K1 vector; ended post-step observation is still forwarded."""
    def __init__(self,terminal,size):
        self.terminal,self.size=terminal,size;self.stepped=False;self.resets=0
    def batch_info(self):
        return dict(batch_size=1,raw_frame_cap=1,action_repeat=1,seed_mode={'mode':'training'},
            effective_excluded_seed_ranges=list(ppo._RESERVED_RANGES),next_episode_indices=[1])
    def observations(self):
        data=scene(p=(2,125),size=self.size if self.stepped else 4)
        return {k:np.asarray(v,dtype=d) for k,v,d in zip(ppo._OBSERVATIONS,data,
            (np.float32,np.float32,np.int64,np.bool_),strict=True)}
    def episode_info(self):
        terminal=self.stepped and self.terminal;truncated=self.stepped and not self.terminal
        alive=int(self.stepped)-int(terminal)
        return [dict(seed=dict(slot=0,episode=0,counter=0,actual_seed=100,evaluation=False),startup_frames=13,
            gameplay_frames=int(self.stepped),alive_frames=alive,score_raw_fixed=0,score=0.,score_delta_sum_raw_fixed=0,
            objective_return=alive/100-5*terminal,terminated=terminal,truncated=truncated,bootstrap=not terminal,
            death_event_count=int(terminal))]
    def step(self,actions):
        assert not self.stepped;self.stepped=True
        return dict(observations=self.observations(),rewards=np.array([0. if self.terminal else .01],dtype=np.float32)-5*self.terminal,
            score_delta_raw_fixed=np.array([0],dtype=np.int32),alive_raw_frames=np.array([not self.terminal],dtype=np.uint32),
            elapsed_raw_frames=np.array([1],dtype=np.uint32),terminated=np.array([self.terminal]),
            truncated=np.array([not self.terminal]),info=self.episode_info())
    def reset_done(self,indices):
        self.resets+=1;raise AssertionError('Closing vector must not reset')


@pytest.mark.parametrize('terminal',[False,True])
def test_actual_PPO_post_step_forward_accepts_overshoot_before_terminal_mask(terminal):
    model=RayGeometryTeacher(OmniscientEntityTeacher())
    with torch.no_grad():model.critic_head[-1].weight.zero_();model.critic_head[-1].bias.fill_(7)
    seen=[]
    handle=model.register_forward_pre_hook(lambda m,args:seen.append(float(args[0][0,0,4])*4))
    env=BootstrapEnv(terminal,275249/65536)
    try:result=ppo.collect_rollout(model,env,1,'cpu',gameplay_frame_budget=1)
    finally:handle.remove()
    assert seen==[4,275249/65536] and env.resets==0
    assert result.gameplay_frames==1 and result.batch.next_values.item()==(0 if terminal else 7)
    assert result.batch.terminated.item()==terminal and result.batch.truncated.item()!=terminal


@pytest.mark.parametrize('size',[4.5,float('nan')])
def test_invalid_terminal_row_still_fails_before_mask_with_minimal_diagnostic(size):
    model=RayGeometryTeacher(OmniscientEntityTeacher());env=BootstrapEnv(True,size)
    with pytest.raises(AdmittedPlayerGeometryError) as caught:
        ppo.collect_rollout(model,env,1,'cpu',gameplay_frame_budget=1)
    assert caught.value.phase=='post_step_bootstrap' and env.resets==0
    expected_size='nan' if np.isnan(size) else size
    assert caught.value.player_geometry_rows==[dict(row=0,player_x=2.,player_y=125.,player_size=expected_size)]
    from geometry_diagnostics import geometry_failure
    diagnostic=geometry_failure(caught.value)
    assert diagnostic==[dict(row=0,player_x=2.,player_y=125.,player_size=expected_size,phase='post_step_bootstrap')]
    json.dumps(diagnostic,allow_nan=False)


def test_original_PPO_masking_and_reward_audit_code_not_changed():
    root=Path(__file__).resolve().parents[1]
    old=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-teacher-ray-geometry-20261030/learning/runs/v2/teacher-ray-screen-20261030-r3/runtime/dodge_rl/ppo.py').read_text()
    new=(root/'ppo_runtime.py').read_text()
    for start,end in [('                storage["next_values"][step].copy_', '                _guard(check_guard)'),
                      ('def _audit_step(', '\ndef collect_rollout(')]:
        assert old[old.index(start):old.index(end,old.index(start))]==new[new.index(start):new.index(end,new.index(start))]
