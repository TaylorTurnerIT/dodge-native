"""Publish concrete parent launch gates only after the independent reviews have been accepted."""
from pathlib import Path
import json
import sys

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent / 'uniform2-continuation600-luna-20261028-r2'
sys.path.insert(0, str(PACKAGE))
import binding as b
import finalize_registration
import launch


def main():
    review_path = HERE / 'parent-review-acceptance.json'
    reviews = b.read(review_path)
    b.need(reviews['status'] == 'accepted_independent_reviews_by_parent'
           and len(reviews['reviewers']) == 2 and reviews['blocking_findings_remaining'] == 0,
           'two accepted independent reviews required')
    b.check_pins(reviews['pins'])
    source_sha = b.sha(PACKAGE / 'source-manifest.json')
    b.need(source_sha == reviews['source_manifest_sha256'], 'accepted review source changed')
    draft_path = PACKAGE / 'registration-draft.json'
    b.need(b.sha(draft_path) == reviews['registration_draft_sha256'], 'reviewed draft changed')
    draft = b.read(draft_path)
    b.validate_static(draft, require_registered=False, streams=True, startup=True)
    launch.main_state_free(draft)
    checks = b.read(HERE / 'parent-checks.json')
    runtime = b.read(HERE / 'runtime-qualification.json')
    b.need(checks['source_manifest_sha256'] == source_sha
           and checks['segmented_environment_scope_accepted'] is True
           and checks['battery_override_accepted'] is True
           and checks['calibration_accepted'] is True,
           'parent scope/calibration checks differ')
    b.need(runtime['status'] == 'passed_actual_runtime_restore_native_constructor_and_scratch_isolation'
           and runtime['source_manifest_sha256'] == source_sha,
           'actual runtime qualification missing or source changed')
    source_acceptance = PACKAGE / 'source-acceptance.json'
    b.save(source_acceptance, b.source_acceptance_document(source_sha))
    calibration = HERE / 'calibration-acceptance.json'
    b.save(calibration, dict(status='accepted_parent_resource_calibration',
        registration_draft_sha256=b.sha(draft_path), limits=draft['limits'],
        measured_basis=draft['calibration'],
        native_qualification_sha256=b.sha(HERE / 'runtime-qualification.json'),
        accepted_scope='600 updates, eleven full-run D6 evaluations, ten fresh-environment segments; user-authorized battery execution.',
        limitations='No fresh PPO throughput measurement. Observed prior training and evaluation costs estimate time; hard limits stay enforced.'))
    final = finalize_registration.finalize(draft_path, b.sha(draft_path), calibration, b.sha(calibration))
    b.validate_static(final, streams=True, startup=True)
    final_path = PACKAGE / 'registration-final.json'
    b.save(final_path, final)
    gate_files = [review_path, HERE / 'parent-checks.json', HERE / 'runtime-qualification.json',
                  HERE / 'runtime-qualification-registration.json', HERE / 'qualify_runtime.py',
                  b.PARENT / 'restore-qualification.json', b.PARENT / 'user-authorization.json',
                  b.PARENT / 'battery-power-override.json', b.PARENT / 'development-cohort-reservation.json',
                  HERE / 'audit_segment_streams.py', Path(__file__).resolve(),
                  calibration, source_acceptance, final_path]
    pins = {str(path): b.sha(path) for path in gate_files}
    pins.update(reviews['pins'])
    gate_path = PACKAGE / 'gate-acceptance.json'
    b.save(gate_path, b.approval_document(b.sha(final_path), source_sha, pins))
    b.save(HERE / 'authorization-ready.json', dict(
        status='parent_gates_accepted_ready_for_exactly_one_native_launch',
        registration_path=str(final_path), registration_sha256=b.sha(final_path),
        gate_path=str(gate_path), gate_sha256=b.sha(gate_path),
        source_acceptance_path=str(source_acceptance), source_acceptance_sha256=b.sha(source_acceptance),
        main_lease_installed=False, attempt_marker_consumed=False, training_launched=False,
        terminal_order=['Observe successful directly-reaped raw exit and absence of owned process groups.',
                        'Run parent audit_segment_streams.py before any lease release.',
                        'Run package audit.py to recompute accounting and selection and clear only its exact lease.',
                        'Publish source and compact evidence; keep weights local.']))
    print(json.dumps(b.read(HERE / 'authorization-ready.json')))


if __name__ == '__main__':
    main()
