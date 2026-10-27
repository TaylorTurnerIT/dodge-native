"""Three extracted helpers on registered CPython; no candidate/project import."""
import ast,contextlib,hashlib,json,math,pathlib,sys,threading
O=pathlib.Path(__file__).resolve().parent;C=O.parent/'postovernight-long-D2-boundary-prepare-r14'
identity=json.loads((C/'long-identity.json').read_text());assert sys.version==identity['runtime_policy']['python'];assert str(pathlib.Path(sys.executable).resolve())==identity['runtime_policy']['interpreter']
source=(C/'long_d2.py').read_text();names={'require','restore_boundary_switch_interval','boundary_switch_interval'};nodes=[n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name in names];assert len(nodes)==3
ns=dict(sys=sys,threading=threading,math=math,contextmanager=contextlib.contextmanager,BOUNDARY_SWITCH_INTERVAL=.0001,Stop=RuntimeError)
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(C/'long_d2.py'),'exec'),ns)
saved=sys.getswitchinterval();rows=[]
try:
 for ticks in list(range(1,2001))+[2731,5000,20000,100000,1000000]:
  sys.setswitchinterval((ticks+.25)/1000000);observed=sys.getswitchinterval();sys.setswitchinterval(.000002);ns['restore_boundary_switch_interval'](observed);assert sys.getswitchinterval()==observed
  with ns['boundary_switch_interval']():
   inside=sys.getswitchinterval();assert inside<=.0001
   with ns['boundary_switch_interval']():assert sys.getswitchinterval()==inside
   assert sys.getswitchinterval()==inside
  assert sys.getswitchinterval()==observed
  rows.append(dict(ticks=ticks,observed=observed,inside=inside,restored=sys.getswitchinterval()))
finally:ns['restore_boundary_switch_interval'](saved)
assert sys.getswitchinterval()==saved
result=dict(status='passed',python=sys.version,executable=sys.executable,source_sha256=hashlib.sha256(source.encode()).hexdigest(),cases=len(rows),rows=rows,final_interval=saved,no_project_imports=True,scope='Registered CPython interval operations only; no OS lifecycle, signals, contention, native or ML validation.')
(O/'registered-quantization-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='rows'}))
