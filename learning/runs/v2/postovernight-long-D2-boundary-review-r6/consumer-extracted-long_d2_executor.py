def validate_wait_reports(receipt, raw_exit, elapsed_seconds):
    groups=receipt['ownership']
    c.require(set(groups)=={'supervisor','worker'},'Ownership incomplete')
    t0=float.fromhex(receipt['t0_monotonic_hex'])
    c.require(math.isfinite(t0) and t0>=0,'Invalid T0')
    for role,key,seconds in (('supervisor','inner_wait',c.INNER_SECONDS),('worker','worker_wait',c.WORKER_SECONDS)):
        group=groups[role];report=receipt[key]
        pid=group['pid'];parent=group['parent_at_registration']
        c.require(type(pid) is int and pid>1 and type(parent) is int and parent>1
                  and group['pgid']==pid and group['new_session_verified'] is True
                  and group['group_absent'] is True,'Invalid owned group')
        c.require(type(report['pid']) is int and report['pid']==pid
                  and type(report['reaped_by']) is int and report['reaped_by']==parent
                  and report['direct_child_reaped'] is True,'Direct-parent reap missing')
        status=report['raw_wait_status'];rc=report['returncode'];at=report['observed_monotonic']
        c.require(type(status) is int and 0<=status<=65535 and os.WIFEXITED(status)
                  and type(rc) is int and rc==raw_exit and os.waitstatus_to_exitcode(status)==rc,
                  'Raw wait/outcome differs')
        c.require(type(at) in (int,float) and math.isfinite(at)
                  and t0<=at<t0+seconds and at<=t0+elapsed_seconds,'Direct reap time invalid')
    c.require(groups['worker']['parent_at_registration']==groups['supervisor']['pid']
              and groups['worker']['pid']!=groups['supervisor']['pid']
              and receipt['worker_wait']['observed_monotonic']<=receipt['inner_wait']['observed_monotonic'],
              'Owned parent/order differs')
    return True

def accept_observed(receipt, raw_exit, elapsed_seconds, *, registration_sha256=None, summary_sha256=None):
    """Parent holds these digests and independently observes raw exit and wall.

    File checks are current actual bytes, not a manifest-only passing verdict.
    Missing parent pins, mandatory summary, ownership, or critical files reject.
    """
    try:
        if not (type(raw_exit) is int and raw_exit in (0,2) and type(elapsed_seconds) in (int,float)
                and math.isfinite(elapsed_seconds) and 0<=elapsed_seconds<=NORMAL_SECONDS
                and receipt.get('schema')=='long_d2_outer_acceptance_v2' and receipt.get('accepted') is True
                and receipt.get('expected_exit_code')==raw_exit and receipt.get('experiment_status')=='complete'
                and receipt.get('outcome')==('D2_progress_gate_passed' if raw_exit==0 else 'budget_closed_below_gate')
                and receipt.get('teacher_qualified') is False and receipt.get('training_parent_eligible') is False):
            return False
        registration=receipt['registration'];bindings=receipt['bindings'];summary=receipt['integrity_summary']
        c.require(registration_sha256 is not None and receipt['registration_sha256']==registration_sha256==c.sha(REGISTRATION_PATH), 'Parent registration digest missing/different')
        c.require(c.read_json(REGISTRATION_PATH)==registration,'Registration content differs')
        c.verify_files(registration['pins'])
        c.require(summary_sha256 is not None and bindings['integrity_summary_sha256']==summary_sha256==c.sha(bindings['integrity_summary_path']), 'Parent summary digest missing/different')
        c.require(c.read_json(bindings['integrity_summary_path'])==summary and integrity.summary_valid(summary,registration),'Mandatory summary differs')
        c.require(receipt['required_lease']==c.read_json(c.ORIGINAL_ROOT/c.PREPARE_REL/'required-lease.json'),'Required ownership/lease differs')
        c.require(set(receipt['ownership'])=={'supervisor','worker'} and all(v['new_session_verified'] and v['group_absent'] for v in receipt['ownership'].values()),'Ownership incomplete')
        validate_wait_reports(receipt,raw_exit,elapsed_seconds)
        output=Path(registration['output'])
        c.verify_files({str(output/k):v for k,v in bindings['artifacts'].items()})
        for name,key in (('artifact-manifest.json','artifact_manifest_sha256'),('long-run-result.json','run_result_sha256'),('finalization-result.json','terminal_sha256'),('long-worker-result.json','worker_result_sha256')):
            c.require(c.sha(output/name)==bindings[key],'Critical artifact differs: '+name)
        return True
    except (KeyError, TypeError, ValueError, OverflowError, OSError, c.Stop):
        return False
