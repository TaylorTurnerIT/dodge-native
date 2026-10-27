"""Accept the completed LR arm and retain its best complete-update candidate."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path.cwd();OWN=Path(__file__).resolve().parent
PREP=ROOT/'learning/runs/v2/D2-retained276-lr3em5-prepare-luna-20261026-r2';RUN=ROOT/'learning/runs/v2/D2-retained276-lr3em5-20261026-r2';OBSERVER=ROOT/'learning/runs/v2/D2-retained276-lr3em5-execution-observer-luna-20261026-r2';AUDITOR=ROOT/'learning/runs/v2/D2-retained276-lr3em5-auditor-luna-20261026-r2'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_text())
def write(name,v):
 with (OWN/name).open('x') as f:f.write(json.dumps(v,indent=2,sort_keys=True)+'\n')
reg=read(PREP/'registration.json');statepath=Path(reg['state_path']);expected_lease=reg['expected_lease']
def guard():
 s=read(statepath);assert s['active_long_campaign']==expected_lease and s['active_inference_diagnostic'] is None
 assert not Path(reg['cancel_path']).exists() and s.get('cancel_requested') in (None,False)
 for p,h in reg['pins'].items():assert sha(p)==h,p
 return s
s=guard();full=read(AUDITOR/'full-audit.json');obs=read(OBSERVER/'observation.json');worker=read(RUN/'worker-result.json');execution=read(RUN/'execution-result.json')
assert full['mode']=='full_parent_only' and full['audit']['updates_audited']==[276,288,300,312,324,336]
assert full['registration']['pins_checked_before_and_after']==13801 and obs['success_authoritative']
assert obs['launch_count']==execution['actual_worker_launch_count']==1 and obs['outer_raw_exit']==obs['worker_raw_exit']==0
assert execution['directly_reaped'] and obs['worker_group_absent'] and obs['outer_process_absent'] and obs['worker_process_absent']
assert obs['outer_inclusive_wall_seconds']<=1800 and worker['elapsed_seconds']<=1790
assert obs['max_aggregate_rss_bytes']<=6*1024**3 and obs['worker_resources']['peak_mps_driver_bytes']<=6*1024**3
assert worker['counters']['updates']==60 and worker['counters']['environment_decisions']==983040 and worker['counters']['optimizer_steps']<=7680
absence={}
for pid in [obs['observer_pid'],obs['outer_pid'],obs['worker_launch']['worker_pid']]:
 r=subprocess.run(['/bin/ps','-p',str(pid),'-o','pid=,pgid=,lstart=,command='],capture_output=True,text=True)
 assert r.returncode==1 and not r.stdout.strip(),str(pid);absence[str(pid)]={'returncode':r.returncode,'stdout':r.stdout}
for pgid in {obs['outer_process_group'],obs['worker_launch']['owned_pgid']}:
 try:os.killpg(pgid,0)
 except ProcessLookupError:pass
 else:raise AssertionError('Owned process group remains: '+str(pgid))
candidates=full['audit']['candidates'];best=max(candidates,key=lambda k:(candidates[k]['mean_alive_frames'],-int(k)))
assert int(best)==300==full['audit']['proposed_best_update'];assert candidates[best]['mean_alive_frames']>2483.65625
checkpoint=RUN/f'checkpoint-{int(best):06d}-candidate.pt';assert sha(checkpoint)==candidates[best]['checkpoint_sha256']
sys.path.insert(0,str(PREP));import runner
sys.path.insert(0,reg['runtime_root']);import torch
torch.set_num_threads(2)
from dodge_rl.checkpoints import load_checkpoint
selected=load_checkpoint(checkpoint,expected_sha256=sha(checkpoint));assert selected['phase_update']==300 and selected['local_update']==24 and selected['update_progress']['complete']
assert selected['cumulative_counters']['updates']==348 and selected['counters']['optimizer_steps']==3072
assert all(g['lr']==3e-5 for g in selected['optimizer']['param_groups'])
certificate=RUN/'development-000300.json';cert=read(certificate);rows=cert['evaluation']['rows'];v=sorted(r['alive_frames'] for r in rows)
assert len(v)==64 and sum(v)/64==2704.390625
from collections import Counter
performance={'update':300,'q1_bottom16_mean':sum(v[:16])/16,'q4_top16_mean':sum(v[-16:])/16,'mean_alive_frames':sum(v)/64,'mean_score':cert['evaluation']['mean_score'],'episodes':64,'deaths':64,'caps':0,'death_causes':dict(Counter(r['death_cause'] for r in rows)),'checkpoint_sha256':sha(checkpoint),'certificate_sha256':sha(certificate)}
outer=obs['outer_inclusive_wall_seconds'];cost=7118.78208862512+outer;future=selected['cumulative_selected_checkpoint_trajectory_wall_seconds'];now=datetime.now(timezone.utc).isoformat()
audit={'schema':'d2_lr3em5_parent_terminal_audit_v1','status':'accepted_completed_iteration_and_selected_intermediate300','at_utc':now,'registration_sha256':sha(PREP/'registration.json'),'source_pins_unchanged':13801,'full_audit_sha256':sha(AUDITOR/'full-audit.json'),'full_audit_path':str(AUDITOR/'full-audit.json'),'observer_sha256':sha(OBSERVER/'observation.json'),'all_six_candidates_audited':True,'selected_update':300,'selected_performance':performance,'raw_exits':{'outer':0,'worker':0},'observed_outer_seconds':outer,'process_absence':absence,'owned_groups_absent':True,'raw_counters':worker['counters'],'selected_counters':selected['counters'],'selected_cumulative_counters':selected['cumulative_counters'],'resource_limits_passed':True,'UTC_annotation':'Observer UTC timestamps jumped during execution; declared monotonic duration governs the time budget. UTC difference is not used as elapsed runtime.','child_summary_correction':'Child returned score tail means; canonical performance here and six-candidate audit use alive-frame tail means.'}
write('audit.json',audit)
completed={'schema':'d2_completed_iteration_parent_audit_receipt_v1','status':'accepted_completed_training_iteration_with_best_replacement','at_utc':now,'run_id':reg['run_id'],'phase':'D2','normal_training_iteration':True,'completed_local_updates':60,'completed_phase_updates':336,'counters':worker['counters'],'cumulative_counters':worker['cumulative_counters'],'endpoint_checkpoint_sha256':candidates['336']['checkpoint_sha256'],'best_replacement':True,'selected_phase_update':300,'training_continuation_eligible':False,'stage_promotion_eligible':False,'competence_passed':False,'checkpoint_metadata_unchanged':True,'raw_exits':{'outer':0,'worker':0},'owned_processes_and_groups_absent':True,'registration_path':str(PREP/'registration.json'),'registration_sha256':sha(PREP/'registration.json'),'audit_path':str(OWN/'audit.json'),'audit_sha256':sha(OWN/'audit.json'),'full_audit_sha256':sha(AUDITOR/'full-audit.json'),'authority':'Completed iteration/resource-cost accounting. Separate selected300 receipt grants model continuation; endpoint336 is not retained.','wall_accounting':{'completed_campaign_resource_cost_before_seconds':7118.78208862512,'completed_campaign_resource_cost_after_seconds':cost,'observed_outer_seconds':outer,'selected_checkpoint_future_baseline_seconds':future,'completed_discarded_branch_end_highwater_seconds':4760.062404125177+outer,'semantics':'Later36 updates after selected300 add resource cost, not selected model/Adam/RNG/counter ancestry.'}}
write('completed-iteration-receipt.json',completed)
fp={k:runner.fingerprint(selected[field]) for k,field in [('model','model'),('optimizer','optimizer'),('rng','rng')]}
receipt={'schema':'d2_retained_best_candidate_parent_receipt_v1','status':'accepted_complete_candidate_from_completed_normal_training_iteration','at_utc':now,'run_id':reg['run_id'],'phase':'D2','checkpoint_path':str(checkpoint),'checkpoint_sha256':sha(checkpoint),'checkpoint_sidecar_sha256':sha(Path(str(checkpoint)+'.json')),'checkpoint_metadata_unchanged':True,'candidate_phase_update':300,'candidate_local_update':24,'candidate_counters':selected['counters'],'candidate_cumulative_counters':selected['cumulative_counters'],'counters':selected['counters'],'cumulative_counters':selected['cumulative_counters'],'inherited_counters':selected['inherited_counters'],'next_episode_indices':selected['next_episode_indices'],'learner_fingerprints':fp,'identity_sha256':selected['identity_sha256'],'config_sha256':selected['config_sha256'],'runtime_sha256':selected['runtime_sha256'],'native_sha256':selected['native_sha256'],'policy_sha256':selected['policy_sha256'],'parent_registration_sha256':reg['parent']['registration_sha256'],'candidate_parent_checkpoint_sha256':reg['parent']['sha256'],'parent_checkpoint_sha256':reg['parent']['sha256'],'previous_retained_checkpoint_sha256':reg['parent']['sha256'],'parent_terminal_receipt_path':reg['parent']['terminal_receipt_path'],'parent_terminal_receipt_sha256':reg['parent']['terminal_receipt_sha256'],'completed_iteration_local_updates':60,'completed_iteration_phase_update_end':336,'completed_iteration_receipt_path':str(OWN/'completed-iteration-receipt.json'),'completed_iteration_receipt_sha256':sha(OWN/'completed-iteration-receipt.json'),'registration_path':str(PREP/'registration.json'),'registration_sha256':sha(PREP/'registration.json'),'evaluation_path':str(certificate),'evaluation_sha256':sha(certificate),'evaluation_jsonl_path':str(RUN/'development-000300.jsonl'),'evaluation_jsonl_sha256':sha(RUN/'development-000300.jsonl'),'audit_path':str(OWN/'audit.json'),'audit_sha256':sha(OWN/'audit.json'),'performance':performance,'selection_rule':'Highest independently audited mean alive frames on same64 D2 development seeds; ties keep earlier candidate/incumbent.','effective_learning_rate':3e-5,'competence_passed':False,'stage_promotion_eligible':False,'training_continuation_eligible':True,'authority_scope':'Exact selected300 complete-update candidate may parent a NEW registered D2 continuation. Model/Adam/RNG and counters stop atlocal24; later36 discarded updates add resource cost only. No D3/student/B/E/qualification authority.','wall_accounting':{'definition':'Selected intermediate checkpoint point clock and whole completed campaign resource cost remain distinct.','future_checkpoint_trajectory_baseline_seconds':future,'selected_checkpoint_reported_cumulative_D2_wall_seconds':future,'selected_checkpoint_reported_current_iteration_wall_seconds':selected['current_iteration_observed_outer_seconds'],'selected_checkpoint_reported_trajectory_wall_seconds':future,'selected_checkpoint_reported_iteration_wall_seconds':selected['current_iteration_observed_outer_seconds'],'successful_ancestor_and_completed_campaign_cost_seconds':cost,'whole_completed_iteration_observed_outer_seconds':outer}}
write('retained-best-candidate-receipt.json',receipt)
write('retained-best-decision.json',{'selection':'retained_best_integrity_accepted_checkpoint','phase_update':300,'checkpoint_path':str(checkpoint),'checkpoint_sha256':sha(checkpoint),'receipt_path':str(OWN/'retained-best-candidate-receipt.json'),'receipt_sha256':sha(OWN/'retained-best-candidate-receipt.json'),'previous_mean':2483.65625,'new_mean':2704.390625,'endpoint336_not_selected':True,'future_branch_baseline_seconds':future,'completed_campaign_cost_seconds':cost})
# Final source/lease/cancel check occurs after all acceptance publications.
s=guard();write('state-before-lease-clear.json',s)
s['active_long_campaign']=None;s['last_update_at_utc']=now;s['postcritic_training_work'].update(active_campaign=None,status='accepted_LR3e-5_iteration;retained300_selected;endpoint336_discarded',latest_parent_terminal_receipt=str((OWN/'retained-best-candidate-receipt.json').relative_to(ROOT)),latest_parent_terminal_receipt_sha256=sha(OWN/'retained-best-candidate-receipt.json'),latest_completed_iteration_receipt=str((OWN/'completed-iteration-receipt.json').relative_to(ROOT)),latest_completed_iteration_receipt_sha256=sha(OWN/'completed-iteration-receipt.json'),completed_campaign_resource_cost_seconds=cost,cumulative_D2_inclusive_wall_seconds=future,latest_performance=performance,best_observed_current_lineage_reference={'phase_update':300,'run_id':reg['run_id'],'checkpoint_sha256':sha(checkpoint),'parent_terminal_receipt':str((OWN/'retained-best-candidate-receipt.json').relative_to(ROOT)),'parent_terminal_receipt_sha256':sha(OWN/'retained-best-candidate-receipt.json'),'Q1_bottom16_mean':performance['q1_bottom16_mean'],'Q4_top16_mean':performance['q4_top16_mean'],'mean_alive_frames':performance['mean_alive_frames']})
s['training_parent_selection_policy'].update(current_parent_phase_update=300,current_parent_sha256=sha(checkpoint),current_parent_receipt=str((OWN/'retained-best-candidate-receipt.json').relative_to(ROOT)),current_parent_receipt_sha256=sha(OWN/'retained-best-candidate-receipt.json'),parent_receipt_schema=receipt['schema'])
s['tasks']['retained276_lr3em5_r2_execution_luna_20261026_r2'].update(status='completed',workState='result_available',result_ingested=True,ingested_at_utc=now,actual_outcome='accepted_completed_iteration_selected300',parent_terminal_audit=str((OWN/'audit.json').relative_to(ROOT)),lease_cleared_at_utc=now)
s['parallel_acceleration_work'].update(status='LR3e-5R2accepted;retained300mean2704.390625;playbackrequested',canonical_report=str((OWN/'report.md').relative_to(ROOT)))
stage=statepath.with_name('state-lr3em5-r2-complete.tmp');stage.write_text(json.dumps(s,indent=2,sort_keys=True)+'\n');os.replace(stage,statepath);write('state-after-lease-clear.json',s)
text=['# LR3e-5 iteration accepted; retained best300','', 'All60 updates and all six candidates passed independent terminal audit. Selected300 improves the same64-seed development mean8.9%; endpoint336 is preserved and discarded. No competence or qualification claim.','', '| Candidate | Q1 alive frames | Q4 alive frames | Mean alive frames |','| --- | ---: | ---: | ---: |']
for k,c in candidates.items():
 p=c['performance']['alive_frames'];text.append(f"| {k} | {p['Q1']} | {p['Q4']} | {p['mean']} |")
text+=['',f"Observed monotonic outer duration: {outer}s. Completed resource cost: {cost}s. Selected300 future branch baseline: {future}s. Later36 updates are not selected learner ancestry.",'', 'Selected deaths:26 normal enemies,16 static rectangles,15 kamikazes,6 moving rectangles,1 explosion. All64 died; no caps.','', 'The child terminal summary reported score-tail statistics; the table above uses alive-frame tails.']
(OWN/'report.md').write_text('\n'.join(text)+'\n')
print(json.dumps({'status':audit['status'],'retained_phase':300,'checkpoint_sha256':sha(checkpoint),'performance':performance,'future_baseline':future,'resource_cost':cost,'matching_lease_cleared':True}))
