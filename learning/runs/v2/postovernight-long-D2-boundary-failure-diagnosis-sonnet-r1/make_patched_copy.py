#!/usr/bin/env python3
"""Build a PATCHED COPY (inside this diagnosis dir only) of the frozen r3 modules.

Frozen r3 is read, never written. Every replacement must match exactly once.
The copy exists only to run the same discriminators against the proposed fix.
"""
import shutil
import sys
from pathlib import Path

FROZEN = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/postovernight-long-D2-boundary-prepare-r3')
OUT = Path(__file__).resolve().parent / 'patched-candidate'
MODULES = ('lifecycle.py', 'processes.py', 'boundary_integrity.py', 'long_d2.py', 'long_d2_executor.py')

PATCHES = {
 'lifecycle.py': [(
"""    now = time.monotonic()
    candidates = [now] if at is None else [now, at]
    if ACTIVE is not None:
        if ACTIVE.first_at is not None:candidates.append(ACTIVE.first_at)""",
"""    now = time.monotonic()
    descriptor = getattr(error, 'first_failure_descriptor', None)
    if at is None and descriptor is not None:
        at = descriptor.get('timestamp')  # already-observed failure keeps its own time
    candidates = [now] if at is None else [now, at]
    if ACTIVE is not None:
        if ACTIVE.first_at is not None:candidates.append(ACTIVE.first_at)""")],
 'long_d2.py': [(
"""    now = time.monotonic()
    candidates = [now]
    if guard is not None and guard.failure_at is not None:
        candidates.append(guard.failure_at)
    if life.ACTIVE is not None:
        if life.ACTIVE.first_at is not None:
            candidates.append(life.ACTIVE.first_at)
        if now >= life.ACTIVE.deadline:
            candidates.append(life.ACTIVE.deadline)
        life.ACTIVE.phase = 'FAILURE'
    local_until = life.POOL.fail(error, min(candidates))
""",
"""    if life.ACTIVE is not None:
        life.ACTIVE.phase = 'FAILURE'
    # primary_error's descriptor already holds the earliest guard/latch/deadline/catch time.
    local_until = life.POOL.fail(error)
""")],
 'long_d2_executor.py': [
  ("""    def fail(self,error,at=None):
        now=time.monotonic()""",
   """    def fail(self,error,at=None):
        if not isinstance(error,BaseException):error=c.Stop(str(error),'safety_stop')
        now=time.monotonic()"""),
  ("self.fail('Executor recorded cancellation',self.latch.first_at)", "self.fail(c.Stop('Executor recorded cancellation','cancelled'),self.latch.first_at)"),
  ("self.fail('Worker cutoff',self.t0+c.WORKER_SECONDS)", "self.fail(c.Stop('Worker cutoff','wall_guard'),self.t0+c.WORKER_SECONDS)"),
  ("self.fail('Inner cutoff',self.t0+c.INNER_SECONDS)", "self.fail(c.Stop('Inner cutoff','wall_guard'),self.t0+c.INNER_SECONDS)"),
  ("self.fail('Outer cutoff',self.t0+NORMAL_SECONDS)", "self.fail(c.Stop('Outer cutoff','wall_guard'),self.t0+NORMAL_SECONDS)"),
  ("self.fail('Outer sample age')", "self.fail(c.Stop('Outer sample age','resource_stop'))"),
  ("self.fail('Inner raw failure')", "self.fail(c.Stop('Inner raw failure','publication_failure'))"),
 ],
}

def main():
    if OUT.exists():
        raise SystemExit('patched-candidate already exists; refuse to overwrite')
    OUT.mkdir()
    for name in MODULES:
        text = (FROZEN / name).read_text()
        for old, new in PATCHES.get(name, []):
            if text.count(old) != 1:
                raise SystemExit(f'{name}: patch anchor count {text.count(old)} != 1: {old[:60]!r}')
            text = text.replace(old, new)
        (OUT / name).write_text(text)
    print('patched copy written:', OUT)

if __name__ == '__main__':
    main()
