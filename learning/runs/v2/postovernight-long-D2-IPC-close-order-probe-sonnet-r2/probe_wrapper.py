#!/usr/bin/env python
# Wrapper: enforces actual 60s total, owns exact child PIDs/groups, reaps, positively probes absence.
import hashlib, json, os, signal, subprocess, sys, time
T0 = time.monotonic(); TOTAL = 60.0; HARD = T0 + TOTAL; MAIN_DEADLINE = T0 + 40.0; KILL_AT = T0 + 45.0
PY = '/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/.venv/bin/python'
OUT = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(OUT, 'close_order_probe.py')
def sha(p): return hashlib.sha256(open(p, 'rb').read()).hexdigest()
class Term(BaseException): pass
def h(sig, frm): raise Term(sig)
for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP): signal.signal(s, h)
def reap(pid, deadline):
    while True:
        try: p, st = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError: return dict(reaped=False, note='ChildProcessError')
        if p: return dict(reaped=True, raw_wait_status=st, exit=os.waitstatus_to_exitcode(st))
        if time.monotonic() >= deadline: return dict(reaped=False, note='deadline')
        time.sleep(0.01)
def pid_alive(pid):
    try: os.kill(pid, 0); return True
    except ProcessLookupError: return False
    except PermissionError: return True
def grp_absent(pgid):
    try: os.killpg(pgid, 0); return False
    except ProcessLookupError: return True
    except PermissionError: return False
def cmd_of(pid):
    try: return subprocess.run(['ps', '-p', str(pid), '-o', 'command='], capture_output=True, text=True, timeout=2).stdout.strip()
    except Exception as e: return 'ERR ' + repr(e)
def cleanup(rows, main_pid):
    out = []
    for pid in sorted({r['pid'] for r in rows if r.get('pid') not in (None, os.getpid())} | {r['worker_pid'] for r in rows if r.get('worker_pid')}):
        e = dict(pid=pid, alive_before=pid_alive(pid))
        if e['alive_before'] or not grp_absent(pid):
            c = cmd_of(pid); e['command'] = c
            if 'close_order_probe.py' in c or pid == main_pid:
                for sn, sg in (('TERM', signal.SIGTERM), ('KILL', signal.SIGKILL)):
                    try: os.killpg(pid, sg); e[sn] = 'sent'
                    except ProcessLookupError: e[sn] = 'absent'; break
                    except OSError as x: e[sn] = repr(x)
                    t = time.monotonic() + 0.4
                    while time.monotonic() < t and not grp_absent(pid): time.sleep(0.01)
                    if grp_absent(pid): break
            else: e['skipped_foreign_command'] = True
        e['group_absent_after'] = grp_absent(pid); e['pid_alive_after'] = pid_alive(pid)
        out.append(e)
    return out
def main():
    plan = json.load(open(os.path.join(OUT, 'plan.json')))
    rc = dict(argv=sys.argv, cwd=os.getcwd(), executable=sys.executable, version=sys.version, t0_monotonic=T0, wall_start=time.time(),
              env={k: os.environ.get(k) for k in ('PYTHONDONTWRITEBYTECODE', 'PYTHONPYCACHEPREFIX', 'PATH')},
              wrapper_sha256=sha(__file__), script_sha256=sha(SCRIPT), plan_script_sha256=plan['script_sha256'], plan_wrapper_sha256=plan['wrapper_sha256'])
    if sys.executable != PY or rc['script_sha256'] != plan['script_sha256'] or rc['wrapper_sha256'] != plan['wrapper_sha256']:
        rc['refused'] = 'interpreter or hash mismatch with plan'; print(json.dumps(rc, indent=1)); return 3
    outdir = os.path.join(OUT, 'probe-out'); os.mkdir(outdir)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPYCACHEPREFIX=os.environ['PYTHONPYCACHEPREFIX'])
    argv = [PY, '-B', SCRIPT, 'main', outdir, repr(MAIN_DEADLINE)]
    rc.update(child_argv=argv, child_env_pycache=env['PYTHONPYCACHEPREFIX'], child_cwd=os.getcwd())
    p = None; status = None; main_pid = None; budget_failure = None
    out_f = open(os.path.join(OUT, 'probe-stdout.json'), 'wb'); err_f = open(os.path.join(OUT, 'probe-stderr.log'), 'wb')
    try:
        p = subprocess.Popen(argv, stdout=out_f, stderr=err_f, env=env, start_new_session=True); main_pid = p.pid
        rc['main_pid'] = main_pid
        while True:
            pid, st = os.waitpid(p.pid, os.WNOHANG)
            if pid: status = dict(reaped=True, raw_wait_status=st, exit=os.waitstatus_to_exitcode(st), at=time.monotonic() - T0); break
            if time.monotonic() >= KILL_AT: budget_failure = 'main exceeded wrapper KILL_AT'; break
            time.sleep(0.02)
    except BaseException as e:
        budget_failure = 'wrapper interrupted: ' + repr(e)
    finally:
        rows = []
        try: rows = [json.loads(l) for l in open(os.path.join(outdir, 'owned-pids.jsonl'))]
        except Exception: pass
        if main_pid and status is None:
            try: os.killpg(main_pid, signal.SIGKILL)
            except ProcessLookupError: pass
            status = reap(main_pid, min(HARD - 5, time.monotonic() + 2.0)); status['killed_by_wrapper'] = True
        rc['owned_rows'] = rows
        rc['cleanup'] = cleanup(rows + ([dict(pid=main_pid)] if main_pid else []), main_pid)
        out_f.close(); err_f.close()
        rc['main_status'] = status; rc['budget_failure'] = budget_failure
        rc['wrapper_elapsed'] = time.monotonic() - T0; rc['within_60s'] = rc['wrapper_elapsed'] <= TOTAL
        rc['all_absent'] = all(c['group_absent_after'] and not c['pid_alive_after'] for c in rc['cleanup'])
        json.dump(rc, open(os.path.join(OUT, 'wrapper-result.json'), 'w'), indent=1, sort_keys=True, default=str)
    return 0 if status and status.get('exit') == 0 and not budget_failure and rc['all_absent'] else 1
if __name__ == '__main__': sys.exit(main())
