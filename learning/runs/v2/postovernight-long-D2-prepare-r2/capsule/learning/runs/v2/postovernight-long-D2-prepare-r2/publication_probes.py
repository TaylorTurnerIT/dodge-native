"""Owned stdlib OS probes of actual supervise/Guard, never a campaign launch.

All authority files, logs, mutations and signals belong to the named scenario.
Events live outside the synthetic output and therefore cannot alter its manifest.
LONG_D2_TEST_SOURCE permits exact r1 or retained single-line negative controls.
"""
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import types
from unittest.mock import patch
import test_long_d2 as t

c=t.c
HERE=Path(__file__).resolve().parent


def scenario(root,phase='hash-before',mutation='cancel',mode='closure',delay=0.0):
    root=Path(root).resolve();root.mkdir(exist_ok=False)
    output=root/'campaign';state=root/'state.json';watched=root/'watched.txt'
    watched.write_text('original frozen synthetic bytes\n')
    pins={str(watched):c.sha(watched)}
    state.write_text(json.dumps({'active_long_campaign':t.lease()}))
    (root/'capsule-manifest.json').write_text('{"files":{}}')
    context=({**t.PROTOCOL,'output':'campaign'},t.CONFIG,t.BASE,{},pins,t.lease())
    args=types.SimpleNamespace(output=output,state_path=state)
    real_sha,real_replace,real_verify=c.sha,c.replace_json,c.verify_files
    real_alarm,real_stop=c.absolute_alarm,c.stop_owned
    real_signal=c.signal.signal
    old_handlers={number:signal.getsignal(number) for number in (signal.SIGINT,signal.SIGTERM)}
    events=[];fired=[False];guards=[];started=time.monotonic()
    writers=set();writer_checks=[];real_open=Path.open
    def event(kind,**fields):
        events.append(dict(event=kind,elapsed=time.monotonic()-started,**fields))
        (root/'events.json').write_text(json.dumps(events,sort_keys=True,indent=2)+'\n')
    def trigger(at):
        if phase!=at or fired[0]:return
        fired[0]=True;event('trigger',phase=phase,mutation=mutation)
        if mutation=='cancel':
            value=c.read_json(state);value['active_long_campaign']['cancel_requested']=True
            state.write_text(json.dumps(value))
        elif mutation=='input':watched.write_text('changed pinned bytes\n')
        elif mutation in ('SIGINT','SIGTERM'):
            number=getattr(signal,mutation)
            event('real_signal',number=number,handler=str(signal.getsignal(number)))
            os.kill(os.getpid(),number)
        if delay:time.sleep(delay)
    def terminal_exists():
        return (output/'finalization-result.json').exists()
    class ActualGuard(c.Guard):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs);guards.append(self)
        def close(self):
            if terminal_exists():trigger('monitor-close-before')
            super().close()
            if terminal_exists():trigger('monitor-close-after')
            event('guard_closed',receipt=self.receipt())
        def sample(self,*args,**kwargs):
            if terminal_exists():trigger('authority-before')
            super().sample(*args,**kwargs)
            if terminal_exists():trigger('authority-after')
    class Buffer(io.StringIO):
        def close(self):
            if terminal_exists():trigger('stream-close-before')
            super().close()
            if terminal_exists():trigger('stream-close-after')
    def verify(actual):
        if terminal_exists():trigger('full-verify-before')
        real_verify(actual)
        if terminal_exists():trigger('full-verify-after')
    class TrackedWriter:
        def __init__(self,inner,path):self.inner,self.path=inner,path;writers.add(str(path))
        def __getattr__(self,name):return getattr(self.inner,name)
        def __enter__(self):self.inner.__enter__();return self
        def __exit__(self,*args):
            try:return self.inner.__exit__(*args)
            finally:writers.discard(str(self.path))
        def close(self):
            try:return self.inner.close()
            finally:writers.discard(str(self.path))
    def opening(path,mode='r',*args,**kwargs):
        value=real_open(path,mode,*args,**kwargs)
        if path.is_relative_to(output) and any(x in mode for x in ('w','a','x','+')):
            return TrackedWriter(value,path)
        return value
    def hashing(path):
        path=Path(path);artifact=path.is_relative_to(output)
        if artifact:
            writer_checks.append(dict(path=path.name,open_output_writers=sorted(writers),
                                      live_memory_monitor=any(g.thread is not None and g.thread.is_alive() for g in guards)))
            trigger('hash-before')
        value=real_sha(path)
        if artifact:trigger('hash-after')
        return value
    def replacing(path,value):
        if path.name=='artifact-manifest.json':trigger('manifest-before')
        if path.name=='finalization-result.json':trigger('terminal-before')
        real_replace(path,value)
        if path.name=='artifact-manifest.json':trigger('manifest-after')
        if path.name=='finalization-result.json':trigger('terminal-after')
    @contextmanager
    def alarm(deadline):
        with real_alarm(deadline):yield
        if terminal_exists():trigger('alarm-exit')
    def signal_handler(number,handler):
        value=real_signal(number,handler)
        if number in old_handlers and handler==old_handlers[number] and terminal_exists():
            trigger('latch-restore')
        return value
    def stop(process):
        receipt=real_stop(process);event('owned_stop',receipt=receipt);return receipt
    def command(*unused):
        return [sys.executable,'-B',str(HERE/'fake_worker.py'),'--output',str(output),'--mode',mode]
    with patch.object(c,'ORIGINAL_ROOT',root),patch.object(c,'ROOT',root), \
         patch.object(c,'STATE_PATH',state),patch.object(c,'assert_readonly_capsule'), \
         patch.object(c,'sha',side_effect=hashing),patch.object(c,'replace_json',side_effect=replacing), \
         patch.object(c,'verify_files',side_effect=verify),patch.object(c,'stop_owned',side_effect=stop), \
         patch.object(c.signal,'signal',side_effect=signal_handler), \
         patch.object(Path,'open',opening), \
         patch.object(c.io if hasattr(c,'io') else io,'StringIO',Buffer):
        code=c.supervise(args,context_provider=lambda unused:context,command_factory=command,
                         guard_factory=ActualGuard,alarm_factory=alarm,started=started)
    terminal=c.read_json(output/'finalization-result.json')
    result=c.read_json(output/'long-run-result.json')
    manifest=output/'artifact-manifest.json'
    stable=True
    if manifest.exists():
        entries=c.read_json(manifest)
        stable=all(real_sha(output/name)==digest for name,digest in entries.items())
        stable=stable and terminal['artifact_manifest_sha256']==real_sha(manifest)
        stable=stable and terminal['run_result_sha256']==real_sha(output/'long-run-result.json')
    for g in guards:
        event('guard_final',receipt=g.receipt(),threads_stopped=all(
            thread is None or not thread.is_alive() for thread in (g.thread,getattr(g,'verify_thread',None))))
    cleanup=result.get('owned_process_stop',{})
    absent=False
    if cleanup.get('owned_pgid'):
        try:os.killpg(cleanup['owned_pgid'],0)
        except ProcessLookupError:absent=True
    observed=dict(return_code=code,phase=phase,mutation=mutation,mode=mode,delay_seconds=delay,
                  actual_supervise=True,actual_guard=True,owned_stdlib_OS_worker=True,
                  trigger_fired=fired[0],manifest_available=manifest.exists(),manifest_still_matches=stable,
                  terminal=terminal,events=events,owned_group_positively_absent=absent,
                  artifact_hash_writer_checks=writer_checks,
                  input_matches=real_sha(watched)==pins[str(watched)],
                  cancel_requested=c.read_json(state)['active_long_campaign']['cancel_requested'],
                  controller_sha256=real_sha(Path(c.__file__)),
                  ML_imports=any(n in ('torch','numpy','dodge_rl') or n.startswith(('torch.','numpy.','dodge_rl.'))
                                 for n in sys.modules))
    (root/'events.json').write_text(json.dumps(events,sort_keys=True,indent=2)+'\n')
    (root/'observation.json').write_text(json.dumps(observed,sort_keys=True,indent=2)+'\n')
    return observed


if __name__=='__main__':
    value=scenario(sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],float(sys.argv[5]))
    print(json.dumps({k:value[k] for k in ('return_code','trigger_fired','manifest_available','manifest_still_matches')}))
    raise SystemExit(value['return_code'])
