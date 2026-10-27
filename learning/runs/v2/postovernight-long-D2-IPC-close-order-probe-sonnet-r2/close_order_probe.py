#!/usr/bin/env python
# Preregistered close-order discriminator (r2). stdlib only. Writes only under OUT.
# Roles: main (executor) / supervisor / worker. Two fixed cases, each once, order fixed.
import array, fcntl, json, os, signal, socket, subprocess, sys, time
PY = '/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/.venv/bin/python'
HOLD_AFTER_READY = 0.4
def now(): return time.monotonic()
def rec(path, **o):
    o['t'] = o.get('t', now()); o.setdefault('pid', os.getpid())
    with open(path, 'a') as f: f.write(json.dumps(o, sort_keys=True) + '\n')
def fdinfo(fd):
    try:
        st = os.fstat(fd); fl = fcntl.fcntl(fd, fcntl.F_GETFD)
        return dict(fd=fd, open=True, dev=st.st_dev, ino=st.st_ino, mode=oct(st.st_mode), cloexec=bool(fl & fcntl.FD_CLOEXEC))
    except OSError as e:
        return dict(fd=fd, open=False, errno=e.errno, error=type(e).__name__)
class Ch:
    def __init__(self, sock, ev, role, name): self.s, self.ev, self.role, self.name, self.seq = sock, ev, role, name, 0
    def send(self, kind, timeout, fd=None, **extra):
        self.seq += 1
        raw = json.dumps(dict(kind=kind, seq=self.seq, sender=os.getpid(), **extra), sort_keys=True).encode()
        anc = [] if fd is None else [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', [fd]))]
        self.s.settimeout(timeout); t0 = now()
        try:
            n = self.s.sendmsg([raw], anc); r = dict(ok=True, sent=n, length=len(raw), scm=fd is not None)
        except OSError as e:
            r = dict(ok=False, error=type(e).__name__, errno=e.errno, length=len(raw), timed_out=isinstance(e, TimeoutError))
        t1 = now()
        rec(self.ev, role=self.role, e='send', chan=self.name, msg=kind, seq=self.seq, t_start=t0, t=t1, dt=t1 - t0, **r)
        return r
    def recv(self, timeout, label):
        self.s.settimeout(timeout); t0 = now(); fds = []
        try:
            raw, anc, flags, _ = self.s.recvmsg(60001, socket.CMSG_SPACE(4))
            for l, k, d in anc:
                if l == socket.SOL_SOCKET and k == socket.SCM_RIGHTS:
                    a = array.array('i'); a.frombytes(d[:len(d) - len(d) % 4]); fds += list(a)
            kind = seq = None
            if raw:
                try: j = json.loads(raw); kind, seq = j.get('kind'), j.get('seq')
                except Exception: kind = 'undecodable'
            r = dict(ok=True, raw_length=len(raw), flags=flags, anc_records=len(anc), nfds=len(fds), msg=kind, rseq=seq, fds=fds)
        except OSError as e:
            r = dict(ok=False, error=type(e).__name__, errno=e.errno, timed_out=isinstance(e, TimeoutError))
        t1 = now()
        rec(self.ev, role=self.role, e='recv', chan=self.name, label=label, t_start=t0, t=t1, dt=t1 - t0, **r)
        return r
def reap(pid, deadline):
    while True:
        try: p, st = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError: return dict(reaped=False, note='ChildProcessError')
        if p: return dict(reaped=True, raw_wait_status=st, exit=os.waitstatus_to_exitcode(st))
        if now() >= deadline: return dict(reaped=False, note='deadline')
        time.sleep(0.01)
def kill_group(pgid, deadline):
    out = dict(pgid=pgid)
    for name, sig in (('TERM', signal.SIGTERM), ('KILL', signal.SIGKILL)):
        try: os.killpg(pgid, sig); out[name] = 'sent'
        except ProcessLookupError: out[name] = 'absent'; break
        except OSError as e: out[name] = repr(e)
        end = min(deadline, now() + 0.5)
        while now() < end:
            try: os.killpg(pgid, 0)
            except ProcessLookupError: break
            time.sleep(0.01)
    return out
def absent(pgid):
    try: os.killpg(pgid, 0); return False
    except ProcessLookupError: return True
    except OSError: return False

def supervisor(case, ch_fd, ev, owned):
    ch = Ch(socket.socket(fileno=ch_fd), ev, 'supervisor', 'super')
    r = ch.recv(3.0, 'start+gate')
    gate = socket.socket(fileno=r['fds'][0]); gfd = gate.fileno()
    rec(ev, role='supervisor', e='gate_received', case=case, fdinfo=fdinfo(gfd))
    w = None
    try:
        w = subprocess.Popen([PY, '-B', os.path.abspath(__file__), 'worker', str(gfd), ev, case], start_new_session=True, pass_fds=(gfd,))
        rec(owned, e='worker', worker_pid=w.pid, pgid=w.pid)
        rec(ev, role='supervisor', e='worker_popen_returned', worker_pid=w.pid, gate_fdinfo=fdinfo(gfd))
        closed = False
        if case == 'case2_early_close':
            gate.close(); st = fdinfo(gfd); closed = True
            rec(ev, role='supervisor', e='gate_closed_right_after_popen', closed_fdinfo=st, before_register_send=True)
        ch.send('register_worker', 1.0, worker_pid=w.pid)
        ch.recv(5.0, 'registered')
        done = ch.recv(3.0, 'ack_attempt_done_barrier') if not closed else None
        if not closed:
            pre = fdinfo(gfd); gate.close(); post = fdinfo(gfd)
            rec(ev, role='supervisor', e='gate_closed_after_barrier_release', probe_only_artificial_barrier=True, pre=pre, post=post)
            closed = True
        else:
            ch.recv(3.0, 'ack_attempt_done_notice_nonbarrier')
    finally:
        if not gate.fileno() == -1:
            gate.close(); rec(ev, role='supervisor', e='gate_closed_in_finally')
    res = reap(w.pid, now() + 4.0) if w else {}
    if not res.get('reaped') and w:
        res = dict(res, kill=kill_group(w.pid, now() + 1.5)); res.update(reap(w.pid, now() + 1.0))
    rec(ev, role='supervisor', e='worker_reaped', **res)
    ch.send('done', 1.0)

def worker(gfd, ev, case):
    g = Ch(socket.socket(fileno=gfd), ev, 'worker', 'gate')
    rec(ev, role='worker', e='start', fdinfo=fdinfo(gfd), case=case)
    time.sleep(0.12)
    g.send('worker_ready', 0.5)
    g.recv(2.0, 'start_ack')

def run_case(case, out, deadline, owned):
    ev = os.path.join(out, case + '.jsonl')
    parent, child_socket = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    gp, gc = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    pc, pg = Ch(parent, ev, 'executor', 'super'), Ch(gp, ev, 'executor', 'gate')
    rec(ev, role='executor', e='case_begin', case=case, fdinfo=dict(parent=fdinfo(parent.fileno()), child_socket=fdinfo(child_socket.fileno()), gp=fdinfo(gp.fileno()), gc=fdinfo(gc.fileno())))
    p = subprocess.Popen([PY, '-B', os.path.abspath(__file__), 'supervisor', case, str(child_socket.fileno()), ev, owned],
                         start_new_session=True, pass_fds=(child_socket.fileno(),))
    rec(owned, e='supervisor', pid=p.pid, pgid=p.pid, case=case)
    result = dict(case=case, supervisor_pid=p.pid)
    try:
        pc.send('start', 1.0, fd=gc.fileno()); child_socket.close(); gc.close()
        reg = pc.recv(min(5.0, deadline - now()), 'register_worker')
        rdy = pg.recv(min(5.0, deadline - now()), 'worker_ready')
        t_ready = now(); result['t_ready_observed'] = t_ready
        rec(ev, role='executor', e='worker_ready_observed', t=t_ready, positive=bool(rdy.get('ok') and rdy.get('msg') == 'worker_ready'))
        if not (rdy.get('ok') and rdy.get('msg') == 'worker_ready' and reg.get('ok')): result['precondition_failed'] = True
        else:
            time.sleep(max(0.0, t_ready + HOLD_AFTER_READY - now()))
            result['registered_send'] = pc.send('registered', 1.0, hold_after_ready=now() - t_ready)   # registered BEFORE start_ack
            result['start_ack_send'] = pg.send('start_ack', 0.2)                                         # production .2s send timeout
            result['start_ack_attempt_done_t'] = now()
            pc.send('ack_attempt_done', 1.0)
            fin = pc.recv(min(5.0, deadline - now()), 'supervisor_done')
            result['final'] = fin
    finally:
        parent_reap = reap(p.pid, min(deadline, now() + 4.0))
        res = dict(parent_reap)
        if not parent_reap.get('reaped'):
            res['kill'] = kill_group(p.pid, now() + 1.5); res.update(reap(p.pid, now() + 1.0))
        result['supervisor_wait'] = res
        parent.close(); gp.close()
        try: child_socket.close()
        except Exception: pass
        try: gc.close()
        except Exception: pass
        result['supervisor_group_absent'] = absent(p.pid)
    return result

def evalcase(c, ev):
    rows = [json.loads(l) for l in open(ev)]
    w_ack = next((r for r in rows if r.get('role') == 'worker' and r.get('e') == 'recv'), {})
    send = c.get('start_ack_send', {})
    zero = bool(w_ack.get('ok') and w_ack.get('raw_length') == 0 and w_ack.get('flags') == 0)
    delivered = bool(w_ack.get('ok') and w_ack.get('msg') == 'start_ack' and send.get('ok'))
    return dict(worker_ack_recv=dict((k, w_ack.get(k)) for k in ('ok', 'raw_length', 'flags', 'msg', 'error', 'errno', 'dt')),
                executor_start_ack_send=send, zero_byte_flags0=zero, ack_send_timeout=bool(send.get('timed_out')), delivered=delivered)

def main(out, wrapper_deadline):
    deadline = float(wrapper_deadline)
    owned = os.path.join(out, 'owned-pids.jsonl'); rec(owned, e='main', pid=os.getpid(), pgid=os.getpgrp())
    res = dict(sys_executable=sys.executable, version=sys.version, t_start=now(), cases={}, hold_after_ready=HOLD_AFTER_READY)
    try:
        for case in ('case1_legacy_close_delayed_registration', 'case2_early_close_after_popen'):
            res['cases'][case] = run_case(case, out, deadline, owned)
            res['cases'][case]['eval'] = evalcase(res['cases'][case], os.path.join(out, case + '.jsonl'))
            if res['cases'][case].get('precondition_failed') or now() > deadline: res['stopped_after'] = case; break
    except BaseException as e:
        res['unexpected_error'] = repr(e)
    c1 = res['cases'].get('case1_legacy_close_delayed_registration', {}).get('eval')
    c2 = res['cases'].get('case2_early_close_after_popen', {}).get('eval')
    if 'unexpected_error' in res or c1 is None or c2 is None: v = 'failed'
    elif c1['zero_byte_flags0'] and c1['ack_send_timeout'] and c2['delivered']: v = 'paired_support'
    else: v = 'inconclusive'
    res['verdict'] = v; res['t_end'] = now()
    print(json.dumps(res, sort_keys=True, indent=1))

if __name__ == '__main__':
    a = sys.argv
    if a[1] == 'main': main(a[2], a[3])
    elif a[1] == 'supervisor': supervisor(a[2], int(a[3]), a[4], a[5])
    elif a[1] == 'worker': worker(int(a[2]), a[3], a[4])
