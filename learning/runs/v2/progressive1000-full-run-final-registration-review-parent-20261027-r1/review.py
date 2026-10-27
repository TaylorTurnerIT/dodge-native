"""Read-only frozen final registration review; stdlib/hash checks only."""
import hashlib,json,math,os,sys
from pathlib import Path
ROOT=Path.cwd()
P=ROOT/'learning/runs/v2/progressive1000-full-run-evaluator-parent-20261027-r2'
OUT=ROOT/'learning/runs/v2/progressive1000-full-run-final-registration-review-parent-20261027-r1'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text())
expected_source='768b37ca840ba924a67f0260d7320b1c12f19a3797bb3c279ef6de9e344d875a'
expected_registration='590ddf50dfaec0aed329ae4dc6f2b2f6a32708e6b3e173347ed6946d43c43dd1'
assert sha(P/'source-manifest.json')==expected_source
assert sha(P/'registration-final.json')==expected_registration
sys.path.insert(0,str(P));import binding as b
r=read(P/'registration-final.json');draft=read(P/'registration-draft.json')
changed=[k for k in r if r[k]!=draft[k]]
assert set(changed)=={'status','limits','calibration','input_pins'}
assert {k:v for k,v in r['limits'].items() if k not in ('work_seconds','total_seconds')}=={k:v for k,v in draft['limits'].items() if k not in ('work_seconds','total_seconds')}
assert all(r['input_pins'].get(k)==v for k,v in draft['input_pins'].items())
assert len(set(r['input_pins'])-set(draft['input_pins']))==2
cal=read(r['calibration']['parent_acceptance_path'])
assert sha(r['calibration']['parent_acceptance_path'])==r['calibration']['parent_acceptance_sha256']
b.check_pins(cal['pins'])
completion_path=next(k for k in cal['pins'] if k.endswith('/six-endpoint-completion.json'))
completion=read(completion_path);recomputed=[]
for entry in completion['endpoints']:
 h=Path(entry['audit']).parent
 metrics=[json.loads(x) for x in (h/'worker-output/training-metrics.jsonl').read_text().splitlines()]
 d={x['global_update']:x for x in metrics};rows=[]
 for line in (h/'progress-reports.jsonl').read_text().splitlines():
  row=json.loads(line)
  if row['phase']=='between_updates' and 'guard_calls' not in row:
   i=row['completed_updates'];frames=d[i]['counters']['raw_frames']-(d[i-1]['counters']['raw_frames'] if i>1 else 0)
   rows.append(dict(update=i,collection_seconds=row['phase_seconds']['collection'],returned_gameplay_frames=frames,seconds_per_frame=row['phase_seconds']['collection']/frames))
 assert len(rows)==60
 worker=read(h/'worker-output/worker-result.json')
 recomputed.append(dict(run_id=entry['run_id'],worst_collection=max(rows,key=lambda x:x['seconds_per_frame']),measured_updates=60,peak_rss_bytes=worker['peak_rss_bytes'],peak_mps_driver_bytes=worker['peak_mps_driver_bytes']))
assert recomputed==cal['measurements']
worst=max(x['worst_collection']['seconds_per_frame'] for x in recomputed)
prior=r['calibration']['prior_measurement'];historical=prior['elapsed_seconds']/prior['raw_frames']
assert worst==cal['current_worst_seconds_per_frame'] and historical==cal['historical_evaluation_seconds_per_frame']
assert math.ceil(2*max(worst,historical)*129117184+10)==35132==r['limits']['work_seconds']==cal['work_seconds']
assert r['limits']['total_seconds']==35142 and r['limits']['cleanup_seconds']==10
assert max(x['peak_rss_bytes'] for x in recomputed)==972111872==cal['peak_measured_training_RSS_bytes']
assert max(x['peak_mps_driver_bytes'] for x in recomputed)==2382184448==cal['peak_measured_training_MPS_bytes']
assert cal['fresh_dedicated_evaluation_benchmark'] is False and len(cal['limitations'])==4
b.validate_static(r,require_registered=True,hash_checkpoints=True)
assert r['evaluation_rng_seed']==2026102702 and r['bootstrap']['seed']==2026102701
assert r['seeds']==list(range(0xD3000000,0xD3000400)) and len(r['policies'])==7
assert r['semantics']['planned_episodes']==7168
for key in ('output','attempt_claim_path','launch_marker_path'):
 assert not os.path.lexists(r[key]),key
for name in ('launch-envelope.json','parent-execution.json','execution-exit.json','observer.log','cancel'):
 assert not os.path.lexists(P/name),name
assert not (P/'dispatch'/r['run_id']).exists()
state=read(r['state_path']);assert all(state.get(k)is None for k in ('active_long_campaign','active_inference_diagnostic','active_inference_campaign','active_inference_lease'))
acceptance=read(P/'source-acceptance.json')
assert acceptance['status']=='accepted_source_review_only' and acceptance['source_manifest_sha256']==expected_source
assert sha(acceptance['independent_review'])==acceptance['independent_review_sha256']
assert read(acceptance['independent_review'])['status']=='no_blocking_source_findings'
assert not any(k=='torch' or k.startswith('torch.') or k=='dodge_rl' or k.startswith('dodge_rl.') for k in sys.modules)
assert sha(P/'source-manifest.json')==expected_source and sha(P/'registration-final.json')==expected_registration
report=dict(schema='progressive1000_final_frozen_registration_independent_review_v1',status='no_blocking_findings',source_manifest_sha256=expected_source,registration_sha256=expected_registration,blocking_findings=[],verified=['Final delta restricted to status, measured wall limits, calibration acceptance, and two external pins.','All 360 update collection costs, resource maxima and conservative projection independently recomputed.','Static registered preflight passed including all seven checkpoint byte hashes, accepted producer identities, source/runtime/dependency pins, cohort reservation and seed exclusion.','Registered cache empty, imports bytecode-disabled, lexical interpreter exact.','Output, attempt, marker, dispatch and launch evidence unspent; conflicting leases absent.','Numeric sampling and bootstrap RNG fixed before evaluation.','Exact source and final-registration SHA unchanged before and after review.'],calibration_limits=cal['limitations'],fresh_dedicated_evaluation_benchmark=False,static_registered_preflight='passed',checkpoint_access='SHA256 byte hashing only; no deserialization',torch_imported=False,native_imported=False,model_used=False,launch=False,ledger_writes=False,launch_authority=False,remaining_parent_action='Publish exact gate acceptance and run parent launcher once; this receipt grants no launch authority.')
with (OUT/'receipt.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps(dict(status=report['status'],static_preflight='passed',work_seconds=35132,source_sha=expected_source,registration_sha=expected_registration)))
