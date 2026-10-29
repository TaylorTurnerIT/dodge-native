"""Publish concrete source/runtime/calibration launch gates after independently reviewed preparation."""
from pathlib import Path
import os
import sys

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent / 'control-frequency-confirmation-luna-20261029-r1'
sys.path.insert(0, str(PACKAGE))
import binding as b
import finalize_registration
import launch


def main():
    draft_path = PACKAGE / 'registration-draft.json'
    draft = b.read(draft_path)
    source_sha = b.sha(PACKAGE / 'source-manifest.json')
    reviews_path = HERE / 'parent-review-acceptance.json'
    reviews = b.read(reviews_path)
    b.need(reviews['status'] == 'accepted_independent_reviews_by_parent'
           and len(reviews['reviewers']) == 2 and reviews['blocking_findings_remaining'] == 0
           and reviews['source_manifest_sha256'] == source_sha
           and reviews['registration_draft_sha256'] == b.sha(draft_path), 'Independent source reviews differ.')
    b.verify_pins(reviews['pins'])
    qpath = HERE / 'actual-runtime-qualification.json'
    qreg_path = HERE / 'actual-runtime-qualification-registration.json'
    qsource = HERE / 'qualify_startup.py'
    q = b.read(qpath)
    b.need(q['status'] == 'passed_actual_worker_model_native_and_four_collector_conditions'
           and q['source_manifest_sha256'] == source_sha
           and q['runtime_manifest_sha256'] == draft['runtime_manifest_sha256']
           and q['model_fingerprint'] == draft['model_fingerprint']
           and q['registration_sha256'] == b.sha(qreg_path)
           and q['qualification_source_sha256'] == b.sha(qsource)
           and q['constructors'] == 4 and q['gameplay_frames'] == 32 and q['native_steps'] == 20
           and q['optimizer_steps'] == q['checkpoint_writes'] == q['dev_seed_games'] == 0
           and q['interpreter'] == draft['interpreter']
           and Path(q['python_prefix']).resolve() == (b.ROOT / 'python/.venv').resolve(),
           'Actual runtime/interpreter/collector qualification differs.')
    b.verify_pins(b.read(qreg_path)['pins'])
    native = b.read(HERE / 'runtime-binding.json')
    b.verify_pins(native['pins'])
    native_home = Path(native['runtime_root']).parent
    parity = b.read(native_home / 'accepted-native-parity.json')
    b.need(parity['repeat4_exact_all_fields'] is True
           and parity['all_returned_observations_and_history_match'] is True
           and parity['repeat1_raw_elapsed_alive_and_score_arrays_match'] is True,
           'Native common-runtime parity not established within registered probe scope.')
    calibration = b.read(HERE / 'calibration.json')
    b.need(calibration['status'] == 'parent_accepted_projection'
           and calibration['limits'] == draft['limits']
           and calibration['margin_included_seconds'] <= draft['limits']['work_seconds'], 'Resource calibration differs.')
    launch.state_free(draft)
    for path in (draft['output'], draft['attempt_claim_path'], draft['launch_marker_path']):
        b.need(not os.path.lexists(path), 'Fresh confirmation markers/output required.')
    cache = Path(draft['import_policy']['pycache_prefix'])
    b.need(not os.path.lexists(cache), 'Bytecode cache already exists; refusing to reuse it.')
    cache.mkdir(mode=0o700)
    acceptance_path = HERE / 'calibration-acceptance.json'
    b.save(acceptance_path, dict(schema='control_frequency_confirmation_parent_calibration_acceptance_v1',
        status='accepted', draft_sha256=b.sha(draft_path), source_manifest_sha256=source_sha,
        limits=draft['limits'], calibration_sha256=b.sha(HERE / 'calibration.json'),
        actual_runtime_qualification_sha256=b.sha(qpath),
        limitation='Empirical runtime estimate; hard limits remain enforced. No full-game throughput claim from startup probes.'))
    source_path = PACKAGE / 'source-acceptance.json'
    b.save(source_path, b.source_acceptance_document(source_sha))
    final = finalize_registration.finalize(str(draft_path), b.sha(draft_path), str(acceptance_path), b.sha(acceptance_path))
    b.validate_static(final)
    final_path = PACKAGE / 'registration-final.json'
    b.save(final_path, final)
    paths = [reviews_path, qpath, qreg_path, qsource, acceptance_path, final_path, source_path,
             HERE / 'accept_terminal.py', Path(__file__).resolve(), HERE / 'protocol.json',
             HERE / 'user-authorization.json', HERE / 'cohort-reservation.json', HERE / 'runtime-binding.json', HERE / 'calibration.json']
    pins = {str(path): b.sha(path) for path in paths}
    pins.update(reviews['pins'])
    gate_path = PACKAGE / 'gate-acceptance.json'
    b.save(gate_path, b.approval_document(b.sha(final_path), source_sha, pins))
    b.save(HERE / 'authorization-ready.json', dict(status='parent_gates_ready_exactly_one_frozen_policy_confirmation',
        registration_path=str(final_path), registration_sha256=b.sha(final_path),
        gate_path=str(gate_path), gate_sha256=b.sha(gate_path),
        source_acceptance_path=str(source_path), source_acceptance_sha256=b.sha(source_path),
        screen_launched=False, markers_consumed=False,
        terminal_auditor=str(HERE / 'accept_terminal.py')))
    print('parent_source_native_runtime_resource_and_exact_once_gates_ready')


if __name__ == '__main__':
    main()
