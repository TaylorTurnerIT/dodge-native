"""Prepare and verify the new attempt's filesystem before any child or claim."""
from pathlib import Path
import os
import tempfile

CHILD_DIRECTORIES=('owner','supervisor','worker','acceptance')


def create_layout(root):
    """Staging only: create a fresh layout, never repair a used attempt."""
    root=Path(root)
    (root/'output').mkdir()
    for name in CHILD_DIRECTORIES:
        (root/'output'/name).mkdir()
    (root/'empty-pycache').mkdir()


def check_layout(root):
    """Fail before claims/spawn when a required directory is unsafe or absent."""
    root=Path(root)
    output=root/'output';cache=root/'empty-pycache'
    required=[output,*[output/name for name in CHILD_DIRECTORIES],cache]
    for directory in required:
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError('Required real directory missing or unsafe: '+str(directory))
    if sorted(p.name for p in output.iterdir()) != sorted(CHILD_DIRECTORIES):
        raise ValueError('Output root contains prior claims,logs or unexpected entries')
    if any(list(directory.iterdir()) for directory in required[1:]):
        raise ValueError('Required child/cache directory is not empty; no retry')
    checked=[]
    for directory in required:
        descriptor,path=tempfile.mkstemp(prefix='.directory-preflight-',dir=directory)
        path=Path(path)
        # A failed probe remains for first-failure inspection. Delete only a
        # successfully verified probe owned by this call.
        with os.fdopen(descriptor,'wb') as stream:
            stream.write(b'dodge-prelaunch-directory-v1\n');stream.flush();os.fsync(stream.fileno())
        if path.read_bytes()!=b'dodge-prelaunch-directory-v1\n':
            raise ValueError('Directory probe readback differs: '+str(directory))
        path.unlink()
        descriptor=os.open(directory,os.O_RDONLY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)
        checked.append(str(directory))
    return dict(status='required_directories_empty_real_writable_fsync_checked',directories=checked,
                host_coordinator='absent; host caller creates it once after this check',
                claims_created=0,children_spawned=0,lease_operations=0)
