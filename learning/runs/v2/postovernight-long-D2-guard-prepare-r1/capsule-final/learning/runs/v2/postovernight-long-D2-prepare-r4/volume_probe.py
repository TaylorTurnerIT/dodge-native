"""Pure stdlib warm-cache pin and 512 MiB artifact-volume controls."""
from pathlib import Path
import json
import time
import long_d2 as c
HERE=Path(__file__).resolve().parent

def main():
    out=HERE/'hash-volume-control';out.mkdir()
    block=b'\0'*(1024*1024);path=out/'synthetic-512MiB.bin'
    start=time.monotonic()
    with path.open('xb') as stream:
        for _ in range(512):stream.write(block)
        stream.flush()
    write=time.monotonic()-start
    start=time.monotonic();digest=c.sha(path);artifact=time.monotonic()-start
    pins=c.read_json(HERE/'expanded-inventory.json')['full_pins']
    start=time.monotonic();c.verify_files(pins);full=time.monotonic()-start
    receipt=dict(stdlib_only=True,ML_imports=False,artifact_bytes=path.stat().st_size,artifact_sha256=digest,
        artifact_write_seconds=write,artifact_hash_seconds=artifact,full_pin_count=len(pins),full_pin_hash_seconds=full,
        full_pin_bytes=sum(Path(p).stat().st_size for p in pins),
        each_inside_30_second_reserve=artifact<30 and full<30,full_pin_IO_inside_5_seconds=full<=5,
        cache_scope='ordinary local filesystem; repeated immutable files can be warm cached',
        future_ML_runtime_measured=False,future_artifact_volume_guaranteed=False)
    c.save(HERE/'hash-volume-receipt.json',receipt)
    c.require(receipt['each_inside_30_second_reserve'] and receipt['full_pin_IO_inside_5_seconds'],'Hash controls exceed fixed bounds')
    print(json.dumps(receipt,sort_keys=True))

if __name__=='__main__':main()
