"""CPU-only parent verification. No launch or lease mutation."""
import builtins
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import runpy
import symtable
import sys

ROOT = Path(__file__).resolve().parents[4]
OWN = Path(__file__).resolve().parent
SOURCE = ROOT / 'learning/runs/v2/D2-retained204-lr1e4-prepare-luna-20261026-r3'
EXPECTED_REGISTRATION = '68063348dede3050c4a8852c6314f4c95fd3a623e89c9499413f2325f4edad44'


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            result.update(block)
    return result.hexdigest()


assert digest(SOURCE / 'registration.json') == EXPECTED_REGISTRATION
registration = json.loads((SOURCE / 'registration.json').read_text())
manifest = json.loads((SOURCE / 'source-manifest.json').read_text())
receipt = json.loads((SOURCE / 'preparation-receipt.json').read_text())
assert digest(SOURCE / 'source-manifest.json') == receipt['artifact_sha256']['source-manifest.json']
assert sys.dont_write_bytecode and sys.flags.dont_write_bytecode
assert Path(sys.executable).resolve() == Path(registration['interpreter']).resolve()
assert sys.pycache_prefix == registration['import_policy']['pycache_prefix']
assert not any(Path(sys.pycache_prefix).iterdir())


def verify_all():
    for path, expected in registration['pins'].items():
        assert digest(path) == expected, path
    for path, expected in manifest['files_sha256'].items():
        assert digest(SOURCE / path) == expected, path


verify_all()
unresolved = []
for filename in ('runner.py', 'execute_once.py', 'resume_lr_transition.py'):
    table = symtable.symtable((SOURCE / filename).read_text(), filename, 'exec')
    defined = {symbol.get_name() for symbol in table.get_symbols()
               if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace()}

    def inspect(scope):
        for symbol in scope.get_symbols():
            name = symbol.get_name()
            if (symbol.is_referenced() and symbol.is_global() and name not in defined
                    and not hasattr(builtins, name) and not name.startswith('__')):
                unresolved.append((filename, scope.get_name(), name))
        for child in scope.get_children():
            inspect(child)

    inspect(table)
assert not unresolved, unresolved
runpy.run_path(str(SOURCE / 'test_source_contract.py'), run_name='parent_source_contract')
runpy.run_path(str(SOURCE / 'test_entry_counter_binding.py'), run_name='parent_entry_counter_binding')
runpy.run_path(str(SOURCE / 'test_entry_evaluation.py'), run_name='parent_entry_evaluation')

# Run the exact frozen CPU controls, redirecting only their result destination.
# __file__ remains the frozen source path, so imports and authority paths are exact.
control_path = SOURCE / 'cpu_restore_and_controls.py'
control_source = control_path.read_text()
old_destination = '(OUT/"cpu-restore-and-controls.json").write_text'
new_destination = '(' + repr(str(OWN / 'cpu-restore-and-controls.json')) + ')'
assert control_source.count(old_destination) == 1
control_source = control_source.replace(old_destination, 'Path(' + new_destination + ').write_text')
exec(compile(control_source, str(control_path), 'exec'),
     {'__name__': 'parent_cpu_controls', '__file__': str(control_path)})

runner = sys.modules['runner']
bad = copy.deepcopy(registration)
bad['lr_transition_helper_sha256'] = '0' * 64
try:
    runner.load_verified_transition(bad)
except ValueError:
    wrong_helper_digest_rejected = True
else:
    raise AssertionError('Wrong helper digest was accepted')

verify_all()
assert not any(Path(sys.pycache_prefix).iterdir())
result = {
    'schema': 'retained204_lr1e4_parent_cpu_validation_v1',
    'status': 'passed',
    'registration_sha256': EXPECTED_REGISTRATION,
    'registration_pins_checked_before_after': len(registration['pins']),
    'manifest_files_checked_before_after': len(manifest['files_sha256']),
    'source_contract_passed': True,
    'undefined_global_names': unresolved,
    'actual204_cpu_model_adam_restore_and_negative_controls': True,
    'wrong_helper_digest_rejected_before_execution': wrong_helper_digest_rejected,
    'bytecode_cache_empty': True,
    'exact_lease_assertion_mocked_only_for_preparation': True,
    'MPS_RNG_restore_or_environment_or_training': False,
    'cpu_result_sha256': digest(OWN / 'cpu-restore-and-controls.json'),
}
with (OWN / 'validation.json').open('x') as stream:
    json.dump(result, stream, indent=2)
    stream.write('\n')
print(json.dumps(result))
