"""One bounded sequential CPU unit attempt with own process-group cleanup.

No automatic retries. Results and first failure survive a stop. The 300-second
budget covers all child execution and comparison, not source preparation.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import traceback

OUT = Path(__file__).resolve().parent
INPUTS = json.loads((OUT / 'inputs.json').read_text())
PLAN = json.loads((OUT / 'plan.json').read_text())

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def verify_inputs():
    checked = {path: sha(path) for path in INPUTS['pins']}
    assert checked == INPUTS['pins'], 'protected listed input changed'
    for relative, expected in INPUTS['copied_sources'].items():
        assert sha(OUT / relative) == expected, relative
    return {'verified_count': len(checked), 'all_match': True}

assert sys.version_info[:3] == (3, 12, 15), sys.version
assert Path(sys.executable).absolute() == Path(INPUTS['python']).absolute(), sys.executable
assert not (OUT / 'invocation.json').exists(), 'unit attempt already recorded; no automatic retry'
pre = verify_inputs()
commands = [
    ('parity-old', 'parity_driver.py', 'old'),
    ('parity-new', 'parity_driver.py', 'new'),
    ('actual-integration', 'integration_driver.py'),
    ('binding-controls', 'controls_driver.py', 'binding'),
    ('fake-controls', 'controls_driver.py', 'fake'),
]
environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPYCACHEPREFIX=str(OUT / 'cache'),
    TMPDIR=str(OUT / 'tmp'), OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
    VECLIB_MAXIMUM_THREADS='1', PYTORCH_ENABLE_MPS_FALLBACK='0')
report = {'schema': 'bounded_cpu_unit_invocation_v1', 'at_utc': datetime.now(timezone.utc).isoformat(),
    'python': sys.version, 'executable': sys.executable, 'process_deadline_seconds': 120,
    'total_child_wall_cap_seconds': 300, 'commands': [], 'complete': False,
    'preflight': pre, 'plan_sha256': sha(OUT / 'plan.json'),
    'environment_overrides': {k: environment[k] for k in ('PYTHONDONTWRITEBYTECODE', 'PYTHONPYCACHEPREFIX',
        'TMPDIR', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
        'VECLIB_MAXIMUM_THREADS', 'PYTORCH_ENABLE_MPS_FALLBACK')},
    'source_hashes': {str(p.relative_to(OUT)): sha(p) for p in OUT.rglob('*.py')}}
start = time.monotonic()
write('invocation.json', report)
try:
    for name, script, *args in commands:
        remaining = 300 - (time.monotonic()-start)
        if remaining <= 0:
            raise TimeoutError('aggregate unit wall budget exhausted before ' + name)
        deadline = min(120, remaining)
        argv = [INPUTS['python'], '-I', '-B', str(OUT / script), *args]
        row = {'name': name, 'argv': argv, 'cwd': str(OUT), 'deadline_seconds': deadline,
            'log': 'logs/' + name + '.log'}
        report['commands'].append(row)
        write('invocation.json', report)
        child_start = time.monotonic()
        with (OUT / row['log']).open('xb') as log:
            process = subprocess.Popen(argv, cwd=OUT, env=environment, stdout=log,
                stderr=subprocess.STDOUT, start_new_session=True)
            row['pid'] = row['process_group'] = process.pid
            try:
                row['exit_code'] = process.wait(timeout=deadline)
            except subprocess.TimeoutExpired:
                row['timed_out'] = True
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                    row['group_cleanup'] = 'SIGKILL sent to owned group'
                except ProcessLookupError:
                    row['group_cleanup'] = 'owned group already absent'
                if process.poll() is None:
                    process.wait(timeout=5)
                try:
                    os.killpg(process.pid, 0)
                    row['group_absent'] = False
                except ProcessLookupError:
                    row['group_absent'] = True
                row['exit_code'] = process.returncode
                row['wall_seconds'] = time.monotonic()-child_start
                write('invocation.json', report)
        print(json.dumps(row), flush=True)
        assert not row.get('timed_out') and row['exit_code'] == 0 and row['group_absent'], row
    old = json.loads((OUT / 'results/parity-old.json').read_text())
    new = json.loads((OUT / 'results/parity-new.json').read_text())
    assert old['complete'] and new['complete']
    comparisons = []
    for a, b in zip(old['cases'], new['cases'], strict=True):
        # Everything in each case is binary-independent: compare complete
        # metadata, every typed array digest, resets and rolling trajectory.
        same = a == b
        comparisons.append({'difficulty': a['difficulty'], 'layout': a['layout'],
            'exact': same, 'old_digest': a['rolling_digest'], 'new_digest': b['rolling_digest'],
            'decisions': len(a['steps']), 'deaths': a['deaths'], 'caps': a['caps'], 'resets': a['resets']})
        write('results/parity-comparison.json', {'comparisons': comparisons, 'all_exact': all(r['exact'] for r in comparisons)})
        assert same, 'finite old/new trajectory mismatch; preserve results, no retries'
    assert old['seed_lists'] == new['seed_lists'] and old['action_vectors'] == new['action_vectors']
    assert old['cutoff_calls'] == new['cutoff_calls'] == 0
    report['postflight'] = verify_inputs()
    report['complete'] = True
except BaseException:
    report['first_failure'] = traceback.format_exc()
    (OUT / 'logs/first-failure.log').write_text(report['first_failure'])
    raise
finally:
    report['total_wall_seconds'] = time.monotonic()-start
    write('invocation.json', report)
