"""Read-only preflight: AC power and a scoped caffeinate helper tied to this dispatcher.

Operational guard only; it changes no power setting. The dispatcher must be started as
`/usr/bin/caffeinate -ims <env/python dispatcher>`. macOS caffeinate execs the utility and keeps
a helper CHILD that owns the assertions, so the helper is a direct child of this process
(same process group). The dispatcher's own parent is unrelated (e.g. the app server).
"""
import os
import re
import subprocess

CAFFEINATE = "/usr/bin/caffeinate"
FLAGS = "-ims"
REQUIRED_ASSERTIONS = ("PreventUserIdleSystemSleep", "PreventSystemSleep")
_ASSERTION = re.compile(r"\s*pid (\d+)\(([^)]*)\):.*?\b(Prevent\w+)\b")


def _run(argv):
    return subprocess.run(argv, capture_output=True, text=True, check=True, timeout=20).stdout


def _processes(text):
    rows = []
    for line in text.splitlines():
        fields = line.split(None, 3)
        if len(fields) == 4 and all(field.isdigit() for field in fields[:3]):
            rows.append(dict(pid=int(fields[0]), ppid=int(fields[1]), pgid=int(fields[2]), command=fields[3]))
    return rows


def check(run=_run, pid=None):
    """Return a receipt dict or raise ValueError. `run` is injectable for fake tests."""
    pid = os.getpid() if pid is None else pid
    if "AC Power" not in run(["/usr/bin/pmset", "-g", "batt"]).splitlines()[0]:
        raise ValueError("not drawing from AC power")
    rows = _processes(run(["/bin/ps", "-axo", "pid=,ppid=,pgid=,command="]))
    me = next((row for row in rows if row["pid"] == pid), None)
    if me is None:
        raise ValueError("dispatcher process not found in ps: " + str(pid))
    helpers = []
    for row in rows:
        tokens = row["command"].split()
        if (row["ppid"] == pid and row["pgid"] == me["pgid"] and len(tokens) > 2
                and tokens[0] == CAFFEINATE and tokens[1] == FLAGS):
            helpers.append(row)
    if len(helpers) != 1:
        raise ValueError("expected exactly one `/usr/bin/caffeinate -ims <command>` helper child of the dispatcher "
                         "in its process group, found " + str(len(helpers)))
    helper = helpers[0]["pid"]
    held = set()
    for line in run(["/usr/bin/pmset", "-g", "assertions"]).splitlines():
        match = _ASSERTION.match(line)
        if match and int(match.group(1)) == helper and match.group(2) == "caffeinate":
            held.add(match.group(3))
    missing = [name for name in REQUIRED_ASSERTIONS if name not in held]
    if missing:
        raise ValueError("caffeinate assertion not held by dispatcher's caffeinate helper: " + ",".join(missing))
    return dict(on_ac=True, dispatcher_pid=pid, caffeinate_helper_pid=helper, assertions=sorted(held))
