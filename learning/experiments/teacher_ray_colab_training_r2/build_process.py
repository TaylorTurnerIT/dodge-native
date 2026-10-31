"""Bound setup/install/compiler process groups without importing a native engine."""
import os
from pathlib import Path
import signal
import subprocess
import time

import common as c
from supervisor import group_resources, exited_without_reaping


def run(command, *, reg, cwd, env, stdout, stderr, deadline,
        resource_probe=group_resources,exit_probe=exited_without_reaping):
    child=None
    try:
        c.check_lease(reg)
        with Path(stdout).open('xb') as output,Path(stderr).open('xb') as errors:
            child=subprocess.Popen(command,cwd=cwd,env=env,stdout=output,stderr=errors,start_new_session=True)
            while not exit_probe(child):
                c.check_lease(reg)
                c.need(time.monotonic()<deadline,'Native setup deadline')
                c.need(sum(resource_probe(child.pid).values())<reg['rss_bytes'],'Native setup6GiB RSS ceiling')
                time.sleep(.25)
            # Keep the leader unreaped while checking for leaked descendants.
            c.need(not resource_probe(child.pid),'Native setup process descendants remain')
            child.wait(timeout=2);c.need(child.returncode==0,'Native setup subprocess failed')
    finally:
        if child is not None and child.returncode is None:
            try:os.killpg(child.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            until=time.monotonic()+2
            while resource_probe(child.pid) and time.monotonic()<until:time.sleep(.02)
            if resource_probe(child.pid):
                try:os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            child.wait(timeout=2)
