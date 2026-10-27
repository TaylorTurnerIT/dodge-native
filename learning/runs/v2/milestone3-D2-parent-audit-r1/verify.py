from __future__ import annotations
import collections, datetime, hashlib, json, math, pathlib, subprocess, time
import numpy as np
import torch
from dodge_rl import checkpoints as ckpt

ROOT = pathlib.Path.cwd()
OUT = ROOT / 'learning/runs/v2/milestone3-D2-parent-audit-r1'
RUN = ROOT / 'learning/runs/v2/milestone3-D2-curriculum-r1'
EXE = ROOT / 'learning/runs/v2/milestone3-D2-execution-r1'
START = datetime.datetime.now(datetime.timezone.utc)
AT = time.monotonic()
inputs = {}

def raw(path):
    path = pathlib.Path(path)
    value = path.read_bytes()
    digest = hashlib.sha256(value).hexdigest()
    name = str(path.relative_to(ROOT))
    if name in inputs:
        assert inputs[name] == digest, ('input changed', name)
    inputs[name] = digest
    return value

def digest(path): return hashlib.sha256(raw(path)).hexdigest()
def data(path): return json.loads(raw(path))
def rows(path): return [json.loads(line) for line in raw(path).splitlines()]

def finite(value):
    if isinstance(value, torch.Tensor):
        return not value.is_floating_point() or bool(torch.isfinite(value).all())
    if isinstance(value, dict): return all(finite(x) for x in value.values())
    if isinstance(value, (tuple, list)): return all(finite(x) for x in value)
    return not isinstance(value, float) or math.isfinite(value)

def equal(a, b):
    if isinstance(a, torch.Tensor):
        return isinstance(b, torch.Tensor) and a.dtype == b.dtype and a.shape == b.shape and torch.equal(a, b)
    if isinstance(a, np.ndarray):
        return isinstance(b, np.ndarray) and a.dtype == b.dtype and np.array_equal(a, b)
    if isinstance(a, dict):
        return isinstance(b, dict) and set(a) == set(b) and all(equal(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return type(a) is type(b) and len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


plan_path = ROOT / 'learning/runs/v2-orchestration/milestone3_D2_curriculum_r1-plan.json'
assert digest(plan_path) == '05a5d54b275ebab0be4719faf40357a4aa5cc09719386adc179257d725c002de'
plan = data(plan_path); counts = {}
for directory,label in [(EXE,'execution'),(RUN,'runner')]:
    manifest=data(directory/'artifact-sha256.json')
    for name,want in manifest.items(): assert digest(directory/name)==want,(label,name)
    inventory={str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file()}
    assert inventory==set(manifest)|{'artifact-sha256.json'},(label,'inventory')
    counts[label]=len(manifest)
assert counts['runner']==41
identity=data(ROOT/plan['identity']); config=data(ROOT/plan['config'])
assert digest(ROOT/plan['identity'])==plan['identity_sha256']=='56dcf1ba848c2e2acdca967ce8ed5bca9457551659421a9070c2f7c5ba2bc14f'
assert digest(ROOT/plan['config'])==plan['config_sha256']=='2d8eb5626d0debdf5416d0b89610d78ddd56011c3238a82fec72efabe1bd7fe3'
assert hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()==identity['config_sha256']==plan['semantic_config_sha256']
assert len(identity['sources'])==75
for name,want in identity['sources'].items(): assert digest(ROOT/name)==want,name
assert config['phase']=='D2' and config['device']=='mps' and config['phase_settings']['run_seed']==5562881586070242562
assert config['phase_settings']['difficulty']==2 and config['phase_settings']['patterns_enabled'] is True and config['phase_settings']['budget_seconds']==1800
assert data(RUN/'identity.json')==identity and data(RUN/'registered-config.json')==config
command=data(EXE/'command-terminal.json'); start=data(EXE/'command-start.json')
assert command['argv']==start['argv']==plan['argv'] and command['cwd']==plan['cwd'] and command['environment_overrides']==plan['environment']
assert command['supervisor_exit_code']==1 and type(command['supervisor_exit_code']) is int and not command['timed_out']
assert command['seconds_to_cutoff_at_launch']>=2400 and datetime.datetime.fromisoformat(command['started_at_utc'])<datetime.datetime(2026,10,24,12,20,tzinfo=datetime.timezone.utc)
assert command['duration_seconds']<1830 and digest(EXE/'execute_once.py')==command['wrapper_source_sha256']
assert data(EXE/'wrapper-tool-exit.json')['exit_code']==1
post_tool=data(EXE/'postflight-tool-exit.json'); assert post_tool['exit_code']==0 and post_tool['wrapper_observed_exit_code']==1 and digest(EXE/'retain_postflight.py')==post_tool['script_sha256']
wrapper_events=rows(EXE/'wrapper-events.jsonl'); assert sum(x['kind']=='command_launched_once' for x in wrapper_events)==1
rr=data(RUN/'run-result.json'); wr=data(RUN/'worker-result.json'); er=data(EXE/'result.json'); pf=data(EXE/'postflight-receipt.json')
assert rr['status']==wr['status']=='failed' and rr['worker_exit_code']==1 and er['supervisor_exit_code']==1 and er['wrapper_observed_exit_code']==1
assert rr['error']==wr['error']=="GuardStop('Experiment wall guard expired')"
assert abs(rr['consumed_phase_wall_seconds']-1800.439149916987)<1e-9
assert rr['automatic_retries']==0 and rr['limits_relaxed'] is False and rr['B_opened'] is False and er['command_launch_count']==1 and er['B_E_opened'] is False
assert len(pf['checks'])==146 and all(x is True for x in pf['checks'].values())
assert pf['receipt_failures']==[] and pf['signal_events']==[] and pf['remaining_owned_processes']==[] and not pf['outer_timed_out']
assert er['evidence_verification_failures']==[] and er['receipt_only_verification_failures']==[]
expected=[(0,1.4765625,295.25),(16,4.71875,756.65625),(32,6.078125,869.984375),(48,5.7265625,855.890625),(64,5.8359375,877.96875),(80,6.4453125,939.609375),(96,8.9140625,1148.78125)]
evaluations=[]
for proof_path,want in zip(sorted(RUN.glob('*.evaluation.json')),expected,strict=True):
    proof=data(proof_path); checkpoint=pathlib.Path(str(proof_path)[:-len('.evaluation.json')]); stream=sorted(rows(RUN/(checkpoint.stem+'-D2-development.jsonl')),key=lambda x:x['episode_index']); value=proof['evaluations']['D2']
    assert stream==value['rows'] and len(stream)==64 and [x['seed'] for x in stream]==list(range(3489660928,3489660992))
    assert [x['episode_index'] for x in stream]==list(range(64)) and value['action_mode']=='deterministic_argmax' and value['complete'] and value['gradients'] is False
    assert proof['phase']=='D2' and proof['complete'] and proof['checkpoint_sha256']==digest(checkpoint)
    for x in stream:
        assert x['score']==x['score_raw_fixed']/65536 and x['terminated']!=x['truncated'] and 0<x['gameplay_frames']<=18000
        assert x['alive_frames']==x['gameplay_frames']-int(x['terminated'])
        assert abs(x['objective_return']-(x['score']+x['alive_frames']/100-5*int(x['terminated'])))<=1e-9
    score=sum(x['score_raw_fixed'] for x in stream)/(64*65536); alive=sum(x['alive_frames'] for x in stream)/64
    assert (score,alive)==want[1:] and score==value['mean_score'] and alive==value['mean_alive_frames']
    assert proof['passed']==(score>=50 and alive>=3060)==False and sum(x['terminated'] for x in stream)==64 and sum(x['truncated'] for x in stream)==0
    evaluations.append({'phase_updates':want[0],'checkpoint':checkpoint.name,'checkpoint_sha256':digest(checkpoint),'mean_score':score,'mean_alive_frames':alive,'deaths':64,'caps':0,'passed':False})
assert evaluations[-1]['checkpoint_sha256']=='2d598e1973ded1748ec18d59ed11abe524b2f2a9d68c8796d105266a31d4e8b6'
assert not (RUN/(wr['checkpoint']+'.evaluation.json')).exists() and wr['checkpoint_tag']=='interrupted_mid_update'
metrics=rows(RUN/'training-metrics.jsonl'); assert len(metrics)==104 and finite(metrics)
assert [x['counters']['phase_updates'] for x in metrics]==list(range(1,105))
assert all(x['metrics']['finite'] and x['metrics']['actor_grad_norm']>0 and x['metrics']['critic_grad_norm']>0 for x in metrics)
assert all(x['metrics']['entropy']>=.3 and x['metrics']['approx_kl']<.1 and x['metrics']['transitions']==16384 for x in metrics)
new_steps=sum(x['metrics']['optimizer_steps'] for x in metrics);assert new_steps==13248
training=rows(RUN/'training-episodes.jsonl');completed=[x['info'] for x in training if x['kind']=='native_completed_episode'];accepts=[x for x in training if x['kind']=='collection_accepted'];errors=[]
for info in completed:
    assert info['score_raw_fixed']==info['score_delta_sum_raw_fixed'] and info['score']==info['score_raw_fixed']/65536
    assert info['alive_frames']==info['gameplay_frames']-int(info['terminated'])
    error=abs(info['objective_return']-(info['score_delta_sum_raw_fixed']/65536+info['alive_frames']/100-5*int(info['terminated'])));errors.append(error);assert error<=1e-9
assert len({(x['seed']['slot'],x['seed']['episode']) for x in completed})==len(completed)
assert len(accepts)==105 and sum(x['completed_episodes'] for x in accepts)==len(completed)
initial=[x for x in training if x['kind']=='initial'];assert len(initial)==1 and initial[0]['batch_info']['run_seed']==5562881586070242562 and initial[0]['batch_info']['initial_episode_indices']==[0]*64
ranges=[(2952790016,2952791015),(3489660928,3489661055),(3758096384,3758097383)]
assert initial[0]['batch_info']['effective_excluded_seed_ranges']==[list(x) for x in ranges]
infos=list(initial[0]['info'])
for x in training:
    if x['kind']=='native_reset':infos.extend(x['info'])
seen=set();last={}
for x in infos:
    q=x['seed'];slot=q['slot'];episode=q['episode'];actual=q['actual_seed'];assert type(actual)is int and 0<=actual<2**32 and not any(a<=actual<=b for a,b in ranges)
    assert q['evaluation'] is False and (slot,episode)not in seen and episode==last.get(slot,-1)+1;seen.add((slot,episode));last[slot]=episode
resources={}
for name in ['supervisor-resources.jsonl','worker-resources.jsonl']:
    v=rows(RUN/name);assert v and finite(v);resources[name]={'samples':len(v),'maximum_rss_bytes':max(x.get('rss_bytes',0) for x in v),'maximum_self_peak_rss_bytes':max(x.get('self_peak_rss_bytes',0) for x in v),'maximum_mps_driver_bytes':max(x.get('mps_driver_bytes',0) for x in v),'maximum_worker_rss_bytes':max(x.get('worker_rss_bytes',0) for x in v)}
    assert all(v<=6442450944 for k,v in resources[name].items() if k!='samples')
assert resources==data(EXE/'resource-summary.json')==er['actual_resource_series_maxima']
assert max(resources['worker-resources.jsonl']['maximum_rss_bytes'],resources['worker-resources.jsonl']['maximum_self_peak_rss_bytes'])==wr['maximum_observed_RSS_bytes']==952745984
assert resources['worker-resources.jsonl']['maximum_mps_driver_bytes']==wr['maximum_MPS_driver_bytes']==2456387584
owned=data(RUN/'owned-process.json');pids=[command['wrapper_pid'],command['supervisor_pid'],owned['owned_pid']];proc=subprocess.run(['ps','-p',','.join(map(str,pids)),'-o','pid=,pgid=,command='],capture_output=True,text=True,timeout=5);assert proc.returncode==1 and not proc.stdout.strip(),proc.stdout
assert data(EXE/'process-ownership-after.json')['remaining_owned']==[]
parent_path=ROOT/plan['parent_checkpoint'];assert digest(parent_path)==plan['parent_checkpoint_sha256'];parent=torch.load(parent_path,map_location='cpu',weights_only=False)
lineage=data(RUN/'parent-lineage.json');assert lineage['parent_sha256']==plan['parent_checkpoint_sha256'] and lineage['parent_terminal_receipt']==plan['parent_terminal_receipt'] and lineage['transition_to']=='D2'
states=[];tensor_summary=[]
for path in sorted(RUN.glob('*.pt')):
    raw(path);state=torch.load(path,map_location='cpu',weights_only=False);states.append(state)
    assert state['identity']==identity and state['parent_checkpoint_sha256']==plan['parent_checkpoint_sha256'] and finite(state['model']) and finite(state['optimizer'])
    actual=sorted({float(v['step']) for v in state['optimizer']['state'].values()});partial=state['update_progress'].get('optimizer_steps',0) if state['update_progress'].get('in_update') else 0
    assert actual==[float(state['counters']['optimizer_steps']+partial)]
    if state['tag']=='interrupted_mid_update':assert state['update_progress']['in_update'] and not state['update_progress']['complete']
    elif state['counters']['phase_updates']:assert state['update_progress']['complete'] is True and not state['update_progress']['in_update']
    tensor_summary.append({'file':path.name,'phase_updates':state['counters']['phase_updates'],'total_updates':state['counters']['updates'],'Adam_steps':actual,'partial_Adam_steps':partial,'tag':state['tag']})
assert len(states)==15;entry,final=states[0],states[-1]
assert equal(entry['model'],parent['model']) and equal(entry['optimizer'],parent['optimizer']) and equal(entry['rng'],parent['rng'])
assert entry['counters']['updates']==48 and entry['counters']['optimizer_steps']==6144 and entry['counters']['phase_updates']==0
assert final['tag']=='interrupted_mid_update' and final['counters']['updates']==152 and final['counters']['phase_updates']==104 and final['counters']['optimizer_steps']==6144+13248
assert final['update_progress']==wr['update_progress'] and final['update_progress']['optimizer_steps']==69
assert digest(RUN/wr['checkpoint'])==wr['checkpoint_sha256']=='bc0bb18106d52ca2e133fc6123263779660a4324c031b2b4ca5ad3b0741ae194'
try:ckpt.require_complete_update(final)
except ValueError as error:ineligible=str(error)
else:raise AssertionError('partial learner unexpectedly eligible')
abandoned=[x for x in training if x['kind']=='abandoned_on_fresh_env_resume'];assert len(abandoned)==64 and abandoned==[dict(x,reason='curriculum_namespace_transition') for x in parent['abandoned_episodes']]
for name,want in inputs.items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==want,name
(OUT/'inspected-inputs.json').write_text(json.dumps(inputs,indent=2,sort_keys=True)+'\n')
report={'status':'passed_retained_failure_audit','findings':[],'started_at_utc':START.isoformat(),'finished_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'elapsed_seconds':time.monotonic()-AT,'scope':'retained_receipts_raw_rows_CPU_checkpoint_deserialization_and_read_only_ineligibility_validator;no_model_execution_update_gameplay_or_tests','verified':{'execution_artifacts':counts['execution'],'runner_artifacts':counts['runner'],'current_source_pins':75,'command_invocations':1,'supervisor_exit_code':1,'worker_exit_code':1,'wrapper_exit_code':1,'source_phase_wall_seconds':rr['consumed_phase_wall_seconds'],'postflight_checks':146,'all_inspected_inputs_unchanged':len(inputs),'completed_training_episodes':len(completed),'maximum_reward_error':max(errors),'training_seed_starts_and_resets_checked':len(infos),'completed_collections':len(accepts),'inherited_updates':48,'inherited_Adam_steps':6144,'new_complete_updates':104,'new_complete_Adam_steps':13248,'partial_Adam_steps':69,'total_complete_updates':152,'total_actual_Adam_steps':19461,'entry_model_Adam_RNG_equal_parent':True,'abandoned_parent_episodes_logged':64,'retained_checkpoints':15,'no_owned_processes':pids},'development_evaluations':evaluations,'resource_maxima':resources,'checkpoint_tensor_summary':tensor_summary,'failure_checkpoint':str((RUN/wr['checkpoint']).relative_to(ROOT)),'failure_checkpoint_sha256':wr['checkpoint_sha256'],'ineligibility_validator_message':ineligible,'D2_progress_passed':False,'D2_D3_qualified':False,'caveats':['Accounted wall1800.439149916987 includes cooperative cancellation/checkpoint cleanup after the1800-second guard;not relaxed training budget.','Last complete evaluation is phase96 candidate000022;final phase104-plus-partial failure checkpoint was not evaluated. Do not call phase96 scores terminal-checkpoint performance.','All failed-run artifacts remain diagnostic/ineligible;no candidate selected or successor authorized.','Entry tensor equality and saved RNG establish checkpoint continuity, not uninterrupted gameplay replay.','RSS/MPS peaks are separate sampled/cooperative measurements.']}
(OUT/'audit.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':report['status'],'verified':report['verified'],'audit_sha256':hashlib.sha256((OUT/'audit.json').read_bytes()).hexdigest()}))
