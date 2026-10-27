"""Read-only source/manifest audit. No project imports or campaign execution."""
import ast
import hashlib
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
CANDIDATE=HERE.parent/'postovernight-long-D2-boundary-prepare-r3'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for b in iter(lambda:stream.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def read(path):return json.loads(Path(path).read_text())

initial=read(HERE/'input-hashes.json')
initial_by_path={r['path']:r for r in initial['inputs']}
source_snapshot=HERE/'source-snapshot';source_snapshot.mkdir()
snapshots={}
for p in sorted(CANDIDATE.iterdir()):
    if p.is_file() and p.suffix in {'.py','.json'}:
        rel=str(p.relative_to(ROOT));raw=p.read_bytes();actual=hashlib.sha256(raw).hexdigest()
        assert actual==initial_by_path[rel]['sha256'],rel
        (source_snapshot/p.name).write_bytes(raw);snapshots[rel]=actual

def blocks(path):
    source=path.read_text()
    return {n.name:ast.get_source_segment(source,n) for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}

def worker_body(path):
    source=path.read_text();tree=ast.parse(source)
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='worker')
    node=next(n for n in node.body if isinstance(n,ast.With)).body[0]
    lines=source.splitlines(True)
    return ''.join(lines[node.body[0].lineno-1:node.body[-1].end_lineno])

protected=('Learner','Schedule','run_schedule','environment_kwargs','counter_report','compare_control','tree_fingerprint','assert_equal_tree','validate_long_config','expected_lease','assert_lease','check_module_origins','outcome_fields','result_code')
current=blocks(CANDIDATE/'long_d2.py');equal={}
for label in ('postovernight-long-D2-guard-prepare-r1','postovernight-long-D2-prepare-r4'):
    old=HERE.parent/label/'long_d2.py';old_blocks=blocks(old)
    equal[label]={k:current[k]==old_blocks[k] for k in protected}
    equal[label]['worker_ML_try_body']=worker_body(CANDIDATE/'long_d2.py')==worker_body(old)
    assert all(equal[label].values())
p=read(ROOT/'learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r4.json')
identity=read(CANDIDATE/'long-identity.json');classification=read(CANDIDATE/'classification.json')
B=classification['B'];R=read(CANDIDATE/'native-manifest.json')['files'];archive=read(CANDIDATE/'archive-manifest.json');A=archive['files']
classes={'B':B,'R':R,'A':A};counts={k:len(v) for k,v in classes.items()}
assert counts=={'B':235,'R':37,'A':9998}
canonical={}
for label,bindings in classes.items():
    for path,digest in bindings.items():
        key=str(Path(path).resolve())
        assert key not in canonical or canonical[key]==(label,digest),(key,canonical.get(key),(label,digest))
        canonical[key]=(label,digest)
old=read(HERE.parent/'postovernight-long-D2-guard-prepare-r1/expanded-inventory.json')['full_pins']
assert len(old)==10091
for path,digest in old.items():
    matches=[label for label,pins in classes.items() if pins.get(path)==digest]
    assert len(matches)==1,(path,matches)
old_identity=read(HERE.parent/'postovernight-long-D2-guard-prepare-r1/long-identity.json')
for key,count in (('retained_r4_union',9870),('retained_r3_union',9675)):
    assert len(old_identity[key])==count
    assert all(old.get(n)==d for n,d in old_identity[key].items())
legacy={str(ROOT/name):digest for name,digest in p['base_identity']['sources'].items()}
assert len(legacy)==75 and all(sha(n)==digest and B[n]==digest for n,digest in legacy.items())
foundation=p['base_identity']['foundation']
dependencies=[str(ROOT/'learning/runs/v2-orchestration/milestone2-acceptance-r2.json'),str(ROOT/'learning/runs/v2/milestone2-campaign-freeze-r4/frozen-identity.json'),*foundation['binary_and_receipt_sha256']]
assert all(path in B for path in dependencies)
assert sha(ROOT/p['config_path'])=='2ac814d3842228017d09669364a8391344722da56ad19f41ad9030dbb930c2db'
assert p['config']['phase_settings']['run_seed']==5562873868232098305
assert sha(ROOT/p['parent_checkpoint'])=='ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f'
assert (CANDIDATE/'processes.py').read_bytes()==(HERE.parent/'postovernight-long-D2-prepare-r4/processes.py').read_bytes()
report=dict(schema='boundary_r3_static_source_audit_v1',snapshot_hashes=snapshots,protected_blocks_equal=equal,legacy75_current_hashes=legacy,foundation_dependencies_classified_B=dependencies,class_counts=counts,canonical_class_conflicts=0,old_full_bindings_covered=10091,retained_r4=9870,retained_r3=9675,processes_equal_R4=True,config_seed_D1_hash_checked=True,no_ML_native_imports=True,initial_snapshot_parent_attempt_metadata_excluded_from_authority=True,elapsed_since_initial_snapshot_seconds=time.time()-initial['timestamp'])
(HERE/'static-source-audit.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in {'snapshot_hashes','protected_blocks_equal','legacy75_current_hashes','foundation_dependencies_classified_B'}},indent=2))
