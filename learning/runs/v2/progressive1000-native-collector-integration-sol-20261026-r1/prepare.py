"""Copy only Python unit sources and verify explicit input pins; no runtime install."""
from pathlib import Path
import ast
import hashlib
import json
import shutil
import textwrap

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
RUNS = OUT.parent
NATIVE = RUNS / 'progressive1000-native-build-repair-sol-20261026-r2'
COLLECTOR = RUNS / 'progressive1000-collector-identity-parent-20261026-r2'
OLD = RUNS / 'D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime/dodge_rl/_native.cpython-312-darwin.so'
DESIGN = RUNS / 'progressive1000-curriculum-replica-parent-20261026-r3/experiment.json'
ACCEPT = RUNS / 'progressive1000-collector-r2-parent-acceptance-20261026-r1/acceptance.json'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

pins = {
    str(NATIVE / 'extension/final/_native.cpython-312-darwin.so'): '29d49a1317ebe1367932e88514f744242a8e67cf7e6d7d0ab64d5f008cbed567',
    str(OLD): '022d41dde9bace0b4f4c4c06b9b4ed007bc2c60013cd98734086e587d7bb997e',
    str(NATIVE / 'source-manifest.json'): '6a3c3a4c6b884fe59015d4dc299a15883d6dc7f108b55171e1e3dc800cf46aba',
    str(COLLECTOR / 'source-manifest.json'): '16200c082f53f62eb01c068de18ebd826da8d3a06969ce82de1c218c70f9d8f9',
    str(DESIGN): 'c20bd35188c4b4dd36687bc10c7998e6410c70d37300be92db9a42b3d01c43c0',
}
for path, expected in pins.items():
    assert sha(Path(path)) == expected, path
acceptance = json.loads(ACCEPT.read_text())
assert acceptance['status'] == 'accepted_source_for_native_integration_only'
assert acceptance['source_manifest_sha256'] == pins[str(COLLECTOR / 'source-manifest.json')]
pins[str(ACCEPT)] = sha(ACCEPT)
for relative, expected in json.loads((NATIVE / 'source-manifest.json').read_text())['files'].items():
    path = NATIVE / 'source' / relative
    assert sha(path) == expected, path
    pins[str(path)] = expected
for row in json.loads((COLLECTOR / 'source-manifest.json').read_text())['files']:
    path = Path(row['path'])
    assert sha(path) == row['sha256'], path
    pins[str(path)] = row['sha256']
for path in [NATIVE / 'binding_tests.py', ROOT / 'README.md']:
    pins[str(path)] = sha(path)
for name in ['logs', 'results', 'cache', 'tmp', 'extension/final']:
    (OUT / name).mkdir(parents=True, exist_ok=True)
for name in ['successor', 'tests']:
    shutil.copytree(COLLECTOR / name, OUT / name)
shutil.copy2(NATIVE / 'binding_tests.py', OUT / 'binding_controls.py')
(OUT / 'extension/final/manifest.json').write_text(json.dumps({
    'path': str(NATIVE / 'extension/final/_native.cpython-312-darwin.so'),
    'sha256': pins[str(NATIVE / 'extension/final/_native.cpython-312-darwin.so')],
    'reference_only_not_installed_or_copied': True}, indent=2) + '\n')
source = (NATIVE / 'binding_tests.py').read_text()
node = next(n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef) and n.name == 'avoidance_actions')
policy = textwrap.dedent('\n'.join(source.splitlines()[node.lineno-1:node.end_lineno]))
(OUT / 'fixed_policy.py').write_text('"""Fixed observation-only unit policy copied from pinned native binding controls."""\nimport numpy as np\n\n' + policy + '\n')
inputs = {'schema': 'integration_input_pins_v1', 'pins': pins,
    'native_new': str(NATIVE / 'extension/final/_native.cpython-312-darwin.so'),
    'native_old': str(OLD), 'collector': str(COLLECTOR), 'design': str(DESIGN),
    'python': str(ROOT / 'python/.venv/bin/python3.12'),
    'copied_sources': {str(p.relative_to(OUT)): sha(p) for p in OUT.rglob('*.py')},
    'acceptance': acceptance, 'checkpoint_read': False}
(OUT / 'inputs.json').write_text(json.dumps(inputs, indent=2, sort_keys=True) + '\n')
print(json.dumps({'pins_verified': len(pins), 'copied_collector_exact': True, 'owned': str(OUT)}))
