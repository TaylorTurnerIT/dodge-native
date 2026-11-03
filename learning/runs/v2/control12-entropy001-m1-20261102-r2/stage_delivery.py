"""Trusted SSH delivery; require remote byte readback before stage execution."""
import hashlib, json, os, shlex, subprocess, sys
from pathlib import Path
SSH=['/usr/bin/ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','macbook-1']
SCP=['/usr/bin/scp','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12']
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def run(args): return subprocess.run(args,text=True,capture_output=True,check=True).stdout.strip()
phase='not_started'
owns_claim=False
def deliver(packet):
    global phase, owns_claim
    phase='claim'
    packet=Path(packet);contract_path=packet/'staging-contract.json';contract=json.loads(contract_path.read_text())
    claim=packet/'stage-delivery.claimed'
    fd=os.open(claim,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    owns_claim=True
    with os.fdopen(fd,'w') as stream:
        json.dump({'status':'delivery_started_no_retry','contract_sha256':sha(contract_path)},stream);stream.flush();os.fsync(stream.fileno())
    directory=os.open(packet,os.O_RDONLY);os.fsync(directory);os.close(directory)
    phase='local_contract_validation'
    archive_spec=contract['archive'];script_spec=contract['script']
    archive=packet/archive_spec['local_filename'];script=packet/script_spec['local_filename']
    if archive.name!=archive_spec['local_filename'] or archive.stat().st_size!=archive_spec['bytes'] or sha(archive)!=archive_spec['sha256']:
        raise ValueError('local archive contract mismatch')
    if script.stat().st_size!=script_spec['bytes'] or sha(script)!=script_spec['sha256']:
        raise ValueError('local stage script contract mismatch')
    remote_directory=contract['delivery_directory']
    if any(str(Path(item).parent)!=remote_directory for item in (archive_spec['destination'],script_spec['destination'],contract['contract_destination'])):
        raise ValueError('delivery paths must use the reserved directory')
    phase='reserve_remote_directory'
    run(SSH+['/bin/mkdir -m 700 '+shlex.quote(remote_directory)])
    phase='upload'
    run(SCP+[str(archive),'macbook-1:'+archive_spec['destination']])
    run(SCP+[str(script),'macbook-1:'+script_spec['destination']])
    run(SCP+[str(contract_path),'macbook-1:'+contract['contract_destination']])
    # This remote command reads metadata only. It does not execute packet code.
    readback_code="import hashlib,json,os,sys; print(json.dumps([{'path':p,'bytes':os.path.getsize(p),'sha256':hashlib.sha256(open(p,'rb').read()).hexdigest()} for p in sys.argv[1:]]))"
    paths=[archive_spec['destination'],script_spec['destination'],contract['contract_destination']]
    readback_command=' '.join([shlex.quote(contract['readback_python']),'-B','-c',shlex.quote(readback_code),*[shlex.quote(p) for p in paths]])
    phase='remote_readback'
    observed=json.loads(run(SSH+[readback_command]))
    expected=[(archive_spec['destination'],archive_spec['bytes'],archive_spec['sha256']),(script_spec['destination'],script_spec['bytes'],script_spec['sha256']),(contract['contract_destination'],contract_path.stat().st_size,sha(contract_path))]
    actual=[(entry['path'],entry['bytes'],entry['sha256']) for entry in observed]
    if actual!=expected: raise ValueError('trusted remote readback mismatch; stage script not executed')
    stage_command=' '.join([shlex.quote(contract['readback_python']),'-B',shlex.quote(script_spec['destination']),'--contract',shlex.quote(contract['contract_destination']),'--archive',shlex.quote(archive_spec['destination']),'--run-root',shlex.quote(contract['run_root'])])
    phase='stage_execution'
    run(SSH+[stage_command])
    phase='verify_stage_receipt'
    receipt_path=contract['run_root']+'/staging-preflight.json'
    receipt=json.loads(run(SSH+['/bin/cat '+shlex.quote(receipt_path)]))
    if receipt.get('status')!='staged_full_packet_readonly_gates_passed_no_runtime' or receipt.get('record')!='DODGE-075' or receipt.get('run_id')!=contract['run_id'] or receipt.get('source_commit',{}).get('commit')!=contract['source_commit'] or receipt.get('registration_sha256')!=contract['registration_sha256'] or receipt.get('archive_sha256')!=archive_spec['sha256'] or receipt.get('stage_script_sha256')!=script_spec['sha256']:
        raise ValueError('remote staging receipt does not match contract')
    return json.dumps(receipt,sort_keys=True)
if __name__=='__main__':
    try:
        print(deliver(sys.argv[1]))
    except BaseException as error:
        packet=Path(sys.argv[1]); failure=packet/'stage-delivery-first-failure.json'
        if owns_claim and not failure.exists():
            with failure.open('x') as stream:
                json.dump({'status':'first_delivery_failure_preserved','phase':phase,'error_class':type(error).__name__},stream);stream.flush();os.fsync(stream.fileno())
            directory=os.open(packet,os.O_RDONLY);os.fsync(directory);os.close(directory)
        raise
