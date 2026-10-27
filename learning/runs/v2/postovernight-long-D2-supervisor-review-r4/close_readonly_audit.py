"""Close recorded evidence only; never starts another candidate scenario."""
from pathlib import Path
import hashlib,json,os,signal,sys,time
OUT=Path(__file__).resolve().parent;PREP=OUT.parent/'postovernight-long-D2-prepare-r4';sys.path.insert(0,str(PREP))
import processes as owned
import long_d2_executor as e
read=lambda p:json.loads(p.read_text())
summary=read(OUT/'fresh-checks-summary.json');assert summary['successful'] and summary['OS_subprocesses']==40
rows=[read(p) for p in sorted((OUT/'targeted-controls').glob('*/observed-command.json'))];assert len(rows)==40
extra_root=OUT/'takeover-controls/closure';extra=read(extra_root/'observed-command.json')
events=[json.loads(s) for s in (extra_root/'takeover-events.jsonl').read_text().splitlines()]
starts=[x for x in events if x['kind']=='monitor_start'];exits=[x for x in events if x['kind']=='monitor_exit'];fails=[x for x in events if x['kind']=='failure']
assert len(starts)==2 and len({x['pool'] for x in events})==1 and len(exits)==1
assert starts[0]['stop']!=starts[1]['stop'] and not any(x['stop_set'] for x in starts)
assert exits[0]['stop']==starts[0]['stop'] and exits[0]['stop_set'] and exits[0]['monotonic']<starts[1]['monotonic']
assert starts[1]['until']==fails[0]['until'] and all(x['until']<=fails[0]['until'] for x in fails)
assert extra['raw_wait']['returncode']==1 and not extra['harness_kill_required'] and not extra['observed_acceptance']
assert 0<=extra['raw_wait']['observed_monotonic']-fails[0]['until']<.1
closure=dict(status='recorded_evidence_readonly_audit',candidate_rerun=False,additional_OS_executions=1,collector_raw_exit=1,collector_error="KeyError: 'role'",collector_reason='Custom takeover-events.jsonl has no fixture role field; run_checks.case completed candidate observation then failed while auditing arm events',pass_variant_not_started=True,counted_as_clean_driver_pass=False,observed_candidate_raw_exit=1,observed_wall_seconds=extra['elapsed_seconds'],observed_acceptance=False,new_watchdog_new_event_same_pool=True,retiring_watchdog_exited_before_new_started=True,earliest_deadline_never_extended=True,deadline_observation_lag_seconds=extra['raw_wait']['observed_monotonic']-fails[0]['until'],events=events)
(OUT/'takeover-recorded-evidence-audit.json').write_text(json.dumps(closure,indent=2)+'\n')
groups=set();pids=set();final_io=[]
for row in rows+[extra]:
 pids.add(row['raw_wait']['pid']);root=Path(row['argv'][-1]);receipt=read(root/'execution/acceptance-receipt.json') if (root/'execution/acceptance-receipt.json').exists() else {}
 assert row['raw_wait']['direct_child_reaped'] and row['raw_wait']['returncode']==row['expected']
 assert all(row['positive_group_absence'].values()) and not row['harness_kill_required']
 assert all(not x['open_writers'] for x in row['writer_checks'])
 for g in receipt.get('ownership',{}).values():groups.add(g['pgid'])
 for p in root.glob('*-events.jsonl'):
  for s in p.read_text().splitlines():
   event=json.loads(s)
   if event['kind']=='ownership':groups.update(g['pgid'] for g in event['ownership'].values())
   if event['kind']=='final_IO_boundary':
    assert event['latch_phase']=='NORMAL' and not event['watchdog_alive'] and not any(event['guard_handles_alive']);final_io.append(event)
 if row['expected'] in (0,2):
  assert e.accept_observed(receipt,row['raw_wait']['returncode'],row['elapsed_seconds'])
  assert receipt['ownership']['supervisor']['group_absent'] and receipt['ownership']['worker']['group_absent']
  assert receipt['worker_wait']['direct_child_reaped'] and receipt['inner_wait']['direct_child_reaped']
absence={str(pgid):owned.absent(pgid,time.monotonic()+.2) for pgid in groups}
process_absence={}
for pid in pids:
 try:os.kill(pid,0);process_absence[str(pid)]=False
 except ProcessLookupError:process_absence[str(pid)]=True
assert all(absence.values()) and all(process_absence.values())
(OUT/'owned-processes-after.json').write_text(json.dumps(dict(groups=absence,direct_executors=process_absence,nonchild_worker_waitpid_claimed=False),sort_keys=True,indent=2)+'\n')
final_summary=dict(clean_driver_OS_cases=len(rows),ancillary_OS_executions=1,total_outer_OS_executions=len(rows)+1,clean_positive_acceptances=sum(row['expected'] in (0,2) for row in rows),clean_expected_rejections=sum(row['expected']==1 for row in rows),known_groups_positively_absent=len(groups),direct_executors_reaped_and_absent=len(pids),final_IO_boundaries_inspected=len(final_io),no_post_collector_failure_candidate_execution=True,ML_imports=[n for n in sys.modules if n.split('.')[0] in ('torch','numpy','dodge_rl')])
(OUT/'execution-evidence-summary.json').write_text(json.dumps(final_summary,indent=2)+'\n');print(json.dumps(final_summary))
