"""Outcome-blind, single-run exception for an absent bytecode cache directory."""
import hashlib
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
ORIGINAL = HERE.parent / 'control-frequency-screen-parent-20261028-r1'
PACKAGE = HERE.parent / 'control-frequency-screen-luna-20261028-r1'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require_absent_cache(path):
    # lexists also rejects dangling symlinks. Never manufacture an empty directory.
    if os.path.lexists(path):
        raise ValueError('Cache exception requires the preserved absent path.')


def validate_review_approval(approval, plan, plan_path):
    sys.path.insert(0, str(PACKAGE))
    import binding as b
    review_path = Path(plan['independent_review_path'])
    b.need(approval['status'] == 'accepted_independent_review_of_outcome_blind_cache_disposition'
           and approval['blocking_findings_remaining'] == 0
           and approval['plan_sha256'] == b.sha(plan_path)
           and approval['reviewer_role'] == 'independent_source_review'
           and approval['review_path'] == str(review_path), 'Repair review acceptance differs.')
    b.need(approval['review_sha256'] == b.sha(review_path)
           and approval['pins'].get(str(review_path)) == b.sha(review_path),
           'Independent review receipt is not hash-bound.')
    review = b.read(review_path)
    b.need(review['status'] == 'no_blocking_findings'
           and review['role'] == 'independent_source_review'
           and review['blocking_findings_remaining'] == 0
           and review['plan_sha256'] == b.sha(plan_path)
           and review['reviewed_pins'] == plan['pins'], 'Independent review scope or verdict differs.')
    b.verify_pins(approval['pins'])


def validate_contract():
    sys.path.insert(0, str(PACKAGE))
    import binding as b
    approval = b.read(HERE / 'parent-review-acceptance.json')
    plan_path = HERE / 'repair-plan.json'
    plan = b.read(plan_path)
    validate_review_approval(approval, plan, plan_path)
    b.verify_pins(plan['pins'])
    b.need(plan['status'] == 'frozen_before_D7_performance_inspection'
           and plan['run_id'] == 'control-frequency-screen-luna-20261028-r1'
           and plan['only_exception'] == 'registered_cache_path_absent'
           and plan['evaluation_rerun'] is False, 'Repair scope differs.')
    incident = b.read(ORIGINAL / 'terminal-audit-incident-r1.json')
    b.verify_pins(incident['pins'])
    b.need(incident['status'] == 'parent_acceptance_blocked_missing_registered_cache_directory'
           and incident['D7_performance_inspected'] is False
           and incident['cache']['lexists'] is False, 'Original incident differs.')
    reg = b.read(PACKAGE / 'registration-final.json')
    cache = Path(reg['import_policy']['pycache_prefix'])
    b.need(str(cache) == incident['cache']['path'], 'Cache path differs.')
    require_absent_cache(cache)
    b.need(sys.dont_write_bytecode is True and sys.pycache_prefix == str(cache),
           'Repair auditor must retain the registered bytecode policy.')
    execution = b.read(PACKAGE / 'parent-execution.json')
    envelope = b.read(PACKAGE / 'launch-envelope.json')
    observation = b.read(Path(envelope['control']) / 'observation.json')
    for command in (execution['command'], observation['command']):
        b.need(command[0] == reg['interpreter'] and command[1] == '-B',
               'Recorded observer or worker did not use the pinned interpreter and -B.')
    # Reconstruct the new auditor from the previously reviewed source and explicit
    # deltas. This rejects unnoticed removal of any original non-cache check.
    delta = b.read(HERE / 'reviewed-delta.json')
    old_path = Path(delta['original_path'])
    b.need(b.sha(old_path) == delta['original_sha256'], 'Original auditor changed.')
    expected = old_path.read_text()
    for change in delta['replacements']:
        b.need(expected.count(change['before']) == 1, 'Ambiguous reviewed source delta.')
        expected = expected.replace(change['before'], change['after'])
    b.need(expected == (HERE / 'accept_saved_screen.py').read_text(),
           'Successor auditor differs from reviewed explicit deltas.')
    return dict(plan_path=str(plan_path), plan_sha256=b.sha(plan_path),
                review_acceptance_sha256=b.sha(HERE / 'parent-review-acceptance.json'),
                original_incident_sha256=b.sha(ORIGINAL / 'terminal-audit-incident-r1.json'),
                exception='Missing cache directory accepted as a disclosed protocol deviation; no cache path created or modified.',
                limitation='Current absence and frozen -B commands establish no cache artifacts at acceptance. They do not prove continuous filesystem absence throughout execution.',
                non_cache_checks='All original checks retained.', evaluation_rerun=False)
