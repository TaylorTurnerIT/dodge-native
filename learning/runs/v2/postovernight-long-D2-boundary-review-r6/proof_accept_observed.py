"""Run the exact extracted acceptance consumer against local, hash-bound files.

The fixture changes only filesystem roots/constants, and supplies no process or
ML evidence. All hash/JSON/file validation and summary validation are real.
"""
import ast
import copy
import hashlib
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
CANDIDATE = HERE.parent / 'postovernight-long-D2-boundary-prepare-r6'
FIXTURE = HERE / 'acceptance-fixture'
FIXTURE.mkdir()
c = SimpleNamespace(ORIGINAL_ROOT=FIXTURE, PREPARE_REL='prepare')
life = SimpleNamespace()
integrity = SimpleNamespace()
ns = dict(Path=Path, hashlib=hashlib, json=json, math=math, os=os, c=c, life=life,
          integrity=integrity, NORMAL_SECONDS=7200, HASH_OBSERVER=None,
          VERIFY_LOCAL=SimpleNamespace(), REGISTRATION_PATH=FIXTURE/'registration.json')

def extract(filename, names):
    source = (CANDIDATE / filename).read_text()
    nodes = [n for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    assert {n.name for n in nodes} == set(names)
    (HERE / ('consumer-extracted-' + filename)).write_text('\n\n'.join(ast.get_source_segment(source,n) for n in nodes)+'\n')
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(CANDIDATE/filename),'exec'),ns)

extract('lifecycle.py', {'Stop'})
c.Stop=life.Stop=ns['Stop']
extract('long_d2.py', {'require','sha','read_json','verify_files'})
for name in ('require','sha','read_json','verify_files'):setattr(c,name,ns[name])
extract('boundary_integrity.py', {'need','summary_valid'})
integrity.summary_valid=ns['summary_valid']
c.INNER_SECONDS=7170;c.WORKER_SECONDS=7140
extract('long_d2_executor.py', {'validate_wait_reports','accept_observed'})

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')

registration={k:'a'*64 for k in ('protocol_sha256','config_sha256','identity_sha256','classification_sha256','reservation_sha256')}
registration.update(schema='long_d2_executor_registration_v2',class_manifest_hashes={'B':'b'*64,'R':'c'*64,'A':'d'*64},class_counts={'B':1,'R':1,'A':1},output=str(FIXTURE/'output'))
leaf=FIXTURE/'input.txt';leaf.write_text('source-only fixture\n')
registration['pins']={str(leaf):c.sha(leaf)}
save(ns['REGISTRATION_PATH'],registration)
regsha=c.sha(ns['REGISTRATION_PATH'])
worker={k:registration[k] for k in ('protocol_sha256','config_sha256','identity_sha256','classification_sha256')}
worker.update(schema='long_d2_worker_integrity_summary_v1',manifests=registration['class_manifest_hashes'],boundary_count=1,boundaries=[{'sequence':0,'verdict':'passed'}],final_live_legacy=True,final_runtime={'verdict':'passed','cache':{'empty':True}},first_local_failure=None,first_global_failure=None)
summary={k:registration[k] for k in ('protocol_sha256','config_sha256','identity_sha256','classification_sha256','reservation_sha256')}
summary.update(schema='long_d2_compact_integrity_summary_v1',manifests=registration['class_manifest_hashes'],worker=worker,first_local_failure=None,first_global_failure=None)
for endpoint in ('preflight','postflight'):
    summary[endpoint]=dict(role='outer_'+endpoint,verdict='passed',counts=registration['class_counts'],classification_sha256=registration['classification_sha256'],manifests=registration['class_manifest_hashes'])
summary_path=FIXTURE/'integrity-summary.json';save(summary_path,summary);summarysha=c.sha(summary_path)
lease={'fixture':'exact unchanged required lease'};save(FIXTURE/'prepare/required-lease.json',lease)
output=Path(registration['output']);output.mkdir()
bindings={'artifacts':{},'integrity_summary_path':str(summary_path),'integrity_summary_sha256':summarysha}
for name,key in (('artifact-manifest.json','artifact_manifest_sha256'),('long-run-result.json','run_result_sha256'),('finalization-result.json','terminal_sha256'),('long-worker-result.json','worker_result_sha256')):
    save(output/name,{});bindings[key]=c.sha(output/name)
receipt=dict(schema='long_d2_outer_acceptance_v2',accepted=True,expected_exit_code=0,experiment_status='complete',outcome='D2_progress_gate_passed',teacher_qualified=False,training_parent_eligible=False,registration=registration,registration_sha256=regsha,bindings=bindings,integrity_summary=summary,required_lease=lease,t0_monotonic_hex=(100.).hex(),ownership={role:dict(pid=pid,pgid=pid,parent_at_registration=parent,new_session_verified=True,group_absent=True) for role,pid,parent in [('supervisor',200,150),('worker',300,200)]})
receipt['inner_wait']=dict(pid=200,reaped_by=150,returncode=0,direct_child_reaped=True,raw_wait_status=0,observed_monotonic=100.8)
receipt['worker_wait']=dict(pid=300,reaped_by=200,returncode=0,direct_child_reaped=True,raw_wait_status=0,observed_monotonic=100.5)
def consume(r,raw=0):return ns['accept_observed'](r,raw,1.0,registration_sha256=regsha,summary_sha256=summarysha)
results={'control_0':consume(receipt)}
raw2=copy.deepcopy(receipt);raw2.update(expected_exit_code=2,outcome='budget_closed_below_gate')
for key in ('inner_wait','worker_wait'):raw2[key].update(returncode=2,raw_wait_status=512)
results['control_2']=consume(raw2,2)
missing=copy.deepcopy(receipt);missing.pop('inner_wait');missing.pop('worker_wait')
results['missing_reports_rejected']=not consume(missing)
failed=copy.deepcopy(receipt)
for key in ('inner_wait','worker_wait'):failed[key].update(returncode=1,direct_child_reaped=False,raw_wait_status=256)
results['failed_reports_rejected']=not consume(failed)
results['stale_accepted_receipt_raw1_rejected']=not consume(receipt,1)
for field,value in [('pid',999),('reaped_by',999),('raw_wait_status',15),('observed_monotonic',float('nan')),('observed_monotonic',float('inf')),('observed_monotonic',7240.),('observed_monotonic','100.5')]:
    bad=copy.deepcopy(receipt);bad['worker_wait'][field]=value
    results['reject_'+field+'_'+str(value)]=not consume(bad)
save(HERE/'consumer-proof-results.json',results)
save(FIXTURE/'receipt-control.json',receipt)
print(json.dumps(results,indent=2,sort_keys=True))
assert all(results.values())
