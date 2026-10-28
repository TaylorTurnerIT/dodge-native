"""Read-only preflight: AC power and a scoped caffeinate held by this dispatcher's parent.

Operational guard only; it changes no power setting. The dispatcher must be started as
`/usr/bin/caffeinate -ims <env/python dispatcher>` so the assertion spans the observer wait.
"""
import os
import re
import subprocess

CAFFEINATE = "/usr/bin/caffeinate"
REQUIRED_ASSERTIONS = ("PreventUserIdleSystemSleep", "PreventSystemSleep")


def _run(argv):
    return subprocess.run(argv, capture_output=True, text=True, check=True, timeout=20).stdout


def check(run=_run, pid=None, ppid=None):
    """Return a receipt dict or raise ValueError. `run` is injectable for fake tests."""
    pid = os.getpid() if pid is None else pid
    ppid = os.getppid() if ppid is None else ppid
    if "AC Power" not in run(["/usr/bin/pmset", "-g", "batt"]).splitlines()[0]:
        raise ValueError("not drawing from AC power")
    command = run(["/bin/ps", "-o", "command=", "-p", str(ppid)]).strip().split()
    if len(command) < 2 or command[0] != CAFFEINATE or command[1] != "-ims":
        raise ValueError("dispatcher parent is not exactly `/usr/bin/caffeinate -ims`: " + " ".join(command[:3]))
    held = set()
    for line in run(["/usr/bin/pmset", "-g", "assertions"]).splitlines():
        match = re.match(r"\s*pid (\d+)\(caffeinate\):.*?\b(Prevent\w+)\b", line)
        if match and int(match.group(1)) == ppid:
            held.add(match.group(2))
    missing = [name for name in REQUIRED_ASSERTIONS if name not in held]
    if missing:
        raise ValueError("caffeinate assertion not held by dispatcher parent: " + ",".join(missing))
    return dict(on_ac=True, caffeinate_pid=ppid, dispatcher_pid=pid, assertions=sorted(held))
