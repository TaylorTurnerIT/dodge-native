"""One unchanged startup helper, with an isolated validation cache and guardian."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import signal
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CANDIDATE = ROOT / 'learning/runs/v2/postovernight-long-D2-boundary-prepare-r14'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def main():
    stress = read(CANDIDATE / 'attempts/attempt-05-changed-source-stress/stress/stress-result.json')
    assert stress['status'] == 'passed' and len(stress['boundaries']) == 13
    assert all(row['verdict'] == 'passed' for row in stress['boundaries'])
    pins = read(CANDIDATE / 'parent-frozen-pins.json')
    for name, digest in pins.items():
        assert sha(ROOT / name) == digest, name
    assert not any((CANDIDATE / 'production-pycache-prefix').iterdir())
    stage = HERE / 'startup-stage'
    stage.mkdir()
    cache = stage / 'validation-only-pycache'
    cache.mkdir()
    manifest = dict(output=str(stage / 'output'), validation_only_pycache_prefix=str(cache),
                    helper_sha256=sha(CANDIDATE / 'rehearsal.py'))
    manifest_path = stage / 'manifest.json'
    save(manifest_path, manifest)
    argv = [str(ROOT / 'learning/.venv/bin/python'), '-B', str(CANDIDATE / 'rehearsal.py'),
            str(manifest_path)]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPYCACHEPREFIX=str(cache))
    env.pop('PYTORCH_ENABLE_MPS_FALLBACK', None)
    command = dict(argv=argv, cwd=str(ROOT), registered_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   work_seconds=120, emergency_guardian_seconds=130, invocations=1, retries=0,
                   wrapper_sha256=sha(Path(__file__)), frozen_pins=pins,
                   manifest_sha256=sha(manifest_path),
                   environment={key: env[key] for key in ('PYTHONDONTWRITEBYTECODE', 'PYTHONPYCACHEPREFIX')},
                   unset_environment=['PYTORCH_ENABLE_MPS_FALLBACK'],
                   scope='Real imports/origins/unchanged check_frozen; architecture-only constructor with original RNG preservation. No D1 decode, environment, inference, gradients, optimizer or training.',
                   guardian_scope='Only failed shutdown/publication; helper owns unchanged 120-second work deadline.')
    save(stage / 'command.json', command)
    started = time.monotonic()
    guardian = False
    with (stage / 'stdout.log').open('xb') as stdout, (stage / 'stderr.log').open('xb') as stderr:
        child = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=stdout, stderr=stderr,
                                 start_new_session=True)
        try:
            code = child.wait(timeout=130)
        except subprocess.TimeoutExpired:
            guardian = True
            os.killpg(child.pid, signal.SIGKILL)
            code = child.wait(timeout=5)
    absent = False
    try:
        os.killpg(child.pid, 0)
    except ProcessLookupError:
        absent = True
    after = {name: sha(ROOT / name) == digest for name, digest in pins.items()}
    result = dict(raw_exit=code, elapsed_seconds=time.monotonic() - started,
                  guardian_fired=guardian, direct_child_reaped=True, group_absent=absent,
                  pid=child.pid, invocations=1, retries=0, frozen_pin_rechecks=after,
                  validation_cache_empty=not any(cache.iterdir()),
                  production_cache_empty=not any((CANDIDATE / 'production-pycache-prefix').iterdir()),
                  completed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    save(stage / 'raw-result.json', result)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if code == 0 and not guardian and absent and all(after.values())
                     and result['validation_cache_empty'] and result['production_cache_empty'] else 1)


if __name__ == '__main__':
    main()
