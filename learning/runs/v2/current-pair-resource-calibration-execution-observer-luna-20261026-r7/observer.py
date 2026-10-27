import datetime, hashlib, json, os, pathlib, subprocess, sys, time
ROOT=pathlib.Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
SRC=ROOT/'learning/runs/v2/current-pair-resource-calibration-prepare-luna-20261026-r7'
PARENT=ROOT/'learning/runs/v2/current-pair-resource-calibration-parent-execution-20261026-r7'
EVID=ROOT/'learning/runs/v2/current-pair-resource-calibration-execution-observer-luna-20261026-r7'
PLAN=SRC/'calibration-plan.json'; PINS=SRC/'source-pins.json'; LAUNCHER=SRC/'launch_once.py'; PROBE=SRC/'probe.py'; RES=PARENT/'reservation.json'; STATE=ROOT/'learning/runs/v2-orchestration/state.json'
OUTPUT=SRC/'probe-output'; MARKER=SRC/'launch-once.marker'; LAUNCH=EVID/'launch.json'; OBS=EVID/'observation.json'
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def identity(pid):
 try:
  out=subprocess.run(['/bin/ps','-p',str(pid),'-o','pid=,ppid=,pgid=,lstart=,command='],capture_output=True,text=True,timeout=2,check=True).stdout.strip()
  return {'pid':pid,'ps':out}
 except Exception as e: return {'pid':pid,'error':f'{type(e).__name__}: {e}'}
expected={'calibration-plan.json':'d8b16337301c558c37918580043277b0642f5fe7dfa08fba296583718c4bc301','source-pins.json':'4a05c85b5321bcc48b7c3d16c0d4a1e2a42d893f24fa47111be2008f3d00504f','launch_once.py':'888751e18fb5a7fb2a53e7b46be3272854142b5bc989e6d938e919496e693ffe','probe.py':'a78bde1702d5b1c6a55a08011c077d295db3d32c74a7deb23454f01fa47b3224','reservation.json':'f9940fe15956453869b9bc4640867ca0df009df001b4c0d2e3055536d00585ec'}
actual={p.name:sha(p) for p in (PLAN,PINS,LAUNCHER,PROBE,RES)}
if actual!=expected: raise RuntimeError(f'input hashes mismatch: {actual}')
if OUTPUT.exists() or MARKER.exists(): raise RuntimeError('unexpected source output or marker already exists')
plan=json.loads(PLAN.read_text()); reservation=json.loads(RES.read_text()); state=json.loads(STATE.read_text())
active=state.get('active_inference_diagnostic'); required=plan['authoritative_state_fields']['active_inference_diagnostic']|{'plan_sha256':expected['calibration-plan.json'],'campaign_launch_authorized':True,'review_receipt_sha256':reservation['review_receipt_sha256'],'review_source_manifest_sha256':reservation['review_source_manifest_sha256']}
if active!=required or state.get('active_long_campaign') is not None: raise RuntimeError('live authority mismatch')
if reservation.get('authorized_once') is not True or reservation.get('cancel_requested') is not False: raise RuntimeError('reservation authorization mismatch')
cache=EVID/'observer-bytecode-cache-empty'; cache.mkdir(exist_ok=True)
if any(cache.iterdir()): raise RuntimeError('observer bytecode cache not empty')
env=os.environ.copy(); env['PYTHONDONTWRITEBYTECODE']='1'; env['PYTHONPYCACHEPREFIX']=str(cache); env.pop('PYTHONPATH',None)
argv=[str(ROOT/'python/.venv/bin/python'),'-B',str(LAUNCHER),'--plan',str(PLAN),'--pins',str(PINS),'--reservation',str(RES),'--output',str(OUTPUT)]
started_utc=utc(); started_mono=time.monotonic(); stdout_path=EVID/'launcher.stdout.log'; stderr_path=EVID/'launcher.stderr.log'
with stdout_path.open('wb') as so, stderr_path.open('wb') as se:
 p=subprocess.Popen(argv,cwd=str(ROOT),env=env,stdin=subprocess.DEVNULL,stdout=so,stderr=se,start_new_session=True)
 birth=identity(p.pid)
 launch={'schema':'r7_calibration_launch_observer_v1','actual_launch_count':1,'argv':argv,'cwd':str(ROOT),'environment_policy':{'PYTHONDONTWRITEBYTECODE':'1','PYTHONPYCACHEPREFIX':str(cache),'PYTHONPATH':'unset','inherited_environment':'otherwise inherited'},'started_at_utc':started_utc,'started_monotonic_seconds':started_mono,'observer_pid':os.getpid(),'launcher_pid':p.pid,'launcher_identity_at_spawn':birth,'launcher_pgid':p.pid,'input_sha256':actual,'live_state_sha256_at_prelaunch':sha(STATE),'output':str(OUTPUT),'marker':str(MARKER),'stdout_log':str(stdout_path),'stderr_log':str(stderr_path),'monitor_deadline_seconds':120}
 LAUNCH.write_text(json.dumps(launch,sort_keys=True,indent=2)+'\n')
 deadline=started_mono+120
 try:
  while True:
   rc=p.poll()
   if rc is not None: break
   if time.monotonic()>=deadline:
    raise TimeoutError('launcher exceeded 120-second outer deadline; no signal sent by observer')
   time.sleep(.2)
 except BaseException as e:
  # Preserve fresh process identity and any launcher result; observer does not signal a process or group.
  data={'schema':'r7_calibration_execution_observation_v1','status':'observer_timeout_or_error','actual_launch_count':1,'error':f'{type(e).__name__}: {e}','finished_at_utc':utc(),'finished_monotonic_seconds':time.monotonic(),'launcher_identity_now':identity(p.pid),'launcher_returncode':p.poll(),'launch_record':str(LAUNCH),'output_exists':OUTPUT.exists(),'marker_exists':MARKER.exists()}
  OBS.write_text(json.dumps(data,sort_keys=True,indent=2)+'\n'); raise
 ended=time.monotonic(); paths=[OUTPUT/'launcher-result.json',OUTPUT/'launcher-cleanup-evidence.json',OUTPUT/'probe.stdout.log',OUTPUT/'probe.stderr.log',OUTPUT/'cpu-preflight.stdout.log',OUTPUT/'cpu-preflight.stderr.log',OUTPUT/'cpu-preflight.json',MARKER]
 terminal={str(x):({'exists':x.exists(),'sha256':sha(x) if x.is_file() else None,'size_bytes':x.stat().st_size if x.is_file() else None} if x.exists() else {'exists':False}) for x in paths}
 result={}
 rp=OUTPUT/'launcher-result.json'
 if rp.exists():
  try: result=json.loads(rp.read_text())
  except Exception as e: result={'parse_error':f'{type(e).__name__}: {e}'}
 obs={'schema':'r7_calibration_execution_observation_v1','status':'launcher_exited','actual_launch_count':1,'started_at_utc':started_utc,'finished_at_utc':utc(),'started_monotonic_seconds':started_mono,'finished_monotonic_seconds':ended,'actual_wall_seconds':ended-started_mono,'argv':argv,'environment_policy':launch['environment_policy'],'cwd':str(ROOT),'launcher_pid':p.pid,'launcher_identity_at_spawn':birth,'launcher_identity_after_exit':identity(p.pid),'launcher_pgid':p.pid,'raw_outer_exit':p.returncode,'terminal_result':result,'terminal_paths_and_hashes':terminal,'stdout_log_sha256':sha(stdout_path),'stderr_log_sha256':sha(stderr_path),'source_hashes_after':{p.name:sha(p) for p in (PLAN,PINS,LAUNCHER,PROBE,RES)},'source_hashes_before':actual,'probe_claims_scope':{'real_game_episodes':0,'training':False,'workload':'synthetic fake environments; historical best204 MPS forward only','claim_source':'launcher/probe outputs only'},'resource_summary':{k:result.get(k) for k in ('active_seconds','mps_forward_calls','complete_resource_samples','max_sample_gap_seconds','max_sample_age_seconds','maximum_mps_driver_bytes','maximum_aggregate_current_rss_bytes','owned_processes_and_groups_absent','raw_exits','status')},'terminal_paths_and_hashes':terminal,'launcher_stdout_stderr':{'stdout':str(stdout_path),'stderr':str(stderr_path)}}
 OBS.write_text(json.dumps(obs,sort_keys=True,indent=2)+'\n')
 print(json.dumps({'raw_outer_exit':p.returncode,'actual_wall_seconds':ended-started_mono,'launcher_result':result,'observation':str(OBS)},sort_keys=True))
 sys.exit(p.returncode)
