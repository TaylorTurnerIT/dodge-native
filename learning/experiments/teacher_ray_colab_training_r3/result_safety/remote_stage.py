"""Real subprocess wrapper with durable status independent of notebook output."""
import os
import signal
import subprocess
import time

from .custody import canonical, durable_new, identity, real_directory
from .lifecycle import stage_result


def group_absent(pgid):
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def run_stage_child(command, root, expected, *, guard, seconds, terminal_export,
                    clock=time.monotonic, pause=time.sleep, failure_export=None):
    """Exactly one subprocess; this function never retries work or copies."""
    root = real_directory(root)
    durable_new(root / "stage.claimed", canonical(identity(expected)))
    process, export, failure, code = None, None, None, None
    deadline = clock() + seconds
    try:
        guard()
        with (root / "stage.stdout").open("xb") as stdout, (root / "stage.stderr").open("xb") as stderr:
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=True)
            while process.poll() is None:
                guard()
                if clock() >= deadline:
                    raise TimeoutError("Remote stage deadline")
                pause(.05)
            code = process.wait()
            stdout.flush(); os.fsync(stdout.fileno())
            stderr.flush(); os.fsync(stderr.fileno())
        guard()
        if code == 0 and group_absent(process.pid):
            export = terminal_export()
    except BaseException as error:
        failure = type(error).__name__
    finally:
        if process is not None:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
            code = process.wait()
        if failure_export is not None:
            try:failure_export()
            except BaseException:pass
        if code != 0 or failure is not None or export is None:
            durable_new(root / "stage-first-failure.json", canonical(dict(identity(expected),
                        exception_type=failure, observed_exit_code=code, campaign_success=False)))
        result = stage_result(root / "stage-exit.json", expected,
                              returncode=-1 if code is None else code,
                              directly_reaped=process is not None,
                              owned_group_absent=process is not None and group_absent(process.pid),
                              export=export if failure is None else None)
    return result
