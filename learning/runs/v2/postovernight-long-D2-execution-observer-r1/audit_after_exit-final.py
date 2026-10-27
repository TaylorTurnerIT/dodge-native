#!/usr/bin/env python3
"""Postrun read-only evidence audit. Never imports ML or deserializes checkpoints."""
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
import traceback
ROOT=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
OUT=ROOT/'learning/runs/v2/postovernight-long-D2-execution-observer-r1'
PREP=ROOT/'learning/runs/v2/postovernight-long-D2-prepare-r4'
CAPSULE=PREP/'capsule-final'
CAMPAIGN=ROOT/'learning/runs/v2/postovernight-long-D2-campaign-r1'
STATE=ROOT/'learning/runs/v2-orchestration/state.json'

def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def save(name,value):
    with (OUT/name).open('x') as f:json.dump(value,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n')
def require(ok,message):
    if not ok:raise RuntimeError(message)
def lines(path):
    if not path.exists():return []
    with path.open() as f:return [json.loads(line) for line in f if line.strip()]

def main():
    audit_start=time.monotonic();audit_utc=utc();errors=[];checks={}
    process=read(OUT/'process-exit.json');raw=process.get('raw_wait_report');wall=process.get('actual_wall_seconds')
    require(process['stdout_stderr_closed'] is True,'Observer streams still open')
    registration=read(PREP/'registration.json');receipt_path=Path(registration['receipt'])
    receipt=read(receipt_path) if receipt_path.is_file() else {}
    def audit(name,callback):
        try:
            value=callback();checks[name]=dict(passed=True,evidence=value);return value
        except BaseException as e:
            checks[name]=dict(passed=False,error=repr(e),traceback=traceback.format_exc());errors.append(name+': '+repr(e));return None
    def raw_check():
        require(process['actual_command_launch_count']==1 and raw is not None,'Exactly one invocation/raw proof missing')
        require(raw['pid']==process['outer_pid'] and raw['reaped_by']==process['observer_pid'] and raw['direct_child_reaped'] is True,'Direct-child raw ownership differs')
        require(os.waitstatus_to_exitcode(raw['raw_wait_status'])==raw['returncode'],'Raw status/returncode mismatch')
        require(wall==raw['observed_monotonic']-process['popen_before_monotonic'],'Conservative wall binding mismatch')
        require(not process['errors'] and not process.get('deadline_missed'),'Observer recorded failure')
        return dict(raw=raw,actual_wall_seconds=wall,within_normal_cap=wall<=7200,within_latest_failure_cap=wall<=7210)
    audit('actual_direct_child_raw_and_wall',raw_check)
    sys.path.insert(0,str(CAPSULE/'learning/runs/v2/postovernight-long-D2-prepare-r4'))
    import long_d2 as c
    import long_d2_executor as executor
    import processes as owned
    require(not any(n in ('torch','numpy','dodge_rl') or n.startswith(('torch.','numpy.','dodge_rl.')) for n in sys.modules),'Postrun audit imported ML')
    def authority():
        context=c.capsule_context(CAPSULE);lease=read(PREP/'required-lease.json');state=read(STATE)
        c.assert_lease(STATE,lease)
        require(len(lease)==15 and state['scheduler_enabled'] is False and state['scheduler_next_run_at'] is None,'Strict lease/scheduler differs')
        before=read(OUT/'sourcehashes-before.json');mismatch={};mutable={}
        for path,digest in before['protected'].items():
            actual=sha(path)
            if actual!=digest:
                (mutable if path==str(STATE) else mismatch)[path]=dict(before=digest,after=actual)
        save('postflight-input-verification.json',dict(full_pin_count=len(context[4]),protected_count=len(before['protected']),immutable_mismatches=mismatch,mutable_state_changes=mutable,strict_lease_exact=True,identity_raw_sha256=sha(CAPSULE/c.PREPARE_REL/'long-identity.json'),identity_semantic_sha256=c.semantic_hash(context[3])))
        require(not mismatch,'Protected immutable input bytes changed')
        return context
    context=audit('frozen_inputs_and_strict_lease',authority)
    def absent():
        groups=dict(process['owned_identities'])
        mapping={'supervisor':'inner','worker':'worker'}
        for role,record in receipt.get('ownership',{}).items():
            key=mapping[role]
            if key not in groups:groups[key]=record
            else:require(groups[key]['pid']==record['pid'] and groups[key]['pgid']==record['pgid'] and groups[key]['argv']==record['argv'],'Receipt/observer owned identity differs')
        rows=owned.census(time.monotonic()+1);records={}
        for role,record in groups.items():
            pgid=record['pgid'];positive=owned.absent(pgid,time.monotonic()+1)
            members=[r for r in rows if r['pgid']==pgid]
            records[role]=dict(pid=record['pid'],pgid=pgid,positively_absent=positive,census_members=members)
            require(positive and not members,'Owned group remains: '+role)
        save('postflight-owned-absence.json',dict(groups=records,all_three_groups_observed=set(records)=={'outer','inner','worker'},observed_utc=utc(),direct_child_reaping_scope='outer only; inner and worker reaping belongs to their direct parents'))
        require('outer' in records,'Outer group proof missing')
        if raw and raw['returncode'] in (0,2):require(set(records)=={'outer','inner','worker'},'Normal acceptance requires all three group identities')
        return records
    absence=audit('owned_groups_positively_absent',absent)
    manifest={str(p.relative_to(CAMPAIGN)):sha(p) for p in sorted(CAMPAIGN.rglob('*')) if p.is_file()} if CAMPAIGN.exists() else {}
    save('campaign-observed-artifact-manifest.json',dict(files=manifest,stable_owned_groups_proven=absence is not None,observed_utc=utc(),source='Read-only postrun observation, separate from frozen campaign manifest'))
    wr=read(CAMPAIGN/'long-worker-result.json') if (CAMPAIGN/'long-worker-result.json').is_file() else {}
    run=read(CAMPAIGN/'long-run-result.json') if (CAMPAIGN/'long-run-result.json').is_file() else {}
    terminal=read(CAMPAIGN/'finalization-result.json') if (CAMPAIGN/'finalization-result.json').is_file() else {}
    index=read(CAMPAIGN/'checkpoint-index.json') if (CAMPAIGN/'checkpoint-index.json').is_file() else []
    def manifest_check():
        path=CAMPAIGN/'artifact-manifest.json';expected=read(path)
        actual={k:v for k,v in manifest.items() if k not in ('artifact-manifest.json','finalization-result.json')}
        require(expected==actual,'Frozen campaign manifest inventory or hash mismatch')
        require(terminal['artifact_manifest_sha256']==sha(path) and terminal['run_result_sha256']==sha(CAMPAIGN/'long-run-result.json'),'Terminal manifest/run binding mismatch')
        return dict(artifact_count=len(expected),manifest_sha256=sha(path),terminal_sha256=sha(CAMPAIGN/'finalization-result.json'))
    if (CAMPAIGN/'artifact-manifest.json').is_file():audit('campaign_manifest_terminal_bindings',manifest_check)
    else:checks['campaign_manifest_terminal_bindings']=dict(passed=False,error='Missing frozen campaign manifest; failed/partial outputs retained');errors.append('Missing frozen campaign manifest')
    minimum=False;bindings=None
    if raw is not None:
        minimum=executor.accept_observed(receipt,raw['returncode'],wall)
        if raw['returncode'] in (0,2) and context is not None:
            bindings=audit('full_normal_artifact_validator',lambda:executor.validate_artifacts(CAMPAIGN,raw['returncode'],context,lambda full:None))
    def receipt_check():
        require(minimum,'Frozen accept_observed rejected actual raw/wall/receipt')
        require(receipt['registration']==registration and receipt['required_lease']==context[5],'Outer registration/lease binding mismatch')
        require(receipt['bindings']==bindings,'Outer receipt artifact bindings differ')
        require(receipt['inner_wait']['returncode']==receipt['worker_wait']['returncode']==raw['returncode'],'Inner/worker raw status differs')
        t0=float.fromhex(receipt['t0_monotonic_hex'])
        require(process['popen_before_monotonic']<=t0<=raw['observed_monotonic'],'Shared T0 outside observed run')
        for role,key,cap in [('inner','inner_wait',7170),('worker','worker_wait',7140)]:
            report=receipt[key]
            require(report['direct_child_reaped'] is True and os.waitstatus_to_exitcode(report['raw_wait_status'])==report['returncode'] and report['observed_monotonic']-t0<cap,'Owned raw/deadline proof differs: '+role)
        resources=receipt['outer_resources']
        require(resources['latched_failure'] is None,'Outer resource/pin latch failure')
        for k in ('maximum_rss_bytes','maximum_self_peak_rss_bytes','maximum_mps_driver_bytes'):require(type(resources[k]) is int and 0<=resources[k]<=c.LIMIT,'Outer resource cap invalid')
        require(resources['maximum_sample_gap_seconds']<=.5 and resources['maximum_full_input_gap_seconds']<=5,'Outer resource/full-pin sample gap invalid')
        return dict(shared_T0=t0,outer_wall_from_T0=raw['observed_monotonic']-t0,inner_wall=receipt['inner_wait']['observed_monotonic']-t0,worker_wall=receipt['worker_wait']['observed_monotonic']-t0)
    audit('parent_acceptance_condition',receipt_check)
    entry=read(CAMPAIGN/'entry-control.json') if (CAMPAIGN/'entry-control.json').is_file() else None
    restoration=read(CAMPAIGN/'entry-restoration.json') if (CAMPAIGN/'entry-restoration.json').is_file() else None
    episodes=lines(CAMPAIGN/'training-episodes.jsonl');initial=next((r for r in episodes if r.get('kind')=='initial'),None)
    def env_check():
        require(initial is not None,'Initial environment metadata missing')
        metadata=initial['batch_info'];infos=initial['info']
        require(len(infos)==64 and metadata['initial_episode_indices']==[0]*64 and metadata['next_episode_indices']==[1]*64,'Fresh zero-index 64-environment contract differs')
        require(metadata['batch_size']==64 and metadata['action_repeat']==4 and metadata['difficulty']==2 and metadata['patterns_enabled'] is True and metadata['powerups_enabled'] is True and metadata['run_seed']==5562873868232098305,'Environment fixed fields differ')
        require(metadata['reward_version']=='score_plus_0.01_alive_minus_5_termination_v1' and metadata['render_pixels'] is False and metadata['auxiliary_targets'] is False,'Environment reward/render fields differ')
        require(all(r['seed']['episode']==0 and r['seed']['slot']==i and r['seed']['evaluation'] is False and r['alive_frames']==r['gameplay_frames']==r['score_raw_fixed']==0 for i,r in enumerate(infos)),'Initial environment state differs')
        return dict(kwargs=initial['kwargs'],batch_info=metadata,slots=64,all_episode_indices_zero=True)
    audit('actual_fresh_environment',env_check)
    schedule=lines(CAMPAIGN/'schedule.jsonl');metrics=lines(CAMPAIGN/'training-metrics.jsonl')
    def schedule_check():
        previous={'U':25.,'E':150.,'C':15.,'F':30.};evaluations=[]
        for row in schedule:
            reserves=row['reserves'];require(reserves['C']==15 and reserves['F']==30,'Fixed reserves changed')
            require(reserves['U']>=previous['U'] and reserves['E']>=previous['E'],'Reserve shrank');previous=reserves
            if row['event']=='cadence_evaluation':require(row['phase_updates']%16==0,'Off-cadence evaluation');evaluations.append(row['phase_updates'])
        for i,row in enumerate(metrics,1):
            require(row['counters']['phase_updates']==i and row['update_progress']['complete'] is True and row['update_progress']['in_update'] is False and row['metrics']['finite'] is True,'Complete update/finite accounting differs')
            require(entry is not None and row['monotonic']>=next(r['monotonic'] for r in schedule if r['event']=='cadence_evaluation'),'Gradient completed before entry control')
        return dict(complete_update_records=len(metrics),cadence_phase_updates=evaluations,final_reserves=previous)
    audit('schedule_and_complete_update_accounting',schedule_check)
    evaluation_table=[]
    def evaluate_json():
        certs=sorted(CAMPAIGN.glob('*.long-evaluation.json'))
        by={r['checkpoint']:r for r in index}
        for j,path in enumerate(certs):
            cert=read(path);ev=cert['evaluations']['D2'];rows=ev['rows'];name=path.name.removesuffix('.long-evaluation.json');record=by.get(name)
            require(len(rows)==ev['episodes']==64 and ev['complete'] is True and ev['gradients'] is False and ev['action_mode']=='deterministic_argmax','Evaluation contract differs')
            for i,row in enumerate(rows):require(set(row)==set(c.ROW_KEYS) and row['episode_index']==i and row['seed']==c.SEEDS[i],'Evaluation rows/seed order differs')
            score=sum(r['score'] for r in rows)/64;alive=sum(r['alive_frames'] for r in rows)/64;gate=score>=50 and alive>=3060
            require(score==ev['mean_score'] and alive==ev['mean_alive_frames'] and gate==cert['progression_gate_passed'],'Evaluation means/gate differs')
            require(cert['checkpoint_sha256']==sha(CAMPAIGN/name) and cert['teacher_qualified'] is False and cert['training_parent_eligible'] is False,'Certificate/checkpoint hash/eligibility mismatch')
            if j==0:
                control=c.read_json(ROOT/context[0]['entry_control'])['evaluations']['D2'] if context else None
                require(control is not None and rows==control['rows'] and score==1.4765625 and alive==295.25,'Actual entry rows differ from frozen historical control')
            evaluation_table.append(dict(checkpoint=name,phase_updates=record['counters']['phase_updates'] if record else (0 if j==0 else None),mean_score=score,mean_alive_frames=alive,episodes=64,caps=ev['caps'],deaths=ev['deaths'],gate_passed=gate,certificate_sha256=sha(path)))
        return evaluation_table
    audit('evaluation_rows_certificates_and_entry',evaluate_json)
    resources={}
    for role,record in [('outer',receipt.get('outer_resources')),('inner',terminal.get('supervisor_resources_final')),('worker',wr.get('worker_resources'))]:
        if record is not None:resources[role]=record
    worker_samples=lines(CAMPAIGN/'worker-resources.jsonl');inner_samples=lines(CAMPAIGN/'supervisor-guard.jsonl')
    sampled={role:dict(samples=len(rows),maximum_rss_bytes=max((r['rss_bytes'] for r in rows),default=None),maximum_self_peak_rss_bytes=max((r['self_peak_rss_bytes'] for r in rows),default=None),maximum_mps_driver_bytes=max((r['mps_driver_bytes'] for r in rows),default=None)) for role,rows in [('worker',worker_samples),('inner',inner_samples)]}
    failure_clock=None
    if receipt.get('first_failure_monotonic') is not None and raw is not None:
        failure_clock=dict(first_failure_monotonic=receipt['first_failure_monotonic'],cleanup_until_monotonic=receipt.get('cleanup_until_monotonic'),reap_after_first_failure_seconds=raw['observed_monotonic']-receipt['first_failure_monotonic'],within_shared_failure_deadline=raw['observed_monotonic']<=receipt.get('cleanup_until_monotonic',-1))
    accepted=bool(minimum and bindings is not None and not errors and raw and raw['returncode'] in (0,2) and wall<=7200)
    def retained_binding_check():
        require(context is not None,'Frozen context missing')
        p,config,base,identity,pins,lease=context
        require(wr['run_id']==p['run_id'] and wr['protocol_sha256']==c.PROTOCOL_SHA256 and wr['config_document_sha256']==c.CONFIG_SHA256 and wr['identity_document_sha256']==lease['identity_sha256'] and wr['checkpoint_identity_semantic_sha256']==c.semantic_hash(identity),'Failed worker frozen identity differs')
        require(c.read_json(CAMPAIGN/'long-config.json')==config and c.read_json(CAMPAIGN/'long-identity.json')==identity,'Campaign config/identity differs')
        require(restoration['matched'] is True and restoration['before_any_environment_or_gradient'] is True and set(restoration['bitwise_sha256'])=={'model','Adam','RNG'},'Actual restoration proof differs')
        require(entry['matched'] is True and entry['rows']==64 and entry['fields']==list(c.ROW_KEYS) and entry['control_document_sha256']==p['entry_control_sha256'] and all(entry[k] is True for k in ('RNG_unchanged','model_Adam_unchanged','zero_gradients_before_control')),'Entry control proof differs')
        lineage=c.read_json(CAMPAIGN/'parent-lineage.json')
        require(lineage['parent_checkpoint_sha256']==p['parent_checkpoint_sha256'] and lineage['parent_terminal_receipt']==p['parent_terminal_receipt'] and lineage['inherited_counters']==c.PARENT_COUNTERS and lineage['failed_D2_experience_inherited'] is False,'Retained D1 lineage differs')
        origins=c.read_json(CAMPAIGN/'actual-import-origins.json');require(origins,'Actual import origin evidence missing')
        for name,record in origins.items():
            policy=identity['legacy_module_origins'].get(record['origin'])
            require((name=='dodge_rl' or name.startswith('dodge_rl.')) and policy is not None and policy['sha256']==record['sha256'] and policy['mirror']==record['mirror'],'Actual import origin policy differs')
        require(len(index)==len(list(CAMPAIGN.glob('*.pt'))),'Checkpoint inventory differs')
        for record in index:
            require(sha(CAMPAIGN/record['checkpoint'])==record['sha256'] and record['training_parent_eligible'] is False,'Retained checkpoint index/hash/eligibility differs')
            if record['evaluated']:require(record['evaluation_sha256']==sha(CAMPAIGN/(record['checkpoint']+'.long-evaluation.json')),'Retained evaluation certificate SHA differs')
        failure=wr.get('failure_checkpoint')
        require(failure is not None and failure in index and failure['tag']=='failure' and failure['evaluated'] is False and failure['progression_gate_passed'] is False,'Failure checkpoint binding/tag differs')
        require(wr['expected_exit_code']==raw['returncode']==receipt['expected_exit_code']==1 and wr['experiment_status']==receipt['experiment_status']=='failed','Failed worker/raw/outer outcome differs')
        require(wr['teacher_qualified'] is False and wr['training_parent_eligible'] is False and wr['same_phase_resume'] is False and wr['automatic_retries']==0 and wr['B_E_student_D3_opened'] is False,'Failed worker scope/eligibility differs')
        counters=wr['counters'];last_complete=metrics[-1]['counters']
        require(counters['inherited']==c.PARENT_COUNTERS and counters['phase_updates']==len(metrics)==51 and counters['partial_optimizer_steps']==0,'Retained failure counters differ')
        require(counters['cumulative']['optimizer_steps']==counters['inherited']['optimizer_steps']+counters['phase']['optimizer_steps']==counters['actual_optimizer_steps_including_partial'],'Optimizer accounting differs')
        return dict(checkpoints=len(index),certificate_count=len(evaluation_table),source_identity_raw=wr['identity_document_sha256'],checkpoint_identity_semantic=wr['checkpoint_identity_semantic_sha256'],actual_import_origins=origins,last_complete_metric_counters=last_complete,partial_rollout_environment_decisions=counters['cumulative']['environment_decisions']-last_complete['cumulative']['environment_decisions'],partial_rollout_raw_frames=counters['cumulative']['raw_frames']-last_complete['cumulative']['raw_frames'],checkpoint_content_scope='Runtime-reported metadata and independently hashed bytes; no postrun deserialization')
    retained_bindings=audit('retained_failure_checkpoint_identity_origin_lineage_bindings',retained_binding_check)
    inner_failure=c.read_json(CAMPAIGN/'inner-failure.json') if (CAMPAIGN/'inner-failure.json').is_file() else {}
    failure_details=dict(primary_observed_guard_error=wr.get('final_verification_error'),worker_latched_failure=wr.get('worker_resources',{}).get('latched_failure'),worker_maximum_full_input_gap_seconds=wr.get('worker_resources',{}).get('maximum_full_input_gap_seconds'),worker_persisted_outcome=wr.get('outcome'),worker_persisted_error=wr.get('error'),worker_traceback=wr.get('traceback'),outer_error=receipt.get('error'),inner_failure=inner_failure,observer_requested_cancellation=process.get('cancellation_requests'),lease_cancel_requested=c.read_json(STATE)['active_long_campaign']['cancel_requested'],worker_wait_missing=receipt.get('worker_wait') is None,inner_and_worker_direct_reaping_claimed_by_observer=False,frozen_run_terminal_manifest_missing=not (CAMPAIGN/'artifact-manifest.json').exists(),resource_interpretation='Observed RSS and MPS maxima were below separate caps; full-input observation gap failed, so resource/identity monitoring gate did not pass')
    save('failure-evidence.json',failure_details)
    final=wr.get('final_checkpoint') or wr.get('failure_checkpoint');counters=wr.get('counters') or (metrics[-1]['counters'] if metrics else None)
    result=dict(schema='long_D2_execution_observer_result_v1',status='complete' if accepted else 'failed',outcome=wr.get('outcome') or receipt.get('error') or 'missing_terminal_evidence',actual_command_launch_count=process['actual_command_launch_count'],command=read(OUT/'command.json'),raw_wait_report=raw,actual_wall_seconds=wall,start_utc=process.get('popen_before_utc'),reap_utc=process.get('reap_observed_utc'),observer_own_exit_excluded_from_experiment_scope=True,parent_acceptance_condition=accepted,frozen_accept_observed_minimum=minimum,checks=checks,errors=errors,outer_receipt_sha256=sha(receipt_path) if receipt_path.is_file() else None,entry_restoration=restoration,entry_control=entry,evaluation_table=evaluation_table,latest_evaluation=evaluation_table[-1] if evaluation_table else None,phase_updates=None if counters is None else counters['phase_updates'],counters=counters,final_checkpoint=final,checkpoint_index=index,failure_checkpoint=wr.get('failure_checkpoint'),final_complete_update=None if final is None else final.get('complete_update'),final_evaluated=None if final is None else final.get('evaluated'),progress_gate_passed=bool(accepted and raw['returncode']==0),resources=resources,resource_samples=sampled,failure_cleanup_clock=failure_clock,failure_details=failure_details,retained_bindings=retained_bindings,owned_groups_absent=absence,all_failed_outputs_preserved=True,teacher_qualified=False,training_parent_eligible=False,ledger_written=False,scheduler_enabled=False,audit_started_utc=audit_utc,audit_finished_utc=utc(),postrun_readonly_audit_seconds=time.monotonic()-audit_start,additional_ML_model_inference_evaluation_training=False,limitations=['Postrun audit reads JSON and hashes checkpoint bytes; no independent checkpoint deserialization or model execution.','Restoration and no-gradient entry proof comes from frozen actual runtime receipts plus exact entry-row comparison.','Finite process/filesystem samples cannot prove absence of transient changes or post-scan signals.','Kernel scheduling and uninterruptibility remain measured-bound limitations; raw failure or late exit rejects.','R3 lost intermediate aggregate stdout remains historical and unrecoverable.','No qualification, training-parent eligibility, D3/B/E/student, retry or resume authority.'])
    save('execution-result.json',result)
    manifest={str(p.relative_to(OUT)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='artifact-manifest.json'}
    save('artifact-manifest.json',manifest)
    print(json.dumps(dict(status=result['status'],raw_exit=None if raw is None else raw['returncode'],actual_wall_seconds=wall,phase_updates=result['phase_updates'],latest_evaluation=result['latest_evaluation'],progress_gate_passed=result['progress_gate_passed'],errors=errors,postrun_readonly_audit_seconds=result['postrun_readonly_audit_seconds']),sort_keys=True))
if __name__=='__main__':main()
