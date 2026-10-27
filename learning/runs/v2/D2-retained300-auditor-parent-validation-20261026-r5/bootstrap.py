import json,pathlib,sys
ROOT=pathlib.Path.cwd()
SOURCE=ROOT/'learning/runs/v2/D2-retained300-all-candidate-auditor-luna-20261026-r5'
sys.path.insert(0,str(SOURCE))
import wrapper as w
w.bind_bytecode();w.reject_preloaded_dodge()
reg=w.load_registration();w.bind_interpreter(reg)
pins=w.verify_pins(reg['pins'])
a=w.load_auditor()
runner,loaded,config=a.load_frozen()
if loaded!=reg:raise RuntimeError('Bootstrap registration differs')
dependencies=w.bind_dependency_origins(reg)
a.import_runtime=w.make_strict_import_runtime(a.import_runtime,reg)
ckpt,gate,identity=a.import_runtime(reg)
w.check_versions(reg)
origins=w.check_loaded_dodge(reg,pathlib.Path(reg['runtime_root']).resolve(),reg['runtime_continuity']['member_sha256'])
w.bind_observer_directory(w.OBSERVER_DIR)
record={'status':'passed_unmocked_auditor_bootstrap_CPU_only','pins_checked':pins,'dependency_origins':dependencies,'dodge_origins':origins,'exact_lease_checked':True,'full_audit_ran':False,'current_training_outputs_read':False,'MPS_used':False,'environment_constructed':False}
pathlib.Path(__file__).with_name('bootstrap.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'status':record['status'],'pins_checked':pins,'dodge_modules_checked':len(origins),'full_audit_ran':False}))
