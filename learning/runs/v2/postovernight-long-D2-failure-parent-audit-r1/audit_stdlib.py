"""Independent receipt audit. Does not import ML or deserialize checkpoints."""
import collections
import concurrent.futures
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
BASE = ROOT / 'learning/runs/v2'
OUT = BASE / 'postovernight-long-D2-failure-parent-audit-r1'
CAM = BASE / 'postovernight-long-D2-campaign-r1'
OBS = BASE / 'postovernight-long-D2-execution-observer-r1'
PREP = BASE / 'postovernight-long-D2-prepare-r4'
CAP = PREP / 'capsule-final'
started = time.monotonic()
inputs = {}
checks = {}

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def track(path):
    path = Path(path)
    key = str(path)
    if key not in inputs:
        inputs[key] = digest(path)
    return path

def pairs(items):
    d = {}
    for k,v in items:
        if k in d:
            raise ValueError('Duplicate JSON key: '+k)
        d[k] = v
    return d

def parse(data):
    return json.loads(data, object_pairs_hook=pairs, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))

def load(path):
    return parse(track(path).read_text())

def lines(path):
    return [parse(x) for x in track(path).read_text().splitlines() if x.strip()]

def check(name, condition, detail=None):
    checks[name] = {'passed': bool(condition)}
    if detail is not None:
        checks[name]['detail'] = detail

def sem(d):
    return hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def hash_many(paths):
    paths = sorted(set(map(str,paths)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        return dict(zip(paths,pool.map(digest, paths)))

def save(name, data):
    (OUT/name).write_text(json.dumps(data,indent=2,sort_keys=True,allow_nan=False)+'\n')

wr = load(CAM/'long-worker-result.json')
outer = load(BASE/'postovernight-long-D2-execution-r1/acceptance-receipt.json')
wait = load(OBS/'raw-wait.json')
start = load(OBS/'start.json')
exitrec = load(OBS/'process-exit.json')
reg = load(PREP/'registration.json')
proto = load(ROOT/'learning/runs/v2-orchestration/postovernight-long-D2-r1-protocol-r4.json')
identity = load(CAM/'long-identity.json')
config = load(CAM/'long-config.json')
capsule = load(CAP/'capsule-manifest.json')
before = load(OBS/'sourcehashes-before.json')
index = load(CAM/'checkpoint-index.json')
lineage = load(CAM/'parent-lineage.json')
restoration = load(CAM/'entry-restoration.json')
control = load(CAM/'entry-control.json')
historical = load(ROOT/proto['entry_control'])
track(ROOT/proto['parent_checkpoint'])
track(ROOT/'crates/dodge-rl-env/src/seed.rs')
track(ROOT/'docs/implementation-plan-v2.md')
track(ROOT/'docs/SPEC_PRIVILEGED_VIT_RL.md')

manifest_results = {}
for name in ('artifact-manifest.json','artifact-manifest-supplement-r1.json'):
    m = load(OBS/name)
    actual = hash_many(OBS/k for k in m)
    inputs.update(actual)
    bad = {k:{'expected':v,'actual':actual[str(OBS/k)]} for k,v in m.items() if actual[str(OBS/k)] != v}
    manifest_results[name] = {'files':len(m),'mismatches':bad}
    check('observer_manifest_'+name,not bad,bad)
observed = load(OBS/'campaign-observed-artifact-manifest.json')
actual = hash_many(CAM/k for k in observed['files'])
inputs.update(actual)
bad = {k:v for k,v in observed['files'].items() if actual[str(CAM/k)] != v}
check('campaign_manifest_hashes',not bad,bad)
check('campaign_exact_inventory',set(observed['files'])=={x.name for x in CAM.iterdir() if x.is_file()})
check('all_checkpoint_bytes_match_index',all(inputs[str(CAM/x['checkpoint'])]==x['sha256'] for x in index))
check('checkpoint_inventory',len(index)==8 and len(list(CAM.glob('*.pt')))==8)

pins = {str(CAP/k):v for k,v in capsule['files'].items()}
pins.update(identity['original_input_pins'])
pins.update({str(ROOT/k):v for k,v in identity['controller_sources'].items()})
pins[str(CAP/'capsule-manifest.json')] = reg['capsule_manifest_sha256']
pins[str(PREP/'long-identity.json')] = reg['identity_sha256']
check('full_pin_set_equals_prelaunch',pins==before['pins'] and len(pins)==9870)
pin_actual = hash_many(pins)
inputs.update(pin_actual)
pin_bad = {p:{'expected':d,'actual':pin_actual[p]} for p,d in pins.items() if pin_actual[p]!=d}
check('all_9870_frozen_pins_current',not pin_bad,pin_bad)
cap_entries = list(CAP.rglob('*'))+[CAP]
check('capsule_read_only_and_no_symlinks',all(not x.is_symlink() and not x.stat().st_mode&0o222 for x in cap_entries))
check('capsule_exact_inventory',{str(x.relative_to(CAP)) for x in cap_entries if x.is_file()}==set(capsule['files'])|{'capsule-manifest.json'})
check('identity_copies_and_semantic',digest(CAM/'long-identity.json')==reg['identity_sha256']==digest(PREP/'long-identity.json') and sem(identity)==wr['checkpoint_identity_semantic_sha256'])
check('protocol_and_config',digest(ROOT/'learning/runs/v2-orchestration/postovernight-long-D2-r1-protocol-r4.json')==reg['protocol_sha256']==wr['protocol_sha256'] and digest(CAM/'long-config.json')==reg['config_sha256']==wr['config_document_sha256'] and config==identity['config'])
check('legacy_75_source_and_origin_mirrors',len(identity['base_registered_identity']['sources'])==75 and all(digest(Path(k))==v['sha256']==digest(CAP/v['mirror']) for k,v in identity['legacy_module_origins'].items()))
check('parent_lineage',digest(ROOT/proto['parent_checkpoint'])==proto['parent_checkpoint_sha256']==lineage['parent_checkpoint_sha256'] and lineage['failed_D2_experience_inherited'] is False and lineage['abandoned_parent_episodes']==64)
check('runtime_restoration_receipt',restoration['matched'] is True and restoration['before_any_environment_or_gradient'] is True)
check('one_invocation_no_external_cancel',start['actual_command_launch_count']==1 and exitrec['actual_command_launch_count']==1 and not exitrec['retry'] and not exitrec['cancellation_requests'] and not track(OBS/'signals.jsonl').read_text() and not outer['forwarded_cancellation'])
check('outer_failure_raw_reap',wait['report']['returncode']==1 and wait['report']['raw_wait_status']==256 and wait['report']['direct_child_reaped'] and outer['accepted'] is False and outer['experiment_status']=='failed')
check('bounded_failure_cleanup',wait['report']['observed_monotonic']<=outer['cleanup_until_monotonic'] and outer['cleanup_until_monotonic']==outer['first_failure_monotonic']+10 and outer['cleanup_complete'])
check('inner_direct_reap',outer['inner_wait']['direct_child_reaped'] and outer['inner_wait']['returncode']==1 and outer['inner_wait']['raw_wait_status']==256)
check('worker_direct_reap_receipt_absent',outer['worker_wait'] is None)
check('primary_latched_guard_failure',wr['final_verification_error']=="Stop('Full input verification gap exceeded 5s')" and wr['worker_resources']['maximum_full_input_gap_seconds']>5 and 'Guard' not in wr['traceback'] and 'in monitor' in wr['traceback'])
check('cleanup_SIGTERM_explains_cancelled',wr['outcome']=='cancelled' and wr['cancellation_signal']=='SIGTERM' and wr['cancellation_requests']==1 and all(x['term_sent'] for x in outer['ownership'].values()) and not load(CAM/'inner-failure.json')['required_lease']['cancel_requested'])

metrics = lines(CAM/'training-metrics.jsonl')
episodes = lines(CAM/'training-episodes.jsonl')
schedule = lines(CAM/'schedule.jsonl')
resources = lines(CAM/'worker-resources.jsonl')
kinds = collections.Counter(x['kind'] for x in episodes)
events = collections.Counter(x['event'] for x in schedule)
check('51_complete_updates_128_Adam_steps_each',len(metrics)==51 and [x['counters']['phase_updates'] for x in metrics]==list(range(1,52)) and all(x['metrics']['optimizer_steps']==128 and x['update_progress']['complete'] and x['metrics']['finite'] for x in metrics))
check('all_numeric_metrics_finite',all(math.isfinite(v) for r in metrics for v in r['metrics'].values() if type(v) in (int,float)))
final = wr['counters']; complete = metrics[-1]['counters']
check('final_counter_addition',all(final['cumulative'][k]==final['inherited'][k]+final['phase'][k] for k in ['environment_decisions','optimizer_steps','raw_frames','updates']))
check('complete_and_partial_counters',complete['phase']['environment_decisions']==51*16384 and complete['phase']['optimizer_steps']==51*128 and final['phase']['updates']==51 and final['partial_optimizer_steps']==0 and final['actual_optimizer_steps_including_partial']==12672)
accepted = [x for x in episodes if x['kind']=='collection_accepted']
check('complete_rollout_accounting',len(accepted)==51 and sum(x['transitions'] for x in accepted)==complete['phase']['environment_decisions'] and sum(x['returned_raw_frames'] for x in accepted)==complete['phase']['raw_frames'])

MASK=(1<<64)-1
def mix(z):
    z=((z^(z>>30))*0xBF58476D1CE4E5B9)&MASK
    z=((z^(z>>27))*0x94D049BB133111EB)&MASK
    return z^(z>>31)
initial=next(x for x in episodes if x['kind']=='initial')
run_seed=initial['batch_info']['run_seed']; exclusions=config['excluded_seed_ranges']
def seed_ok(s):
    base=mix(run_seed^0x444F4447455F5632)^mix((s['slot']+0x9E3779B97F4A7C15)&MASK)^mix((s['episode']+0xD1B54A32D192ED03)&MASK)
    counter=0
    while True:
        actual=mix(base^mix((counter+0x94D049BB133111EB)&MASK))>>32
        if not any(a<=actual<=b for a,b in exclusions):break
        counter+=1
    return s['counter']==counter and s['actual_seed']==actual and s['evaluation'] is False

seed_checks=[]; progression=[]; rewards=[]; active={}; completed=[]; boundaries=[]; pending=set(); reset_count=0
for r in episodes:
    kind=r['kind']
    if kind=='initial':
        for info in r['info']:
            s=info['seed'];active[s['slot']]=s;seed_checks.append(seed_ok(s));progression.append(s['episode']==0)
    elif kind=='native_completed_episode':
        info=r['info'];s=info['seed'];slot=s['slot'];seed_checks.append(seed_ok(s));progression.append(active[slot]==s and slot not in pending);pending.add(slot);completed.append(info)
        expected=info['score_delta_sum_raw_fixed']/65536+.01*info['alive_frames']-5*int(info['terminated'])
        rewards.append(math.isclose(info['objective_return'],expected,rel_tol=0,abs_tol=1e-9) and info['score']==info['score_raw_fixed']/65536 and info['gameplay_frames']==info['alive_frames']+int(info['terminated']))
    elif kind=='native_reset':
        progression.append(len(r['indices'])==len(r['info']))
        for slot,info in zip(r['indices'],r['info']):
            s=info['seed'];seed_checks.append(seed_ok(s));progression.append(s['slot']==slot and s['episode']==active[slot]['episode']+1 and slot in pending);pending.discard(slot);active[slot]=s;reset_count+=1
    elif kind=='checkpoint_resume_boundary':
        boundaries.append(r)
        progression.append(r['live_environment_reset'] is False and len(r['abandoned_on_resume'])==64)
        for row in r['abandoned_on_resume']:
            s=row['seed'];seed_checks.append(seed_ok(s));progression.append(active[s['slot']]==s and r['next_episode_indices'][s['slot']]==s['episode']+1)
check('exact_fresh_u32_seed_derivation',all(seed_checks),{'metadata_records':len(seed_checks),'run_seed':run_seed,'exclusions':exclusions})
check('per_slot_episode_reset_progression',all(progression) and not pending,{'reset_infos':reset_count,'completed_episodes':len(completed),'pending':sorted(pending)})
check('completed_reward_and_frame_accounting',all(rewards),{'completed_episodes':len(completed)})
active_frames=sum(x['gameplay_frames'] for x in boundaries[-1]['abandoned_on_resume'])
check('full_training_raw_frame_conservation',sum(x['gameplay_frames'] for x in completed)+active_frames==final['phase']['raw_frames'])

table=[]
keys=['episode_index','seed','score_raw_fixed','score','alive_frames','gameplay_frames','terminated','truncated','objective_return']
for item in index:
    if not item['evaluated']:continue
    cert=load(CAM/(item['checkpoint']+'.long-evaluation.json'))
    e=cert['evaluations']['D2']; rows=e['rows']; raw=lines(CAM/(item['checkpoint']+'.D2-development.jsonl'))
    score=sum(x['score_raw_fixed'] for x in rows)/65536/64;alive=sum(x['alive_frames'] for x in rows)/64
    check('evaluation_'+item['checkpoint'],len(rows)==64 and len(raw)==64 and sorted(rows,key=lambda x:x['episode_index'])==sorted(raw,key=lambda x:x['episode_index']) and score==e['mean_score'] and alive==e['mean_alive_frames'] and cert['checkpoint_sha256']==item['sha256'] and sorted((x['episode_index'],x['seed']) for x in rows)==[(i,3489660928+i) for i in range(64)] and all(math.isclose(x['objective_return'],x['score']+.01*x['alive_frames']-5*int(x['terminated']),abs_tol=1e-9) for x in rows))
    passed=score>=proto['evaluation']['mean_score_gate'] and alive>=proto['evaluation']['mean_alive_frames_gate']
    check('evaluation_gate_'+item['checkpoint'],cert['progression_gate_passed']==passed and not cert['teacher_qualified'] and not cert['training_parent_eligible'])
    if item['counters']['phase_updates']==0:
        historical_rows=historical['evaluations']['D2']['rows']
        project=lambda rs:sorted([{k:x[k] for k in keys} for x in rs],key=lambda x:(x['episode_index'],x['seed']))
        check('entry_nine_field_control_reproduction',project(rows)==project(historical_rows) and control['matched'] and control['zero_gradients_before_control'])
    table.append({'checkpoint':item['checkpoint'],'phase_updates':item['counters']['phase_updates'],'mean_score':score,'mean_alive_frames':alive,'deaths':sum(x['terminated'] for x in rows),'caps':sum(x['truncated'] for x in rows),'gate_passed':passed})

check('evaluation_cadence_0_16_32_48',[x['phase_updates'] for x in table]==[0,16,32,48] and [x['phase_updates'] for x in schedule if x['event']=='cadence_evaluation']==[0,16,32,48])
check('admitted_and_complete_schedule',[x['phase_updates'] for x in schedule if x['event']=='update_admitted']==list(range(52)) and [x['phase_updates'] for x in schedule if x['event']=='update_complete']==list(range(1,52)))
schedule_ok=[]; last_u=last_e=0
for row in schedule:
    r=row['reserves'];schedule_ok.append(r['U']>=last_u and r['E']>=last_e);last_u=r['U'];last_e=r['E']
    if row['event'] in ('block_admitted','update_admitted'):
        done=0 if row['event']=='block_admitted' else row['phase_updates']%16
        cost=(16-done)*r['U']+r['E']+(2 if done<8 else 1)*r['C']+r['F']
        schedule_ok.append(math.isclose(cost,row['required_seconds']) and row['remaining_worker_seconds']>=cost)
check('schedule_admission_formula_and_nondecreasing_reserves',all(schedule_ok))
maxima={k:max(x[k] for x in resources) for k in ['rss_bytes','self_peak_rss_bytes','mps_driver_bytes','sample_gap_seconds']}
check('resource_stream_maxima_receipt',maxima['rss_bytes']==wr['worker_resources']['maximum_rss_bytes'] and maxima['self_peak_rss_bytes']==wr['worker_resources']['maximum_self_peak_rss_bytes'] and maxima['mps_driver_bytes']==wr['worker_resources']['maximum_mps_driver_bytes'] and maxima['sample_gap_seconds']==wr['worker_resources']['maximum_sample_gap_seconds'])
check('observed_memory_caps',maxima['self_peak_rss_bytes']<=proto['rss_limit_bytes'] and maxima['mps_driver_bytes']<=proto['mps_driver_limit_bytes'])
check('resource_sample_order',all(b['monotonic']>a['monotonic'] for a,b in zip(resources,resources[1:])))
observations=lines(OBS/'process-observations.jsonl');observer_max={}
for row in observations:
    for p in row.get('owned',[]):
        role=p['role'];observer_max[role]=max(observer_max.get(role,0),p['rss_bytes'])
census=subprocess.run(['ps','-axo','pid=,ppid=,pgid=,stat=,command='],check=True,capture_output=True,text=True).stdout
absence={}
for role,pgid in [('outer',30643),('inner',30650),('worker',30714)]:
    try:os.killpg(pgid,0);absent=False;error=None
    except ProcessLookupError:absent=True;error='ESRCH'
    except PermissionError:absent=False;error='EPERM'
    members=[line for line in census.splitlines() if len(line.split(None,4))>=3 and line.split(None,4)[2]==str(pgid)]
    absence[role]={'pgid':pgid,'positive_absence':absent,'probe':error,'census_members':members}
check('current_positive_owned_group_absence',all(x['positive_absence'] and not x['census_members'] for x in absence.values()))
missing=[x for x in ['artifact-manifest.json','finalization-result.json','long-run-result.json'] if not (CAM/x).exists()]
check('failed_outputs_ineligible',not wr['teacher_qualified'] and not wr['training_parent_eligible'] and not wr['progression_gate_passed'] and not wr['B_E_student_D3_opened'] and not wr['D3_parent_candidate_pending_separate_parent_audit'] and index[-1]['tag']=='failure' and not index[-1]['evaluated'] and not index[-1]['training_parent_eligible'])

after=hash_many(inputs)
immutable_bad={p:{'before':v,'after':after[p]} for p,v in inputs.items() if after[p]!=v}
check('audit_inputs_unchanged_before_after',not immutable_bad,immutable_bad)
save('input-sha256-manifest.json',{'schema':'independent_audit_input_sha256_v1','files':inputs,'end_files':after,'mismatches':immutable_bad})
limitations=[
    'The first independent audit script stopped while reading an observer row without an owned field. Its exact script and stderr were retained. A corrected receipt-only audit used an empty owned list for that row; training was not retried.',
    'The run failed; this audit accepts only the internal consistency of preserved failure evidence. It does not accept a successful experiment, teacher qualification, or continuation authority.',
    'No ML or native modules were imported. Checkpoint bytes were hashed only; checkpoint contents, Adam/RNG/model restoration fingerprints, and update metadata were not independently deserialized.',
    'Positive process-group absence is not proof that the worker was directly reaped. The worker direct-child wait receipt is missing; the outer and inner direct-child reap receipts are present.',
    'No final campaign-owned manifest, finalization result, or long-run-result was produced. The observer inventory preserves 31 stable files after positive group absence.',
    'The four evaluations are deterministic development-seed evidence only. No B qualification, E replication, D3 evaluation, student work, or postrun inference was performed.',
    'The entry control and restoration receipts plus counters support entry-before-gradient ordering. schedule.jsonl has no timestamps; no independent per-event timing claim is made.',
    'Worker RSS sample maximum, worker self-reported peak RSS, and MPS driver maximum are separate quantities. Inner/outer on-disk resource receipts are absent; observer sampled maxima are bounded observations only.',
    'Finite filesystem sampling does not exclude transient mutation between reads or any later mutation. The current audit verifies all 9870 frozen pins, not every mutable parent ledger/state file.',
    'Earlier observer collector KeyError(monotonic) remains retained. Its read-only supplement repairs schedule interpretation without reexecuting training.',
]
result={'schema':'independent_failed_long_D2_audit_v1','started_utc':'2026-10-24T19:59:05Z','finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'audit_script_seconds':time.monotonic()-started,'failure_evidence_consistent':all(x['passed'] for x in checks.values()),'experiment_status':'failed','accepted_successful_training':False,'teacher_qualified':False,'training_parent_eligible':False,'retry_performed':False,'ML_native_imports_checkpoint_deserialization_inference_evaluation_training':False,'primary_failure':wr['final_verification_error'],'persisted_worker_outcome':wr['outcome'],'maximum_full_input_gap_seconds':wr['worker_resources']['maximum_full_input_gap_seconds'],'actual_wall_seconds':wait['actual_wall_seconds'],'raw_wait':wait['report'],'inner_wait':outer['inner_wait'],'worker_wait':outer['worker_wait'],'checks':checks,'manifest_checks':manifest_results,'frozen_pin_count':len(pins),'capsule_files':len(capsule['files']),'campaign_files':len(observed['files']),'checkpoint_index_metadata':index,'counters':final,'last_complete_update_counters':complete,'partial_rollout':{'environment_decisions':final['phase']['environment_decisions']-complete['phase']['environment_decisions'],'raw_frames':final['phase']['raw_frames']-complete['phase']['raw_frames'],'partial_Adam_steps':final['partial_optimizer_steps']},'stream_counts':{'training_metrics':len(metrics),'episode_rows':len(episodes),'episode_kinds':dict(kinds),'schedule':len(schedule),'schedule_events':dict(events),'worker_resources':len(resources)},'evaluation_table':table,'entry_restoration_runtime_receipt':restoration,'entry_control_runtime_receipt':control,'worker_resource_maxima':maxima,'observer_sampled_RSS_maxima':observer_max,'current_owned_absence':absence,'missing_final_artifacts':missing,'limitations':limitations}
save('audit.json',result)
rows='\n'.join('| '+str(x['phase_updates'])+' | '+str(x['mean_score'])+' | '+str(x['mean_alive_frames'])+' | '+str(x['deaths'])+' | '+str(x['caps'])+' | false |' for x in table)
failed=[k for k,v in checks.items() if not v['passed']]
markdown=f'''# Independent failed long-D2 audit\n\nThe one-shot run failed after {wait['actual_wall_seconds']} seconds, with outer return code 1 and raw wait status 256. The primary recorded guard failure was `{wr['final_verification_error']}`. Its maximum full-input verification gap was {wr['worker_resources']['maximum_full_input_gap_seconds']} seconds against the unchanged 5-second bound. The worker's persisted `cancelled` outcome followed supervisor SIGTERM cleanup; the observer recorded no external cancellation, and the lease cancellation flag remained false.\n\nThe failure evidence is internally consistent: **{all(x['passed'] for x in checks.values())}**. Failed audit checks: {failed}. This is not a successful training verdict or continuation authority.\n\n## Preserved training and evaluation evidence\n\nThere were 51 complete new PPO updates and 6528 new Adam steps, following 48 inherited updates and 6144 inherited Adam steps. The final counters report 99 total updates and 12672 total Adam steps. Complete new updates consumed 835584 decisions and 3335599 raw frames. The interrupted rollout added 13312 decisions and 53153 raw frames without an Adam step. Final new totals were 848896 decisions and 3388752 raw frames.\n\n| New updates | Mean score | Mean alive frames | Deaths | Caps | Gate passed |\n| --- | --- | --- | --- | --- | --- |\n{rows}\n\nAll four evaluations used the same 64 D2 development seeds and deterministic argmax actions. The fixed progression gate requires mean score 50 and mean alive frames 3060. No evaluation passed. Latest evaluated checkpoint was index 16 at phase update 48. Final checkpoint index 17 is a failure checkpoint at phase update 51, unevaluated and ineligible. Its `complete_update:true` metadata describes learner update state; the environment had consumed an additional partial rollout.\n\n## Independent verification\n\nThe audit recomputed all development means and nine-field entry-control equality from JSON rows; all completed-episode rewards; fresh u32 training-seed tuple hashes, exclusions, and per-slot reset progression; full training raw-frame conservation; complete rollout and Adam-step accounting; checkpoint-byte hashes; evaluation cadence; schedule reserve formulas; resource maxima; observer manifests; campaign inventory; and all 9870 frozen pins. It checked exact read-only capsule inventory, source/mirror identity, and input hashes before and after this audit. No candidate code was imported.\n\nThe three owned process groups are currently positively absent. Outer and inner direct-child reap receipts exist. The worker wait receipt is null; group absence does not repair that evidence gap. Cleanup completed within the original ten-second failure window.\n\n## Resources and limits\n\nWorker sampled RSS maximum was {maxima['rss_bytes']} bytes. Worker self-reported peak RSS was {maxima['self_peak_rss_bytes']} bytes. MPS driver allocation maximum was {maxima['mps_driver_bytes']} bytes. The largest resource sample gap was {maxima['sample_gap_seconds']} seconds. These observed memory values were below their separate registered caps. The input-observation gap gate failed.\n\n'''+ '\n'.join('- '+x for x in limitations)+'\n'
(OUT/'audit.md').write_text(markdown)
own={str(p.relative_to(OUT)):digest(p) for p in OUT.rglob('*') if p.is_file() and p.name!='artifact-manifest.json'}
save('artifact-manifest.json',{'schema':'independent_audit_artifact_manifest_v1','manifest_excludes_itself':True,'files':own})
print(json.dumps({'failure_evidence_consistent':result['failure_evidence_consistent'],'failed_checks':failed,'audit_sha256':digest(OUT/'audit.json'),'artifact_manifest_sha256':digest(OUT/'artifact-manifest.json'),'elapsed_seconds':time.monotonic()-started},sort_keys=True))
