"""Pure source vendoring from the archived build's verified Cargo crate cache.

No Cargo command, extension import, environment constructor or seed is used.
Output is an owned source artifact, never a shared package/cache mutation.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import tomllib


def prepare(lock_path, cache, output):
    output = Path(output); output.mkdir(exist_ok=False)
    lock = tomllib.loads(Path(lock_path).read_text())
    sources = {}
    for package in lock['package']:
        if 'source' not in package: continue
        if package['source'] != 'registry+https://github.com/rust-lang/crates.io-index':
            raise ValueError('Unsupported dependency source')
        name = package['name'] + '-' + package['version']
        candidates = list(Path(cache).glob('*/' + name + '.crate'))
        if len(candidates) != 1: raise ValueError('Ambiguous/missing locked source: ' + name)
        data = candidates[0].read_bytes()
        if hashlib.sha256(data).hexdigest() != package['checksum']:
            raise ValueError('Locked crate archive digest differs: ' + name)
        destination = output / name; destination.mkdir()
        checksums = {}
        with tarfile.open(candidates[0], 'r:gz') as archive:
            for member in archive.getmembers():
                path = PurePosixPath(member.name)
                if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != name:
                    raise ValueError('Unsafe dependency source path')
                if member.isdir(): continue
                if not member.isfile(): raise ValueError('Non-file dependency source')
                relative = PurePosixPath(*path.parts[1:]).as_posix()
                contents = archive.extractfile(member).read()
                target = destination / relative; target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as stream: stream.write(contents)
                checksums[relative] = hashlib.sha256(contents).hexdigest()
        with (destination / '.cargo-checksum.json').open('x') as stream:
            json.dump({'package': package['checksum'], 'files': checksums}, stream, sort_keys=True)
        sources[name] = dict(archive_sha256=package['checksum'], source_archive=str(candidates[0]), files=len(checksums))
    return sources
