"""Real058 producers/archives/decoder with scripted CPU-only dummy boundaries."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import time
from types import SimpleNamespace

import numpy as np
import pytest
import torch

import common as c
from receipts import write_stage, write_archive, decode_archive
from worker import run_trajectory
from supervisor import supervise


def fixture_reg():
    jobs=[dict(id=name,arm='rays' if 'rays' in name else 'control',replica='1' if name.startswith('r1') else '2')
          for name in ('r1-control','r1-rays','r2-rays','r2-control')]
    return dict(record='DODGE-064',job_nonce='CPU-dummy-fixture',registration_sha256='a'*64,payload_sha256='b'*64,
        jobs=jobs,envs=1,rollout=1,updates=3,frame_target=3,total_actual_frames=12,
        effective_minibatch=1,microbatch=1,checkpoint_updates=[1,2,3],prefix_updates=2,
        work_seconds=10,receipt_seconds=.1,campaign_total_seconds=100,IO_reserve_seconds=0,
        rss_bytes=6*1024**3,cuda_driver_bytes=6*1024**3,campaign_started_monotonic=time.monotonic(),
        arms={arm:dict(gamma=.99,gae_lambda=.90) for arm in ('control','rays')},
        ppo=dict(update_epochs=1,learning_rate=3e-5,target_kl=.03,reward_scale=.1))


class DummySession:
    """No model/environment: script one boundary into the REAL metric writer."""
    fixture_only=True
    stream_digest='CPU-fixture-no-seed-pool'
    def __init__(self,reg,job,out,guard):
        from update_telemetry import Recorder, JsonlSink
        from dodge_rl import ppo
        self.reg,self.job,self.out,self.n=reg,job,out,0
        self.ppo=ppo;self.recorder=Recorder(job['id'],1);self.sink=JsonlSink(out/'updates.jsonl')
        self.adapter=SimpleNamespace(completed_updates=0,env=Boundary())
        self.config=ppo.PPOConfig(gamma=.99,gae_lambda=.90,update_epochs=1,minibatch_size=1,learning_rate=3e-5)
        self.effective_minibatch_size=self.microbatch_size=1

    def step(self,update,guard):
        from update_telemetry import instrument_update
        result=instrument_update(self,self.ppo,self.recorder,self.sink,resource_snapshot=self.resources,check_guard=guard)
        return dict(passive_GAE_return_identity=True,**self.counts())

    def update_once(self,check_guard=None):
        if check_guard:check_guard()
        self.adapter.env.step(np.array([0],dtype=np.int64))
        values=torch.zeros(1,1);rewards=torch.tensor([[.001]],dtype=torch.float32)
        terminated=truncated=torch.zeros(1,1,dtype=torch.bool)
        self.ppo.compute_gae(rewards,values,values,terminated,truncated,.99,.90)
        batch=SimpleNamespace(actions=torch.zeros(1,1,dtype=torch.int64),values=values,
            raw_rewards=torch.tensor([[.01]],dtype=torch.float32),rewards=rewards,
            score_delta_raw_fixed=torch.zeros(1,1,dtype=torch.int64),alive_raw_frames=torch.ones(1,1,dtype=torch.int64),
            terminated=terminated,elapsed_raw_frames=torch.ones(1,1,dtype=torch.int64))
        metrics=dict(epochs_completed=1,epoch_approx_kls=[.001],optimizer_steps=1,early_stop_kl=False,
            approx_kl=.001,entropy=1.,value_loss=.01,clip_fraction=0.,explained_variance=None,transitions=1)
        self.n+=1;self.adapter.completed_updates=self.n
        return SimpleNamespace(batch=batch),metrics,dict(completed_updates=self.n)

    def resources(self):return dict(peak_rss_bytes=1024,peak_cuda_reserved_bytes=0,peak_cuda_allocated_bytes=0)
    def counts(self):return dict(training_frames=self.recorder.frames,completed_updates=self.n,native_games=0)
    def checkpoint(self,path,update):
        # Fixture bytes are not Torch weights. Production uses LiveSession's writer.
        c.publish(path,lambda f:f.write(b'CPU fixture checkpoint placeholder'))
        return dict(update=update,filename=path.name,sha256=c.sha(path))
    def failure(self,error):return dict(collection_status='interrupted_before_return',collected_valid_vectors=None)
    def close(self):self.sink.close()


class Boundary:
    """Scripted metadata only, no engine/physics/future simulation or seed use."""
    def __init__(self):self.n=0
    def batch_info(self):return dict(action_repeat=1)
    def episode_info(self):
        return [dict(seed=dict(slot=0,episode=0,actual_seed=0),gameplay_frames=self.n,terminated=False,truncated=False)]
    def step(self,actions):
        self.n+=1
        return dict(elapsed_raw_frames=np.array([1],dtype=np.int64),info=self.episode_info())


def produce_fixture_tree(root,reg):
    for job in reg['jobs']:
        out=root/'outputs'/job['id']
        result=run_trajectory(reg,job,out,DummySession)
        assert result['status']=='complete',result
        # REAL supervisor receives a real subprocess exit; it never fabricates
        # the worker body. Log/claim files are created by the actual supervisor.
        supervised=supervise([sys.executable,'-B','-c','pass'],out,reg,job,check_control=lambda:None,
            resource_probe=live_dummy,GPU_probe=lambda _:0,exit_probe=lambda child:child.poll() is not None,
            qualified_linux=False,sample_seconds=.01)
        assert supervised['status']=='complete',supervised
    write_stage(root/'campaign-result.json',reg,'campaign','complete',native_games=0,
        training_frames=12,trained_weights_saved=True,elapsed_seconds=.1,fixture_only=True)


def live_dummy(pid):
    # Mac CPU fixture only: match Linux probe's exclusion of exited zombies.
    result=subprocess.run(['/bin/ps','-p',str(pid),'-o','stat='],capture_output=True,text=True)
    if result.returncode or not result.stdout.strip() or result.stdout.strip().startswith('Z'):return {}
    return {pid:1024}


def test_real_writers_logs_claims_archive_and_real_decoder(tmp_path):
    reg=fixture_reg();root=tmp_path/'artifacts';root.mkdir()
    produce_fixture_tree(root,reg)
    archive=write_archive(root,tmp_path/'artifacts.tar',reg)
    decoded=decode_archive(archive['path'],archive['sha256'],reg,allow_fixtures=True)
    assert decoded['checkpoint_files']==12
    with pytest.raises(ValueError,match='fixture cannot qualify'):
        decode_archive(archive['path'],archive['sha256'],reg)


def test_actual_worker_missing_savedweight_field_is_not_masked(tmp_path):
    reg=fixture_reg();root=tmp_path/'artifacts';root.mkdir();produce_fixture_tree(root,reg)
    path=root/'outputs/r1-control/worker-result.json';value=c.read(path);del value['trained_weights_saved']
    path.write_text(json.dumps(value))  # Deliberate wire corruption AFTER real production.
    archive=write_archive(root,tmp_path/'bad.tar',reg)
    with pytest.raises(ValueError,match='Missing required stage field'):
        decode_archive(archive['path'],archive['sha256'],reg,allow_fixtures=True)


def test_partial_collection_does_not_reuse_successful_counts(tmp_path):
    class Interrupted(DummySession):
        def update_once(self,check_guard=None):
            if self.n==1:
                self.adapter.env.step(np.array([0],dtype=np.int64))
                raise RuntimeError('CPU interruption after returned boundary, before collection return')
            return super().update_once(check_guard)
    reg=fixture_reg();out=tmp_path/'out';body=run_trajectory(reg,reg['jobs'][0],out,Interrupted)
    assert body['status']=='failed' and body['training_frames']==2 and body['completed_updates']==1
    assert body['partial_observations']['collected_valid_vectors'] is None
    assert body['trained_weights_saved'] is True  # The earlier fixture snapshot is retained.
    assert (out/'worker-first-failure.json').exists() and not (out/'worker-result.json').exists()
    rows=[json.loads(line) for line in (out/'updates.jsonl').read_text().splitlines()]
    assert [row['kind'] for row in rows]==['update_complete','update_failure']
    assert rows[-1]['partial_gameplay_frames']==1


def test_explicit_CUDA_zero_index_uses_real_torch_index_parser():
    from torch.cuda._utils import _get_device_index
    assert _get_device_index(torch.device('cuda',0))==0


def test_ELF_certificate_rejects_MachO_and_wrong_machine(tmp_path):
    from native_build import require_ELF_x86_64
    path=tmp_path/'binary';path.write_bytes(b'\xcf\xfa\xed\xfe'+b'\0'*60)
    with pytest.raises(ValueError,match='ELF'):require_ELF_x86_64(path)
    header=bytearray(64);header[:6]=b'\x7fELF\x02\x01';header[16:20]=struct.pack('<HH',3,62)
    path.write_bytes(header);require_ELF_x86_64(path)
    header[18:20]=struct.pack('<H',183);path.write_bytes(header)
    with pytest.raises(ValueError,match='x86_64'):require_ELF_x86_64(path)


@pytest.mark.parametrize('fault',['wall','resource','cancel','child_failure','driver_probe'])
def test_real_dummy_supervisor_failure_is_reaped_and_preserved(tmp_path,fault):
    reg=fixture_reg();reg['receipt_seconds']=.05
    command=[sys.executable,'-B','-c','import time;time.sleep(2)']
    probe=live_dummy;guard=lambda:None
    if fault=='wall':reg['work_seconds']=.03
    if fault=='resource':reg['rss_bytes']=1
    if fault=='cancel':
        def guard():raise ValueError('Expired lease/control heartbeat')
    if fault=='child_failure':command=[sys.executable,'-B','-c','raise SystemExit(7)']
    def gpu(_):
        if fault=='driver_probe':raise RuntimeError('Driver memory meter unavailable')
        return 0
    result=supervise(command,tmp_path,reg,reg['jobs'][0],check_control=guard,
        resource_probe=probe,GPU_probe=gpu,exit_probe=lambda child:child.poll() is not None,
        qualified_linux=False,sample_seconds=.01)
    assert result['status']=='failed' and result['training_frames'] is None
    assert result['trained_weights_saved'] is None  # Unknown, not synthetic false.
    assert (tmp_path/'supervisor-first-failure.json').exists()


def test_heartbeat_mismatch_expiry_and_stage_control(tmp_path,monkeypatch):
    reg=fixture_reg();reg['expected_lease_sha256']='c'*64
    monkeypatch.setattr(c,'HERE',tmp_path);monkeypatch.setenv('DODGE064_EXECUTION_ADMITTED','true')
    control={key:reg[key] for key in ('record','job_nonce','registration_sha256','expected_lease_sha256')}
    monkeypatch.setattr(c,'_LAST_CONTROL',None)
    control.update(issued_at_utc=time.time()-1,expires_at_utc=time.time()+30,sequence=1,allowed_stage='build')
    (tmp_path/'control.json').write_text(json.dumps(control));c.check_lease(reg)
    control['expires_at_utc']=time.time()-1;(tmp_path/'control.json').write_text(json.dumps(control))
    with pytest.raises(ValueError,match='expired'):c.check_lease(reg)


def test_control_sequence_replay_and_training_admission_binding(tmp_path,monkeypatch):
    reg=fixture_reg();reg['expected_lease_sha256']='c'*64
    monkeypatch.setattr(c,'HERE',tmp_path);monkeypatch.setattr(c,'_LAST_CONTROL',None)
    monkeypatch.setenv('DODGE064_EXECUTION_ADMITTED','true')
    control={key:reg[key] for key in ('record','job_nonce','registration_sha256','expected_lease_sha256')}
    control.update(issued_at_utc=time.time()-1,expires_at_utc=time.time()+30,sequence=1,allowed_stage='build')
    def publish():(tmp_path/'control.json').write_text(json.dumps(control))
    publish();c.check_lease(reg)
    control['expires_at_utc']+=1;publish()
    with pytest.raises(ValueError,match='Same control sequence'):c.check_lease(reg)
    (tmp_path/'runtime-admission.json').write_text('{"CPU_fixture_only":true}')
    control.update(sequence=2,allowed_stage='train',runtime_admission_sha256=c.sha(tmp_path/'runtime-admission.json'))
    publish();c.check_lease(reg)
    control['sequence']=1;publish()
    with pytest.raises(ValueError,match='sequence reversed'):c.check_lease(reg)


def test_pinned_TEXT_launcher_forwards_real_program_argv(tmp_path,monkeypatch):
    import stage_launcher
    source=tmp_path/'source';source.mkdir()
    (source/'remote_entry.py').write_text(
        "import argparse,json,os\nfrom pathlib import Path\n"
        "p=argparse.ArgumentParser();p.add_argument('--registration');p.add_argument('--sha256');p.add_argument('--stage')\n"
        "a=p.parse_args();root=Path(os.environ['DODGE064_RUN_ROOT']);(root/'seen.json').write_text(json.dumps(vars(a)));(root/'build-artifacts.tar').write_bytes(b'CPU-fixture')\n")
    registration=tmp_path/'registration.json';registration.write_text(json.dumps({'stage_timeout_seconds':{'build':3}}))
    monkeypatch.setattr(stage_launcher,'Path',lambda value:tmp_path if str(value)=='/content/dodge064' else Path(value))
    monkeypatch.setenv('DODGE064_STAGE','build');monkeypatch.setenv('DODGE064_EXECUTION_ADMITTED','true')
    monkeypatch.setenv('DODGE064_REGISTRATION_SHA256',c.sha(registration))
    reg=fixture_reg();reg.update(job_nonce='c047a883-3cfa-4362-86b6-f22fdbcb71a1',expected_lease_sha256='c'*64,stage_timeout_seconds={'build':3})
    monkeypatch.setattr(c,'load_registration',lambda path,digest:dict(reg,registration_sha256=digest))
    monkeypatch.setattr(c,'check_lease',lambda reg:None)
    stage_launcher.main()
    assert c.read(tmp_path/'exports/build-exit.json')['directly_reaped'] is True
    assert c.read(tmp_path/'seen.json')==dict(registration=str(registration),sha256=c.sha(registration),stage='build')


def test_launcher_timeout_keeps_cancellation_and_reaps_dummy(tmp_path,monkeypatch):
    import stage_launcher
    source=tmp_path/'source';source.mkdir()
    (source/'remote_entry.py').write_text('import time;time.sleep(2)')
    registration=tmp_path/'registration.json';registration.write_text(json.dumps({'stage_timeout_seconds':{'build':.03}}))
    monkeypatch.setattr(stage_launcher,'Path',lambda value:tmp_path if str(value)=='/content/dodge064' else Path(value))
    monkeypatch.setenv('DODGE064_STAGE','build');monkeypatch.setenv('DODGE064_EXECUTION_ADMITTED','true')
    monkeypatch.setenv('DODGE064_REGISTRATION_SHA256',c.sha(registration))
    reg=fixture_reg();reg.update(job_nonce='c047a883-3cfa-4362-86b6-f22fdbcb71a1',expected_lease_sha256='c'*64,stage_timeout_seconds={'build':.03})
    monkeypatch.setattr(c,'load_registration',lambda path,digest:dict(reg,registration_sha256=digest))
    monkeypatch.setattr(c,'check_lease',lambda reg:None)
    with pytest.raises(RuntimeError,match='durable receipt preserved'):stage_launcher.main()
    assert c.read(tmp_path/'exports/build-exit.json')['status']=='failed'
    assert c.read(tmp_path/'exports/build-exit.json')['owned_group_absent'] is True
    assert (tmp_path/'cancel.requested').exists()


def test_generic_partial_artifact_survives_failure_archive(tmp_path):
    root=tmp_path/'artifacts';root.mkdir();(root/'worker-result.json.partial').write_text('{')
    archive=write_archive(root,tmp_path/'partial.tar',fixture_reg())
    result=decode_archive(archive['path'],archive['sha256'],fixture_reg(),require_complete=False)
    assert result['failed_paths']==['worker-result.json.partial']


def test_actual_prepared_update_resets_collection_fields_before_interruption():
    from worker import PreparedUpdates,failure_observations
    adapter=SimpleNamespace(env=object(),completed_updates=0,gameplay_frames=0,observed_native_steps=0)
    adapter.begin_update=lambda update:None
    def finish():
        adapter.completed_updates+=1;return dict(completed_updates=adapter.completed_updates)
    adapter._finish_after_ppo=finish
    def collect(*args,check_guard=None,**kwargs):
        for _ in range(2):
            adapter.gameplay_frames+=64;adapter.observed_native_steps+=1
            if check_guard:check_guard()
        return SimpleNamespace(batch=SimpleNamespace(actions=SimpleNamespace(shape=(2,64),numel=lambda:128)))
    ppo=SimpleNamespace(collect_rollout=collect,ppo_update=lambda *args,**kwargs:{})
    config=SimpleNamespace(learning_rate=3e-5,adam_eps=1e-5)
    optimizer=SimpleNamespace(param_groups=[dict(lr=3e-5,eps=1e-5)])
    prepared=PreparedUpdates(None,optimizer,adapter,config,ppo,
        dict(microbatch=512,effective_minibatch=2048,rollout=1024,frame_target=2359296),'cpu')
    prepared.update_once();assert prepared.collected_valid_vectors==2
    def interrupt():raise KeyboardInterrupt('CPU returned-vector fixture')
    with pytest.raises(KeyboardInterrupt):prepared.update_once(interrupt)
    result=failure_observations(prepared)
    assert result['attempted_update']==2 and result['observed_returned_frames_this_attempt']==64
    assert result['observed_returned_vectors_this_attempt']==1
    assert result['collected_valid_vectors'] is result['collected_valid_transitions'] is None


def test_stale_runtime_cache_rejected_before_any_import(tmp_path,monkeypatch):
    from native_build import verify_certificate,SOURCE_ROOT,inventory
    monkeypatch.setattr(c,'HERE',tmp_path)
    runtime=tmp_path/'runtime';runtime.mkdir();(runtime/'module.py').write_text('pass')
    (tmp_path/'artifacts').mkdir()
    reg=fixture_reg();reg['runtime_root']=str(runtime)
    write_stage(tmp_path/'artifacts/native-build.json',reg,'native_build','complete',
        native_games=0,training_frames=0,trained_weights_saved=False,runtime_members=inventory(runtime),
        engine_source_manifest_sha256=c.sha(SOURCE_ROOT/'native_source_manifest.json'))
    (runtime/'__pycache__').mkdir();(runtime/'__pycache__/stale.pyc').write_bytes(b'CPU fixture')
    with pytest.raises(ValueError,match='Runtime inventory changed'):verify_certificate(reg)


@pytest.mark.parametrize('fault',['complete','deadline','RSS'])
def test_real_setup_command_guard_without_build_or_native(tmp_path,monkeypatch,fault):
    import build_process
    monkeypatch.setattr(c,'check_lease',lambda reg:None)
    reg=fixture_reg();code='pass' if fault=='complete' else 'import time;time.sleep(2)'
    if fault=='RSS':reg['rss_bytes']=1
    call=lambda:build_process.run([sys.executable,'-B','-c',code],reg=reg,cwd=tmp_path,
        env=dict(os.environ),stdout=tmp_path/'setup.stdout',stderr=tmp_path/'setup.stderr',
        deadline=time.monotonic()+(.01 if fault=='deadline' else 5),resource_probe=live_dummy,
        exit_probe=lambda child:child.poll() is not None)
    if fault=='complete':call()
    else:
        with pytest.raises(ValueError):call()


def test_real_source_bundle_and_TEXT_unpack_allow_preexisting_inputs_only(tmp_path,monkeypatch):
    from bundle import write
    import unpack_launcher
    root=tmp_path/'remote';root.mkdir();(root/'inputs').mkdir();(root/'control.json').write_text('{}')
    vendor=tmp_path/'vendor-input';vendor.mkdir();(vendor/'fixture.rs').write_text('// CPU source fixture')
    archive=write(root/'source-input.tar',vendor)
    registration=root/'registration.json'
    registration.write_text(json.dumps(dict(record='DODGE-064',accelerator='A100',job_nonce='CPU-source-fixture',payload_sha256=archive['sha256'])))
    monkeypatch.setattr(unpack_launcher,'Path',lambda path:root if str(path)=='/content/dodge064' else Path(path))
    monkeypatch.setenv('DODGE064_REGISTRATION_SHA256',c.sha(registration))
    unpack_launcher.main()
    result=c.read(root/'source-assembly.json')
    assert result['native_games']==result['training_frames']==0 and result['trained_weights_saved'] is False
    assert (root/'source/remote_entry.py').is_file() and (root/'vendor/fixture.rs').is_file()
    with pytest.raises(ValueError,match='Consumed/old058'):unpack_launcher.main()
