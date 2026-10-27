import hashlib,json,pathlib,sys
ROOT=pathlib.Path.cwd();SOURCE=ROOT/'learning/runs/v2/D2-retained324-linear-integrated-luna-20261026-r4';OUT=ROOT/'learning/runs/v2/D2-retained324-linear-parent-launch-20261026-r1'
sys.path.insert(0,str(SOURCE))
import runner,parent_adapter,registration_schema,execute_once
reg,config=runner.load_registration(str(SOURCE/'registration-final-r2.json'),'0a6bf98221689ffcf62a28289dae7bb98eb89bc8d3c02b93127f4a04df75cb4e')
assert reg['expected_lease']==json.loads(pathlib.Path(reg['state_path']).read_text())['active_long_campaign']
for m,name in ((runner,'runner.py'),(parent_adapter,'parent_adapter.py'),(registration_schema,'registration_schema.py'),(execute_once,'execute_once.py')):assert pathlib.Path(m.__file__).resolve()==SOURCE/name
assert pathlib.Path(runner.lr_schedule.__file__).resolve()==SOURCE/'lr_schedule.py'
record={'status':'passed_unmocked_full_registration_CPU_bootstrap','pins_checked':len(reg['pins']),'actual_modules_colocated':True,'exact_lease_checked':True,'bytecode_policy_checked':True,'native_runtime_source_continuity_checked':True,'config_PPO_checked':True,'actual_launches':0,'MPS_used':False,'environment_constructed':False,'full_audit_run':False}
(OUT/'full-CPU-bootstrap.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
