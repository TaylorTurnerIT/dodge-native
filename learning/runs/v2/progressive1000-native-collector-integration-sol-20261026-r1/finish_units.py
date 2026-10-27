"""Retain failed first harness; rerun only its repaired fake-control import.

Never reruns parity, native integration or passed binding controls. No source
changes to copied accepted collector/tests. Aggregate child wall remains <300s.
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
INITIAL = json.loads((OUT / 'invocation.json').read_text())

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def compare():
    old = json.loads((OUT / 'results/parity-old.json').read_text())
    new = json.loads((OUT / 'results/parity-new.json').read_text())
    assert old['complete'] and new['complete']
    comparisons = []
    for a, b in zip(old['cases'], new['cases'], strict=True):
        comparisons.append({'difficulty': a['difficulty'], 'layout': a['layout'],
            'exact': a == b, 'old_digest': a['rolling_digest'], 'new_digest': b['rolling_digest'],
            'decisions': len(a['steps']), 'deaths': a['deaths'], 'caps': a['caps'], 'resets': a['resets']})
    report = {'comparisons': comparisons, 'all_exact': all(r['exact'] for r in comparisons),
        'method': 'complete per-case equality, typed array dtype/shape/C-byte hashes, scalar hex floats, every-step/reset and batch metadata',
        'limits': 'finite descriptive unit trajectories only; no global source-to-binary correspondence or training qualification',
        'cutoff_calls': old['cutoff_calls'] + new['cutoff_calls'],
        'seed_action_inputs_exact': old['seed_lists'] == new['seed_lists'] and old['action_vectors'] == new['action_vectors']}
    write('results/parity-comparison.json', report)
    assert report['all_exact'] and report['seed_action_inputs_exact'] and report['cutoff_calls'] == 0
    return report

assert sys.version_info[:3] == (3, 12, 15)
assert not (OUT / 'repair-invocation.json').exists(), 'repair already consumed'
assert INITIAL['commands'][-1]['name'] == 'fake-controls' and INITIAL['commands'][-1]['exit_code'] == 1
assert 'ModuleNotFoundError' in (OUT / 'logs/fake-controls.log').read_text()
for row in INITIAL['commands'][:-1]:
    assert row['exit_code'] == 0 and row['group_absent']
parity = compare()  # Read existing outputs only; no native process rerun.
prior_wall = sum(r['wall_seconds'] for r in INITIAL['commands'])
argv = [INPUTS['python'], '-I', '-B', str(OUT / 'repairs/control-import-r1/controls_driver.py'), 'fake']
env = dict(os.environ, **INITIAL['environment_overrides'])
report = {'at_utc': datetime.now(timezone.utc).isoformat(), 'argv': argv,
    'cwd': str(OUT), 'deadline_seconds': min(120, 300-prior_wall),
    'preserved_first_failure': 'logs/first-failure.log', 'repair_diff': 'repairs/control-import-r1.diff',
    'rerun_scope': 'fake controls only, corrected import path', 'native_repeated': False,
    'prior_child_wall_seconds': prior_wall, 'complete': False,
    'driver_sha256': sha(OUT / 'repairs/control-import-r1/controls_driver.py')}
write('repair-invocation.json', report)
start = time.monotonic()
try:
    with (OUT / 'logs/fake-controls-repaired.log').open('xb') as log:
        process = subprocess.Popen(argv, cwd=OUT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        report['pid'] = report['process_group'] = process.pid
        try:
            report['exit_code'] = process.wait(timeout=report['deadline_seconds'])
        except subprocess.TimeoutExpired:
            report['timed_out'] = True
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
                report['group_cleanup'] = 'SIGKILL sent to owned group'
            except ProcessLookupError:
                report['group_cleanup'] = 'owned group already absent'
            if process.poll() is None:
                process.wait(timeout=5)
            try:
                os.killpg(process.pid, 0)
                report['group_absent'] = False
            except ProcessLookupError:
                report['group_absent'] = True
            report['exit_code'] = process.returncode
    assert report['exit_code'] == 0 and report['group_absent'] and not report.get('timed_out')
    for path, expected in INPUTS['pins'].items():
        assert sha(path) == expected, path
    for relative, expected in INPUTS['copied_sources'].items():
        assert sha(OUT / relative) == expected, relative
    report['postflight'] = {'all_64_listed_input_pins_match': True,
        'original_collector_copies_unchanged': True}
    report['complete'] = True
except BaseException:
    report['repair_failure'] = traceback.format_exc()
    raise
finally:
    report['wall_seconds'] = time.monotonic()-start
    report['aggregate_child_wall_seconds'] = prior_wall + report['wall_seconds']
    assert report['aggregate_child_wall_seconds'] < 300
    write('repair-invocation.json', report)
    print(json.dumps(report), flush=True)
