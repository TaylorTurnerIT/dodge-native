"""Parent terminal audit for the completed timing probe; never promotes weights."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys

PACKAGE=Path(__file__).resolve().parent
ROOT=PACKAGE.parents[3]
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--run-id',required=True)
run_id=parser.parse_args().run_id
if '/' in run_id or run_id not in {row['run_id'] for row in json.loads((PACKAGE/'registration-index.json').read_text())['runs']}:
    raise ValueError('unregistered comparison run')
HERE=PACKAGE/run_id
SUPERVISOR=ROOT/'learning/runs/v2/progressive1000-opening-maintenance-supervisor-parent-20261027-r1'
sys.path.insert(0,str(SUPERVISOR))
import binding as b
import terminal


def main():
    reg_path=HERE/'registration-final.json';reg=b.read(reg_path);digest=b.sha(reg_path)
    execution=b.read(HERE/'parent-execution.json');exit_record=b.read(HERE/'execution-exit.json')
    envelope=b.read(HERE/'launch-envelope.json');control=Path(envelope['control'])
    observation=b.read(control/'observation.json');out=Path(reg['output'])
    b.need(exit_record['raw_observer_exit_code']==0 and exit_record['observer_directly_reaped'],'observer did not complete cleanly')
    b.need(observation['status']=='completed_pending_parent_audit' and observation['observed_worker_raw_exit']==0
        and observation['directly_reaped'] and observation['first_event'] is None,'worker did not complete cleanly')
    groups=[]
    rows=subprocess.run(['/bin/ps','-axo','pid=,ppid=,pgid=,command='],check=True,capture_output=True,text=True).stdout
    parsed=[line.split(None,3) for line in rows.splitlines() if line.strip()]
    for role,pgid in [('observer',execution['observer_pgid']),('worker',observation['owned_pgid'])]:
        b.need(not any(int(row[2])==pgid for row in parsed),role+' group still present')
        try:os.killpg(pgid,0)
        except ProcessLookupError:pass
        else:raise ValueError(role+' group absence not proven')
        groups.append(dict(role=role,pgid=pgid,absent=True))
    b.need(digest==execution['registration_sha256']==observation['registration_sha256'],'registration drift')
    b.need(b.sha(HERE/'launch-envelope.json')==execution['envelope_sha256'],'envelope drift')
    b.verify_bound(envelope,reg,preflight=False)
    worker=b.read(out/'worker-result.json')
    report=terminal.validate_outputs(reg,worker,digest)
    c=b.contracts()
    import successor_identity
    expected_identity=successor_identity.learner_identity(reg,digest)
    expected_identity_sha=hashlib.sha256(json.dumps(expected_identity,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    # Deserialize only authenticated local checkpoint bytes, on CPU, after all
    # source/pin/group checks. This is integrity inspection, never learner restore.
    import torch
    metrics=list(terminal.rows(out/'training-metrics.jsonl',strict=True))
    embedded=[]
    for record in worker['integrity_checkpoints']:
        path=Path(record['path']);b.need(b.sha(path)==record['sha256'],'checkpoint changed before inspection')
        checkpoint=torch.load(path,map_location='cpu',weights_only=False)
        local=record['global_update']
        b.need(checkpoint['identity']==expected_identity and checkpoint['identity_sha256']==expected_identity_sha,'embedded identity differs')
        b.need(checkpoint['global_update']==local and checkpoint['phase_update']==324+local
            and checkpoint['cumulative_update']==372+local and checkpoint['counters']==metrics[local-1]['counters'],'embedded counters differ')
        b.need(checkpoint['parent_checkpoint_sha256']==reg['parent_checkpoint_sha256']
            and checkpoint['successor_runtime_manifest_sha256']==reg['runtime_manifest_sha256'],'embedded lineage differs')
        b.need(all(group['lr']==3e-5 and group['eps']==1e-5 for group in checkpoint['optimizer']['param_groups']),'embedded constant Adam differs')
        b.need(checkpoint['training_eligible'] is False and checkpoint['promoted'] is False
            and checkpoint['automatic_selection'] is False and checkpoint['formal_comparison_endpoint'] is (local==60),'probe checkpoint claims eligibility')
        b.need(checkpoint['curriculum_state']['completed_updates']==local,'embedded curriculum counters differ')
        for tensor in checkpoint['model'].values():
            b.need(tensor.device.type=='cpu' and bool(torch.isfinite(tensor).all()),'nonfinite model tensor')
        embedded.append(dict(global_update=local,path=str(path),sha256=record['sha256'],embedded_identity_and_counters='passed',comparison_endpoint=(local==60)))
        del checkpoint
    progress=[]
    for line in (control/'worker.log').read_text().splitlines():
        try:row=json.loads(line)
        except ValueError:continue
        if row.get('schema')=='progressive1000_progress_v1':progress.append(row)
    complete=[row for row in progress if row['phase']=='between_updates' and 'guard_calls' not in row]
    b.need([row['completed_updates'] for row in complete]==list(range(1,61)),'phase completion journal incomplete')
    phases={name:[row['phase_seconds'].get(name,0) for row in complete] for name in ['collection','PPO','collection_journal','metrics_write','checkpoint']}
    timing=dict(completed_updates=60,elapsed_seconds=exit_record['elapsed_seconds'],
        phase_mean_seconds={name:statistics.mean(values) for name,values in phases.items()},
        phase_max_seconds={name:max(values) for name,values in phases.items()},
        mean_seconds_per_update=complete[-1]['average_seconds_per_update'],
        recent_seconds_per_update=complete[-1]['recent_seconds_per_update'],
        projected_60_seconds=complete[-1]['average_seconds_per_update']*60,
        shared_GPU_MPS_confirmed_by_user=True,
        interpretation='PPO timing varies under confirmed shared MPS use. Prior historical slowdown cause is not uniquely established.',
        timing_limit='Tiny negative between_updates bookkeeping intervals in R1 are excluded; R2 corrects clock sample order.')
    b.save(HERE/'timing-result.json',timing)
    c.cache_check(reg)
    audit=dict(schema='parent_progressive1000_monitored_arm_terminal_audit_v1',
        status='integrity_accepted_pending_six_arm_comparison',registration_sha256=digest,completed_updates=60,
        counters=worker['counters'],raw_worker_exit_code=0,raw_observer_exit_code=0,
        process_groups=groups,postflight_inputs_dependencies_cache='passed',embedded_checkpoints=embedded,
        terminal_accounting=report,timing=timing,formal_comparison_endpoint=worker['formal_comparison_endpoint'],
        parent_checkpoint_unchanged=324,training_eligible=False,promoted=False,automatic_selection=False,
        at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    b.save(HERE/'parent-terminal-audit.json',audit)
    b.save(HERE/'compact-campaign-receipt.json',dict(schema='parent_timing_probe_compact_evidence_v1',
        audit=audit,worker=worker,raw_observation=observation,raw_execution_exit=exit_record,
        entry_restoration=b.read(out/'entry-restoration.json'),metrics=metrics,progress=progress,
        checkpoint_bytes='local only'))
    state=b.read(reg['state_path']);b.need(state['active_long_campaign']==reg['expected_lease'],'refusing to clear another lease')
    state['active_long_campaign']=None
    state['progressive1000_curriculum_work'].update(active_registered_run=None,current_launch_authorized=False,
        status='monitored_arm_complete_parent_audited;remaining_arms_pending_exact_launch',
        latest_monitored_arm_terminal_audit=str(HERE/'parent-terminal-audit.json'),
        latest_monitored_arm_terminal_audit_sha256=b.sha(HERE/'parent-terminal-audit.json'),
        shared_GPU_MPS_confirmed_by_user=True)
    state['progressive1000_curriculum_work'].setdefault('monitored_completed_arms',[]).append(dict(run_id=reg['run_id'],registration_sha256=digest,audit=str(HERE/'parent-terminal-audit.json'),endpoint=worker['formal_comparison_endpoint']))
    staged=Path(reg['state_path']).with_name('state.probe-terminal.pending.json');b.save(staged,state);os.replace(staged,reg['state_path'])
    fd=os.open(Path(reg['state_path']).parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
    b.save(HERE/'lease-release.json',dict(status='exact_lease_cleared_after_durable_parent_audit',audit_sha256=b.sha(HERE/'parent-terminal-audit.json')))
    print(json.dumps(timing,indent=2),flush=True)


if __name__=='__main__':main()
