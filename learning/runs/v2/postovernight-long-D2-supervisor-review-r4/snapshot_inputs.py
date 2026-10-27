"""Read-only input baseline and final comparison; writes only own review files."""
from pathlib import Path
import hashlib,json,time,sys
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
PREP=OUT.parent/'postovernight-long-D2-prepare-r4'
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
if len(sys.argv)>1:
 prior=json.loads((OUT/'input-sha256-manifest.json').read_text());actual={n:sha(n) for n in prior}
 mismatch={n:dict(before=prior[n],after=actual[n]) for n in prior if actual[n]!=prior[n]}
 value=dict(files=len(actual),mismatches=mismatch,monotonic=time.monotonic())
 (OUT/'final-unchanged-check.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value));assert not mismatch
else:
 expected={**json.loads((PREP/'protected-before.json').read_text()),**json.loads((PREP/'expanded-inventory.json').read_text())['full_pins']}
 for path in PREP.rglob('*'):
  if path.is_file():expected.setdefault(str(path),None)
 for path in (ROOT/'learning/runs/v2-orchestration').glob('postovernight-long-D2*'):
  if path.is_file():expected.setdefault(str(path),None)
 for dirname in ('postovernight-long-D2-terminal-design-codex-r1','postovernight-long-D2-terminal-design-opus-r1','postovernight-long-D2-design-opus-r1','postovernight-long-D2-terminal-plan-audit-r1','postovernight-long-D2-supervisor-review-r1','postovernight-long-D2-supervisor-review-r2','postovernight-long-D2-supervisor-review-r3','postovernight-long-D2-r3-evidence-api-audit-r1'):
  for path in (OUT.parent/dirname).rglob('*'):
   if path.is_file():expected.setdefault(str(path),None)
 for name in ('docs/implementation-plan-v2.md','docs/SPEC_PRIVILEGED_VIT_RL.md','learning/runs/v2-orchestration/state.json'):expected.setdefault(str(ROOT/name),None)
 actual={n:sha(n) for n in expected};mismatch={n:dict(expected=expected[n],actual=actual[n]) for n in expected if expected[n] is not None and actual[n]!=expected[n]}
 (OUT/'input-sha256-manifest.json').write_text(json.dumps(actual,sort_keys=True,indent=2)+'\n')
 value=dict(schema='r4_review_input_snapshot_v1',files=len(actual),expected_digest_mismatches=mismatch,python=sys.executable,monotonic=time.monotonic(),ML_imports=[n for n in sys.modules if n.split('.')[0] in ('torch','numpy','dodge_rl')])
 (OUT/'input-check.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value));assert not mismatch
