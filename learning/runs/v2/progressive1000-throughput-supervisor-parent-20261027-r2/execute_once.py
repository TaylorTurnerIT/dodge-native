"""Adapted D2 one-use launcher. Parent owns marker, lease and acceptance.

Only control files are written here. The accepted worker creates its own output.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback
import binding as r
import terminal

def group_exists(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # A group exists even when the kernel temporarily denies the probe.
        # Never turn unknown/denied permission into evidence of absence.
        return True


def stop_owned(process, *, send=None, deadline=None):
    """Existing five-second TERM, five-second KILL policy on exact owned group."""
    r.need(type(process.pid) is int and process.pid > 1 and process.pid != os.getpgrp(),
           "Refusing unsafe process group")
    result = {"owned_pid": process.pid, "owned_pgid": process.pid, "errors": []}
    for sig, wait_seconds in ((signal.SIGTERM, 5), (signal.SIGKILL, 5)):
        if deadline is not None:
            wait_seconds = min(wait_seconds, max(0, deadline-time.monotonic()))
        signal_started = time.monotonic()
        group_gone = False
        try:
            if send is None:
                os.killpg(process.pid, sig)
            else:
                send(sig)
            result[signal.Signals(sig).name] = True
        except ProcessLookupError:
            group_gone = True
        except BaseException as error:
            result["errors"].append(repr(error))
        if sig == signal.SIGTERM:
            # Keep the direct child unreaped for the entire TERM grace. Even an
            # exited leader pins the original group while descendants survive.
            # No wait/poll (and no platform-specific waitid) before escalation.
            try:
                if not group_gone:
                    time.sleep(max(0, wait_seconds-(time.monotonic()-signal_started)))
            except BaseException as error:
                result["errors"].append(repr(error))
            continue
        try:
            process.wait(timeout=wait_seconds)
        except BaseException as error:
            result["errors"].append(repr(error))
        # KILL already used the retained ownership pin. Reap the direct child,
        # then allow owned orphan descendants to disappear within the same grace.
        while group_exists(process.pid) and time.monotonic()-signal_started < wait_seconds:
            time.sleep(min(.01,max(0,wait_seconds-(time.monotonic()-signal_started))))
    result.update(exit_code=process.poll(), reaped=process.poll() is not None)
    return result


def execute(envelope_path, envelope_sha, **kwargs):
    """Compatibility entry point: the observer directly owns the worker now."""
    from observe import main
    return main(envelope_path, envelope_sha, **kwargs)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--envelope', required=True)
    parser.add_argument('--envelope-sha256', required=True)
    args = parser.parse_args()
    raise SystemExit(execute(args.envelope, args.envelope_sha256))
