"""Trusted SSH delivery; require remote byte readback before stage execution."""
import hashlib, json, shlex, subprocess, sys
from pathlib import Path
SSH=['/usr/bin/ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','macbook-1']
SCP=['/usr/bin/scp','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12']
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def run(args): return subprocess.run(args,text=True,capture_output=True,check=True).stdout.strip()
def deliver(packet):
    packet=Path(packet);contract_path=packet/'staging-contract.json';contract=json.loads(contract_path.read_text())
    archive_spec=contract['archive'];script_spec=contract['script']
    archive=packet/archive_spec['local_filename'];script=packet/script_spec['local_filename']
    if archive.name!=archive_spec['local_filename'] or archive.stat().st_size!=archive_spec['bytes'] or sha(archive)!=archive_spec['sha256']:
        raise ValueError('local archive contract mismatch')
    if script.stat().st_size!=script_spec['bytes'] or sha(script)!=script_spec['sha256']:
        raise ValueError('local stage script contract mismatch')
    run(SCP+[str(archive),'macbook-1:'+archive_spec['destination']])
    run(SCP+[str(script),'macbook-1:'+script_spec['destination']])
    run(SCP+[str(contract_path),'macbook-1:'+contract['contract_destination']])
    # This remote command reads metadata only. It does not execute packet code.
    readback_code="import hashlib,json,os,sys; print(json.dumps([{'path':p,'bytes':os.path.getsize(p),'sha256':hashlib.sha256(open(p,'rb').read()).hexdigest()} for p in sys.argv[1:]]))"
    paths=[archive_spec['destination'],script_spec['destination'],contract['contract_destination']]
    readback_command=' '.join([shlex.quote(contract['readback_python']),'-B','-c',shlex.quote(readback_code),*[shlex.quote(p) for p in paths]])
    observed=json.loads(run(SSH+[readback_command]))
    expected=[(archive_spec['destination'],archive_spec['bytes'],archive_spec['sha256']),(script_spec['destination'],script_spec['bytes'],script_spec['sha256']),(contract['contract_destination'],contract_path.stat().st_size,sha(contract_path))]
    actual=[(entry['path'],entry['bytes'],entry['sha256']) for entry in observed]
    if actual!=expected: raise ValueError('trusted remote readback mismatch; stage script not executed')
    stage_command=' '.join([shlex.quote(contract['readback_python']),'-B',shlex.quote(script_spec['destination']),'--contract',shlex.quote(contract['contract_destination']),'--archive',shlex.quote(archive_spec['destination']),'--run-root',shlex.quote(contract['run_root'])])
    return run(SSH+[stage_command])
if __name__=='__main__': print(deliver(sys.argv[1]))
