"""Pure text transform of the FROZEN r10 executor into the PROPOSED escalation ordering.

Reads the frozen file, never writes it. Used by model_harness.py and to emit
proposed-executor-escalation.diff (a source proposal only; not applied anywhere).
"""
import difflib
from pathlib import Path

FROZEN = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/postovernight-long-D2-boundary-prepare-r10')

OLD_KILL = """                    if time.monotonic()>=min(self.pool.first+5,self.pool.until-.5):
                        self.monitor_duty('KILL_'+role,lambda record=record:owned.signal_once(record,signal.SIGKILL))
"""
NEW_KILL = """                    due=[True]  # A failing gate defaults to the old immediate KILL.
                    self.monitor_duty('KILL_gate_'+role,lambda role=role:due.__setitem__(0,self.kill_due(role)))
                    if due[0]:
                        self.monitor_duty('KILL_'+role,lambda record=record:owned.signal_once(record,signal.SIGKILL))
"""
ANCHOR = "    def monitor(self):\n"
KILL_DUE = '''    def kill_due(self,role):
        """Worker/descendant KILL keeps the original cutpoint. A live supervisor with
        a registered, unreported worker outlives that KILL until it relays the
        validated direct wait report or the unchanged latest bound (until-.5)."""
        now=time.monotonic();latest=self.pool.until-.5
        if now<min(self.pool.first+5,latest):return False
        reason='original_cutpoint'
        if role=='supervisor':
            if now>=latest:reason='latest_bound'
            elif self.worker_wait is not None:reason='validated_worker_wait'
            elif self.child is None or self.child.report is not None:reason='supervisor_reaped'
            elif 'worker' not in self.groups:reason='no_registered_worker'
            else:return False
        if not any(x.get('kind')=='escalation' and x['role']==role for x in self.events):
            self.events.append(dict(kind='escalation',role=role,reason=reason,monotonic=now))
        return True

'''


def proposed_text():
    src = (FROZEN / 'long_d2_executor.py').read_text()
    assert src.count(OLD_KILL) == 1 and src.count(ANCHOR) == 1
    return src.replace(OLD_KILL, NEW_KILL).replace(ANCHOR, KILL_DUE + ANCHOR)


def diff_text():
    old = (FROZEN / 'long_d2_executor.py').read_text().splitlines(True)
    new = proposed_text().splitlines(True)
    return ''.join(difflib.unified_diff(old, new, 'a/long_d2_executor.py', 'b/long_d2_executor.py'))
