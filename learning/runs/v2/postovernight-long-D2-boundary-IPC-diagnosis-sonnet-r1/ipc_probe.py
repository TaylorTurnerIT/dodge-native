#!/usr/bin/env python
# Preregistered single-invocation transport microprobe. stdlib only. Owned output only.
# Cases (fixed, no retries): A plain; B dup+close; C SCM_RIGHTS same-process; D1/D2 cross-process
# executor->supervisor(SCM_RIGHTS)->worker(pass_fds) with supervisor gate close before/after exchange.
import array, json, os, socket, subprocess, sys, time, signal
OUT = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == 'main' else None
def now(): return time.monotonic()
def rec(path, obj):
    with open(path, 'a') as f: f.write(json.dumps(obj, sort_keys=True) + '\n')
def recv(sock, timeout):
    sock.settimeout(timeout)
    t = now()
    try:
        raw, anc, flags, _ = sock.recvmsg(60001, socket.CMSG_SPACE(4))
        return dict(ok=True, raw_length=len(raw), raw=raw[:60].decode('latin1'), flags=flags, anc=len(anc), dt=now()-t)
    except OSError as e:
        return dict(ok=False, error=type(e).__name__, errno=e.errno, dt=now()-t)
def send(sock, data, timeout, fd=None):
    sock.settimeout(timeout)
    t = now()
    try:
        anc = [] if fd is None else [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', [fd]))]
        n = sock.sendmsg([data], anc)
        return dict(ok=True, sent=n, dt=now()-t)
    except OSError as e:
        return dict(ok=False, error=type(e).__name__, errno=e.errno, dt=now()-t)
def recv_fd(sock, timeout):
    sock.settimeout(timeout)
    raw, anc, flags, _ = sock.recvmsg(60001, socket.CMSG_SPACE(4))
    fds = array.array('i')
    for l, k, d in anc:
        if l == socket.SOL_SOCKET and k == socket.SCM_RIGHTS: fds.frombytes(d[:len(d)-len(d) % 4])
    return raw, list(fds)

def exchange(gp, gc, tag):
    # worker-side gc sends ready; parent-side gp receives, acks; gc receives ack
    r = {}
    r['ready_send'] = send(gc, b'ready', .5)
    r['ready_recv'] = recv(gp, .5)
    r['ack_send'] = send(gp, b'ack', .2)
    r['ack_recv'] = recv(gc, .5)
    return r

def case_A():
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    r = exchange(a, b, 'A'); a.close(); b.close(); return r
def case_B():
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    b2 = socket.socket(fileno=os.dup(b.fileno()))
    b2.close()   # duplicate close, original remains
    r = exchange(a, b, 'B'); r['dup_fd_closed'] = True
    a.close(); b.close(); return r
def case_C():
    p, q = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    gp, gc = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    r = {}
    r['transfer_send'] = send(p, b'start', .5, gc.fileno())
    gc.close()   # production closes sender's copy immediately after send (rights in flight)
    raw, fds = recv_fd(q, .5)
    r['transfer_fds'] = fds
    g2 = socket.socket(fileno=fds[0])
    r.update(exchange(gp, g2, 'C'))
    g2.close(); gp.close(); p.close(); q.close(); return r

def case_D(variant, outdir):
    # Executor side (this process). variant D1: supervisor closes gate right after registered ack
    # (production order). D2: supervisor keeps gate until worker reports done (control).
    ev = os.path.join(outdir, variant + '.jsonl')
    parent, child_socket = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    gp, gc = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    me = os.path.abspath(__file__)
    p = subprocess.Popen([sys.executable, '-B', me, 'supervisor', str(child_socket.fileno()), ev, variant],
                         start_new_session=True, pass_fds=(child_socket.fileno(),))
    rec(ev, dict(role='executor', e='spawn', pid=os.getpid(), supervisor_pid=p.pid, t=now(),
                 fds=dict(parent=parent.fileno(), child=child_socket.fileno(), gp=gp.fileno(), gc=gc.fileno())))
    rec(ev, dict(role='executor', e='start_send', **send(parent, b'start', 1.0, gc.fileno())))
    child_socket.close(); gc.close()
    # register_worker from supervisor
    r = recv(parent, 5.0); rec(ev, dict(role='executor', e='register_recv', **r))
    rec(ev, dict(role='executor', e='registered_send', **send(parent, b'registered', 1.0)))
    # worker_ready via gp
    r = recv(gp, 5.0); rec(ev, dict(role='executor', e='ready_recv', t=now(), **r))
    rec(ev, dict(role='executor', e='start_ack_send', t=now(), **send(gp, b'start_ack', .2)))
    r = recv(parent, 3.0); rec(ev, dict(role='executor', e='post_recv_super', **r))
    try: rc = p.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL); rc = p.wait(); rec(ev, dict(role='executor', e='killed_exact_owned_group'))
    rec(ev, dict(role='executor', e='supervisor_exit', rc=rc, t=now()))
    parent.close(); gp.close()
    return dict(events=ev, supervisor_rc=rc)

def supervisor(fd, ev, variant):
    ch = socket.socket(fileno=fd)
    raw, fds = recv_fd(ch, 3.0)
    gate = socket.socket(fileno=fds[0])
    rec(ev, dict(role='supervisor', e='gate_received', pid=os.getpid(), gate_fd=gate.fileno(), nfds=len(fds), t=now()))
    w = subprocess.Popen([sys.executable, '-B', os.path.abspath(__file__), 'worker', str(gate.fileno()), ev, variant],
                         start_new_session=True, pass_fds=(gate.fileno(),))
    rec(ev, dict(role='supervisor', e='worker_spawn', worker_pid=w.pid, t=now()))
    rec(ev, dict(role='supervisor', e='register_send', **send(ch, b'register', 1.0)))
    r = recv(ch, 3.0); rec(ev, dict(role='supervisor', e='registered_recv', **r))
    if variant == 'D1':
        gate.close(); rec(ev, dict(role='supervisor', e='gate_closed_before_exchange', t=now()))
    try: rc = w.wait(timeout=4)
    except subprocess.TimeoutExpired:
        os.killpg(w.pid, signal.SIGKILL); rc = w.wait(); rec(ev, dict(role='supervisor', e='killed_exact_owned_worker_group'))
    rec(ev, dict(role='supervisor', e='worker_exit', rc=rc, t=now()))
    rec(ev, dict(role='supervisor', e='final_send', **send(ch, b'done', 1.0)))

def worker(fd, ev, variant):
    g = socket.socket(fileno=fd)
    rec(ev, dict(role='worker', e='start', pid=os.getpid(), fd=fd, t=now()))
    time.sleep(0.12)   # approximate production worker startup lag
    rec(ev, dict(role='worker', e='ready_send', t=now(), **send(g, b'worker_ready', .5)))
    r = recv(g, 2.0); rec(ev, dict(role='worker', e='ack_recv', t=now(), **r))

def main():
    out = OUT; os.makedirs(out, exist_ok=True)
    res = dict(python=sys.version, executable=sys.executable, pid=os.getpid(), t_start=now(), cases={})
    for name, fn in (('A_plain', case_A), ('B_dup_close', case_B), ('C_scm_same_process', case_C)):
        try: res['cases'][name] = fn()
        except BaseException as e:
            res['cases'][name] = dict(unexpected_error=repr(e)); res['stopped_after'] = name; break
    else:
        for v in ('D1', 'D2'):
            try: res['cases'][v] = case_D(v, out)
            except BaseException as e:
                res['cases'][v] = dict(unexpected_error=repr(e)); res['stopped_after'] = v; break
    res['t_end'] = now()
    print(json.dumps(res, sort_keys=True, indent=1))

if __name__ == '__main__':
    if sys.argv[1] == 'main': main()
    elif sys.argv[1] == 'supervisor': supervisor(int(sys.argv[2]), sys.argv[3], sys.argv[4])
    elif sys.argv[1] == 'worker': worker(int(sys.argv[2]), sys.argv[3], sys.argv[4])
