"""Deterministic process model. Real monitor/pump, inner reap and fixture consumer.

No OS child, signal, socket, thread, lifecycle campaign or transport observation.
Only time.sleep in the extracted inner block becomes a generator yield so a
single-threaded fake scheduler can interleave the exact remainder of that block.
"""
from pathlib import Path
from types import SimpleNamespace as NS,ModuleType
from unittest.mock import patch
from contextlib import ExitStack
import ast,copy,errno,hashlib,json,os,signal,textwrap,threading
import long_d2 as c
import long_d2_executor as e
import lifecycle as life
import processes as owned
from test_repairs import execution,desc
from test_r7 import group
from fixture_guards import validate_fixture
H=Path(__file__).resolve().parent

def extracted(path,start,end):
    s=path.read_text();a=s.index(start);b=s.index(end,a)
    return textwrap.dedent(s[a:b])
INNER=extracted(H/'long_d2.py',"        if 'failure_ack_unavailable' not in result and child is not None:","        # Optional bounded diagnostics follow")
REAP=extracted(H/'long_d2_executor.py','        reaping={}\n',"        result=dict(schema='long_d2_outer_acceptance_v2',accepted=False")
class Cooperative(ast.NodeTransformer):
    def visit_Expr(self,node):
        if isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute) and isinstance(node.value.func.value,ast.Name) and node.value.func.value.id=='time' and node.value.func.attr=='sleep':
            return ast.copy_location(ast.Expr(value=ast.Yield(value=node.value.args[0])),node)
        return self.generic_visit(node)
tree=ast.parse('def inner_actor(worker_wait_attempted=False):\n'+textwrap.indent(INNER,'    ')+'\n    if world.state[200]!="alive":return\n    yield .05\n    if not hold_supervisor:world.die(200,256)\n')
INNER_CODE=compile(ast.fix_missing_locations(Cooperative().visit(tree)),'actual_inner_reap_cooperative','exec')
REAP_CODE=compile(REAP,'actual_failed_receipt_reaping','exec')

class DeadlineExit(BaseException):pass
class World:
    def __init__(self,clock,term_dies=False,dead_parent=False):
        self.clock=clock;self.term_dies=term_dies;self.state={200:'alive',300:'alive'};self.raw={};self.signals=[]
        if dead_parent:self.die(200,7<<8)
    def die(self,pid,raw):
        self.state[pid]='zombie';self.raw[pid]=raw
        if pid==200 and self.state[300]=='zombie':self.state[300]='gone'
        if pid==300 and self.state[200]!='alive':self.state[300]='gone'
    def killpg(self,pid,number):
        if self.state[pid]=='gone':raise ProcessLookupError()
        if number==0:return
        self.signals.append((self.clock[0],pid,int(number)))
        if self.state[pid]=='alive' and (number==signal.SIGKILL or number==signal.SIGTERM and pid==300 and self.term_dies):self.die(pid,int(number))
    def reap(self,pid):
        if self.state[pid]!='zombie':return None
        self.state[pid]='gone';raw=self.raw[pid]
        return dict(pid=pid,reaped_by=os.getpid(),direct_child_reaped=True,raw_wait_status=raw,returncode=os.waitstatus_to_exitcode(raw),observed_monotonic=self.clock[0])
class Child:
    def __init__(self,world,pid):self.world=world;self.process=NS(pid=pid);self.report=None
    def poll(self):
        if self.report is None:self.report=self.world.reap(self.process.pid)
        return self.report

def old_module():
    module=ModuleType('r10_negative_control');module.__file__=str(H/'r10-source/long_d2_executor.py')
    exec(compile(Path(module.__file__).read_text(),module.__file__,'exec'),module.__dict__)
    return module

def run(*,old=False,responsive=True,lost_ipc=False,dead_parent=False,term_dies=False,tighten=False,late=None,gate_error=False,signal_error=False):
    module=old_module() if old else e
    clock=[99.75 if late is None else late];world=World(clock,term_dies,dead_parent)
    x=execution();x.__class__=module.Execution;x.guard.last_sample=clock[0];x.latch.deadline=10000.
    del x.pump
    x.child=Child(world,200);x.groups={'supervisor':group(200,150),'worker':group(300,200)}
    for rec in x.groups.values():rec.update(term_sent=False,kill_sent=False,group_absent=False)
    x.recovery_proven=True;queue=[];sent=[];inner_results={};inner_pool=life.FailurePool(90.)
    active_actor=[False];iterator=[None];wake=[None];actor_done=[False]
    class Super:
        sock=NS(fileno=lambda:9)
        def receive(self,deadline):
            life.remaining(deadline)
            if queue:return queue.pop(0),[]
            raise ConnectionResetError(errno.ECONNRESET,'modeled supervisor loss')
        def send(self,*a):life.remaining(a[1])
    class Worker:
        sock=NS(fileno=lambda:10)
        def receive(self,deadline):raise ConnectionResetError(errno.ECONNRESET,'modeled worker loss')
    x.super_channel=Super();x.worker_channel=Worker()
    class InnerChannel:
        def send(self,value,deadline):
            life.remaining(deadline);sent.append((clock[0],value['kind']))
            if lost_ipc:raise BrokenPipeError('modeled worker_wait lost')
            queue.append(json.loads(json.dumps(dict(sender=200,**value))))
    def advance_actor():
        if not responsive or world.state[200]!='alive' or actor_done[0]:return
        if wake[0] is not None and clock[0]<wake[0]:return
        active_actor[0]=True
        try:
            if iterator[0] is None:
                inner_pool.fail('shared failure',x.pool.first,x.pool.first_global,peer=True)
                ns=dict(result=inner_results,child=Child(world,300),process=NS(pid=300),started=90.,until=inner_pool.until,
                    worker_wait_attempted=False,life=NS(POOL=inner_pool,CHANNEL=InnerChannel(),remaining=life.remaining),owned=owned,os=os,time=e.time,world=world,hold_supervisor=lost_ipc)
                exec(INNER_CODE,ns);iterator[0]=ns['inner_actor']()
            try:wake[0]=clock[0]+next(iterator[0])
            except StopIteration:actor_done[0]=True
        finally:active_actor[0]=False
    class Stop:
        count=0
        def wait(self,*a):
            self.count+=1;clock[0]+=.02;x.guard.last_sample=clock[0]
            if tighten and self.count==3:x.pool.fail('late earlier peer',99.5,desc(99.5),peer=True)
            advance_actor()
            if clock[0]>111.:raise AssertionError('independent deadline not enforced')
            return x.cleanup_complete
    x.stop=Stop()
    def ready(sockets,*a):
        values=[]
        if x.super_channel.sock in sockets and (queue or world.state[200]!='alive'):values.append(x.super_channel.sock)
        if x.worker_channel.sock in sockets and world.state[300]!='alive':values.append(x.worker_channel.sock)
        return values,[],[]
    def killpg(pid,number):
        if signal_error and pid==200 and number==signal.SIGTERM:raise PermissionError('modeled supervisor TERM denied')
        world.killpg(pid,number)
    def leaf(code):raise DeadlineExit(code)
    ended=False
    with ExitStack() as stack:
        for target,name,value in [(life,'ACTIVE',x.latch),(e.time,'monotonic',lambda:clock[0]),(os,'getpid',lambda:200 if active_actor[0] else 150),
            (os,'killpg',killpg),(os,'getpgrp',lambda:999),(e.select,'select',ready),(os,'_exit',leaf)]:stack.enter_context(patch.object(target,name,value))
        if gate_error:
            def broken(role):raise ValueError('modeled eligibility gate error')
            stack.enter_context(patch.object(x,'kill_due',broken))
        x.fail(c.Stop('source cutoff','wall_guard'),99.75)
        try:x.monitor()
        except DeadlineExit:ended=True
        # Dispose the stopped fake actor without permitting a killed process tail.
        if iterator[0] is not None and world.state[200]!='alive':iterator[0].close()
        ns=dict(self=x,os=os,owned=owned,time=e.time,cleanup_errors=[])
        exec(REAP_CODE,ns)
    # Independent synthetic absence was observed by the actual monitor.
    result=dict(first=x.pool.first,until=x.pool.until,clock=clock[0],worker_wait=x.worker_wait,inner_wait=x.child.report,
        reaping=ns['reaping'],cleanup_complete=x.cleanup_complete,deadline_exit=ended,signals=world.signals,
        sent=sent,inner_result=inner_results,events=x.events,source_extracts=dict(inner_sha256=hashlib.sha256(INNER.encode()).hexdigest(),reaping_sha256=hashlib.sha256(REAP.encode()).hexdigest()))
    result['kills']={role:[t for t,pid,n in world.signals if pid==rec['pid'] and n==signal.SIGKILL] for role,rec in x.groups.items()}
    receipt=dict(accepted=False,executor_t0_monotonic=90.,cleanup_until_monotonic=x.pool.until,ownership=x.groups,
        inner_wait=x.child.report,worker_wait=x.worker_wait,reaping=ns['reaping'])
    events=[dict(kind='owned_spawn',owned_role=role,pid=rec['pid'],monotonic=90.1) for role,rec in x.groups.items()]+[dict(kind='wedged_entry',role='worker')]
    options=dict(mode='wedged',expectation_class='failed_supervisor_alive',expected_exit=1,injection_contract=None)
    try:validate_fixture(receipt,events,{role:rec['group_absent'] for role,rec in x.groups.items()},options,receipt_available=True);result['fixture']='passed'
    except AssertionError as error:result['fixture']=str(error)
    return result
