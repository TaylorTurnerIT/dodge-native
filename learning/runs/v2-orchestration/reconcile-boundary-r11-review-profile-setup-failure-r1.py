"""Reconcile completed evidence without importing or executing the candidate."""
from pathlib import Path
import datetime
import hashlib
import json
import os

ROOT = Path(__file__).resolve().parents[3]
ORCH = ROOT / 'learning/runs/v2-orchestration'
REVIEW = ROOT / 'learning/runs/v2/postovernight-long-D2-boundary-review-r11'
PROFILE = ROOT / 'learning/runs/v2/postovernight-long-D2-boundary-profile-r1'
CANDIDATE = ROOT / 'learning/runs/v2/postovernight-long-D2-boundary-prepare-r11'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def inventory(base, entries):
    for name, value in entries.items():
        path = base / name
        digest = value if isinstance(value, str) else value['sha256']
        assert sha(path) == digest, str(path)
        if isinstance(value, dict) and 'bytes' in value:
            assert path.stat().st_size == value['bytes'], str(path)
    return len(entries)


def main():
    state = read(ORCH / 'state.json')
    task = state['tasks']['postovernight_long_D2_boundary_review_r11']
    assert not task['result_ingested'], 'Review already ingested'
    assert state['active_long_campaign'] is None
    assert not state['post_overnight_long_D2_r2']['single_use_consumed']
    at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    pins = read(CANDIDATE / 'parent-frozen-pins.json')
    pin_count = inventory(ROOT, pins)
    inputs = inventory(ROOT, read(REVIEW / 'input-manifest.json')['files'])
    outputs = inventory(REVIEW, read(REVIEW / 'output-manifest.json')['files'])
    receipt = read(REVIEW / 'review-receipt.json')
    assert receipt['verdict'] == 'no_findings' and receipt['findings'] == 0
    assert receipt['proof_raw_exits'] == [0, 0, 0]
    assert receipt['static_raw_exit'] == 0
    for name, key in [('audit.md', 'audit_sha256'), ('findings.json', 'findings_sha256'),
                      ('input-manifest.json', 'input_manifest_sha256'),
                      ('end-verification.json', 'end_verification_sha256')]:
        assert sha(REVIEW / name) == receipt[key]
    profile_plan = read(PROFILE / 'plan.json')
    inventory(PROFILE, profile_plan['scripts_sha256'])
    assert profile_plan['frozen_candidate_pins'] == pins
    command = read(PROFILE / 'command.json')
    assert command['scripts_sha256'] == profile_plan['scripts_sha256']
    wrapper = read(PROFILE / 'wrapper-result.json')
    result = read(PROFILE / 'output/result.json')
    assert wrapper['returncode'] == 0 and wrapper['retries'] == 0
    assert wrapper['direct_child_reaped'] and wrapper['group_absent']
    assert wrapper['one_script_invocation'] and not wrapper['guardian_fired']
    assert wrapper['elapsed_seconds'] < 60
    assert result['status'] == 'completed_diagnostic_not_validation'
    assert result['contender_absent'] and result['sampler_absent']
    assert not result['forbidden_modules']
    boundaries = result['boundaries']
    assert len(boundaries) == 2
    assert all(row['verdict'] == 'passed' and row['bytes'] == 47527648
               and row['files'] == 273 for row in boundaries)
    json_count = 0
    for base in (REVIEW, PROFILE):
        for path in base.rglob('*.json'):
            read(path)
            json_count += 1
    review_assessment = dict(
        schema='parent_frozen_r11_review_reconciliation_v1', reconciled_at_utc=at,
        task_id=task['task_id'], task_status='completed', workState='result_available',
        has_pending_child_runs=False, terminal_summary='No findings',
        verdict='accepted_source_and_synthetic_review_only',
        frozen_pins_rehashed=pin_count, immutable_review_inputs_rehashed=inputs,
        review_outputs_rehashed=outputs,
        receipt_sha256=sha(REVIEW / 'review-receipt.json'),
        limitations=receipt['limitations'],
        foundation_validation_passed=False,
        reason='The separate first r11 contention stress failed at its unchanged 120-second wall cap.')
    review_path = ORCH / 'postovernight-long-D2-boundary-review-r11-parent-reconciliation.json'
    save(review_path, review_assessment)
    profile_assessment = dict(
        schema='parent_one_boundary_profile_assessment_v1', reconciled_at_utc=at,
        status='accepted_diagnostic_only_not_foundation_validation',
        frozen_pins_rehashed=pin_count, profile_scripts_rehashed=2,
        raw_exit=wrapper['returncode'], wall_seconds=wrapper['elapsed_seconds'],
        one_invocation=True, retries=0, direct_child_reaped=True,
        group_absent=True, contender_absent=True, sampler_absent=True,
        boundary_measurements=[{key: row[key] for key in
            ('sequence', 'duration_seconds', 'thread_cpu_seconds', 'bytes', 'files', 'verdict')}
            for row in boundaries],
        conclusions=[
            'The contended pass spent most elapsed time off the calling thread CPU.',
            'The profile does not uniquely separate GIL handoff, storage, scheduler, or profiler overhead.',
            'SHA/open/read costs are larger than project_members in cumulative profile entries; the prior project-members-dominance hypothesis is unsupported.',
            'Overlapping cumulative entries must not be summed; threading.wait attribution exceeds the measured boundary.',
            'The actual Guard and integrity.verify ran without source monkeypatching; the callback did not run production legacy/runtime/origin checks.',
            'Both boundaries read the same 47,527,648 bytes in 273 hash calls; no R/A endpoint campaign ran.'
        ],
        limitations=result['limitations'] + [
            'No benchmark, speedup, reliability, MPS, native-runtime, startup or training claim.',
            'The prior failed stress remains failed; no unchanged-source retry is authorized by this diagnostic.'
        ],
        observed_RSS_bytes=result['resources']['maximum_rss_bytes'],
        maximum_sample_gap_seconds=result['resources']['maximum_sample_gap_seconds'],
        MPS_driver_observed=False, startup_rehearsal_launched=False,
        training_launched=False, JSON_files_parsed=json_count)
    save(PROFILE / 'parent-assessment.json', profile_assessment)
    manifest = {str(path.relative_to(PROFILE)): dict(sha256=sha(path), bytes=path.stat().st_size)
                for path in sorted(PROFILE.rglob('*')) if path.is_file()}
    save(PROFILE / 'parent-evidence-manifest.json', dict(files=manifest, excludes_itself=True,
                                                      logs_closed=True))
    task.update(status='completed', workState='result_available', result_ingested=True,
                ingested_at_utc=at, verdict='No findings',
                parent_reconciliation=str(review_path.relative_to(ROOT)))
    run = state['post_overnight_long_D2_r2']
    run.update(status='r11_review_accepted_source_only;stress_failed;profile_complete;next_design_pending',
               boundary_review_r11_parent_reconciliation=str(review_path.relative_to(ROOT)),
               boundary_review_r11_parent_reconciliation_sha256=sha(review_path),
               profile_status='completed_diagnostic_only',
               profile_parent_assessment=str((PROFILE / 'parent-assessment.json').relative_to(ROOT)),
               profile_parent_assessment_sha256=sha(PROFILE / 'parent-assessment.json'))
    state.update(status='postovernight_long_D2_r2_r11_reconciled;contention_design_pending;no_active_training',
                 last_update_at_utc=at,
                 next_actions=[
                     'Obtain a targeted Sonnet contention diagnosis/design from reconciled r11 profile evidence.',
                     'Preserve frozen r11 source and failed stress; use a distinct reviewed candidate for any repair.',
                     'Startup rehearsal and unused one-shot training remain held until required validation passes.'
                 ])
    pending = ORCH / '.state-r11-review-profile.pending.json'
    save(pending, state)
    read(pending)
    os.replace(pending, ORCH / 'state.json')
    print(json.dumps(dict(review=review_assessment, profile=profile_assessment), indent=2))


if __name__ == '__main__':
    main()
