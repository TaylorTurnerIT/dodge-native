"""Supplement the retained postrun collector error using only actual JSON fields."""
import copy
import datetime
import hashlib
import json
from pathlib import Path
import time
ROOT=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
OUT=ROOT/'learning/runs/v2/postovernight-long-D2-execution-observer-r1'
CAMPAIGN=ROOT/'learning/runs/v2/postovernight-long-D2-campaign-r1'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_text())
def save(n,v):
 with (OUT/n).open('x') as f:json.dump(v,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n')
def require(ok,message):
 if not ok:raise RuntimeError(message)
def rows(n):
 with (CAMPAIGN/n).open() as f:return [json.loads(line) for line in f if line.strip()]
start=time.monotonic();started=datetime.datetime.now(datetime.timezone.utc).isoformat()
original_manifest=read(OUT/'artifact-manifest.json')
require(all(sha(OUT/n)==digest for n,digest in original_manifest.items()),'Original observer artifact digest changed')
original=read(OUT/'execution-result.json');schedule=rows('schedule.jsonl');metrics=rows('training-metrics.jsonl');index=read(CAMPAIGN/'checkpoint-index.json')
previous=dict(U=25.,E=150.,C=15.,F=30.);cadence=[];complete=[];admitted=[]
for row in schedule:
 r=row['reserves']
 require(r['C']==15 and r['F']==30 and r['U']>=previous['U'] and r['E']>=previous['E'],'Frozen reserve contract differs')
 previous=r
 if row['event']=='cadence_evaluation':require(row['phase_updates']%16==0,'Off-cadence evaluation');cadence.append(row['phase_updates'])
 if row['event']=='update_complete':complete.append(row['phase_updates'])
 if row['event']=='update_admitted':admitted.append(row['phase_updates'])
require(cadence==[0,16,32,48] and complete==list(range(1,52)) and admitted==list(range(52)),'Schedule cadence/complete/admitted accounting differs')
for i,row in enumerate(metrics,1):
 require(row['counters']['phase_updates']==i and row['update_progress']['complete'] is True and row['update_progress']['in_update'] is False and row['metrics']['finite'] is True,'Metric complete/finite accounting differs')
require(len(metrics)==51,'Metric count differs')
require(all(r['counters']['phase_updates']%16==0 for r in index if r['tag']=='long_evaluated'),'Evaluated checkpoint cadence differs')
require(all(r['counters']['phase_updates']%8==0 and r['counters']['phase_updates']%16!=0 for r in index if r['tag']=='long_periodic'),'Periodic checkpoint cadence differs')
entry=read(CAMPAIGN/'entry-control.json');require(entry['zero_gradients_before_control'] is True and entry['matched'] is True,'Runtime entry-before-gradient receipt differs')
proof=dict(passed=True,complete_update_records=51,cadence_phase_updates=cadence,update_complete_phase_updates=complete,update_admitted_from_phase_updates=admitted,final_reserves=previous,schedule_contains_monotonic_field=False,entry_before_gradient_evidence='Frozen run_schedule calls entry evaluate_checkpoint before update_once; actual entry-control.json records zero_gradients_before_control=true; entry checkpoint counters.phase_updates=0. No independent schedule timestamp claim.',original_collector_error="KeyError('monotonic')",training_reexecuted=False,experiment_invocations=1)
save('postflight-schedule-supplement-r1.json',proof)
process_rows=rows_placeholder=None
observer_peaks={}
with (OUT/'process-observations.jsonl').open() as f:
 for line in f:
  row=json.loads(line)
  for item in row.get('owned',[]):observer_peaks[item['role']]=max(observer_peaks.get(item['role'],0),item['rss_bytes'])
final=copy.deepcopy(original)
final['original_execution_result_sha256']=sha(OUT/'execution-result.json')
final['retained_audit_tool_error']=dict(check='schedule_and_complete_update_accounting',error="KeyError('monotonic')",reason='Collector assumed a timestamp field absent from frozen schedule schema.',original_result='execution-result.json',supplement='postflight-schedule-supplement-r1.json')
final['checks']['schedule_and_complete_update_accounting']=dict(passed=True,evidence=proof,corrected_by_supplement=True)
final['errors']=[e for e in final['errors'] if not e.startswith('schedule_and_complete_update_accounting:')]
final['observer_sampled_process_RSS_maxima_bytes']=observer_peaks
final['outer_inner_resource_receipts_missing']=True
final['resource_scope']='Worker stream and worker final receipt preserve separate RSS/MPS maxima. Outer/inner finalized resource receipts are missing; slower observer process samples are supplemental only.'
final['postrun_audit_supplement_started_utc']=started
final['postrun_audit_supplement_seconds']=time.monotonic()-start
final['status']='failed';final['parent_acceptance_condition']=False;final['progress_gate_passed']=False
final['canonical_result']='execution-result-final.json'
save('postflight-command-receipt.json',dict(original_audit_argv=[str(ROOT/'learning/.venv/bin/python'),'-B',str(OUT/'audit_after_exit-final.py')],original_audit_cwd=str(ROOT),original_audit_returncode=0,original_audit_seconds=original['postrun_readonly_audit_seconds'],supplement_argv=['/usr/bin/python3','-B',str(OUT/'audit_supplement_r1.py')],ML_import_or_checkpoint_deserialization=False,original_collector_error_retained=True))
save('execution-result-final.json',final)
manifest={str(p.relative_to(OUT)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='artifact-manifest-supplement-r1.json'}
save('artifact-manifest-supplement-r1.json',manifest)
print(json.dumps(dict(status=final['status'],raw_exit=final['raw_wait_report']['returncode'],actual_wall_seconds=final['actual_wall_seconds'],phase_updates=final['phase_updates'],latest_evaluation=final['latest_evaluation'],errors=final['errors'],retained_collector_error=final['retained_audit_tool_error'],observer_RSS_maxima=observer_peaks,source_hashes='postflight-input-verification.json',supplement_seconds=final['postrun_audit_supplement_seconds']),sort_keys=True))
