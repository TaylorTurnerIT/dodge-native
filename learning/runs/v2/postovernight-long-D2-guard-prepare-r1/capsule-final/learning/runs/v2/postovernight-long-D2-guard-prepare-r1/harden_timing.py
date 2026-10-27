"""Pre-freeze timing audit correction; retain every tested source via attempts."""
from pathlib import Path
import json
H=Path(__file__).resolve().parent;p=H/'long_d2.py';s=p.read_text()
s=s.replace('    digest = hashlib.sha256()\n    if HASH_OBSERVER', '    digest = hashlib.sha256()\n    bytes_hashed = 0\n    if HASH_OBSERVER',1)
s=s.replace('            digest.update(block)\n    if HASH_OBSERVER','            digest.update(block)\n            bytes_hashed += len(block)\n    if HASH_OBSERVER',1)
s=s.replace('stats["bytes"] += Path(path).stat().st_size','stats["bytes"] += bytes_hashed')
s=s.replace("status='interrupted')","status='interrupted',\n                       hash_count_scope='completed controller sha calls; legacy internal file_hash excluded')")
s=s.replace("        path = Path(path)\n        path.parent.mkdir", "        permission(); life.remaining(deadline)\n        path = Path(path)\n        path.parent.mkdir")
s=s.replace("        with path.open('x') as stream:\n            for row", "        permission(); life.remaining(deadline)\n        with path.open('x') as stream:\n            for row")
s=s.replace("        manifest = dict(schema='long_d2_verification_output_v1'", "        manifest = dict(schema='long_d2_verification_output_v1'")
s=s.replace("        save(path.with_suffix('.manifest.json'), manifest)", "        permission(); life.remaining(deadline)\n        save(path.with_suffix('.manifest.json'), manifest)")
s=s.replace("    start, cpu = time.monotonic(), time.thread_time()\n    try:\n        yield\n    finally:\n        if row is not None:\n            row['components'][name] = dict(duration_seconds=time.monotonic()-start,\n                                          thread_cpu_seconds=time.thread_time()-cpu)","    start, cpu = time.monotonic(), time.thread_time()\n    before = None if row is None else (row['files'], row['bytes'])\n    status = 'failed'\n    try:\n        yield\n        status = 'passed'\n    finally:\n        if row is not None:\n            row['components'][name] = dict(duration_seconds=time.monotonic()-start,\n                                          thread_cpu_seconds=time.thread_time()-cpu, status=status,\n                                          observed_hash_files=row['files']-before[0],\n                                          observed_hash_bytes=row['bytes']-before[1])")
p.write_text(s)
p=H/'test_guard_repair.py';s=p.read_text().replace("self.assertEqual((E/'no-ack.jsonl').stat().st_size,0)","self.assertFalse((E/'no-ack.jsonl').exists())\n        self.assertFalse((E/'expired.jsonl').exists())");p.write_text(s)
(H/'timing-audit-correction.json').write_text(json.dumps(dict(reason='Static pre-freeze audit found permission/deadline checks followed timing file creation; require checks before mkdir/open/manifest write',scope='Telemetry only; hash bytes count now actual read bytes, component hash count scope explicit',prior_tested_source='attempts/units-04/sources',next_attempt='attempts/units-05',stress_executed=False,limits_trigger_pins_learner_unchanged=True),indent=2)+'\n')
