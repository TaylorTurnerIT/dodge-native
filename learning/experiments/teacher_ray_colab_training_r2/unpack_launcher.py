"""Pinned CLI TEXT source assembler; permits preexisting inputs/control only."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tarfile


def main():
    root=Path('/content/dodge062')
    if root.is_symlink() or root.resolve()!=root:raise ValueError('Owned058 root must be a direct directory')
    for name in ('source','vendor','build','artifacts'):
        if (root/name).exists() or (root/name).is_symlink():raise ValueError('Consumed/old058 output present: '+name)
    registration=root/'registration.json';digest=os.environ['DODGE062_REGISTRATION_SHA256']
    if registration.is_symlink() or (root/'source-input.tar').is_symlink():raise ValueError('058 input symlink forbidden')
    if hashlib.sha256(registration.read_bytes()).hexdigest()!=digest:raise ValueError('Registration differs')
    reg=json.loads(registration.read_text());payload=root/'source-input.tar'
    if reg['record']!='DODGE-062' or reg['accelerator']!='A100':raise ValueError('Wrong058 source admission')
    with (root/'source-assembly.claimed').open('x') as stream:
        json.dump({'registration_sha256':digest,'job_nonce':reg['job_nonce']},stream)
        stream.flush();os.fsync(stream.fileno())
    if hashlib.sha256(payload.read_bytes()).hexdigest()!=reg['payload_sha256']:raise ValueError('Source archive differs')
    with tarfile.open(payload,'r:') as archive:
        entries=archive.getmembers();names=[entry.name for entry in entries]
        if len(names)!=len(set(names)):raise ValueError('Duplicate source member')
        for entry in entries:
            path=PurePosixPath(entry.name)
            if not entry.isfile() or path.is_absolute() or '..' in path.parts:raise ValueError('Unsafe source member')
        manifest=json.loads(archive.extractfile('source-manifest.json').read())
        if set(names)!={*manifest,'source-manifest.json'}:raise ValueError('Source inventory differs')
        for name,expected in manifest.items():
            if PurePosixPath(name).parts[0] not in ('source','vendor'):raise ValueError('Unexpected source root')
            contents=archive.extractfile(name).read()
            if hashlib.sha256(contents).hexdigest()!=expected:raise ValueError('Source member digest differs')
            target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as stream:stream.write(contents)
    result=dict(schema='dodge_colab_source_assembly_v1',record='DODGE-062',job_nonce=reg['job_nonce'],
        registration_sha256=digest,payload_sha256=reg['payload_sha256'],source_members=len(manifest),
        native_games=0,training_frames=0,trained_weights_saved=False)
    with (root/'source-assembly.json').open('x') as stream:
        json.dump(result,stream,sort_keys=True);stream.flush();os.fsync(stream.fileno())
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
