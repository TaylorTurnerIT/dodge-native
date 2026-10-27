"""Future worker CLI. No process launched during source preparation."""
from __future__ import annotations
import argparse
import math
import time

import contracts as c
import worker


def validate(path, digest, acceptance_path, acceptance_sha, started):
    c.need(c.sha(path) == digest, 'external registration SHA differs')
    reg = c.read(path)
    context = c.verify_registration(reg)
    c.need(c.sha(acceptance_path) == acceptance_sha, 'external source acceptance SHA differs')
    acceptance = c.read(acceptance_path)
    c.need(acceptance == dict(schema='paired_worker_parent_source_acceptance_v2',status='accepted_for_one_registered_worker',
        registration_sha256=digest,source_manifest_sha256=reg['source_manifest_sha256'],run_id=reg['run_id']), 'exact parent source acceptance required')
    c.need(math.isfinite(started) and 0 <= time.monotonic()-started < reg['limits']['work_seconds'], 'inherited launcher start differs')
    marker = c.read(reg['launch_marker_path'])
    c.need(marker == dict(schema='paired_worker_parent_launch_marker_v2',run_id=reg['run_id'],registration_sha256=digest,started=started), 'parent-spent launch marker differs')
    worker.cache_check(reg)
    c.need(c.sha(path) == digest and c.sha(acceptance_path) == acceptance_sha, 'parent gates changed during validation')
    return reg,context


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registration',required=True)
    parser.add_argument('--registration-sha256',required=True)
    parser.add_argument('--source-acceptance',required=True)
    parser.add_argument('--source-acceptance-sha256',required=True)
    parser.add_argument('--started',required=True,type=float)
    parser.add_argument('--validate-only',action='store_true')
    args = parser.parse_args()
    reg, context = validate(args.registration,args.registration_sha256,args.source_acceptance,args.source_acceptance_sha256,args.started)
    if args.validate_only:
        return 0
    return worker.execute(reg,context,args.registration_sha256,args.started)


if __name__ == '__main__':
    raise SystemExit(main())
