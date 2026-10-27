"""Read/hash/AST/JSON review only. Never import or execute target code."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import sys

OWN = Path(__file__).resolve().parent
ROOT = OWN.parents[3]
TARGET = ROOT / 'learning/runs/v2/confirmed324-paired-worker-contract-repair-sol-20261026-r2'
checks = []


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            assert key not in result, (path, key)
            result[key] = value
        return result
    return json.loads(path.read_bytes(), object_pairs_hook=unique)


def check(label, value, details=None):
    assert value, (label, details)
    checks.append(dict(check=label, passed=True, details=details))


def tree(name):
    return ast.parse((TARGET / name).read_bytes(), filename=str(TARGET / name))


def function(parsed, name):
    return next(n for n in ast.walk(parsed) if isinstance(n, ast.FunctionDef) and n.name == name)


def call_name(node):
    return ast.unparse(node.func)


assert sys.dont_write_bytecode
for filename in ('source-manifest.json', 'artifact-manifest.json', 'input-manifest.json'):
    manifest = read(TARGET / filename)
    base = ROOT if filename == 'input-manifest.json' else TARGET
    members = manifest.get('files', manifest.get('pins'))
    check(filename + ' hashes', all(sha(base / n) == h for n, h in members.items()), len(members))

artifact = read(TARGET / 'artifact-manifest.json')
check('artifact inventory complete', {str(p.relative_to(TARGET)) for p in TARGET.rglob('*') if p.is_file()} == set(artifact['files']) | {'artifact-manifest.json'})
check('target empty directories', all((TARGET / n).is_dir() and not any((TARGET / n).iterdir()) for n in artifact['excluded_empty_directories']))
check('receipt source manifest', read(TARGET / 'receipt.json')['source_manifest_sha256'] == sha(TARGET / 'source-manifest.json'))
inputs = read(TARGET / 'input-manifest.json')
runtime = Path(inputs['runtime_root'])
check('runtime exact member inventory', {str(p.relative_to(ROOT)) for p in runtime.rglob('*') if p.is_file() and '__pycache__' not in p.parts} == {n for n in inputs['pins'] if n.startswith(str(runtime.relative_to(ROOT)) + '/')})

r5 = ROOT / 'learning/runs/v2/confirmed324-private-bindings-r5-parent-validation-20261026-r1/source-manifest.json'
check('authoritative R5 manifest pin', sha(r5) == '2b0caf00a5d5e765726d080fd5647211190e472d74ffb33b3466e477cb2906a9')
check('authoritative R5 members', all(sha(Path(n)) == h for n, h in read(r5)['files'].items()), len(read(r5)['files']))
copied = ['attempt_claim.py', 'driver_binding.py', 'fingerprints.py', 'rng_reference.py', 'transition.py']
check('five R5 implementation copies unchanged', all(sha(TARGET / n) == read(r5)['files'][str(Path(read(r5)['source_directory']) / n)] for n in copied), copied)

index = read(TARGET / 'diff-index.json')
patch = ''
for row in index:
    new = TARGET / row['file']
    old = Path(row['baseline']) if row['baseline'] else None
    assert sha(new) == row['sha256']
    if old:
        assert sha(old) == row['baseline_sha256']
    before = old.read_text().splitlines(keepends=True) if old else []
    after = new.read_text().splitlines(keepends=True)
    assert row['unchanged'] == (before == after)
    patch += ''.join(difflib.unified_diff(before, after, fromfile=str(old.relative_to(ROOT)) if old else '/dev/null', tofile=str(new.relative_to(ROOT))))
check('exact diff regenerated from baselines', patch.encode() == (TARGET / 'exact-diff.patch').read_bytes(), len(index))

parsed = {p.name: tree(p.name) for p in TARGET.glob('*.py')}
check('all target Python parses without execution', len(parsed) == 14, sorted(parsed))
transition = parsed['transition.py']
body = function(transition, 'transition')
restore_calls = [n for n in ast.walk(body) if isinstance(n, ast.Call) and call_name(n) == 'restore_trusted']
claim_calls = [n for n in ast.walk(body) if isinstance(n, ast.Call) and call_name(n) == 'attempt_claim.claim']
check('single zeroarg accepted restore after durable claim', len(restore_calls) == len(claim_calls) == 1 and not restore_calls[0].args and not restore_calls[0].keywords and claim_calls[0].lineno < restore_calls[0].lineno)
run = function(parsed['worker.py'], 'run_transition')
calls = [(n.lineno, call_name(n)) for n in ast.walk(run) if isinstance(n, ast.Call)]
check('bootstrap before R5 transition', next(i for i,n in calls if n == 'adapter.bootstrap') < next(i for i,n in calls if n == 'transition.transition'))
restore = function(parsed['driver_binding.py'], 'restore_trusted')
check('bound restore closure zeroarg', not restore.args.args and restore.args.vararg is None and restore.args.kwarg is None)
production = ['worker.py','runtime_adapter.py','contracts.py','build_registration.py','worker_cli.py']
check('production does not import tests', not any(isinstance(n, (ast.Import, ast.ImportFrom)) and any(a.name.startswith('test_') for a in n.names) for name in production for n in ast.walk(parsed[name])))

refroot = ROOT / 'learning/runs/v2/confirmed324-rng-reference-parent-20261026-r3'
audit = read(refroot / 'parent-terminal-audit.json')
check('accepted independent initial-state producer audit', audit['status'] == 'accepted_three_initial_CPU_MPS_generator_references' and audit['registration_sha256'] == '0150cfcdbec53ff4322f72e5fa224cb6a914f3505ea732c0722511b5e031c398' and audit['raw_supervisor_exit_code'] == audit['raw_worker_exit_code'] == 0 and audit['required_postflight_checks_passed'] == 19 and audit['marker_preserved'] is True)
vectors = read(ROOT / 'learning/runs/v2/confirmed324-seed-vectors-parent-20261026-r1/seed-vectors.json')['vectors']
parent = read(ROOT / 'learning/runs/v2/D2-retained300-parent-terminal-audit-20261026-r1/retained-best-candidate-receipt.json')
mask = (1 << 64) - 1


def mix(v):
    v &= mask
    v = ((v ^ (v >> 30)) * 0xBF58476D1CE4E5B9) & mask
    v = ((v ^ (v >> 27)) * 0x94D049BB133111EB) & mask
    return v ^ (v >> 31)


for vector in vectors:
    replica = vector['replica']
    accepted = next(r for r in audit['references'] if r['replica'] == replica)
    ref = read(Path(accepted['path']))
    canonical = json.dumps(dict(study_id='paired-lr-confirmed324-20261026-r1',replica=replica,seeds=vector['seeds']), sort_keys=True,separators=(',', ':'),ensure_ascii=True,allow_nan=False).encode()
    check(f'replica {replica} independent full reference binding', sha(Path(accepted['path'])) == accepted['sha256'] and ref['complete_seed_vector'] == vector['seeds'] and ref['vector_sha256'] == accepted['vector_sha256'] == vector['vector_sha256'] == hashlib.sha256(canonical).hexdigest() and ref['replica'] == replica and ref['study_id'] == 'paired-lr-confirmed324-20261026-r1' and ref['backend'] == 'mps' and ref['torch_version'] == inputs['runtime_versions']['torch'] and ref['accepted_checkpoint_sha256'] == parent['checkpoint_sha256'] and ref['parent_receipt_sha256'] == sha(ROOT / 'learning/runs/v2/D2-retained300-parent-terminal-audit-20261026-r1/retained-best-candidate-receipt.json'))
    a = read(TARGET / f'registration-template-replica-{replica}-A.json')
    b = read(TARGET / f'registration-template-replica-{replica}-B.json')
    check(f'replica {replica} templates inert and paired', a['status'] == b['status'] == 'parent_review_required_not_launchable' and a['vector'] == b['vector'] == vector and a['initial_episode_indices'] == b['initial_episode_indices'] == parent['next_episode_indices'])
    actual = []
    for slot, episode in enumerate(vector['env_control']['episode_indices']):
        base = mix(vector['seeds']['env_master_seed'] ^ 0x444F4447455F5632) ^ mix(slot + 0x9E3779B97F4A7C15) ^ mix(episode + 0xD1B54A32D192ED03)
        counter = 0
        while True:
            seed = mix(base ^ mix(counter + 0x94D049BB133111EB)) >> 32
            if not any(lo <= seed <= hi for lo, hi in a['exclusion_union']):
                break
            counter += 1
        actual.append(seed)
    check(f'replica {replica} 64 seed arithmetic controls', len(actual) == len(set(actual)) == 64 and 0 not in actual and actual[:4] == vector['env_control']['first_slot_actual_seeds'] and hashlib.sha256(b''.join(v.to_bytes(4,'big') for v in actual)).hexdigest() == vector['env_control']['all_slots_actual_seed_sha256'])

design = ROOT / 'learning/runs/v2/progressive1000-curriculum-replica-parent-20261026-r3'
check('independent curriculum design pins preserved', sha(design / 'experiment.json') == 'c20bd35188c4b4dd36687bc10c7998e6410c70d37300be92db9a42b3d01c43c0' and sha(design / 'scheduler_reference.py') == 'a467b7219a9cd801fa3b403a6af112fc693ec3d14c9d311e8845632ef61d844b')
summary = dict(schema='confirmed324_source_only_independent_review_checks_v1',target=str(TARGET),scope='stdlib read/hash/AST/JSON only; no target imports or test execution',checks=checks,check_count=len(checks),target_hashes={n:sha(TARGET/n) for n in ('source-manifest.json','artifact-manifest.json','receipt.json','exact-diff.patch','worker.py','runtime_adapter.py','contracts.py','build_registration.py','worker_cli.py')})
with (OWN / 'static-checks.json').open('x') as stream:
    json.dump(summary, stream, sort_keys=True, indent=2)
    stream.write('\n')
print(json.dumps(dict(passed=len(checks),target_source_manifest_sha256=summary['target_hashes']['source-manifest.json'])))
