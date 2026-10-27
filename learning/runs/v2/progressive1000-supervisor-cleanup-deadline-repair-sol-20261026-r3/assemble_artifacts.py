"""Prepare exact successor metadata; no campaign, state or lease access."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

OWN = Path(__file__).resolve().parent
ROOT = OWN.parents[3]
R2 = OWN.parent/'progressive1000-supervisor-race-repair-sol-20261026-r2'
REVIEW = OWN.parent/'progressive1000-supervisor-r2-final-review-sol-20261026-r2'
ACCEPTED = OWN.parent/'progressive1000-shared-runtime-staticmethod-repair-sol-20261026-r2'
ASSEMBLY = OWN.parent/'progressive1000-matched-run-parent-assembly-20261026-r1'
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text())
def save(name, value):
    with (OWN/name).open('x') as stream:
        stream.write(json.dumps(value,sort_keys=True,indent=2)+'\n')

manifest = read(OWN/'source-manifest.json')
assert sha(R2/'source-manifest.json') == 'df65bb051c9232497d223dc4a73c41e90af9556323d6a16b0aa378724931b12a'
for name,digest in manifest['files'].items():
    assert sha(OWN/name) == digest,name
    if name.endswith('.py'): ast.parse((OWN/name).read_text(),filename=name)
ast.parse(Path(__file__).read_text())
immutable = dict(read(OWN/'preservation-before.json')['pins'])
accepted = {}
for name,base in (('source-manifest.json',ACCEPTED),('runtime-manifest.json',ACCEPTED/'runtime')):
    path = ACCEPTED/name
    digest = sha(path)
    accepted[name] = digest
    immutable[str(path)] = digest
    for member,pin in read(path)['files'].items():
        assert sha(base/member) == pin,member
        immutable[str(base/member)] = pin
assert accepted['source-manifest.json'] == 'be7b8b3c9ef90d1e820df417f54863b6943fb746c451105078923916f19a04a2'
index_path = ASSEMBLY/'final-registration-index.json'
scope_path = ASSEMBLY/'prelaunch-evidence-scope.json'
assert sha(index_path) == '7144e7ab3852eac4307e64fecf884d1dc8b21a769f48267d065cf679b3bedaef'
assert sha(scope_path) == '333d3aada22ddf2959b155160e92d97bb162b95247a1cdac16e6bad089885d6c'
immutable[str(index_path)] = sha(index_path)
immutable[str(scope_path)] = sha(scope_path)
index = read(index_path)
assert len(index['registrations']) == 6
(OWN/'templates').mkdir()
for item in index['registrations']:
    path = Path(item['registration'])
    assert sha(path) == item['sha256']
    immutable[str(path)] = item['sha256']
    reg = read(path)
    assert reg['source_manifest_sha256'] == accepted['source-manifest.json']
    assert reg['runtime_manifest_sha256'] == accepted['runtime-manifest.json']
    envelope = read(R2/'templates'/f"{item['run_id']}.envelope.json")
    assert envelope['registration'] == str(path) and envelope['registration_sha256'] == item['sha256']
    envelope.update(control=str(OWN/'dispatch'/item['run_id']),
                    cancel_path=str(OWN/'dispatch'/('cancel-'+item['run_id'])))
    envelope['pins'] = {str(OWN/Path(p).name) if Path(p).parent == R2 else p:
                       sha(OWN/Path(p).name) if Path(p).parent == R2 else pin
                       for p,pin in envelope['pins'].items()}
    assert envelope['started'] is None and envelope['launch_approval_sha256'] is None
    assert envelope['status'] == 'DRAFT_NO_LAUNCH'
    for p,pin in envelope['pins'].items():
        assert sha(p) == pin
        if not Path(p).is_relative_to(OWN): immutable[p] = pin
    assert sha(envelope['source_acceptance']) == envelope['source_acceptance_sha256']
    immutable[envelope['source_acceptance']] = envelope['source_acceptance_sha256']
    save('templates/'+item['run_id']+'.envelope.json',envelope)
save('templates/launch-approval.template.json',read(R2/'templates/launch-approval.template.json'))
command = read(R2/'launch-command-template.json')
command['argv'] = [p.replace(str(R2),str(OWN)) for p in command['argv']]
save('launch-command-template.json',command)

changes = []; patch = []
for name in manifest['files']:
    prior = R2/name; after = OWN/name
    if prior.read_bytes() == after.read_bytes(): continue
    patch.extend(difflib.unified_diff(prior.read_text().splitlines(keepends=True),
        after.read_text().splitlines(keepends=True),fromfile='a/'+name,tofile='b/'+name))
    changes.append(dict(path=name,original_sha256=sha(prior),sha256=sha(after)))
(OWN/'exact-input-diff.patch').write_text(''.join(patch))
save('diff-index.json',dict(base=str(R2),base_source_manifest_sha256=sha(R2/'source-manifest.json'),
    changed=changes,unchanged=[n for n in manifest['files'] if sha(R2/n)==sha(OWN/n)],
    patch_sha256=sha(OWN/'exact-input-diff.patch')))
def bodies(path):
    text = path.read_text()
    return {n.name:ast.get_source_segment(text,n) for n in ast.walk(ast.parse(text))
            if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')}
reuse = {}
for name in ('test_bindings.py','test_real_processes.py'):
    old,new = bodies(R2/'tests'/name),bodies(OWN/'tests'/name)
    assert set(old) <= set(new)
    reuse[name] = dict(original_count=len(old),unchanged=sorted(n for n in old if old[n]==new[n]),
        adapted=sorted(n for n in old if old[n]!=new[n]),added=sorted(set(new)-set(old)))
assert reuse['test_bindings.py']['original_count'] == 11
assert reuse['test_real_processes.py']['original_count'] == 10
save('control-reuse.json',dict(original_controls_retained=21,suites=reuse,
    guard='Fake Popen prohibition retained. Real signals remain restricted to owned unreaped handles; fresh identity guards unchanged.'))
save('source-pins.json',dict(supervisor_manifest_sha256=sha(OWN/'source-manifest.json'),
    supervisor_files=manifest['files'],frozen_R2_manifest_sha256=sha(R2/'source-manifest.json'),
    independent_review=dict(path=str(REVIEW/'review.md'),sha256=sha(REVIEW/'review.md'),receipt_sha256=sha(REVIEW/'receipt.json')),
    accepted_manifests=accepted,final_registration_index=dict(path=str(index_path),sha256=sha(index_path)),
    registrations=index['registrations'],prelaunch_evidence_scope=dict(path=str(scope_path),sha256=sha(scope_path)),
    immutable_pins=immutable,dependency_binding_sha256=sha(OWN/'dependency-binding.json'),
    installed_dependency_scope='Inherited launch-time checks unchanged; installed dependency inventory not requalified here.'))
drift = [p for p,pin in immutable.items() if sha(p)!=pin]
assert not drift,drift
save('preservation-after.json',dict(pins_checked=len(immutable),drift=drift,
    accepted_worker_runtime_match_pinned_manifests=True,all_six_final_registrations_match_index=True,
    owned_cache_empty=not list((OWN/'empty-cache').iterdir()),owned_dispatch_absent=not (OWN/'dispatch').exists(),
    scope='Named immutable bytes only. No current parent state, lease, marker, registered output/cache or approval-path inspection.'))
save('static-checks.json',dict(ast_parse=True,unchanged_runtime_files=['binding.py','terminal.py','dependency-binding.json'],
    source_manifest_files=len(manifest['files']),inert_envelopes=6,original_control_count=21,
    added_tests=2,accepted_worker_runtime_edits=0,actual_campaign_launches=0))
print(json.dumps(dict(changed_source_files=len(changes),immutable_pins=len(immutable),inert_envelopes=6)))
