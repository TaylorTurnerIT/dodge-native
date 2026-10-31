"""CLI TEXT entry with durable child status independent of CLI return code."""
import hashlib
import json
import os
from pathlib import Path
import sys


def main():
    root=Path('/content/dodge064');stage=os.environ['DODGE064_STAGE']
    if stage not in ('preflight','build','train'):raise ValueError('Unknown064 stage')
    if os.environ.get('DODGE064_EXECUTION_ADMITTED')!='true':raise ValueError('064 execution admission absent')
    digest=os.environ['DODGE064_REGISTRATION_SHA256'];registration=root/'registration.json'
    if hashlib.sha256(registration.read_bytes()).hexdigest()!=digest:raise ValueError('064 registration differs')
    os.environ['DODGE064_RUN_ROOT']=str(root)
    sys.path.insert(0,str(root/'source'))
    import common as c
    from result_safety.remote_stage import run_stage_child
    from result_safety.custody import canonical,durable_new
    from safety_hooks import preflight_export,terminal_export
    reg=c.load_registration(registration,digest);reg['control_stage']='build' if stage=='preflight' else stage
    c.check_lease(reg)
    def exported():
        if stage=='preflight':return preflight_export(reg)
        if stage=='build':return dict(sha256=c.sha(root/'build-artifacts.tar'),manifest=dict(sequence=0))
        return terminal_export(reg)
    result=run_stage_child([sys.executable,'-B',str(root/'source/remote_entry.py'),
               '--registration',str(registration),'--sha256',digest,'--stage',stage],
               root/'stages'/stage,reg,guard=lambda:c.check_lease(reg),
               seconds=reg['stage_timeout_seconds'][stage],terminal_export=exported,
               failure_export=(lambda:terminal_export(reg,failure=True)) if stage=='train' else None)
    name='stage-exit.json' if stage=='train' else stage+'-exit.json'
    durable_new(root/'exports'/name,canonical(result))
    if result['status']!='complete':
        (root/'cancel.requested').touch(exist_ok=True)
        raise RuntimeError('064 remote '+stage+' failed; durable receipt preserved')


if __name__=='__main__':main()
