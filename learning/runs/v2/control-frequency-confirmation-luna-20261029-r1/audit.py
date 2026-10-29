"""Local terminal audit. Does not clear or mutate the main lease."""
from __future__ import annotations
import argparse
from pathlib import Path
import binding as b
import terminal

def observer_execution_result_path(envelope,reg):
    control=Path(envelope['control']).resolve()
    b.need(control==(b.HERE/'dispatch'/reg['run_id']).resolve(),'observer control path differs')
    return control/'execution-result.json'


def audit(registration,registration_sha,gate_path,gate_sha,source_path,source_sha):
    b.verify_pins({registration:registration_sha,gate_path:gate_sha,source_path:source_sha})
    reg=b.read(registration);b.validate_static(reg)
    b.need(b.sha(registration)==registration_sha,'registration hash differs')
    b.need(b.read(source_path)==b.source_acceptance_document(reg['source_manifest_sha256']),'source acceptance differs')
    gate=b.read(gate_path);b.need(gate==b.approval_document(registration_sha,reg['source_manifest_sha256'],gate.get('pins')),'gate acceptance differs');b.verify_pins(gate['pins'])
    envelope=b.read(b.HERE/'launch-envelope.json')
    execution=b.read(observer_execution_result_path(envelope,reg));exitrec=b.read(b.HERE/'execution-exit.json')
    b.need(execution['status']=='completed_pending_parent_audit' and execution['owned_group_absent'] is True and execution['directly_reaped'] is True and exitrec['raw_observer_exit_code']==0,'supervisor terminal state differs')
    worker=b.read(Path(reg['output'])/'worker-result.json');checks=terminal.validate_outputs(reg,worker,registration_sha)
    marker=b.read(reg['launch_marker_path']);b.need(marker['registration_sha256']==registration_sha and marker['run_id']==reg['run_id'],'spent marker differs')
    result=dict(schema='control_frequency_confirmation_local_terminal_audit_v1',status='complete_pending_parent_acceptance',run_id=reg['run_id'],registration_sha256=registration_sha,source_manifest_sha256=reg['source_manifest_sha256'],worker_sha256=b.sha(Path(reg['output'])/'worker-result.json'),comparison_sha256=worker['comparison_sha256'],terminal_checks=checks,lease_owner='parent terminal auditor',lease_cleared=False,automatic_selection=False,promoted=False)
    b.save(b.HERE/'local-terminal-audit.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('registration','registration-sha256','gate','gate-sha256','source-acceptance','source-acceptance-sha256'):p.add_argument('--'+name,required=True)
    a=p.parse_args();print(audit(a.registration,a.registration_sha256,a.gate,a.gate_sha256,a.source_acceptance,a.source_acceptance_sha256))
