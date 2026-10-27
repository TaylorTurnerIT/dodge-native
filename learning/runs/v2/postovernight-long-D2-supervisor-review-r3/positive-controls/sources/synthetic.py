#!/usr/bin/env python3
"""Subprocess-only stdlib controls. Never authorizes a production campaign.

The JSON/PT-shaped artifacts here are explicitly synthetic byte files. No
Torch/native/teacher import, deserialization, inference or gameplay occurs.
"""
import time
ENTRY=time.monotonic()
import argparse
import copy
import io
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import types
import long_d2 as c
import long_d2_executor as e
import lifecycle as life
import processes as owned
HERE=Path(__file__).resolve().parent
ORIGINAL=c.ORIGINAL_ROOT
P=c.registered_protocol(ORIGINAL/c.PROTOCOL_REL)
CONFIG=c.read_json(ORIGINAL/P['config_path']);BASE=c.read_json(ORIGINAL/P['base_config_path'])


def setup(root):
    options=c.read_json(root/'options.json')
    c.ORIGINAL_ROOT=c.ROOT=root;c.STATE_PATH=root/'state.json'
    c.WORKER_SECONDS=options.get('worker_seconds',8)
    c.INNER_SECONDS=options.get('inner_seconds',10)
    e.NORMAL_SECONDS=options.get('outer_seconds',12)
    pins=c.read_json(root/'pins.json')
    identity={'version':'synthetic_only','legacy_module_origins':{str(root/'module.py'):dict(sha256=pins[str(root/'module.py')],mirror='module.py')}}
    p=copy.deepcopy(P);p['output']='campaign'
    lease=c.expected_lease(p,'a'*64,'b'*64,root,'c'*64)
    context=p,CONFIG,BASE,identity,pins,lease
    c.capsule_context=lambda *a,**kw:context
    c.assert_readonly_capsule=lambda *a:None  # Owned fixture has no real capsule.
    c.check_module_origins=lambda *a,**kw:{}
    return options,context


def install_hooks(root,options,role):
    fired=False;writers=set()
    event_path=root/(role+'-events.jsonl')
    def event(kind,**fields):
        with event_path.open('a') as stream:
            stream.write(json.dumps(dict(kind=kind,role=role,monotonic=time.monotonic(),**fields),sort_keys=True)+'\n')
    def trigger(phase):
        nonlocal fired
        if fired or options.get('phase')!=role+':'+phase:return
        fired=True;mutation=options.get('mutation','none')
        event('injection',phase=phase,mutation=mutation,handler_INT=str(signal.getsignal(signal.SIGINT)),handler_TERM=str(signal.getsignal(signal.SIGTERM)))
        if mutation=='cancel':
            value=c.read_json(root/'state.json');value['active_long_campaign']['cancel_requested']=True
            c.replace_json(root/'state.json',value)
        elif mutation=='input':(root/'watched.txt').write_text('persistent changed pin\n')
        elif mutation in ('forward_SIGINT','forward_SIGTERM'):
            os.kill(int(sys.argv[sys.argv.index('--executor-pid')+1]),getattr(signal,mutation[8:]))
        elif mutation in ('SIGINT','SIGTERM','SIGALRM','SIGKILL'):
            os.kill(os.getpid(),getattr(signal,mutation))
        elif mutation=='crash':os._exit(7)
        elif mutation=='extra':(root/'campaign/extra.txt').write_text('extra')
        elif mutation=='pending':(root/'campaign/.late.pending').write_text('pending')
        elif mutation=='symlink':(root/'campaign/link').symlink_to(root/'watched.txt')
        elif mutation=='binding':
            path=root/'campaign/finalization-result.json';value=c.read_json(path);value['run_result_sha256']='0'*64
            c.replace_json(path,value)
        if options.get('delay',0):time.sleep(options['delay'])
    real_replace=c.replace_json
    def replacing(path,value):
        name={'artifact-manifest.json':'manifest','finalization-result.json':'terminal','acceptance-receipt.json':'receipt'}.get(path.name)
        if name:trigger(name+'-before')
        if name=='receipt' and value.get('accepted') is False and options.get('failure_persistence_delay'):
            time.sleep(options['failure_persistence_delay'])
        real_replace(path,value)
        if name:trigger(name+'-after')
    c.replace_json=replacing
    real_sha=c.sha
    def hashing(path):
        path=Path(path)
        if path.is_relative_to(root/'campaign'):
            event('hash',path=str(path),open_writers=sorted(writers))
            trigger('hash-before')
        result=real_sha(path)
        if path.is_relative_to(root/'campaign'):trigger('hash-after')
        return result
    c.sha=hashing
    real_open=Path.open
    class Writer:
        def __init__(self,inner,path):self.inner,self.path=inner,str(path);writers.add(self.path)
        def __getattr__(self,key):return getattr(self.inner,key)
        def __enter__(self):return self
        def __exit__(self,*a):self.close()
        def close(self):
            try:self.inner.close()
            finally:writers.discard(self.path)
    def opening(path,mode='r',*a,**kw):
        inner=real_open(path,mode,*a,**kw)
        if path.is_relative_to(root/'campaign') and any(x in mode for x in 'wxa+'):
            return Writer(inner,path)
        return inner
    Path.open=opening
    real_close=c.Guard.close
    def closing(guard):
        trigger('guard-close-before')
        real_close(guard)
        event('guard_closed',handles_absent=all(t is None or not t.is_alive() for t in (guard.thread,guard.verify_thread)),receipt=guard.receipt())
        trigger('guard-close-after')
    c.Guard.close=closing
    real_verify=c.verify_files
    def verify(pins):
        ready=(root/'campaign/finalization-result.json').exists() if role=='inner' else (root/'execution/acceptance-receipt.json').exists()
        if ready:trigger('full-verify-before')
        real_verify(pins)
        if ready:trigger('full-verify-after')
    c.verify_files=verify
    real_buffer=c.io.StringIO
    class Buffer(real_buffer):
        def close(self):
            trigger('stream-close-before');super().close();trigger('stream-close-after')
    c.io.StringIO=Buffer
    real_join=threading.Thread.join
    def joining(thread,*a,**kw):
        if thread.name=='long-D2-executor-watchdog':trigger('watchdog-join-before')
        result=real_join(thread,*a,**kw)
        if thread.name=='long-D2-executor-watchdog':trigger('watchdog-join-after')
        return result
    threading.Thread.join=joining
    real_pending=life.ProcessLatch.pending_once
    def pending(latch):
        trigger('pending-before');real_pending(latch);trigger('exit-gap')
    life.ProcessLatch.pending_once=pending
    real_timer=signal.setitimer
    def timer(which,seconds,*a):
        event('timer',seconds=seconds)
        if seconds==0:trigger('blocked-before-disarm')
        return real_timer(which,seconds,*a)
    signal.setitimer=timer
    real_authority=e.Execution.authority
    def final_authority(execution,force=False):
        if execution.watchdog is not None and not execution.watchdog.is_alive() and (root/'execution/acceptance-receipt.json').exists():
            trigger('before-D')
        return real_authority(execution,force)
    e.Execution.authority=final_authority
    real_final=life.final_exit
    def final(code,latch,deadline,failed=lambda:False):
        if role!='outer':trigger('before-D')
        real_final(code,latch,deadline,failed)
    life.final_exit=final
    real_popen=subprocess.Popen
    def popen(*a,**kw):
        result=real_popen(*a,**kw)
        if role=='inner':trigger('spawn-before-registration')
        return result
    subprocess.Popen=popen
    real_poll=owned.Child.poll
    def polling(child):
        if role=='inner':trigger('during-worker')
        return real_poll(child)
    owned.Child.poll=polling
    return trigger,event


def fake_worker(args,context,options,event):
    p,config,base,identity,pins,lease=context
    output=args.output
    if options.get('mode') in ('blocked','wedged','descendant'):
        signal.signal(signal.SIGTERM,signal.SIG_IGN)
        if options['mode']=='wedged':signal.signal(signal.SIGALRM,signal.SIG_IGN)
        if options['mode'] in ('blocked','wedged'):
            while True:time.sleep(.01)
        subprocess.Popen([sys.executable,'-B','-c','import time; time.sleep(30)'])
    with (output/'worker-resources.jsonl').open('x') as resources:
        guard=c.Guard(args.started+c.WORKER_SECONDS,lambda:c.assert_lease(args.state_path,lease),lambda:c.verify_files(pins),resources)
        guard.start()
        mode=options.get('mode','closure');passed=mode=='pass'
        outcome='D2_progress_gate_passed' if passed else 'budget_closed_below_gate'
        result=c.outcome_fields(outcome,True)
        origins={'dodge_rl':dict(origin=str(c.ROOT/'module.py'),**identity['legacy_module_origins'][str(c.ROOT/'module.py')])}
        control=c.read_json(ORIGINAL/P['entry_control'])['evaluations']['D2']
        evaluation=copy.deepcopy(control)
        if passed:
            for row in evaluation['rows']:
                row.update(score=50,alive_frames=3060)
            evaluation.update(mean_score=50,mean_alive_frames=3060)
        checkpoint='checkpoint-000010-long_evaluated.pt'
        (output/checkpoint).write_bytes(b'SYNTHETIC_STDLIB_ONLY_NOT_A_TEACHER\n')
        digest=c.sha(output/checkpoint)
        certificate=dict(phase='long_D2',evaluation_stage='D2',checkpoint_sha256=digest,complete=True,
                         evaluations={'D2':evaluation},progression_gate_passed=passed,
                         training_parent_eligible=False,teacher_qualified=False)
        c.save(output/(checkpoint+'.long-evaluation.json'),certificate)
        record=dict(checkpoint=checkpoint,sha256=digest,complete_update=True,training_parent_eligible=False,
                    evaluated=True,progression_gate_passed=passed,evaluation_sha256=c.sha(output/(checkpoint+'.long-evaluation.json')))
        values={'entry-restoration.json':dict(matched=True,before_any_environment_or_gradient=True,
                        bitwise_sha256=dict(model='synthetic',Adam='synthetic',RNG='synthetic')),
                'entry-control.json':dict(matched=True,rows=64,fields=list(c.ROW_KEYS),control_document_sha256=p['entry_control_sha256'],
                        RNG_unchanged=True,model_Adam_unchanged=True,zero_gradients_before_control=True),
                'parent-lineage.json':dict(parent_checkpoint_sha256=p['parent_checkpoint_sha256'],parent_terminal_receipt=p['parent_terminal_receipt'],
                        inherited_counters=c.PARENT_COUNTERS,failed_D2_experience_inherited=False),
                'long-config.json':config,'long-identity.json':identity,'checkpoint-index.json':[record],
                'actual-import-origins.json':origins}
        for name,value in values.items():c.save(output/name,value)
        for name in ('training-episodes.jsonl','training-metrics.jsonl','schedule.jsonl',checkpoint+'.D2-development.jsonl'):
            (output/name).write_text('')
        guard.close()
        result.update(run_id=p['run_id'],protocol_sha256=c.PROTOCOL_SHA256,config_document_sha256=c.CONFIG_SHA256,
            identity_document_sha256=lease['identity_sha256'],checkpoint_identity_semantic_sha256=c.semantic_hash(identity),
            actual_import_origins=origins,final_checkpoint=record,worker_resources=guard.receipt())
    c.save(output/'long-worker-result.json',result)
    event('synthetic_worker_closed',ML_imports=False)
    if options.get('mode','').startswith('raw-'):
        number=getattr(signal,options['mode'][4:]);signal.signal(number,signal.SIG_DFL);os.kill(os.getpid(),number)
    return 7 if mode=='wrong-exit' else c.result_code(result)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=('executor','run','worker'))
    parser.add_argument('--root',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--state-path',type=Path)
    parser.add_argument('--started',type=float)
    parser.add_argument('--supervisor-pid',type=int)
    parser.add_argument('--executor-fd',type=int)
    parser.add_argument('--executor-pid',type=int)
    args=parser.parse_args()
    root=(args.root or args.output.parent).resolve();options,context=setup(root)
    role={'executor':'outer','run':'inner','worker':'worker'}[args.command]
    trigger,event=install_hooks(root,options,role)
    def worker_factory(supervisor,fd,t0):
        return e.worker_command(HERE/'synthetic.py',root/'campaign',root/'state.json',t0,supervisor,fd,os.getpid())
    if args.command=='executor':
        registration=dict(controller=str(HERE/'synthetic.py'),executor=str(HERE/'long_d2_executor.py'),
            output=str(root/'campaign'),receipt=str(root/'execution/acceptance-receipt.json'),state_path=str(root/'state.json'),
            identity_sha256=context[-1]['identity_sha256'],capsule_manifest_sha256=context[-1]['capsule_manifest_sha256'],pins={})
        def supervisor_factory(fd,t0):
            return [sys.executable,'-B',str(HERE/'synthetic.py'),'run','--output',str(root/'campaign'),
                    '--state-path',str(root/'state.json'),'--executor-fd',str(fd),'--executor-pid',str(os.getpid())]
        execution=e.Execution(ENTRY,registration,context,supervisor_factory=supervisor_factory,worker_factory=worker_factory)
        execution.run()
    elif args.command=='run':
        t0,handoff,gate=c.owned_handoff(args)
        def command_factory(args,t0,fd):return worker_factory(os.getpid(),fd,t0)[:-1]+[str(args.executor_pid)]
        code,guard=c.supervise_owned(args,t0,handoff,gate,context_provider=lambda _:context,command_factory=command_factory)
        life.final_exit(code,life.ACTIVE,life.POOL.until or t0+c.INNER_SECONDS,
                        lambda:guard is not None and guard.failure is not None)
    else:
        context=c.worker_gate(args)
        code=fake_worker(args,context,options,event)
        life.CHANNEL.send(dict(kind='worker_done',t0_monotonic_hex=args.started.hex(),expected_exit_code=code),life.POOL.until or args.started+c.WORKER_SECONDS)
        life.CHANNEL.sock.close()
        life.final_exit(code,life.ACTIVE,life.POOL.until or args.started+c.WORKER_SECONDS)


if __name__=='__main__':main()
