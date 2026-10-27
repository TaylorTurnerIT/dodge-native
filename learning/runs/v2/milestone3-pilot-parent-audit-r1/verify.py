from __future__ import annotations
import hashlib, json, math, os, pathlib, subprocess, sys, time, datetime, collections
import torch
from dodge_rl import checkpoints as ckpt

ROOT=pathlib.Path.cwd()
OUT=ROOT/'learning/runs/v2/milestone3-pilot-parent-audit-r1'
RUN=ROOT/'learning/runs/v2/milestone3-D1-pilot-r1'
EXE=ROOT/'learning/runs/v2/milestone3-pilot-execution-r1'
START=datetime.datetime.now(datetime.timezone.utc)
AT=time.monotonic()
inputs={}
def raw(p):
 p=pathlib.Path(p)
 b=p.read_bytes();d=hashlib.sha256(b).hexdigest();key=str(p.relative_to(ROOT))
 if key in inputs: assert inputs[key]==d,('changed',key)
 inputs[key]=d
 return b
def digest(p):return hashlib.sha256(raw(p)).hexdigest()
def data(p):return json.loads(raw(p))
def rows(p):return [json.loads(x) for x in raw(p).splitlines()]
def finite(v):
 if isinstance(v,torch.Tensor):return not v.is_floating_point() or bool(torch.isfinite(v).all())
 if isinstance(v,dict):return all(finite(x) for x in v.values())
 if isinstance(v,(list,tuple)):return all(finite(x) for x in v)
 if isinstance(v,float):return math.isfinite(v)
 return True
plan=data(ROOT/'learning/runs/v2-orchestration/milestone3_D1_pilot_r1-plan.json')
assert digest(ROOT/'learning/runs/v2-orchestration/milestone3_D1_pilot_r1-plan.json')=='7a7e3aadba3a27d112b068a3df310c03891797ecc0022d11ef1aca096f1d13da'
counts={}
for directory,label in [(EXE,'execution'),(RUN,'runner')]:
 manifest=data(directory/'artifact-sha256.json')
 for n,d in manifest.items():assert digest(directory/n)==d,(label,n)
 observed={str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file()}
 assert observed==set(manifest)|{'artifact-sha256.json'},(label,'inventory')
 counts[label]=len(manifest)
identity=data(ROOT/plan['identity']);config=data(ROOT/plan['config'])
assert digest(ROOT/plan['identity'])==plan['identity_sha256']=='7d59a77c389abcaa91481be8cd8dd7d1154f29f2544f70badc06c706db543379'
assert digest(ROOT/plan['config'])==plan['config_sha256']=='0c987279795ff2618592dc46fbab723a4341fce290df718475897494f56d19e4'
canonical=json.dumps(config,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
assert hashlib.sha256(canonical).hexdigest()==plan['semantic_config_sha256']==identity['config_sha256']
assert len(identity['sources'])==75
for n,d in identity['sources'].items():assert digest(ROOT/n)==d,n
assert config['phase']=='pilot' and config['device']=='mps' and config['parent_checkpoint_sha256'] is None
assert config['phase_settings']['initialization_seed']==23002 and config['phase_settings']['run_seed']==5562878240475796481
assert data(RUN/'registered-config.json')==config and data(RUN/'identity.json')==identity
command=data(EXE/'command-terminal.json');start=data(EXE/'command-start.json')
assert command['argv']==start['argv']==plan['argv']
assert command['environment_overrides']==plan['environment'] and command['cwd']==plan['cwd']
assert command['supervisor_exit_code']==0 and type(command['supervisor_exit_code']) is int and not command['timed_out']
assert command['duration_seconds']<330
assert data(EXE/'wrapper-tool-exit.json')['exit_code']==0
assert digest(EXE/'execute_once.py')==command['wrapper_source_sha256']
events=rows(EXE/'wrapper-events.jsonl');assert sum(x['kind']=='command_launched_once' for x in events)==1
assert not any(x['kind'].lower().find('signal')>=0 or x['kind'].lower().find('timeout')>=0 for x in events)
rr=data(RUN/'run-result.json');wr=data(RUN/'worker-result.json');er=data(EXE/'result.json')
assert rr['status']==wr['status']=='passed' and rr['worker_result']==wr
assert rr['worker_exit_code']==0 and rr['consumed_phase_wall_seconds']<300 and wr['elapsed_seconds']<300
assert rr['automatic_retries']==0 and rr['limits_relaxed'] is False and rr['B_opened'] is False
assert er['command_launch_count']==1 and er['automatic_retries']==0 and not er['limits_relaxed'] and not er['B_E_opened']
proof=data(RUN/(wr['checkpoint']+'.evaluation.json'))
assert proof==wr['evaluation'] and proof['complete'] and proof['passed'] and proof['phase']=='pilot'
expected=list(range(3489660928,3489660992))
summary={}
for name,filename,value in [('before','pilot-before-development.jsonl',proof['before']),('after','checkpoint-000004-candidate-D1-development.jsonl',proof['evaluations']['D1'])]:
 stream=sorted(rows(RUN/filename),key=lambda x:x['episode_index']);cert=sorted(value['rows'],key=lambda x:x['episode_index'])
 assert stream==cert and len(stream)==64 and [x['seed'] for x in stream]==expected
 assert [x['episode_index'] for x in stream]==list(range(64))
 assert value['stage']=='D1' and value['action_mode']=='deterministic_argmax' and value['gradients'] is False and value['complete']
 for row in stream:
  assert row['score']==row['score_raw_fixed']/65536
  assert row['terminated']!=row['truncated'] and 0<row['gameplay_frames']<=2000
  assert row['alive_frames']==row['gameplay_frames']-int(row['terminated'])
  assert abs(row['objective_return']-(row['score']+row['alive_frames']/100-5*int(row['terminated'])))<=1e-9
 score=sum(x['score_raw_fixed'] for x in stream)/(64*65536)
 alive=sum(x['alive_frames'] for x in stream)/64
 deaths=sum(x['terminated'] for x in stream);caps=sum(x['truncated'] for x in stream)
 assert score==value['mean_score'] and alive==value['mean_alive_frames'] and deaths==value['deaths'] and caps==value['caps']
 summary[name]={'mean_score':score,'mean_alive_frames':alive,'deaths':deaths,'caps':caps,'episodes':64}
assert summary['before']=={'mean_score':.03125,'mean_alive_frames':223.140625,'deaths':64,'caps':0,'episodes':64}
assert summary['after']=={'mean_score':3.921875,'mean_alive_frames':990.296875,'deaths':61,'caps':3,'episodes':64}
assert summary['after']['mean_score']>summary['before']['mean_score'] and summary['after']['mean_alive_frames']>summary['before']['mean_alive_frames']
assert sorted(p.name for p in RUN.glob('*-development.jsonl'))==['checkpoint-000004-candidate-D1-development.jsonl','pilot-before-development.jsonl']
metrics=rows(RUN/'training-metrics.jsonl');assert len(metrics)==16 and finite(metrics)
assert [x['counters']['phase_updates'] for x in metrics]==list(range(1,17))
assert all(x['metrics']['finite'] and x['metrics']['actor_grad_norm']>0 and x['metrics']['critic_grad_norm']>0 for x in metrics)
assert all(x['metrics']['entropy']>=.3 for x in metrics)
assert max(x['metrics']['approx_kl'] for x in metrics)<.1
assert sum(x['metrics']['optimizer_steps'] for x in metrics)==2048
assert all(x['metrics']['transitions']==16384 and x['metrics']['optimizer_steps']==128 and x['metrics']['epochs_completed']==4 for x in metrics)
assert wr['counters']['phase_updates']==16 and wr['counters']['optimizer_steps']==2048
assert proof['actor_gradient_seen'] and proof['critic_gradient_seen'] and proof['completed_training_updates']==16
training=rows(RUN/'training-episodes.jsonl');kinds=collections.Counter(x['kind'] for x in training)
completed=[x['info'] for x in training if x['kind']=='native_completed_episode'];assert len(completed)==3098
assert len({(x['seed']['slot'],x['seed']['episode']) for x in completed})==3098
errors=[]
for x in completed:
 assert x['score_raw_fixed']==x['score_delta_sum_raw_fixed'] and x['score']==x['score_raw_fixed']/65536
 assert x['alive_frames']==x['gameplay_frames']-int(x['terminated'])
 errors.append(abs(x['objective_return']-(x['score_delta_sum_raw_fixed']/65536+x['alive_frames']/100-5*int(x['terminated']))))
 assert errors[-1]<=1e-9
accept=[x for x in training if x['kind']=='collection_accepted'];assert len(accept)==16
assert sum(x['completed_episodes'] for x in accept)==3098 and sum(x['transitions'] for x in accept)==262144
assert sum(x['returned_raw_frames'] for x in accept)==wr['counters']['raw_frames']==1043929
initial=[x for x in training if x['kind']=='initial'];assert len(initial)==1
assert initial[0]['batch_info']['run_seed']==5562878240475796481 and initial[0]['batch_info']['initial_episode_indices']==[0]*64
ranges=[(2952790016,2952791015),(3489660928,3489661055),(3758096384,3758097383)]
assert initial[0]['batch_info']['effective_excluded_seed_ranges']==[list(x) for x in ranges]
infos=list(initial[0]['info'])
for row in training:
 if row['kind']=='native_reset':infos.extend(row['info'])
seen=set();last={}
for info in infos:
 seed=info['seed'];actual=seed['actual_seed'];slot=seed['slot'];ep=seed['episode']
 assert type(actual) is int and 0<=actual<2**32 and not any(a<=actual<=b for a,b in ranges) and seed['evaluation'] is False
 assert (slot,ep) not in seen;seen.add((slot,ep));assert ep==last.get(slot,-1)+1;last[slot]=ep
resources={}
for filename in ['supervisor-resources.jsonl','worker-resources.jsonl']:
 values=rows(RUN/filename);assert values and finite(values)
 resources[filename]={'samples':len(values),'maximum_rss_bytes':max(x.get('rss_bytes',0) for x in values),'maximum_self_peak_rss_bytes':max(x.get('self_peak_rss_bytes',0) for x in values),'maximum_mps_driver_bytes':max(x.get('mps_driver_bytes',0) for x in values),'maximum_worker_rss_bytes':max(x.get('worker_rss_bytes',0) for x in values)}
 assert all(v<=6442450944 for k,v in resources[filename].items() if k!='samples')
assert resources==data(EXE/'resource-summary.json')==er['actual_resource_series_maxima']
assert max(resources['worker-resources.jsonl']['maximum_rss_bytes'],resources['worker-resources.jsonl']['maximum_self_peak_rss_bytes'])==wr['maximum_observed_RSS_bytes']==934952960
assert resources['worker-resources.jsonl']['maximum_mps_driver_bytes']==wr['maximum_MPS_driver_bytes']==2399076352
owned=data(RUN/'owned-process.json');pids=[command['wrapper_pid'],command['supervisor_pid'],owned['owned_pid']]
check=subprocess.run(['ps','-p',','.join(map(str,pids)),'-o','pid=,pgid=,command='],capture_output=True,text=True,timeout=5)
assert check.returncode==1 and not check.stdout.strip(),check.stdout
assert data(EXE/'process-ownership-after.json')['remaining_owned']==[]
ckptpaths=[RUN/x for x in ['checkpoint-000001-pilot_initial.pt','checkpoint-000002-periodic.pt','checkpoint-000003-periodic.pt','checkpoint-000004-candidate.pt']]
states=[];tensor_summary=[]
for path in ckptpaths:
 raw(path);state=torch.load(path,map_location='cpu',weights_only=False);states.append(state)
 assert state['identity']==identity and state['parent_checkpoint_sha256'] is None and finite(state['model']) and finite(state['optimizer'])
 steps=sorted({float(v['step']) for v in state['optimizer']['state'].values()})
 tensor_summary.append({'file':path.name,'tag':state['tag'],'optimizer_entries':len(state['optimizer']['state']),'actual_Adam_steps':steps,'phase_updates':state['counters']['phase_updates']})
assert states[0]['tag']=='pilot_initial' and states[0]['optimizer']['state']=={} and states[0]['counters']['phase_updates']==0
assert states[-1]['tag']=='candidate' and states[-1]['update_progress']['complete'] is True and not states[-1]['update_progress']['in_update']
assert tensor_summary[-1]['actual_Adam_steps']==[2048.0] and tensor_summary[-1]['optimizer_entries']==41
probe_initial=ROOT/'learning/runs/v2/milestone3-device-probe-r1/checkpoint-000001-probe_diagnostic.pt';raw(probe_initial);probe=torch.load(probe_initial,map_location='cpu',weights_only=False)
assert any(not torch.equal(t,probe['model'][n]) for n,t in states[0]['model'].items())
assert any(not torch.equal(t,states[-1]['model'][n]) for n,t in states[0]['model'].items())
anchor={'run_id':rr['run_id'],'phase':'pilot','run_result_sha256':digest(RUN/'run-result.json'),'checkpoint_sha256':digest(RUN/wr['checkpoint']),'evaluation_sha256':digest(RUN/(wr['checkpoint']+'.evaluation.json')),'identity_sha256':plan['identity_sha256'],'config_sha256':plan['config_sha256'],'supervisor_exit_code':command['supervisor_exit_code']}
validated_rr,validated_wr=ckpt.validate_terminal_receipt(RUN,anchor);assert validated_rr==rr and validated_wr==wr
for n,d in inputs.items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==d,n
(OUT/'inspected-inputs.json').write_text(json.dumps(inputs,indent=2,sort_keys=True)+'\n')
report={'status':'passed','findings':[],'started_at_utc':START.isoformat(),'finished_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'elapsed_seconds':time.monotonic()-AT,'scope':'retained_receipts_raw_rows_CPU_checkpoint_deserialization_and_read_only_terminal_validator;no_model_execution_update_gameplay_or_tests','verified':{'execution_artifacts':counts['execution'],'runner_artifacts':counts['runner'],'current_source_pins':len(identity['sources']),'command_invocations':1,'supervisor_exit_code':command['supervisor_exit_code'],'worker_exit_code':rr['worker_exit_code'],'source_phase_wall_seconds':rr['consumed_phase_wall_seconds'],'all_inspected_inputs_unchanged':len(inputs),'terminal_validator':'passed','completed_training_episodes':len(completed),'maximum_reward_error':max(errors),'training_seed_starts_and_resets_checked':len(infos),'completed_updates':len(metrics),'actual_Adam_steps':2048,'no_owned_processes':pids},'paired_development':summary,'resource_maxima':resources,'checkpoint_tensor_summary':tensor_summary,'parent_terminal_receipt':anchor,'parent_checkpoint':str((RUN/wr['checkpoint']).relative_to(ROOT)),'parent_checkpoint_sha256':digest(RUN/wr['checkpoint']),'pilot_improvement_passed':True,'D1_competence_passed':False,'D2_D3_qualified':False,'caveats':['Fresh initialization seed and RNG lineage are supported by registered config, empty initial optimizer, distinct probe/pilot starting weights and reviewed initialization/loading code. No initializer or gameplay replay was performed.','Pilot improvement only; final development score3.921875 and alive990.296875 remain below registered D1 progress floors10 and1500.','Observed RSS and MPS driver peaks are separate sampled/cooperative measurements, not an unsampled hard OS bound.']}
(OUT/'audit.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps(report))
