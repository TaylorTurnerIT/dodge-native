import hashlib,json,os,pathlib,sys
ROOT=pathlib.Path.cwd();SOURCE=ROOT/'learning/runs/v2/D2-retained324-linear-auditor-prepare-luna-20261026-r2';OWN=ROOT/'learning/runs/v2/D2-retained324-linear-auditor-parent-assembly-20261026-r2';OBS=ROOT/'learning/runs/v2/D2-retained324-linear-execution-observer-parent-20261026-r1';RUN=ROOT/'learning/runs/v2/D2-retained324-linear-lr-20261026-r1'
regpath=ROOT/'learning/runs/v2/D2-retained324-linear-integrated-luna-20261026-r4/registration-final-r2.json';reg=json.loads(regpath.read_text());assert hashlib.sha256(regpath.read_bytes()).hexdigest()=='0a6bf98221689ffcf62a28289dae7bb98eb89bc8d3c02b93127f4a04df75cb4e'
obs=json.loads((OBS/'observation.json').read_text());execution=json.loads((RUN/'execution-result.json').read_text());assert obs['success_authoritative'] is True and obs['outer_raw_exit']==obs['worker_raw_exit']==0
for pid in (obs['observer_pid'],obs['outer_pid'],execution['worker_pid']):
 try:os.kill(pid,0)
 except ProcessLookupError:pass
 else:raise RuntimeError(f'Owned process remains:{pid}')
for group in (obs.get('outer_process_group'),execution['owned_pgid']):
 if group is None:continue
 assert type(group) is int and group>1
 try:os.killpg(group,0)
 except ProcessLookupError:pass
 else:raise RuntimeError(f'Owned group remains:{group}')
worker_cache=pathlib.Path(reg['import_policy']['pycache_prefix']);assert worker_cache==ROOT/'learning/runs/v2/D2-retained324-continuation-prepare-luna-20261026-r2/empty-pycache';assert worker_cache.is_dir() and not any(worker_cache.iterdir());assert not any((SOURCE/'empty-pycache').iterdir())
assert json.loads(pathlib.Path(reg['state_path']).read_text())['active_long_campaign']==reg['expected_lease']
sys.path.insert(0,str(SOURCE));import wrapper
result=wrapper.full_mode(observer_dir=str(OBS),expected_binding_sha256='392cce25d75694ab87980ef7de148560216baf93fa3e3ce6f977adbd63bab36b',name='full-audit.json')
assert not any(worker_cache.iterdir()) and not any((SOURCE/'empty-pycache').iterdir())
assert json.loads(pathlib.Path(reg['state_path']).read_text())['active_long_campaign']==reg['expected_lease']
record={'status':'passed_parent_full_candidate_audit','full_audit_sha256':hashlib.sha256((SOURCE/'full-audit.json').read_bytes()).hexdigest(),'binding_sha256':'392cce25d75694ab87980ef7de148560216baf93fa3e3ce6f977adbd63bab36b','owned_process_groups_absent_before':True,'worker_registered_cache_empty_pre_post':True,'auditor_cache_empty_pre_post':True,'lease_unchanged':True,'accepted_checkpoint_or_lease_clear':False}
(OWN/'full-audit-parent-receipt.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record));print(json.dumps({'audit_status':result['audit']['status'],'updates_audited':result['audit']['updates_audited'],'proposed_best_update':result['audit']['proposed_best_update']}))
