"""Exercise real worker publication and terminal audit with synthetic runtime/collector only."""
from __future__ import annotations
import hashlib
import subprocess
import ast
import json
import tempfile
import time,sys
from types import SimpleNamespace
from pathlib import Path
import binding as b
import screen
import terminal
import worker
import audit
import death_telemetry


class FakeRandom:
    def seed(self, _seed): pass
class FakeNumpy:
    random=FakeRandom()
class FakeMPS:
    def manual_seed(self, _seed): pass
    def driver_allocated_memory(self): return 0
    def empty_cache(self): pass
class FakeTorch:
    mps=FakeMPS()
    def manual_seed(self, _seed): pass
    def is_grad_enabled(self): return True
class FakeCheckpoints:
    def capture_rng(self, _backend): return {'state':'stable'}
    def restore_rng(self, _state, _backend): pass
class FakeModel:
    def state_dict(self): return {'weights':'frozen'}


def fake_row(index, seed, repeat):
    contacts={cause:0 for cause in screen.DEATH_CAUSES[:-1]};contacts['unknown']=1
    score_raw=(index+1)*65536
    return dict(episode_index=index,seed=seed,score_raw_fixed=score_raw,
        score_delta_sum_raw_fixed=score_raw,alive_frames=3,gameplay_frames=4,
        startup_frames=13,raw_frames=17,action_repeat=repeat,policy_decisions=4//repeat,
        episode_latency_ns=1000,terminated=True,truncated=False,death_cause='unknown',
        fatal_gameplay_frame=4,death_observed_lethal_contacts=contacts,score=score_raw/65536,
        objective_return=score_raw/65536+3/100-5)


def fake_collector(model, env_factory, observation_keys, death_fields, seeds, excluded, guard,
                   *, action_repeat, action_mode, batch_size, event_sink):
    rows=[]
    for index,seed in enumerate(seeds):
        guard()
        info=dict(seed=dict(evaluation=True,actual_seed=seed),startup_frames=13,gameplay_frames=0)
        event_sink(dict(kind='constructor',episode_index=index,info=info))
        for _ in range(4//action_repeat):
            guard();event_sink(dict(kind='step',episode_index=index,elapsed_raw_frames=action_repeat,info={}))
        row=fake_row(index,seed,action_repeat);rows.append(row)
        event_sink(dict(kind='completed',row=row))
    return rows


def test_registered_interpreter_is_project_venv_without_imports():
    reg=b.read(b.HERE/'registration-draft.json');interpreter=Path(reg['interpreter'])
    expected=b.ROOT/'python/.venv/bin/python'
    assert interpreter==expected and interpreter.resolve().is_file()
    code='import importlib.util,json,sys;print(json.dumps(dict(prefix=sys.prefix,numpy=importlib.util.find_spec(\"numpy\") is not None,torch=importlib.util.find_spec(\"torch\") is not None)))'
    proc=subprocess.run([str(interpreter),'-B','-c',code],capture_output=True,text=True,check=True,env={**__import__('os').environ,'PYTHONDONTWRITEBYTECODE':'1'})
    data=json.loads(proc.stdout)
    assert Path(data['prefix']).resolve()==(b.ROOT/'python/.venv').resolve() and data['numpy'] and data['torch']


def test_local_death_helper_has_no_legacy_imports():
    assert 'expanded_eval' not in sys.modules and 'contracts' not in sys.modules
    root=Path(__file__).resolve().parents[4]
    old=ast.parse((root/'learning/runs/v2/fullgame-seed-priority-experiment-luna-20261027-r3/death_telemetry.py').read_text())
    new=ast.parse((Path(__file__).parent/'death_telemetry.py').read_text())
    extract=lambda tree: next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='death_fields')
    assert ast.dump(extract(old),include_attributes=False)==ast.dump(extract(new),include_attributes=False)


def test_audit_uses_observer_control_path():
    old=b.HERE
    try:
        with tempfile.TemporaryDirectory(prefix='dodge-control-audit-path-') as temp:
            b.HERE=Path(temp);reg={'run_id':'synthetic-run'}
            envelope={'control':str(Path(temp)/'dispatch'/'synthetic-run')}
            assert audit.observer_execution_result_path(envelope,reg).resolve()==(Path(temp)/'dispatch'/'synthetic-run'/'execution-result.json').resolve()
    finally:b.HERE=old


def test_worker_then_terminal():
    protocol=b.PROTOCOL;seeds=protocol['seeds'];order=protocol['order']
    with tempfile.TemporaryDirectory(prefix='dodge-control-screen-e2e-') as temp:
        root=Path(temp);checkpoint=root/'checkpoint.pt';checkpoint.write_bytes(b'synthetic test bytes')
        checkpoint_sha=hashlib.sha256(checkpoint.read_bytes()).hexdigest();out=root/'worker-output';claim=root/'attempt.claimed'
        reg=dict(run_id='synthetic-run',output=str(out),attempt_claim_path=str(claim),limits=dict(protocol['limits']),
            condition_limits=dict(protocol['condition_limits']),order=order,condition_map=b.CONDITION_MAP,
            controller_seeds=protocol['controller_seeds'],checkpoint_path=str(checkpoint),checkpoint_sha256=checkpoint_sha,
            model_fingerprint='f'*64,evaluation_exclusions=protocol['evaluation_exclusions'],batch_size=64,
            backend='mps',neural_inputs=list(screen.NEURAL_INPUTS),runtime_manifest_sha256='a'*64,
            seeds=seeds,bootstrap=dict(seed=protocol['statistics']['bootstrap']['seed'],draws=12,
                contrasts=protocol['statistics']['contrasts']))
        envelope=dict(started=time.monotonic(),registration_sha256='b'*64)
        fake_torch=FakeTorch();fake_checkpoints=FakeCheckpoints();model=FakeModel()
        fingerprint=lambda _value:'f'*64
        def fake_auth(_reg):
            sys.modules['death_telemetry']=SimpleNamespace(death_fields=lambda *a: {})
            return FakeNumpy(),fake_torch,SimpleNamespace(VecDodgeEnv=object),fake_checkpoints,object()
        patches=[(worker.b,'load_envelope',lambda path,digest:(envelope,reg)),
            (worker.b,'verify_bound',lambda *a,**k:None),(worker.b,'check_lease',lambda _reg:None),
            (worker,'authenticate_runtime',fake_auth),
            (worker,'load_fingerprint_helper',lambda _reg:fingerprint),
            (worker,'load_frozen_policy',lambda *a:model),
            (worker.screen,'_production_rows',fake_collector)]
        saved=[]
        for obj,name,value in patches:
            saved.append((obj,name,getattr(obj,name)));setattr(obj,name,value)
        try:
            assert worker.run('unused-envelope','c'*64)==0
            result=b.read(out/'worker-result.json')
            report=terminal.validate_outputs(reg,result,envelope['registration_sha256'])
            assert report['episodes']==2048 and report['native_steps']==sum(4//b.CONDITION_MAP[g['condition']]['action_repeat']*256 for g in order)
            stored=b.read(out/'comparison.json')
            assert stored['comparison_elapsed_seconds']==result['comparison_elapsed_seconds']
            assert result['comparison_elapsed_seconds']<=result['elapsed_seconds']
        finally:
            for obj,name,value in reversed(saved):setattr(obj,name,value)


if __name__=='__main__':
    test_registered_interpreter_is_project_venv_without_imports();test_local_death_helper_has_no_legacy_imports();test_audit_uses_observer_control_path();test_worker_then_terminal();print('synthetic worker-to-terminal test passed')
