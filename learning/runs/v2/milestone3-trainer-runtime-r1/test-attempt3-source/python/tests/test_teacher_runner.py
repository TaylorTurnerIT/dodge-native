"""Synthetic protocol, source identity, evaluation, and resource guard tests."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import io
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from dodge_rl import dev_eval as d
from dodge_rl import identity as i
from dodge_rl import supervision as s
from dodge_rl import train_teacher as t

torch.set_num_threads(4)


def test_registered_namespaces_are_distinct_and_fully_fixed():
    configs = [i.default_config(phase, parent_sha256="a"*64 if phase in {"D1","D2","D3"} else None)
               for phase in ("probe","pilot","D1","D2","D3")]
    assert len({cfg["phase_settings"]["run_seed"] for cfg in configs}) == 5
    assert [cfg["phase_settings"]["budget_seconds"] for cfg in configs] == [180,300,1800,1800,1800]
    for cfg in configs: assert i.validate_config(cfg) == cfg
    bad = copy.deepcopy(configs[1]);bad["ppo"]["reward_scale"] = 1
    with pytest.raises(ValueError, match="registered"): i.validate_config(bad)


def test_constructors_explicitly_supply_all_reservations_and_resume_indices():
    cfg = i.default_config("pilot")
    value = i.training_env_config(cfg, [8]*64)
    assert value["excluded_seed_ranges"] == [(0xB0000000,0xB00003E7),(0xD0000000,0xD000007F),(0xE0000000,0xE00003E7)]
    assert value["initial_episode_indices"] == [8]*64
    for invalid in ([0], [None]*64, [-1]*64, [2**64]*64):
        with pytest.raises(ValueError): i.training_env_config(cfg, invalid)


def fake_training_env(cfg, *, omit_D=False, version="dodge_slot_splitmix64_high32_reject_v1", indices=None):
    indices = [0]*64 if indices is None else indices
    metadata = {"effective_excluded_seed_ranges": cfg["excluded_seed_ranges"][:1] if omit_D else cfg["excluded_seed_ranges"],
                "seed_stream_version": version, "seed_exclusion_version": "mandatory_b_plus_inclusive_union_rehash_v1",
                "seed_mode": {"mode":"training","run_seed":cfg["phase_settings"]["run_seed"]},
                "initial_episode_indices":indices,"batch_size":64,"action_repeat":4}
    infos = [{"seed":{"slot":slot,"episode":episode,"evaluation":False,"actual_seed":slot+100},
              "startup_frames":13,"gameplay_frames":0} for slot,episode in enumerate(indices)]
    return SimpleNamespace(batch_info=lambda:metadata,episode_info=lambda:infos)


def test_training_preflight_checks_effective_union_versions_and_echo():
    cfg=i.default_config("pilot")
    assert i.verify_training_env(fake_training_env(cfg),cfg)["batch_size"]==64
    with pytest.raises(ValueError,match="exclusions"): i.verify_training_env(fake_training_env(cfg,omit_D=True),cfg)
    with pytest.raises(ValueError,match="version"): i.verify_training_env(fake_training_env(cfg,version="other"),cfg)
    with pytest.raises(ValueError,match="echoed"): i.verify_training_env(fake_training_env(cfg,indices=[1]*64),cfg)


def fixture_root(path):
    names = ["Cargo.toml","Cargo.lock","rust-toolchain.toml",".cargo/config.toml","assets/dodge.p8",
             "python/pyproject.toml","python/requirements-local-mac.txt","docs/SPEC_PRIVILEGED_VIT_RL.md",
             "docs/implementation-plan-v2.md","docs/v2-environment-contract.md","docs/v2-teacher-training-plan.md",
             "docs/v2-m3-component-contract.md","docs/teacher-qualification-v2.json",str(i.PROTOCOL_PATH),
             "python/dodge_rl/model.py","python/dodge_rl/_native.so"]
    for name in names:
        p=path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b"original")
    return path


@pytest.mark.parametrize("change",["byte","untracked","binary"])
def test_inventory_catches_actual_bytes_untracked_files_and_so(tmp_path,change):
    root=fixture_root(tmp_path);before=i.source_inventory(root)
    if change=="byte": (root/"python/dodge_rl/model.py").write_bytes(b"originaL")
    if change=="untracked": (root/"python/dodge_rl/new.py").write_bytes(b"new")
    if change=="binary": (root/"python/dodge_rl/_native.so").write_bytes(b"different")
    assert i.source_inventory(root)!=before


def test_inventory_excludes_only_cache_artifacts(tmp_path):
    root=fixture_root(tmp_path);before=i.source_inventory(root)
    cache=root/"python/dodge_rl/__pycache__/generated.pyc";cache.parent.mkdir();cache.write_bytes(b"cache")
    assert i.source_inventory(root)==before


def test_real_identity_is_read_only_and_preserves_torch_rng():
    cfg=i.default_config("probe");rng=torch.get_rng_state().clone()
    identity=i.build_identity(cfg)
    assert torch.equal(rng,torch.get_rng_state())
    assert identity["architecture"]["token_count"]==81
    assert identity["foundation"]["extension_sha256"]==i.EXTENSION_SHA256
    assert any(name.endswith(".so") for name in identity["sources"])
    assert identity["config_sha256"]==i.identity_hash(cfg)


def test_raw_config_anchor_rejects_even_whitespace_replacement(tmp_path):
    path=tmp_path/"cfg.json";path.write_text(json.dumps(i.default_config("pilot")))
    expected=i.file_hash(path);assert t.read_config(path,expected)["phase"]=="pilot"
    path.write_text(path.read_text()+"\n")
    with pytest.raises(ValueError,match="document changed"):t.read_config(path,expected)


class FakePolicy(torch.nn.Module):
    def forward(self,g,e,types,mask):
        assert not torch.is_grad_enabled()
        return SimpleNamespace(logits=torch.zeros((len(g),9)),values=torch.zeros(len(g)))


class FakeEvalEnv:
    instances=[]
    def __init__(self,**cfg):
        self.cfg=cfg;self.seed=cfg["seeds_by_slot"][0][0];self.calls=0;self.done=False
        self.duration=(self.seed-0xD0000000)%3+1
        self.instances.append(self)
    def episode_info(self):
        return [{"seed":{"evaluation":True,"actual_seed":self.seed},"startup_frames":13}]
    def observations(self):
        return {"global_feats":np.zeros((1,1,14),np.float32),"entity_feats":np.zeros((1,80,16),np.float32),
                "entity_types":np.zeros((1,80),np.int64),"entity_mask":np.zeros((1,80),bool)}
    def step(self,actions):
        assert not self.done,"ended environment was stepped"
        self.calls+=1;self.done=self.calls==self.duration
        alive=self.calls-int(self.done)
        info={"seed":{"actual_seed":self.seed},"bootstrap":not self.done,"score_raw_fixed":0,
              "score_delta_sum_raw_fixed":0,"alive_frames":alive,"gameplay_frames":self.calls,
              "objective_return":alive/100-5*self.done}
        return {"info":[info],"terminated":np.array([self.done]),"truncated":np.array([False]),
                "observations":self.observations()}
    def reset_done(self,*args):raise AssertionError("Development evaluation must never reset")


def test_development_batches_alive_policies_and_never_steps_ended_slot():
    FakeEvalEnv.instances=[];model=FakePolicy();model.train()
    result=d.evaluate(model,"D1",env_factory=FakeEvalEnv)
    assert result["episodes"]==64 and result["deaths"]==64 and model.training
    assert [env.calls for env in FakeEvalEnv.instances]==[env.duration for env in FakeEvalEnv.instances]
    assert all(env.cfg["raw_frame_cap"]==2000 and env.cfg["patterns_enabled"] is False for env in FakeEvalEnv.instances)
    assert [row["seed"] for row in result["rows"]]==d.development_seeds()


@pytest.mark.parametrize("seed",[0xB0000000,0xE0000000,0xD0000040,-1])
def test_arbitrary_or_nonfirst64D_seed_rejected_before_construction(seed):
    with pytest.raises(ValueError,match="development D"):
        d.development_environment_config(seed,"D1")


def test_development_difficulty_flags_and_caps():
    for stage in ("D1","D2","D3"):
        cfg=d.development_environment_config(0xD0000000,stage)
        assert cfg["difficulty"]==int(stage[-1]) and cfg["powerups_enabled"]
        assert cfg["raw_frame_cap"]==(2000 if stage=="D1" else 18000)
        assert cfg["patterns_enabled"]==(stage!="D1")


def test_pilot_requires_strict_both_metric_improvement():
    from test_checkpoints import eval_result
    before=eval_result(1,500)
    assert d.pilot_improved(before,eval_result(2,600))
    assert not d.pilot_improved(before,eval_result(1,600))
    assert not d.pilot_improved(before,eval_result(2,500))
    assert not d.pilot_improved(before,eval_result(.5,700))


def test_summary_gate_rejects_posthoc_mean_tampering():
    from test_checkpoints import eval_result
    result=eval_result(9,1600);assert not d.progress_passed("D1",{"D1":result})
    result["mean_score"]=10
    with pytest.raises(ValueError,match="summary"):d.progress_passed("D1",{"D1":result})


def test_cutoff_arithmetic_full_budget_and_reserve():
    s.check_budget(datetime(2026,10,24,12,20,tzinfo=timezone.utc),1800)
    with pytest.raises(ValueError,match="reserve"):
        s.check_budget(datetime(2026,10,24,12,20,0,1,tzinfo=timezone.utc),1800)


def guard_fixture(tmp_path,monkeypatch,*,rss=100,mps=False):
    state=tmp_path/"state.json";state.write_text(json.dumps({"active_long_campaign":{
        "run_id":"run","identity_sha256":"id","config_sha256":"cfg",
        "kind":"M3_teacher","authorization":"frozen_reviewed_M3_teacher"}}))
    monkeypatch.setattr(s.time,"monotonic",lambda:0.)
    monkeypatch.setattr(s,"utc_now",lambda:datetime(2026,10,24,10,tzinfo=timezone.utc))
    monkeypatch.setattr(s,"current_rss_bytes",lambda pid:rss)
    monkeypatch.setattr(s,"peak_rss_bytes",lambda:100)
    stream=io.StringIO()
    guard=s.Guard(deadline=10,run_id="run",identity_sha256="id",config_sha256="cfg",stream=stream,
                  state_path=state,mps=mps)
    return guard,state,stream


def test_guard_checks_actual_lease_and_keeps_resource_series(tmp_path,monkeypatch):
    guard,state,stream=guard_fixture(tmp_path,monkeypatch);guard.check(force=True)
    assert json.loads(stream.getvalue())["rss_bytes"]==100
    data=json.loads(state.read_text());data["active_long_campaign"]["identity_sha256"]="other";state.write_text(json.dumps(data))
    with pytest.raises(ValueError,match="identity/config"):guard.check(force=True)


def test_guard_RSS_failure_retains_sample_before_exception(tmp_path,monkeypatch):
    guard,_,stream=guard_fixture(tmp_path,monkeypatch,rss=s.RSS_LIMIT+1)
    with pytest.raises(s.GuardStop,match="RSS"):guard.check(force=True)
    assert json.loads(stream.getvalue())["rss_bytes"]==s.RSS_LIMIT+1


def test_guard_MPS_limit_is_separate_from_RSS(tmp_path,monkeypatch):
    guard,_,stream=guard_fixture(tmp_path,monkeypatch,mps=True)
    monkeypatch.setattr(torch.mps,"driver_allocated_memory",lambda:s.RSS_LIMIT+1)
    with pytest.raises(s.GuardStop,match="MPS"):guard.check(force=True)
    sample=json.loads(stream.getvalue());assert sample["rss_bytes"]==100 and sample["mps_driver_bytes"]==s.RSS_LIMIT+1


def test_wall_and_cutoff_reject_before_new_work(tmp_path,monkeypatch):
    guard,_,_=guard_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(s.time,"monotonic",lambda:10.)
    with pytest.raises(s.GuardStop,match="wall"):guard.check()
    monkeypatch.setattr(s.time,"monotonic",lambda:0.)
    monkeypatch.setattr(s,"utc_now",lambda:s.CUTOFF)
    with pytest.raises(s.GuardStop,match="cutoff"):guard.check()


def test_streaming_proxy_retains_completed_native_work_before_collection_acceptance():
    stream=io.StringIO();counters={"environment_decisions":0,"raw_frames":0}
    info={"terminated":True,"truncated":False,"seed":{"actual_seed":100}}
    inner=SimpleNamespace(step=lambda a:{"info":[info],"elapsed_raw_frames":np.array([3])},
                          reset_done=lambda indices:{"info":[{"seed":{"actual_seed":101}}]})
    env=t.TrainingEnvLog(inner,counters,stream);env.step(np.array([0]));env.reset_done([0])
    records=[json.loads(line) for line in stream.getvalue().splitlines()]
    assert counters=={"environment_decisions":1,"raw_frames":3}
    assert [r["kind"] for r in records]==["native_completed_episode","native_reset"]


def test_training_batch_raw_diagnostics_cannot_be_omitted():
    with pytest.raises(ValueError,match="mandatory"):
        t.require_raw_diagnostics(SimpleNamespace(raw_rewards=None))


def test_same_phase_resume_cannot_restart_consumed_pilot_budget():
    cfg=i.default_config("pilot")
    used,left=t.remaining_phase_budget(cfg,{"run_context":{"consumed_wall_seconds":299.5}})
    assert used==299.5 and left==.5
    for value in (300,301,None,-1,float("nan")):
        with pytest.raises(ValueError):
            t.remaining_phase_budget(cfg,{"run_context":{"consumed_wall_seconds":value}})


def test_probe_selection_requires_equal_optimizer_work():
    rows=[{"device":"cpu","status":"completed","optimizer_steps":128,
           "metrics":{"epochs_completed":4},"measured_inference_plus_update_seconds":3},
          {"device":"mps","status":"completed","optimizer_steps":32,
           "metrics":{"epochs_completed":1},"measured_inference_plus_update_seconds":1}]
    assert t.choose_probe_device(rows)==("cpu",["mps"])
    rows[1]["optimizer_steps"]=128;rows[1]["metrics"]["epochs_completed"]=4
    assert t.choose_probe_device(rows)==("mps",[])


def test_frozen_identity_document_is_anchored_before_revalidation(tmp_path,monkeypatch):
    path=tmp_path/"identity.json";path.write_text(json.dumps({"x":1}));anchor=i.file_hash(path)
    monkeypatch.setattr(i,"build_identity",lambda cfg,root:{"x":1})
    assert i.check_frozen(path,anchor,{})=={"x":1}
    path.write_text(json.dumps({"x":2}))
    monkeypatch.setattr(i,"build_identity",lambda cfg,root:{"x":2})
    with pytest.raises(ValueError,match="document changed"):i.check_frozen(path,anchor,{})


def test_frozen_identity_rejects_current_source_change(tmp_path,monkeypatch):
    path=tmp_path/"identity.json";path.write_text(json.dumps({"sources":{"a":"old"}}));anchor=i.file_hash(path)
    monkeypatch.setattr(i,"build_identity",lambda cfg,root:{"sources":{"a":"new"}})
    with pytest.raises(ValueError,match="identity mismatch"):i.check_frozen(path,anchor,{})


def test_worker_rejects_extended_deadline_before_identity_or_execution(tmp_path,monkeypatch):
    path=tmp_path/"cfg.json";path.write_text(json.dumps(i.default_config("pilot")))
    args=SimpleNamespace(config=path,config_sha256=i.file_hash(path),phase="pilot",
                         consumed_wall_seconds=0,execution_started_monotonic=0,deadline_monotonic=1000)
    monkeypatch.setattr(t.time,"monotonic",lambda:1.)
    with pytest.raises(ValueError,match="registered consumed phase budget"):t.worker(args)


def test_cleanup_signal_exit_race_retains_receipt_without_broad_kill(monkeypatch):
    process=SimpleNamespace(pid=740001,returncode=None)
    process.poll=lambda:process.returncode
    def signal(pid,sig):
        assert pid==740001
        process.returncode=0
        raise ProcessLookupError("already exited")
    process.wait=lambda timeout:0
    monkeypatch.setattr(s.os,"killpg",signal)
    result=s.stop_owned(process)
    assert result["reaped"] and result["exit_signal_race"] and result["errors"]==[]


def test_cleanup_wait_failure_is_recorded_not_lost(monkeypatch):
    process=SimpleNamespace(pid=740002,poll=lambda:None)
    def wait(timeout):raise OSError("synthetic wait failure")
    process.wait=wait
    calls=[];monkeypatch.setattr(s.os,"killpg",lambda pid,sig:calls.append((pid,sig)))
    result=s.stop_owned(process)
    assert not result["reaped"] and len(result["errors"])==2
    assert all(pid==740002 for pid,_ in calls)


@pytest.mark.parametrize("late",[False,True])
def test_supervisor_checks_completed_worker_boundary_without_real_process(tmp_path,monkeypatch,late):
    cfg=tmp_path/"cfg.json";cfg.write_text(json.dumps(i.default_config("pilot")))
    identity=tmp_path/"id.json";identity.write_text('{}')
    args=SimpleNamespace(config=cfg,identity=identity,run_dir=tmp_path/"run",command="pilot",
                         run_id="test",resume_checkpoint=None,parent_checkpoint=None)
    clock=SimpleNamespace(now=0.)
    monkeypatch.setattr(t.time,"monotonic",lambda:clock.now)
    monkeypatch.setattr(s,"utc_now",lambda:datetime(2026,10,24,10,tzinfo=timezone.utc))
    monkeypatch.setattr(t,"utc_now",s.utc_now)
    monkeypatch.setattr(t,"verify_inputs",lambda *a:{})
    monkeypatch.setattr(t,"assert_lease",lambda *a:{})
    monkeypatch.setattr(s,"assert_lease",lambda *a:{})
    monkeypatch.setattr(s,"current_rss_bytes",lambda pid:100)
    monkeypatch.setattr(s,"peak_rss_bytes",lambda:100)
    class Process:
        pid=740003
        def __init__(self,*a,**kw):
            (args.run_dir/'worker-result.json').write_text(json.dumps({"status":"passed",
                 "identity_sha256":i.file_hash(identity),"config_sha256":i.file_hash(cfg)}))
        def poll(self):return 0
        def wait(self,timeout):
            if late:clock.now=301.
            return 0
    monkeypatch.setattr(t.subprocess,"Popen",Process)
    status=t.run_supervised(args)
    result=json.loads((args.run_dir/'run-result.json').read_text())
    assert status==(1 if late else 0)
    assert result['status']==('failed' if late else 'passed')
    assert result['automatic_retries']==0
    if late:assert 'wall guard' in result['error'] and result['owned_process_stop']['reaped']
