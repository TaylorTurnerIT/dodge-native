"""Regenerate own Python/runtime source manifests without imports or native calls."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def write(path,doc):Path(path).write_text(json.dumps(doc,sort_keys=True,indent=2)+'\n')
def main():
    runtime=HERE/'runtime'
    rfiles={str(p.relative_to(runtime)):sha(p) for p in sorted(runtime.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and not p.is_symlink()}
    write(HERE/'runtime-manifest.json',{'schema':'dodge_seed_priority_runtime_manifest_v1',
        'profile':'copied_release_binary_python_runtime_modified','launch_authority':False,'files':rfiles})
    includes=[]
    for p in HERE.rglob('*'):
        if not p.is_file() or p.is_symlink() or '__pycache__' in p.parts:continue
        rel=p.relative_to(HERE)
        if rel.parts[0] in {'registrations','attempts','worker-output','empty-pycache','launch-markers','deferred'}:continue
        if rel in {Path('source-manifest.json'),Path('runtime-manifest.json')} or rel.parts[:1]==('runtime',):continue
        if p.suffix=='.py' or str(rel) in {'README.md','experiment.json','shared-config.json','seed-vectors.json',
            'input-manifest.json','binary-manifest.json','evaluation-contract.json','training-pool-candidate.json'}:
            includes.append(rel)
    files={str(rel):sha(HERE/rel) for rel in sorted(includes)}
    write(HERE/'source-manifest.json',{'schema':'dodge_seed_priority_source_manifest_v1',
        'status':'owned_source_inventory_no_launch_authority','launch_authority':False,
        'runtime_manifest_sha256':sha(HERE/'runtime-manifest.json'),'files':files})
    print(json.dumps({'source_files':len(files),'runtime_files':len(rfiles),
        'source_manifest_sha256':sha(HERE/'source-manifest.json'),
        'runtime_manifest_sha256':sha(HERE/'runtime-manifest.json')},sort_keys=True))
if __name__=='__main__':main()
