"""Stdlib adapters for the accepted worker; no restore or training implementation."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT / 'learning/runs/v2/progressive1000-throughput-runtime-parent-20261027-r2'
SOURCE_SHA = 'e14147338e8da864b1e51c1928124b5103700e22c3ae389e5642bf92c6561f0a'
LIMITS = dict(work_seconds=3780, total_seconds=3790, cleanup_seconds=10,
              rss_bytes=6*1024**3, mps_bytes=6*1024**3,
              raw_frames=64*13 + 983040*(4+13), resets=983040, retries=0)


class Cancelled(RuntimeError):
    pass


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            value.update(block)
    return value.hexdigest()


def read(path):
    def unique(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate JSON field: '+key)
            result[key] = value
        return result
    return json.loads(Path(path).read_bytes(), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def save(path, value):
    """Publish complete durable JSON atomically, without replacing a first receipt.

    A same-directory hard link is the exclusive commit point. Readers never see
    the staging inode until its entire contents have been flushed and fsynced.
    An interrupted staging file is not a committed receipt.
    """
    path = Path(path)
    fd, staging = tempfile.mkstemp(prefix='.'+path.name+'.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.link(staging, path)  # Atomic O_EXCL-equivalent publication; no replace.
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.unlink(staging)


def contracts():
    # Authenticate executable source before importing even its stdlib definitions.
    need(sha(SOURCE/'source-manifest.json') == SOURCE_SHA, 'accepted source manifest differs')
    for rel, digest in read(SOURCE/'source-manifest.json')['files'].items():
        path = SOURCE/rel
        need(path.resolve().is_relative_to(SOURCE) and not path.is_symlink(), 'source path escapes')
        need(sha(path) == digest, 'accepted source differs: '+rel)
    sys.path.insert(0, str(SOURCE))
    import contracts as c
    need(Path(c.__file__).resolve() == SOURCE/'contracts.py', 'contracts import origin differs')
    return c


def load_envelope(path, digest):
    need(sha(path) == digest, 'envelope external SHA differs')
    value = read(path)
    need(set(value) == {'schema','status','registration','registration_sha256','launch_approval',
         'launch_approval_sha256','source_acceptance','source_acceptance_sha256','control',
         'cancel_path','started','pins','interpreter_resolved','interpreter_sha256'}, 'envelope fields differ')
    need(value['schema'] == 'progressive1000_existing_supervisor_envelope_v1'
         and value['status'] == 'parent_bound_exactly_one_run', 'inert envelope has no launch authority')
    need(type(value['started']) in (int,float) and math.isfinite(value['started']), 'start must be finite')
    control = Path(value['control'])
    need(control.is_absolute() and control.resolve().is_relative_to(HERE/'dispatch'), 'control must be owned dispatch path')
    for name in ('registration','launch_approval','source_acceptance','cancel_path'):
        need(Path(value[name]).is_absolute(), 'absolute envelope path required: '+name)
    required = {str(HERE/name) for name in ('binding.py','terminal.py','execute_once.py','observe.py','dependency-binding.json')}
    need(required <= set(value['pins']), 'supervisor code pins missing')
    check_pins(value)
    reg = read(value['registration'])
    need(control == HERE/'dispatch'/reg['run_id'], 'one fixed dispatch directory per registered run required')
    need(reg['limits'] == LIMITS and LIMITS['raw_frames'] == 16712512, 'inherited bounds differ')
    out = Path(reg['output']).resolve()
    need(not control.resolve().is_relative_to(out) and not out.is_relative_to(control.resolve()), 'control/output overlap')
    need(not Path(value['cancel_path']).resolve().is_relative_to(out), 'cancel path inside worker output')
    return value, reg


def check_pins(envelope):
    for path, digest in envelope['pins'].items():
        need(sha(path) == digest, 'envelope pin drift: '+path)
    need(sha(envelope['registration']) == envelope['registration_sha256'], 'registration drift')
    need(sha(envelope['launch_approval']) == envelope['launch_approval_sha256'], 'launch approval drift')
    need(sha(envelope['source_acceptance']) == envelope['source_acceptance_sha256'], 'source acceptance drift')


def check_lease(reg):
    state = read(reg['state_path'])
    need(state.get('active_long_campaign') == reg['expected_lease'], 'parent lease changed')
    need(all(state.get(k) is None for k in ('active_inference_campaign','active_inference_diagnostic',
                                          'active_inference_lease')), 'conflicting inference lease')


def verify_dependencies(reg):
    """Reuse the proven launcher's installed Torch/NumPy inventory, hash only."""
    binding = read(HERE/'dependency-binding.json')
    need(sha(binding['registration_path']) == binding['registration_sha256']
         and sha(binding['inventory_path']) == binding['inventory_sha256'], 'historical dependency anchor drift')
    old = read(binding['registration_path']); inventory = read(binding['inventory_path'])
    need(reg['interpreter'] == old['interpreter'], 'dependency interpreter origin differs')
    for path, item in inventory['pins'].items():
        need(old['pins'].get(path) == item['sha256'] == sha(path), 'installed dependency pin drift: '+path)
    need(sha(Path(reg['interpreter']).resolve(strict=True)) == old['pins'][str(Path(reg['interpreter']).resolve(strict=True))],
         'resolved interpreter differs from historical pin')
    return dict(checked=len(inventory['pins']),scope=inventory['scope'])


def verify_bound(envelope, reg, *, preflight):
    c = contracts()
    check_pins(envelope)
    accepted = read(envelope['source_acceptance'])
    need(accepted['schema'] == 'parent_progressive1000_shared_source_acceptance_v1'
         and accepted['source_path'] == str(SOURCE)
         and accepted['source_manifest_sha256'] == reg['source_manifest_sha256'] == SOURCE_SHA
         and accepted['runtime_manifest_sha256'] == reg['runtime_manifest_sha256'], 'source acceptance binding differs')
    need(reg['limits'] == LIMITS, 'inherited limits differ')
    check_lease(reg)
    need(not os.path.lexists(envelope['cancel_path']), 'parent cancel marker present')
    need(str(Path(reg['interpreter']).resolve(strict=True)) == envelope['interpreter_resolved']
         and sha(envelope['interpreter_resolved']) == envelope['interpreter_sha256'], 'interpreter pin differs')
    verify_dependencies(reg)
    if preflight:
        c.preflight(envelope['registration'], envelope['registration_sha256'],
                    envelope['launch_approval'], envelope['launch_approval_sha256'], envelope['started'])
    else:
        # validate_static intentionally rejects spent output/claim. Recheck its
        # immutable inputs directly after exit, without pretending they are absent.
        c.verify_inputs()
        c.verify_manifest(SOURCE/'source-manifest.json', reg['source_manifest_sha256'], SOURCE)
        c.verify_manifest(SOURCE/'runtime-manifest.json', reg['runtime_manifest_sha256'], SOURCE/'runtime', exact=True)
        need(c.sha(SOURCE/'input-manifest.json') == reg['input_manifest_sha256'], 'input manifest drift')
        for path, digest in ((reg['reference']['receipt_path'],reg['reference']['receipt_sha256']),
                             (reg['reference_approval']['path'],reg['reference_approval']['sha256']),
                             (ROOT/c.PARENT_RECEIPT,reg['parent_receipt_sha256'])):
            need(sha(path) == digest, 'external input drift: '+str(path))
        parent = read(ROOT/c.PARENT_RECEIPT)
        need(sha(parent['checkpoint_path']) == reg['parent_checkpoint_sha256'], 'parent checkpoint byte drift')
        need(read(reg['launch_marker_path']) == dict(schema='progressive1000_parent_spent_launch_marker_v1',
             registration_sha256=envelope['registration_sha256'],run_id=reg['run_id'],started=envelope['started']), 'parent marker drift')
        c.cache_check(reg)
    check_pins(envelope)


def worker_command(envelope, reg):
    return [reg['interpreter'], '-B', str(SOURCE/'worker_cli.py'),
            '--registration', envelope['registration'], '--registration-sha256', envelope['registration_sha256'],
            '--source-acceptance', envelope['launch_approval'],
            '--source-acceptance-sha256', envelope['launch_approval_sha256'], '--started', repr(envelope['started'])]


def worker_resources(out, *, strict=False):
    """Read only complete sampled lines; new worker uses rss_bytes, not peak_rss_bytes."""
    path = Path(out)/'resources.jsonl'
    result = dict(samples=0, peak_rss_bytes=None, peak_mps_driver_bytes=None)
    if not path.is_file():
        return result
    for line in path.read_text().splitlines(keepends=True):
        if not line.endswith('\n'):
            need(not strict, 'torn terminal resource journal')
            break
        row = json.loads(line)
        need(all(type(row[k]) is int and row[k] >= 0 for k in ('rss_bytes','mps_driver_bytes')), 'invalid resource sample')
        result['samples'] += 1
        result['peak_rss_bytes'] = max(result['peak_rss_bytes'] or 0, row['rss_bytes'])
        result['peak_mps_driver_bytes'] = max(result['peak_mps_driver_bytes'] or 0, row['mps_driver_bytes'])
    return result
