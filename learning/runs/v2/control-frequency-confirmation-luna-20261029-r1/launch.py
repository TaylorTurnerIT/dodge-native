"""Exactly-once launcher; requires parent source, runtime, resource, and authorization gates."""
from __future__ import annotations
import argparse,datetime,os,subprocess,time
from pathlib import Path
import binding as b
import power_guard

PENDING='state.control-frequency-confirmation.pending.json'

def replace_state(path,state):
    staged=Path(path).with_name(PENDING);b.save(staged,state);os.replace(staged,path)
    fd=os.open(Path(path).parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

def state_free(reg):
    path=Path(reg['state_path']);b.need(not os.path.lexists(path.with_name(PENDING)),'shared state pending file exists')
    state=b.read(path)
    for key in ('active_long_campaign','active_inference_diagnostic','active_inference_campaign','active_inference_lease'):
        b.need(state.get(key)is None,'active lease blocks screen: '+key)
    b.need(state.get('training_hold',{}).get('active') is not True,'training hold active')
    return state

def install_lease(reg):
    state=state_free(reg);state[reg['lease_key']]=reg['expected_lease']
    state['last_update_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();replace_state(reg['state_path'],state)

def check_acceptances(reg_path,reg_sha,gate_path,gate_sha,source_path,source_sha):
    b.verify_pins({reg_path:reg_sha,gate_path:gate_sha,source_path:source_sha})
    reg=b.read(reg_path);b.validate_static(reg)
    source=b.read(source_path)
    b.need(source==b.source_acceptance_document(reg['source_manifest_sha256']),'independent source acceptance differs')
    gate=b.read(gate_path)
    b.need(gate==b.approval_document(reg_sha,reg['source_manifest_sha256'],gate.get('pins')),'exact parent gates missing')
    b.verify_pins(gate['pins'])
    return reg,gate

def require_empty_pycache(reg):
    cache=Path(reg['import_policy']['pycache_prefix'])
    b.need(cache.is_dir() and not cache.is_symlink(),'registered bytecode cache must be a real directory before lease installation')
    b.need(not any(cache.iterdir()),'registered bytecode cache must be empty before lease installation')
    return cache

def main(registration,registration_sha,gate_path,gate_sha,source_acceptance,source_acceptance_sha):
    reg,gate=check_acceptances(registration,registration_sha,gate_path,gate_sha,source_acceptance,source_acceptance_sha)
    require_empty_pycache(reg)
    for path in (reg['output'],reg['attempt_claim_path'],reg['launch_marker_path'],b.HERE/'launch-envelope.json',b.HERE/'parent-execution.json',b.HERE/'execution-exit.json',b.HERE/'observer.log',b.HERE/'worker-output'):
        b.need(not os.path.lexists(path),'registered exactly-once output already exists: '+str(path))
    control=b.HERE/'dispatch'/reg['run_id'];b.need(not control.exists(),'dispatch already spent')
    power=power_guard.check(override=None);b.need(power['on_ac'] is True,'DODGE-012 requires AC power')
    b.need(b.sha(reg['runtime_manifest_path'])==reg['runtime_manifest_sha256'],'runtime manifest changed')
    started=time.monotonic();install_lease(reg)
    pins={str(Path(registration).resolve()):registration_sha,reg['interpreter']:reg['interpreter_sha256'],
          str(b.HERE/'source-manifest.json'):reg['source_manifest_sha256'],
          str(Path(gate_path).resolve()):gate_sha,
          str(Path(source_acceptance).resolve()):source_acceptance_sha,**gate['pins'],**reg['input_pins']}
    envelope=dict(schema='control_frequency_confirmation_envelope_v1',run_id=reg['run_id'],registration=str(Path(registration).resolve()),
        registration_sha256=registration_sha,source_manifest_sha256=reg['source_manifest_sha256'],control=str(control),
        cancel_path=str(b.CANCEL),started=started,pins=pins)
    env_path=b.HERE/'launch-envelope.json';b.save(env_path,envelope);env_sha=b.sha(env_path)
    b.save(reg['launch_marker_path'],dict(schema='control_frequency_confirmation_spent_marker_v1',run_id=reg['run_id'],registration_sha256=registration_sha,started=started))
    env,loaded=b.load_envelope(env_path,env_sha);b.verify_bound(env,loaded,preflight=True)
    childenv=os.environ.copy();childenv.update(PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=reg['import_policy']['pycache_prefix'],PYTHONPATH=reg['runtime_root'])
    command=[reg['interpreter'],'-B',str(b.HERE/'observe.py'),'--envelope',str(env_path),'--envelope-sha256',env_sha]
    with (b.HERE/'observer.log').open('x') as log:
        process=subprocess.Popen(command,cwd=b.ROOT,env=childenv,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        b.save(b.HERE/'parent-execution.json',dict(observer_pid=process.pid,observer_pgid=process.pid,command=command,started=started,
            registration_sha256=registration_sha,envelope_sha256=env_sha,power_guard=power,lease_clear_owner='parent terminal auditor'))
        code=process.wait()
    b.save(b.HERE/'execution-exit.json',dict(raw_observer_exit_code=code,observer_directly_reaped=True,
        elapsed_seconds=time.monotonic()-started,registration_sha256=registration_sha,parent_terminal_audit_pending=True,
        lease_cleared=False))
    return int(code!=0)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('registration','registration-sha256','gate','gate-sha256','source-acceptance','source-acceptance-sha256'):parser.add_argument('--'+name,required=True)
    a=parser.parse_args();raise SystemExit(main(a.registration,a.registration_sha256,a.gate,a.gate_sha256,a.source_acceptance,a.source_acceptance_sha256))
