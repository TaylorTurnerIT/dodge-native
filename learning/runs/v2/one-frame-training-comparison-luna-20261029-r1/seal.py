"""Seal exact source/runtime members for independent review. Never authorizes launch."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import binding as b

SOURCE_FILES = (
    'README.md', 'audit.py', 'binding.py', 'build_registration.py', 'death_telemetry.py',
    'evaluation.py', 'execute_once.py', 'fingerprints.py', 'launch.py', 'observe.py',
    'policy-plan.json', 'power_guard.py', 'registration-schema.json', 'screen.py', 'seal.py',
    'seeds.py', 'stream-audit.py', 'terminal.py', 'tests.py', 'worker.py',
    'runtime-tests/test_registered_ppo.py',
)


def members(root):
    result={}
    for path in sorted(Path(root).rglob('*')):
        if '__pycache__' in path.parts or path.suffix == '.pyc':
            raise ValueError('bytecode is forbidden in the selected runtime: '+str(path))
        if path.is_symlink():
            raise ValueError('symlink in runtime tree: '+str(path))
        if path.is_file():
            result[str(path.relative_to(root))]=b.sha(path)
    return result


def seal(*, reseal=False):
    runtime_files=members(b.RUNTIME_ROOT)
    b.need(runtime_files, 'pinned runtime tree is empty')
    runtime_doc=dict(schema='one_frame_training_comparison_runtime_manifest_v1',
        runtime_root=str(b.RUNTIME_ROOT.resolve()), files=runtime_files, launch_authority=False)
    if b.RUNTIME_MANIFEST.exists():
        b.need(b.read(b.RUNTIME_MANIFEST)==runtime_doc,
               'runtime members changed after initial sealing; preserve and review runtime successor')
    else:
        b.save(b.RUNTIME_MANIFEST,runtime_doc)
    files={}
    for name in SOURCE_FILES:
        path=b.HERE/name
        b.need(path.is_file() and not path.is_symlink(), 'registered package member missing: '+name)
        files[name]=b.sha(path)
    files[b.RUNTIME_MANIFEST.name]=b.sha(b.RUNTIME_MANIFEST)
    source_doc=dict(schema='one_frame_training_comparison_source_manifest_v1',run_id=b.RUN_ID,
        files=files,launch_authority=False)
    if b.SOURCE_MANIFEST.exists():
        b.need(reseal, 'source manifest exists; use explicit --reseal for owned source update')
        for path in (b.HERE/'attempt.claimed',b.HERE/'launch.claimed',b.HERE/'launch-envelope.json',
                     b.HERE/'worker-output',b.HERE/'dispatch'):
            b.need(not os.path.lexists(path), 'cannot reseal after exactly-once dispatch began: '+str(path))
        old=b.read(b.SOURCE_MANIFEST)
        b.need(old.get('run_id')==b.RUN_ID and old.get('launch_authority') is False,
               'existing source manifest is not owned inert source')
        staging=b.SOURCE_MANIFEST.with_name('.source-manifest.pending.json')
        with staging.open('x') as stream:
            json.dump(source_doc,stream,indent=2,sort_keys=True);stream.write('\n')
            stream.flush();os.fsync(stream.fileno())
        os.replace(staging,b.SOURCE_MANIFEST)
        directory=os.open(b.HERE,os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    else:
        b.save(b.SOURCE_MANIFEST,source_doc)
    return source_doc,runtime_doc


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--seal',action='store_true',required=True)
    parser.add_argument('--reseal',action='store_true')
    args=parser.parse_args();seal(reseal=args.reseal);print('source and runtime manifests sealed; launch authority remains false')
