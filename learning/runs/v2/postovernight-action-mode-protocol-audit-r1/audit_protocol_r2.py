"""Saved-data/source protocol audit only. No Torch, native environment, model, or tests."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path.cwd()
PROTOCOL=ROOT/'learning/runs/v2-orchestration/postovernight-action-mode-r1-protocol.json'
OUT=ROOT/'learning/runs/v2/postovernight-action-mode-protocol-audit-r1/raw-checks.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
p=json.loads(PROTOCOL.read_text())
checks={'protocol_path':str(PROTOCOL.relative_to(ROOT)),'protocol_sha256':sha(PROTOCOL),'auditor_python':sys.version,'scope':'plain Python parsing and hashing only; no models, Torch, gameplay, tests, benchmark or runner inspection'}
assert p['version']=='v2_postovernight_action_mode_diagnostic_v1'
assert p['episodes_expected']==len(p['checkpoints'])*(1+len(p['sampling']['controller_seeds']))*p['development_seeds']['count']==768
assert p['development_seeds']['last']-p['development_seeds']['first']+1==64
assert p['development_seeds']['first']==0xD0000000 and p['development_seeds']['last']==0xD000003F
assert len(p['order'])==len(set(p['order']))==12
assert p['wall_budget_seconds']==600 and p['cleanup_reserve_seconds']==10
assert p['device']=='mps' and p['cpu_fallback'] is False
assert p['statistics']['unit'].startswith('64 paired game-seed clusters')
assert p['statistics']['primary_checkpoint']=='phase104'
assert p['logging']['no_killer_inference'] is True
sources={f:sha(ROOT/f) for f in p['foundation_sources']}
assert sources==p['foundation_sources']
checks['foundation_source_count']=len(sources)
checks['foundation_sources_match']=True
checks['foundation_identity_sha256']=sha(ROOT/p['foundation_identity_path'])
assert checks['foundation_identity_sha256']==p['foundation_identity_sha256']
checks['checkpoint_hashes']={}
checks['historical_controls']={}
fields={'episode_index','seed','score_raw_fixed','score','alive_frames','gameplay_frames','terminated','truncated','objective_return'}
for c in p['checkpoints']:
 assert sha(ROOT/c['path'])==c['sha256']
 checks['checkpoint_hashes'][c['label']]=c['sha256']
 if c['control'] is None:
  checks['historical_controls'][c['label']]={'historical_control_available':False}
  continue
 assert sha(ROOT/c['control'])==c['control_sha256']
 rows=[json.loads(x) for x in (ROOT/c['control']).read_text().splitlines()]
 assert len(rows)==64 and len({r['seed'] for r in rows})==64
 rows.sort(key=lambda r:r['seed'])
 assert [r['seed'] for r in rows]==list(range(0xD0000000,0xD0000040))
 assert [r['episode_index'] for r in rows]==list(range(64))
 assert all(set(r)==fields for r in rows)
 assert all(r['score']==r['score_raw_fixed']/65536 and r['terminated'] != r['truncated'] for r in rows)
 assert all(r['objective_return']==r['score']+r['alive_frames']/100-5*r['terminated'] for r in rows)
 checks['historical_controls'][c['label']]={'historical_control_available':True,'rows':64,'fields':sorted(fields),'mean_alive_frames':sum(r['alive_frames'] for r in rows)/64,'mean_score':sum(r['score'] for r in rows)/64,'raw_frames':sum(r['gameplay_frames'] for r in rows),'max_episode_gameplay_frames':max(r['gameplay_frames'] for r in rows),'control_sha256':c['control_sha256']}
checks['expected_episodes']=768
checks['absolute_worst_case_raw_frames']=768*18000
checks['absolute_worst_case_decision_trace_rows']=768*4500
checks['sampling_controller_seeds']=p['sampling']['controller_seeds']
checks['protected_hashes_unchanged_after_audit']=all(sha(ROOT/f)==h for f,h in sources.items())
assert checks['protected_hashes_unchanged_after_audit']
OUT.write_text(json.dumps(checks,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:v for k,v in checks.items() if k not in ('auditor_python',)},indent=2))
