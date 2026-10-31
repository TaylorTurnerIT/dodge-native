"""Source-only058 payload from owned code/engine and verified vendored source.

No checkpoint, pool contents, CLI config, compiled binary, SQLite or run output
is included. Original420 and the fixed pool are separate future admitted inputs.
"""
import argparse
import io
from pathlib import Path
import tarfile

import common as c

ROOT=Path(__file__).resolve().parent


def write(output,vendor_root):
    manifest={}
    with tarfile.open(output,'x') as archive:
        sources=[path for path in ROOT.iterdir() if path.is_file() and path.suffix in ('.py','.json','.md')]
        for directory in ('runtime','native_source','result_safety'):
            sources.extend(path for path in (ROOT/directory).rglob('*') if path.is_file())
        vendors=list(Path(vendor_root).rglob('*'))
        members=[(path,'source/'+path.relative_to(ROOT).as_posix()) for path in sources]
        members.extend((path,'vendor/'+path.relative_to(vendor_root).as_posix()) for path in vendors if path.is_file())
        for path,name in sorted(members,key=lambda pair:pair[1]):
            c.need(not path.is_symlink() and '__pycache__' not in path.parts,'Non-source or symlink payload member')
            c.need(path.suffix not in ('.pt','.so','.dylib','.sqlite3','.pyc'),'Compiled/private payload member forbidden')
            data=path.read_bytes();manifest[name]=c.sha(path)
            item=tarfile.TarInfo(name);item.size=len(data);item.mode=0o444
            archive.addfile(item,io.BytesIO(data))
        data=c.canonical(manifest);item=tarfile.TarInfo('source-manifest.json');item.size=len(data)
        archive.addfile(item,io.BytesIO(data))
    return dict(path=str(output),sha256=c.sha(output),bytes=Path(output).stat().st_size,members=manifest)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--vendor',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();print(c.canonical(write(args.output,Path(args.vendor))).decode())
