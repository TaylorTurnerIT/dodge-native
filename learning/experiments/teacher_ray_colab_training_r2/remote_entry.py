"""Reviewed parent's remote serial entry point; no allocation or global ledger."""
import argparse
import os
from pathlib import Path
import sys
import time

import common as c
from native_build import build_runtime
from receipts import write_stage, write_archive, decode_archive
from supervisor import supervise


def run_campaign(reg, registration_path, digest, *, supervisor=supervise):
    artifacts = c.HERE/'artifacts'
    started = time.monotonic(); reg['campaign_started_monotonic'] = started
    c.save(artifacts/'campaign.claimed',dict(record='DODGE-062',job_nonce=reg['job_nonce']))
    results=[];failure=None
    def guard():
        c.check_lease(reg)
        c.need(time.monotonic()-started<reg['campaign_total_seconds'],'Remote training campaign cap')
    try:
        for job in reg['jobs']:
            guard()
            out=artifacts/'outputs'/job['id']
            command=[sys.executable,'-B',str(Path(__file__).with_name('worker.py')),
                     '--registration',str(registration_path),'--sha256',digest,'--job',job['id']]
            result=supervisor(command,out,reg,job,check_control=guard)
            results.append(result)
            c.need(result['status']=='complete','Serial job failed; later jobs stay unopened')
        frames=sum(result['training_frames'] for result in results)
        c.need(frames==reg['total_actual_frames'],'Campaign actual-frame target differs')
        body=write_stage(artifacts/'campaign-result.json',reg,'campaign','complete',
            native_games=sum(result['native_games'] for result in results),training_frames=frames,
            trained_weights_saved=any(result['trained_weights_saved'] for result in results),
            job_order=[job['id'] for job in reg['jobs']],elapsed_seconds=time.monotonic()-started,
            no_resume=True,promotion=False,evaluation_games=0)
    except BaseException as error:
        failure=repr(error)
        body=write_stage(artifacts/'campaign-first-failure.json',reg,'campaign','failed',
            native_games=None,training_frames=None,
            trained_weights_saved=any('.pt' in path.name for path in artifacts.rglob('*') if path.is_file()),
            completed_job_reports=results,error=failure,elapsed_seconds=time.monotonic()-started)
    archive=write_archive(artifacts,c.HERE/'training-artifacts.tar',reg)
    # Decode the producer's REAL archive before reporting readiness to retrieve.
    decoded=decode_archive(archive['path'],archive['sha256'],reg,require_complete=failure is None)
    return dict(status=body['status'],archive=archive,decoded=decoded,error=failure)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--registration',required=True);parser.add_argument('--sha256',required=True)
    parser.add_argument('--stage',choices=('build','train'),required=True)
    args=parser.parse_args();reg=c.load_registration(args.registration,args.sha256)
    reg['control_stage']=args.stage;c.check_lease(reg)
    if args.stage=='build':
        c.need(c.read(c.HERE/'control.json')['allowed_stage']=='build','Build-stage control absent')
        error=None
        try:build_runtime(reg)
        except BaseException as failure:error=failure
        archive=write_archive(c.HERE/'artifacts',c.HERE/'build-artifacts.tar',reg)
        print(c.canonical(dict(status='native_build_ready_constructor_unopened' if error is None else 'native_build_failed',
            archive=archive,certificate_path=str(c.HERE/'artifacts/native-build.json'),
            certificate_sha256=c.sha(c.HERE/'artifacts/native-build.json') if error is None else None)).decode(),flush=True)
        if error is not None:raise error
    else:
        # Parent separately inspects/pins the build/runtime certificate before
        # this train command. No auto-chain from a successful compilation.
        from native_build import verify_certificate
        cert=verify_certificate(reg)
        admission=c.read(c.HERE/'runtime-admission.json');control=c.read(c.HERE/'control.json')
        for key in ('record','job_nonce','registration_sha256','expected_lease_sha256'):
            c.need(admission.get(key)==reg[key],'Runtime-admission identity differs')
        c.need(control['allowed_stage']=='train' and control['runtime_admission_sha256']==c.sha(c.HERE/'runtime-admission.json')
               and admission['accepted_build_certificate_sha256']==c.sha(c.HERE/'artifacts/native-build.json'),
               'Parent accepted build certificate binding absent/different')
        result=run_campaign(reg,args.registration,args.sha256)
        print(c.canonical(result).decode(),flush=True)
        if result['status']!='complete':raise SystemExit(1)


if __name__=='__main__':main()
