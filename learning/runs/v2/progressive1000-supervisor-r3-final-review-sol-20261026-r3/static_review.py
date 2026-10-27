"""Read-only byte/JSON/AST checks. Never imports or executes reviewed code."""
import ast
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
BASE = OUT.parent
R3 = BASE / 'progressive1000-supervisor-cleanup-deadline-repair-sol-20261026-r3'
R2 = BASE / 'progressive1000-supervisor-race-repair-sol-20261026-r2'
R1 = BASE / 'progressive1000-existing-supervisor-binding-sol-20261026-r1'
WORKER = BASE / 'progressive1000-shared-runtime-staticmethod-repair-sol-20261026-r2'
ASSEMBLY = BASE / 'progressive1000-matched-run-parent-assembly-20261026-r1'
REVIEWS = [BASE / 'progressive1000-final-supervisor-registration-review-sol-20261026-r1',
           BASE / 'progressive1000-supervisor-r2-final-review-sol-20261026-r2']

def read(path):
    return json.loads(Path(path).read_bytes())

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()

def save(name, value):
    with (OUT / name).open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write('\n')

def functions(path, tests=False):
    tree = ast.parse(Path(path).read_bytes(), filename=str(path))
    return {n.name: ast.dump(n, include_attributes=False) for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and (not tests or n.name.startswith('test_'))}

pins = read(R3 / 'source-pins.json')['immutable_pins']
expected = dict(pins)
for folder in (R3, R2, R1, WORKER, *REVIEWS):
    for path in folder.rglob('*'):
        if path.is_file():
            expected.setdefault(str(path), sha(path))
index_path = ASSEMBLY / 'final-registration-index.json'
index = read(index_path)
expected[str(index_path)] = '7144e7ab3852eac4307e64fecf884d1dc8b21a769f48267d065cf679b3bedaef'
scope_path = ASSEMBLY / 'prelaunch-evidence-scope.json'
expected[str(scope_path)] = '333d3aada22ddf2959b155160e92d97bb162b95247a1cdac16e6bad089885d6c'
for item in index['registrations']:
    expected[item['registration']] = item['sha256']
dep = read(R3 / 'dependency-binding.json')
inventory = read(dep['inventory_path'])
old_registration = read(dep['registration_path'])
for path, item in inventory['pins'].items():
    assert old_registration['pins'][path] == item['sha256']
    expected[path] = item['sha256']
before = {path: sha(path) for path in sorted(expected)}
save('preservation-before.json', dict(pins=before,
    scope='Named bytes only; includes frozen trees and installed dependencies. No live state/lease/marker/output paths read.'))
mismatches = [dict(path=p, expected=h, actual=before[p]) for p,h in expected.items() if before[p] != h]
assert not mismatches, mismatches

manifests = []
for folder, digest in ((R3, '76cb63b37e06fdd3737638e19ce44eef471fc7c878ee9ed92f6e58280f8fa5e4'),
                       (R2, 'df65bb051c9232497d223dc4a73c41e90af9556323d6a16b0aa378724931b12a'),
                       (WORKER, 'be7b8b3c9ef90d1e820df417f54863b6943fb746c451105078923916f19a04a2')):
    manifest = folder / 'source-manifest.json'
    assert sha(manifest) == digest
    files = read(manifest)['files']
    for relative, wanted in files.items():
        assert sha(folder / relative) == wanted, relative
    manifests.append(dict(path=str(manifest), sha256=digest, members=len(files)))
runtime = read(WORKER / 'runtime-manifest.json')
for relative, digest in runtime['files'].items():
    assert sha(WORKER / 'runtime' / relative) == digest

parsed = []
for folder in (R3, R2):
    for path in [*folder.glob('*.py'), *folder.glob('tests/*.py')]:
        ast.parse(path.read_bytes(), filename=str(path)); parsed.append(str(path))
unchanged = {name: (R3/name).read_bytes() == (R2/name).read_bytes()
             for name in ('binding.py', 'terminal.py', 'dependency-binding.json')}
assert all(unchanged.values())
reuse = {}
claims = read(R3 / 'control-reuse.json')['suites']
for name in ('test_bindings.py', 'test_real_processes.py'):
    old, new = functions(R2/'tests'/name, True), functions(R3/'tests'/name, True)
    result = dict(unchanged=sorted(k for k in old if new.get(k) == old[k]),
                  adapted=sorted(k for k in old if k in new and new[k] != old[k]),
                  added=sorted(set(new)-set(old)), removed=sorted(set(old)-set(new)))
    assert not result['removed']
    assert all(result[k] == sorted(claims[name][k]) for k in ('unchanged','adapted','added'))
    reuse[name] = result

templates = []
for item in index['registrations']:
    reg = read(item['registration'])
    template_path = R3/'templates'/('envelope-'+item['run_id']+'.json')
    if not template_path.exists():
        matches = [p for p in (R3/'templates').glob('*.json')
                   if read(p).get('registration') == item['registration']]
        assert len(matches) == 1
        template_path = matches[0]
    env = read(template_path)
    assert env['registration'] == item['registration'] and env['registration_sha256'] == item['sha256']
    assert env['status'] == 'DRAFT_NO_LAUNCH' and env['started'] is None and env['launch_approval_sha256'] is None
    for path, digest in env['pins'].items():
        assert sha(path) == digest
    assert sha(env['source_acceptance']) == env['source_acceptance_sha256']
    assert sha(env['interpreter_resolved']) == env['interpreter_sha256']
    assert Path(env['control']) == R3/'dispatch'/reg['run_id']
    assert not Path(env['control']).is_relative_to(Path(reg['output']))
    assert not Path(env['cancel_path']).is_relative_to(Path(reg['output']))
    assert reg['source_manifest_sha256'] == manifests[2]['sha256']
    assert reg['schedule']['updates'] == 60 and reg['schedule']['integrity_local_updates'] == [12,24,36,48,60]
    assert reg['schedule']['formal_evaluation_local_updates'] == [60]
    assert reg['ppo']['learning_rate'] == 3e-5 and reg['schedule']['promotion'] is False
    assert reg['limits'] == dict(cleanup_seconds=10, mps_bytes=6442450944, raw_frames=16712512,
        resets=983040,retries=0,rss_bytes=6442450944,total_seconds=1800,work_seconds=1790)
    templates.append(dict(**item, template=str(template_path), template_sha256=sha(template_path)))
regs = [read(i['registration']) for i in index['registrations']]
for replica in (1,2,3):
    pair = [r for r in regs if r['replica'] == replica]
    assert len(pair) == 2 and {r['curriculum_enabled'] for r in pair} == {False, True}
    for field in ('pair_id','vector','expected_parent_fingerprints','parent_checkpoint_sha256',
                  'parent_receipt_sha256','ppo','schedule','shared_config','initial_episode_indices','reference'):
        assert pair[0][field] == pair[1][field], field

save('input-pin-checks.json', dict(manifests=manifests, runtime_manifest_sha256=sha(WORKER/'runtime-manifest.json'),
    final_registration_index_sha256=sha(index_path),prelaunch_evidence_scope_sha256=sha(scope_path),
    installed_dependency_pins_checked=len(inventory['pins']), immutable_author_pins_checked=len(pins),
    registrations=templates, mismatches=mismatches))
save('static-checks.json', dict(ast_files_parsed=parsed, byte_identical_to_R2=unchanged,
    control_body_reuse=reuse, retained_original_controls=21, added_controls=2,
    target_imports=False, target_execution=False, tests_run=0, process_probes=0,
    normal_loop_reap_trace='ownership-interleaving.json', deadline_trace='review.md',
    qualification_tables='Opaque bytes only; no table contents decoded.'))
after = {path: sha(path) for path in before}
drift = [path for path in before if before[path] != after[path]]
save('preservation-after.json', dict(pins=after, drift=drift, checked=len(after),
    scope='Matches reviewer snapshot; not a whole-workspace or live lease audit.'))
assert not drift, drift
print(json.dumps(dict(pins_checked=len(after),installed_dependency_pins=len(inventory['pins']),
    registrations=len(templates), ast_files=len(parsed), drift=drift, input_mismatches=mismatches)))
