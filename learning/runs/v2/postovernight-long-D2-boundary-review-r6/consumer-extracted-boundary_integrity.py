def need(ok, message):
    if not ok:
        raise life.Stop(message)

def summary_valid(summary, registration):
    try:
        worker = summary['worker']
        need(summary['schema']=='long_d2_compact_integrity_summary_v1', 'Wrong integrity summary schema')
        for key in ('protocol_sha256','config_sha256','identity_sha256','classification_sha256','reservation_sha256'):
            need(summary[key] == registration[key], 'Summary binding differs: '+key)
        need(summary['manifests'] == registration['class_manifest_hashes'], 'Class manifest bindings differ')
        for label in ('preflight','postflight'):
            endpoint = summary[label]
            need(endpoint['verdict']=='passed' and endpoint['role']=='outer_'+label, 'Missing actual endpoint')
            need(endpoint['counts']==registration['class_counts'], 'Endpoint class count differs')
            need(endpoint['classification_sha256']==registration['classification_sha256'] and endpoint['manifests']==registration['class_manifest_hashes'], 'Endpoint roots differ')
        need(worker['schema']=='long_d2_worker_integrity_summary_v1' and worker['final_live_legacy'] is True, 'Final legacy proof missing')
        for key in ('protocol_sha256','config_sha256','identity_sha256','classification_sha256'):
            need(worker[key]==registration[key], 'Worker summary differs: '+key)
        need(worker['manifests']==registration['class_manifest_hashes'], 'Worker manifests differ')
        rows = worker['boundaries']
        need(worker['boundary_count']==len(rows) and len(rows)>0, 'Worker boundary count differs')
        need(all(r['sequence']==i and r['verdict']=='passed' for i,r in enumerate(rows)), 'Worker boundary sequence failed')
        need(worker['final_runtime']['verdict']=='passed' and worker['final_runtime']['cache']['empty'] is True, 'Runtime/cache proof missing')
        need(all(summary[k] is None and worker[k] is None for k in ('first_local_failure','first_global_failure')), 'Failure prohibits acceptance')
        return True
    except (KeyError, TypeError, life.Stop):
        return False
