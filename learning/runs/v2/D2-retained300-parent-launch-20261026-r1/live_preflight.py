import copy,json,sys
from pathlib import Path
source=Path(sys.argv[1]);owned=Path(sys.argv[2]);digest=sys.argv[3]
sys.path.insert(0,str(source))
import runner,registration_schema
reg=json.loads((source/'registration.json').read_text());controls={}
for key,value in [('schema','d2_retained276_continuation_registration_v1'),('run_id','D2-retained276-lr3em5-20261026-r1'),('output',str(owned/'wrong-output'))]:
    bad=copy.deepcopy(reg);bad[key]=value
    try:runner.validate_registration(bad)
    except ValueError:controls[key]=True
    else:raise AssertionError('Runner identity mutation passed: '+key)
loaded,config=runner.load_registration(source/'registration.json',digest)
assert Path(registration_schema.__file__).resolve()==source/'registration_schema.py'
assert runner.sha(source/'registration_schema.py')==loaded['registration_schema_module_sha256']
assert not Path(loaded['output']).exists()
result={'status':'passed_unmocked_registration_preflight','registration_sha256':digest,'pins':len(loaded['pins']),'identity_negatives':controls,'lease_assertion':'unmocked','registration_schema_origin':registration_schema.__file__,'config_sha256':loaded['config_sha256'],'worker_started':False,'MPS_used':False}
(owned/'live-preflight.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
