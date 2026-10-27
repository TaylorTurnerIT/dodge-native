"""Register immutable source and one <=300s fail-fast stdlib invocation."""
from pathlib import Path
import ast
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import time

H = Path(__file__).resolve().parent
ROOT = H.parents[3]
MODULES = ('test_r12', 'test_r11', 'test_r10', 'test_r7', 'test_repairs', 'test_boundary')

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')

def inventory():
    paths = list(H.glob('*.py')) + [H/'protocol-r9-proposal.json', H/'protocol-r8-proposal.json']
    for name in ('original-source', 'r6-source', 'r9-source', 'r10-source', 'r11-source'):
        paths.extend(path for path in (H/name).rglob('*') if path.is_file())
    paths += [H/'retained-r9-injection.json', H/'preparation-copy.json']
    return {str(path.relative_to(H)):dict(sha256=sha(path), bytes=path.stat().st_size) for path in sorted(set(paths))}

def main():
    out = H/'unit-stage'
    out.mkdir()  # Exclusive, never reused.
    result = dict(validation_attempts=0, raw_exit=None, no_retry=True)
    try:
        cache = out/'fresh-pycache'
        cache.mkdir()
        fixtures = out/'fixtures'
        fixtures.mkdir()
        planned = []
        for module in MODULES:
            tree = ast.parse((H/(module+'.py')).read_text())
            for cls in tree.body:
                if isinstance(cls, ast.ClassDef):
                    planned.extend(module+'.'+cls.name+'.'+node.name for node in cls.body
                        if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'))
        for path in H.glob('*.py'):
            compile(path.read_text(), str(path), 'exec')  # Parse only; no candidate import.
        source = inventory()
        save(H/'source-manifest.json', dict(schema='r12_source_manifest_v1', files=source,
            frozen_before_test=True, production_capsule=False))
        source_snapshot = out/'sources'
        source_snapshot.mkdir()
        for name in source:
            target = source_snapshot/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(H/name, target)
        original = json.loads((H/'preparation-copy.json').read_text())['original_fixture_files']
        observed = {path.name:sha(path) for path in (H/'original-source').iterdir() if path.is_file()}
        existing = [name for name in planned if not name.startswith('test_r12.')]
        expected = []
        for module in MODULES[1:]:
            tree = ast.parse((H/'r11-source'/(module+'.py')).read_text())
            for cls in tree.body:
                if isinstance(cls, ast.ClassDef):
                    expected.extend(module+'.'+cls.name+'.'+node.name for node in cls.body
                        if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'))
        inputs = json.loads((H/'input-manifest.json').read_text())['files']
        input_match = {name:sha(Path(name)) == value['sha256'] for name,value in inputs.items()}
        checks = dict(existing_methods_exact=existing == expected and len(existing) == 112,
            new_methods=len(planned)-len(existing), unique_names=len(planned)==len(set(planned)),
            original_fixture_exact=original == observed, input_bindings_all_match=all(input_match.values()),
            cache_empty=not any(cache.iterdir()), fixtures_empty=not any(fixtures.iterdir()),
            no_current_old_envelopes=not any((H/name).exists() for name in
                ('classification.json','long-identity.json','registration.json','capsule-final','required-lease.json')),
            existing_test_sources_exact=all((H/(name+'.py')).read_bytes()==(H/'r11-source'/(name+'.py')).read_bytes() for name in MODULES[1:]),
            planned_tests=planned, input_rechecks=input_match)
        save(out/'setup-precheck.json', checks)
        if not (checks['existing_methods_exact'] and checks['new_methods'] > 0 and checks['unique_names']
                and checks['original_fixture_exact'] and checks['input_bindings_all_match']
                and checks['cache_empty'] and checks['fixtures_empty'] and checks['no_current_old_envelopes']
                and checks['existing_test_sources_exact']):
            raise RuntimeError('Registered setup precheck failed; no test invocation or retry')
        argv = ['learning/.venv/bin/python','-B',str(H/'run_unit_suite.py')]
        env = dict(os.environ, VALIDATION_DIR=str(fixtures), PYTHONDONTWRITEBYTECODE='1',
                   PYTHONPYCACHEPREFIX=str(cache))
        save(out/'command.json', dict(argv=argv,cwd=str(ROOT), timeout_seconds=300,
            registered_at_utc=now(), source_manifest_sha256=sha(H/'source-manifest.json'),
            ordered_modules=list(MODULES), failfast=True, retries=0,
            environment={key:env[key] for key in ('VALIDATION_DIR','PYTHONDONTWRITEBYTECODE','PYTHONPYCACHEPREFIX')},
            other_environment_sha256={key:hashlib.sha256(value.encode()).hexdigest() for key,value in env.items()
                if key not in ('VALIDATION_DIR','PYTHONDONTWRITEBYTECODE','PYTHONPYCACHEPREFIX')},
            historical_static_binding='Four unchanged inherited static methods use exact r11 snapshot and registration constants; all 108 inherited behavioral/source-invariant methods use r12; new exact-delta tests cover r12.'))
        started = time.monotonic()
        result.update(validation_attempts=1, started_at_utc=now())
        with (out/'stdout.log').open('xb') as stdout, (out/'stderr.log').open('xb') as stderr:
            process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=stdout, stderr=stderr)
            try:
                raw = process.wait(timeout=300)
                result.update(raw_exit=raw, timed_out=False)
            except subprocess.TimeoutExpired:
                process.kill()
                raw = process.wait()
                result.update(raw_exit=raw, timed_out=True, termination='300s test bound; no retry')
        result.update(elapsed_seconds=time.monotonic()-started, direct_child_reaped=True,
            completed_at_utc=now(), source_inventory_unchanged=source == inventory(),
            cache_empty=not any(cache.iterdir()))
    except BaseException as error:
        result.update(setup_or_wrapper_error=repr(error), completed_at_utc=now())
    finally:
        save(out/'raw-result.json', result)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result.get('raw_exit') == 0 and not result.get('timed_out')
        and result.get('source_inventory_unchanged') and result.get('cache_empty') else 1)

if __name__ == '__main__':
    main()
