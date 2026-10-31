"""Pinned Colab CLI TEXT cell: run the real argparse entry in a fresh process.

CLI exec does not forward argv. Parent supplies registered environment values;
its control renewal/financial/global-lease checks run outside this blocking cell.
"""
import json
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys


def main():
    root=Path('/content/dodge062')
    registration=root/'registration.json'
    stage=os.environ['DODGE062_STAGE']
    if stage not in ('build','train'):raise ValueError('Unknown058 stage')
    if os.environ.get('DODGE062_EXECUTION_ADMITTED')!='true':raise ValueError('Parent058 admission absent')
    digest=os.environ['DODGE062_REGISTRATION_SHA256']
    if hashlib.sha256(registration.read_bytes()).hexdigest()!=digest:raise ValueError('058 registration digest differs')
    reg=json.loads(registration.read_text())
    timeout=reg['stage_timeout_seconds'][stage]
    command=[sys.executable,'-B',str(root/'source/remote_entry.py'),
             '--registration',str(registration),'--sha256',digest,'--stage',stage]
    child=subprocess.Popen(command,start_new_session=True,env=dict(os.environ,DODGE062_RUN_ROOT=str(root),PYTHONDONTWRITEBYTECODE='1'))
    try:
        code=child.wait(timeout=timeout)
    except BaseException:
        # Cancellation is persistent; reconnects must not erase it or rerun.
        (root/'cancel.requested').touch(exist_ok=True)
        try:os.killpg(child.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        try:child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
        raise
    if code:raise RuntimeError('058 '+stage+' child failed with exit '+str(code))


if __name__=='__main__':main()
