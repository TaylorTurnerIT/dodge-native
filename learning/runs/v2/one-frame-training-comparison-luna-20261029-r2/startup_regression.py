"""Bounded CPU regression for observer-to-child dispatch; fixture only."""
from __future__ import annotations

import hashlib
import ast
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

import binding as candidate_binding
import observe as candidate_observe
import terminal as candidate_terminal


ROOT = Path(__file__).resolve().parents[4]
R6 = ROOT/'learning/runs/v2/one-frame-training-comparison-luna-20261029-r1'
CHILD_SOURCE = '''import json, os, sys
from pathlib import Path
out = Path(os.environ['STARTUP_REGRESSION_OUTPUT'])
Path(os.environ['STARTUP_REGRESSION_STARTED']).write_text('dummy child started\\n')
(out/'worker-result.json').write_text(json.dumps({'status':'dummy_completed','fixture_only':True})+'\\n')
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fixture(root):
    root=Path(root)
    root.mkdir(parents=True,exist_ok=True)
    out=root/'worker-output'; out.mkdir()
    cache=root/'empty-pycache'; cache.mkdir()
    control=root/'dispatch'/'startup-repair-cpu-fixture'; control.parent.mkdir()
    reg=dict(phase='qualification',run_id='startup-repair-cpu-fixture',output=str(out),
        execution_root=str(root),runtime_root=str(root),
        import_policy={'pycache_prefix':str(cache)},
        limits={'work_seconds':10,'total_seconds':20,'cleanup_seconds':2,
            'postflight_seconds':3,'rss_bytes':2**30,'mps_bytes':2**30})
    reg_path=root/'registration.json'
    reg_path.write_text(json.dumps(reg,sort_keys=True)+'\n')
    reg_sha=sha(reg_path)
    env=dict(phase='qualification',run_id=reg['run_id'],registration=str(reg_path.resolve()),
        registration_sha256=reg_sha,pins={str(reg_path.resolve()):reg_sha},
        control=str(control.resolve()),cancel_path=str(root/'cancel'),started=time.monotonic())
    env_path=root/'launch-envelope.json'
    env_path.write_text(json.dumps(env,sort_keys=True)+'\n')
    return reg,env_path,sha(env_path),control,out,cache


def write_dummy(child_dir):
    child_dir=Path(child_dir); child_dir.mkdir(parents=True,exist_ok=True)
    (child_dir/'worker.py').write_text(CHILD_SOURCE,encoding='utf-8')


def verify_source_spine():
    binding_tree=ast.parse((Path(__file__).parent/'binding.py').read_text())
    helpers=[node for node in binding_tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))
        and node.name=='worker_command']
    assert len(helpers)==1,f'expected one worker_command definition, found {len(helpers)}'
    args=helpers[0].args
    names=[item.arg for item in args.posonlyargs+args.args]
    assert names==['envelope'] and not args.vararg and not args.kwarg,names
    observe_tree=ast.parse((Path(__file__).parent/'observe.py').read_text())
    calls=[node for node in ast.walk(observe_tree) if isinstance(node,ast.Call)
        and isinstance(node.func,ast.Attribute) and node.func.attr=='worker_command']
    assert (len(calls)==1 and len(calls[0].args)==1 and not calls[0].keywords), \
        'observer must call the accepted one-argument helper exactly once'
    return dict(helper_definitions=1,helper_positional_args=names,
        observer_call_positional_args=1,observer_call_count=1)


def install_fixture_gates(binding, terminal):
    return (
        patch.object(binding,'verify_bound',return_value=None),
        patch.object(binding,'check_lease',return_value=None),
        patch.object(terminal,'validate_qualification_outputs',
                     return_value={'fixture_only':True,'resource_qualified':False}),
        patch.object(terminal,'qualification_accounting',
                     return_value={'fixture_only':True,'resource_qualified':False}),
    )


def exercise_candidate(tmp):
    reg,env_path,env_sha,control,out,cache=fixture(tmp)
    child_dir=Path(tmp)/'dummy-command-source'; write_dummy(child_dir)
    started=Path(tmp)/'dummy-child-started'
    previous_here=candidate_binding.HERE
    previous_root=candidate_binding.ROOT
    previous_output=os.environ.get('STARTUP_REGRESSION_OUTPUT')
    previous_started=os.environ.get('STARTUP_REGRESSION_STARTED')
    candidate_binding.HERE=child_dir
    candidate_binding.ROOT=ROOT
    os.environ['STARTUP_REGRESSION_OUTPUT']=str(out)
    os.environ['STARTUP_REGRESSION_STARTED']=str(started)
    gates=install_fixture_gates(candidate_binding,candidate_terminal)
    try:
        with gates[0],gates[1],gates[2],gates[3]:
            rc=candidate_observe.main(str(env_path),env_sha)
    finally:
        candidate_binding.HERE=previous_here
        candidate_binding.ROOT=previous_root
        for name,value in (('STARTUP_REGRESSION_OUTPUT',previous_output),
                           ('STARTUP_REGRESSION_STARTED',previous_started)):
            if value is None: os.environ.pop(name,None)
            else: os.environ[name]=value
    observation=json.loads((control/'observation.json').read_text())
    if rc != 0:
        log=(control/'worker.log').read_text() if (control/'worker.log').is_file() else ''
        raise AssertionError({'rc':rc,'observation':observation,'worker_log':log})
    launch=json.loads((control/'worker-launch.json').read_text())
    final=json.loads((control/'observer-finalization.json').read_text())
    command=launch['command']
    assert rc==0,observation
    assert observation['status']=='completed_pending_parent_audit',observation
    assert observation['actual_worker_launch_count']==1,observation
    assert observation['directly_reaped'] is True and observation['owned_group_absent'] is True,observation
    assert observation['observed_worker_raw_exit']==0,observation
    assert final['status']=='completed_pending_parent_audit' and final['deadline_consumed'] is False,final
    assert started.is_file(), 'dummy child did not start'
    assert json.loads((out/'worker-result.json').read_text())=={
        'status':'dummy_completed','fixture_only':True}
    assert Path(command[2]).resolve()==(child_dir/'worker.py').resolve(),command
    assert command[1]=='-B' and command[3:]==[
        '--envelope',str(env_path.resolve()),'--envelope-sha256',env_sha],command
    assert cache.is_dir() and not any(cache.iterdir()),'fixture bytecode cache changed'
    return dict(result='pass',raw_exit=observation['observed_worker_raw_exit'],
        direct_reap=observation['directly_reaped'],owned_group_absent=observation['owned_group_absent'],
        child_marker_sha256=sha(started),observer_receipt_sha256=sha(control/'observation.json'),
        command_builder='candidate binding.worker_command(envelope)',
        fixture_gates=['verify_bound','check_lease','qualification output validation',
                       'qualification accounting'],
        runtime_qualification=False)


def frozen_r6_modules():
    names=('binding','execute_once','terminal','observe')
    saved={name:sys.modules.pop(name,None) for name in names}
    saved_path=list(sys.path)
    sys.path.insert(0,str(R6))
    try:
        modules={name:importlib.import_module(name) for name in names}
    finally:
        for name in names: sys.modules.pop(name,None)
        for name,module in saved.items():
            if module is not None: sys.modules[name]=module
        sys.path[:]=saved_path
    return modules


def exercise_frozen_negative(tmp):
    modules=frozen_r6_modules()
    binding=modules['binding']; observe=modules['observe']; terminal=modules['terminal']
    reg,env_path,env_sha,control,out,cache=fixture(tmp)
    child_dir=Path(tmp)/'dummy-command-source'; write_dummy(child_dir)
    started=Path(tmp)/'dummy-child-started'
    previous_here=binding.HERE; previous_root=binding.ROOT
    previous_output=os.environ.get('STARTUP_REGRESSION_OUTPUT')
    previous_started=os.environ.get('STARTUP_REGRESSION_STARTED')
    binding.HERE=child_dir; binding.ROOT=ROOT
    os.environ['STARTUP_REGRESSION_OUTPUT']=str(out)
    os.environ['STARTUP_REGRESSION_STARTED']=str(started)
    gates=install_fixture_gates(binding,terminal)
    try:
        with gates[0],gates[1],gates[2],gates[3]:
            rc=observe.main(str(env_path),env_sha)
    finally:
        binding.HERE=previous_here; binding.ROOT=previous_root
        for name,value in (('STARTUP_REGRESSION_OUTPUT',previous_output),
                           ('STARTUP_REGRESSION_STARTED',previous_started)):
            if value is None: os.environ.pop(name,None)
            else: os.environ[name]=value
    observation=json.loads((control/'observation.json').read_text())
    assert rc==1,observation
    assert observation['actual_worker_launch_count']==0,observation
    assert observation['worker_ownership_state']=='not_launched',observation
    assert observation['first_event']['kind']=='observer_failure',observation
    assert observation['first_event']['error']==(
        "TypeError('worker_command() takes 1 positional argument but 2 were given')"),observation
    assert not started.exists(),'frozen two-argument call launched dummy child'
    assert not (control/'worker-launch.json').exists(),'frozen call published worker launch'
    assert cache.is_dir() and not any(cache.iterdir()),'fixture bytecode cache changed'
    return dict(result='pass',raw_exit=observation.get('observed_worker_raw_exit'),
        actual_worker_launch_count=0,child_marker_absent=True,
        error=observation['first_event']['error'],
        observer_receipt_sha256=sha(control/'observation.json'),
        fixture_gates=['verify_bound','check_lease','qualification output validation',
                       'qualification accounting'],
        runtime_qualification=False)


def main():
    spine=verify_source_spine()
    with tempfile.TemporaryDirectory(prefix='dodge-startup-candidate-') as temp:
        candidate=exercise_candidate(Path(temp)/'candidate')
    with tempfile.TemporaryDirectory(prefix='dodge-startup-r6-negative-') as temp:
        frozen=exercise_frozen_negative(Path(temp)/'frozen-r6')
    print(json.dumps({'schema':'dodge013_startup_cpu_regression_v1',
        'status':'pass','candidate':candidate,'frozen_r6_negative':frozen,
        'source_spine':spine,
        'scope':'CPU dummy-child lifecycle only; fixture gates do not qualify resources'},
        indent=2,sort_keys=True))


if __name__=='__main__':
    main()
