"""Rebuild preparation metadata and inert templates; never launch or edit inputs."""
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil

OWN=Path(__file__).resolve().parent
ROOT=OWN.parents[3]
R1=ROOT/'learning/runs/v2/progressive1000-existing-supervisor-binding-sol-20261026-r1'
REVIEW=ROOT/'learning/runs/v2/progressive1000-final-supervisor-registration-review-sol-20261026-r1'
INDEX=ROOT/'learning/runs/v2/progressive1000-matched-run-parent-assembly-20261026-r1/final-registration-index.json'
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text())
def save(name,value): (OWN/name).write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')
assert sha(R1/'source-manifest.json')=='8351fabd8a54685007e74a050200f2e25ac19e2e6ae3a4b11cf98535ef4c3d4f'
manifest=read(OWN/'source-manifest.json')
for name,digest in manifest['files'].items(): assert sha(OWN/name)==digest,name
SCOPE=INDEX.parent/'prelaunch-evidence-scope.json'
assert sha(SCOPE)=='333d3aada22ddf2959b155160e92d97bb162b95247a1cdac16e6bad089885d6c'
index=read(INDEX)
pins=read(OWN/'preservation-before.json')['pins']
drift=[path for path,digest in pins.items() if sha(path)!=digest]
assert not drift,drift
states={}
(OWN/'templates').mkdir(exist_ok=True)
for item in index['registrations']:
    assert sha(item['registration'])==item['sha256']
    reg=read(item['registration'])
    old=read(R1/'templates'/f"{item['run_id']}.envelope.json")
    old.update(registration=item['registration'],registration_sha256=item['sha256'],
        control=str(OWN/'dispatch'/item['run_id']),cancel_path=str(OWN/'dispatch'/('cancel-'+item['run_id'])),
        started=None,status='DRAFT_NO_LAUNCH',launch_approval_sha256=None)
    old['pins']={str(OWN/Path(path).name) if Path(path).parent==R1 else path:
                 sha(OWN/Path(path).name) if Path(path).parent==R1 else digest
                 for path,digest in old['pins'].items()}
    old['pins'][str(OWN/'source-manifest.json')]=sha(OWN/'source-manifest.json')
    save('templates/'+item['run_id']+'.envelope.json',old)
    state=dict(output_lexists=os.path.lexists(reg['output']),
        attempt_claim_lexists=os.path.lexists(reg['attempt_claim_path']),
        launch_marker_lexists=os.path.lexists(reg['launch_marker_path']),
        launch_approval_lexists=os.path.lexists(old['launch_approval']),
        cache_is_dir=Path(reg['import_policy']['pycache_prefix']).is_dir(),
        cache_members=sorted(str(p.relative_to(reg['import_policy']['pycache_prefix'])) for p in Path(reg['import_policy']['pycache_prefix']).rglob('*')))
    assert not any(state[k] for k in ('output_lexists','attempt_claim_lexists','launch_marker_lexists','launch_approval_lexists'))
    assert state['cache_is_dir'] and not state['cache_members']
    states[item['run_id']]=state
shutil.copyfile(R1/'templates/launch-approval.template.json',OWN/'templates/launch-approval.template.json')
command=read(R1/'launch-command-template.json')
command['argv']=[part.replace(str(R1),str(OWN)) for part in command['argv']]
save('launch-command-template.json',command)
save('preservation-after.json',dict(pins_checked=len(pins),drift=drift,registration_states=states,
    owned_cache_empty=not list((OWN/'empty-cache').iterdir()),dispatch_absent=not (OWN/'dispatch').exists(),
    scope='All R1/review files, inherited named source pins, final index and six final registrations, and orchestration state bytes. No whole-workspace snapshot or attribution of concurrent writes. Registered paths match the frozen review absent/empty state.'))
# Exact textual changes: no claims that modified function bodies are unchanged.
a=(R1/'tests/test_bindings.py').read_text();z=(OWN/'tests/test_bindings.py').read_text()
def bodies(text):
    return {node.name:ast.get_source_segment(text,node) for node in ast.walk(ast.parse(text))
            if isinstance(node,ast.FunctionDef) and node.name.startswith('test_')}
old,new=bodies(a),bodies(z)
unchanged=sorted(name for name in old if old[name]==new.get(name))
changed=sorted(name for name in old if old[name]!=new.get(name))
save('control-reuse.json',dict(original_tests=len(old),unchanged_tests=unchanged,adapted_tests=changed,
    guard='Fake suite still forbids every actual subprocess.Popen. Separate real suite permits only owned stdlib helpers and bounded read-only ps.'))
patch=[];changes=[]
for name in manifest['files']:
    prior=R1/name;after=OWN/name
    if prior.exists() and prior.read_bytes()==after.read_bytes(): continue
    patch.extend(difflib.unified_diff(prior.read_text().splitlines(keepends=True) if prior.exists() else [],
        after.read_text().splitlines(keepends=True),fromfile='a/'+name if prior.exists() else '/dev/null',tofile='b/'+name))
    changes.append(dict(path=name,original_sha256=sha(prior) if prior.exists() else None,sha256=sha(after)))
(OWN/'exact-input-diff.patch').write_text(''.join(patch))
save('diff-index.json',dict(base=str(R1),base_source_manifest_sha256=sha(R1/'source-manifest.json'),
    changed_or_new=changes,unchanged_runtime_files=['terminal.py','dependency-binding.json'],
    patch_sha256=sha(OWN/'exact-input-diff.patch')))
save('source-pins.json',dict(supervisor_manifest_sha256=sha(OWN/'source-manifest.json'),
    supervisor_files=manifest['files'],original_supervisor_manifest_sha256=sha(R1/'source-manifest.json'),
    independent_review=dict(path=str(REVIEW/'review.md'),sha256=sha(REVIEW/'review.md'),receipt_sha256=sha(REVIEW/'receipt.json')),
    final_registration_index=dict(path=str(INDEX),sha256=sha(INDEX)),registrations=index['registrations'],
    prelaunch_evidence_scope_path=str(SCOPE),
    prelaunch_evidence_scope_sha256='333d3aada22ddf2959b155160e92d97bb162b95247a1cdac16e6bad089885d6c',
    accepted_worker_manifest_sha256='be7b8b3c9ef90d1e820df417f54863b6943fb746c451105078923916f19a04a2',
    dependency_binding_sha256=sha(OWN/'dependency-binding.json'),preserved_named_inputs_file='preservation-before.json'))
for path in OWN.glob('*.py'): ast.parse(path.read_text(),filename=str(path))
for path in (OWN/'tests').glob('*.py'): ast.parse(path.read_text(),filename=str(path))
save('static-checks.json',dict(stdlib_ast_parse=True,unchanged_fake_controls=len(unchanged),adapted_fake_controls=len(changed),
    final_registration_count=len(states),runtime_limits=read(index['registrations'][0]['registration'])['limits'],
    accepted_worker_or_runtime_edits=0,parent_state_edits=0,real_dispatches=0))
print(json.dumps(dict(supervisor_manifest_sha256=sha(OWN/'source-manifest.json'),preserved_pins=len(pins),unchanged_controls=len(unchanged),adapted_controls=len(changed))))
