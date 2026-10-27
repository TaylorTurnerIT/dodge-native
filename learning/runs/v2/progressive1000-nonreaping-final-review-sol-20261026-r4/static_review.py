"""Static byte, AST and JSON review only. Never import or execute target code."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
BASE = OUT.parent
R5 = BASE / 'progressive1000-supervisor-nonreaping-parent-completion-20261026-r5'
R4 = BASE / 'progressive1000-supervisor-nonreaping-poll-repair-sol-20261026-r4'
R3 = BASE / 'progressive1000-supervisor-cleanup-deadline-repair-sol-20261026-r3'
WORKER = BASE / 'progressive1000-shared-runtime-staticmethod-repair-sol-20261026-r2'
EXPECTED = 'fd54444b88e80175e7acbef2d37f0d8b613c0018cb6110e85a1ded0e88cfe579'
tracked = {}
checks = {}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def pin(path, expected=None):
    path = Path(path).resolve()
    actual = sha(path)
    if expected is not None:
        assert actual == expected, (str(path), expected, actual)
    tracked[str(path)] = actual
    return actual


def read(path):
    pin(path)
    return json.loads(Path(path).read_bytes())


def save(name, value):
    with (OUT / name).open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


manifest = read(R5 / 'source-manifest.json')
assert pin(R5 / 'source-manifest.json') == EXPECTED
for rel, digest in manifest['files'].items():
    pin(R5 / rel, digest)
    pin(R4 / rel, digest)
pin(R4 / 'source-manifest.json', EXPECTED)
checks['R4_R5_operational_files_byte_identical'] = list(manifest['files'])
for rel in ('binding.py', 'terminal.py', 'execute_once.py', 'dependency-binding.json', 'tests/run_controls.py'):
    assert pin(R3 / rel) == pin(R5 / rel)
old_observe = (R3 / 'observe.py').read_text()
new_observe = (R5 / 'observe.py').read_text()
assert old_observe[old_observe.index('    except BaseException as error:\n        latch('):] == new_observe[new_observe.index('    except BaseException as error:\n        latch('):]
checks['R3_exceptional_cleanup_and_finalization_byte_identical'] = True

pins = read(R5 / 'source-pins.json')
for path, digest in pins['immutable_pins'].items():
    pin(path, digest)  # Qualification members stay opaque bytes.
checks['author_immutable_pins_checked'] = len(pins['immutable_pins'])
dependency = read(R5 / 'dependency-binding.json')
for name in ('registration', 'inventory'):
    pin(dependency[name + '_path'], dependency[name + '_sha256'])
old_registration = read(dependency['registration_path'])
inventory = read(dependency['inventory_path'])
for path, item in inventory['pins'].items():
    assert old_registration['pins'][path] == item['sha256']
    pin(path, item['sha256'])
checks['installed_dependency_pins_checked'] = len(inventory['pins'])
for name, digest in pins['accepted_manifests'].items():
    pin(WORKER / name, digest)
    for rel, value in read(WORKER / name)['files'].items():
        pin((WORKER / 'runtime' if name == 'runtime-manifest.json' else WORKER) / rel, value)
scope = pins['prelaunch_evidence_scope']
pin(scope['path'], '333d3aada22ddf2959b155160e92d97bb162b95247a1cdac16e6bad089885d6c')

index_info = pins['final_registration_index']
pin(index_info['path'], index_info['sha256'])
index = read(index_info['path'])
assert index['registrations'] == pins['registrations']
bindings = []
for item in index['registrations']:
    pin(item['registration'], item['sha256'])
    reg = read(item['registration'])
    template_path = R5 / 'templates' / (item['run_id'] + '.envelope.json')
    env = read(template_path)
    old_env = read(R4 / 'templates' / template_path.name)
    for key in ('control', 'cancel_path'):
        assert env[key] == old_env[key].replace(str(R4), str(R5))
    assert env['pins'] == {p.replace(str(R4), str(R5)): d for p, d in old_env['pins'].items()}
    assert {k: v for k, v in env.items() if k not in ('control', 'cancel_path', 'pins')} == {k: v for k, v in old_env.items() if k not in ('control', 'cancel_path', 'pins')}
    assert env['registration'] == item['registration'] and env['registration_sha256'] == item['sha256']
    assert env['status'] == 'DRAFT_NO_LAUNCH' and env['started'] is None and env['launch_approval_sha256'] is None
    assert env['control'] == str(R5 / 'dispatch' / item['run_id'])
    assert not Path(env['control']).is_relative_to(Path(reg['output']))
    assert not Path(env['cancel_path']).is_relative_to(Path(reg['output']))
    for path, digest in env['pins'].items():
        pin(path, digest)
    pin(env['interpreter_resolved'], env['interpreter_sha256'])
    pin(env['source_acceptance'], env['source_acceptance_sha256'])
    assert env['source_acceptance'] != env['launch_approval']
    assert reg['limits'] == dict(cleanup_seconds=10, mps_bytes=6442450944, raw_frames=16712512, resets=983040, retries=0, rss_bytes=6442450944, total_seconds=1800, work_seconds=1790)
    assert reg['schedule']['updates'] == 60 and reg['schedule']['integrity_local_updates'] == [12, 24, 36, 48, 60]
    assert reg['schedule']['formal_evaluation_local_updates'] == [60]
    assert reg['ppo']['learning_rate'] == 3e-5 and reg['shared_config']['global_updates'] == 60
    assert reg['source_manifest_sha256'] == pins['accepted_manifests']['source-manifest.json']
    bindings.append(dict(**item, template=str(template_path), template_sha256=sha(template_path)))
assert len(bindings) == 6
checks['six_exact_inert_envelopes'] = bindings

ast_paths = [R5 / p for p in manifest['files'] if p.endswith('.py')]
ast_paths += [WORKER / p for p in ('contracts.py', 'worker_cli.py')]
for path in ast_paths:
    ast.parse(path.read_text(), filename=str(path))
checks['ast_files_parsed'] = len(ast_paths)
reuse = read(R5 / 'control-reuse.json')
for filename, spec in reuse['suites'].items():
    def bodies(root):
        return {node.name: ast.dump(node, include_attributes=False) for node in ast.walk(ast.parse((root / 'tests' / filename).read_text())) if isinstance(node, ast.FunctionDef) and node.name.startswith('test_')}
    old, new = bodies(R3), bodies(R5)
    assert len(old) == spec['original_count']
    assert set(new) - set(old) == set(spec['added']) and not set(old) - set(new)
    assert [n for n in old if old[n] != new[n]] == spec['adapted']
checks['original_controls_retained'] = 23
checks['new_real_controls'] = reuse['suites']['test_real_processes.py']['added']

patch_path = R5 / 'parent-exact-diff-from-r3.patch'
patch = patch_path.read_text()
parts = []
for line in patch.splitlines():
    if line.startswith('--- '):
        before = Path(line[4:])
    elif line.startswith('+++ '):
        after = Path(line[4:])
        pin(before); pin(after)
        parts.extend(difflib.unified_diff(before.read_text().splitlines(True), after.read_text().splitlines(True), fromfile=str(before), tofile=str(after)))
assert ''.join(parts) == patch
pin(patch_path)
checks['parent_exact_diff_reproduced'] = True

abi = read(R5 / 'abi-provenance.json')
for header in abi['headers']:
    pin(header['path'], header['sha256'])
    lines = Path(header['path']).read_text().splitlines()
    for excerpt in header['excerpts']:
        assert '\n'.join(lines[excerpt['first_line']-1:excerpt['last_line']]) == excerpt['text']
for path, digest in abi['stdlib_loader_pins'].items():
    pin(path, digest)
pin(R5 / abi['raw_probe']['path'], abi['raw_probe']['sha256'])
checks['sdk_headers_and_excerpts_verified'] = len(abi['headers'])
checks['ABI_review'] = 'Darwin arm64 LP64 siginfo_t: 104 bytes, alignment 8, offsets 0/4/8/12/16/20/24/32/40/48; int/uint32/pointer/int call; WEXITED|WNOHANG|WNOWAIT = 37. No libc load or syscall by reviewer.'

evidence = {}
for name in ('test-receipt.json', 'real-test-receipt.json'):
    data = read(R5 / name)
    evidence[name] = {k: data[k] for k in ('tests_run', 'errors', 'failures', 'raw_exit', 'elapsed_seconds')}
    if name.startswith('real'):
        evidence[name]['remaining_owned_handles'] = data['remaining_owned_handles']
        evidence[name]['selected_checks'] = {e['test'].split('.')[-1]: e['checks'] for e in data['evidence'] if any(x in e['test'] for x in ('fork_after_first_snapshot', 'nonreaping_waitid', 'total_deadline', 'empty_anchors'))}
checks['inherited_R4_evidence_not_replayed'] = evidence
pin(R5 / 'README.md')
for name in ('parent-completion.json', 'development-first-failure.json', 'development-r1-test-receipt.json', 'launch-command-template.json'):
    read(R5 / name)
for name in ('progressive1000-final-supervisor-registration-review-sol-20261026-r1', 'progressive1000-supervisor-r2-final-review-sol-20261026-r2', 'progressive1000-supervisor-r3-final-review-sol-20261026-r3'):
    read(BASE / name / 'receipt.json')
    pin(BASE / name / 'review.md')

save('input-pin-checks.json', dict(checks=checks, target_source_manifest_sha256=EXPECTED))
save('preservation-before.json', dict(pins=tracked, scope='Named immutable inputs, SDK, dependencies and inherited evidence bytes. No live lease or whole-workspace audit.'))
print(json.dumps(dict(status='static_checks_passed', tracked_pins=len(tracked), immutable_pins=checks['author_immutable_pins_checked'], dependency_pins=checks['installed_dependency_pins_checked'], envelopes=len(bindings), ast_files=len(ast_paths)), sort_keys=True))
