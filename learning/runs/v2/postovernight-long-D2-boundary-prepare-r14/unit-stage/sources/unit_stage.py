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
MODULES = ('test_r14', 'test_r11', 'test_r10', 'test_r7', 'test_repairs', 'test_boundary')

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')

def inventory():
    paths = list(H.glob('*.py')) + [H/'protocol-r10-proposal.json', H/'protocol-r9-proposal.json', H/'protocol-r8-proposal.json']
    for name in ('original-source', 'r6-source', 'r9-source', 'r10-source', 'r11-source', 'r12-source'):
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
        save(H/'source-manifest.json', dict(schema='r14_source_manifest_v1', files=source,
            frozen_before_test=True, production_capsule=False))
        source_snapshot = out/'sources'
        source_snapshot.mkdir()
        for name in source:
            target = source_snapshot/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(H/name, target)
        original = json.loads((H/'preparation-copy.json').read_text())['original_fixture_files']
        observed = {path.name:sha(path) for path in (H/'original-source').iterdir() if path.is_file()}
        existing = [name for name in planned if not name.startswith('test_r14.')]
        expected = []
        for module in MODULES[1:]:
            tree = ast.parse((H/'r11-source'/(module+'.py')).read_text())
            for cls in tree.body:
                if isinstance(cls, ast.ClassDef):
                    expected.extend(module+'.'+cls.name+'.'+node.name for node in cls.body
                        if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'))
        manifest = json.loads((H/'input-manifest.json').read_text())
        inputs = dict(manifest['r12_inputs'], **{k:dict(sha256=v) for k,v in manifest['additional_inputs'].items()})
        input_match = {name:sha(Path(name)) == value['sha256'] for name,value in inputs.items()}
        migrated = {'test_r11': ['test_C01_exact_success_consumers_transport_inner_fixtures_and_old91','test_C02_protocol_only_candidate_paths_and_qualified_semantics'],
                    'test_r10': ['test_exact_r9_transport_success_consumers_protected_blocks'],
                    'test_r7': ['test_success_consumers_and_protected_failure_helpers_byte_equal']}
        def method_texts(path):
            text = path.read_text(); tree = ast.parse(text); lines = text.splitlines(True); found = {}
            for cls in tree.body:
                if isinstance(cls, ast.ClassDef):
                    for node in cls.body:
                        if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
                            found[cls.name+'.'+node.name] = ''.join(lines[node.lineno-1:node.end_lineno])
            return text, lines, found
        migrated_ok = True; changed_methods = []; unchanged_count = 0
        for module in MODULES[1:]:
            now_text, now_lines, now = method_texts(H/(module+'.py'))
            old_text, old_lines, old = method_texts(H/'r12-source'/(module+'.py'))
            migrated_ok &= list(now) == list(old)
            for key in now:
                if now[key] == old[key]: unchanged_count += 1
                else: changed_methods.append(module+'.'+key)
            def strip(text, lines, found, names):
                out = text
                for key in names: out = out.replace(found[key], '', 1)
                return out
            names = [k for k in now if k.split('.')[1] in migrated.get(module, [])]
            migrated_ok &= strip(now_text, now_lines, now, names) == strip(old_text, old_lines, old, names)
            if module not in migrated:
                migrated_ok &= now_text == old_text
        expected_changed = sorted(m+'.'+('R11' if m=='test_r11' else 'R10' if m=='test_r10' else 'R7')+'.'+n for m, ns in migrated.items() for n in ns)
        migrated_ok &= sorted(changed_methods) == expected_changed and unchanged_count == 108
        checks = dict(changed_inherited_methods=sorted(changed_methods), unchanged_inherited_methods=unchanged_count,
            existing_methods_exact=existing == expected and len(existing) == 112,
            new_methods=len(planned)-len(existing), unique_names=len(planned)==len(set(planned)),
            original_fixture_exact=original == observed, input_bindings_all_match=all(input_match.values()),
            cache_empty=not any(cache.iterdir()), fixtures_empty=not any(fixtures.iterdir()),
            no_current_old_envelopes=not any((H/name).exists() for name in
                ('classification.json','long-identity.json','registration.json','capsule-final','required-lease.json')),
            existing_test_sources_exact=migrated_ok,
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
            migrated_static_methods='Four named inherited static methods have explicitly migrated expectations and run against the current r14 candidate; 108 inherited method bodies byte-identical to r12/r11; no historical-target rebinding.'))
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
