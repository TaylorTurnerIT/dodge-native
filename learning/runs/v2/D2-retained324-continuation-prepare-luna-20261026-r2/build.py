import hashlib,json,pathlib
root=pathlib.Path.cwd().resolve(); own=root/'learning/runs/v2/D2-retained324-continuation-prepare-luna-20261026-r2'
base=json.loads((root/'learning/runs/v2/D2-retained300-continuation-freeze-20261026-r5/registration.json').read_text())
sha=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
pa=root/'learning/runs/v2/D2-retained300-parent-terminal-audit-20261026-r1'
receipt_path=pa/'retained-best-candidate-receipt.json'; rec=json.loads(receipt_path.read_text()); cost=pa/'completed-iteration-receipt.json'; audit=pa/'audit.json'; decision=pa/'retained-best-decision.json'
full=root/'learning/runs/v2/D2-retained300-all-candidate-auditor-luna-20261026-r5/full-audit.json'
worker=root/'learning/runs/v2/D2-retained300-continuation-20261026-r1/worker-result.json'
prodreg=pathlib.Path(rec['registration_path']); cfg=pathlib.Path(base['config_path'])
# Preserve historical/runtime/source evidence, replace predecessor component authorities and accepted parent pins.
pins=base['pins']; olddir=root/'learning/runs/v2/D2-retained300-continuation-freeze-20261026-r5'
for n in ('runner.py','execute_once.py','parent_adapter.py','registration_schema.py'): pins.pop(str((olddir/n).resolve()),None)
new_sources={n:own/n for n in ('runner.py','execute_once.py','parent_adapter.py','registration_schema.py')}
for p in new_sources.values(): pins[str(p)]=sha(p)
# Remove prior parent's mutable authority paths from active pins, then pin every new receipt/evidence path.
for key in ('path','terminal_receipt_path','completed_cost_receipt_path','metadata_path','decision_path','audit_path','full_audit_path','producing_worker_result_path','registration_path','source_evaluation_path','source_evaluation_jsonl_path'):
 v=base['parent'].get(key)
 if v: pins.pop(str(pathlib.Path(v).resolve()),None)
for p in [pathlib.Path(rec['checkpoint_path']),receipt_path,cost,audit,decision,full,worker,prodreg,pathlib.Path(rec['evaluation_path']),pathlib.Path(rec['evaluation_jsonl_path']),pathlib.Path(rec['checkpoint_path']+'.json')]: pins[str(p.resolve())]=sha(p)
# update own source pins / dynamic entrypaths
reg=base
reg.update(schema='d2_retained324_same_lr_registration_v1',transition_schema='d2_retained324_same_lr_continuation_v1',run_id='D2-retained324-continuation-20261026-r1',run_seed=4200000001,
 phase_start=324,phase_end=384,expected_total_updates=432,new_updates=60,parent_total_updates=372,output=str(root/'learning/runs/v2/D2-retained324-continuation-20261026-r1'),
 runner_path=str(new_sources['runner.py']),launcher_path=str(new_sources['execute_once.py']),parent_adapter_path=str(new_sources['parent_adapter.py']),
 registration_schema_module_path=str(new_sources['registration_schema.py']),runner_sha256=sha(new_sources['runner.py']),launcher_sha256=sha(new_sources['execute_once.py']),parent_adapter_sha256=sha(new_sources['parent_adapter.py']),registration_schema_module_sha256=sha(new_sources['registration_schema.py']),
 config_sha256='1c24df3eea150160451ada08e9f6844cd67645abf5fb8b712afd14abca930ce8',parent_config_sha256='1c24df3eea150160451ada08e9f6844cd67645abf5fb8b712afd14abca930ce8',
 evaluation_updates=[324,336,348,360,372,384],expected_lease={'authorization':'user_continue_D2_training_v3','kind':'D2_gradient_alignment','parent_checkpoint_sha256':rec['checkpoint_sha256'],'run_id':'D2-retained324-continuation-20261026-r1'},
 cancel_path=str((root/'learning/runs/v2/D2-retained324-continuation-20261026-r1.cancel')),import_policy={'pycache_prefix':str(own/'empty-pycache'),'write_bytecode':False})
reg['limits'].update(max_updates=60,eval_updates=[324,336,348,360,372,384],retries=0,work_seconds=1790,total_seconds=1800,planned_seconds=1750,cleanup_seconds=10,RSS_bytes=6442450944,MPS_bytes=6442450944)
reg['resource_estimate'].update(observed_control_outer_seconds=1137.0270813340321,scaled_seconds=1307.5811435341368,preregistered_work_seconds=1750,hard_work_cap_seconds=1790,outer_cap_seconds=1800,cleanup_reserve_seconds=10,observed_control_optimizer_steps=7680,maximum_arm_optimizer_steps_at_4_epochs=7680,relaxation_permitted=False)
reg['expected_outputs']=['entry-restoration.json','launch-marker.json','worker-launch.json','worker-result.json','worker.log','resources.jsonl','training-episodes.jsonl','training-metrics.jsonl']
for u in [324,336,348,360,372,384]: reg['expected_outputs'] += [f'checkpoint-{u:06d}-candidate.pt',f'checkpoint-{u:06d}-candidate.pt.json',f'development-{u:06d}.json',f'development-{u:06d}.jsonl']
reg['parent'].update(path=rec['checkpoint_path'],sha256=rec['checkpoint_sha256'],sidecar_sha256=rec['checkpoint_sidecar_sha256'],phase='D2',phase_update=324,local_update=24,
 terminal_receipt_path=str(receipt_path),terminal_receipt_sha256=sha(receipt_path),completed_cost_receipt_path=str(cost),completed_cost_receipt_sha256=sha(cost),completed_iteration_receipt_path=str(cost),completed_iteration_receipt_sha256=sha(cost),
 metadata_path=rec['checkpoint_path']+'.json',metadata_sha256=rec['checkpoint_sidecar_sha256'],audit_path=str(audit),audit_sha256=sha(audit),decision_path=str(decision),decision_sha256=sha(decision),full_audit_path=str(full),full_audit_sha256=sha(full),
 producing_worker_result_path=str(worker),producing_worker_result_sha256=sha(worker),registration_path=str(prodreg),registration_sha256=rec['registration_sha256'],source_evaluation_path=rec['evaluation_path'],source_evaluation_sha256=rec['evaluation_sha256'],source_evaluation_jsonl_path=rec['evaluation_jsonl_path'],source_evaluation_jsonl_sha256=rec['evaluation_jsonl_sha256'],
 total_update=372,phase_local_update=24,wall_accounting=rec['wall_accounting'])
reg['resource_cost_anchor']={'authority':'resource_cost_only; no model or continuation authority','path':str(cost),'sha256':sha(cost)}
reg['parent_registration_sha256']=rec['registration_sha256']
reg['pins']=pins
out=own/'registration.json'; out.write_text(json.dumps(reg,indent=2,sort_keys=True)+'\n')
