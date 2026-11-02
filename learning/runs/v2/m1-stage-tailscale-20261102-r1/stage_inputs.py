"""Verify and stage accepted immutable inputs on the named M1 host."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

ROOT = Path('/Users/taylor/Projects/dodge-native')
OUT = ROOT / 'learning/runs/v2/m1-stage-tailscale-20261102-r1'
EXPECTED = '31117e6b875ca06d0715b653f5cd90f6fa925a4ffa007a3ecd335846e49f1dbe'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def durable(path, data):
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_RDONLY)
    os.fsync(fd)
    os.close(fd)

def unpack(archive, destination):
    members = archive.getmembers()
    names = [m.name for m in members]
    assert len(names) == len(set(names)), 'Duplicate archive member'
    for member in members:
        name = PurePosixPath(member.name)
        assert not name.is_absolute() and '..' not in name.parts
        assert member.isfile() or member.isdir(), 'Links and special files forbidden'
        target = destination / member.name
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            durable(target, archive.extractfile(member).read())

bundle = OUT / 'inputs.tar'
assert bundle.stat().st_size == 9297920 and sha(bundle) == EXPECTED
inputs = OUT / 'inputs'
inputs.mkdir()
with tarfile.open(bundle) as archive:
    unpack(archive, inputs)
manifest = json.loads((inputs / 'manifest.json').read_bytes())
expected_files = {row['path'] for row in manifest['files']} | {'manifest.json'}
assert {str(p.relative_to(inputs)) for p in inputs.rglob('*') if p.is_file()} == expected_files
for row in manifest['files']:
    path = inputs / row['path']
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    path.chmod(0o444)
(inputs / 'manifest.json').chmod(0o444)
commit = manifest['source_commit']
assert commit == '20338f462a95fd751be2569f7e8b0da8089990a8'
config = json.loads(subprocess.check_output(['git', 'show', commit + ':learning/runs/v2/performance-loop-20261101-r1/config.json'], cwd=ROOT))
source = OUT / 'accepted-source'
source.mkdir()
data = subprocess.check_output(['git', 'archive', commit, 'learning/experiments/local_performance_loop'], cwd=ROOT)
with tarfile.open(fileobj=io.BytesIO(data)) as archive:
    unpack(archive, source)
for path in (source / 'learning/experiments/local_performance_loop').glob('*.py'):
    original = '/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/' + str(path.relative_to(source))
    assert sha(path) == config['source_pins'][original]
    path.chmod(0o444)
requirements = ''.join(f'{name}=={version}\n' for name, version in sorted(manifest['versions'].items()))
durable(OUT / 'requirements-exact.txt', requirements.encode())
receipt = dict(status='accepted_bytes_and_source_staged_not_runtime_qualified', bundle_sha256=EXPECTED,
    source_commit=commit, file_count=len(manifest['files']), target_environment=manifest['target_environment'],
    inputs=str(inputs), accepted_source=str(source), prior_failure_preserved=True,
    no_checkpoint_load=True, no_native_or_device_work=True)
durable(OUT / 'staging-acceptance.json', (json.dumps(receipt, indent=2) + '\n').encode())
print(json.dumps(receipt))
