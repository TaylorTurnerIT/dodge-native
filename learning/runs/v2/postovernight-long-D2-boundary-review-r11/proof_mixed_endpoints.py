"""Independent source-extracted adversarial IPC discriminator; no real sockets."""
from extract import *
import array,copy,errno,json,socket,stat

closed=[]
osfake=NS(getpid=lambda:150,waitstatus_to_exitcode=os.waitstatus_to_exitcode,
          close=lambda fd:closed.append(fd))
channel_ns=dict(time=clock,math=math,threading=threading,os=osfake,socket=socket,
                array=array,stat=stat,json=json,Stop=life.Stop,remaining=life.remaining)
extract('lifecycle.py',{'Channel'},channel_ns)
Channel=channel_ns['Channel']
selectfake=NS(select=None)
namespace=dict(c=c,life=life,owned=owned,time=clock,math=math,os=osfake,json=json,
               signal=signal,threading=threading,select=selectfake,NORMAL_SECONDS=7200)
extract('long_d2_executor.py',{'Execution'},namespace)
Execution=namespace['Execution']

def descriptor(at,role):
    return dict(timestamp=at,kind='fixture_source',outcome='resource_stop',role=role,
                timing_basis='synthetic_observation',signal=None)

def packet(role,at=99.5,seq=1):
    return dict(schema='long_d2_owned_ipc_v1',seq=seq,sender=200 if role=='supervisor' else 300,
                kind='failure',t0_monotonic_hex=(90.).hex(),first_monotonic_hex=at.hex(),
                reason='fixture failure',descriptor=descriptor(at,role))

def execution():
    clock.value=100.
    x=Execution.__new__(Execution);x.t0=90.;x.pool=life.FailurePool(90.)
    x.events=[];x.forwarded=[];x.ipc_lock=threading.RLock()
    x.latch=NS(first_cancel_at=None,first_alarm_at=None,deadline=7290.,
               cancellation_requests=0,requested_signal=None,phase='NORMAL')
    life.ACTIVE=ln['ACTIVE']=x.latch
    x.guard=NS(failure=None,failure_at=None,last_sample=100.)
    x.child=NS(process=NS(pid=200),report=None,poll=lambda:None)
    x.groups={r:dict(pid=p,pgid=p,parent_at_registration=q,new_session_verified=True,
                    group_absent=False,term_sent=False,kill_sent=False,
                    gate_ack_attempted=False,gate_acked=False,gate_ack_failed=False)
              for r,p,q in [('supervisor',200,150),('worker',300,200)]}
    x.recovery_proven=x.cleanup_complete=False
    x.worker_wait=x.inner_ready=x.worker_ready=None
    return x

class Sock:
    def __init__(self,role,raw,*,fault=None,anc=None,flags=0):
        self.role=role;self.raw=raw;self.fault=fault;self.anc=anc or [];self.flags=flags
        self.reads=[];self.sends=[];self.timeouts=[];self.pending=True
    def fileno(self):return 9 if self.role=='supervisor' else 10
    def settimeout(self,n):self.timeouts.append(n)
    def recvmsg(self,*args):
        self.reads.append(clock.value);self.pending=False
        if self.fault=='reset':raise ConnectionResetError(errno.ECONNRESET,'fixture reset')
        return self.raw,self.anc,self.flags,None
    def sendmsg(self,parts,anc):
        self.sends.append(json.loads(parts[0]))
        if self.fault=='ack':raise OSError(errno.EPIPE,'fixture ACK failure')
        if self.fault=='partial_ack':return len(parts[0])-1
        return len(parts[0])

def channel(sock):
    ch=Channel.__new__(Channel);ch.sock=sock;ch.t0=90.;ch.lock=threading.RLock()
    ch.sent=ch.received=0
    return ch

def run(role,fault,*,final=False):
    x=execution();socks={}
    x.pool.fail('prior direct source',99.75,descriptor(99.75,'outer'))
    for r in ('supervisor','worker'):
        p=packet(r,99.625 if r==role else 99.5);raw=json.dumps(p).encode();anc=[];flags=0
        if r==role:
            if fault=='empty':raw=b''
            elif fault=='partial_json':raw=b'{"schema":'
            elif fault=='list_json':raw=b'[]'
            elif fault=='duplicate':raw=b'{"schema":1,"schema":2}'
            elif fault=='schema':p['schema']='wrong';raw=json.dumps(p).encode()
            elif fault=='sequence':p['seq']=2;raw=json.dumps(p).encode()
            elif fault=='sender':p['sender']=301;raw=json.dumps(p).encode()
            elif fault=='clock':p['t0_monotonic_hex']=(91.).hex();raw=json.dumps(p).encode()
            elif fault=='future':p['first_monotonic_hex']=(101.).hex();raw=json.dumps(p).encode()
            elif fault=='FD':anc=[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[8765]).tobytes())]
            elif fault=='truncated':flags=socket.MSG_TRUNC
        socks[r]=Sock(r,raw,fault=fault if r==role else None,anc=anc,flags=flags)
    x.super_channel=channel(socks['supervisor']);x.worker_channel=channel(socks['worker'])
    selectfake.select=lambda values,*a:([s for s in values if s.pending],[],[])
    caught=None
    try:x.pump(deadline_limit=109.5 if final else None)
    except BaseException as error:caught=repr(error)
    assert caught is not None,(role,fault,'error disappeared')
    assert (x.pool.first,x.pool.until)==(99.5,109.5),(role,fault,x.pool.first,x.pool.until)
    other='worker' if role=='supervisor' else 'supervisor'
    assert len(socks[other].reads)==1 and len(socks[other].sends)==1
    assert socks[other].sends[0]['kind']=='failure_ack'
    assert socks[other].sends[0]['cleanup_until_monotonic_hex']==(109.5).hex()
    assert x.groups['worker']['gate_acked'] is False and not x.recovery_proven
    assert x.worker_wait is None and x.child.report is None
    return dict(bad_endpoint=role,fault=fault,final_drain=final,caught=caught,
                first=x.pool.first,until=x.pool.until,diagnostics=x.events,
                reads={r:len(s.reads) for r,s in socks.items()},
                sends={r:s.sends for r,s in socks.items()},
                sequence={r:ch.received for r,ch in [('supervisor',x.super_channel),('worker',x.worker_channel)]})

cases=[run(role,fault,final=final) for role in ('supervisor','worker')
       for fault in ('reset','empty','partial_json','list_json','duplicate','schema','sequence',
                     'sender','clock','future','FD','truncated','ack','partial_ack')
       for final in (False,True)]

# Empty datagrams consume no sequence. New readiness after repeated diagnostic
# capacity exhaustion must still admit an earlier, valid seq1 source.
x=execution();bad=Sock('supervisor',b'');good=Sock('worker',json.dumps(packet('worker')).encode())
x.super_channel=channel(bad);x.worker_channel=channel(good)
selectfake.select=lambda values,*a:([s for s in values if s.pending],[],[])
for n in range(12):
    bad.pending=True;bad.flags=n*65536
    try:x.pump()
    except life.Stop:pass
assert len([v for v in x.events if v['kind']=='monitor_error'])==8
assert not getattr(x.super_channel,'peer_closed',False)
bad.raw=json.dumps(packet('supervisor',99.25)).encode();bad.flags=0;bad.pending=True
x.pump()
assert (x.pool.first,x.pool.until)==(99.25,109.25)
assert x.super_channel.received==1 and len(bad.sends)==1
assert not x.recovery_proven and x.groups['worker']['gate_acked'] is False
late=dict(first=x.pool.first,until=x.pool.until,events=x.events,
          supervisor_reads=len(bad.reads),worker_reads=len(good.reads),supervisor_ACKs=len(bad.sends))
result=dict(cases=cases,late_after_full_diagnostics=late,extractions=extractions,
            limits='Exact AST source blocks; fake datagrams/readiness/time/process identities. No real IPC, OS lifecycle, runtime, performance or acceptance evidence.')
(H/'mixed-endpoints-results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(cases=len(cases),late_after_full_diagnostics=late,passed=True),indent=2))
