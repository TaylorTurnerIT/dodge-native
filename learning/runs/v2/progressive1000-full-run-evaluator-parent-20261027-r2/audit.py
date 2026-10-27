"""Root terminal audit; exact lease release follows durable accepted evidence."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import subprocess
import binding as b
import terminal
from paired_statistics import paired_intervals


def main(envelope_path,envelope_sha):
    e,reg=b.load_envelope(envelope_path,envelope_sha)
    b.need(not (b.HERE/'parent-terminal-audit.json').exists(),'parent audit already exists; inspect, never duplicate')
    b.check_lease(reg);execution=b.read(b.HERE/'parent-execution.json');exit_record=b.read(b.HERE/'execution-exit.json')
    observation=b.read(Path(e['control'])/'observation.json')
    b.need(execution['registration_sha256']==exit_record['registration_sha256']==e['registration_sha256']
        and execution['envelope_sha256']==envelope_sha,'execution identity differs')
    b.need(exit_record['raw_observer_exit_code']==0 and exit_record['observer_directly_reaped'] is True
        and observation['observed_worker_raw_exit']==0 and observation['directly_reaped'] is True
        and observation['first_event'] is None and observation['status']=='completed_pending_parent_audit'
        and observation['owned_group_absent'] is True,'supervisor raw completion differs')
    processes=subprocess.run(['/bin/ps','-axo','pid=,ppid=,pgid=,command='],capture_output=True,text=True,check=True).stdout
    groups=[]
    for role,pgid in [('observer',execution['observer_pgid']),('worker',observation['owned_pgid'])]:
        b.need(not any(int(line.split(None,3)[2])==pgid for line in processes.splitlines() if line.strip()),
            role+' process group remains')
        try:os.killpg(pgid,0)
        except ProcessLookupError:pass
        else:raise ValueError(role+' group absence not proven')
        groups.append(dict(role=role,pgid=pgid,absent=True))
    b.verify_bound(e,reg,preflight=False)
    out=Path(reg['output']);worker=b.read(out/'worker-result.json')
    accounting=terminal.validate_outputs(reg,worker,e['registration_sha256'])
    manifest=b.read(Path(e['control'])/'artifact-manifest.json')
    b.check_pins({str(out/name):digest for name,digest in manifest.items()})
    policy_rows={p['id']:b.read(out/(p['id']+'.json'))['rows'] for p in reg['policies']}
    intervals=paired_intervals(policy_rows,reg['bootstrap'])
    b.need(intervals==b.read(out/'comparison.json')['paired_conditional_seed_intervals'],
        'independent terminal bootstrap recomputation differs')
    audit=dict(schema='progressive1000_full_evaluation_parent_terminal_audit_v2',
        status='accepted_complete_fixed_endpoint_evaluation',registration_sha256=e['registration_sha256'],
        source_manifest_sha256=reg['source_manifest_sha256'],raw_worker_exit_code=0,raw_observer_exit_code=0,
        process_groups=groups,postflight_inputs_dependencies_cache='passed',accounting=accounting,
        comparison_path=str(out/'comparison.json'),comparison_sha256=b.sha(out/'comparison.json'),
        intervals_independently_recomputed=True,parent_checkpoint_unchanged=324,
        automatic_selection=False,promoted=False,training_eligible=False)
    b.save(b.HERE/'parent-terminal-audit.json',audit)
    state=b.read(reg['state_path']);b.need(state['active_long_campaign']==reg['expected_lease'],'refusing another lease')
    state['active_long_campaign']=None
    state.setdefault('progressive1000_curriculum_work',{}).update(full_comparison_complete=True,
        full_evaluation_parent_audit=str(b.HERE/'parent-terminal-audit.json'),
        full_evaluation_parent_audit_sha256=b.sha(b.HERE/'parent-terminal-audit.json'))
    from launch import replace_state
    replace_state(reg['state_path'],state)
    b.save(b.HERE/'lease-release.json',dict(status='exact_lease_cleared_after_durable_parent_audit',
        audit_sha256=b.sha(b.HERE/'parent-terminal-audit.json')))
    print('accepted_fixed_full_run_evaluation_no_promotion',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--envelope',required=True)
    parser.add_argument('--envelope-sha256',required=True);args=parser.parse_args()
    main(args.envelope,args.envelope_sha256)
