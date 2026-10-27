# Stdlib-only structural model of long_d2_executor.monitor (extracted control flow, not production code).
import json, threading, time
class M:
    def __init__(s, structure):
        s.until = time.monotonic() + 0.5; s.log = dict(pump_errors=0, term=0, kill=0, absence=0, deadline_exit=False)
        s.structure = structure; s.stop = threading.Event()
    def pump(self):                       # persistent failure, as EDESTADDRREQ on start_ack retry
        self.log['pump_errors'] += 1; raise OSError(39, 'Destination address required')
    def cleanup(self):
        self.log['term'] += 1; self.log['kill'] += 1; self.log['absence'] += 1
    def deadline(self):
        if time.monotonic() >= self.until: self.log['deadline_exit'] = True; self.stop.set()
    def monitor_current(self):            # one broad try; pump precedes cleanup
        while not self.stop.wait(.02):
            try:
                self.pump(); self.cleanup(); self.deadline()
            except BaseException:
                self.deadline()          # only the except-branch deadline check survives
    def monitor_isolated(self):           # fallible IPC isolated; duties each own try
        while not self.stop.wait(.02):
            try: self.pump()
            except BaseException: pass
            try: self.cleanup()
            except BaseException: pass
            try: self.deadline()
            except BaseException: pass
out = {}
for name in ('current', 'isolated'):
    m = M(name); t = threading.Thread(target=getattr(m, 'monitor_' + name)); t.start(); t.join(3)
    out[name] = dict(m.log, thread_alive=t.is_alive())
    m.stop.set()
print(json.dumps(out, indent=1, sort_keys=True))
