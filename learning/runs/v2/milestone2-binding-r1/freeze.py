"""Freeze reviewable sources, installed native identity, and bounded check receipts."""
from __future__ import annotations
import datetime
import difflib
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile

import dodge_rl
import dodge_rl._native as native

root = Path.cwd()
out = Path(__file__).resolve().parent

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(name, value):
    (out / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

owned = [Path('Cargo.lock'), Path('crates/dodge-rl-env/Cargo.toml')]
owned += [Path(f'crates/dodge-rl-env/src/{name}.rs') for name in
          ['lib', 'config', 'seed', 'env', 'python', 'seed_extension_tests', 'seed_reservation_tests']]
owned += [Path(p) for p in ['python/pyproject.toml','python/dodge_rl/__init__.py','python/tests/test_env.py']]
input_manifest = json.loads((out/'input-manifest.json').read_text())
owned_names = {str(p) for p in owned}
changes = {p: {'before': old, 'after': digest(p)} for p, old in input_manifest.items()
           if p not in owned_names and digest(p) != old}
# The app's orchestration ledger is shared dynamic state, never owned or edited here.
source_changes = {p: change for p, change in changes.items() if p != 'learning/runs/v2-orchestration/state.json'}
assert not source_changes, source_changes
write('frozen-input-audit.json', {'unowned_source_changes': source_changes,
      'externally_changed_dynamic_inputs': changes,
      'frozen_unowned_files_checked': len(set(input_manifest) - owned_names)})
write('owned-source-manifest.json', {str(p): digest(p) for p in owned})
# Inventory the entire effective crate plus its frozen inputs and Python sources.
paths = set(Path(p) for p in input_manifest) | set(owned)
paths.remove(Path('learning/runs/v2-orchestration/state.json'))
paths.update(p for p in Path('crates/dodge-rl-env').rglob('*') if p.is_file())
write('source-manifest.json', {str(p): digest(p) for p in sorted(paths)})
with tarfile.open(out/'source-final.tar.gz', 'w:gz') as archive:
    for p in sorted(paths):
        archive.add(p, arcname=str(p), recursive=False)
patch = []
with tarfile.open(out/'inputs.tar.gz', 'r:gz') as archive:
    initial_names = set(archive.getnames())
    for p in owned:
        before = archive.extractfile(str(p)).read().decode() if str(p) in initial_names else ''
        patch.extend(difflib.unified_diff(before.splitlines(True), p.read_text().splitlines(True),
                     fromfile='before/'+str(p) if before else '/dev/null', tofile='after/'+str(p)))
(out/'owned-changes.patch').write_text(''.join(patch))

native_path = Path(native.__file__).resolve()
assert native_path.is_relative_to(root/'python/dodge_rl')
binary_out = out/'binary'
binary_out.mkdir(exist_ok=True)
shutil.copy2(native_path, binary_out/native_path.name)
wheels = []
for wheel in sorted((out/'wheels').glob('*.whl')):
    with zipfile.ZipFile(wheel) as archive:
        extension_names = [n for n in archive.namelist() if n.endswith('.so')]
        assert len(extension_names) == 1
        extension_hash = hashlib.sha256(archive.read(extension_names[0])).hexdigest()
        assert extension_hash == digest(native_path)
    wheels.append({'path':str(wheel.relative_to(root)), 'sha256':digest(wheel),
                   'extension_member':extension_names[0], 'extension_sha256':extension_hash})
identity = {
    'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'python':sys.version, 'python_executable':sys.executable,
    'platform':platform.platform(), 'package_import_path':dodge_rl.__file__,
    'extension_import_path':str(native_path), 'extension_sha256':digest(native_path),
    'extension_archive_path':str((binary_out/native_path.name).relative_to(root)),
    'packages':{p:importlib.metadata.version(p) for p in ['dodge-rl','numpy','torch','pytest','maturin']},
    'rustc':subprocess.check_output(['rustc','+1.97.1','-Vv'],text=True),
    'cargo':subprocess.check_output(['cargo','+1.97.1','-V'],text=True).strip(),
    'rust_toolchain_sha256':digest('rust-toolchain.toml'),
    'cargo_lock_sha256':digest('Cargo.lock'),
    'wheels':wheels,
    'git_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
    'git_status':subprocess.check_output(['git','status','--short'],text=True),
    'installed_metadata_files':{p:str(importlib.metadata.distribution('dodge-rl').read_text(p))
                              for p in ['METADATA','direct_url.json']},
}
write('installed-identity.json',identity)
write('rust-locked-packages.json', tomllib.loads(Path('Cargo.lock').read_text())['package'])
commands = [json.loads(line) for line in (out/'commands.jsonl').read_text().splitlines()]
final_labels = ['build-python-final-r2','pytest-final-r2','rust-default-final-r2','fmt-final-r2','clippy-final-r2','wheel-final-r2']
manifest = json.loads((out/'owned-source-manifest.json').read_text())
for label in final_labels:
    record = next(r for r in commands if r['label']==label)
    assert record['exit_code'] == 0, label
    for p, old in record['source_sha256'].items():
        assert digest(p)==old, (label,p)
failures = [
 {'label':'freeze-r1', 'kind':'receipt_scope_assertion', 'exit_code':1,
  'detail':'Freeze checker compared Python test hashes captured during Clippy before the final input-copy test was added. Rust source was unchanged. Retained failing freeze script, then refreshed final Clippy receipt against complete final source.'},
 {'label':'build-python-r1', 'kind':'packaging_config_not_discovered',
  'exit_code':0, 'detail':'Invoking maturin from root with only --manifest-path missed python/pyproject.toml and emitted a missing PyInit_dodge_rl_env warning. Removed only that local venv package, then rebuilt from python/. Logs retained.'},
 {'label':'pytest-r1','kind':'incorrect_test_assumption','exit_code':1,
  'detail':'61 passed before assertion that neutral terminal global features must differ from fresh globals. Neutral position and zero score can match. Corrected test to compare entity features; no gameplay change.'},
 {'label':'clippy-r1','kind':'test_only_observer_not_sync','exit_code':101,
  'detail':'cfg(test) raw observer closures are Send-only. Binding module registration now excludes only the Rust unit-test artifact. Normal library all-feature Clippy and real extension compile/check binding code. Frozen observer/test sources unchanged.'},
 {'label':'initial-input-audit','kind':'external_dynamic_ledger_drift','exit_code':1,
  'detail':'Inline assertion found only orchestration state.json changed since input freeze. Never edited here. Final frozen-input-audit.json separates dynamic ledger drift from unchanged frozen sources.'},
]
write('failure-ledger.json', {'failures':failures,
      'evidence_limitations':['Intermediate extension binaries from early develop builds were overwritten before independent binary hashes/archives were captured. Their source hashes and full build/test logs are retained; only final installed binary and matching wheel are archived.']})
summary = {
 'status':'implementation_complete_ready_for_independent_parent_audit',
 'at_utc':identity['at_utc'],
 'tests':{'rust_unit_passed':41,'rust_primitive_passed':35,'rust_ignored_replay':1,
          'rust_doc_tests':0,'python_passed':68,
          'whole_workspace_tests_executed':False,
          'whole_workspace_all_targets_all_features_clippy':'passed','workspace_fmt':'passed'},
 'input_acceptance_sha256':input_manifest['learning/runs/v2-orchestration/milestone2-wrapper-acceptance-r2.json'],
 'features_sha256':digest('crates/dodge-rl-env/src/features.rs'),
 'original_tests_sha256':digest('crates/dodge-rl-env/src/tests.rs'),
 'extension_import_path':identity['extension_import_path'],
 'extension_sha256':identity['extension_sha256'],
 'cargo_lock_sha256':identity['cargo_lock_sha256'],
 'source_archive_sha256':digest(out/'source-final.tar.gz'),
 'owned_patch_sha256':digest(out/'owned-changes.patch'),
 'long_campaigns_executed':False,'teacher_or_student_work':False,
 'remaining':['independent parent Codex audit of binding and separate harness',
              'one parent-owned bounded 100k postwarmup memory/throughput campaign',
              'full 1000 paired heuristic episodes at D2 and D3'],
 'evidence_limitations':json.loads((out/'failure-ledger.json').read_text())['evidence_limitations'],
}
write('result.json',summary)
print(json.dumps(summary,indent=2))
