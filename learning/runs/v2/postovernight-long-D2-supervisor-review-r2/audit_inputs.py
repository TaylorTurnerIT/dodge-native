"""Read-only inventory and final byte comparison; stdlib only."""
from pathlib import Path
import hashlib
import json
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PREP = HERE.parent / 'postovernight-long-D2-prepare-r2'

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def save(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

if sys.argv[1] == 'before':
    paths = {p.resolve() for p in PREP.rglob('*') if p.is_file()}
    protected = json.loads((PREP / 'protected-before.json').read_bytes())
    paths.update((ROOT / p).resolve() for p in protected)
    identity = json.loads((PREP / 'long-identity.json').read_bytes())
    paths.update(Path(p).resolve() for p in identity['original_input_pins'])
    paths.update((ROOT / p).resolve() for p in identity['controller_sources'])
    paths.update((ROOT / p).resolve() for p in ('learning/runs/v2-orchestration/postovernight-long-D2-r1-protocol-r2.json',
                 'learning/runs/v2-orchestration/postovernight-long-D2-r1-config.json'))
    files = {str(p): sha(p) for p in sorted(paths)}
    save('input-sha256-manifest.json', files)
    save('input-inventory-receipt.json', dict(files=len(files), captured_at_utc=datetime.now(timezone.utc).isoformat(),
         manifest_sha256=sha(HERE / 'input-sha256-manifest.json'),
         protected_expected_mismatches=[p for p, h in protected.items() if sha(ROOT / p) != h]))
else:
    before = json.loads((HERE / 'input-sha256-manifest.json').read_bytes())
    changed = [p for p, h in before.items() if not Path(p).is_file() or sha(Path(p)) != h]
    save('input-sha256-verification-after.json', dict(files=len(before), mismatches=changed,
         manifest_sha256=sha(HERE / 'input-sha256-manifest.json'), verified_at_utc=datetime.now(timezone.utc).isoformat()))
    print(json.dumps(dict(files=len(before), mismatches=changed)))
