"""Validate JSON, re-verify frozen pins, write receipt.json and output-manifest.json (manifest excludes itself)."""
import hashlib, json, sys
from pathlib import Path
ROOT = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79'); OUT = Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
R10 = ROOT / 'learning/runs/v2/postovernight-long-D2-boundary-prepare-r10'
pins = json.loads((R10 / 'parent-frozen-pins.json').read_text())
post = {k: sha(ROOT / k) == v for k, v in pins.items()}
validation = {}
for name in ('plan.json', 'input-hashes.json', 'model-results.json'):
    try: json.loads((OUT / name).read_text()); validation[name] = 'valid'
    except Exception as error: validation[name] = 'INVALID: ' + repr(error)
results = json.loads((OUT / 'model-results.json').read_text())
assertions = results['assertions']
receipt = dict(schema='escalation_reap_design_sonnet_receipt_v1', json_validation=validation,
    frozen_pins_reverified_after_work=sum(post.values()), frozen_pins_total=len(post),
    protocol_r7_sha256_after=sha(ROOT / 'learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r7.json'),
    model_assertions_passed=sum(1 for v in assertions.values() if v is True), model_assertions_total=len(assertions), model_assertions_failed=[k for k, v in assertions.items() if v is not True],
    commands=['cd /Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79',
              'PYTHONDONTWRITEBYTECODE=1 learning/.venv/bin/python -I -B learning/runs/v2/postovernight-long-D2-escalation-reap-design-sonnet-r1/model_harness.py > .../model-run.log 2>&1   (rc=0)',
              'learning/.venv/bin/python -I -B .../build_plan_and_hashes.py', 'learning/.venv/bin/python -I -B .../finalize_receipt.py'],
    not_run=['OS stage/probes/stress/startup rehearsal','existing 91 stdlib unit methods','ML/native imports, checkpoint/env/inference/gradients/training','lease/scheduler/commit/PR/deploy/messages','nested delegation/provider calls','live signals/processes'],
    wrote_only_inside=str(OUT.relative_to(ROOT)), frozen_edited=False,
    limits='Pure modeled proof (fake clock/process/IPC around real executor/inner/receipt code); not OS closure; source proposal only; no auto follow-on.')
(OUT / 'receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
manifest = {p.name: dict(sha256=sha(p), bytes=p.stat().st_size) for p in sorted(OUT.iterdir()) if p.is_file() and p.name != 'output-manifest.json'}
(OUT / 'output-manifest.json').write_text(json.dumps(dict(excludes_itself=True, files=manifest), indent=2, sort_keys=True) + '\n')
print(json.dumps(receipt, indent=1)[:1800]); print(len(manifest), 'files in manifest')
