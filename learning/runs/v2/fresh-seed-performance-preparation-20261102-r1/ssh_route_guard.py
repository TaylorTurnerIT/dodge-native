"""Verify the registered SSH host route before creating any attempt claim."""
import hashlib
import json
import os
from pathlib import Path
import subprocess


def inspect_context(binding, *, environ=None, run=None, identity=None):
    environ=os.environ if environ is None else environ
    run=subprocess.run if run is None else run
    identity=dict(pid=os.getpid(),ppid=os.getppid(),pgid=os.getpgrp(),uid=os.getuid(),euid=os.geteuid()) if identity is None else identity
    connection=environ.get('SSH_CONNECTION','').split()
    if len(connection)!=4:
        raise ValueError('Registered SSH host session required before any attempt claim')
    client,client_port,server,server_port=connection
    if not (client==binding['required_client_ip'] and server==binding['required_server_ip']
            and int(server_port)==binding['required_server_port'] and 0<int(client_port)<65536):
        raise ValueError('Actual SSH route differs from registered preflight route')
    if identity['uid']!=binding['required_uid'] or identity['euid']!=binding['required_euid']:
        raise ValueError('Actual SSH host user identity differs')
    result=run(['/bin/ps','-axo','pid=,ppid=,pgid=,rss='],text=True,capture_output=True,check=True)
    rows=[line.split() for line in result.stdout.splitlines()]
    rows=[row for row in rows if len(row)==4 and int(row[0])==identity['pid']]
    if len(rows)!=1:
        raise ValueError('Actual host process inspection did not find this caller')
    pid,ppid,pgid,rss=map(int,rows[0])
    if (pid,ppid,pgid)!=(identity['pid'],identity['ppid'],identity['pgid']) or rss<0:
        raise ValueError('Actual host process identity/resource observation differs')
    return dict(**identity,SSH_CONNECTION=' '.join(connection),ps_exit_code=result.returncode,
                self_RSS_bytes=rss*1024,route='M4 task -> trusted SSH -> M1 host Python')


def verify_preflight(binding):
    path=Path(binding['preflight_receipt'])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=binding['preflight_receipt_sha256']:
        raise ValueError('Registered host preflight receipt changed')
    receipt=json.loads(path.read_bytes())
    if not (receipt['status']=='passed_actual_SSH_host_context_nontraining_preflight'
            and receipt['context']['global_ps_exit']==0 and receipt['child_exit']['directly_reaped']
            and receipt['child_exit']['group_absent'] and receipt['child_exit']['raw_exit_code']==0
            and receipt['child_exit']['observed_exit_code']==0
            and receipt['ledger_written'] is False and receipt['lease_operations']==0):
        raise ValueError('Required host process/lifecycle preflight proof missing')
    return dict(preflight_receipt_sha256=binding['preflight_receipt_sha256'],**inspect_context(binding))
