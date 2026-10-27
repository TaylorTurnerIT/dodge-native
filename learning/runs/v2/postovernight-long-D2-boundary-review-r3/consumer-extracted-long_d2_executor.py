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
        output=Path(registration['output'])
        c.verify_files({str(output/k):v for k,v in bindings['artifacts'].items()})
        for name,key in (('artifact-manifest.json','artifact_manifest_sha256'),('long-run-result.json','run_result_sha256'),('finalization-result.json','terminal_sha256'),('long-worker-result.json','worker_result_sha256')):
            c.require(c.sha(output/name)==bindings[key],'Critical artifact differs: '+name)
        return True
    except (KeyError, TypeError, OSError, c.Stop):
        return False
