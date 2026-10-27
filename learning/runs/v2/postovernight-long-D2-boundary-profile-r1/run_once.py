"""Single invocation, bounded process guardian, immutable command receipt."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import signal
import subprocess
import time

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[3]


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def main():
    plan = json.loads((HERE / 'plan.json').read_text())
    for name, digest in plan['scripts_sha256'].items():
        assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == digest, name
    cache = HERE / 'fresh-pycache'
    cache.mkdir()
    argv = [str(WORKSPACE / 'learning/.venv/bin/python'), '-B', str(HERE / 'profile_once.py')]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPYCACHEPREFIX=str(cache))
    env.pop('PYTORCH_ENABLE_MPS_FALLBACK', None)
    save(HERE / 'command.json', dict(argv=argv, cwd=str(WORKSPACE),
        registered_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        work_cap_seconds=60, emergency_process_guardian_seconds=70,
        environment={name: env[name] for name in ('PYTHONDONTWRITEBYTECODE','PYTHONPYCACHEPREFIX')},
        scripts_sha256=plan['scripts_sha256']))
    started = time.monotonic()
    with (HERE / 'stdout.log').open('xb') as stdout, (HERE / 'stderr.log').open('xb') as stderr:
        process = subprocess.Popen(argv, cwd=WORKSPACE, env=env, stdout=stdout,
                                   stderr=stderr, start_new_session=True)
        guardian = False
        try:
            code = process.wait(timeout=70)
        except subprocess.TimeoutExpired:
            guardian = True
            os.killpg(process.pid, signal.SIGKILL)
            code = process.wait(timeout=2)
    absent = False
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        absent = True
    result = dict(pid=process.pid, returncode=code, direct_child_reaped=True,
                  group_absent=absent, guardian_fired=guardian,
                  elapsed_seconds=time.monotonic() - started,
                  completed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  one_script_invocation=True, retries=0)
    save(HERE / 'wrapper-result.json', result)
    print(json.dumps(result, sort_keys=True), flush=True)
    raise SystemExit(0 if code == 0 and absent and not guardian else 1)


if __name__ == '__main__':
    main()
