"""First r14 test-child invocation, outside its frozen broken setup wrapper."""
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
ORCH = ROOT / 'learning/runs/v2-orchestration'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def verify(base, entries):
    for name, row in entries.items():
        path = base / name
        digest = row if isinstance(row, str) else row['sha256']
        assert sha(path) == digest, str(path)
        if isinstance(row, dict) and 'bytes' in row:
            assert path.stat().st_size == row['bytes'], str(path)
    return len(entries)


def main():
    sources = read(CANDIDATE / 'source-manifest.json')['files']
    inputs = read(CANDIDATE / 'input-manifest.json')
    counts = dict(source=verify(CANDIDATE, sources),
                  base_inputs=verify(ROOT, inputs['r12_inputs']),
                  additional_inputs=verify(ROOT, inputs['additional_inputs']),
                  evidence=verify(CANDIDATE, read(CANDIDATE / 'evidence-manifest.json')['files']))
    completion = read(CANDIDATE / 'completion-receipt.json')
    assert completion['test_invocations'] == 0
    assert sha(CANDIDATE / 'implementation-result.json') == completion['implementation_result_sha256']
    assert sha(CANDIDATE / 'evidence-manifest.json') == completion['evidence_manifest_sha256']
    precheck = read(CANDIDATE / 'unit-stage/setup-precheck.json')
    assert all(precheck[key] for key in ('existing_methods_exact', 'existing_test_sources_exact',
                                      'input_bindings_all_match', 'original_fixture_exact', 'unique_names'))
    assert len(precheck['planned_tests']) == 143
    assert precheck['unchanged_inherited_methods'] == 108 and precheck['new_methods'] == 31
    stage = HERE / 'unit-stage'
    stage.mkdir()
    fixtures, cache = stage / 'fixtures', stage / 'fresh-pycache'
    fixtures.mkdir()
    cache.mkdir()
    argv = [str(ROOT / 'learning/.venv/bin/python'), '-B', str(CANDIDATE / 'run_unit_suite.py')]
    env = dict(os.environ, VALIDATION_DIR=str(fixtures), PYTHONDONTWRITEBYTECODE='1',
               PYTHONPYCACHEPREFIX=str(cache))
    env.pop('PYTORCH_ENABLE_MPS_FALLBACK', None)
    command = dict(argv=argv, cwd=str(ROOT), timeout_seconds=300, retries=0, failfast=True,
                   registered_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   wrapper_sha256=sha(Path(__file__)), source_manifest_sha256=sha(CANDIDATE / 'source-manifest.json'),
                   verified_members=counts, planned_tests=precheck['planned_tests'],
                   environment={key: env[key] for key in
                                ('VALIDATION_DIR', 'PYTHONDONTWRITEBYTECODE', 'PYTHONPYCACHEPREFIX')},
                   reason='Original r14 setup wrapper failed before command publication or test-child launch. This is the first test invocation; frozen source and original failed setup remain unchanged.')
    save(HERE / 'plan.json', command)
    save(stage / 'command.json', command)
    state = read(ORCH / 'state.json')
    task = state['tasks']['postovernight_long_D2_boundary_repair_r14']
    assert not task['result_ingested']
    task.update(status='completed', workState='result_available', result_ingested=True,
                ingested_at_utc=command['registered_at_utc'], verdict='prepared_source;setup_wrapper_failed;zero_tests',
                parent_validation=str(HERE.relative_to(ROOT)))
    run = state['post_overnight_long_D2_r2']
    assert state['active_long_campaign'] is None and not run['single_use_consumed']
    run.update(status='r14_first_test_invocation_registered_parent_wrapper;training_held',
               r14_source_owner='released_frozen;no_writer',
               r14_parent_validation=str(HERE.relative_to(ROOT)))
    state.update(status='postovernight_long_D2_r2_r14_parent_unit_stage_running;no_active_training',
                 last_update_at_utc=command['registered_at_utc'])
    pending = ORCH / '.state-r14-parent-units.pending.json'
    save(pending, state)
    os.replace(pending, ORCH / 'state.json')
    started = time.monotonic()
    timed_out = False
    with (stage / 'stdout.log').open('xb') as stdout, (stage / 'stderr.log').open('xb') as stderr:
        child = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=stdout, stderr=stderr,
                                 start_new_session=True)
        try:
            code = child.wait(timeout=300)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(child.pid, signal.SIGKILL)
            code = child.wait(timeout=5)
    absent = False
    try:
        os.killpg(child.pid, 0)
    except ProcessLookupError:
        absent = True
    raw = dict(raw_exit=code, elapsed_seconds=time.monotonic() - started,
               timed_out=timed_out, direct_child_reaped=True, group_absent=absent,
               invocations=1, retries=0, pid=child.pid,
               source_members_rechecked=verify(CANDIDATE, sources),
               candidate_source_unchanged=True, cache_empty=not any(cache.iterdir()),
               completed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    save(stage / 'raw-result.json', raw)
    print(json.dumps(raw, sort_keys=True))
    raise SystemExit(0 if code == 0 and not timed_out and absent and raw['cache_empty'] else 1)


if __name__ == '__main__':
    main()
