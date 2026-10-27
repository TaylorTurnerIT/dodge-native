import ast,json,math
from pathlib import Path
O=Path(__file__).resolve().parent;H=O.parent/'postovernight-long-D2-guard-prepare-r1'
s=(H/'long_d2_executor.py').read_text();n=next(n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef) and n.name=='accept_observed');m=ast.Module(body=[n],type_ignores=[]);ns={'math':math,'NORMAL_SECONDS':7200};exec(compile(m,'frozen-accept-observed','exec'),ns)
receipt={'schema':'long_d2_outer_acceptance_v1','accepted':True,'expected_exit_code':2,'experiment_status':'complete','outcome':'budget_closed_below_gate','teacher_qualified':False,'training_parent_eligible':False}
r={'valid_receipt_plus_raw2':ns['accept_observed'](receipt,2,1.0),'same_receipt_plus_raw1':ns['accept_observed'](receipt,1,1.0),'scope':'pure source-extracted acceptance predicate; no subprocess/campaign'};assert r['valid_receipt_plus_raw2'] and not r['same_receipt_plus_raw1'];(O/'acceptance-discriminator.json').write_text(json.dumps(r,indent=2)+'\n');(O/'accept-observed-executed.ast.txt').write_text(ast.dump(m,indent=2)+'\n');print(json.dumps(r))
