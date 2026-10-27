"""Declared observations, not continuous immutability or memory attestation.

The external registration and parent-held launch digest anchor the root DAG.
Leaf manifests never include themselves, identity, capsule manifest, or registration.
Only an endpoint pass reads archive and installed native bytes.
"""
from pathlib import Path
import importlib.machinery
import os
import sys
import time
import lifecycle as life


def need(ok, message):
    if not ok:
        raise life.Stop(message)


def merge_bindings(*maps):
    result, canonical = {}, {}
    for values in maps:
        for name, digest in values.items():
            path = Path(name)
            need(path.is_absolute() and '..' not in path.parts, 'Noncanonical input binding: '+name)
            resolved = str(path.resolve())
            need(name not in result or result[name] == digest, 'Conflicting path binding: '+name)
            need(resolved not in canonical or canonical[resolved] == digest, 'Conflicting canonical binding: '+name)
            result[name] = canonical[resolved] = digest
    return result


def project_members(root):
    paths = set()
    for base in (root/'python/dodge_rl', root/'python/tests', root/'crates'):
        for path in base.rglob('*'):
            relative = path.relative_to(base)
            if path.is_file() and not {'__pycache__','.pytest_cache','target','build'}.intersection(relative.parts):
                if base.name == 'dodge_rl' or path.suffix in {'.py','.rs','.toml','.lock'}:
                    need(not path.is_symlink(), 'Project source symlink: '+str(path))
                    paths.add(str(path.relative_to(root)))
    return paths


def native_members(roots):
    values = set()
    for root in map(Path, roots):
        need(root.is_dir(), 'Native root missing: '+str(root))
        for path in root.rglob('*'):
            if path.is_file() and (path.suffix.lower() in {'.so','.dylib','.pyd','.dll'} or '.so.' in path.name):
                values.add(str(path))
    return values


def cache_check(policy):
    prefix = Path(policy['pycache_prefix'])
    need(prefix.is_absolute() and prefix.resolve() == prefix and prefix.is_dir() and not prefix.is_symlink(), 'Cache prefix noncanonical/missing')
    need(sys.pycache_prefix == str(prefix) and os.environ.get('PYTHONPYCACHEPREFIX') == str(prefix), 'Cache prefix not installed at interpreter startup')
    need(sys.dont_write_bytecode and os.environ.get('PYTHONDONTWRITEBYTECODE') == '1', 'Bytecode write policy differs')
    need(not any(prefix.iterdir()), 'Registered cache prefix polluted')
    return dict(prefix=str(prefix), empty=True, startup_prefix=True, dont_write_bytecode=True)


def runtime_check(identity, root, *, modules=None, paths=None, imported=None, cache_policy=None):
    """Inspect every loaded extension, including unexpected lazy extensions."""
    policy = identity['runtime_policy']
    cache = cache_check(policy if cache_policy is None else cache_policy)
    modules = sys.modules if modules is None else modules
    project_loaded = 'dodge_rl' in modules if imported is None else imported
    actual = list(sys.path if paths is None else paths)
    expected = policy['sys_path_after_project'] if project_loaded else policy['sys_path_before_project']
    need(actual == expected, 'Canonical sys.path differs: '+repr(actual))
    for key, value in policy['environment'].items():
        need(os.environ.get(key) == value, 'Runtime environment differs: '+key)
    need(str(Path(sys.executable).resolve()) == policy['interpreter'], 'Runtime interpreter differs')
    need(sys.version == policy['python'], 'Runtime Python version differs')
    native = {}
    allowed = identity['native_origins']
    project_packages = {}
    for name, module in tuple(modules.items()):
        if name == 'dodge_rl' or name.startswith('dodge_rl.'):
            if hasattr(module, '__path__'):
                current = list(map(str, module.__path__))
                expected_path = str(root/'python'/Path(*name.split('.')))
                need(current == [expected_path], 'Project __path__ differs: '+name)
                project_packages[name] = current
        origin = getattr(module, '__file__', None)
        if origin is not None and any(str(origin).endswith(s) for s in importlib.machinery.EXTENSION_SUFFIXES):
            path = str(Path(origin).resolve())
            need(path in allowed, 'Unregistered loaded native origin: '+name+':'+path)
            native[name] = dict(origin=path, sha256=allowed[path])
    metadata = dict(python=sys.version, interpreter=policy['interpreter'])
    if project_loaded:
        torch, numpy = modules.get('torch'), modules.get('numpy')
        need(torch is not None and numpy is not None, 'ML runtime metadata unavailable')
        need(str(torch.__version__) == policy['torch'] and numpy.__version__ == policy['numpy'], 'ML version differs')
        need(torch.get_num_threads() == 4 and torch.backends.mps.is_available(), 'MPS/thread policy differs')
        need(not os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK'), 'MPS fallback forbidden')
        metadata.update(torch=str(torch.__version__), numpy=numpy.__version__, threads=4, mps_available=True)
    return dict(verdict='passed', cache=cache, sys_path=actual, project_packages=project_packages,
                native_origins=native, runtime=metadata, whole_OS_or_memory_attestation=False)


def verify(context, root, *, endpoint=None):
    import long_d2 as c
    p, config, base, identity, pins, lease = context
    start = time.monotonic()
    classification = c.read_json(root/c.PREPARE_REL/'classification.json')
    need(c.sha(root/c.PREPARE_REL/'classification.json') == identity['classification_sha256'], 'Classification root differs')
    c.verify_files(pins)  # B leaf bytes and explicit root envelopes, never R/A members.
    c.assert_readonly_capsule(root, c.read_json(root/'capsule-manifest.json'))
    expected_project = {name for name in base_source_names(identity) if name.startswith(('python/dodge_rl/','python/tests/','crates/'))}
    need(project_members(c.ORIGINAL_ROOT) == expected_project, 'Project membership changed')
    result = dict(schema='long_d2_integrity_observation_v1', role='boundary' if endpoint is None else 'outer_'+endpoint,
                  verdict='passed', classification_sha256=identity['classification_sha256'],
                  manifests=identity['class_manifest_hashes'], counts={'B':len(classification['B'])},
                  root_envelope_count=len(pins)-len(classification['B']), start_monotonic=start)
    if endpoint is not None:
        need(endpoint in {'preflight','postflight'}, 'Unknown endpoint')
        native = c.read_json(root/c.PREPARE_REL/'native-manifest.json')
        archive = c.read_json(root/c.PREPARE_REL/'archive-manifest.json')
        need(native_members(native['roots']) == set(native['discovered_members']), 'Installed native membership changed')
        for label, manifest in (('R',native),('A',archive)):
            at = time.monotonic()
            c.verify_files(manifest['files'])
            result.setdefault('classes',{})[label] = dict(files=len(manifest['files']), bytes=sum(Path(n).stat().st_size for n in manifest['files']), duration_seconds=time.monotonic()-at)
            result['counts'][label] = len(manifest['files'])
    result.update(end_monotonic=time.monotonic(), duration_seconds=time.monotonic()-start)
    return result


def base_source_names(identity):
    return identity['base_registered_identity']['sources']


def worker_summary(identity, guard, final_runtime, lease):
    rows = guard.boundaries
    need(rows and all(row['verdict']=='passed' for row in rows), 'Incomplete/failed worker boundary')
    need(final_runtime is not None and final_runtime.get('verdict') == 'passed', 'Final live runtime proof missing')
    return dict(schema='long_d2_worker_integrity_summary_v1', protocol_sha256=identity['protocol_sha256'],
                config_sha256=identity['config_sha256'], identity_sha256=lease['identity_sha256'],
                classification_sha256=identity['classification_sha256'], manifests=identity['class_manifest_hashes'],
                boundary_count=len(rows), boundaries=rows, final_live_legacy=True, final_runtime=final_runtime,
                first_local_failure=None, first_global_failure=None)


def summary_valid(summary, registration):
    try:
        worker = summary['worker']
        need(summary['schema']=='long_d2_compact_integrity_summary_v1', 'Wrong integrity summary schema')
        for key in ('protocol_sha256','config_sha256','identity_sha256','classification_sha256','reservation_sha256'):
            need(summary[key] == registration[key], 'Summary binding differs: '+key)
        need(summary['manifests'] == registration['class_manifest_hashes'], 'Class manifest bindings differ')
        for label in ('preflight','postflight'):
            endpoint = summary[label]
            need(endpoint['verdict']=='passed' and endpoint['role']=='outer_'+label, 'Missing actual endpoint')
            need(endpoint['counts']==registration['class_counts'], 'Endpoint class count differs')
            need(endpoint['classification_sha256']==registration['classification_sha256'] and endpoint['manifests']==registration['class_manifest_hashes'], 'Endpoint roots differ')
        need(worker['schema']=='long_d2_worker_integrity_summary_v1' and worker['final_live_legacy'] is True, 'Final legacy proof missing')
        for key in ('protocol_sha256','config_sha256','identity_sha256','classification_sha256'):
            need(worker[key]==registration[key], 'Worker summary differs: '+key)
        need(worker['manifests']==registration['class_manifest_hashes'], 'Worker manifests differ')
        rows = worker['boundaries']
        need(worker['boundary_count']==len(rows) and len(rows)>0, 'Worker boundary count differs')
        need(all(r['sequence']==i and r['verdict']=='passed' for i,r in enumerate(rows)), 'Worker boundary sequence failed')
        need(worker['final_runtime']['verdict']=='passed' and worker['final_runtime']['cache']['empty'] is True, 'Runtime/cache proof missing')
        need(all(summary[k] is None and worker[k] is None for k in ('first_local_failure','first_global_failure')), 'Failure prohibits acceptance')
        return True
    except (KeyError, TypeError, life.Stop):
        return False
