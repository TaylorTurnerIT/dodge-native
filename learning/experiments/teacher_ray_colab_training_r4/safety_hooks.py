"""Remote durability barriers. No allocator, global ledger or extra model step."""
import json
import time
from pathlib import Path

import common as c
from result_safety import custody
from result_safety.lifecycle import CheckpointGate, schedule


def publisher(reg):
    return custody.Publisher(c.HERE/'exports',reg)


def preflight_export(reg):
    p=c.HERE/'exports/manifests/000001.json'
    return dict(sha256=c.sha(p),manifest=c.read(p))


def preflight(reg):
    c.need(not (c.HERE/'roundtrip.bin').exists(),'Storage rehearsal already consumed')
    chunks=reg['storage_challenge']['chunks']
    c.need(len(chunks)==32 and len({x['sha256'] for x in chunks})==32,'Random full-size challenge required')
    with (c.HERE/'roundtrip.bin').open('xb') as out:
        for item in chunks:
            c.check_lease(reg)
            path=Path(item['remote']);data=path.read_bytes()
            c.need(len(data)==1048576 and custody.digest(data)==item['sha256'],'Challenge chunk differs')
            out.write(data)
        out.flush();__import__('os').fsync(out.fileno())
    c.need(c.sha(c.HERE/'roundtrip.bin')==reg['storage_challenge']['sha256'],'Challenge reconstruction differs')
    gate=CheckpointGate(publisher(reg),tuple(x['id'] for x in reg['jobs']),
                        guard=lambda:c.check_lease(reg),ack_seconds=reg['result_safety']['checkpoint_ack_seconds'])
    gate.preflight(c.HERE/'roundtrip.bin')


def checkpoint_factory(reg,actual_factory):
    gate=CheckpointGate(publisher(reg),tuple(x['id'] for x in reg['jobs']),
                        guard=lambda:c.check_lease(reg),ack_seconds=reg['result_safety']['checkpoint_ack_seconds'])
    return gate.wrap_factory(actual_factory,preflight_export(reg))


def completed_job_backup(reg,job,out,began,campaign_guard):
    def guard():
        campaign_guard()
        c.need(time.monotonic()-began<reg['work_seconds']+reg['receipt_seconds'],
               'Job receipt/backup deadline exceeded')
    guard()
    files={p.name:p for p in Path(out).iterdir() if p.is_file()}
    c.need(not any('.partial' in name or 'failure' in name for name in files),'Failed job cannot open successor')
    gate=CheckpointGate(publisher(reg),tuple(x['id'] for x in reg['jobs']),guard=guard,
                        ack_seconds=reg['result_safety']['job_ack_seconds'])
    gate.job_complete(job['id'],files)
    guard()
    c.save(Path(out)/'job-backup-complete.json',dict(status='backup_acknowledged_before_next_job',
           job=job['id'],elapsed_including_backup_seconds=time.monotonic()-began,
           registration_sha256=reg['registration_sha256'],job_nonce=reg['job_nonce']))


def terminal_export(reg,*,failure=False):
    path=c.HERE/'training-artifacts.tar'
    c.need(path.is_file(),'Remote training archive absent')
    seq=900000 if failure else len(schedule(tuple(x['id'] for x in reg['jobs']),(12,24,36)))
    return publisher(reg).publish(seq,'terminal',{'training-artifacts.tar':path})
