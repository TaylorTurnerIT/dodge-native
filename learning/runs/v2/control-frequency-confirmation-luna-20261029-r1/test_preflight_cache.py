"""Guard the pre-lease bytecode-cache contract with filesystem regressions."""
import ast
import tempfile
from pathlib import Path
import launch


def rejected(registration, message):
    try:
        launch.require_empty_pycache(registration)
    except ValueError as error:
        assert message in str(error)
    else:
        raise AssertionError(f"accepted invalid cache: {registration}")


def test_cache_filesystem_shapes():
    with tempfile.TemporaryDirectory(prefix='dodge-confirmation-cache-') as temp:
        root = Path(temp)
        absent = root / 'absent'
        rejected({'import_policy': {'pycache_prefix': str(absent)}}, 'real directory')
        regular_file = root / 'file'
        regular_file.write_text('x')
        rejected({'import_policy': {'pycache_prefix': str(regular_file)}}, 'real directory')
        target = root / 'target'
        target.mkdir()
        link = root / 'link'
        link.symlink_to(target, target_is_directory=True)
        rejected({'import_policy': {'pycache_prefix': str(link)}}, 'real directory')
        populated = root / 'populated'
        populated.mkdir()
        (populated / 'cached.pyc').write_bytes(b'x')
        rejected({'import_policy': {'pycache_prefix': str(populated)}}, 'must be empty')
        empty = root / 'empty'
        empty.mkdir()
        assert launch.require_empty_pycache({'import_policy': {'pycache_prefix': str(empty)}}) == empty


def test_launcher_checks_cache_before_lease_or_markers():
    tree = ast.parse(Path(launch.__file__).read_text())
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
    source = Path(launch.__file__).read_text()
    body = source[source.index('def main('):]
    assert body.index('require_empty_pycache(reg)') < body.index('install_lease(reg)')
    calls = {node.func.id: node.lineno for node in ast.walk(main)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert calls['require_empty_pycache'] < calls['install_lease']


if __name__ == '__main__':
    test_cache_filesystem_shapes()
    test_launcher_checks_cache_before_lease_or_markers()
    print('preflight cache regressions passed')
