"""Fake-clock model of the REAL executor monitor/pump/signal_once/absent and the
SOURCE-EXTRACTED inner reaping block. No live signals, processes, sockets or ML.

Fake: time.monotonic/sleep, os.killpg, os.getpid (thread-aware), select.select, the two
IPC channel endpoints, the direct-child objects. Real: Execution.monitor/pump/fail,
FailurePool, processes.signal_once/absent/validate_report, the inner reap block text,
the publish_failed reaping-classification block text, fixture_guards.validate_fixture.
"""
import sys, os, json, hashlib, threading, signal, types, textwrap, time, select, errno, ast
from pathlib import Path
from unittest.mock import patch
HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE)); import proposal_patch as pp
sys.path.insert(0, str(pp.FROZEN))
import lifecycle as life, processes as owned, long_d2 as c
import long_d2_executor as e_old
from fixture_guards import validate_fixture
NS = types.SimpleNamespace
EXEC_PID, SUP_PID, WRK_PID = 1000, 200, 300

# ---- proposed module (in-memory compile of transformed frozen text) ----
e_new = types.ModuleType('long_d2_executor_proposed'); e_new.__file__ = str(pp.FROZEN / 'long_d2_executor.py')
exec(compile(pp.proposed_text(), 'long_d2_executor_proposed', 'exec'), e_new.__dict__)

# ---- source-extracted blocks, pinned by hash ----
def block(path, start, end):
    lines = Path(path).read_text().splitlines(True)
    a = next(i for i, l in enumerate(lines) if l.startswith(start)); b = next(i for i, l in enumerate(lines) if l.startswith(end) and i > a)
    text = textwrap.dedent(''.join(lines[a:b]))
    return text, hashlib.sha256(text.encode()).hexdigest(), (a + 1, b)
INNER_TEXT, INNER_SHA, INNER_LINES = block(pp.FROZEN / 'long_d2.py', "        if 'failure_ack_unavailable' not in result and child is not None:", "        # Optional bounded diagnostics follow")
REAP_TEXT, REAP_SHA, REAP_LINES = block(pp.FROZEN / 'long_d2_executor.py', "        reaping={}", "        result=dict(schema='long_d2_outer_acceptance_v2',accepted=False")
INNER_CODE = compile(INNER_TEXT, 'inner_reap_block', 'exec'); REAP_CODE = compile(REAP_TEXT, 'reaping_block', 'exec')


class World:
    """Process table with zombie semantics; killpg(0) succeeds on a zombie leader."""
    def __init__(s, clock, wedged=True, sup_dead_at_start=False):
        s.clock = clock; s.wedged = wedged
        s.state = {SUP_PID: 'alive', WRK_PID: 'alive'}; s.status = {}; s.signals = []
        s.exit_at = None; s.drop_on_kill = True; s.sup_lost_queue = False
        if sup_dead_at_start: s.state[SUP_PID] = 'zombie'; s.status[SUP_PID] = 7 << 8
    def killpg(s, pgid, number):
        if pgid not in s.state or s.state[pgid] == 'gone': raise ProcessLookupError()
        if number == 0: return
        s.signals.append((round(s.clock[0], 6), pgid, int(number)))
        if s.state[pgid] != 'alive': return
        if number == signal.SIGKILL or (number == signal.SIGTERM and pgid == WRK_PID and not s.wedged):
            s.die(pgid, int(number))
        # supervisor TERM: handler records only (phase FAILURE); wedged worker ignores TERM
    def die(s, pid, raw):
        s.state[pid] = 'zombie'; s.status[pid] = raw
        if pid == WRK_PID and s.state[SUP_PID] != 'alive': s.state[WRK_PID] = 'gone'  # init reaps the orphan
        if pid == SUP_PID:
            s.sup_lost_queue = True  # r10 evidence: unreceived datagram state is not relied on after peer death
            if s.state[WRK_PID] == 'zombie': s.state[WRK_PID] = 'gone'  # init reaps the orphan zombie
            if s.state[WRK_PID] == 'alive': s.orphan = True
    def reap(s, pid, parent):
        if s.state.get(pid) != 'zombie': return None
        raw = s.status[pid]; s.state[pid] = 'gone'
        code = os.waitstatus_to_exitcode(raw)
        return dict(pid=pid, raw_wait_status=raw, returncode=code, reaped_by=parent, direct_child_reaped=True, observed_monotonic=s.clock[0])


class FakeChild:
    def __init__(s, world, pid, parent_of): s.w, s.process, s.report, s.parent_of = world, NS(pid=pid), None, parent_of
    def poll(s):
        if s.report is None: s.report = s.w.reap(s.process.pid, os.getpid())
        return s.report


class WorkerGate:  # executor's end of the worker gate socket: reset once the worker dies (never marked expected-closed)
    def __init__(s, world): s.sock = NS(fileno=lambda: 5); s.peer_closed = False; s.w = world; s.received = 1
    def receive(s, deadline, sender=None):
        life.remaining(deadline)
        raise ConnectionResetError(errno.ECONNRESET, 'worker gate peer closed')
    def send(s, value, deadline): life.remaining(deadline)


class Queue:
    def __init__(s): s.q = []


class ExecChannel:  # executor's end of the supervisor socket
    def __init__(s, world, inbox): s.sock = NS(fileno=lambda: 9); s.peer_closed = False; s.w, s.inbox, s.received = world, inbox, 0
    def receive(s, deadline, sender=None):
        life.remaining(deadline)
        if s.inbox.q:
            s.received += 1; return json.loads(s.inbox.q.pop(0)), []
        raise ConnectionResetError(errno.ECONNRESET, 'peer closed')
    def send(s, value, deadline): life.remaining(deadline)


class InnerChannel:  # supervisor's end; sends are JSON-roundtripped like the real Channel
    def __init__(s, world, inbox, fail_send): s.w, s.inbox, s.sent, s.fail_send, s.log = world, inbox, 0, fail_send, []
    def send(s, value, deadline, fd=None):
        life.remaining(deadline)
        if s.fail_send: raise OSError(errno.EPIPE, 'modeled lost IPC')
        s.sent += 1; raw = json.dumps(dict(schema='long_d2_owned_ipc_v1', sender=os.getpid(), seq=s.sent, **value), sort_keys=True, allow_nan=False)
        s.inbox.q.append(raw); s.log.append((round(s.w.clock[0], 6), value['kind']))


class Lockstep:
    def __init__(s, clock, body): s.clock, s.body, s.wake, s.done, s.exc = clock, body, None, False, None; s.resume = threading.Semaphore(0); s.blocked = threading.Semaphore(0); s.started = False; s.thread = threading.Thread(target=s.run, daemon=True)
    def run(s):
        s.resume.acquire()
        try: s.body()
        except BaseException as error: s.exc = error
        s.done = True; s.blocked.release()
    def sleep(s, seconds): s.wake = s.clock[0] + seconds; s.blocked.release(); s.resume.acquire()
    def advance(s):
        if s.done: return
        if not s.started: s.started = True; s.thread.start()
        elif s.wake is not None and s.wake > s.clock[0] + 1e-9: return
        s.wake = None; s.resume.release(); s.blocked.acquire()


def run_scenario(mod, name, *, t0, first_at, worker_s, inner_s, outer_s, wedged=True, supervisor='responsive',
                 sup_dead_at_start=False, post_reap_exit=.05, lost_ipc=False, tighten=None, tick=.02, ack_delay=.02,
                 fail_ts=None):
    clock = [t0 + 0.5 * worker_s]; inner = None
    w = World(clock, wedged=wedged, sup_dead_at_start=sup_dead_at_start)
    x = mod.Execution.__new__(mod.Execution)
    x.t0 = t0; x.pool = life.FailurePool(t0, outer_s); x.latch = NS(first_at=None, first_cancel_at=None, first_alarm_at=None, deadline=t0 + outer_s + 100, cancellation_requests=0, requested_signal=None, alarm_seen=False, phase='NORMAL')
    x.guard = NS(failure=None, failure_at=None, last_sample=clock[0]); x.groups = {}; x.child = FakeChild(w, SUP_PID, EXEC_PID)
    x.worker_wait = None; x.inner_ready = None; x.worker_ready = None; x.forwarded = []; x.events = []; x.ipc_lock = threading.RLock()
    x.recovery_proven = True; x.cleanup_complete = False
    g = lambda pid, par: dict(pid=pid, pgid=pid, parent_at_registration=par, new_session_verified=True, term_sent=False, kill_sent=False, group_absent=False, ownership='exact_command_parent_T0_capsule_output', argv=['model'])
    x.groups = {'supervisor': g(SUP_PID, EXEC_PID), 'worker': g(WRK_PID, SUP_PID)}
    inbox = Queue(); x.super_channel = ExecChannel(w, inbox); x.worker_channel = WorkerGate(w)
    if sup_dead_at_start: x.child.poll()  # executor reaps the deliberately crashed supervisor (rc 7)
    inner_pool = life.FailurePool(t0, outer_s)
    ichan = InnerChannel(w, inbox, lost_ipc)

    def inner_body():
        # Supervisor ACKed the shared pool, then enters the SOURCE-EXTRACTED best-effort reap block.
        until = inner_pool.fail('modeled supervisor failure', x.pool.first, x.pool.first_global, peer=True)
        ns = dict(result={}, child=FakeChild(w, WRK_PID, SUP_PID), process=NS(pid=WRK_PID), started=t0, until=until, worker_wait_attempted=False, life=life, owned=owned, os=os, time=time, mod=None)
        with patch.object(life, 'POOL', inner_pool), patch.object(life, 'CHANNEL', ichan):
            exec(INNER_CODE, ns)
        ns['result']['_worker_wait_send_attempted'] = ns['worker_wait_attempted']
        inner_out.update(result=ns['result'], child_report=ns['child'].report)
        # Remainder of the real handler (optional diagnostic, joins, close) modeled as a short bounded tail then exit(1).
        time.sleep(post_reap_exit)
        if w.state[SUP_PID] == 'alive': w.die(SUP_PID, 1 << 8)
    inner_out = {}
    if supervisor == 'responsive': inner = Lockstep(clock, inner_body)
    started_inner = [False]

    def fake_sleep(seconds):
        if inner is not None and threading.current_thread() is inner.thread: inner.sleep(seconds)
        else: raise AssertionError('unexpected sleep outside modeled supervisor')
    real_getpid = os.getpid
    def fake_getpid(): return SUP_PID if inner is not None and threading.current_thread() is inner.thread else EXEC_PID
    class Stop:
        count = 0
        def wait(s, *a):
            clock[0] += tick; x.guard.last_sample = clock[0]
            if tighten and not s.__dict__.get('tightened') and clock[0] >= tighten['at']:
                s.tightened = True; x.pool.fail('late earlier peer failure', tighten['first'], dict(timestamp=tighten['first'], kind='source', outcome='safety_stop', role='peer', timing_basis='test_actual_observation', signal=None), peer=True)
            if inner is not None and w.state[SUP_PID] == 'alive' and x.pool.first is not None and clock[0] >= x.pool.first + ack_delay: inner.advance()
            if inner is not None and inner.done and inner.exc is not None and not isinstance(inner.exc, SystemExit): raise AssertionError('modeled supervisor raised: ' + repr(inner.exc))
            if clock[0] > (x.pool.until or clock[0]) + 0.05: raise AssertionError('deadline not enforced')
            return bool(x.cleanup_complete)
    x.stop = Stop()
    def fake_select(r, wl, xl, timeout=None):
        out = []
        for ch in r:
            if ch is x.super_channel.sock and (inbox.q or w.sup_lost_queue): out.append(ch)
            if ch is x.worker_channel.sock and w.state[WRK_PID] != 'alive': out.append(ch)
        return (out, [], [])
    class Exit(BaseException): pass
    def leaf(code): raise Exit(code)
    timeline = dict(deadline_exit=False)
    patches = [patch.object(life, 'ACTIVE', x.latch), patch.object(time, 'monotonic', side_effect=lambda: clock[0]), patch.object(time, 'sleep', fake_sleep),
               patch.object(os, 'killpg', lambda pgid, number: w.killpg(pgid, number)), patch.object(os, 'getpid', fake_getpid), patch.object(os, '_exit', leaf),
               patch.object(select, 'select', fake_select), patch.object(c, 'WORKER_SECONDS', worker_s), patch.object(c, 'INNER_SECONDS', inner_s), patch.object(mod, 'NORMAL_SECONDS', outer_s)]
    for p in patches: p.start()
    try:
        clock[0] = t0 + first_at  # monitor first observes the registered worker cutoff at its own explicit source time
        x.guard.last_sample = clock[0]
        x.fail(c.Stop('Worker cutoff', 'wall_guard'), t0 + (worker_s if fail_ts is None else fail_ts))
        try: x.monitor()
        except Exit: timeline['deadline_exit'] = True
        # receipt-side classification: the SOURCE-EXTRACTED publish_failed block
        cleanup_errors = []; ns = dict(self=x, os=os, owned=owned, time=time, cleanup_errors=cleanup_errors, reaping=None)
        exec(REAP_CODE, ns); reaping = ns['reaping']
        absence = {r: owned.absent(rec['pgid'], x.pool.until + 1) for r, rec in x.groups.items()}
    finally:
        for p in reversed(patches): p.stop()
    kills = {role: [t for t, pid, n in w.signals if pid == rec['pid'] and n == int(signal.SIGKILL)] for role, rec in x.groups.items()}
    terms = {role: [t for t, pid, n in w.signals if pid == rec['pid'] and n == int(signal.SIGTERM)] for role, rec in x.groups.items()}
    esc = [dict(role=ev['role'], reason=ev['reason'], monotonic=round(ev['monotonic'], 6)) for ev in x.events if ev.get('kind') == 'escalation']
    out = dict(name=name, first=x.pool.first, until=x.pool.until, final_clock=round(clock[0], 6), worker_kill=kills['worker'], supervisor_kill=kills['supervisor'], worker_term=terms['worker'][:1], supervisor_term=terms['supervisor'][:1],
               same_tick_both_kill=bool(kills['worker'] and kills['supervisor'] and abs(kills['worker'][0] - kills['supervisor'][0]) < 1e-9),
               worker_wait_validated=x.worker_wait is not None, worker_wait=x.worker_wait, inner_wait=x.child.report, reaping=reaping, absence=absence,
               cleanup_complete=bool(x.cleanup_complete), deadline_exit=timeline['deadline_exit'], escalation_events=esc,
               monitor_errors=[ev for ev in x.events if ev.get('kind') == 'monitor_error'], reaping_block_cleanup_errors=cleanup_errors, ipc_sent=ichan.log, inner_reap_result={k: v for k, v in inner_out.get('result', {}).items() if k.startswith('worker_')} if inner_out else None,
               clock_end_vs_until=round((x.pool.until or 0) - clock[0], 6), cleanup_ordering_ok=(clock[0] <= x.pool.until))
    return out, x, w


def fixture_check(out, x, t0, first_at, worker_s, inner_s, outer_s, cls='failed_supervisor_alive'):
    receipt = dict(accepted=False, executor_t0_monotonic=t0, cleanup_until_monotonic=x.pool.until, ownership=x.groups, inner_wait=out['inner_wait'], worker_wait=out['worker_wait'], reaping=out['reaping'])
    spawns = [dict(kind='owned_spawn', role='outer', owned_role='supervisor', pid=SUP_PID, monotonic=t0 + .01), dict(kind='owned_spawn', role='inner', owned_role='worker', pid=WRK_PID, monotonic=t0 + .02), dict(kind='wedged_entry', role='worker', monotonic=t0 + .3, pid=WRK_PID)]
    options = dict(mode='wedged', expectation_class=cls, expected_exit=1, worker_seconds=worker_s, inner_seconds=inner_s, outer_seconds=outer_s, injection_contract=None)
    try:
        validate_fixture(receipt, spawns, out['absence'], options, receipt_available=True); return 'passed'
    except AssertionError as error: return 'AssertionError: ' + str(error)


def main():
    r10 = dict(t0=516539.26029925, first_at=.6, worker_s=.6, inner_s=1., outer_s=1.5)
    prod = dict(t0=1000., first_at=7140., worker_s=7140., inner_s=7170., outer_s=7200.)
    results = {}
    for label, mod in (('old_frozen', e_old), ('proposed', e_new)):
        res = {}
        o, x, w = run_scenario(mod, 'r10_replay_wedged', **r10); o['fixture_wedged_class'] = fixture_check(o, x, r10['t0'], .6, .6, 1., 1.5); res['r10_replay_wedged'] = o
        o, x, w = run_scenario(mod, 'production_scale_wedged', **prod); o['fixture_wedged_class'] = fixture_check(o, x, prod['t0'], 7140., 7140., 7170., 7200.); res['production_scale_wedged'] = o
        o, x, w = run_scenario(mod, 'unresponsive_supervisor', supervisor='hung', **r10); res['unresponsive_supervisor'] = o
        o, x, w = run_scenario(mod, 'lost_ipc_worker_wait_send', lost_ipc=True, **r10); res['lost_ipc_worker_wait_send'] = o
        o, x, w = run_scenario(mod, 'earlier_ack_tightening_after_ack', tighten=dict(at=r10['t0'] + .9, first=r10['t0'] + .4), **r10); res['earlier_ack_tightening_after_ack'] = o
        o, x, w = run_scenario(mod, 'genuine_parent_death_orphan', supervisor='hung', sup_dead_at_start=True, **r10); res['genuine_parent_death_orphan'] = o
        o, x, w = run_scenario(mod, 'worker_dies_on_TERM_normal', wedged=False, **r10); res['worker_dies_on_TERM_normal'] = o
        # monitor observes the (explicit-timestamp) outer-cutoff failure late; source timestamp stays t0+7200
        late = dict(t0=1000., worker_s=7300., inner_s=7300., outer_s=7200., fail_ts=7200.)
        o, x, w = run_scenario(mod, 'late_observed_inside_reap_window', first_at=7206.5, **late); res['late_observed_inside_reap_window'] = o
        o, x, w = run_scenario(mod, 'late_observed_after_latest_bound', first_at=7209.6, **late); res['late_observed_after_latest_bound'] = o
        results[label] = res
    results['source_extracts'] = dict(inner_reap_block=dict(file='long_d2.py', lines=INNER_LINES, sha256=INNER_SHA), publish_failed_reaping_block=dict(file='long_d2_executor.py', lines=REAP_LINES, sha256=REAP_SHA))
    A = {}
    O, P = results['old_frozen'], results['proposed']
    A['A1_old_reproduces_r10_same_tick_and_predicate'] = O['r10_replay_wedged']['same_tick_both_kill'] and not O['r10_replay_wedged']['worker_wait_validated'] and O['r10_replay_wedged']['fixture_wedged_class'] == 'AssertionError: owned direct reap missing'
    r = P['r10_replay_wedged']; kw, ks = r['worker_kill'][0], r['supervisor_kill'][0]
    A['A2_proposed_r10_worker_kill_unchanged'] = abs(kw - O['r10_replay_wedged']['worker_kill'][0]) < 1e-9
    A['A2_proposed_r10_supervisor_after_worker_and_after_wait'] = ks > kw and r['worker_wait_validated'] and r['worker_wait']['observed_monotonic'] < ks and r['worker_wait']['reaped_by'] == SUP_PID
    A['A2_proposed_r10_reaping_direct_and_fixture_passes'] = r['reaping']['worker'] == dict(status='direct_reaped', basis='validated_direct_parent_waitpid_report') and r['fixture_wedged_class'] == 'passed' and r['cleanup_complete']
    A['A2_proposed_r10_within_unchanged_cap'] = r['final_clock'] <= r['until'] and ks < r['until'] - .5
    u = P['unresponsive_supervisor']
    A['A3_unresponsive_supervisor_fallback_at_until_minus_half'] = abs(u['supervisor_kill'][0] - (u['until'] - .5)) <= .02 + 1e-9 and u['supervisor_kill'][0] > u['worker_kill'][0] and u['worker_wait'] is None and u['reaping']['worker']['status'] == 'unproven' and u['cleanup_complete'] and u['final_clock'] <= u['until']
    l = P['lost_ipc_worker_wait_send']
    A['A4_lost_ipc_unproven_not_fabricated'] = l['worker_wait'] is None and l['reaping']['worker']['status'] == 'unproven' and l['ipc_sent'] == [] and l['cleanup_complete']
    t = P['earlier_ack_tightening_after_ack']
    A['A5_tightening_worker_wait_still_relayed'] = t['worker_wait_validated'] and t['supervisor_kill'][0] > t['worker_kill'][0] and t['final_clock'] <= t['until'] and t['until'] < r['until']
    A['A6_genuine_parent_death_identical_old_new_and_unproven'] = (O['genuine_parent_death_orphan']['worker_kill'] == P['genuine_parent_death_orphan']['worker_kill'] and P['genuine_parent_death_orphan']['worker_wait'] is None and P['genuine_parent_death_orphan']['reaping']['worker'] == dict(status='unproven', basis='supervisor_dead_before_report'))
    A['A7_worker_dies_on_TERM_old_new_equal_no_kill'] = O['worker_dies_on_TERM_normal']['worker_kill'] == P['worker_dies_on_TERM_normal']['worker_kill'] == [] and P['worker_dies_on_TERM_normal']['worker_wait_validated']
    a, b = P['late_observed_inside_reap_window'], P['late_observed_after_latest_bound']
    A['A8_late_inside_window_relays'] = a['worker_wait_validated'] and a['supervisor_kill'][0] > a['worker_kill'][0]
    A['A8_late_after_latest_bound_same_tick_truthfully_unproven'] = b['same_tick_both_kill'] and b['worker_wait'] is None and b['reaping']['worker']['status'] == 'unproven' and O['late_observed_after_latest_bound']['same_tick_both_kill']
    A['A9_direct_reaped_iff_validated_worker_wait_all_cases'] = all((v['reaping']['worker']['status'] == 'direct_reaped') == (v['worker_wait'] is not None) for lab in ('old_frozen', 'proposed') for v in results[lab].values())
    A['A9b_no_case_labels_orphan_as_direct'] = all(v['reaping']['worker']['basis'] != 'validated_direct_parent_waitpid_report' or v['worker_wait'] is not None for lab in ('old_frozen', 'proposed') for v in results[lab].values())
    A['A11_all_cases_cleanup_complete_and_before_until'] = all(v['cleanup_complete'] or v['name'] == 'x' for v in P.values()) and all(v['final_clock'] <= v['until'] for v in P.values())
    A['A13_retained_worker_gate_IPC_loss_reproduced_and_does_not_starve_supervisor_channel'] = (any(ev['duty'] == 'IPC' and 'Unexpected private IPC loss' in ev['error'] for ev in r['monitor_errors']) and r['worker_wait_validated'])
    rs = lambda v: sorted((e_['role'], e_['reason']) for e_ in v['escalation_events'])
    A['A14_escalation_reasons'] = (rs(r) == [('supervisor', 'validated_worker_wait'), ('worker', 'original_cutpoint')] and rs(u) == [('supervisor', 'latest_bound'), ('worker', 'original_cutpoint')]
                                   and rs(b) == [('supervisor', 'latest_bound'), ('worker', 'original_cutpoint')] and rs(P['genuine_parent_death_orphan']) == [('supervisor', 'supervisor_reaped'), ('worker', 'original_cutpoint')])
    # AST: proposed vs frozen differ only in Execution.monitor and new Execution.kill_due
    def fn_dumps(path_text):
        tree = ast.parse(path_text); out = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for f in node.body:
                    if isinstance(f, ast.FunctionDef): out[node.name + '.' + f.name] = ast.dump(f)
        for f in tree.body:
            if isinstance(f, ast.FunctionDef): out[f.name] = ast.dump(f)
        return out
    old_ast, new_ast = fn_dumps((pp.FROZEN / 'long_d2_executor.py').read_text()), fn_dumps(pp.proposed_text())
    changed = sorted(k for k in set(old_ast) | set(new_ast) if old_ast.get(k) != new_ast.get(k))
    A['A12_only_monitor_and_kill_due_differ'] = changed == ['Execution.kill_due', 'Execution.monitor']
    results['changed_functions'] = changed
    results['assertions'] = A
    (HERE / 'model-results.json').write_text(json.dumps(results, indent=2, sort_keys=True, default=str) + '\n')
    (HERE / 'proposed-executor-escalation.diff').write_text(pp.diff_text())
    print(json.dumps(A, indent=1)); 
    # compact digest
    for label in ('old_frozen', 'proposed'):
        print('==', label)
        for k, v in results[label].items():
            print(f"{k:38s} wKILL={v['worker_kill'][:1]} sKILL={v['supervisor_kill'][:1]} same_tick={v['same_tick_both_kill']} wait={v['worker_wait_validated']} reap_w={v['reaping']['worker']} clean={v['cleanup_complete']} fixture={v.get('fixture_wedged_class','-')[:60]}")

if __name__ == '__main__': main()
