"""Package owned source/fake evidence only. No runtime or launch operations."""
import ast
from datetime import datetime,timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import probe
import build_registration
HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'confirmed324-probe-finalization-repair-sol-20261026-r5'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v): Path(p).write_text(json.dumps(v,sort_keys=True,indent=2)+'\n')
assert sys.dont_write_bytecode and sys.pycache_prefix==str(HERE/'empty-pycache')
assert not any((HERE/'empty-pycache').iterdir())
assert not any(k.split('.')[0] in {'torch','numpy','dodge_rl'} for k in sys.modules)
# Move preparation-history scripts away from the final review entrypoints.
history=HERE/'tmp/preparation-history'; history.mkdir(exist_ok=True)
for name in ('prepare_files.py','adapt_supervisor.py','refine_source.py','tighten_source.py','harden_consumer.py','update_test_fixtures.py','fix_synthetic_controls.py','final_contract_refinements.py','final_sampler_fix.py'):
    path=HERE/name
    if path.exists(): path.rename(history/name)
reg=build_registration.build()
assert reg['status']=='draft_parent_review_required' and not Path(reg['output_dir']).exists()
assert not Path(reg['one_shot_marker']).exists() and not Path(reg['attempt_claim_path']).exists()
write(HERE/'registration-template.json',reg)
write(HERE/'parent-run-command-template.json',{'status':'inert_not_launch_authority','prerequisites':'separate parent freeze/review/calibration/lease/once-only authorization','environment':{'PYTHONDONTWRITEBYTECODE':'1','PYTHONPYCACHEPREFIX':'PARENT_REGISTERED_NEW_EMPTY_CACHE'},'argv':[reg['runtime']['python_path'],'-B',str(HERE/'supervisor_cli.py'),'--registration','PARENT_FROZEN_ABSOLUTE_REGISTRATION_PATH','--registration-sha256','PARENT_FROZEN_REGISTRATION_SHA256'],'required_venv_prefix':reg['runtime']['expected_venv_prefix'],'expected_registration_schema':probe.SCHEMA})
source_files=sorted(p for p in HERE.iterdir() if p.suffix=='.py')
for p in source_files: ast.parse(p.read_bytes(),filename=str(p))
source={p.name:sha(p) for p in source_files}
write(HERE/'source-manifest.json',{'schema':'confirmed324_restore_probe_prepared_source_v1','authority':'inventory only; no parent source acceptance','files':source,'input_manifest_sha256':sha(HERE/'input-manifest.json'),'external_R3_manifest_sha256':probe.R3_SHA,'authoritative_R5_manifest_sha256':probe.R5_SHA})
production=('build_registration.py','probe.py','supervisor_cli.py','worker_cli.py')
def diff(names):
    text=''
    for name in names:
        before=(OLD/name).read_text().splitlines(True) if (OLD/name).is_file() else []
        after=(HERE/name).read_text().splitlines(True)
        text+=''.join(difflib.unified_diff(before,after,fromfile=str(OLD/name) if before else '/dev/null',tofile=str(HERE/name)))
    return text
(HERE/'production-diff.patch').write_text(diff(production))
(HERE/'exact-diff.patch').write_text(diff([p.name for p in source_files]+['README.md','input-manifest.json','registration-template.json','parent-run-command-template.json']))
# Verify R5 execute() body changed only telemetry/result schema, not lifecycle.
a=ast.parse((OLD/'supervisor_cli.py').read_text()); b=ast.parse((HERE/'supervisor_cli.py').read_text())
old_execute=next(n for n in a.body if isinstance(n,ast.FunctionDef) and n.name=='execute')
new_execute=next(n for n in b.body if isinstance(n,ast.FunctionDef) and n.name=='execute')
old_body=ast.get_source_segment((OLD/'supervisor_cli.py').read_text(),old_execute)
new_body=ast.get_source_segment((HERE/'supervisor_cli.py').read_text(),new_execute)
normalized=new_body.replace('rows=None; resource_samples=[]','rows=None')
normalized=normalized.replace("\n     resource_samples.append({'elapsed_seconds':now-start,'process_group_current_rss_bytes':rss,'process_rows':rows})",'')
normalized=normalized.replace("'schema':'confirmed324_claimed_restore_probe_outer_receipt_v1'","'schema':'d2_layerb_rng_reference_probe_outer_receipt_v1'")
normalized=normalized.replace("'resource_samples':resource_samples,'registered_limits':reg['limits'],",'')
assert normalized==old_body,'unexpected lifecycle-body change'
summary=probe.read(HERE/'fake-test-summary.json')
assert summary['tests_run']==46 and not summary['failures'] and not summary['errors'] and not summary['loaded_runtime_modules'] and not summary['blocked_runtime_import_requests']
legacy_log=(HERE/'lifecycle-tests-pass2.log').read_text()
assert 'Ran 48 tests' in legacy_log and legacy_log.rstrip().endswith('OK')
focused_log=(HERE/'tests.log').read_text(); assert 'Ran 46 tests' in focused_log and focused_log.rstrip().endswith('OK')
write(HERE/'test-results.json',{'schema':'source_only_synthetic_controls_v1','passed':94,'carried_predecessor':48,'focused':46,'lifecycle_log':'lifecycle-tests-pass2.log','focused_log':'tests.log','focused_summary':summary,'lifecycle_execute_body_preserved_except_telemetry_and_receipt_schema':True,'limits_are_proposals_not_measurements':True,'actual_runtime_qualified':False,'final_source_files':source,'retained_initial_failures':['tests-pass1.log','lifecycle-tests.log','tests-pass4.log'],'test_instrumentation':'synthetic_worker_driver.py bypasses gates only in test subprocess; supervisor tests substitute only the child executable; consumer semantic fixtures are fabricated'})
before=probe.read(HERE/'preservation-before.json')
after={p:sha(p) for p in before['immutable']}
assert after==before['immutable'],'immutable input drift'
state=before['state']; now=sha(state['path'])
write(HERE/'preservation-after.json',{'immutable':after,'immutable_unchanged':True,'enumerated_files':len(after),'state':{'path':state['path'],'before_sha256':state['sha256'],'after_sha256':now,'unchanged':now==state['sha256'],'owned_by_parent_not_written_by_this_task':True},'root_README_unchanged':after[str(probe.ROOT/'README.md')]==before['immutable'][str(probe.ROOT/'README.md')],'cache_empty':not any((HERE/'empty-pycache').iterdir()),'scope':'enumerated read set only; no global filesystem claim'})
receipts=[]
for p in sorted((HERE/'tmp').rglob('*.json')):
    if p.name in ('outer-receipt.json','result.json','worker-failure.json','COMMITTED.json','driver-result.json','driver-scope.json'):
        receipts.append(dict(path=str(p.relative_to(HERE)),sha256=sha(p),bytes=p.stat().st_size))
write(HERE/'synthetic-receipt-index.json',{'schema':'synthetic_evidence_index_v1','authority':'synthetic only; never runtime qualification or parent acceptance','files':receipts})
receipt={'schema':'confirmed324_restore_probe_source_preparation_v1','status':'prepared_not_registered_not_runtime_qualified','created_at_utc':datetime.now(timezone.utc).isoformat(),'owned_output':str(HERE),'source_manifest':{'path':str(HERE/'source-manifest.json'),'sha256':sha(HERE/'source-manifest.json')},'input_manifest':{'path':str(HERE/'input-manifest.json'),'sha256':sha(HERE/'input-manifest.json')},'accepted_R3_manifest_sha256':probe.R3_SHA,'authoritative_R5_manifest_sha256':probe.R5_SHA,'accepted_checkpoint_sha256':probe.PARENT,'accepted_integrity_receipt_sha256':probe.PARENT_RECEIPT,'accepted_confirmation_sha256':probe.ACCEPTANCE,'reference_registration_sha256':'0150cfcdbec53ff4322f72e5fa224cb6a914f3505ea732c0722511b5e031c398','seed_vectors_sha256':reg['vectors_sha256'],'replica':1,'study_id':probe.STUDY,'arm':probe.ARM,'scope':probe.SCOPE,'limits':probe.LIMITS,'limits_status':'proposed, not measured','test_summary':{'passed':94,'carried':48,'focused':46,'stdlib_fake_only':True,'initial_failures_retained':True},'preparation_operations':dict(real_Torch_NumPy_native_imports=0,real_MPS_calls=0,checkpoint_deserializations=0,actual_models_environments_training_evaluation=0,actual_probe_launches=0,actual_lease_writes=0,actual_marker_or_transition_claims=0,actual_training_seeds_consumed=0,subdelegations=0,commits=0,pushes=0,writes_outside_owned_output=0),'interpreter':summary,'preservation':{'enumerated_files':len(after),'unchanged':True,'parent_state_unchanged_at_packaging':now==state['sha256'],'root_README_unchanged':True},'lifecycle_execute_body_preserved_except_telemetry_and_receipt_schema':True,'template_authority':'none; proposed parent directory absent; no lease installed','remaining_parent_gates':['unique run/output/owner-token/outer-marker/subclaim and fresh empty cache','full registration/source/input freeze','independent exact-source review','separate actual dependency/runtime/resource calibration decision','fresh parent state and exact probe lease installation','separately authorized exactly-once execution without retry','parent terminal audit, process absence and replica-1 qualification only'],'evidence_limits':['No real runtime validation or timing/memory measurement.','No hard filesystem/hash/fsync/finalization watchdog.','MPS heartbeat sampling begins after adapter authentication/checkpoint validation.','Package bytes are unpinned.','Python profile is not general native-code instrumentation.','SIGKILL cannot run worker cleanup; parent supervises/reaps groups.','Exclusive publication can leave partial files; I/O failures can prevent complete receipts.','Preservation checks cover enumerated inputs only.']}
write(HERE/'receipt.json',receipt)
artifacts=[]
for p in sorted(HERE.iterdir()):
    if p.is_file() and p.name not in ('artifact-manifest.json','finalization.log'): artifacts.append(dict(path=p.name,bytes=p.stat().st_size,sha256=sha(p)))
write(HERE/'artifact-manifest.json',{'schema':'restore_probe_preparation_artifacts_v1','files':artifacts,'synthetic_evidence_index':'synthetic-receipt-index.json','excluded_live_packaging_stdout':'finalization.log'})
print(json.dumps(dict(status=receipt['status'],tests_passed=94,immutable_files_unchanged=len(after),parent_state_unchanged=now==state['sha256'],cache_empty=True,source_manifest_sha256=sha(HERE/'source-manifest.json'))))
