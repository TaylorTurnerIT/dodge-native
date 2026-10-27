"""Read-only R4 identity and retained evidence audit; no execution claims."""
from pathlib import Path
import ast,hashlib,json,sys
OUT=Path(__file__).resolve().parent;PREP=OUT.parent/'postovernight-long-D2-prepare-r4';ROOT=OUT.parents[3]
def read(p):return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def nodes(path):
 s=path.read_text();lines=s.splitlines(True)
 return {n.name:''.join(lines[min([n.lineno]+[d.lineno for d in n.decorator_list])-1:n.end_lineno]) for n in ast.parse(s).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
expected={'long_d2.py':'a8f1e9a979f9f1308417924cf2390e538fd01049557502f5bb1cea270df2bd1a','long_d2_executor.py':'6ab9555a7edc63a6f299cb7c3b90dc5441a53b879e0f9c3c2e12bf5c44ab8b52','long-identity.json':'abd50a467ae9827699648c5509954f96f357725fc50cc33aa15e03bd89884340','capsule-final/capsule-manifest.json':'f0dac0e0eff869504c7b1f17e37a1fd572b0160e8d4daf774045895e44ba2f8a','registration.json':'3fd53b41d47c406d7d5079c49cfa7408d6e9dfc649d3d55520d4e3c081f94f5e'}
assert all(sha(PREP/n)==v for n,v in expected.items())
a=nodes(PREP.parent/'postovernight-long-D2-prepare-r3/long_d2.py');b=nodes(PREP/'long_d2.py')
names=('Learner','Schedule','run_schedule','environment_kwargs','counter_report','compare_control','tree_fingerprint','assert_equal_tree','validate_long_config','expected_lease','assert_lease','check_module_origins','outcome_fields','result_code')
equal={n:a[n]==b[n] for n in names};assert all(equal.values())
def ml_body(path):
 s=path.read_text();w=next(n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef) and n.name=='worker');t=next(n for n in w.body if isinstance(n,ast.With)).body[0]
 return ''.join(s.splitlines(True)[t.body[0].lineno-1:t.body[-1].end_lineno])
assert ml_body(PREP/'long_d2.py')==ml_body(PREP.parent/'postovernight-long-D2-prepare-r3/long_d2.py')
artifacts=read(PREP/'artifact-inventory.json');assert all(sha(PREP/n)==v for n,v in artifacts.items())
assert {str(p.relative_to(PREP)) for p in PREP.rglob('*') if p.is_file()}==set(artifacts)|{'artifact-inventory.json'}
pins=read(PREP/'expanded-inventory.json')['full_pins'];old=read(PREP.parent/'postovernight-long-D2-prepare-r3/expanded-inventory.json')['full_pins'];assert len(pins)==9870 and len(old)==9675 and all(pins.get(n)==v for n,v in old.items())
p3=read(ROOT/'learning/runs/v2-orchestration/postovernight-long-D2-r1-protocol-r3.json');p4=read(ROOT/'learning/runs/v2-orchestration/postovernight-long-D2-r1-protocol-r4.json')
p3['controller']=p4['controller'];p3['registered_at_utc']=p4['registered_at_utc'];p3['terminal_lifecycle']['executor']=p4['terminal_lifecycle']['executor'];assert p3==p4
units=read(PREP/'attempts/units-final/unit-result.json');assert units['methods_run']==71 and units['successful'] and units['errors']==units['failures']==0 and not units['ML_imports']
assert all(sha(PREP/n)==v for n,v in units['sources'].items())
matrices={};groups=set()
for label in ('matrix-01','matrix-final'):
 matrix=read(PREP/'attempts'/label/'summary.json');seen=set();events_total=0
 for row in matrix['results']:
  case=Path(row['argv'][-1]);assert case not in seen;seen.add(case)
  assert read(case/'observed-command.json')==row
  assert row['raw_wait']['returncode']==row['expected'] and not row['harness_kill_required'] and row['elapsed_seconds']<=row['maximum_wall_seconds']
  ev=[json.loads(line) for p in case.glob('*-events.jsonl') for line in p.read_text().splitlines()];events_total+=len(ev)
  options=read(case/'options.json');assert not options.get('phase') or any(x['kind']=='injection' and x['role']+':'+x['phase']==options['phase'] for x in ev)
  assert all(not x['open_writers'] for x in row['writer_checks']) and all(row['positive_group_absence'].values())
  for x in ev:
   if x['kind']=='ownership':groups.update(g['pgid'] for g in x['ownership'].values())
  if (case/'execution/acceptance-receipt.json').exists():groups.update(g['pgid'] for g in read(case/'execution/acceptance-receipt.json').get('ownership',{}).values())
  if options.get('phase')=='outer:final-IO':
   boundaries=[x for x in ev if x['kind']=='final_IO_boundary'];assert boundaries and all(x['latch_phase']=='NORMAL' and not x['watchdog_alive'] and not any(x['guard_handles_alive']) for x in boundaries)
 assert len(seen)==matrix['OS_subprocesses']
 tested=read(PREP/'attempts'/label/'tested-sources.json');drift={n:dict(tested=v,current=sha(PREP/n)) for n,v in tested.items() if sha(PREP/n)!=v}
 for n,v in tested.items():assert sha(PREP/'attempts'/label/'sources'/n)==v
 matrices[label]=dict(cases=len(seen),events=events_total,source_drift=drift)
assert not matrices['matrix-final']['source_drift']
report=dict(status='verified_retained_only',exact_inputs=expected,protected_ML_nodes=equal,worker_ML_try_body_equal=True,artifact_entries=len(artifacts),full_pins=len(pins),old_pins_exact=len(old),protocol_three_field_revision_only=True,retained_units=71,retained_worker_AST_scenarios=len(list((PREP/'attempts/units-final').glob('worker-*.json'))),matrices=matrices,retained_unique_groups=len(groups),post_matrix_helpers=sorted(set(units['sources'])-set(read(PREP/'attempts/matrix-final/tested-sources.json'))),old_R3_aggregate_stdout_restored=False,old_R2_minus14_cause='unproven; no retry',ML_imports=[n for n in sys.modules if n.split('.')[0] in ('torch','numpy','dodge_rl')])
with (OUT/'retained-evidence-audit.json').open('x') as f:json.dump(report,f,sort_keys=True,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('exact_inputs','protected_ML_nodes')}))
