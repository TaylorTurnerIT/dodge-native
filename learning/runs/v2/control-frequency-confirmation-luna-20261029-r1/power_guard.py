"""Read-only AC and caffeinate assertion guard for this frozen-policy screen.

Launch must run under `/usr/bin/caffeinate -ims`. Battery power is refused because
this screen has no battery override. The guard changes no OS power setting.
"""
import os
import re
import subprocess

CAFFEINATE = "/usr/bin/caffeinate"
FLAGS = "-ims"
AC_ASSERTIONS = ("PreventUserIdleSystemSleep", "PreventSystemSleep")
BATTERY_ASSERTIONS = ("PreventUserIdleSystemSleep",)
OVERRIDE_FIELDS = {
    "schema": "dodge_uniform2_continuation600_battery_power_override_v1",
    "status": "explicit_user_authorized_battery_execution",
    "user_instruction": "I got plenty of power, do it anyway.",
    "scope": "Exactly the authorized 600-update Uniform2 continuation campaign and its registered evaluations.",
    "ac_power_required": False,
    "caffeinate_required": True,
    "caffeinate_flags": "-ims",
    "required_on_battery_assertions": ["PreventUserIdleSystemSleep"],
    "prevent_system_sleep_assertion_required_only_on_ac": True,
    "other_launch_review_resource_exact_once_seed_and_checkpoint_requirements_unchanged": True,
    "macos_power_settings_changed": False,
}
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


def validate_override(document):
    """Exact record from the parent; only the timestamp is free. Never relaxes anything but AC and `-s` on battery."""
    if type(document) is not dict or {k: v for k, v in document.items() if k != "recorded_at_utc"} != OVERRIDE_FIELDS \
            or type(document.get("recorded_at_utc")) is not str:
        raise ValueError("battery power override record differs")
    return document


def check(run=_run, pid=None, *, override=None):
    """Return a receipt dict or raise ValueError. `run` is injectable for fake tests.

    `override` is the already-hash-verified override document, or None (then battery is refused).
    """
    pid = os.getpid() if pid is None else pid
    source = run(["/usr/bin/pmset", "-g", "batt"]).splitlines()[0]
    if "AC Power" in source:
        on_ac, required = True, AC_ASSERTIONS
    elif "Battery Power" in source:
        if override is None:
            raise ValueError("on battery power and no pinned explicit battery override")
        validate_override(override)
        on_ac, required = False, BATTERY_ASSERTIONS
    else:
        raise ValueError("power source not recognized: " + source)
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
    missing = [name for name in required if name not in held]
    if missing:
        raise ValueError("caffeinate assertion not held by dispatcher's caffeinate helper: " + ",".join(missing))
    return dict(on_ac=on_ac, power_source="AC Power" if on_ac else "Battery Power", battery_override_used=not on_ac,
                dispatcher_pid=pid, caffeinate_helper_pid=helper, required_assertions=list(required),
                assertions=sorted(held))
