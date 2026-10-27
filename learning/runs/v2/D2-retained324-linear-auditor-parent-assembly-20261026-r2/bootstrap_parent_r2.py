import hashlib,json,pathlib,sys
ROOT=pathlib.Path.cwd();SOURCE=ROOT/'learning/runs/v2/D2-retained324-linear-auditor-prepare-luna-20261026-r2';OWN=ROOT/'learning/runs/v2/D2-retained324-linear-auditor-parent-assembly-20261026-r2'
sys.path.insert(0,str(SOURCE))
import wrapper
BINDING_SHA='392cce25d75694ab87980ef7de148560216baf93fa3e3ce6f977adbd63bab36b'
wrapper.load_binding(BINDING_SHA);reg=wrapper.load_registration();wrapper.bind_interpreter(reg);wrapper.reject_preloaded_dodge();wrapper.bind_bytecode()
worker_cache=pathlib.Path(reg['import_policy']['pycache_prefix']);assert worker_cache==ROOT/'learning/runs/v2/D2-retained324-continuation-prepare-luna-20261026-r2/empty-pycache'
assert worker_cache.is_dir() and not any(worker_cache.iterdir())
pins_before=wrapper.verify_pins(reg['pins']);dependency_origins=wrapper.bind_dependency_origins(reg)
auditor=wrapper.load_auditor();runner,loaded,config=auditor.load_frozen(expected_binding_sha256=BINDING_SHA);assert loaded==reg
launcher=auditor.load_pinned_module('execute_once_frozen',auditor.LAUNCHER_PATH,auditor.LAUNCHER_SHA);assert launcher.r is runner
strict=wrapper.make_strict_import_runtime(auditor.import_runtime,reg);strict(reg)
origins=wrapper.check_loaded_dodge(reg,pathlib.Path(reg['runtime_root']).resolve(),reg['runtime_continuity']['member_sha256'])
assert wrapper.verify_pins(reg['pins'])==pins_before
assert not any(worker_cache.iterdir()) and not any(wrapper.PYCACHE_PREFIX.iterdir())
assert hashlib.sha256((SOURCE/'audit-binding.json').read_bytes()).hexdigest()==BINDING_SHA
record={'status':'passed_unmocked_cold_auditor_package_and_runtime_bootstrap','binding_sha256':BINDING_SHA,'pins_checked':pins_before,'single_cold_runner_load':True,'actual_launcher_bound_to_actual_runner':True,'worker_prefix_empty_pre_post':True,'auditor_prefix_empty_pre_post':True,'strict_Dodge_origins':origins,'dependency_origins':dependency_origins,'MPS_used':False,'environment_constructed':False,'checkpoint_binary_loaded':False,'actual_candidate_audit':False,'lease_cleared':False,'prior_parent_driver_failure':'First driver loaded frozen runner twice in one process; cold-cache guard correctly rejected second import. Original sources unchanged.'}
(OWN/'bootstrap-receipt-r2.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
